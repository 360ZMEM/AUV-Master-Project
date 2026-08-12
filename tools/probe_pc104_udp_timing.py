#!/usr/bin/env python3
"""Probe packet-level Jetson--PC104/VxWorks UDP timing.

The probe sends safe zero-thrust $CKTH downlink packets and records any $AUV
uplink packets received on the local UDP socket.  It measures host-side send
cadence, uplink inter-arrival jitter, frame-number gaps, and PC104 uptime
monotonicity when the firmware exports the uptime marker.  It does not claim
one-way physical latency unless the remote firmware provides synchronized
timestamps or an explicit echo path.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import select
import socket
import statistics
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from common.protocol import (  # noqa: E402
    KEY_BOTTOM,
    KEY_CONTROL_MODE_BYTE,
    KEY_FRAME_NUMBER,
    KEY_LEFT,
    KEY_MOCK_AMD_TIMESTAMP_US,
    KEY_OBJ_ADDRESS,
    KEY_RIGHT,
    KEY_SIDE_MOTOR_RPM,
    KEY_THRUST,
    KEY_TOP,
    KEY_WORK_INSTRUCTION,
    PROTOCOL_UPLINK_SIZE,
    build_downlink_packet_from_payload,
    parse_uplink_packet,
)
from tools.experiment_contract import finalize_bundle, initialize_bundle  # noqa: E402


CSV_FIELDS = (
    "event_type",
    "sample_index",
    "elapsed_s",
    "monotonic_s",
    "remote_addr",
    "packet_size_bytes",
    "downlink_frame",
    "uplink_frame",
    "send_interval_ms",
    "uplink_interarrival_ms",
    "uplink_frame_gap",
    "pc104_uptime_ms",
    "pc104_time_valid",
    "pc104_uptime_delta_ms",
    "pc104_dvl_bi_uptime_ms",
    "pc104_dvl_bi_time_valid",
    "pc104_downlink_echo_valid",
    "pc104_downlink_echo_frame",
    "pc104_downlink_recv_uptime_ms",
    "pc104_downlink_recv_to_pack_ms",
    "downlink_echo_rtt_ms",
    "control_mode_byte",
    "work_instruction",
    "main_motor_rpm",
    "side_motor_rpm",
    "depth_m",
    "heading_deg",
    "parse_ok",
    "parse_error",
)


def percentile(values: list[float], q: float) -> float:
    finite = sorted(value for value in values if math.isfinite(value))
    if not finite:
        return float("nan")
    index = min(len(finite) - 1, max(0, round((len(finite) - 1) * q)))
    return float(finite[index])


def finite_mean(values: list[float]) -> float:
    finite = [value for value in values if math.isfinite(value)]
    return float(statistics.fmean(finite)) if finite else float("nan")


def finite_std(values: list[float]) -> float:
    finite = [value for value in values if math.isfinite(value)]
    return float(statistics.stdev(finite)) if len(finite) > 1 else 0.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote-host", default="192.168.0.101")
    parser.add_argument("--remote-port", type=int, default=21)
    parser.add_argument("--local-host", default="0.0.0.0")
    parser.add_argument("--local-port", type=int, default=52365)
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--send-rate-hz", type=float, default=10.0)
    parser.add_argument("--socket-timeout-s", type=float, default=0.02)
    parser.add_argument("--recv-buffer-size", type=int, default=2048)
    parser.add_argument("--obj-address", type=int, default=1)
    parser.add_argument("--control-mode-byte", type=int, default=238)
    parser.add_argument("--work-instruction", type=int, default=0)
    parser.add_argument("--main-motor-rpm-scale", type=float, default=15.0)
    parser.add_argument("--side-motor-rpm", type=int, default=0)
    parser.add_argument(
        "--receive-only",
        action="store_true",
        help="Do not send downlink frames; only listen for uplink timing.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
    )
    return parser.parse_args()


def build_safe_packet(
    *,
    frame_number: int,
    elapsed_us: int,
    args: argparse.Namespace,
) -> bytes:
    payload = {
        KEY_FRAME_NUMBER: frame_number & 0xFF,
        KEY_OBJ_ADDRESS: int(args.obj_address),
        KEY_CONTROL_MODE_BYTE: int(args.control_mode_byte),
        KEY_WORK_INSTRUCTION: int(args.work_instruction),
        KEY_RIGHT: 0.0,
        KEY_TOP: 0.0,
        KEY_LEFT: 0.0,
        KEY_BOTTOM: 0.0,
        KEY_THRUST: 0.0,
        KEY_SIDE_MOTOR_RPM: int(args.side_motor_rpm),
        KEY_MOCK_AMD_TIMESTAMP_US: int(max(1, elapsed_us)),
    }
    return build_downlink_packet_from_payload(
        payload,
        main_motor_rpm_scale=float(args.main_motor_rpm_scale),
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_summary(path: Path, summary: dict[str, Any]) -> None:
    fields = list(summary.keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(summary)


def summarize(rows: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    sends = [row for row in rows if row.get("event_type") == "downlink_send"]
    uplinks = [
        row
        for row in rows
        if row.get("event_type") == "uplink_recv" and int(row.get("parse_ok") or 0) == 1
    ]
    parse_errors = [row for row in rows if row.get("event_type") == "uplink_parse_error"]
    send_intervals = [
        float(row["send_interval_ms"])
        for row in sends
        if str(row.get("send_interval_ms", "")).strip()
    ]
    uplink_intervals = [
        float(row["uplink_interarrival_ms"])
        for row in uplinks
        if str(row.get("uplink_interarrival_ms", "")).strip()
    ]
    frame_gaps = [
        int(row["uplink_frame_gap"])
        for row in uplinks
        if str(row.get("uplink_frame_gap", "")).strip()
    ]
    pc104_deltas = [
        float(row["pc104_uptime_delta_ms"])
        for row in uplinks
        if str(row.get("pc104_uptime_delta_ms", "")).strip()
    ]
    valid_pc104 = [row for row in uplinks if int(row.get("pc104_time_valid") or 0) == 1]
    valid_echo = [row for row in uplinks if int(row.get("pc104_downlink_echo_valid") or 0) == 1]
    echo_rtts = [
        float(row["downlink_echo_rtt_ms"])
        for row in valid_echo
        if str(row.get("downlink_echo_rtt_ms", "")).strip()
    ]
    recv_to_pack = [
        float(row["pc104_downlink_recv_to_pack_ms"])
        for row in valid_echo
        if str(row.get("pc104_downlink_recv_to_pack_ms", "")).strip()
    ]
    elapsed = float(args.duration)
    sequence_gap_count = sum(1 for gap in frame_gaps if gap != 1)
    estimated_lost_frames = sum(max(0, gap - 1) for gap in frame_gaps)
    status = "ok" if uplinks and not parse_errors else "parse_errors" if parse_errors else "no_uplink"

    return {
        "scenario": "pc104_udp_timing_probe",
        "status": status,
        "error": "" if status == "ok" else status,
        "remote_host": args.remote_host,
        "remote_port": args.remote_port,
        "local_host": args.local_host,
        "local_port": args.local_port,
        "duration_s": elapsed,
        "target_send_rate_hz": 0.0 if args.receive_only else float(args.send_rate_hz),
        "downlink_count": len(sends),
        "uplink_count": len(uplinks),
        "parse_error_count": len(parse_errors),
        "observed_downlink_rate_hz": len(sends) / elapsed if elapsed > 0.0 else float("nan"),
        "observed_uplink_rate_hz": len(uplinks) / elapsed if elapsed > 0.0 else float("nan"),
        "downlink_interval_mean_ms": finite_mean(send_intervals),
        "downlink_interval_std_ms": finite_std(send_intervals),
        "downlink_interval_p95_ms": percentile(send_intervals, 0.95),
        "downlink_interval_max_ms": max(send_intervals) if send_intervals else float("nan"),
        "uplink_interarrival_mean_ms": finite_mean(uplink_intervals),
        "uplink_interarrival_std_ms": finite_std(uplink_intervals),
        "uplink_interarrival_p50_ms": percentile(uplink_intervals, 0.50),
        "uplink_interarrival_p95_ms": percentile(uplink_intervals, 0.95),
        "uplink_interarrival_p99_ms": percentile(uplink_intervals, 0.99),
        "uplink_interarrival_max_ms": max(uplink_intervals) if uplink_intervals else float("nan"),
        "uplink_sequence_gap_count": sequence_gap_count,
        "uplink_estimated_lost_frames": estimated_lost_frames,
        "pc104_time_valid_rate": len(valid_pc104) / len(uplinks) if uplinks else float("nan"),
        "pc104_uptime_delta_mean_ms": finite_mean(pc104_deltas),
        "pc104_uptime_delta_std_ms": finite_std(pc104_deltas),
        "pc104_uptime_delta_p95_ms": percentile(pc104_deltas, 0.95),
        "pc104_downlink_echo_valid_rate": len(valid_echo) / len(uplinks) if uplinks else float("nan"),
        "downlink_echo_rtt_p50_ms": percentile(echo_rtts, 0.50),
        "downlink_echo_rtt_p95_ms": percentile(echo_rtts, 0.95),
        "downlink_echo_rtt_max_ms": max(echo_rtts) if echo_rtts else float("nan"),
        "pc104_downlink_recv_to_pack_p50_ms": percentile(recv_to_pack, 0.50),
        "pc104_downlink_recv_to_pack_p95_ms": percentile(recv_to_pack, 0.95),
        "pc104_downlink_recv_to_pack_max_ms": max(recv_to_pack) if recv_to_pack else float("nan"),
        "firmware_echo_rtt_available": bool(echo_rtts),
        "one_way_latency_claim": False,
        "round_trip_latency_claim": False,
        "capability_gate_status": "passed" if status == "ok" else "failed",
        "effective_sample_count": len(uplinks),
        "failure_event_count": 0 if status == "ok" else 1,
        "solver_wall_time_current_ms": "not_applicable",
        "fallback_type": "not_applicable",
    }


def write_report(output_dir: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# PC104 UDP Timing Probe",
        "",
        f"- Status: `{summary['status']}`",
        f"- Remote: `{summary['remote_host']}:{summary['remote_port']}`",
        f"- Local: `{summary['local_host']}:{summary['local_port']}`",
        f"- Duration: `{float(summary['duration_s']):.1f} s`",
        f"- Downlink frames: `{summary['downlink_count']}`",
        f"- Parsed uplink frames: `{summary['uplink_count']}`",
        f"- Uplink observed rate: `{float(summary['observed_uplink_rate_hz']):.3f} Hz`",
        f"- Uplink inter-arrival p95: `{float(summary['uplink_interarrival_p95_ms']):.3f} ms`",
        f"- Sequence gap count: `{summary['uplink_sequence_gap_count']}`",
        f"- Firmware echo valid rate: `{float(summary['pc104_downlink_echo_valid_rate']):.3f}`",
        f"- Firmware echo RTT p95: `{float(summary['downlink_echo_rtt_p95_ms']):.3f} ms`",
        f"- PC104 receive-to-pack p95: `{float(summary['pc104_downlink_recv_to_pack_p95_ms']):.3f} ms`",
        "",
        "Boundary: this probe records packet-level host timing, uplink frame gaps, "
        "PC104 uptime monotonicity, and firmware echo RTT when the VxWorks echo "
        "extension is present. Without a synchronized Jetson--PC104 clock, it "
        "must not be reported as strict one-way physical latency.",
        "",
        "Primary artifacts: `udp_timing_samples.csv`, `udp_timing_summary.csv`, "
        "`metrics.csv`, `status.json`.",
        "",
    ]
    (output_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def run_probe(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    remote = (str(args.remote_host), int(args.remote_port))
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((str(args.local_host), int(args.local_port)))
    sock.setblocking(False)

    start = time.monotonic()
    end_time = start + float(args.duration)
    period_s = 1.0 / max(float(args.send_rate_hz), 1.0e-9)
    next_send = start
    frame = 0
    send_index = 0
    recv_index = 0
    prev_send_mono: float | None = None
    prev_recv_mono: float | None = None
    prev_uplink_frame: int | None = None
    prev_pc104_uptime_ms: int | None = None
    send_mono_by_frame: dict[int, float] = {}

    try:
        while time.monotonic() < end_time:
            now = time.monotonic()
            if not args.receive_only and now >= next_send:
                elapsed_s = now - start
                packet = build_safe_packet(
                    frame_number=frame,
                    elapsed_us=int(elapsed_s * 1.0e6),
                    args=args,
                )
                sock.sendto(packet, remote)
                send_mono_by_frame[int(frame)] = now
                send_index += 1
                rows.append(
                    {
                        "event_type": "downlink_send",
                        "sample_index": send_index,
                        "elapsed_s": elapsed_s,
                        "monotonic_s": now,
                        "remote_addr": f"{remote[0]}:{remote[1]}",
                        "packet_size_bytes": len(packet),
                        "downlink_frame": frame,
                        "send_interval_ms": (
                            (now - prev_send_mono) * 1000.0
                            if prev_send_mono is not None
                            else ""
                        ),
                        "control_mode_byte": int(args.control_mode_byte),
                        "work_instruction": int(args.work_instruction),
                        "parse_ok": "",
                        "parse_error": "",
                    }
                )
                prev_send_mono = now
                frame = (frame + 1) & 0xFF
                next_send += period_s
                if next_send < now - period_s:
                    next_send = now + period_s

            timeout = min(float(args.socket_timeout_s), max(0.0, end_time - time.monotonic()))
            readable, _, _ = select.select([sock], [], [], timeout)
            for readable_sock in readable:
                packet, addr = readable_sock.recvfrom(int(args.recv_buffer_size))
                recv_mono = time.monotonic()
                recv_index += 1
                elapsed_s = recv_mono - start
                base = {
                    "sample_index": recv_index,
                    "elapsed_s": elapsed_s,
                    "monotonic_s": recv_mono,
                    "remote_addr": f"{addr[0]}:{addr[1]}",
                    "packet_size_bytes": len(packet),
                    "uplink_interarrival_ms": (
                        (recv_mono - prev_recv_mono) * 1000.0
                        if prev_recv_mono is not None
                        else ""
                    ),
                }
                prev_recv_mono = recv_mono
                try:
                    telemetry = parse_uplink_packet(packet)
                except Exception as exc:
                    rows.append(
                        {
                            **base,
                            "event_type": "uplink_parse_error",
                            "parse_ok": 0,
                            "parse_error": str(exc),
                        }
                    )
                    continue

                gap = ""
                if prev_uplink_frame is not None:
                    gap = (int(telemetry.frame_number) - prev_uplink_frame) & 0xFF
                pc104_delta = ""
                if telemetry.pc104_time_valid and prev_pc104_uptime_ms is not None:
                    pc104_delta = int(telemetry.pc104_uptime_ms) - prev_pc104_uptime_ms
                if telemetry.pc104_time_valid:
                    prev_pc104_uptime_ms = int(telemetry.pc104_uptime_ms)
                prev_uplink_frame = int(telemetry.frame_number)
                echo_rtt_ms = ""
                recv_to_pack_ms = ""
                if telemetry.pc104_downlink_echo_valid:
                    echoed_frame = int(telemetry.pc104_downlink_echo_frame)
                    sent_mono = send_mono_by_frame.get(echoed_frame)
                    if sent_mono is not None and recv_mono >= sent_mono:
                        echo_rtt_ms = (recv_mono - sent_mono) * 1000.0
                    if telemetry.pc104_time_valid:
                        recv_to_pack_candidate = (
                            int(telemetry.pc104_uptime_ms)
                            - int(telemetry.pc104_downlink_recv_uptime_ms)
                        )
                        if recv_to_pack_candidate >= 0:
                            recv_to_pack_ms = recv_to_pack_candidate
                rows.append(
                    {
                        **base,
                        "event_type": "uplink_recv",
                        "uplink_frame": int(telemetry.frame_number),
                        "uplink_frame_gap": gap,
                        "pc104_uptime_ms": int(telemetry.pc104_uptime_ms),
                        "pc104_time_valid": int(telemetry.pc104_time_valid),
                        "pc104_uptime_delta_ms": pc104_delta,
                        "pc104_dvl_bi_uptime_ms": int(telemetry.pc104_dvl_bi_uptime_ms),
                        "pc104_dvl_bi_time_valid": int(telemetry.pc104_dvl_bi_time_valid),
                        "pc104_downlink_echo_valid": int(telemetry.pc104_downlink_echo_valid),
                        "pc104_downlink_echo_frame": int(telemetry.pc104_downlink_echo_frame),
                        "pc104_downlink_recv_uptime_ms": int(telemetry.pc104_downlink_recv_uptime_ms),
                        "pc104_downlink_recv_to_pack_ms": recv_to_pack_ms,
                        "downlink_echo_rtt_ms": echo_rtt_ms,
                        "control_mode_byte": int(telemetry.control_mode_byte),
                        "work_instruction": int(telemetry.work_instruction),
                        "main_motor_rpm": int(telemetry.main_motor_rpm),
                        "side_motor_rpm": int(telemetry.side_motor_rpm),
                        "depth_m": float(telemetry.depth_m),
                        "heading_deg": float(telemetry.heading_deg),
                        "parse_ok": 1,
                        "parse_error": "",
                    }
                )
    finally:
        sock.close()

    summary = summarize(rows, args)
    if int(summary["uplink_count"]) == 0:
        summary["error"] = (
            "no parsed uplink packets; check PC104 power, host interface, route, "
            "firewall, and local/remote UDP ports"
        )
    return rows, summary


def main() -> int:
    args = parse_args()
    if args.duration <= 0.0:
        raise SystemExit("--duration must be positive")
    if args.send_rate_hz <= 0.0 and not args.receive_only:
        raise SystemExit("--send-rate-hz must be positive unless --receive-only is used")

    stamp = time.strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or (
        REPO_ROOT / "results/control/pc104_udp_timing" / stamp
    )
    initialize_bundle(
        output_dir,
        experiment_id=f"pc104_udp_timing_{stamp}",
        runner="tools/probe_pc104_udp_timing.py",
        argv=sys.argv,
        data_layer="physical_pc104_udp_packet_timing",
        matrix={
            "remote_host": args.remote_host,
            "remote_port": args.remote_port,
            "local_host": args.local_host,
            "local_port": args.local_port,
            "duration_s": args.duration,
            "send_rate_hz": 0.0 if args.receive_only else args.send_rate_hz,
            "receive_only": bool(args.receive_only),
            "safe_zero_thrust_downlink": not args.receive_only,
            "one_way_latency_claim": False,
        },
        duration_s=args.duration,
        config_paths=[
            Path(__file__),
            REPO_ROOT / "common/protocol.py",
            REPO_ROOT / "brain_linux/config/params.protocol_udp_arbiter.real.yaml",
            REPO_ROOT / "brain_linux/config/params.protocol_udp_pc104.yaml",
        ],
        extra_manifest={
            "hardware_required": True,
            "safe_zero_thrust_downlink": not args.receive_only,
            "one_way_latency_claim": False,
            "round_trip_latency_claim": False,
            "notes": (
                "Use on the Jetson/PC104 subnet. Without parsed uplink frames the "
                "bundle is a connectivity negative result, not physical timing evidence."
            ),
        },
    )
    rows, summary = run_probe(args)
    write_csv(output_dir / "udp_timing_samples.csv", rows)
    write_summary(output_dir / "udp_timing_summary.csv", summary)
    finalize_bundle(output_dir, [summary])
    write_report(output_dir, summary)
    (output_dir / "probe_args.json").write_text(
        json.dumps(
            {
                key: str(value) if isinstance(value, Path) else value
                for key, value in vars(args).items()
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        "[pc104-timing] status={status} downlink={downlink} uplink={uplink} -> {path}".format(
            status=summary["status"],
            downlink=summary["downlink_count"],
            uplink=summary["uplink_count"],
            path=output_dir,
        ),
        flush=True,
    )
    return 0 if summary["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
