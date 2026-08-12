#!/usr/bin/env python3
"""Build a machine-readable ADC ENOB and 0.05 nT evidence summary."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def build_summary(source: dict[str, Any], source_path: Path) -> dict[str, Any]:
    full_scale_span_v = float(source["full_scale_span_v"])
    adc_bits = int(source["adc_bits"])
    target_output_rate_hz = int(source["target_output_rate_hz"])
    base = source["measurements"]["2000"]
    high_rate = source["measurements"]["16000"]
    best_2khz = next(
        item
        for item in high_rate["osr"]
        if int(item["output_rate_hz"]) == target_output_rate_hz
    )
    lockin = high_rate["lockin_45hz"]
    sensitivity_mv_per_ut = float(lockin["sensor_sensitivity_mv_per_ut"])
    nominal_lsb_v = full_scale_span_v / (2**adc_bits)
    nominal_lsb_nt = nominal_lsb_v * 1e6 / sensitivity_mv_per_ut
    target_sensitivity_nt = 0.05
    base_sigma_v = float(base["metrics"]["sigma_v"])
    expected_base_enob = math.log2(
        full_scale_span_v / (math.sqrt(12.0) * base_sigma_v)
    )
    reported_base_enob = float(base["metrics"]["enob_noise_bits"])
    if not math.isclose(
        expected_base_enob,
        reported_base_enob,
        rel_tol=0.0,
        abs_tol=1e-10,
    ):
        raise ValueError("source ENOB does not match the declared noise formula")

    vector_rms_nt = float(lockin["vector_rms_nt_peak"])
    quadrature_3sigma_nt = float(lockin["quadrature_3sigma_nt_peak"])
    return {
        "schema_version": 1,
        "evidence_id": "MAG-ADC-ENOB-CH4",
        "source": {
            "path": str(source_path),
            "sha256": sha256_file(source_path),
            "created_at": source.get("created_at"),
            "channel_index": source["channel_index"],
            "input_condition": "CH4 differential input shorted",
            "sample_duration_s_per_rate": source["duration_sec"],
        },
        "adc": {
            "nominal_bits": adc_bits,
            "full_scale_span_v": full_scale_span_v,
            "nominal_lsb_uv": nominal_lsb_v * 1e6,
            "nominal_lsb_equivalent_nt": nominal_lsb_nt,
            "sensor_sensitivity_mv_per_ut": sensitivity_mv_per_ut,
        },
        "wideband_noise": {
            "sample_rate_hz": 2000,
            "rms_noise_uv": base_sigma_v * 1e6,
            "noise_enob_bits": reported_base_enob,
        },
        "oversampling": {
            "input_sample_rate_hz": 16000,
            "osr": int(best_2khz["osr"]),
            "output_sample_rate_hz": int(best_2khz["output_rate_hz"]),
            "rms_noise_uv": float(best_2khz["sigma_v"]) * 1e6,
            "noise_enob_bits": float(best_2khz["enob_noise_bits"]),
            "measured_gain_bits": float(best_2khz["measured_gain_bits"]),
            "ideal_white_noise_gain_bits": float(best_2khz["ideal_gain_bits"]),
        },
        "lockin_45hz": {
            "input_sample_rate_hz": 16000,
            "output_sample_rate_hz": int(lockin["output_rate_hz"]),
            "osr": int(lockin["osr"]),
            "window_sec": float(lockin["window_sec"]),
            "window_count": int(lockin["window_count"]),
            "vector_rms_nt_peak": vector_rms_nt,
            "quadrature_3sigma_nt_peak": quadrature_3sigma_nt,
            "target_sensitivity_nt": target_sensitivity_nt,
            "vector_rms_below_target": vector_rms_nt < target_sensitivity_nt,
            "quadrature_3sigma_below_target": (
                quadrature_3sigma_nt < target_sensitivity_nt
            ),
        },
        "interpretation": {
            "supported": (
                "Under the shorted-input, 16 kHz acquisition, OSR=8 and "
                "1 s 45 Hz coherent-integration condition, the ADC subchain "
                "has noise at the 0.05 nT sensitivity scale."
            ),
            "not_supported": [
                "24-bit accuracy or 24 effective bits",
                "0.05 nT absolute accuracy",
                "complete TMR/front-end/system compliance",
                "wideband 0.05 nT noise performance",
            ],
            "concept_boundary": (
                "Sensitivity is a minimum detectable change under a stated "
                "bandwidth and decision rule; accuracy requires traceable truth "
                "and a complete uncertainty budget."
            ),
        },
    }


def write_report(path: Path, summary: dict[str, Any]) -> None:
    adc = summary["adc"]
    wideband = summary["wideband_noise"]
    oversampling = summary["oversampling"]
    lockin = summary["lockin_45hz"]
    lines = [
        "# ADC ENOB 与 0.05 nT 灵敏度量级证据摘要",
        "",
        "> 本摘要只评价短接 ADC 子链路，不是整机磁力仪准确度或标准符合性检定。",
        "",
        "| 指标 | 结果 | 解释边界 |",
        "|---|---:|---|",
        f"| 标称位数 | {adc['nominal_bits']} bit | 不是有效位数 |",
        f"| 标称 LSB | {adc['nominal_lsb_uv']:.6f} µV = "
        f"{adc['nominal_lsb_equivalent_nt']:.6f} nT | "
        "按 20 mV/µT 名义灵敏度换算 |",
        f"| 2 kHz 短接宽带 RMS | {wideband['rms_noise_uv']:.3f} µV | "
        f"噪声 ENOB={wideband['noise_enob_bits']:.3f} bit |",
        f"| 16 kHz、OSR=8 后 2 kHz RMS | "
        f"{oversampling['rms_noise_uv']:.3f} µV | "
        f"噪声 ENOB={oversampling['noise_enob_bits']:.3f} bit |",
        f"| 1 s、45 Hz 锁相矢量 RMS | "
        f"{lockin['vector_rms_nt_peak']:.5f} nT | "
        "窄带、短接输入、正弦峰值口径 |",
        f"| I/Q 单分量 3σ | "
        f"{lockin['quadrature_3sigma_nt_peak']:.5f} nT | "
        "略高于 0.05 nT，不能宣称整机达标 |",
        "",
        "标称单码对应磁场变化约为 "
        f"`{adc['nominal_lsb_equivalent_nt']:.4f} nT`，略大于 `0.05 nT`；"
        "超采样、噪声抖动和相干积分利用多样本统计量获得亚 LSB 的窄带估计。"
        "这说明廉价 ADC 的数字码宽不是最终检测下限，但不改变其宽带 ENOB 只有"
        f"约 `{wideband['noise_enob_bits']:.2f} bit` 的事实。",
        "",
        "建议论文表述：在短接输入和给定处理条件下，ADC 子链路的 45 Hz 等效"
        "磁噪声进入 0.05 nT 灵敏度量级；整机结论仍需 M1/M4 引入 TMR、模拟前端、"
        "环境背景和独立注入真值后判定。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_path = args.input.resolve()
    source = json.loads(source_path.read_text(encoding="utf-8"))
    summary = build_summary(source, source_path)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "enob_alignment_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_report(args.output_dir / "report.md", summary)
    print(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
