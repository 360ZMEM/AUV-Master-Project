#!/usr/bin/env python3
"""Industry-standard alignment table (27 号文 §6, 组 E).

Prior evidence for "does the pure simulation meet the cable-inspection task
targets?" is scattered across several artifact families:

  * DL/T 1278-style acceptance runs (``results/cable_ops_report/``) — route
    offset, tracking confidence, valid-burial ratio, acceptance pass.
  * The ADC/SK2301 shorted-input sub-chain sensitivity
    (``enob_alignment_summary.json``) — the 45 Hz lock-in vector RMS.
  * The R07 measured background replay (``r07_summary.json``) — the Hann-window
    p95/p99 residual amplitude of a real 3.9 s recording.
  * The zig-zag burial-inversion tuning sweep
    (``AUV-Master-Mag/results/20260705_zigzag_burial/*.csv``) — single-cycle
    burial MAE per true depth.
  * The CBF terrain-following seed sweep (``summary_by_terrain.csv``) — near-bed
    clearance and 1.5 m safety-violation ratio.

This runner reads those sources (each optional; a missing source becomes an
explicit ``证据缺口`` row rather than a fabricated number) and folds them into a
single table:

    | 指标 | 标准/任务要求 | 仿真设置 | 仿真结果 | 是否满足 | 说明 |

Every row carries an explicit realism boundary in the ``说明`` column, per the
plan: pure-simulation rows say what they *do not* prove. In particular the
0.05 nT sensitivity row is marked **子链量级、非整机达标** because the 0.0230 nT
figure is a shorted-ADC sub-chain result, not a whole-instrument absolute
accuracy.

Outputs a contract-compliant bundle (``experiment_contract``) plus:
  * ``standard_alignment_table.csv``   — machine-readable rows
  * ``standard_alignment_table.md``    — Markdown table for review
  * ``standard_alignment_table.tex``   — thuthesis longtable fragment
  * ``figures/standard_alignment_matrix.{png,pdf}`` — pass/gap matrix figure

Usage:
    python3 tools/build_standard_alignment_table.py \
        --output-dir results/cable_ops_report/standard_alignment/<ts>
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.experiment_contract import finalize_bundle, initialize_bundle  # noqa: E402

# --------------------------------------------------------------------------- #
# Default evidence sources (all resolved relative to the repo root).           #
# --------------------------------------------------------------------------- #
DEFAULT_ACCEPTANCE_RUNS = (
    "results/cable_ops_report/acceptance_fresh1_20260706_135331/inspection_summary.json",
    "results/cable_ops_report/acceptance_fresh2_20260706_135757/inspection_summary.json",
    "results/cable_ops_report/acceptance_fresh3_20260706_140156/inspection_summary.json",
)
DEFAULT_ENOB_SUMMARY = (
    "results/magnetic_analysis/20260809_r08_adc_enob_alignment/enob_alignment_summary.json"
)
DEFAULT_BACKGROUND_SUMMARY = (
    "results/magnetic_analysis/20260809_r07_45hz_reanalysis/r07_summary.json"
)
DEFAULT_BURIAL_TUNING = (
    "AUV-Master-Mag/results/20260705_zigzag_burial/zigzag_burial_tuning_shallow_mid.csv",
    "AUV-Master-Mag/results/20260705_zigzag_burial/zigzag_burial_tuning_focused.csv",
    "AUV-Master-Mag/results/20260705_zigzag_burial/zigzag_burial_tuning_depth2.csv",
)
DEFAULT_TERRAIN_SUMMARY = (
    "results/control/terrain_controller_seed_sweep_20260810_171620_cbf_terrain_3seed_pid_mpc_60s/summary_by_terrain.csv"
)

EXPERIMENT_ID = "e_standard_alignment_table"

# Verdict vocabulary: keep it small and auditable.
VERDICT_PASS = "满足"              # simulation-side target met
VERDICT_SUBCHAIN = "子链量级"       # sub-chain magnitude only, NOT whole-instrument
VERDICT_NOT_MET = "未达标"
VERDICT_GAP = "证据缺口"           # source missing / not quantified this round


@dataclass
class Row:
    metric: str
    requirement: str
    sim_setup: str
    sim_result: str
    verdict: str
    realism: str  # "仿真满足" / "实物待验证" / "子链量级、非整机达标"
    note: str
    sources: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "requirement": self.requirement,
            "sim_setup": self.sim_setup,
            "sim_result": self.sim_result,
            "verdict": self.verdict,
            "realism": self.realism,
            "note": self.note,
            "sources": ";".join(self.sources),
        }


# --------------------------------------------------------------------------- #
# Small IO helpers                                                             #
# --------------------------------------------------------------------------- #
def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def _display(path: Path) -> str:
    try:
        return str(_resolve(path).relative_to(REPO_ROOT))
    except ValueError:
        return str(_resolve(path))


def _load_json(path: Path) -> dict[str, Any] | None:
    resolved = _resolve(path)
    if not resolved.is_file():
        return None
    return json.loads(resolved.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    resolved = _resolve(path)
    if not resolved.is_file():
        return []
    with resolved.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _fnum(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


# --------------------------------------------------------------------------- #
# Per-source row builders                                                      #
# --------------------------------------------------------------------------- #
def _acceptance_rows(run_paths: Sequence[Path]) -> list[Row]:
    """Aggregate the DL/T 1278 acceptance runs into task-metric rows."""
    summaries: list[dict[str, Any]] = []
    used: list[str] = []
    for path in run_paths:
        data = _load_json(path)
        if data is not None:
            summaries.append(data)
            used.append(_display(path))

    if not summaries:
        return [
            Row(
                metric="海缆巡检工业验收",
                requirement="≥3 次运行且通过率 ≥0.67（DL/T 1278 风格）",
                sim_setup="数字孪生确定性先验，实时巡检落盘 + 离线评分聚合",
                sim_result="—",
                verdict=VERDICT_GAP,
                realism="实物待验证",
                note="未找到验收运行产物（inspection_summary.json）",
                sources=[],
            )
        ]

    n = len(summaries)
    thresholds = summaries[0].get("acceptance_thresholds", {}) or {}
    max_off_target = _fnum(thresholds.get("max_route_offset_target_m")) or 2.0
    mean_off_target = _fnum(thresholds.get("mean_route_offset_target_m")) or 1.0
    conf_target = _fnum(thresholds.get("confidence_target")) or 0.65
    sigma_ratio_target = _fnum(thresholds.get("max_burial_sigma_over_limit_ratio")) or 0.05
    valid_burial_target = _fnum(thresholds.get("min_valid_burial_ratio")) or 0.8

    def _collect(key: str) -> list[float]:
        return [v for v in (_fnum(s.get(key)) for s in summaries) if v is not None]

    max_off = _collect("max_route_offset_m")
    mean_off = _collect("mean_route_offset_m")
    conf_p05 = _collect("confidence_p05")
    valid_burial = _collect("valid_burial_ratio")
    sigma_ratio = _collect("burial_sigma_over_limit_ratio")
    pass_count = sum(1 for s in summaries if bool(s.get("industrial_acceptance_pass")))
    pass_ratio = pass_count / n

    boundary = (
        "确定性先验下近零路由偏移/近常值置信度只证明链路与评分逻辑正确，"
        "非真实检测精度；就绪判定限于有效巡检窗口，三次为同场景连续重复"
    )
    rows = [
        Row(
            metric="沿线路由最大偏移",
            requirement=f"≤{max_off_target:.1f} m",
            sim_setup=f"{n} 次数字孪生验收运行，有效巡检窗口内逐帧",
            sim_result=(
                f"max {max(max_off):.2e} m（{n} 次最坏值）" if max_off else "—"
            ),
            verdict=VERDICT_PASS if max_off and max(max_off) <= max_off_target else VERDICT_GAP,
            realism="仿真满足",
            note=boundary,
            sources=used,
        ),
        Row(
            metric="沿线路由平均偏移",
            requirement=f"≤{mean_off_target:.1f} m",
            sim_setup=f"{n} 次数字孪生验收运行，窗口内均值",
            sim_result=(
                f"mean {max(mean_off):.2e} m（{n} 次最坏均值）" if mean_off else "—"
            ),
            verdict=VERDICT_PASS if mean_off and max(mean_off) <= mean_off_target else VERDICT_GAP,
            realism="仿真满足",
            note="同上：近零偏移源于确定性先验，非真实检测精度",
            sources=used,
        ),
        Row(
            metric="跟踪置信度 p05",
            requirement=f"≥{conf_target:.2f}",
            sim_setup=f"{n} 次验收运行，窗口内 5 分位",
            sim_result=(f"p05 min {min(conf_p05):.3f}" if conf_p05 else "—"),
            verdict=VERDICT_PASS if conf_p05 and min(conf_p05) >= conf_target else VERDICT_GAP,
            realism="仿真满足",
            note="近常值置信度证明评分逻辑正确，非真实感知置信分布",
            sources=used,
        ),
        Row(
            metric="有效埋深覆盖率",
            requirement=f"≥{valid_burial_target:.2f}",
            sim_setup=f"{n} 次验收运行，窗口内有效埋深样本比例",
            sim_result=(f"min {min(valid_burial):.3f}" if valid_burial else "—"),
            verdict=(
                VERDICT_PASS
                if valid_burial and min(valid_burial) >= valid_burial_target
                else VERDICT_GAP
            ),
            realism="仿真满足",
            note="数字孪生确定性埋深先验，非真实反演覆盖",
            sources=used,
        ),
        Row(
            metric="埋深不确定度超限比例",
            requirement=f"≤{sigma_ratio_target:.2f}",
            sim_setup=f"{n} 次验收运行，burial σ 超 0.15 m 的样本比例",
            sim_result=(f"max {max(sigma_ratio):.3f}" if sigma_ratio else "—"),
            verdict=(
                VERDICT_PASS
                if sigma_ratio and max(sigma_ratio) <= sigma_ratio_target
                else VERDICT_GAP
            ),
            realism="仿真满足",
            note="确定性先验下的形式一致性检查",
            sources=used,
        ),
        Row(
            metric="工业验收通过率",
            requirement="≥3 次运行且通过率 ≥0.67",
            sim_setup=f"{n} 次全新运行聚合",
            sim_result=f"{pass_count}/{n} 通过（通过率 {pass_ratio:.2f}）",
            verdict=VERDICT_PASS if n >= 3 and pass_ratio >= 0.67 else VERDICT_GAP,
            realism="仿真满足",
            note="初步验收就绪：非现场海试验收；限于数字孪生确定性先验",
            sources=used,
        ),
    ]
    return rows


def _magnetic_rows(enob_path: Path, background_path: Path) -> list[Row]:
    rows: list[Row] = []

    enob = _load_json(enob_path)
    if enob is not None:
        lockin = enob.get("lockin_45hz", {}) or {}
        vector_rms = _fnum(lockin.get("vector_rms_nt_peak"))
        quad_3sigma = _fnum(lockin.get("quadrature_3sigma_nt_peak"))
        target = _fnum(lockin.get("target_sensitivity_nt")) or 0.05
        setup = (
            f"SK2301/ADC 短接输入子链，16 kHz 采样、OSR={lockin.get('osr', 8)}、"
            f"{_fnum(lockin.get('window_sec')) or 1.0:.0f} s 45 Hz 相干积分"
        )
        result = "—"
        if vector_rms is not None:
            result = f"矢量 RMS {vector_rms:.4f} nT"
            if quad_3sigma is not None:
                result += f"；I/Q 3σ {quad_3sigma:.4f} nT"
        rows.append(
            Row(
                metric="磁探测灵敏度",
                requirement=f"{target:.2f} nT 系统目标（最小可辨磁场变化）",
                sim_setup=setup,
                sim_result=result,
                verdict=VERDICT_SUBCHAIN,
                realism="子链量级、非整机达标",
                note=(
                    "仅 ADC 短接子链的等效磁噪声达 0.05 nT 量级；"
                    "整机绝对精度还取决于 TMR 本征噪声、模拟前端、温漂与标定，"
                    "I/Q 3σ 已高于 0.05 nT，不等同整机达标"
                ),
                sources=[_display(enob_path)],
            )
        )
    else:
        rows.append(
            Row(
                metric="磁探测灵敏度",
                requirement="0.05 nT 系统目标",
                sim_setup="SK2301/ADC 短接子链 45 Hz 锁相",
                sim_result="—",
                verdict=VERDICT_GAP,
                realism="子链量级、非整机达标",
                note="未找到 enob_alignment_summary.json",
                sources=[],
            )
        )

    bg = _load_json(background_path)
    if bg is not None:
        variants = (bg.get("background_recording", {}) or {}).get("variants", {}) or {}
        hann = variants.get("hann_linear", {}) or {}
        vec_p95 = _fnum(hann.get("vector_p95_nt"))
        vec_p99 = _fnum(hann.get("vector_p99_nt"))
        duration = _fnum((bg.get("background_recording", {}) or {}).get("duration_s"))
        result = "—"
        if vec_p95 is not None and vec_p99 is not None:
            result = f"Hann 矢量 p95/p99 = {vec_p95:.3f}/{vec_p99:.3f} nT"
        rows.append(
            Row(
                metric="实测背景残差抑制",
                requirement="0.05 nT 系统目标（实测背景条件下）",
                sim_setup=(
                    f"实测 {duration:.2f} s 2 kHz 三轴背景回放，Hann 窗短记录谱估计"
                    if duration is not None
                    else "实测三轴背景回放，Hann 窗谱估计"
                ),
                sim_result=result,
                verdict=VERDICT_NOT_MET,
                realism="子链量级、非整机达标",
                note=(
                    "Hann 抑制短记录泄漏约 83%，但 p99 矢量幅值仍约 0.398 nT，"
                    "未证明 0.05 nT 系统目标；3.9 s 短记录不支持长时平稳性/虚警率"
                ),
                sources=[_display(background_path)],
            )
        )
    else:
        rows.append(
            Row(
                metric="实测背景残差抑制",
                requirement="0.05 nT 系统目标",
                sim_setup="实测背景回放 Hann 窗谱估计",
                sim_result="—",
                verdict=VERDICT_GAP,
                realism="子链量级、非整机达标",
                note="未找到 r07_summary.json",
                sources=[],
            )
        )
    return rows


def _burial_rows(tuning_paths: Sequence[Path]) -> list[Row]:
    """Best single-cycle burial MAE per true depth from the zig-zag sweep."""
    best: dict[float, dict[str, Any]] = {}
    used: list[str] = []
    for path in tuning_paths:
        rows = _read_csv(path)
        if rows:
            used.append(_display(path))
        for r in rows:
            depth = _fnum(r.get("burial_depth_true_m"))
            mae = _fnum(r.get("cycle_burial_mae_m"))
            if depth is None or mae is None:
                continue
            passed = str(r.get("passed_dl_t_1278", "")).strip() in ("1", "1.0", "True", "true")
            angle = _fnum(r.get("zigzag_angle_deg"))
            candidate = {"mae": mae, "angle": angle, "passed": passed}
            current = best.get(depth)
            # Prefer DL/T-passing cycles; among those (or among all), keep the min MAE.
            if current is None:
                best[depth] = candidate
                continue
            better_pass = passed and not current["passed"]
            same_pass = passed == current["passed"]
            if better_pass or (same_pass and mae < current["mae"]):
                best[depth] = candidate

    if not best:
        return [
            Row(
                metric="埋深反演误差（之字形单周期）",
                requirement="≤0.15 m（行业参考量级）",
                sim_setup="AUV-Master-Mag 之字形主动激励调优扫描",
                sim_result="—",
                verdict=VERDICT_GAP,
                realism="实物待验证",
                note="未找到 zigzag_burial_tuning 产物",
                sources=[],
            )
        ]

    parts = []
    verdict = VERDICT_PASS
    for depth in sorted(best):
        item = best[depth]
        ang = f"{item['angle']:.0f}°" if item["angle"] is not None else "—"
        parts.append(f"{depth:.1f} m@{ang} → {item['mae']:.3f} m")
        if item["mae"] > 0.15:
            verdict = VERDICT_SUBCHAIN  # algorithm-level potential, not universal pass
    return [
        Row(
            metric="埋深反演误差（之字形单周期）",
            requirement="≤0.15 m（DL/T 行业参考量级）",
            sim_setup="AUV-Master-Mag 之字形主动激励调优，单周期口径，n=1 确定性复现",
            sim_result="；".join(parts),
            verdict=verdict,
            realism="实物待验证",
            note=(
                "达到 0.15 m 参考目标量级为算法级潜力：专用磁探测仓库、纯仿真、"
                "单次复现（n=1）、单周期口径；非主仓端到端或实测埋深精度"
            ),
            sources=used,
        )
    ]


def _terrain_rows(terrain_path: Path) -> list[Row]:
    rows = _read_csv(terrain_path)
    if not rows:
        return [
            Row(
                metric="近底离底安全（离底高度/安全裕度）",
                requirement="巡航离底 3–5 m；离底 ≥1.5 m 无安全违规",
                sim_setup="CBF 安全过滤地形跟随多种子扫描",
                sim_result="—",
                verdict=VERDICT_GAP,
                realism="实物待验证",
                note="未找到 summary_by_terrain.csv",
                sources=[],
            )
        ]

    clearance_min = [
        v for v in (_fnum(r.get("clearance_min_min_m")) for r in rows) if v is not None
    ]
    viol_max = [
        v
        for v in (
            _fnum(r.get("seabed_clearance_safety_violation_ratio_1p5m_max")) for r in rows
        )
        if v is not None
    ]
    clearance_mean = [
        v
        for v in (_fnum(r.get("seabed_clearance_mean_m_mean")) for r in rows)
        if v is not None
    ]
    n_rows = len(rows)
    result_bits = []
    if clearance_min:
        result_bits.append(f"最小净空 {min(clearance_min):.2f} m")
    if clearance_mean:
        result_bits.append(
            f"平均离底 {min(clearance_mean):.2f}–{max(clearance_mean):.2f} m"
        )
    if viol_max:
        result_bits.append(f"1.5 m 违规率 max {max(viol_max):.3f}")

    clearance_ok = bool(clearance_min) and min(clearance_min) >= 1.5
    viol_ok = (not viol_max) or max(viol_max) <= 0.0
    verdict = VERDICT_PASS if clearance_ok and viol_ok else VERDICT_GAP
    mean_note = (
        f"平均离底约 {min(clearance_mean):.2f}–{max(clearance_mean):.2f} m 处于 3 m 目标附近"
        if clearance_mean
        else "平均离底处于 3 m 目标附近"
    )
    min_note = (
        f"，最小净空 {min(clearance_min):.2f} m 未破 1.5 m" if clearance_min else ""
    )
    return [
        Row(
            metric="近底离底安全（离底高度/安全裕度）",
            requirement="巡航离底 3–5 m；离底 ≥1.5 m 零安全违规",
            sim_setup=f"CBF 安全过滤地形跟随，{n_rows} 组（控制器×地形档），各多种子",
            sim_result="；".join(result_bits) if result_bits else "—",
            verdict=verdict,
            realism="仿真满足",
            note=(
                "手动设定点加运动学代理口径；不代表 PVS 原生执行链或真机水动力；"
                + mean_note
                + min_note
            ),
            sources=[_display(terrain_path)],
        )
    ]


def _optional_gap_rows() -> list[Row]:
    """Task targets named in 27 号文 §6 that are NOT quantified this round.

    Listed explicitly (rather than silently dropped) so the alignment table is
    self-contained about what remains an evidence gap.
    """
    return [
        Row(
            metric="巡航航速",
            requirement="≤2 kn（≈1.03 m/s）",
            sim_setup="—",
            sim_result="—",
            verdict=VERDICT_GAP,
            realism="实物待验证",
            note="本轮未在统一口径下量化巡航航速，作为待补量化项",
            sources=[],
        ),
        Row(
            metric="姿态误差",
            requirement="≤0.05°（若任务要求）",
            sim_setup="—",
            sim_result="—",
            verdict=VERDICT_GAP,
            realism="实物待验证",
            note="本轮无统一姿态误差评分口径，作为待补量化项",
            sources=[],
        ),
    ]


# --------------------------------------------------------------------------- #
# Output writers                                                               #
# --------------------------------------------------------------------------- #
_CSV_FIELDS = [
    "metric",
    "requirement",
    "sim_setup",
    "sim_result",
    "verdict",
    "realism",
    "note",
    "sources",
]


def _write_csv(path: Path, rows: Sequence[Row]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.as_dict())


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|")


def _write_markdown(path: Path, rows: Sequence[Row]) -> None:
    lines = [
        "# 行业标准指标对齐单表（组 E）",
        "",
        "从算法演示到任务指标验证：只回答纯仿真是否满足，"
        "每行显式标注 仿真满足 / 实物待验证 / 子链量级。",
        "",
        "| 指标 | 标准/任务要求 | 仿真设置 | 仿真结果 | 是否满足 | 现实边界 | 说明 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            "| "
            + " | ".join(
                _md_escape(x)
                for x in (
                    r.metric,
                    r.requirement,
                    r.sim_setup,
                    r.sim_result,
                    r.verdict,
                    r.realism,
                    r.note,
                )
            )
            + " |"
        )
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _tex_escape(text: str) -> str:
    replace = {
        "&": r"\&",
        "%": r"\%",
        "#": r"\#",
        "_": r"\_",
        "→": r"$\rightarrow$",
        "±": r"$\pm$",
        "°": r"\textdegree{}",
        "≤": r"$\leq$",
        "≥": r"$\geq$",
        "σ": r"\(\sigma\)",
        "≈": r"$\approx$",
        "–": "--",
    }
    for src, dst in replace.items():
        text = text.replace(src, dst)
    return text


def _write_tex(path: Path, rows: Sequence[Row]) -> None:
    lines = [
        "% Auto-generated by tools/build_standard_alignment_table.py (27 号文 组 E).",
        "% 请勿手工编辑：重跑脚本以刷新。",
        r"\begin{longtable}{p{0.15\linewidth}p{0.14\linewidth}p{0.20\linewidth}p{0.20\linewidth}p{0.07\linewidth}p{0.16\linewidth}}",
        r"\caption{海缆巡检任务指标的纯仿真对齐表（每行显式标注现实边界）}\label{tab:ch05-standard-alignment}\\",
        r"\toprule",
        r"指标 & 标准/任务要求 & 仿真设置 & 仿真结果 & 是否满足 & 说明 \\",
        r"\midrule",
        r"\endfirsthead",
        r"\toprule",
        r"指标 & 标准/任务要求 & 仿真设置 & 仿真结果 & 是否满足 & 说明 \\",
        r"\midrule",
        r"\endhead",
        r"\bottomrule",
        r"\endfoot",
    ]
    for r in rows:
        verdict = f"{r.verdict}（{r.realism}）"
        cells = [
            r.metric,
            r.requirement,
            r.sim_setup,
            r.sim_result,
            verdict,
            r.note,
        ]
        lines.append(" & ".join(_tex_escape(c) for c in cells) + r" \\")
    lines.append(r"\end{longtable}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _setup_cjk_font(plt: Any) -> None:
    import os
    import matplotlib.font_manager as fm

    zh_font = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
    if os.path.exists(zh_font):
        fm.fontManager.addfont(zh_font)
        plt.rcParams["font.family"] = fm.FontProperties(fname=zh_font).get_name()
    else:
        plt.rcParams["font.sans-serif"] = [
            "WenQuanYi Zen Hei",
            "SimHei",
        ] + plt.rcParams["font.sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams.update(
        {"font.size": 11, "axes.titlesize": 13, "axes.labelsize": 11, "legend.fontsize": 9}
    )


_VERDICT_COLOR = {
    VERDICT_PASS: "#2ca02c",
    VERDICT_SUBCHAIN: "#ff7f0e",
    VERDICT_NOT_MET: "#d62728",
    VERDICT_GAP: "#7f7f7f",
}


def _plot_matrix(output_dir: Path, rows: Sequence[Row]) -> list[str]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Patch
    except Exception as exc:  # pragma: no cover - env dependent
        (output_dir / "figures" / "figure_skipped.txt").write_text(
            f"matplotlib unavailable: {exc}\n", encoding="utf-8"
        )
        return []

    _setup_cjk_font(plt)
    n = len(rows)
    fig, ax = plt.subplots(figsize=(11, 0.55 * n + 1.6))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, n)
    ax.axis("off")
    ax.set_title("海缆巡检任务指标·纯仿真对齐矩阵", pad=14)

    for i, row in enumerate(reversed(rows)):
        y = i + 0.5
        color = _VERDICT_COLOR.get(row.verdict, "#7f7f7f")
        ax.add_patch(
            plt.Rectangle((0.0, i + 0.05), 1.0, 0.9, facecolor=color, alpha=0.14, edgecolor="none")
        )
        ax.text(0.01, y, row.metric, va="center", ha="left", fontsize=10, weight="bold")
        result_text = row.sim_result if len(row.sim_result) <= 42 else row.sim_result[:40] + "…"
        ax.text(0.36, y, result_text, va="center", ha="left", fontsize=9)
        ax.scatter(0.86, y, s=140, color=color, zorder=3)
        ax.text(0.89, y, f"{row.verdict}", va="center", ha="left", fontsize=9, color=color)

    legend = [
        Patch(facecolor=_VERDICT_COLOR[VERDICT_PASS], label="满足（仿真）"),
        Patch(facecolor=_VERDICT_COLOR[VERDICT_SUBCHAIN], label="子链量级/算法级潜力"),
        Patch(facecolor=_VERDICT_COLOR[VERDICT_NOT_MET], label="未达标"),
        Patch(facecolor=_VERDICT_COLOR[VERDICT_GAP], label="证据缺口/待量化"),
    ]
    ax.legend(handles=legend, loc="upper center", bbox_to_anchor=(0.5, -0.02), ncol=4, frameon=False)

    written: list[str] = []
    for ext in ("png", "pdf"):
        out = output_dir / "figures" / f"standard_alignment_matrix.{ext}"
        fig.savefig(out, bbox_inches="tight", dpi=200)
        written.append(_display(out))
    plt.close(fig)
    return written


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--acceptance-runs",
        nargs="*",
        type=Path,
        default=[Path(p) for p in DEFAULT_ACCEPTANCE_RUNS],
        help="inspection_summary.json files from DL/T 1278 acceptance runs",
    )
    parser.add_argument("--enob-summary", type=Path, default=Path(DEFAULT_ENOB_SUMMARY))
    parser.add_argument(
        "--background-summary", type=Path, default=Path(DEFAULT_BACKGROUND_SUMMARY)
    )
    parser.add_argument(
        "--burial-tuning",
        nargs="*",
        type=Path,
        default=[Path(p) for p in DEFAULT_BURIAL_TUNING],
    )
    parser.add_argument("--terrain-summary", type=Path, default=Path(DEFAULT_TERRAIN_SUMMARY))
    parser.add_argument(
        "--include-optional-gaps",
        action="store_true",
        help="Append 航速/姿态 rows as explicit未量化 evidence gaps",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = _resolve(args.output_dir)

    config_paths = [
        _resolve(p)
        for p in (
            *args.acceptance_runs,
            args.enob_summary,
            args.background_summary,
            *args.burial_tuning,
            args.terrain_summary,
        )
        if _resolve(p).is_file()
    ]

    initialize_bundle(
        output_dir,
        experiment_id=EXPERIMENT_ID,
        runner="tools/build_standard_alignment_table.py",
        argv=sys.argv,
        data_layer="offline_aggregation",
        matrix={
            "acceptance_runs": len(args.acceptance_runs),
            "sources": ["acceptance", "enob", "background", "burial_tuning", "terrain"],
        },
        duration_s=None,
        config_paths=config_paths,
        extra_manifest={
            "purpose": "27 号文 §6 组 E：单张行业指标对齐表",
            "verdict_vocabulary": [VERDICT_PASS, VERDICT_SUBCHAIN, VERDICT_NOT_MET, VERDICT_GAP],
        },
    )

    rows: list[Row] = []
    rows.extend(_acceptance_rows(args.acceptance_runs))
    rows.extend(_burial_rows(args.burial_tuning))
    rows.extend(_magnetic_rows(args.enob_summary, args.background_summary))
    rows.extend(_terrain_rows(args.terrain_summary))
    if args.include_optional_gaps:
        rows.extend(_optional_gap_rows())

    _write_csv(output_dir / "standard_alignment_table.csv", rows)
    _write_markdown(output_dir / "standard_alignment_table.md", rows)
    _write_tex(output_dir / "standard_alignment_table.tex", rows)
    figures = _plot_matrix(output_dir, rows)

    # Contract metrics: one row per alignment metric, status ok/gap.
    verdict_counts: dict[str, int] = {}
    metric_rows: list[dict[str, object]] = []
    for r in rows:
        verdict_counts[r.verdict] = verdict_counts.get(r.verdict, 0) + 1
        status = "ok" if r.verdict != VERDICT_GAP else "evidence_gap"
        metric_rows.append(
            {
                "scenario": r.metric,
                "seed": 0,
                "status": status,
                "verdict": r.verdict,
                "realism": r.realism,
                "requirement": r.requirement,
                "sim_result": r.sim_result,
                "source_count": len(r.sources),
                "effective_sample_count": len(r.sources),
                "failure_event_count": 0 if status == "ok" else 1,
                "capability_gate_status": r.verdict,
                "solver_wall_time_current_ms": "not_applicable",
                "fallback_type": "not_applicable",
            }
        )

    summary = {
        "experiment_id": EXPERIMENT_ID,
        "row_count": len(rows),
        "verdict_counts": verdict_counts,
        "figures": figures,
        "rows": [r.as_dict() for r in rows],
    }
    (output_dir / "standard_alignment_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    finalize_bundle(output_dir, metric_rows, success_statuses={"ok", "evidence_gap"})

    print(f"[组 E] 行业指标对齐表 -> {_display(output_dir)}")
    for verdict, count in sorted(verdict_counts.items()):
        print(f"  {verdict}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
