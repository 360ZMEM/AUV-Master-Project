#!/usr/bin/env python3
"""Legacy Markdown-to-TeX converter retained for historical reproduction.

The maintained thesis sources are the files under ``thuthesis/data``. This
tool is read-only by default and must never run implicitly from a build.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class TableSpec:
    label: str
    caption: str
    font_size: str | None = None


@dataclass(frozen=True)
class HeadingSpec:
    title: str
    label: str


@dataclass(frozen=True)
class MathSpec:
    latex: str


@dataclass(frozen=True)
class ChapterSpec:
    key: str
    title: str
    source: Path
    target: Path
    section_prefix: str
    label_prefix: str
    tables: tuple[TableSpec, ...] = ()
    unnumbered_headings: tuple[HeadingSpec, ...] = ()
    display_math: tuple[MathSpec, ...] = ()
    code_languages: tuple[str, ...] = ()


CHAPTERS = {
    "1": ChapterSpec(
        key="1",
        title="绪论",
        source=ROOT / "docs/thesis/paper/01_background_and_significance.md",
        target=ROOT / "thuthesis/data/auv-chap01.tex",
        section_prefix="1",
        label_prefix="ch01",
        tables=(
            TableSpec(
                "tab:ch01-cable-inspection-equipment",
                "典型海缆探测载荷与自主巡检平台的能力分层",
                font_size="scriptsize",
            ),
        ),
    ),
    "2": ChapterSpec(
        key="2",
        title="系统设计与建模",
        source=ROOT / "docs/thesis/paper/02_system_design.md",
        target=ROOT / "thuthesis/data/auv-chap02.tex",
        section_prefix="2",
        label_prefix="ch02",
        tables=(
            TableSpec("tab:ch02-requirements", "任务需求与验证状态"),
            TableSpec(
                "tab:ch02-hardware",
                "AUV 多源异构系统核心硬件配置与标准支撑",
            ),
            TableSpec("tab:ch02-layers", "五层软件架构职责"),
            TableSpec("tab:ch02-backends", "仿真后端与实物层能力边界"),
            TableSpec("tab:ch02-magnetic-effects", "三相海缆漏磁效应及探测影响"),
            TableSpec("tab:ch02-calibration", "磁传感器空间标定项"),
            TableSpec(
                "tab:ch02-lever-arm-results",
                "杆臂效应与安装角校正前后几何误差对比"
                "（缩比台架/转台标定结果，实物海试标定待补）",
            ),
            TableSpec("tab:ch02-udp-frames", "双脑 UDP 二进制协议帧"),
            TableSpec("tab:ch02-subconn", "SubConn DBH13M 穿舱接口信号映射"),
            TableSpec("tab:ch02-modes", "上位机工作模式与安全通信路径"),
        ),
    ),
    "3": ChapterSpec(
        key="3",
        title="声磁协同状态估计",
        source=ROOT / "docs/thesis/paper/03_state_estimation.md",
        target=ROOT / "thuthesis/data/auv-chap03.tex",
        section_prefix="3",
        label_prefix="ch03",
        tables=(
            TableSpec("tab:ch03-sensor-rates", "传感器系统更新率与传输时延特征"),
            TableSpec("tab:ch03-alignment", "传感器安装偏差与补偿状态"),
        ),
    ),
    "4": ChapterSpec(
        key="4",
        title="决策与控制系统",
        source=ROOT / "docs/thesis/paper/04new_decision_and_control.md",
        target=ROOT / "thuthesis/data/auv-chap04.tex",
        section_prefix="4",
        label_prefix="ch04",
        tables=(
            TableSpec("tab:ch04-control-layers", "决策与控制系统分层职责"),
            TableSpec("tab:ch04-bt-nodes", "行为树关键条件与行动节点"),
            TableSpec("tab:ch04-emergency-priority", "应急故障触发条件与响应行为"),
            TableSpec("tab:ch04-hard-constraints", "模型预测控制硬约束体系"),
            TableSpec(
                "tab:ch04-rate-band-constraints",
                "模型预测控制速率与带宽扩展约束",
            ),
        ),
        unnumbered_headings=(
            HeadingSpec("行为树 vs 状态机对比图组", "sec:ch04-bt-fsm-figures"),
            HeadingSpec("MPC 控制效果实验图组", "sec:ch04-mpc-response-figures"),
            HeadingSpec(
                "PID/内层执行器控制效果图组",
                "sec:ch04-pid-response-figures",
            ),
        ),
        display_math=(
            MathSpec(
                r"""\begin{equation}
\mathbf{X} = [x,\ y,\ z,\ \psi,\ u,\ w]^{\mathsf{T}}
\label{eq:ch04-state-vector}
\end{equation}"""
            ),
            MathSpec(
                r"""\begin{equation}
\mathbf{X} = [x,\ y,\ z,\ \psi,\ u,\ w]^{\mathsf{T}}
\label{eq:ch04-mpc-state}
\end{equation}"""
            ),
            MathSpec(
                r"""\begin{equation}
\mathbf{U} = [\psi_{\mathrm{cmd}},\ z_{\mathrm{cmd}},\ T_{\mathrm{cmd}}]^{\mathsf{T}}
\label{eq:ch04-mpc-control}
\end{equation}"""
            ),
            MathSpec(
                r"""\begin{equation}
\begin{aligned}
\dot{x} &= u\cos\psi, &
\dot{y} &= u\sin\psi, \\
\dot{z} &= -u\sin\theta+w\cos\theta, &
\dot{\psi} &= k_{\psi}(\psi_{\mathrm{cmd}}-\psi), \\
\dot{u} &= \frac{T_{\mathrm{actual}}-d_u u|u|}{m_u}, &
\dot{w} &= \frac{-d_w w+k_z(z_{\mathrm{cmd}}-z)+f_b}{m_w}.
\end{aligned}
\label{eq:ch04-continuous-model}
\end{equation}"""
            ),
            MathSpec(
                r"""\begin{equation}
\mathbf{X}_{k+1}
= \mathbf{X}_k+\Delta t\,f(\mathbf{X}_k,\mathbf{U}_k)
\label{eq:ch04-euler-discretization}
\end{equation}"""
            ),
            MathSpec(
                r"""\begin{equation}
\min J = J_{\mathrm{tracking}}+J_{\mathrm{control}}
\label{eq:ch04-cost-decomposition}
\end{equation}"""
            ),
            MathSpec(
                r"""\begin{equation}
\begin{aligned}
J_{\mathrm{tracking}}=\sum_k \bigl[
&w_x(x_k-x_{\mathrm{ref}})^2+w_y(y_k-y_{\mathrm{ref}})^2 \\
&+w_z(z_k-z_{\mathrm{ref}})^2+w_\psi(\psi_k-\psi_{\mathrm{ref}})^2 \\
&+w_u(u_k-u_{\mathrm{ref}})^2+w_w(w_k-w_{\mathrm{ref}})^2
\bigr].
\end{aligned}
\label{eq:ch04-tracking-cost}
\end{equation}"""
            ),
            MathSpec(
                r"""\begin{equation}
J_{\mathrm{control}}
=\sum_k s_u(c)\left(
W_{\psi_{\mathrm{cmd}}}\psi_{\mathrm{cmd},k}^2
+W_{z_{\mathrm{cmd}}}z_{\mathrm{cmd},k}^2
+W_T T_{\mathrm{cmd},k}^2
\right)
\label{eq:ch04-control-cost}
\end{equation}"""
            ),
            MathSpec(
                r"""\begin{equation}
\rho(c)=(1-c)^\alpha,
\qquad
w_e(c)=w_{e,0}\left[1+s_e\rho(c)\right]
\label{eq:ch04-confidence-weight}
\end{equation}"""
            ),
            MathSpec(
                r"""\begin{equation}
\begin{aligned}
\sigma(x)&=\frac{1}{1+\exp(-x)},\\
s_u(c)&=\gamma_u+(1-\gamma_u)\sigma\!\left(k(c-c_0)\right).
\end{aligned}
\label{eq:ch04-control-scale}
\end{equation}"""
            ),
        ),
    ),
    "5": ChapterSpec(
        key="5",
        title="实验与结果讨论",
        source=ROOT / "docs/thesis/paper/05new_experiments_and_discussion.md",
        target=ROOT / "thuthesis/data/auv-chap05.tex",
        section_prefix="5",
        label_prefix="ch05",
        tables=(
            TableSpec(
                "tab:ch05-simulation-implementation",
                "仿真实施架构的运行层次与数据责任",
            ),
            TableSpec("tab:ch05-scenarios", "仿真场景库及扰动配置"),
            TableSpec(
                "tab:ch05-mag-calibration",
                "磁传感器杆臂与安装角仿真标定结果",
            ),
            TableSpec("tab:ch05-evidence-inventory", "已完成实验及证据边界汇总"),
            TableSpec(
                "tab:ch05-terrain-main",
                "地形跟随真口径主结果（每组单次运行）",
            ),
            TableSpec(
                "tab:ch05-terrain-ablation",
                "PID 地形跟随三档多种子消融结果",
            ),
            TableSpec(
                "tab:ch05-mpc-extreme-paths",
                "模型预测控制极端平面路径公平口径结果",
            ),
            TableSpec(
                "tab:ch05-eskf-robustness",
                "误差状态扩展卡尔曼滤波多扰动场景定位结果",
            ),
            TableSpec(
                "tab:ch05-nis-covariance",
                "归一化新息平方与协方差自适应聚合结果",
            ),
            TableSpec(
                "tab:ch05-uampc-localization",
                "不确定性感知控制主消融定位侧结果",
            ),
            TableSpec(
                "tab:ch05-uampc-control",
                "不确定性感知控制主消融控制侧结果",
                font_size="scriptsize",
            ),
            TableSpec(
                "tab:ch05-cable-algorithm-boundaries",
                "专用仓库算法级电缆探测边界摘要",
            ),
            TableSpec(
                "tab:ch05-distorted-prior",
                "先验畸变开环回放与六自由度闭环失效传导结果",
            ),
            TableSpec(
                "tab:ch05-decoupled-loop",
                "解耦轻量闭环关键量",
            ),
            TableSpec(
                "tab:ch05-closed-loop-acceptance",
                "六自由度闭环在线修正后的窗口内验收结果",
            ),
            TableSpec("tab:ch05-extreme-s-curve", "连续 S 弯极端场景设定"),
            TableSpec("tab:ch05-extreme-hairpin", "发卡掉头极端场景设定"),
            TableSpec("tab:ch05-extreme-slope", "陡坡穿越极端场景设定"),
            TableSpec("tab:ch05-extreme-burial-gap", "埋设间断极端场景设定"),
            TableSpec("tab:ch05-extreme-cross-current", "横流冲击极端场景设定"),
            TableSpec("tab:ch05-extreme-combined", "综合极端场景设定"),
            TableSpec(
                "tab:ch05-proxy-core-smoke",
                "三类核心代理电缆场景冒烟结果",
            ),
            TableSpec(
                "tab:ch05-proxy-full-smoke",
                "六类代理电缆场景冒烟结果",
            ),
        ),
        unnumbered_headings=(
            HeadingSpec("地形跟随实验图组", "sec:ch05-terrain-figures"),
            HeadingSpec("MPC 极端路径轨迹图组", "sec:ch05-mpc-extreme-figures"),
        ),
    ),
    "6": ChapterSpec(
        key="6",
        title="结论与展望",
        source=ROOT / "docs/thesis/paper/06_conclusion_and_outlook.md",
        target=ROOT / "thuthesis/data/auv-chap06.tex",
        section_prefix="6",
        label_prefix="ch06",
    ),
}

DOCUMENT_ORDER = ("1", "2", "3", "4", "5", "6")

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
NUMBERED_TITLE_RE = re.compile(r"^((?:\d+|[A-Z])(?:\.\d+)*)\s+(.+)$")
FENCE_RE = re.compile(r"^```(?P<language>.*)$")
IMAGE_RE = re.compile(r"^!\[(?P<alt>.*)]\((?P<path>[^)]+)\)\s*$")
FIGURE_CAPTION_RE = re.compile(
    r"^\*\*图\s+\d+-\d+\s*(?P<caption>.*?)\*\*\s*"
    r"\\label\{(?P<label>[^}]+)\}\s*$"
)
LEGACY_TABLE_CAPTION_RE = re.compile(r"^\*表\s+\d+-\d+\s+.*\*\s*$")
REFERENCE_HEADING_RE = re.compile(r"^##\s+参考文献\s*$")
ASCII_QUOTE_RE = re.compile(r'"([^"\n]+)"')
TEXTTT_RE = re.compile(r"\\texttt\{((?:\\[{}]|[^{}])*)\}")
SAMPLE_SIZE_RE = re.compile(
    r"(?<!\\\()(?<![A-Za-z0-9_])(?P<symbol>[nN])=(?P<value>\d+)"
)
FIGURE_WITH_BARRIER_RE = re.compile(
    r"\\begin\{figure\}\[htbp\].*?\\end\{figure\}\n\\FloatBarrier",
    re.DOTALL,
)

COMPACT_FIGURE_GROUPS = (
    (
        "fig:ch04-mpc-depth-step",
        "fig:ch04-mpc-heading-step",
        "fig:ch04-mpc-cable-depth",
        "fig:ch04-mpc-cable-heading",
        "fig:ch04-mpc-summary",
    ),
    (
        "fig:ch04-pid-depth-step",
        "fig:ch04-pid-yaw-step",
        "fig:ch04-pid-depth-sine",
        "fig:ch04-pid-yaw-sine",
        "fig:ch04-pid-summary",
    ),
    (
        "fig:ch05-mpc-long-s",
        "fig:ch05-mpc-short-s",
        "fig:ch05-mpc-hairpin",
        "fig:ch05-mpc-chicane",
    ),
)


def source_hash(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def latex_image_path(markdown_path: str) -> str:
    prefix = "../figures/"
    if not markdown_path.startswith(prefix):
        raise ValueError(f"unsupported thesis image path: {markdown_path}")
    relative = markdown_path[len(prefix) :]
    pdf_candidate = ROOT / "docs/thesis/figures" / Path(relative).with_suffix(".pdf")
    if pdf_candidate.exists():
        return str(Path(relative).with_suffix(".pdf"))
    return relative


def skip_blank_lines(lines: list[str], index: int) -> int:
    while index < len(lines) and not lines[index].strip():
        index += 1
    return index


def normalize_chinese_prose(line: str, *, heading: bool = False) -> str:
    normalized = ASCII_QUOTE_RE.sub(lambda match: f"“{match.group(1)}”", line)
    # Paired Chinese em dashes become six consecutive hyphens in Pandoc's
    # LaTeX output. Use ordinary Chinese punctuation for prose as the default.
    normalized = normalized.replace("——", "：" if heading else "，")
    normalized = normalized.replace(" — ", "：")
    return normalized.replace(r"~\ref", r"\nobreakspace{}\ref")


def allow_code_breaks(match: re.Match[str]) -> str:
    content = match.group(1)
    is_yaml = content.endswith(".yaml")
    has_breakpoint = (
        "/" in content
        or r"\_" in content
        or "." in content
        or "=" in content
        or re.search(r"(?<=[a-z])(?=[A-Z])", content)
    )
    if len(content) < 16 or not has_breakpoint:
        return match.group(0)
    content = content.replace(r"\_", r"\_\allowbreak{}")
    content = content.replace("/", r"/\allowbreak{}")
    content = content.replace(".", r".\allowbreak{}")
    content = content.replace("=", r"=\allowbreak{}")
    content = re.sub(
        r"(?<=[a-z])(?=[A-Z])",
        lambda _: r"\allowbreak{}",
        content,
    )
    rendered = rf"\texttt{{{content}}}"
    return rf"{{\small {rendered}}}" if is_yaml else rendered


def compact_consecutive_figure_groups(latex: str) -> str:
    """Allow selected result figures to share pages without changing numbering."""
    compact_labels = {
        label for group in COMPACT_FIGURE_GROUPS for label in group
    }
    group_ends = {group[-1] for group in COMPACT_FIGURE_GROUPS}
    output: list[str] = []
    cursor = 0

    for match in FIGURE_WITH_BARRIER_RE.finditer(latex):
        block = match.group(0)
        label_match = re.search(r"\\label\{([^}]+)\}", block)
        if not label_match or label_match.group(1) not in compact_labels:
            continue

        label = label_match.group(1)
        compact_block = block.replace(
            r"width=0.95\linewidth",
            r"width=0.80\linewidth",
            1,
        )
        if label not in group_ends:
            compact_block = compact_block.removesuffix("\n\\FloatBarrier")

        output.append(latex[cursor : match.start()])
        output.append(compact_block)
        cursor = match.end()

    if not output:
        return latex
    output.append(latex[cursor:])
    return "".join(output)


def postprocess_latex(latex: str, *, academic_stats: bool = False) -> str:
    replacements = {
        r"\texttt{α\ ∈\ {[}1,\ α\_max{]}}": r"\(\alpha \in [1,\alpha_{\max}]\)",
        r"\texttt{c\ ∈\ {[}0,\ 1{]}}": r"\(c \in [0,1]\)",
        r"\texttt{ψ\_cmd\ ∈\ {[}ψ\_min,\ ψ\_max{]}}": (
            r"\(\psi_{\mathrm{cmd}}\in[\psi_{\min},\psi_{\max}]\)"
        ),
        r"\texttt{z\_cmd\ ∈\ {[}z\_min,\ z\_max{]}}": (
            r"\(z_{\mathrm{cmd}}\in[z_{\min},z_{\max}]\)"
        ),
        r"\texttt{ψ\_cmd\ ∈\ {[}min,\ max{]}}": (
            r"\(\psi_{\mathrm{cmd}}\in[\mathrm{min},\mathrm{max}]\)"
        ),
        r"\texttt{z\_cmd\ ∈\ {[}min,\ max{]}}": (
            r"\(z_{\mathrm{cmd}}\in[\mathrm{min},\mathrm{max}]\)"
        ),
        r"\texttt{u\_k\ ≥\ min\_speed}": (
            r"\(u_k \ge \mathrm{min\_speed}\)"
        ),
        r"\texttt{T\_cmd\ ≥\ min\_thrust}": (
            r"\(T_{\mathrm{cmd}} \ge \mathrm{min\_thrust}\)"
        ),
        r"\texttt{T\_cmd\ ≤\ max\_thrust}": (
            r"\(T_{\mathrm{cmd}} \le \mathrm{max\_thrust}\)"
        ),
        r"\texttt{u\_k\ ≥\ u\_min}": r"\(u_k\ge u_{\min}\)",
        r"\texttt{T\_cmd\ ≥\ T\_min}": (
            r"\(T_{\mathrm{cmd}}\ge T_{\min}\)"
        ),
        r"\texttt{T\_cmd\ ≤\ T\_max}": (
            r"\(T_{\mathrm{cmd}}\le T_{\max}\)"
        ),
        (
            r"\texttt{\textbar{}z\_cmd\_\{k+1\}\ -\ "
            r"z\_cmd\_k\textbar{}\ ≤\ Δz\_max}"
        ): (
            r"\(\lvert z_{\mathrm{cmd},k+1}-z_{\mathrm{cmd},k}\rvert"
            r"\le\Delta z_{\max}\)"
        ),
        (
            r"\texttt{\textbar{}ψ\_cmd\_\{k+1\}\ -\ "
            r"ψ\_cmd\_k\textbar{}\ ≤\ Δψ\_max}"
        ): (
            r"\(\lvert\psi_{\mathrm{cmd},k+1}-\psi_{\mathrm{cmd},k}\rvert"
            r"\le\Delta\psi_{\max}\)"
        ),
        (
            r"\texttt{\textbar{}z\_cmd\_k\ -\ "
            r"z\_now\textbar{}\ ≤\ z\_band}"
        ): (
            r"\(\lvert z_{\mathrm{cmd},k}-z_{\mathrm{current}}\rvert"
            r"\le z_b\)"
        ),
        (
            r"\texttt{\textbar{}ψ\_cmd\_k\ -\ "
            r"ψ\_now\textbar{}\ ≤\ ψ\_band}"
        ): (
            r"\(\lvert\psi_{\mathrm{cmd},k}-\psi_{\mathrm{current}}\rvert"
            r"\le\psi_b\)"
        ),
        (
            r"\texttt{\textbackslash{}\textbar{}z\_cmd\_\{k+1\}\ −\ "
            r"z\_cmd\_k\textbackslash{}\textbar{}\ ≤\ Δz\_max}"
        ): (
            r"\(\lvert z_{\mathrm{cmd},k+1}-z_{\mathrm{cmd},k}\rvert "
            r"\le \Delta z_{\max}\)"
        ),
        (
            r"\texttt{\textbackslash{}\textbar{}ψ\_cmd\_\{k+1\}\ −\ "
            r"ψ\_cmd\_k\textbackslash{}\textbar{}\ ≤\ Δψ\_max}"
        ): (
            r"\(\lvert \psi_{\mathrm{cmd},k+1}-\psi_{\mathrm{cmd},k}\rvert "
            r"\le \Delta \psi_{\max}\)"
        ),
        (
            r"\texttt{\textbackslash{}\textbar{}z\_cmd\_k\ −\ "
            r"z\_current\textbackslash{}\textbar{}\ ≤\ z\_band}"
        ): (
            r"\(\lvert z_{\mathrm{cmd},k}-z_{\mathrm{current}}\rvert "
            r"\le z_{\mathrm{band}}\)"
        ),
        (
            r"\texttt{\textbackslash{}\textbar{}ψ\_cmd\_k\ −\ "
            r"ψ\_current\textbackslash{}\textbar{}\ ≤\ psi\_band}"
        ): (
            r"\(\lvert \psi_{\mathrm{cmd},k}-\psi_{\mathrm{current}}\rvert "
            r"\le \psi_{\mathrm{band}}\)"
        ),
        r"\texttt{scenario\_dvl\_dropout\_\{10,30,60,90\}.yaml}": (
            r"{\small\path{scenario_dvl_dropout_{10,30,60,90}.yaml}}"
        ),
        r"\texttt{scenario\_mag\_distortion\_\{light,heavy\}.yaml}": (
            r"{\small\path{scenario_mag_distortion_{light,heavy}.yaml}}"
        ),
        r"\texttt{docs/experiment/benchmark\_test\_log.md}": (
            r"{\small\path{docs/experiment/benchmark_test_log.md}}"
        ),
    }
    for original, replacement in replacements.items():
        latex = latex.replace(original, replacement)
    publication_replacements = {
        "其中 \\texttt{(x,\\ y)} 为水平面位置，"
        "\\texttt{z} 为深度（正向下），"
        "\\texttt{ψ} 为航向角，"
        "\\texttt{u} 为前向速度（surge），"
        "\\texttt{w} 为垂向速度（heave）。": (
            "其中 \\((x,y)\\) 为水平面位置，\\(z\\) 为深度（正向下），"
            "\\(\\psi\\) 为航向角，\\(u\\) 为前向速度（surge），"
            "\\(w\\) 为垂向速度（heave）。"
        ),
        "其中 \\texttt{(x,\\ y)} 为水平面位置，"
        "\\texttt{z} 为深度（正向下），"
        "\\texttt{ψ} 为航向角，"
        "\\texttt{u} 为前向速度，"
        "\\texttt{w} 为垂向速度。": (
            "其中 \\((x,y)\\) 为水平面位置，\\(z\\) 为深度（正向下），"
            "\\(\\psi\\) 为航向角，\\(u\\) 为前向速度，"
            "\\(w\\) 为垂向速度。"
        ),
        "其中俯仰角 \\texttt{θ}": "其中俯仰角 \\(\\theta\\)",
        "功能名称（英文标识）": "功能",
        "电池健康检查（\\texttt{isBatteryOk}）": "电池健康检查",
        "电缆检出确认（\\texttt{isCableDetected}）": "电缆检出确认",
        "通信状态检查（\\texttt{isCommunicationOk}）": "通信状态检查",
        "安全裕度检查（\\texttt{isSafetyMarginViolated}）": "安全裕度检查",
        "之字形搜索（\\texttt{searchPattern}）": "之字形搜索",
        "电缆跟踪（\\texttt{cableTracking}）": "电缆跟踪",
        "紧急上浮（\\texttt{emergencySurface}）": "紧急上浮",
        "返航（\\texttt{returnToHome}）": "返航",
        "其中的整体缩放因子 \\texttt{control\\_scale}": (
            "其中的整体缩放因子 \\(s_u(c)\\)"
        ),
        "式中 \\texttt{conf} 为介于零与一之间的感知置信度，"
        "\\texttt{s\\_low} 为低置信度下的权重放大上限，"
        "\\texttt{α} 为控制放大非线性程度的幂指数。"
        "选择幂函数 \\texttt{(1\\ -\\ conf)\\^{}α} 而非线性形式": (
            "式中 \\(c\\in[0,1]\\) 为感知置信度，"
            "\\(s_e\\) 为低置信度跟踪权重的附加增益，"
            "\\(\\alpha\\) 为置信度映射的幂指数。"
            "选择幂函数 \\(\\rho(c)=(1-c)^\\alpha\\) 而非线性形式"
        ),
        "式中 \\texttt{k} 控制过渡的陡峭程度，"
        "\\texttt{conf\\_thr} 为置信度阈值，"
        "\\texttt{s\\_ctrl} 为低置信度下的控制缩放下限。": (
            "式中 \\(k\\) 控制过渡的陡峭程度，"
            "\\(c_0\\) 为置信度转折点，"
            "\\(\\gamma_u\\) 为低置信度下控制代价的最小缩放比例。"
        ),
        "水平面与深度方向的均方根误差"
        "（\\texttt{RMSE\\_xy}、\\texttt{RMSE\\_z}）": (
            "水平面与深度方向的均方根误差"
            "（\\(\\operatorname{RMSE}_{xy}\\)、"
            "\\(\\operatorname{RMSE}_{z}\\)）"
        ),
        "圆概率误差（\\texttt{CEP50}）": (
            "圆概率误差（\\(\\operatorname{CEP}_{50}\\)）"
        ),
        "既在已知参考附近保守跟随、不贸然远离，"
        "又让指令本身更平滑、避免把噪声放大成动作。": (
            "既在已知参考附近保守跟随、不贸然远离，"
            "又为必要的纠偏动作保留控制权威，并由速率与带宽约束"
            "抑制指令抖动。"
        ),
        "选择幂函数 \\(\\rho(c)=(1-c)^\\alpha\\) 而非线性形式": (
            "选择幂函数 \\(\\rho(c)=(1-c)^\\alpha\\) 而不是线性映射"
        ),
        "低于阈值时缩放因子平滑降到下限，"
        "优化器对控制量施加更大惩罚，输出更平滑的指令。": (
            "低于转折点时缩放因子平滑降到下限，"
            "控制努力惩罚随之减小，使优化器在跟踪权重已放大的同时"
            "仍保留必要的纠偏能力；指令平滑性则由后述速率与带宽约束保证。"
        ),
        "置信度高于阈值时缩放因子接近一": (
            "置信度高于转折点时缩放因子接近一"
        ),
        "仿真标定 scaffold": "仿真标定框架",
        "validation status=pass": "验证状态为通过",
        "代理电缆六场景 smoke": "代理电缆六场景冒烟验证",
        "n=1 smoke": "单次冒烟验证（n=1）",
        "部分档含 retry 合并种子": "部分档合并了重跑种子",
        "其数据源索引见附录 A.7": "其样本量与证据边界见附录 A.7",
        "环境变量约定，一并整理于附录 A.3": (
            "消融定义，一并整理于附录 A.3"
        ),
        "溯源见附录 A.7 所列地形跟随专题文档": (
            "样本量与适用边界见附录 A.7"
        ),
        "溯源与修复始末见附录 A.7 所列地形跟随专题文档": (
            "样本量与适用边界见附录 A.7"
        ),
        "溯源见附录 A.7": "证据边界见附录 A.7",
        "运行器与产物格式见附录 A.6": (
            "评价指标与数据契约见附录 A.6"
        ),
        "解析工具与数据通道一并列于附录 A.6": (
            "计算定义与判定口径见附录 A.6"
        ),
        "配置文件与代码路径见附录 A.1": (
            "场景因子与名义强度见附录 A.1"
        ),
        "帧结构见附录 A.6": "学术数据契约见附录 A.6",
        "全流程记录见附录 A.7 索引": (
            "样本量与证据边界见附录 A.7"
        ),
        "原始数据源索引见附录 A.7": (
            "样本量与证据边界见附录 A.7"
        ),
        "逐行指标与聚合字段整理于附录 A.8": (
            "验收判据与聚合口径见附录 A.8"
        ),
        "相关代码、配置与录制脚本的具体指针统一下沉至附录 A.9": (
            "相应证据层级与恢复条件汇总于附录 A.9"
        ),
        "索引见附录 A.9": "证据层级见附录 A.9",
        "指针见附录 A.9": "证据边界见附录 A.9",
        "代理场景的字段与执行命令见附录 A.10": (
            "代理场景的因子化定义与证据边界见附录 A.10"
        ),
        "计时缺陷的定位过程与具体耗时区间见外围实验完善文档": (
            "求解实时性与回退边界见附录 A.5"
        ),
        "上述三组补充实验的完整设置、数值结果与数据源目录"
        "见外围实验完善文档": (
            "上述三组补充实验的机制定义与证据边界"
            "见附录 A.3、A.5 和 A.7"
        ),
        "各变体的开关配置、逐场景数值结果与数据源，"
        "整理于附录 A.3 与外围实验完善文档": (
            "各变体的数学定义与证据边界整理于附录 A.3 和 A.7"
        ),
        "原始叙述、插图与来源指针留在专用仓库文档中"
        "（证据层级见附录 A.9）": (
            "此处仅保留可复核的结论摘要（证据层级见附录 A.9）"
        ),
        "端到端先验畸变验证的可执行路线与逐步进度记于独立计划文档"
        "（证据边界见附录 A.9）": (
            "端到端先验畸变验证的证据边界见附录 A.9"
        ),
    }
    for original, replacement in publication_replacements.items():
        latex = latex.replace(original, replacement)
    latex = latex.replace("✓", r"\(\checkmark\)")
    latex = latex.replace("✗", r"\(\times\)")
    latex = latex.replace("±", r"\allowbreak{}±")
    latex = TEXTTT_RE.sub(allow_code_breaks, latex)
    if academic_stats:
        latex = SAMPLE_SIZE_RE.sub(
            lambda match: (
                rf"\({match.group('symbol')}={match.group('value')}\)"
            ),
            latex,
        )
    latex = latex.replace(r"\textasciitilde{}\ref", r"~\ref")
    latex = latex.replace(r"\nobreakspace{}\ref", r"~\ref")
    latex = latex.replace(r"\begin{figure}", r"\begin{figure}[htbp]")
    latex = latex.replace(r"\end{figure}", "\\end{figure}\n\\FloatBarrier")
    return compact_consecutive_figure_groups(latex)


def preprocess(
    spec: ChapterSpec,
    source_data: str,
) -> tuple[str, tuple[tuple[str, str], ...]]:
    source_lines = source_data.splitlines()
    body_lines: list[str] = []
    for line in source_lines:
        if REFERENCE_HEADING_RE.match(line):
            break
        body_lines.append(line)

    output: list[str] = []
    table_index = 0
    math_index = 0
    code_index = 0
    code_blocks: list[tuple[str, str]] = []
    heading_specs = {item.title: item for item in spec.unnumbered_headings}
    used_unnumbered_headings: set[str] = set()
    index = 0

    while index < len(body_lines):
        line = body_lines[index]

        fence = FENCE_RE.match(line)
        if fence:
            closing_index = index + 1
            while (
                closing_index < len(body_lines)
                and not body_lines[closing_index].startswith("```")
            ):
                closing_index += 1
            if closing_index >= len(body_lines):
                raise ValueError(f"document {spec.key}: unclosed fenced block")
            block_lines = body_lines[index + 1 : closing_index]
            if spec.display_math:
                if math_index >= len(spec.display_math):
                    raise ValueError(
                        f"document {spec.key}: unexpected formula block "
                        f"#{math_index + 1}"
                    )
                output.extend(("", spec.display_math[math_index].latex, ""))
                math_index += 1
            elif spec.code_languages:
                if code_index >= len(spec.code_languages):
                    raise ValueError(
                        f"document {spec.key}: unexpected code block #{code_index + 1}"
                    )
                language = spec.code_languages[code_index]
                code_blocks.append((language, "\n".join(block_lines)))
                output.extend(
                    ("", f"AUVTHESISCODESENTINEL{code_index:02d}", "")
                )
                code_index += 1
            else:
                output.append(line)
                output.extend(block_lines)
                output.append(body_lines[closing_index])
            index = closing_index + 1
            continue

        heading = HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            title = heading.group(2)
            if level == 1:
                index += 1
                continue
            numbered_title = NUMBERED_TITLE_RE.match(title)
            if not numbered_title:
                heading_spec = heading_specs.get(title)
                if not heading_spec:
                    raise ValueError(
                        f"document {spec.key}: unnumbered heading: {line}"
                    )
                if title in used_unnumbered_headings:
                    raise ValueError(
                        f"document {spec.key}: duplicate unnumbered heading: {line}"
                    )
                used_unnumbered_headings.add(title)
                output.append(
                    f"{'#' * (level - 1)} "
                    f"{normalize_chinese_prose(title, heading=True)} "
                    f"{{#{heading_spec.label}}}"
                )
                index += 1
                continue
            section_number, section_title = numbered_title.groups()
            if section_number.split(".", 1)[0] != spec.section_prefix:
                raise ValueError(
                    f"document {spec.key}: unexpected section number "
                    f"{section_number}"
                )
            label_number = section_number
            if not spec.section_prefix.isdigit():
                label_number = section_number.split(".", 1)[1]
            label = f"sec:{spec.label_prefix}-{label_number.replace('.', '-')}"
            output.append(
                f"{'#' * (level - 1)} "
                f"{normalize_chinese_prose(section_title, heading=True)} "
                f"{{#{label}}}"
            )
            index += 1
            continue

        image = IMAGE_RE.match(line)
        if image:
            caption_index = skip_blank_lines(body_lines, index + 1)
            if caption_index >= len(body_lines):
                raise ValueError(
                    f"document {spec.key}: image without caption: {line}"
                )
            caption = FIGURE_CAPTION_RE.match(body_lines[caption_index])
            if not caption:
                raise ValueError(
                    f"document {spec.key}: malformed figure caption after: {line}"
                )
            path = latex_image_path(image.group("path"))
            output.append(
                f"![{normalize_chinese_prose(caption.group('caption'))}]({path})"
                f"{{#{caption.group('label')} width=95%}}"
            )
            index = caption_index + 1
            continue

        if line.startswith("|"):
            table_lines: list[str] = []
            while index < len(body_lines) and body_lines[index].startswith("|"):
                table_lines.append(body_lines[index])
                index += 1
            if table_index >= len(spec.tables):
                raise ValueError(
                    f"document {spec.key}: unexpected table #{table_index + 1}"
                )
            table_spec = spec.tables[table_index]
            table_index += 1
            if table_spec.font_size:
                output.extend(
                    (rf"\begingroup\{table_spec.font_size}", "")
                )
            output.extend(normalize_chinese_prose(item) for item in table_lines)
            output.append("")
            output.append(f": {table_spec.caption} {{#{table_spec.label}}}")
            next_content = skip_blank_lines(body_lines, index)
            if (
                next_content < len(body_lines)
                and LEGACY_TABLE_CAPTION_RE.match(body_lines[next_content])
            ):
                index = next_content + 1
            output.append("")
            if table_spec.font_size:
                output.extend((r"\endgroup", ""))
            continue

        output.append(normalize_chinese_prose(line))
        index += 1

    if table_index != len(spec.tables):
        raise ValueError(
            f"document {spec.key}: expected {len(spec.tables)} tables, "
            f"found {table_index}"
        )
    if math_index != len(spec.display_math):
        raise ValueError(
            f"document {spec.key}: expected {len(spec.display_math)} formula blocks, "
            f"found {math_index}"
        )
    if code_index != len(spec.code_languages):
        raise ValueError(
            f"document {spec.key}: expected {len(spec.code_languages)} code blocks, "
            f"found {code_index}"
        )
    if used_unnumbered_headings != set(heading_specs):
        missing = sorted(set(heading_specs) - used_unnumbered_headings)
        raise ValueError(
            f"document {spec.key}: missing unnumbered headings: {missing}"
        )
    return "\n".join(output).strip() + "\n", tuple(code_blocks)


def render_latex(spec: ChapterSpec) -> bytes:
    source_data = spec.source.read_text(encoding="utf-8")
    markdown, code_blocks = preprocess(spec, source_data)
    command = (
        "pandoc",
        "-f",
        "markdown+raw_tex+tex_math_dollars-smart",
        "-t",
        "latex",
        "--wrap=none",
    )
    completed = subprocess.run(
        command,
        input=markdown,
        text=True,
        capture_output=True,
        check=True,
    )
    latex = completed.stdout
    for index, (language, code) in enumerate(code_blocks):
        sentinel = f"AUVTHESISCODESENTINEL{index:02d}"
        if latex.count(sentinel) != 1:
            raise ValueError(
                f"document {spec.key}: code sentinel {sentinel} "
                f"appeared {latex.count(sentinel)} times"
            )
        listing = (
            rf"\begin{{lstlisting}}[language={language}]"
            f"\n{code}\n"
            r"\end{lstlisting}"
        )
        latex = latex.replace(sentinel, listing)
    latex = postprocess_latex(
        latex,
        academic_stats=spec.key in {"4", "5", "6"},
    )
    relative_target = spec.target.relative_to(ROOT)
    header = (
        "% !TEX root = ../auv-thesis.tex\n"
        f"% Maintained source: {relative_target}\n"
        f"% Legacy import source: {spec.source.relative_to(ROOT)}\n"
        f"% Legacy import SHA256: {source_hash(source_data)}\n"
        "% Regenerated only by explicit legacy overwrite; review before use.\n\n"
        f"\\chapter{{{spec.title}}}\n\n"
    )
    return (header + latex.rstrip() + "\n").encode("utf-8")


def migrate(chapter_numbers: list[str], *, check: bool) -> int:
    failed = False
    for chapter_number in chapter_numbers:
        spec = CHAPTERS[chapter_number]
        expected = render_latex(spec)
        current = spec.target.read_bytes() if spec.target.exists() else None
        relative_target = spec.target.relative_to(ROOT)
        if check:
            if current == expected:
                print(f"MATCHES_LEGACY     {relative_target}")
            else:
                print(
                    f"DIFFERS_FROM_LEGACY {relative_target} "
                    "(authoritative TeX unchanged)"
                )
                failed = True
            continue
        if current == expected:
            print(f"UNCHANGED {relative_target}")
            continue
        temporary = spec.target.with_suffix(spec.target.suffix + ".tmp")
        temporary.write_bytes(expected)
        temporary.replace(spec.target)
        print(f"UPDATED   {relative_target}")
    return 1 if failed else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Legacy Markdown-to-TeX reproduction tool. "
            "The maintained TeX chapters are authoritative."
        )
    )
    parser.add_argument(
        "--chapter",
        action="append",
        choices=DOCUMENT_ORDER,
        help=(
            "legacy Markdown chapter to render (1-6); "
            "repeat to select multiple documents"
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare legacy rendering without modifying maintained TeX files",
    )
    parser.add_argument(
        "--allow-maintained-tex-overwrite",
        action="store_true",
        help=(
            "explicitly allow the legacy rendering to overwrite maintained "
            "thuthesis/data chapters; never use from a build"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.check and not args.allow_maintained_tex_overwrite:
        raise SystemExit(
            "Refusing to overwrite authoritative thuthesis/data/*.tex files. "
            "Use --check for a read-only legacy comparison. "
            "Only an intentional historical restore may pass "
            "--allow-maintained-tex-overwrite."
        )
    chapter_numbers = args.chapter or list(DOCUMENT_ORDER)
    return migrate(chapter_numbers, check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
