"""Generate the canonical Draw.io architecture diagrams used by the thesis.

Figure titles, subtitles, captions, and long legends intentionally live in the
LaTeX/Markdown publication layer. The diagram canvas contains only information
needed to understand the structure itself.
"""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape


THESIS_OUT = Path(__file__).resolve().parent
INTERNAL_OUT = THESIS_OUT.parents[2] / "internals" / "figures" / "architecture"
VERSION = "30.3.14"

FONT_FAMILY = "Songti SC"
FONT = f"fontFamily={FONT_FAMILY};fontSize=24;fontColor=#26323D;"
LANE_FONT = f"fontFamily={FONT_FAMILY};fontSize=26;fontStyle=1;fontColor=#26323D;"
EDGE_FONT = f"fontFamily={FONT_FAMILY};fontSize=20;fontColor=#25384A;"

PALETTE = {
    "blue": ("#EAF2F8", "#5F8FB8"),
    "green": ("#EEF6EF", "#6E9F78"),
    "yellow": ("#FFF7E8", "#C69B42"),
    "orange": ("#FBEFE5", "#C9824D"),
    "purple": ("#F2EDF7", "#8F78AF"),
    "red": ("#F8EEEE", "#B86F73"),
    "gray": ("#F6F7F8", "#7F8E9A"),
    "teal": ("#EAF6F5", "#5D9E99"),
    "white": ("#FFFFFF", "#667788"),
}

EDGE = (
    "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;"
    "html=1;strokeColor=#536F87;strokeWidth=1.8;"
    f"{EDGE_FONT}labelBackgroundColor=#FFFFFF;labelBorderColor=none;"
    "endArrow=block;endFill=1;endSize=10;"
)
EDGE_MAIN = EDGE.replace("strokeWidth=1.8", "strokeWidth=2.0").replace(
    "fontSize=20", "fontSize=20;fontStyle=1"
)
EDGE_DASH = EDGE + "dashed=1;dashPattern=7 5;"
EDGE_SAFE = EDGE_MAIN.replace("strokeColor=#536F87", "strokeColor=#A34F55")
EDGE_DIRECT = EDGE.replace(
    "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;",
    "edgeStyle=none;rounded=0;orthogonalLoop=0;jettySize=10;",
)
EDGE_DIRECT_DASH = EDGE_DIRECT + "dashed=1;dashPattern=7 5;"


def xml_value(text: str) -> str:
    return escape(text, {'"': "&quot;"}).replace("\n", "&#xa;")


def rich_label(title: str, detail: str = "") -> str:
    if not detail:
        return f"<b>{title}</b>"
    return f"<b>{title}</b><br>{detail}"


def shape_style(kind: str, color: str, extra: str = "") -> str:
    fill, stroke = PALETTE[color]
    base = (
        "whiteSpace=wrap;html=1;align=center;verticalAlign=middle;"
        f"fillColor={fill};strokeColor={stroke};strokeWidth=1.8;spacing=8;{FONT}"
    )
    shapes = {
        "process": "rounded=0;",
        "module": "rounded=1;arcSize=6;",
        "io": "shape=parallelogram;perimeter=parallelogramPerimeter;fixedSize=1;",
        "decision": "rhombus;",
        "gate": "shape=trapezoid;perimeter=trapezoidPerimeter;fixedSize=1;direction=north;",
        "data": "shape=cylinder3;boundedLbl=1;backgroundOutline=1;size=12;",
        "state": "rounded=1;arcSize=18;",
        "terminal": "ellipse;",
        "bt_control": "shape=hexagon;perimeter=hexagonPerimeter2;fixedSize=1;",
    }
    return shapes[kind] + base + extra


def lane_style(color: str) -> str:
    fill, stroke = PALETTE[color]
    return (
        "swimlane;whiteSpace=wrap;html=1;startSize=38;rounded=0;"
        f"fillColor={fill};strokeColor={stroke};strokeWidth=1.8;"
        f"collapsible=0;childLayout=none;{LANE_FONT}"
    )


def add_shape(
    cells: list[str],
    id_: str,
    title: str,
    detail: str,
    x: float,
    y: float,
    w: float,
    h: float,
    color: str = "blue",
    kind: str = "process",
    parent: str = "1",
    extra: str = "",
) -> None:
    value = rich_label(title, detail)
    cells.append(
        f'<mxCell id="{id_}" value="{xml_value(value)}" '
        f'style="{shape_style(kind, color, extra)}" vertex="1" parent="{parent}">'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry" />'
        "</mxCell>"
    )


def add_lane(
    cells: list[str],
    id_: str,
    label: str,
    x: float,
    y: float,
    w: float,
    h: float,
    color: str,
) -> None:
    cells.append(
        f'<mxCell id="{id_}" value="{xml_value(label)}" style="{lane_style(color)}" '
        f'vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" '
        f'height="{h}" as="geometry" /></mxCell>'
    )


def add_anchor(cells: list[str], id_: str, x: float, y: float) -> None:
    style = (
        "ellipse;html=1;opacity=0;fillOpacity=0;strokeOpacity=0;"
        "resizable=0;movable=0;connectable=1;"
    )
    cells.append(
        f'<mxCell id="{id_}" value="" style="{style}" vertex="1" parent="1">'
        f'<mxGeometry x="{x - 1}" y="{y - 1}" width="2" height="2" as="geometry" />'
        "</mxCell>"
    )


def add_note(
    cells: list[str],
    id_: str,
    label: str,
    x: float,
    y: float,
    w: float,
    h: float,
    size: int = 14,
    bold: bool = False,
    color: str = "#3C4A56",
) -> None:
    style = (
        "text;html=1;strokeColor=none;fillColor=none;align=center;"
        f"verticalAlign=middle;whiteSpace=wrap;fontFamily={FONT_FAMILY};"
        f"fontSize={size};fontColor={color};"
    )
    if bold:
        style += "fontStyle=1;"
    cells.append(
        f'<mxCell id="{id_}" value="{xml_value(label)}" style="{style}" '
        f'vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" '
        f'height="{h}" as="geometry" /></mxCell>'
    )


def add_edge(
    cells: list[str],
    id_: str,
    source: str,
    target: str,
    label: str = "",
    *,
    points: list[tuple[float, float]] | None = None,
    extra: str = "",
    main: bool = False,
    dashed: bool = False,
    safe: bool = False,
    direct: bool = False,
) -> None:
    if direct:
        base = EDGE_DIRECT_DASH if dashed else EDGE_DIRECT
    else:
        base = EDGE_SAFE if safe else (EDGE_MAIN if main else (EDGE_DASH if dashed else EDGE))
    if points:
        point_xml = "".join(f'<mxPoint x="{x}" y="{y}" />' for x, y in points)
        geometry = (
            '<mxGeometry relative="1" as="geometry"><Array as="points">'
            f"{point_xml}</Array></mxGeometry>"
        )
    else:
        geometry = '<mxGeometry relative="1" as="geometry" />'
    cells.append(
        f'<mxCell id="{id_}" value="{xml_value(label)}" style="{base + extra}" '
        f'edge="1" parent="1" source="{source}" target="{target}">{geometry}</mxCell>'
    )


def write(
    name: str,
    cells: list[str],
    *,
    out: Path = THESIS_OUT,
    page_width: int = 1380,
    page_height: int = 780,
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    body = "\n        ".join(['<mxCell id="0" />', '<mxCell id="1" parent="0" />'] + cells)
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<mxfile host="drawio" version="{VERSION}">
  <diagram name="{xml_value(name)}">
    <mxGraphModel dx="1200" dy="760" grid="1" gridSize="10" guides="1"
      tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1"
      pageWidth="{page_width}" pageHeight="{page_height}" math="0" shadow="0">
      <root>
        {body}
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
"""
    (out / f"{name}.drawio").write_text(xml, encoding="utf-8")


def code_layer_architecture() -> None:
    cells: list[str] = []
    lanes = [
        ("app", "应用与运行入口", 30, 30, 1320, 115, "blue"),
        ("interface", "接口与虚实适配", 30, 160, 1320, 125, "teal"),
        ("behavior", "行为与安全治理", 30, 300, 1320, 115, "yellow"),
        ("algorithm", "算法与优化", 30, 430, 1320, 125, "green"),
        ("common", "共享协议与物理约束", 30, 570, 1320, 115, "purple"),
    ]
    for spec in lanes:
        add_lane(cells, *spec)
    nodes = [
        ("a1", "独立仿真入口", "main.py", 55, 53, 225, 48, "blue", "io", "app"),
        ("a2", "单进程闭环", "main_loop.py", 355, 53, 225, 48, "blue", "process", "app"),
        ("a3", "桥接运行入口", "run_zenoh_bridge.py", 655, 53, 250, 48, "blue", "io", "app"),
        ("a4", "实验编排入口", "start_experiment.sh", 980, 53, 260, 48, "blue", "io", "app"),
        ("i1", "仿真后端适配", "HoloOcean / PVS", 55, 57, 245, 52, "teal", "module", "interface"),
        ("i2", "坐标转换", "UE4 ↔ NED", 360, 57, 220, 52, "teal", "module", "interface"),
        ("i3", "跨进程通信", "Zenoh / UDP", 650, 57, 220, 52, "teal", "module", "interface"),
        ("i4", "协议级硬件替身", "Mock AMD", 940, 57, 250, 52, "teal", "module", "interface"),
        ("b1", "命令守卫", "合法性过滤", 150, 54, 245, 50, "yellow", "decision", "behavior"),
        ("b2", "安全监控", "限幅 / 急停 / 回退", 530, 54, 245, 50, "red", "decision", "behavior"),
        ("b3", "任务状态管理", "阶段 / 模式", 910, 54, 245, 50, "yellow", "state", "behavior"),
        ("g1", "LOS 制导", "guidance.py", 55, 58, 205, 52, "green", "process", "algorithm"),
        ("g2", "级联 PID", "auv_pid_controller.py", 315, 58, 235, 52, "green", "process", "algorithm"),
        ("g3", "MPC / UA-MPC", "auv_mpc_controller.py", 605, 58, 245, 52, "green", "process", "algorithm"),
        ("g4", "状态估计", "es_ekf.py", 905, 58, 185, 52, "green", "process", "algorithm"),
        ("g5", "轨迹生成", "trajectory_generator.py", 1090, 58, 200, 52, "green", "process", "algorithm"),
        ("c1", "通信契约", "Topic / Payload", 125, 50, 260, 52, "purple", "data", "common"),
        ("c2", "共享语义", "模式 / 指令 / 状态", 535, 50, 260, 52, "purple", "data", "common"),
        ("c3", "物理边界", "限幅 / 饱和 / 日志", 945, 50, 260, 52, "purple", "data", "common"),
    ]
    for spec in nodes:
        add_shape(cells, *spec)
    add_edge(cells, "e1", "a2", "i1", "", main=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "e2", "a3", "i3", "", main=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(
        cells,
        "e3",
        "i3",
        "c1",
        "协议",
        points=[(790, 290), (45, 290), (45, 705), (285, 705)],
        extra="exitX=0.5;exitY=1;entryX=0.5;entryY=1;",
    )
    add_edge(cells, "e4", "b2", "g2", "约束", points=[(650, 420), (435, 420)], extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "e5", "g2", "c3", "物理限幅", points=[(435, 560), (1075, 560)], extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    write("auv_code_layer_architecture", cells, out=INTERNAL_OUT, page_height=720)


def runtime_dataflow() -> None:
    cells: list[str] = []
    add_lane(cells, "single", "路径 A：单进程算法验证闭环", 30, 30, 1320, 285, "green")
    add_lane(cells, "bridge", "路径 B：桥接集成与部署接口闭环", 30, 340, 1320, 345, "blue")
    for spec in [
        ("s1", "目标与轨迹", "参考路点", 55, 75, 190, 62, "blue", "io", "single"),
        ("s2", "制导", "航向 / 深度参考", 285, 75, 200, 62, "green", "process", "single"),
        ("s3", "控制器", "舵角 / 推力", 525, 75, 190, 62, "green", "process", "single"),
        ("s4", "安全过滤", "限幅 / 回退", 755, 75, 190, 62, "yellow", "decision", "single"),
        ("s5", "仿真后端", "PVS / HoloOcean", 985, 75, 220, 62, "teal", "io", "single"),
        ("s6", "传感器状态", "位置 / 姿态 / 速度", 525, 185, 250, 60, "gray", "data", "single"),
        ("b1", "数字孪生或硬件替身", "PVS / HoloOcean / Mock AMD", 55, 80, 235, 68, "teal", "io", "bridge"),
        ("b2", "坐标与帧转换", "统一参考系", 335, 80, 210, 68, "teal", "process", "bridge"),
        ("b3", "跨进程协议", "Zenoh / UDP", 590, 80, 210, 68, "purple", "data", "bridge"),
        ("b4", "ROS2 桥接", "传感 / 控制 Topic", 845, 80, 210, 68, "blue", "process", "bridge"),
        ("b5", "状态估计", "ES-EKF", 1100, 80, 185, 68, "green", "process", "bridge"),
        ("b6", "任务决策", "行为树设定点", 1090, 210, 205, 65, "yellow", "process", "bridge"),
        ("b7", "控制器", "PID / MPC", 820, 210, 205, 65, "green", "process", "bridge"),
        ("b8", "下行控制", "安全仲裁命令", 550, 210, 215, 65, "orange", "io", "bridge"),
        ("b9", "实验黑匣子", "日志 / MCAP / 指标", 255, 200, 220, 78, "purple", "data", "bridge"),
    ]:
        add_shape(cells, *spec)
    for i, (a, b, label) in enumerate(
        [("s1", "s2", "参考"), ("s2", "s3", "目标"), ("s3", "s4", "控制"), ("s4", "s5", "安全指令")],
        1,
    ):
        add_edge(cells, f"sa{i}", a, b, label, main=True, extra="exitX=1;entryX=0;")
    add_edge(cells, "sa5", "s5", "s6", "回读", extra="exitX=0.5;exitY=1;entryX=1;entryY=0.5;")
    add_edge(cells, "sa6", "s6", "s2", "闭环反馈", dashed=True, points=[(430, 285), (430, 145)], extra="exitX=0;entryX=0.5;entryY=1;")
    for i, (a, b, label) in enumerate(
        [("b1", "b2", "状态"), ("b2", "b3", "统一帧"), ("b3", "b4", "协议帧"), ("b4", "b5", "传感 Topic")],
        1,
    ):
        add_edge(cells, f"ba{i}", a, b, label, main=True, extra="exitX=1;entryX=0;")
    add_edge(cells, "ba5", "b5", "b6", "状态与健康", extra="exitX=0.65;exitY=1;entryX=0.65;entryY=0;")
    add_edge(cells, "ba6", "b6", "b7", "设定点", main=True, extra="exitX=0;entryX=1;")
    add_edge(cells, "ba7", "b5", "b7", "滤波状态", extra="exitX=0.3;exitY=1;entryX=0.7;entryY=0;")
    add_edge(cells, "ba8", "b7", "b8", "控制命令", main=True, extra="exitX=0;entryX=1;")
    add_edge(cells, "ba9", "b8", "b3", "编码", extra="exitX=0.5;exitY=0;entryX=0.5;entryY=1;")
    add_edge(cells, "ba10", "b4", "b9", "运行证据", dashed=True, points=[(950, 650), (365, 650)], extra="exitX=0.5;exitY=1;entryX=0.5;entryY=1;")
    add_edge(cells, "ba11", "b3", "b1", "执行反馈", dashed=True, points=[(695, 670), (170, 670)], extra="exitX=0.2;exitY=1;entryX=0.5;entryY=1;")
    write("auv_runtime_dataflow", cells, page_height=720)


def ros2_node_topology() -> None:
    cells: list[str] = []
    add_lane(cells, "external", "外部系统与操作端", 30, 30, 1320, 140, "gray")
    add_lane(cells, "ros", "ROS2 在线闭环", 30, 190, 1320, 330, "blue")
    add_lane(cells, "evidence", "可视化与离线证据", 30, 545, 1320, 130, "purple")
    for spec in [
        ("x1", "仿真/实物接口", "传感器与执行器", 70, 55, 260, 62, "teal", "io", "external"),
        ("x3", "跨进程链路", "UDP / Zenoh", 530, 55, 260, 62, "purple", "data", "external"),
        ("x2", "操作员控制台", "遥控 / 授权 / 急停", 990, 55, 260, 62, "orange", "io", "external"),
        ("n1", "协议桥", "auv_bridge", 70, 85, 205, 65, "blue", "module", "ros"),
        ("n2", "定位与融合", "ES-EKF", 345, 85, 205, 65, "green", "module", "ros"),
        ("n3", "控制器", "PID / MPC", 620, 85, 205, 65, "green", "module", "ros"),
        ("n4", "任务决策", "Behavior Tree", 895, 85, 220, 65, "yellow", "module", "ros"),
        ("bus", "ROS2 Topic 总线", "传感 / 状态 / 设定点 / 命令", 335, 200, 730, 70, "gray", "data", "ros"),
        ("n5", "可视化桥", "Foxglove / Console", 160, 55, 250, 58, "purple", "module", "evidence"),
        ("n6", "实验黑匣子", "rosbag / MCAP", 535, 50, 250, 68, "purple", "data", "evidence"),
        ("n7", "离线分析", "图表 / KPI", 910, 55, 250, 58, "purple", "process", "evidence"),
    ]:
        add_shape(cells, *spec)
    add_edge(cells, "r1", "x1", "x3", "状态/执行", main=True, extra="exitX=1;entryX=0;")
    add_edge(cells, "r2", "x2", "x3", "授权/急停", extra="exitX=1;entryX=0;")
    add_edge(cells, "r3", "x3", "n1", "", main=True, points=[(660, 180), (170, 180)], extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    for i, node in enumerate(["n1", "n2", "n3", "n4"], 1):
        add_edge(cells, f"rbus{i}", node, "bus", "", extra=f"exitX={0.25 if i < 3 else 0.75};exitY=1;entryX={(i-0.5)/4};entryY=0;")
    add_edge(cells, "r4", "bus", "n5", "状态/行为", dashed=True, points=[(270, 530)], extra="exitX=0.2;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "r5", "bus", "n6", "记录 Topic", dashed=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "r6", "n6", "n7", "离线分析", main=True, extra="exitX=1;entryX=0;")
    write("auv_ros2_node_topology", cells, out=INTERNAL_OUT, page_height=710)


def safety_arbiter_deployment() -> None:
    cells: list[str] = []
    add_lane(cells, "pc", "地面站", 30, 30, 300, 650, "orange")
    add_lane(cells, "jetson", "Jetson 仲裁与控制", 355, 30, 660, 650, "blue")
    add_lane(cells, "pc104", "PC104 硬实时执行", 1040, 30, 310, 650, "teal")
    for spec in [
        ("p1", "操作员命令", "遥控 / 授权 / 急停", 45, 75, 210, 70, "orange", "io", "pc"),
        ("p2", "链路新鲜度", "上行年龄 / 看门狗", 45, 220, 210, 70, "yellow", "io", "pc"),
        ("p3", "显式确认", "实物阶段准入", 45, 365, 210, 70, "red", "gate", "pc"),
        ("j1", "协议编解码", "上/下行", 55, 65, 220, 70, "blue", "process", "jetson"),
        ("j2", "AutonomyGuard", "漏水 / 电压 / 置信度 / 时延", 45, 175, 260, 115, "red", "decision", "jetson"),
        ("j3", "控制权仲裁", "REMOTE ↔ AUTONOMOUS", 55, 350, 240, 95, "purple", "decision", "jetson"),
        ("j4", "任务决策", "行为树设定点", 365, 65, 220, 70, "yellow", "process", "jetson"),
        ("j5", "控制器", "PID / MPC / Terrain", 365, 190, 220, 70, "green", "process", "jetson"),
        ("j6", "影子路径", "只记录，不执行", 365, 345, 220, 70, "gray", "data", "jetson"),
        ("j7", "安全回退", "零推力并锁回 REMOTE", 210, 515, 255, 70, "red", "state", "jetson"),
        ("a1", "状态上行", "传感器 / 健康", 50, 75, 210, 70, "teal", "io", "pc104"),
        ("a2", "控制输出", "4 舵 + 推力", 50, 245, 210, 70, "teal", "io", "pc104"),
        ("a3", "执行准入", "极性 / 死区静态验证", 50, 415, 210, 75, "yellow", "gate", "pc104"),
    ]:
        add_shape(cells, *spec)
    add_edge(cells, "e1", "p1", "j1", "命令/授权", main=True, extra="exitX=1;entryX=0;")
    add_edge(cells, "e2", "p2", "j2", "新鲜度", extra="exitX=1;entryX=0;")
    add_edge(cells, "e3", "p3", "j3", "释放权限", dashed=True, extra="exitX=1;entryX=0;")
    add_edge(cells, "e4", "a1", "j1", "上行遥测", main=True, points=[(1180, 80), (520, 80)], extra="exitX=0.5;exitY=0;entryX=0.75;entryY=0;")
    add_edge(cells, "e5", "j1", "j2", "申请自主", main=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "e6", "j2", "j3", "准许/拒绝", main=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "e7", "j4", "j5", "设定点", extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(
        cells,
        "e8",
        "j5",
        "j3",
        "候选命令",
        points=[(830, 355), (590, 355)],
        extra="exitX=0.5;exitY=1;entryX=0.75;entryY=0;",
    )
    add_edge(cells, "e9", "j3", "a2", "选定命令", main=True, points=[(680, 330), (1065, 330)], extra="exitX=1;entryX=0;")
    add_edge(cells, "e10", "j3", "j7", "超时/急停", safe=True, extra="exitX=0.4;exitY=1;entryX=0.4;entryY=0;")
    add_edge(cells, "e11", "j7", "a2", "零推力", safe=True, points=[(990, 620), (1065, 620), (1065, 310)], extra="exitX=1;entryX=0;entryY=0.5;")
    add_edge(cells, "e12", "j6", "j3", "影子快照", dashed=True, extra="exitX=0;entryX=1;")
    add_edge(cells, "e13", "a3", "a2", "通过后释放", extra="exitX=0.5;exitY=0;entryX=0.5;entryY=1;")
    write("auv_safety_arbiter_deployment", cells, out=INTERNAL_OUT, page_height=720)


def system_capability_map() -> None:
    cells: list[str] = []
    add_shape(cells, "core", "自主任务平台", "任务执行 / 安全控制 / 数据闭环", 505, 275, 370, 100, "blue", "process")
    for spec in [
        ("sim", "仿真与环境", "场景 / 传感 / 执行响应", 55, 70, 310, 80, "teal", "io"),
        ("auto", "自主决策控制", "估计 / 决策 / 控制", 535, 45, 310, 80, "green", "process"),
        ("human", "人机协同", "授权 / 接管 / 急停", 1015, 70, 310, 80, "orange", "io"),
        ("deploy", "实物部署", "分级试验 / 安全回退", 55, 500, 310, 80, "red", "gate"),
        ("evidence", "实验验证", "编排 / 指标 / 对比", 535, 535, 310, 80, "yellow", "gate"),
        ("obs", "运行证据", "看板 / 日志 / 黑匣子", 1015, 500, 310, 80, "purple", "data"),
    ]:
        add_shape(cells, *spec)
    add_edge(cells, "c1", "sim", "core", "仿真输入", main=True, points=[(210, 220), (505, 325)], extra="exitX=0.5;exitY=1;entryX=0;entryY=0.5;")
    add_edge(cells, "c2", "auto", "core", "自主能力", main=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "c3", "human", "core", "人工授权", main=True, points=[(1170, 220), (875, 325)], extra="exitX=0.5;exitY=1;entryX=1;entryY=0.5;")
    add_edge(cells, "c4", "core", "deploy", "工程迁移", main=True, points=[(505, 450), (210, 450)], extra="exitX=0;exitY=0.7;entryX=0.5;entryY=0;")
    add_edge(cells, "c5", "core", "evidence", "实验数据", main=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "c6", "core", "obs", "运行记录", main=True, points=[(875, 450), (1170, 450)], extra="exitX=1;exitY=0.7;entryX=0.5;entryY=0;")
    add_edge(cells, "c7", "evidence", "sim", "场景反哺", dashed=True, points=[(445, 645), (25, 645), (25, 110)], extra="exitX=0;entryX=0;")
    add_edge(cells, "c8", "obs", "human", "态势反馈", dashed=True, points=[(1350, 540), (1350, 110)], extra="exitX=1;entryX=1;")
    write("auv_system_capability_map", cells, page_height=670)


def system_subsystem_organization() -> None:
    cells: list[str] = []
    add_lane(cells, "ground", "地面与实验侧", 30, 30, 1320, 145, "orange")
    add_lane(cells, "onboard", "艇载自治侧", 30, 205, 1320, 250, "blue")
    add_lane(cells, "world", "环境与被控对象侧", 30, 485, 1320, 155, "teal")
    for spec in [
        ("g_task", "任务设计", "航线 / 场景 / 目标", 55, 55, 225, 62, "yellow", "io", "ground"),
        ("g_ops", "操作监督", "授权 / 接管 / 急停", 365, 55, 225, 62, "orange", "io", "ground"),
        ("g_exp", "实验管理", "启动 / 记录 / 评估", 675, 55, 225, 62, "purple", "process", "ground"),
        ("g_viz", "可视化分析", "态势 / 图表 / 报告", 985, 55, 225, 62, "purple", "data", "ground"),
        ("o_comm", "通信接入", "上行感知 / 下行控制", 50, 70, 215, 65, "blue", "module", "onboard"),
        ("o_state", "状态理解", "定位 / 健康 / 置信度", 315, 70, 215, 65, "green", "process", "onboard"),
        ("o_task", "任务智能", "模式 / 行为选择", 580, 70, 215, 65, "yellow", "process", "onboard"),
        ("o_ctrl", "运动执行", "控制 / 安全限幅", 845, 70, 215, 65, "green", "process", "onboard"),
        ("o_safe", "安全治理", "权限 / 故障回退", 1100, 70, 170, 65, "red", "decision", "onboard"),
        ("w_sim", "虚拟海洋", "场景 / 扰动注入", 110, 60, 280, 65, "teal", "io", "world"),
        ("w_auv", "真实 AUV", "传感 / 执行 / 动力学", 550, 60, 280, 65, "teal", "io", "world"),
        ("w_env", "外部环境", "水流 / 地形 / 通信", 990, 60, 250, 65, "gray", "io", "world"),
    ]:
        add_shape(cells, *spec)
    add_edge(cells, "s1", "g_task", "o_task", "", points=[(198, 180), (718, 180)], extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "s2", "g_ops", "o_safe", "", main=True, points=[(508, 188), (1215, 188)], extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "s3", "g_exp", "o_comm", "", points=[(818, 196), (188, 196)], extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    for i, (a, b, label) in enumerate(
        [("o_comm", "o_state", "感知"), ("o_state", "o_task", "态势"), ("o_task", "o_ctrl", "目标"), ("o_safe", "o_ctrl", "约束")],
        4,
    ):
        add_edge(cells, f"s{i}", a, b, label, main=True, extra="exitX=1;entryX=0;")
    add_edge(cells, "s8", "o_ctrl", "w_auv", "控制作用", main=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "s9", "w_auv", "o_comm", "传感反馈", dashed=True, points=[(475, 665), (20, 665), (20, 315)], extra="exitX=0;entryX=0;")
    add_edge(cells, "s10", "w_sim", "o_comm", "仿真替身", dashed=True, extra="exitX=0.5;exitY=0;entryX=0.35;entryY=1;")
    add_edge(cells, "s11", "w_env", "o_state", "扰动", dashed=True, points=[(1115, 470), (425, 470)], extra="exitX=0.5;exitY=0;entryX=0.5;entryY=1;")
    add_edge(cells, "s12", "o_state", "g_viz", "", dashed=True, points=[(453, 200), (1128, 200)], extra="exitX=0.5;exitY=0;entryX=0.5;entryY=1;")
    write("auv_system_subsystem_organization", cells, page_height=690)


def autonomy_functional_loop() -> None:
    cells: list[str] = []
    for spec in [
        ("env", "环境与艇体", "水流 / 地形 / 动力学", 55, 235, 245, 78, "teal", "io"),
        ("sense", "感知采集", "运动 / 姿态 / 深度 / 健康", 355, 235, 245, 78, "blue", "process"),
        ("state", "状态理解", "位置 / 速度 / 置信度 / 风险", 655, 235, 245, 78, "green", "process"),
        ("decision", "任务决策", "目标选择 / 模式管理", 955, 235, 245, 78, "yellow", "process"),
        ("control", "运动控制", "跟踪 / 约束 / 平滑输出", 655, 430, 245, 78, "green", "process"),
        ("safety", "安全治理", "权限 / 限幅 / 回退 / 急停", 955, 430, 245, 78, "red", "decision"),
        ("operator", "人工监督", "授权 / 接管 / 任务调整", 55, 430, 245, 78, "orange", "io"),
        ("evidence", "运行证据", "记录 / 回放 / 评估", 355, 430, 245, 78, "purple", "data"),
    ]:
        add_shape(cells, *spec)
    for i, (a, b, label) in enumerate(
        [("env", "sense", "观测"), ("sense", "state", "融合"), ("state", "decision", "态势")], 1
    ):
        add_edge(cells, f"l{i}", a, b, label, main=True, extra="exitX=1;entryX=0;")
    add_edge(
        cells,
        "l4",
        "decision",
        "control",
        "",
        main=True,
        points=[(1078, 370), (778, 370)],
        extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;",
    )
    add_edge(cells, "l5", "control", "env", "控制作用", main=True, points=[(780, 585), (25, 585), (25, 275)], extra="exitX=0.5;exitY=1;entryX=0;")
    add_edge(cells, "l6", "operator", "safety", "授权/接管", main=True, points=[(180, 550), (1080, 550)], extra="exitX=0.5;exitY=1;entryX=0.5;entryY=1;")
    add_edge(cells, "l7", "safety", "control", "安全边界", main=True, extra="exitX=0;entryX=1;")
    add_edge(cells, "l8", "state", "safety", "健康与风险", dashed=True, points=[(780, 360), (1080, 360)], extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "l9", "control", "evidence", "执行记录", dashed=True, extra="exitX=0;entryX=1;")
    add_edge(cells, "l10", "evidence", "operator", "复盘", dashed=True, extra="exitX=0;entryX=1;")
    write("auv_system_autonomy_functional_loop", cells, page_height=640)


def thesis_technical_route() -> None:
    cells: list[str] = []
    stages = [
        ("problem", "任务约束", "弱磁目标 / 近底安全 / 感知退化", 35, "blue", "process"),
        ("observe", "主动形成观测", "声磁协同 / 主动横切", 355, "yellow", "process"),
        ("state", "形成可信状态", "ES-EKF / R<sub>s</sub> / P / c<sub>s</sub>", 675, "green", "process"),
        ("action", "采取安全行动", "行为路由 / UA-MPC / 分层保护", 995, "orange", "process"),
        ("evidence", "分层验证", "仿真 / 孪生 / 部署接口", 1315, "purple", "process"),
    ]
    for id_, title, detail, x, color, kind in stages:
        add_shape(cells, id_, title, detail, x, 105, 275, 100, color, kind)
    for i, (source, target, label) in enumerate(
        [
            ("problem", "observe", "问题 A"),
            ("observe", "state", "问题 B"),
            ("state", "action", "问题 C"),
            ("action", "evidence", "问题 D"),
        ],
        1,
    ):
        add_edge(cells, f"tr{i}", source, target, "", main=True, extra="exitX=1;entryX=0;")
        add_note(cells, f"tr{i}_label", label, 290 + (i - 1) * 320, 40, 120, 40, 20, True)

    add_lane(cells, "support", "工程支撑与迁移边界", 180, 315, 1270, 150, "teal")
    supports = [
        ("s1", "双脑异步架构", "Jetson + PC104", 60),
        ("s2", "统一数据契约", "时间 / 坐标 / 置信度", 355),
        ("s3", "虚实共享算法", "可替换接口后端", 650),
        ("s4", "证据边界", "成立条件 / 失效范围", 945),
    ]
    for id_, title, detail, x in supports:
        add_shape(cells, id_, title, detail, x, 52, 245, 65, "teal", "module", "support")
    add_edge(cells, "support_state", "s2", "state", "接口", dashed=True, points=[(657, 300), (812, 300)], extra="exitX=0.5;exitY=0;entryX=0.5;entryY=1;")
    add_edge(cells, "support_action", "s3", "action", "部署", dashed=True, points=[(952, 275), (1132, 275)], extra="exitX=0.5;exitY=0;entryX=0.5;entryY=1;")
    add_edge(cells, "support_evidence", "s4", "evidence", "边界", dashed=True, points=[(1247, 250), (1452, 250)], extra="exitX=0.5;exitY=0;entryX=0.5;entryY=1;")
    write("auv_thesis_technical_route", cells, page_width=1630, page_height=500)


def verification_to_deployment_ladder() -> None:
    cells: list[str] = []
    stages = [
        ("p1", "算法仿真", "基本可控", "模型证据", 30, "green"),
        ("p2", "系统仿真", "闭环协同", "闭环证据", 290, "teal"),
        ("p3", "协议联调", "通信边界", "链路证据", 550, "blue"),
        ("p4", "影子导航", "不夺权观测", "安全证据", 810, "yellow"),
        ("p5", "单回路闭环", "小范围执行", "执行证据", 1070, "orange"),
        ("p6", "全自主试验", "准入目标", "任务证据", 1330, "red"),
    ]
    for pid, title, detail, evidence, x, color in stages:
        add_shape(cells, pid, title, detail, x, 85, 220, 90, color, "process")
        add_shape(cells, f"g_{pid}", "准入门", "风险受控", x + 35, 225, 150, 65, color, "gate")
        add_shape(cells, f"e_{pid}", evidence, "指标 / 日志", x, 345, 220, 78, color, "module")
        add_edge(cells, f"gate_{pid}", pid, f"g_{pid}", "", dashed=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
        add_edge(cells, f"evidence_{pid}", f"g_{pid}", f"e_{pid}", "", dashed=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    for i in range(1, 6):
        add_edge(cells, f"up{i}", f"p{i}", f"p{i+1}", "", main=True, extra="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    add_note(cells, "goal_note", "能力逐级释放 → 右端为目标，不表示全部阶段已完成", 430, 470, 780, 45, 22, True)
    write("auv_system_verification_deployment_ladder", cells, page_width=1580, page_height=540)


def dual_brain_async_hardware() -> None:
    cells: list[str] = []
    add_lane(cells, "jetson", "Jetson Orin：非实时感知与决策", 30, 40, 500, 610, "blue")
    add_lane(cells, "pc104", "PC104 / VxWorks：硬实时执行与保护", 850, 40, 500, 610, "teal")
    add_shape(cells, "gcs", "操作员上位机", "任务配置 / 授权 / 急停", 585, 50, 210, 82, "yellow", "io")
    add_shape(cells, "bus", "双脑协议接口", "$CKTH 72 B / $AUV 145 B", 585, 205, 210, 140, "gray", "module", extra="dashed=1;dashPattern=8 5;fontStyle=1;")
    add_shape(cells, "sensors", "航行与健康传感", "IMU / DVL / 深度 / 故障字", 585, 415, 210, 82, "green", "io")
    add_shape(cells, "actuators", "执行机构", "主推 / 舵机", 585, 545, 210, 72, "orange", "io")
    for spec in [
        ("j0", "运行环境", "Ubuntu / ROS2", 100, 70, 300, 65, "gray", "io", "jetson"),
        ("j1", "感知与估计", "ES-EKF", 100, 185, 300, 70, "green", "process", "jetson"),
        ("j2", "任务决策", "Behavior Tree", 100, 305, 300, 70, "yellow", "process", "jetson"),
        ("j3", "路径与控制意图", "UA-MPC", 100, 425, 300, 70, "purple", "process", "jetson"),
        ("p0", "运行环境", "VxWorks", 100, 70, 300, 65, "gray", "io", "pc104"),
        ("p1", "姿态内环", "硬实时 PID", 100, 185, 300, 70, "green", "process", "pc104"),
        ("p2", "执行器驱动", "电机 / 舵机", 100, 305, 300, 70, "orange", "process", "pc104"),
        ("p3", "本地失效保护", "看门狗 / 防触底", 100, 425, 300, 70, "red", "decision", "pc104"),
    ]:
        add_shape(cells, *spec)
    add_edge(cells, "d1", "j1", "j2", "", main=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "d2", "j2", "j3", "", main=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "d3", "p1", "p2", "", main=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "d4", "p2", "p3", "", main=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "d5", "j3", "bus", "", main=True, points=[(555, 500), (555, 310)], extra="exitX=1;entryX=0;entryY=0.75;")
    add_edge(cells, "d6", "bus", "p1", "下行", main=True, points=[(825, 240)], extra="exitX=1;exitY=0.25;entryX=0;")
    add_edge(cells, "d7", "p3", "bus", "", dashed=True, points=[(825, 500), (825, 325)], extra="exitX=0;entryX=1;entryY=0.75;")
    add_edge(cells, "d8", "bus", "j1", "上行", dashed=True, points=[(555, 220)], extra="exitX=0;exitY=0.2;entryX=1;")
    add_edge(cells, "d9", "gcs", "j2", "", main=True, points=[(555, 91), (555, 380)], extra="exitX=0;entryX=1;")
    add_edge(cells, "d10", "sensors", "p1", "", main=True, points=[(825, 456), (825, 260)], extra="exitX=1;entryX=0;")
    add_edge(cells, "d11", "p2", "actuators", "", main=True, points=[(825, 380), (825, 581)], extra="exitX=0;entryX=1;")
    write("auv_v2_dual_brain_async_hardware", cells, page_height=690)


def uncertainty_highway() -> None:
    cells: list[str] = []
    for spec in [
        ("m", "观测质量", "时延 / SNR / 缺测", 30, 75, 220, 90, "orange", "io"),
        ("r", "分源量测噪声", "质量分 → R<sub>s</sub>", 300, 75, 220, 90, "purple", "process"),
        ("e", "状态与协方差", "ES-EKF：x 与 P", 570, 75, 220, 90, "green", "process"),
        ("u", "分源置信度", "P + 源健康 → c<sub>s</sub>", 840, 75, 220, 90, "purple", "process"),
        ("bt", "行为路由", "精准巡检 / 搜索回落", 660, 285, 300, 88, "yellow", "decision"),
        ("ctrl", "控制调制", "跟踪权重 / 控制代价 / 速度", 1060, 285, 340, 88, "blue", "process"),
    ]:
        add_shape(cells, *spec)
    for i, (a, b, label) in enumerate(
        [("m", "r", "质量分"), ("r", "e", "R_s"), ("e", "u", "P / 源状态")], 1
    ):
        add_edge(cells, f"u{i}", a, b, label, main=True, extra="exitX=1;entryX=0;")
    add_edge(cells, "u4", "u", "bt", "阈值与迟滞", main=True, points=[(950, 230), (810, 230)], extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "u5", "u", "ctrl", "连续参数调度", main=True, points=[(950, 230), (1230, 230)], extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    write("auv_v2_uncertainty_highway", cells, page_width=1440, page_height=420)


def five_layer_functional_architecture() -> None:
    cells: list[str] = []
    lanes = [
        ("l1", "系统入口与配置分发", 30, 25, 1320, 105, "blue"),
        ("l2", "硬件 / 仿真双工适配", 30, 145, 1320, 115, "teal"),
        ("l3", "自治行为与安全治理", 30, 275, 1320, 115, "yellow"),
        ("l4", "数学模型与优化算法", 30, 405, 1320, 125, "green"),
        ("l5", "协议契约与物理约束", 30, 545, 1320, 110, "purple"),
    ]
    for spec in lanes:
        add_lane(cells, *spec)
    nodes = [
        ("a1", "运行模式", "仿真 / 协议 / 真机", 65, 45, 260, 48, "blue", "io", "l1"),
        ("a2", "参数分发", "场景 / 控制 / 安全", 495, 45, 260, 48, "blue", "io", "l1"),
        ("a3", "生命周期", "启动 / 记录 / 收尾", 925, 45, 260, 48, "blue", "process", "l1"),
        ("b1", "虚实统一接口", "同一控制语义", 65, 50, 260, 52, "teal", "module", "l2"),
        ("b2", "坐标与时间对齐", "统一参考系", 495, 50, 260, 52, "teal", "process", "l2"),
        ("b3", "传感与执行抽象", "输入输出对偶", 925, 50, 260, 52, "teal", "module", "l2"),
        ("c1", "任务状态", "阶段 / 模式 / 回退", 65, 50, 260, 52, "yellow", "state", "l3"),
        ("c2", "安全仲裁", "权限 / 急停 / 降级", 495, 45, 260, 62, "red", "decision", "l3"),
        ("c3", "行为选择", "搜索 / 跟踪 / 保守", 925, 50, 260, 52, "yellow", "decision", "l3"),
        ("d1", "运动学模型", "状态演化", 45, 55, 220, 54, "green", "process", "l4"),
        ("d2", "声学投影", "几何观测约束", 340, 55, 220, 54, "green", "process", "l4"),
        ("d3", "误差状态滤波", "不确定性传播", 635, 55, 220, 54, "green", "process", "l4"),
        ("d4", "非线性优化", "安全平滑控制", 930, 55, 250, 54, "green", "process", "l4"),
        ("e1", "通信契约", "最小字节边界", 150, 45, 270, 50, "purple", "data", "l5"),
        ("e2", "物理可行域", "限幅 / 死区 / 饱和", 555, 45, 270, 50, "purple", "gate", "l5"),
        ("e3", "共享语义", "模式 / 状态 / 指令", 960, 45, 270, 50, "purple", "data", "l5"),
    ]
    for spec in nodes:
        add_shape(cells, *spec)
    add_edge(cells, "f1", "a2", "b1", "", main=True, points=[(625, 140), (195, 140)], extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "f2", "b2", "c2", "", main=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "f3", "c3", "d4", "", main=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "f4", "d3", "e2", "", main=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    write("auv_v2_five_layer_functional_architecture", cells, page_height=690)


def behavior_tree_illustration() -> None:
    cells: list[str] = []
    add_lane(cells, "priority_lane", "根节点优先级与调试级联", 30, 30, 1320, 380, "purple")
    add_lane(cells, "mission_lane", "主任务与置信度路由", 30, 430, 1320, 420, "yellow")

    add_shape(cells, "root", "根选择器", "memory=False；逐 tick 重查", 470, 50, 380, 72, "purple", "bt_control", "priority_lane")
    add_shape(cells, "emergency_seq", "紧急顺序", "优先级 1", 55, 155, 300, 68, "red", "bt_control", "priority_lane")
    add_shape(cells, "standby", "待命检查", "未授权 / 链路不可用", 505, 155, 310, 68, "gray", "decision", "priority_lane")
    add_shape(cells, "debug_selector", "调试级联", "优先级 3", 965, 155, 300, 68, "yellow", "bt_control", "priority_lane")
    add_shape(cells, "emergency_condition", "紧急条件", "漏水 / 低电 / 穿底", 35, 270, 240, 68, "red", "decision", "priority_lane")
    add_shape(cells, "emergency_surface", "紧急上浮", "", 300, 270, 180, 68, "red", "process", "priority_lane")
    add_shape(cells, "idle_goal", "IDLE 目标", "安全悬停", 555, 270, 210, 68, "gray", "state", "priority_lane")
    add_shape(cells, "hold_seq", "保持", "调试等级 1", 825, 270, 150, 68, "blue", "bt_control", "priority_lane")
    add_shape(cells, "path_seq", "解析轨迹", "调试等级 2", 990, 270, 155, 68, "teal", "bt_control", "priority_lane")
    add_shape(cells, "main_entry", "主任务", "调试等级 0 / 3", 1160, 270, 145, 68, "green", "bt_control", "priority_lane")

    add_edge(cells, "bt1", "root", "emergency_seq", "1", main=True, safe=True)
    add_edge(cells, "bt2", "root", "standby", "2", main=True)
    add_edge(cells, "bt3", "root", "debug_selector", "3", main=True)
    add_edge(cells, "bt4", "emergency_seq", "emergency_condition", "", safe=True)
    add_edge(cells, "bt5", "emergency_seq", "emergency_surface", "", safe=True)
    add_edge(cells, "bt6", "standby", "idle_goal", "")
    add_edge(cells, "bt7", "debug_selector", "hold_seq", "1")
    add_edge(cells, "bt8", "debug_selector", "path_seq", "2")
    add_edge(cells, "bt9", "debug_selector", "main_entry", "0 / 3", main=True)

    add_shape(cells, "main_seq", "主任务顺序", "Sequence；memory=False", 470, 45, 380, 72, "green", "bt_control", "mission_lane")
    add_shape(cells, "dive", "定深下潜", "目标深度 4 m", 160, 155, 230, 72, "blue", "process", "mission_lane")
    add_shape(cells, "seabed", "海底安全限制", "穿底约束；降速 0.5", 535, 145, 280, 90, "red", "gate", "mission_lane")
    add_shape(cells, "route", "路线路由", "失败回落搜索", 925, 145, 280, 90, "yellow", "bt_control", "mission_lane")
    add_shape(cells, "precise", "精准巡检顺序", "优先分支", 560, 270, 300, 75, "green", "bt_control", "mission_lane")
    add_shape(cells, "zigzag", "之字形搜索", "低置信度分支", 1040, 275, 220, 68, "orange", "process", "mission_lane")
    add_shape(cells, "confidence", "置信度门控", "定位可用且通过门限", 300, 330, 320, 72, "teal", "decision", "mission_lane")
    add_shape(cells, "tracking", "异常限速", "0.4 × 并行跟踪", 700, 330, 320, 72, "green", "process", "mission_lane")

    add_edge(cells, "bt10", "main_entry", "main_seq", "", main=True, dashed=True, points=[(1330, 390), (1330, 465), (690, 465)], extra="exitX=1;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "bt11", "main_seq", "dive", "", main=True)
    add_edge(cells, "bt12", "main_seq", "seabed", "", main=True)
    add_edge(cells, "bt13", "seabed", "route", "", main=True, safe=True)
    add_edge(cells, "bt14", "route", "precise", "", main=True)
    add_edge(cells, "bt15", "route", "zigzag", "回落")
    add_edge(cells, "bt16", "precise", "confidence", "")
    add_edge(cells, "bt17", "precise", "tracking", "", main=True)
    write("auv_v2_behavior_tree_illustration", cells, page_height=880)


def mission_state_machine() -> None:
    cells: list[str] = []
    states = [
        ("idle", "IDLE", "上电空闲", 35, 70, 220, 86, "gray"),
        ("pre", "PREFLIGHT", "预检 / 授权", 340, 70, 220, 86, "yellow"),
        ("shadow", "SHADOW", "影子导航，不夺权", 645, 70, 230, 86, "orange"),
        ("single", "SINGLE LOOP", "单回路闭环", 960, 70, 230, 86, "blue"),
        ("full", "FULL AUTONOMY", "全自主任务", 1275, 70, 245, 86, "green"),
    ]
    for id_, title, detail, x, y, w, h, color in states:
        add_shape(cells, id_, title, detail, x, y, w, h, color, "state")
    add_shape(cells, "complete", "COMPLETE", "收尾 / 回收", 990, 305, 230, 86, "purple", "terminal")
    add_shape(cells, "safe", "SAFE HOLD", "安全保持 / 回退", 1300, 305, 230, 86, "red", "state")
    transitions = [
        ("idle", "pre", "启动", 238),
        ("pre", "shadow", "预检通过", 543),
        ("shadow", "single", "影子稳定", 858),
        ("single", "full", "闭环稳定", 1173),
    ]
    for i, (a, b, label, note_x) in enumerate(transitions, 1):
        add_note(cells, f"m{i}_label", label, note_x, 15, 120, 38, 18, True)
        add_edge(cells, f"m{i}", a, b, "", main=True, extra="exitX=1;entryX=0;")
    add_edge(cells, "m5", "full", "complete", "任务完成", main=True, points=[(1390, 240), (1105, 240)], extra="exitX=0.35;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "m6", "full", "safe", "安全触发", safe=True, extra="exitX=0.8;exitY=1;entryX=0.8;entryY=0;")
    add_edge(cells, "m7", "single", "safe", "偏差过大", dashed=True, points=[(1125, 205), (1415, 205)], extra="exitX=0.7;exitY=1;entryX=0.25;entryY=0;")
    add_edge(cells, "m8", "shadow", "safe", "置信度不足", dashed=True, points=[(805, 270), (1330, 270)], extra="exitX=0.7;exitY=1;entryX=0.1;entryY=0;")
    add_edge(cells, "m9", "safe", "pre", "复位后再预检", dashed=True, points=[(1415, 485), (450, 485)], extra="exitX=0.5;exitY=1;entryX=0.5;entryY=1;")
    add_edge(cells, "m10", "complete", "idle", "回到空闲", dashed=True, points=[(1105, 535), (145, 535)], extra="exitX=0.5;exitY=1;entryX=0.5;entryY=1;")
    write("auv_v2_mission_state_machine", cells, page_width=1580, page_height=575)


def emergency_transition() -> None:
    cells: list[str] = []
    add_lane(cells, "trigger_lane", "触发条件", 30, 25, 400, 600, "red")
    add_lane(cells, "layer_lane", "处置层级", 500, 25, 400, 600, "purple")
    add_lane(cells, "action_lane", "目标动作", 970, 25, 400, 600, "teal")
    for spec in [
        ("g1", "链路或授权异常", "命令陈旧 / 授权撤销", 55, 65, 310, 78, "red", "io", "trigger_lane"),
        ("g2", "定位置信不足", "门控未通过", 55, 185, 310, 78, "orange", "io", "trigger_lane"),
        ("g3", "独立紧急条件", "漏水 / 低电 / 穿底", 55, 305, 310, 78, "red", "io", "trigger_lane"),
        ("g4", "人工急停", "地面站 ESTOP", 55, 425, 310, 78, "red", "io", "trigger_lane"),
        ("arb", "ROS2 权限仲裁", "新鲜度 / 授权", 45, 65, 310, 78, "purple", "decision", "layer_lane"),
        ("task", "行为树任务路由", "置信门控逐 tick 判定", 45, 185, 310, 78, "yellow", "decision", "layer_lane"),
        ("emergency", "行为树 / PC104 保护", "故障字抢占 / 本地覆盖", 45, 305, 310, 78, "red", "decision", "layer_lane"),
        ("estop", "ROS2 / PC104 急停链", "锁存并回零", 45, 425, 310, 78, "red", "decision", "layer_lane"),
        ("zero", "回零与 REMOTE 锁定", "停止释放自主指令", 45, 65, 310, 78, "gray", "state", "action_lane"),
        ("search", "搜索回落", "低置信度不触发上浮", 45, 185, 310, 78, "yellow", "state", "action_lane"),
        ("surface", "紧急上浮 / 防触底", "独立安全条件", 45, 305, 310, 78, "orange", "state", "action_lane"),
        ("kill", "急停截止", "锁存零执行量", 45, 425, 310, 78, "red", "terminal", "action_lane"),
    ]:
        add_shape(cells, *spec)
    rows = [
        ("g1", "arb", "zero", "新鲜度 / 授权", "回零"),
        ("g2", "task", "search", "置信门控", "任务降级"),
        ("g3", "emergency", "surface", "安全字 / 本地检测", "安全抢占"),
        ("g4", "estop", "kill", "ESTOP", "锁存"),
    ]
    for i, (trigger, layer, action, in_label, out_label) in enumerate(rows, 1):
        add_edge(cells, f"eg{i}a", trigger, layer, in_label, safe=i in {3, 4}, main=i in {1, 2}, extra="exitX=1;entryX=0;")
        add_edge(cells, f"eg{i}b", layer, action, out_label, safe=i in {3, 4}, main=i in {1, 2}, extra="exitX=1;entryX=0;")
    write("auv_v2_emergency_transition", cells, page_width=1400, page_height=650)


def mission_lifecycle_flow() -> None:
    cells: list[str] = []
    add_lane(cells, "op", "操作员 / 地面站", 30, 25, 1320, 130, "orange")
    add_lane(cells, "arb", "安全守卫 / 权限仲裁", 30, 170, 1320, 130, "red")
    add_lane(cells, "brain", "决策与控制", 30, 315, 1320, 145, "blue")
    add_lane(cells, "exec", "执行与反馈", 30, 475, 1320, 130, "teal")
    xs = [45, 305, 565, 825, 1085]
    op_nodes = [
        ("op1", "任务配置", "航线 / 场景 / 目标", "io", "yellow"),
        ("op2", "预检授权", "签发权限", "gate", "yellow"),
        ("op3", "任务监视", "看板 / 视频", "data", "purple"),
        ("op4", "干预窗口", "必要时接管", "io", "orange"),
        ("op5", "任务收尾", "复盘 / 归档", "data", "gray"),
    ]
    ar_nodes = [
        ("ar1", "权限锁定", "拒绝越权", "decision", "red"),
        ("ar2", "守卫检查", "通信 / 电压 / 置信度", "decision", "red"),
        ("ar3", "权限迁移", "REMOTE → AUTONOMOUS", "gate", "purple"),
        ("ar4", "分层回退", "回零 / 本地覆盖", "decision", "red"),
        ("ar5", "结束确认", "关闭自主权限", "gate", "gray"),
    ]
    br_nodes = [
        ("br1", "状态估计", "ES-EKF 初始化", "process", "green"),
        ("br2", "行为树运行", "选择任务分支", "process", "yellow"),
        ("br3", "安全控制", "生成控制指令", "process", "blue"),
        ("br4", "健康监测", "置信度 / 故障", "process", "green"),
        ("br5", "任务报告", "汇总运行证据", "data", "purple"),
    ]
    ex_nodes = [
        ("ex1", "传感上行", "DVL / IMU / 深度", "io", "teal"),
        ("ex2", "执行下行", "舵角 / 推力", "io", "teal"),
        ("ex3", "响应反馈", "姿态 / 位置", "io", "teal"),
        ("ex4", "故障上报", "漏水 / 深度 / DVL", "io", "red"),
        ("ex5", "上浮回收", "人工断电", "terminal", "gray"),
    ]
    for nodes, parent, y in [(op_nodes, "op", 50), (ar_nodes, "arb", 45), (br_nodes, "brain", 52), (ex_nodes, "exec", 45)]:
        for x, (id_, title, detail, kind, color) in zip(xs, nodes):
            height = 72 if id_ == "ar3" else 62
            node_y = 40 if id_ == "ar3" else y
            add_shape(cells, id_, title, detail, x, node_y, 215, height, color, kind, parent)
    for prefix in ["op", "ar", "br"]:
        for i in range(1, 5):
            add_edge(cells, f"{prefix}_flow_{i}", f"{prefix}{i}", f"{prefix}{i+1}", "", main=i in {1, 2, 4}, extra="exitX=1;entryX=0;")
    add_edge(cells, "ml1", "op2", "ar2", "", main=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "ml2", "ar3", "br2", "", main=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "ml3", "br3", "ex2", "", main=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "ml4", "ex1", "br1", "", main=True, extra="exitX=0.5;exitY=0;entryX=0.5;entryY=1;")
    add_edge(cells, "ml5", "ex3", "br4", "", dashed=True, extra="exitX=0.5;exitY=0;entryX=0.35;entryY=1;")
    add_edge(cells, "ml6", "ex4", "br4", "", safe=True, extra="exitX=0.5;exitY=0;entryX=0.65;entryY=1;")
    add_edge(cells, "ml7", "br4", "ar4", "", safe=True, extra="exitX=0.65;exitY=0;entryX=0.65;entryY=1;")
    add_edge(cells, "ml8", "ar4", "op4", "", dashed=True, extra="exitX=0.5;exitY=0;entryX=0.5;entryY=1;")
    add_edge(cells, "ml9", "op5", "ar5", "", main=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "ml10", "ar5", "br5", "", main=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "ml11", "br5", "ex5", "", main=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    write("auv_v2_mission_lifecycle_flow", cells, page_height=640)


def main() -> None:
    code_layer_architecture()
    runtime_dataflow()
    ros2_node_topology()
    safety_arbiter_deployment()
    system_capability_map()
    system_subsystem_organization()
    autonomy_functional_loop()
    thesis_technical_route()
    verification_to_deployment_ladder()
    dual_brain_async_hardware()
    uncertainty_highway()
    five_layer_functional_architecture()
    behavior_tree_illustration()
    mission_state_machine()
    emergency_transition()
    mission_lifecycle_flow()
    for path in sorted(THESIS_OUT.glob("*.drawio")):
        print(path)
    for path in sorted(INTERNAL_OUT.glob("*.drawio")):
        print(path)


if __name__ == "__main__":
    main()
