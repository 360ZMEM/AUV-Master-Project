#!/usr/bin/env python3
"""Plot Direction A decoupled closed-loop online-prior-alignment diagnostics.

Consumes the /auv/cable/diagnostics JSONL extracted from a Direction A MCAP and
renders a single multi-panel figure documenting that the production node's
online prior-alignment estimator is genuinely excited and accepts the
magnetic-derived cross-track observation (reason_code=1), driving a non-zero
accumulated translation correction.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnostics-jsonl", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-confidence", type=float, default=0.35)
    return parser.parse_args()


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _series(rows: list[dict[str, Any]], key: str, default: float = 0.0) -> list[float]:
    out: list[float] = []
    for row in rows:
        value = row.get(key, default)
        try:
            out.append(float(value) if value is not None else default)
        except (TypeError, ValueError):
            out.append(default)
    return out


def main() -> None:
    args = parse_args()
    rows = _read_jsonl(_resolve(args.diagnostics_jsonl))
    if not rows:
        raise SystemExit("no diagnostics rows found")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise SystemExit(f"matplotlib unavailable: {exc}") from exc

    # 图内统一中文：注入文泉驿正黑（容器内唯一 CJK 字体），负号用 ASCII
    import os
    import matplotlib.font_manager as fm

    _zh_font = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
    if os.path.exists(_zh_font):
        fm.fontManager.addfont(_zh_font)
        plt.rcParams["font.family"] = fm.FontProperties(fname=_zh_font).get_name()
    else:
        plt.rcParams["font.sans-serif"] = ["WenQuanYi Zen Hei", "SimHei"] + plt.rcParams["font.sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams.update({"font.size": 12, "axes.titlesize": 13, "axes.labelsize": 12, "legend.fontsize": 9})

    # Build an elapsed-time axis from cumulative dt so the x-axis is seconds.
    dts = _series(rows, "prior_alignment_dt_s", 0.1)
    elapsed: list[float] = []
    acc = 0.0
    for dt in dts:
        elapsed.append(acc)
        acc += dt if dt > 0 else 0.1

    signed_ct = _series(rows, "signed_cross_track_m")
    observed_offset = _series(rows, "prior_alignment_observed_offset_m")
    prior_ct = _series(rows, "prior_alignment_prior_cross_track_m")
    translation_norm = _series(rows, "prior_alignment_translation_norm_m")
    rotation_deg = _series(rows, "prior_alignment_rotation_deg")
    quality = _series(rows, "prior_alignment_cross_track_quality")
    accepted = [bool(row.get("prior_alignment_accepted", False)) for row in rows]
    observed = [bool(row.get("prior_alignment_observed", False)) for row in rows]
    heading_corr = _series(rows, "heading_correction_deg")
    vert_sep = _series(rows, "prior_alignment_vertical_separation_m")

    accept_ratio = sum(1 for a in accepted if a) / max(1, len(accepted))
    observe_ratio = sum(1 for a in observed if a) / max(1, len(observed))
    vsep = vert_sep[len(vert_sep) // 2] if vert_sep else 0.0

    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    fig.suptitle(
        "方向 A 解耦闭环：在线先验对齐被激励且被接受\n"
        f"（垂直间距={vsep:.2f} m，观测={observe_ratio*100:.0f}% 帧，"
        f"接受={accept_ratio*100:.0f}% 帧）",
        fontsize=12,
    )

    ax = axes[0, 0]
    ax.plot(elapsed, signed_ct, label="带符号横向偏差（m）", color="tab:blue")
    ax.plot(elapsed, prior_ct, label="先验横向偏差（m）", color="tab:gray", alpha=0.7)
    ax.plot(elapsed, observed_offset, label="磁导出观测偏移（m）", color="tab:orange", alpha=0.8)
    ax.set_xlabel("经过时间（s）")
    ax.set_ylabel("横向偏差（m）")
    ax.set_title("横向偏差与磁观测对比")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)

    ax = axes[0, 1]
    ax.plot(elapsed, translation_norm, label="累计平移范数（m）", color="tab:green", linewidth=2)
    ax2 = ax.twinx()
    ax2.plot(elapsed, rotation_deg, label="累计旋转（deg）", color="tab:red", alpha=0.7)
    ax.set_xlabel("经过时间（s）")
    ax.set_ylabel("平移范数（m）", color="tab:green")
    ax2.set_ylabel("旋转（deg）", color="tab:red")
    ax.set_title("累计在线先验校正（非零）")
    ax.grid(True, alpha=0.3)
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, fontsize=8, loc="lower right")

    ax = axes[1, 0]
    ax.plot(elapsed, quality, label="横向拟合质量", color="tab:purple", linewidth=2)
    ax.axhline(args.min_confidence, color="tab:red", linestyle="--", label=f"min_confidence={args.min_confidence}")
    ax.set_xlabel("经过时间（s）")
    ax.set_ylabel("拟合质量 [0,1]")
    ax.set_ylim(0.0, 1.05)
    ax.set_title("观测质量门限（超过阈值即接受）")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)

    ax = axes[1, 1]
    accept_num = [1 if a else 0 for a in accepted]
    ax.step(elapsed, accept_num, where="post", label="先验对齐已接受", color="tab:blue")
    ax.plot(elapsed, heading_corr, label="艏向校正（deg）", color="tab:orange", alpha=0.8)
    ax.set_xlabel("经过时间（s）")
    ax.set_ylabel("接受（0/1）/ 艏向校正（deg）")
    ax.set_title("接受判定与转向校正")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)

    fig.tight_layout(rect=(0, 0, 1, 0.95))
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180)
    plt.close(fig)
    print(f"[OK] wrote {output}")
    print(f"[INFO] observed={observe_ratio:.3f} accepted={accept_ratio:.3f} vsep={vsep:.2f}m")


if __name__ == "__main__":
    main()
