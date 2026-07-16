#!/usr/bin/env python3
"""从实验产物 CSV 复算 thuthesis longtable .tex 片段（27 号文 P2-3：自动 LaTeX 表格）。

背景（见审计）：正文第 5 章的数据表全部手写 `tabular`/`longtable`，数字由产物 CSV
**手工转录**——存在"改产物忘改正文"的漂移风险，且答辩时"这张表数据怎么来的"难以一键
回溯。本工具把三张\ *机器可复算*\ 的核心表定义为产物→`.tex` 的确定性转换：

  - tab:ch05-mpc-extreme-paths  ← control_mpc_xy_yaw_extreme/best_comparison.csv
  - tab:ch05-eskf-robustness    ← thesis_sweep_aggregates/.../summary_by_scenario_mode.csv
  - tab:ch05-nis-covariance-ab  ← covariance_ab/covariance_ab_summary.csv

设计约束（复用优先 / 不过度工程化 / 诚实边界）：
  * **不强拆**现有手写表：本工具产物落 `docs/thesis/figures/experiments/auto_tables/`，
    作为\ *可复算 provenance 层*\ 与未来 `\\input` 入口；是否切换正文到 `\\input` 由人决定。
  * 生成的列结构、表头、caption/label 与正文一一对应，数字取自产物 CSV，**不新造口径**。
  * `--verify`：把生成的关键单元格数字与正文 `.tex` 现值逐一比对，任何漂移即报错退出，
    使"产物↔正文"一致性可被 CI/答辩前一键体检。
  * 纯离线读表，零随机、幂等；缺产物则该表跳过并显式报告，不编造数字。

用法：
    python3 tools/build_thesis_data_tables.py                 # 生成 .tex 到 auto_tables/
    python3 tools/build_thesis_data_tables.py --verify        # 只校验正文数字未漂移
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FIG_ROOT = REPO_ROOT / "docs" / "thesis" / "figures" / "experiments"
DEFAULT_OUT_DIR = FIG_ROOT / "auto_tables"
THESIS_CHAP05 = REPO_ROOT / "thuthesis" / "data" / "auv-chap05.tex"

# 产物源（相对仓库根）。
SRC_MPC_EXTREME = FIG_ROOT / "control_mpc_xy_yaw_extreme" / "best_comparison.csv"
SRC_ESKF_SWEEP = (
    REPO_ROOT
    / "results"
    / "thesis_sweep_aggregates"
    / "20260612_170618_p1_sensor_3seed"
    / "summary_by_scenario_mode.csv"
)
SRC_COVARIANCE_AB = FIG_ROOT / "covariance_ab" / "covariance_ab_summary.csv"


# --------------------------------------------------------------------------- #
# 通用工具                                                                      #
# --------------------------------------------------------------------------- #
def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _f(value: object) -> float:
    return float(str(value))


def _display(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


@dataclass
class TableSpec:
    """一张表的定义：产物源 + caption/label + 列头 + 行构造。"""

    key: str
    source: Path
    caption: str
    label: str
    colspec: str
    header: list[str]
    build_rows: Callable[[list[dict[str, str]]], list[list[str]]]
    # 用于 --verify 的关键单元格：从生成行中抽取应在正文出现的字符串。
    verify_tokens: Callable[[list[list[str]]], list[str]] = field(
        default=lambda rows: []
    )


# --------------------------------------------------------------------------- #
# 表 1：MPC 极端平面路径（tab:ch05-mpc-extreme-paths）                          #
# --------------------------------------------------------------------------- #
_MPC_SCENARIO_ZH = {
    "s_turn_long_wave": "长波 S 弯（60 m / 7 m）",
    "hairpin_180deg": "发卡 180° 掉头",
    "s_turn_short_wave": "短波 S 弯",
    "chicane_90deg": "直角折弯",
}
# 正文行序（与 tab:ch05-mpc-extreme-paths 逐行一致）。
_MPC_ORDER = ["s_turn_long_wave", "hairpin_180deg", "s_turn_short_wave", "chicane_90deg"]


def _mpc_conclusion(key: str, red_yaw: str, red_los: str) -> str:
    """结论列：沿用正文口径的定性判断（不新造），带缩减百分比。"""
    if key == "s_turn_long_wave":
        return f"MPC 均优（较仅航向 {red_yaw}、较 LOS {red_los}）"
    if key == "hairpin_180deg":
        return f"MPC 均优（{red_yaw}）"
    if key == "s_turn_short_wave":
        return f"MPC 较仅航向 {red_yaw}、与 LOS 持平"
    if key == "chicane_90deg":
        return "诚实边界：直角折弯上 LOS 前瞻最优"
    return ""


def _pct(value: float) -> str:
    """把 reduction 百分比格式化为带正负号的整数百分比（−41\\%）。"""
    sign = "\u2212" if value < 0 else ""  # U+2212 MINUS SIGN，与正文一致
    return f"{sign}{abs(value):.0f}\\%"


def build_mpc_extreme(rows: list[dict[str, str]]) -> list[list[str]]:
    by_key = {r["scenario"]: r for r in rows}
    out: list[list[str]] = []
    for key in _MPC_ORDER:
        r = by_key[key]
        pid = _f(r["pid_lateral_rmse_m"])
        los = _f(r["los_lateral_rmse_m"])
        mpc = _f(r["mpc_lateral_rmse_m"])
        red_yaw = _pct(_f(r["lateral_rmse_reduction_vs_yaw_pct"]))
        red_los = _pct(_f(r["lateral_rmse_reduction_vs_los_pct"]))
        out.append(
            [
                _MPC_SCENARIO_ZH[key],
                f"{pid:.3f} m",
                f"{los:.3f} m",
                f"{mpc:.3f} m",
                _mpc_conclusion(key, red_yaw, red_los),
            ]
        )
    return out


# --------------------------------------------------------------------------- #
# 表 2：ES-EKF 多扰动鲁棒性（tab:ch05-eskf-robustness）                         #
# --------------------------------------------------------------------------- #
_ESKF_SCENARIO_ZH = {
    "dvl_dropout_10": "DVL 丢包 10\\%",
    "dvl_dropout_30": "DVL 丢包 30\\%",
    "dvl_dropout_60": "DVL 丢包 60\\%",
    "dvl_dropout_90": "DVL 丢包 90\\%",
    "mag_distortion_light": "磁畸变·轻度",
    "mag_distortion_heavy": "磁畸变·重度",
    "sonar_clutter": "声呐杂波",
    "combined_stress": "综合压力",
}
_ESKF_ORDER = list(_ESKF_SCENARIO_ZH.keys())


def _pm(mean: float, std: float, unit: str = " m", digits: int = 2) -> str:
    """均值±标准差，带 \\allowbreak 断行（与正文格式一致）。"""
    return f"{mean:.{digits}f}\\allowbreak{{}}\u00b1{std:.{digits}f}{unit}"


def build_eskf_robustness(rows: list[dict[str, str]]) -> list[list[str]]:
    by_key = {r["scenario"]: r for r in rows}
    out: list[list[str]] = []
    for key in _ESKF_ORDER:
        r = by_key[key]
        n_ok = int(_f(r["runs_ok"]))
        n_total = int(_f(r["runs_total"]))
        out.append(
            [
                _ESKF_SCENARIO_ZH[key],
                f"{n_ok}/{n_total}",
                _pm(_f(r["xy_rmse_mean"]), _f(r["xy_rmse_std"])),
                _pm(_f(r["z_rmse_mean"]), _f(r["z_rmse_std"])),
                _pm(_f(r["cep50_mean"]), _f(r["cep50_std"])),
                _pm(_f(r["max_drift_mean"]), _f(r["max_drift_std"])),
            ]
        )
    return out


# --------------------------------------------------------------------------- #
# 表 3：分源 NIS 与协方差 A/B（tab:ch05-nis-covariance-ab）                     #
# --------------------------------------------------------------------------- #
_ARM_ZH = {
    "A_baseline_default": "基线（默认全局）",
    "B_per_source_gating": "分源门控",
    "C_per_source_tuned": "分源门控+深度整定",
}
_SOURCE_ZH = {"depth": "深度（1 维）", "dvl_world": "DVL（3 维）"}
_ARM_ORDER = ["A_baseline_default", "B_per_source_gating", "C_per_source_tuned"]
_SOURCE_ORDER = ["depth", "dvl_world"]


def build_covariance_ab(rows: list[dict[str, str]]) -> list[list[str]]:
    by_key = {(r["arm"], r["source"]): r for r in rows}
    out: list[list[str]] = []
    for arm in _ARM_ORDER:
        for source in _SOURCE_ORDER:
            r = by_key[(arm, source)]
            out.append(
                [
                    _ARM_ZH[arm],
                    _SOURCE_ZH[source],
                    f"{_f(r['nis_per_dof_mean']):.3f}",
                    f"{_f(r['coverage_95']):.3f}",
                    f"{_f(r['upper_exceed']):.3f}",
                    f"{_f(r['applied_r_scale_mean']):.3f}",
                ]
            )
    return out


# --------------------------------------------------------------------------- #
# 表定义注册表                                                                  #
# --------------------------------------------------------------------------- #
SPECS: list[TableSpec] = [
    TableSpec(
        key="mpc_extreme_paths",
        source=SRC_MPC_EXTREME,
        caption="模型预测控制极端平面路径公平口径结果",
        label="tab:ch05-mpc-extreme-paths",
        colspec=(
            "@{}"
            r">{\raggedright\arraybackslash}p{(\linewidth - 8\tabcolsep) * \real{0.1667}}"
            r">{\raggedleft\arraybackslash}p{(\linewidth - 8\tabcolsep) * \real{0.2222}}"
            r">{\raggedleft\arraybackslash}p{(\linewidth - 8\tabcolsep) * \real{0.2222}}"
            r">{\raggedleft\arraybackslash}p{(\linewidth - 8\tabcolsep) * \real{0.2222}}"
            r">{\raggedright\arraybackslash}p{(\linewidth - 8\tabcolsep) * \real{0.1667}}@{}"
        ),
        header=["场景", "仅航向 PID 横向 RMSE", "LOS 横向 RMSE", "MPC 最优横向 RMSE", "结论"],
        build_rows=build_mpc_extreme,
        verify_tokens=lambda rows: [rows[0][1], rows[0][2], rows[0][3], rows[3][2]],
    ),
    TableSpec(
        key="eskf_robustness",
        source=SRC_ESKF_SWEEP,
        caption="误差状态扩展卡尔曼滤波多扰动场景定位结果",
        label="tab:ch05-eskf-robustness",
        colspec=(
            "@{}"
            r">{\raggedright\arraybackslash}p{(\linewidth - 10\tabcolsep) * \real{0.1304}}"
            r">{\raggedleft\arraybackslash}p{(\linewidth - 10\tabcolsep) * \real{0.1739}}"
            r">{\raggedleft\arraybackslash}p{(\linewidth - 10\tabcolsep) * \real{0.1739}}"
            r">{\raggedleft\arraybackslash}p{(\linewidth - 10\tabcolsep) * \real{0.1739}}"
            r">{\raggedleft\arraybackslash}p{(\linewidth - 10\tabcolsep) * \real{0.1739}}"
            r">{\raggedleft\arraybackslash}p{(\linewidth - 10\tabcolsep) * \real{0.1739}}@{}"
        ),
        header=["场景", "成功/总数", "水平 RMSE", "深度 RMSE", "圆概率误差", "最大漂移"],
        build_rows=build_eskf_robustness,
        # 校验前两行的水平/深度 RMSE 字符串确在正文出现。
        verify_tokens=lambda rows: [rows[0][2], rows[0][3], rows[1][2]],
    ),
    TableSpec(
        key="nis_covariance_ab",
        source=SRC_COVARIANCE_AB,
        caption="分源标准 NIS 与一致性校准 A/B（独立对照，不改主线默认协方差）",
        label="tab:ch05-nis-covariance-ab",
        colspec="@{}llrrrr@{}",
        header=["整定臂", "观测源（自由度）", "NIS/自由度均值", "95\\%带覆盖率", "上界超限率", "实际 R 缩放均值"],
        build_rows=build_covariance_ab,
        # 基线深度 7.205 与 DVL 0.119 是全文引用的锚点，必须逐位复现。
        verify_tokens=lambda rows: [rows[0][2], rows[0][3], rows[0][4], rows[1][2]],
    ),
]


# --------------------------------------------------------------------------- #
# longtable 渲染                                                                #
# --------------------------------------------------------------------------- #
def render_longtable(spec: TableSpec, rows: list[list[str]]) -> str:
    header_line = " & ".join(spec.header) + r" \\"
    lines = [
        f"% 自动生成 by tools/build_thesis_data_tables.py（27 号文 P2-3）。请勿手工编辑：重跑脚本刷新。",
        f"% 源产物：{_display(spec.source)}",
        r"\begin{longtable}[]{" + spec.colspec + "}",
        rf"\caption{{{spec.caption}}}\label{{{spec.label}}}\tabularnewline",
        r"\toprule\noalign{}",
        header_line,
        r"\midrule\noalign{}",
        r"\endfirsthead",
        r"\toprule\noalign{}",
        header_line,
        r"\midrule\noalign{}",
        r"\endhead",
        r"\bottomrule\noalign{}",
        r"\endlastfoot",
    ]
    for row in rows:
        lines.append(" & ".join(row) + r" \\")
    lines.append(r"\end{longtable}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# 验证：生成值 vs 正文现值                                                      #
# --------------------------------------------------------------------------- #
def _normalize(text: str) -> str:
    """把 TeX 空白/断行标记归一化，便于 token 子串比对。"""
    text = text.replace(r"\allowbreak{}", "").replace(r"\allowbreak", "")
    text = text.replace("\u2212", "-")  # MINUS SIGN -> hyphen
    text = re.sub(r"\s+", "", text)
    return text


def verify_against_thesis(specs_rows: list[tuple[TableSpec, list[list[str]]]]) -> list[str]:
    """返回漂移描述列表；空列表表示正文与产物一致。"""
    if not THESIS_CHAP05.is_file():
        return [f"未找到正文 {_display(THESIS_CHAP05)}，跳过校验"]
    body = _normalize(THESIS_CHAP05.read_text(encoding="utf-8"))
    drifts: list[str] = []
    for spec, rows in specs_rows:
        for token in spec.verify_tokens(rows):
            needle = _normalize(token)
            if needle and needle not in body:
                drifts.append(f"[{spec.label}] 产物值 '{token}' 未在正文出现（可能已漂移）")
    return drifts


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUT_DIR,
                   help=f"输出目录（缺省 {_display(DEFAULT_OUT_DIR)}）")
    p.add_argument("--verify", action="store_true",
                   help="只把产物值与正文现值比对，发现漂移即非零退出（不写文件）")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    specs_rows: list[tuple[TableSpec, list[list[str]]]] = []
    missing: list[str] = []
    for spec in SPECS:
        if not spec.source.is_file():
            missing.append(f"[{spec.label}] 缺源产物 {_display(spec.source)}，跳过")
            continue
        rows = spec.build_rows(_read_csv(spec.source))
        specs_rows.append((spec, rows))

    for msg in missing:
        print(f"[data-tables][warn] {msg}")

    if args.verify:
        drifts = verify_against_thesis(specs_rows)
        if drifts:
            print("[data-tables][FAIL] 正文与产物存在漂移：")
            for d in drifts:
                print(f"  - {d}")
            return 1
        print(f"[data-tables][OK] {len(specs_rows)} 张表的关键单元格与正文一致，无漂移。")
        return 0

    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for spec, rows in specs_rows:
        tex = render_longtable(spec, rows)
        out_path = out_dir / f"{spec.key}.tex"
        out_path.write_text(tex, encoding="utf-8")
        written.append(_display(out_path))
        print(f"[data-tables] {spec.label} ({len(rows)} 行) -> {_display(out_path)}")

    # 顺带跑一遍校验，给出产物↔正文一致性提示（不因漂移失败，仅告警）。
    drifts = verify_against_thesis(specs_rows)
    if drifts:
        print("[data-tables][warn] 生成完成，但检出正文与产物差异（建议核对）：")
        for d in drifts:
            print(f"  - {d}")
    else:
        print("[data-tables][OK] 生成完成，且关键单元格与正文一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
