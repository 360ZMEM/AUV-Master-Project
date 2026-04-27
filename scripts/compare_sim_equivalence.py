#!/usr/bin/env python3
"""对比旧版与统一版仿真主循环行为。

该脚本用于验证结构重构后，核心行为趋势是否保持一致：会分别运行两条
仿真管线，解析 stdout 中的关键指标，并输出差异与是否等价的结论。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


METRICS_RE = re.compile(
    r"rms=(?P<rms>[0-9.eE+-]+)m\s+mean_error=(?P<mean>[0-9.eE+-]+)m\s+axis_ratio=(?P<axis>[0-9.eE+-]+)%\s+sat_ratio=(?P<sat>[0-9.eE+-]+)%"
)
FLAGS_RE = re.compile(
    r"safety_event_count=(?P<safety>\d+)\s+pass_rms=(?P<pass_rms>True|False)\s+pass_axis_ratio=(?P<pass_axis>True|False)"
)


@dataclass
class RunMetrics:
    """单次仿真运行的核心指标。"""

    rms: float
    mean_error: float
    axis_ratio: float
    sat_ratio: float
    safety_event_count: int
    pass_rms: bool
    pass_axis_ratio: bool


@dataclass
class CompareResult:
    """两次仿真运行的对比结果。"""

    legacy: RunMetrics
    unified: RunMetrics
    delta_rms: float
    delta_axis_ratio: float
    delta_sat_ratio: float
    delta_safety_events: int
    equivalent: bool


def _parse_metrics(output: str) -> RunMetrics:
    """从仿真输出文本中解析指标。

    该函数使用两个正则表达式从标准输出中提取关键指标和通过/失败标志，
    转换为 RunMetrics 对象。axis_ratio 从百分比转化为小数。

    @param output: 仿真程序输出的完整文本（包括标准输出和标准错误合并）
    @return: RunMetrics 对象，包含 rms、mean_error、axis_ratio、sat_ratio、
            safety_event_count、pass_rms、pass_axis_ratio 七个字段
    @throws ValueError: 若两个正则都无法匹配时抛出异常信息 'failed to parse metrics from simulation output'
    @note: 依赖 METRICS_RE 和 FLAGS_RE 两个全局正则对象，需确保仿真输出包含特定格式的指标行
    """
    m = METRICS_RE.search(output)
    f = FLAGS_RE.search(output)
    if not m or not f:
        raise ValueError("failed to parse metrics from simulation output")

    return RunMetrics(
        rms=float(m.group("rms")),
        mean_error=float(m.group("mean")),
        axis_ratio=float(m.group("axis")) / 100.0,
        sat_ratio=float(m.group("sat")) / 100.0,
        safety_event_count=int(f.group("safety")),
        pass_rms=(f.group("pass_rms") == "True"),
        pass_axis_ratio=(f.group("pass_axis") == "True"),
    )


def _run_command(cmd: list[str], cwd: Path, timeout: int) -> str:
    """在指定工作目录执行外部命令并返回合并输出。

    该函数使用 subprocess.run() 执行给定命令（如运行仿真脚本），
    合并 stdout 和 stderr 输出，设置返回码异常处理。

    @param cmd: 命令行参数列表（包括程序名和参数）
    @param cwd: 工作目录 Path 对象
    @param timeout: 超时秒数（<= 0 表示没有超时）
    @return: 合并输出文本字符串（stdout + '\n' + stderr）
    @throws RuntimeError: 若命令返回码非零时抛出，包含返回码和输出信息
    @note: 不检查 returncode；若 timeout > 0 且超时则会被捕获
    """
    completed = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=None if timeout <= 0 else timeout,
        check=False,
    )
    merged = (completed.stdout or "") + "\n" + (completed.stderr or "")
    if completed.returncode != 0:
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(cmd)}\n{merged}")
    return merged


def _save_log(path: Path, content: str) -> None:
    """将命令输出保存到日志文件。

    该函数简单直接，一次输出内容保存到指定位置。如果指定文件符号的父目录不存在
    即会自动创建多级目录。

    @param path: 上只文件 Path 对象
    @param content: 输出文本字符串
    @throws IOError: 文件写入失败或不是缺权限时抛出
    @note: 会自动创建目录（parents=True、exist_ok=True）；
           不会检查内部写入是否成功（每写入不才会检验）
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main(argv: Optional[list[str]] = None) -> int:
    """脚本入口，运行两条仿真管线并比较结果。

    该函数是等价性检查脚本的第二点五试验站：地处解析命令行参数（不包括两条仿真管线的根目录和配置文件路径）、
    分别运行旧版仿真与统一仿真管线，采集输出指标，按预设容差比较判判是否接近，上输出 JSON 形成的对比结果。

    @param argv: 含令行参数列表（None 表示使用 sys.argv[1:]）
    @return: 返回进程退出码（默认 0 表示成功或接近，优雨时返回 1）
    @throws SystemExit: 含令行参数解析失败或请求帮助时由 argparse 抛出；
                       RuntimeError: 试验输出指标提拔失败；，外部命令执行失败
    @note: 批量加了归算批量罐量（--rms-tol, --axis-ratio-tol, --sat-ratio-tol, --safety-event-tol）；
           dry-run 教很批量不退出仿真，执行高 print 点操作内容。返回码 0 仅表示按接近容差下达成功，
           不表示两版仿真行为完全一样。
    """
    parser = argparse.ArgumentParser(description="Compare legacy and unified simulation behavior")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--legacy-root",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "Master毕业设计代码实现" / "auv_project_new" / "AUV_Software_Stack",
    )
    parser.add_argument("--legacy-config", type=Path, default=None)
    parser.add_argument("--unified-config", type=Path, default=None)
    parser.add_argument("--timeout", type=int, default=0, help="seconds; 0 means no timeout")
    parser.add_argument("--rms-tol", type=float, default=0.10)
    parser.add_argument("--axis-ratio-tol", type=float, default=0.05)
    parser.add_argument("--sat-ratio-tol", type=float, default=0.10)
    parser.add_argument("--safety-event-tol", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    project_root = args.project_root.resolve()
    legacy_root = args.legacy_root.resolve()
    unified_apps = project_root / "sim_holoocean" / "apps"

    legacy_cfg = (args.legacy_config.resolve() if args.legacy_config else (legacy_root / "config" / "sim_params.yaml"))
    unified_cfg = (args.unified_config.resolve() if args.unified_config else (project_root / "config" / "sim_params.yaml"))

    python_executable = sys.executable or "/usr/bin/python3"
    legacy_cmd = [python_executable, "4_codes/main.py", "--config", str(legacy_cfg)]
    unified_cmd = [python_executable, "main.py", "--config", str(unified_cfg)]

    print("[eq] legacy cwd:", legacy_root)
    print("[eq] unified cwd:", unified_apps)
    print("[eq] legacy cmd:", " ".join(legacy_cmd))
    print("[eq] unified cmd:", " ".join(unified_cmd))

    if args.dry_run:
        return 0

    legacy_out = _run_command(legacy_cmd, legacy_root, args.timeout)
    unified_out = _run_command(unified_cmd, unified_apps, args.timeout)

    logs_dir = project_root / "log"
    _save_log(logs_dir / "phase2_5_legacy.log", legacy_out)
    _save_log(logs_dir / "phase2_5_unified.log", unified_out)

    legacy_metrics = _parse_metrics(legacy_out)
    unified_metrics = _parse_metrics(unified_out)

    result = CompareResult(
        legacy=legacy_metrics,
        unified=unified_metrics,
        delta_rms=abs(legacy_metrics.rms - unified_metrics.rms),
        delta_axis_ratio=abs(legacy_metrics.axis_ratio - unified_metrics.axis_ratio),
        delta_sat_ratio=abs(legacy_metrics.sat_ratio - unified_metrics.sat_ratio),
        delta_safety_events=abs(legacy_metrics.safety_event_count - unified_metrics.safety_event_count),
        equivalent=False,
    )

    result.equivalent = (
        result.delta_rms <= args.rms_tol
        and result.delta_axis_ratio <= args.axis_ratio_tol
        and result.delta_sat_ratio <= args.sat_ratio_tol
        and result.delta_safety_events <= args.safety_event_tol
        and legacy_metrics.pass_rms
        and legacy_metrics.pass_axis_ratio
        and unified_metrics.pass_rms
        and unified_metrics.pass_axis_ratio
    )

    summary = asdict(result)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if not result.equivalent:
        print("[eq][FAIL] unified behavior deviates beyond tolerances")
        return 2

    print("[eq][PASS] unified behavior is equivalent within tolerances")
    return 0


if __name__ == "__main__":
    sys.exit(main())
