"""Generate the canonical Draw.io architecture diagrams used by the thesis.

Figure titles, subtitles, captions, and long legends intentionally live in the
LaTeX/Markdown publication layer. The diagram canvas contains only information
needed to understand the structure itself.
"""

from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
from split_five_layer_architecture import split_drawio


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


def compact_cells(cells: list[str], *, x: float = 1, y: float = 1,
                  font: float = 1) -> list[str]:
    """Scale layout dimensions, with independently fixed border line widths.

    Relative edge x is a path fraction, not a length. Cell text, identifiers,
    ports, stroke widths and graph relationships remain unchanged.
    """
    root = ET.fromstring('<root>' + ''.join(cells) + '</root>')
    for cell in root:
        for element in cell.iter():
            if element.tag in ('mxGeometry', 'mxPoint'):
                for key, factor in [('x', x), ('y', y), ('width', x), ('height', y)]:
                    if key not in element.attrib:
                        continue
                    if element.tag == 'mxGeometry' and element.get('relative') == '1' and key == 'x':
                        continue
                    element.set(key, f'{float(element.get(key)) * factor:g}')
        style = []
        for part in cell.get('style', '').split(';'):
            key, sep, value = part.partition('=')
            if sep and key == 'fontSize':
                value = f'{float(value) * font:g}'
            elif sep and key in ('spacing', 'spacingLeft', 'spacingRight', 'spacingTop', 'spacingBottom'):
                value = f'{float(value) * min(x, y):g}'
            style.append(key + sep + value)
        cell.set('style', ';'.join(style))
    return [ET.tostring(c, encoding='unicode') for c in root]


def compact_final_lane(cells: list[str], lane_id: str, ratio: float) -> list[str]:
    """Tighten the final swimlane; retain the dense priority panel above it."""
    root = ET.fromstring('<root>' + ''.join(cells) + '</root>')
    lane = next(c for c in root if c.get('id') == lane_id)
    origin = float(lane.find('mxGeometry').get('y'))
    for cell in root:
        geometry = cell.find('mxGeometry')
        if geometry is not None:
            if cell.get('id') == lane_id or cell.get('parent') == lane_id:
                geometry.set('height', f'{float(geometry.get("height")) * ratio:g}')
            if cell.get('parent') == lane_id:
                geometry.set('y', f'{float(geometry.get("y")) * ratio:g}')
        for point in cell.iter('mxPoint'):
            if 'y' in point.attrib and float(point.get('y')) >= origin:
                point.set('y', f'{origin + (float(point.get("y"))-origin)*ratio:g}')
    return [ET.tostring(c, encoding='unicode') for c in root]


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
    label_offset: tuple[float, float] | None = None,
) -> None:
    if direct:
        base = EDGE_DIRECT_DASH if dashed else EDGE_DIRECT
    else:
        base = EDGE_SAFE if safe else (EDGE_MAIN if main else (EDGE_DASH if dashed else EDGE))
    if points:
        point_xml = "".join(f'<mxPoint x="{x}" y="{y}" />' for x, y in points)
        label_attrs = f' x="{label_offset[0]}" y="{label_offset[1]}"' if label_offset else ""
        geometry = (
            f'<mxGeometry relative="1"{label_attrs} as="geometry"><Array as="points">'
            f"{point_xml}</Array></mxGeometry>"
        )
    else:
        label_attrs = f' x="{label_offset[0]}" y="{label_offset[1]}"' if label_offset else ""
        geometry = f'<mxGeometry relative="1"{label_attrs} as="geometry" />'
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
        ("app", "应用与运行入口", 30, 30, 1320, 250, "blue"),
        ("interface", "接口与虚实适配", 30, 330, 1320, 250, "teal"),
        ("behavior", "行为与安全治理", 30, 630, 1320, 300, "yellow"),
        ("algorithm", "算法与优化", 30, 1000, 1320, 250, "green"),
        ("common", "共享协议与物理约束", 30, 1320, 1320, 260, "purple"),
    ]
    for spec in lanes:
        add_lane(cells, *spec)
        cells[-1] = cells[-1].replace("startSize=38;", "startSize=54;")
    nodes = [
        ("a1", "独立仿真入口", "main.py", 55, 80, 225, 140, "blue", "io", "app"),
        ("a2", "单进程闭环", "main_loop.py", 355, 90, 225, 120, "blue", "process", "app"),
        ("a3", "桥接运行入口", "run_zenoh_<br>bridge.py", 655, 80, 250, 140, "blue", "io", "app"),
        ("a4", "实验编排入口", "start_<br>experiment.sh", 980, 80, 260, 140, "blue", "io", "app"),
        ("i1", "仿真后端适配", "HoloOcean / PVS", 55, 90, 245, 120, "teal", "module", "interface"),
        ("i2", "坐标转换", "UE4 ↔ NED", 360, 90, 220, 120, "teal", "module", "interface"),
        ("i3", "跨进程通信", "Zenoh / UDP", 650, 90, 220, 120, "teal", "module", "interface"),
        ("i4", "协议级硬件替身", "Mock AMD", 940, 90, 250, 120, "teal", "module", "interface"),
        ("b1", "命令守卫", "合法性过滤", 150, 75, 245, 190, "yellow", "decision", "behavior"),
        ("b2", "安全监控", "限幅 / 急停 / 回退", 530, 75, 245, 190, "red", "decision", "behavior"),
        ("b3", "任务状态管理", "阶段 / 模式", 910, 110, 245, 120, "yellow", "state", "behavior"),
        ("g1", "LOS 制导", "guidance.py", 40, 90, 210, 130, "green", "process", "algorithm"),
        ("g2", "级联 PID", "auv_pid_<br>controller.py", 300, 90, 230, 130, "green", "process", "algorithm"),
        ("g3", "MPC / UA-MPC", "auv_mpc_<br>controller.py", 580, 90, 230, 130, "green", "process", "algorithm"),
        ("g4", "状态估计", "es_ekf.py", 860, 90, 190, 130, "green", "process", "algorithm"),
        ("g5", "轨迹生成", "trajectory_<br>generator.py", 1090, 90, 205, 130, "green", "process", "algorithm"),
        ("c1", "通信契约", "Topic / Payload", 125, 80, 260, 140, "purple", "data", "common"),
        ("c2", "共享语义", "模式 / 指令 / 状态", 535, 80, 260, 140, "purple", "data", "common"),
        ("c3", "物理边界", "限幅 / 饱和 / 日志", 945, 80, 260, 140, "purple", "data", "common"),
    ]
    for spec in nodes:
        add_shape(cells, *spec, extra="fontSize=20;")
    add_edge(cells, "e1", "a2", "i1", "", main=True, points=[(497.5, 305), (207.5, 305)], extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "e2", "a3", "i3", "", main=True, points=[(810, 305), (1040, 305), (1040, 395), (790, 395)], extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(
        cells,
        "e3",
        "i3",
        "c1",
        "协议",
        points=[(790, 590), (1375, 590), (1375, 1610), (285, 1610)],
        extra="exitX=0.5;exitY=1;entryX=0.5;entryY=1;",
    )
    add_edge(cells, "e4", "b2", "g2", "约束", points=[(682.5, 970), (445, 970)], extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "e5", "g2", "c3", "物理限幅", points=[(445, 1280), (1105, 1280)], extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    write("auv_code_layer_architecture", cells, out=INTERNAL_OUT, page_width=1420, page_height=1660)


def runtime_dataflow() -> None:
    cells: list[str] = []
    add_lane(cells, "single", "路径 A：单进程算法验证闭环", 30, 30, 1940, 600, "green")
    add_lane(cells, "bridge", "路径 B：桥接集成与部署接口闭环", 30, 700, 1940, 770, "blue")
    cells[:] = [c.replace("startSize=38;", "startSize=60;") for c in cells]
    for spec in [
        ("s1", "目标与轨迹", "参考路点", 50, 160, 250, 160, "blue", "io", "single"),
        ("s2", "制导", "航向 / 深度参考", 420, 175, 250, 130, "green", "process", "single"),
        ("s3", "控制器", "舵角 / 推力", 790, 175, 250, 130, "green", "process", "single"),
        ("s4", "安全过滤", "限幅 / 回退", 1160, 120, 300, 240, "yellow", "decision", "single"),
        ("s5", "仿真后端", "PVS / HoloOcean", 1590, 160, 290, 160, "teal", "io", "single"),
        ("s6", "传感器状态", "位置 / 姿态 / 速度", 790, 420, 340, 130, "gray", "data", "single"),
        ("b1", "数字孪生或硬件替身", "PVS / HoloOcean<br>Mock AMD", 40, 140, 360, 180, "teal", "io", "bridge"),
        ("b2", "坐标与帧转换", "统一参考系", 520, 160, 270, 140, "teal", "process", "bridge"),
        ("b3", "跨进程协议", "Zenoh / UDP", 910, 150, 260, 160, "purple", "data", "bridge"),
        ("b4", "ROS2 桥接", "传感 / 控制 Topic", 1290, 160, 270, 140, "blue", "process", "bridge"),
        ("b5", "状态估计", "ES-EKF", 1680, 160, 220, 140, "green", "process", "bridge"),
        ("b6", "任务决策", "行为树设定点", 1640, 490, 260, 150, "yellow", "process", "bridge"),
        ("b7", "控制器", "PID / MPC", 1220, 490, 280, 150, "green", "process", "bridge"),
        ("b8", "下行控制", "安全仲裁命令", 820, 475, 280, 180, "orange", "io", "bridge"),
        ("b9", "实验黑匣子", "日志 / MCAP / 指标", 410, 475, 280, 180, "purple", "data", "bridge"),
    ]:
        add_shape(cells, *spec, extra="fontSize=24;")
    for i, (a, b, label) in enumerate(
        [("s1", "s2", "参考"), ("s2", "s3", "目标"), ("s3", "s4", "控制"), ("s4", "s5", "安全指令")], 1
    ):
        add_edge(cells, f"sa{i}", a, b, label, main=True, extra="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    add_edge(cells, "sa5", "s5", "s6", "回读", points=[(1765, 515), (1180, 515)], extra="exitX=0.5;exitY=1;entryX=1;entryY=0.5;")
    add_edge(cells, "sa6", "s6", "s2", "闭环反馈", dashed=True, points=[(575, 515)], extra="exitX=0;exitY=0.5;entryX=0.5;entryY=1;")
    for i, (a, b, label) in enumerate(
        [("b1", "b2", "状态"), ("b2", "b3", "统一帧"), ("b3", "b4", "协议帧"), ("b4", "b5", "传感 Topic")], 1
    ):
        add_edge(cells, f"ba{i}", a, b, label, main=True, extra="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    add_edge(cells, "ba5", "b5", "b6", "状态与健康", extra="exitX=0.65;exitY=1;entryX=0.65;entryY=0;")
    add_edge(cells, "ba6", "b6", "b7", "设定点", main=True, extra="exitX=0;exitY=0.5;entryX=1;entryY=0.5;")
    add_edge(cells, "ba7", "b5", "b7", "滤波状态", points=[(1765, 1080), (1630, 1080), (1630, 1120), (1420, 1120)], extra="exitX=0.25;exitY=1;entryX=0.6;entryY=0;")
    add_edge(cells, "ba8", "b7", "b8", "控制命令", main=True, extra="exitX=0;exitY=0.5;entryX=1;entryY=0.5;")
    add_edge(cells, "ba9", "b8", "b3", "编码", extra="exitX=0.5;exitY=0;entryX=0.5;entryY=1;")
    add_edge(cells, "ba10", "b4", "b9", "运行证据", dashed=True, points=[(1563, 1030), (1945, 1030), (1945, 1400), (580, 1400)], extra="exitX=0.9;exitY=1;entryX=0.5;entryY=1;")
    add_edge(cells, "ba11", "b3", "b1", "执行反馈", dashed=True, points=[(992, 1080), (780, 1080), (780, 1440), (250, 1440)], extra="exitX=0.2;exitY=1;entryX=0.5;entryY=1;")
    write("auv_runtime_dataflow", cells, page_width=2020, page_height=1520)


def ros2_node_topology() -> None:
    cells: list[str] = []
    add_lane(cells, "external", "外部系统与操作端", 30, 30, 1850, 340, "gray")
    add_lane(cells, "ros", "ROS2 在线闭环", 30, 450, 1850, 650, "blue")
    add_lane(cells, "evidence", "可视化与离线证据", 30, 1190, 1850, 340, "purple")
    cells[:] = [c.replace("startSize=38;", "startSize=60;") for c in cells]
    for spec in [
        ("x1", "仿真/实物接口", "传感器与执行器", 100, 120, 350, 160, "teal", "io", "external"),
        ("x3", "跨进程链路", "UDP / Zenoh", 730, 120, 350, 160, "purple", "data", "external"),
        ("x2", "操作员控制台", "遥控 / 授权 / 急停", 1350, 120, 350, 160, "orange", "io", "external"),
        ("n1", "协议桥", "auv_bridge", 100, 140, 280, 140, "blue", "module", "ros"),
        ("n2", "定位与融合", "ES-EKF", 550, 140, 280, 140, "green", "module", "ros"),
        ("n3", "控制器", "PID / MPC", 1000, 140, 280, 140, "green", "module", "ros"),
        ("n4", "任务决策", "Behavior Tree", 1450, 140, 280, 140, "yellow", "module", "ros"),
        ("bus", "ROS2 Topic 总线", "传感 / 状态 / 设定点 / 命令", 400, 410, 1100, 160, "gray", "data", "ros"),
        ("n5", "可视化桥", "Foxglove / Console", 150, 140, 350, 140, "purple", "module", "evidence"),
        ("n6", "实验黑匣子", "rosbag / MCAP", 750, 130, 350, 160, "purple", "data", "evidence"),
        ("n7", "离线分析", "图表 / KPI", 1350, 140, 350, 140, "purple", "process", "evidence"),
    ]:
        add_shape(cells, *spec)
    add_edge(cells, "r1", "x1", "x3", "状态/执行", main=True, extra="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    add_edge(cells, "r2", "x2", "x3", "授权/急停", extra="exitX=0;exitY=0.5;entryX=1;entryY=0.5;")
    add_edge(cells, "r3", "x3", "n1", "", main=True, points=[(935, 410), (270, 410)], extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    for i, node in enumerate(["n1", "n2", "n3", "n4"], 1):
        add_edge(cells, f"rbus{i}", node, "bus", "", points=[(270+450*(i-1), 810), (567.5+275*(i-1), 810)], extra=f"exitX=0.5;exitY=1;entryX={(i-.5)/4};entryY=0;")
    add_edge(cells, "r4", "bus", "n5", "状态/行为", dashed=True, points=[(650, 1145), (355, 1145)], extra="exitX=0.2;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "r5", "bus", "n6", "记录 Topic", dashed=True, points=[(980, 1150), (1260, 1150), (1260, 1290), (955, 1290)], extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "r6", "n6", "n7", "离线分析", main=True, extra="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    write("auv_ros2_node_topology", cells, out=INTERNAL_OUT, page_width=1920, page_height=1580)


def safety_arbiter_deployment() -> None:
    cells: list[str] = []
    add_lane(cells, "pc", "地面站", 30, 100, 400, 1710, "orange")
    add_lane(cells, "jetson", "Jetson 仲裁与控制", 500, 100, 1260, 1710, "blue")
    add_lane(cells, "pc104", "PC104 硬实时执行", 1830, 100, 500, 1710, "teal")
    cells[:] = [c.replace("startSize=38;", "startSize=60;") for c in cells]
    for spec in [
        ("p1", "操作员命令", "遥控 / 授权 / 急停", 70, 170, 260, 160, "orange", "io", "pc"),
        ("p2", "链路新鲜度", "上行年龄 / 看门狗", 70, 650, 260, 160, "yellow", "io", "pc"),
        ("p3", "显式确认", "实物阶段准入", 70, 1130, 260, 190, "red", "gate", "pc"),
        ("j1", "协议编解码", "上/下行", 100, 180, 350, 140, "blue", "process", "jetson"),
        ("j2", "AutonomyGuard", "漏水 / 电压<br>置信度 / 时延", 70, 610, 450, 280, "red", "decision", "jetson"),
        ("j3", "控制权仲裁", "REMOTE ↔ AUTONOMOUS", 70, 1080, 450, 300, "purple", "decision", "jetson"),
        ("j4", "任务决策", "行为树设定点", 800, 180, 350, 140, "yellow", "process", "jetson"),
        ("j5", "控制器", "PID / MPC / Terrain", 800, 650, 350, 140, "green", "process", "jetson"),
        ("j6", "影子路径", "只记录，不执行", 800, 1120, 350, 180, "gray", "data", "jetson"),
        ("j7", "安全回退", "零推力并锁回 REMOTE", 470, 1510, 360, 160, "red", "state", "jetson"),
        ("a1", "状态上行", "传感器 / 健康", 75, 170, 350, 160, "teal", "io", "pc104"),
        ("a2", "控制输出", "4 舵 + 推力", 75, 650, 350, 160, "teal", "io", "pc104"),
        ("a3", "执行准入", "极性 / 死区静态验证", 75, 1130, 350, 190, "yellow", "gate", "pc104"),
    ]:
        add_shape(cells, *spec)
    add_edge(cells, "e1", "p1", "j1", "命令/授权", main=True, extra="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    add_edge(cells, "e2", "p2", "j2", "新鲜度", extra="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    add_edge(cells, "e3", "p3", "j3", "释放权限", dashed=True, extra="exitX=0.5;exitY=1;exitPerimeter=0;entryX=0;entryY=0.5;")
    add_edge(cells, "e4", "a1", "j1", "上行遥测", main=True, points=[(2080, 215), (862.5, 215)], extra="exitX=0.5;exitY=0;entryX=0.75;entryY=0;")
    add_edge(cells, "e5", "j1", "j2", "申请自主", main=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "e6", "j2", "j3", "准许/拒绝", main=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "e7", "j4", "j5", "设定点", extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "e8", "j5", "j3", "候选命令", points=[(1475, 1060), (907.5, 1060)], extra="exitX=0.5;exitY=1;entryX=0.75;entryY=0;")
    add_edge(cells, "e9", "j3", "a2", "选定命令", main=True, points=[(1120, 1330), (1120, 680), (1775, 680), (1775, 830)], extra="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    add_edge(cells, "e10", "j3", "j7", "超时/急停", safe=True, points=[(750, 1545), (1114, 1545)], extra="exitX=0.4;exitY=1;entryX=0.4;entryY=0;")
    add_edge(cells, "e11", "j7", "a2", "零推力", safe=True, points=[(1785, 1690), (1785, 920), (1865, 920), (1865, 870)], extra="exitX=1;exitY=0.5;entryX=0;entryY=0.75;")
    add_edge(cells, "e12", "j6", "j3", "影子快照", dashed=True, points=[(1180, 1310), (1180, 1405)], extra="exitX=0;exitY=0.5;entryX=0.75;entryY=0.75;entryPerimeter=0;")
    add_edge(cells, "e13", "a3", "a2", "通过后释放", extra="exitX=0.9473684211;exitY=0.5;exitPerimeter=0;entryX=0.5;entryY=1;")
    write("auv_safety_arbiter_deployment", cells, out=INTERNAL_OUT, page_width=2380, page_height=1860)


def system_capability_map() -> None:
    cells: list[str] = []
    add_shape(cells, "core", "自主任务平台", "任务执行 / 安全控制 / 数据闭环", 505, 275, 370, 100, "blue", "process")
    for spec in [
        ("sim", "仿真与环境", "场景 / 传感 / 执行响应", 55, 70, 310, 80, "teal", "io"),
        ("auto", "自主决策控制", "估计 / 决策 / 控制", 535, 45, 310, 80, "green", "process"),
        ("human", "人机协同", "授权 / 接管 / 急停", 1015, 70, 310, 80, "orange", "io"),
        ("deploy", "实物部署", "分级试验 / 安全回退", 55, 485, 310, 120, "red", "gate"),
        ("evidence", "实验验证", "编排 / 指标 / 对比", 535, 510, 310, 120, "yellow", "gate"),
        ("obs", "运行证据", "看板 / 日志 / 黑匣子", 1015, 485, 310, 120, "purple", "data"),
    ]:
        add_shape(cells, *spec)
    add_edge(cells, "c1", "sim", "core", "仿真输入", main=True, points=[(210, 220), (505, 325)], extra="exitX=0.5;exitY=1;entryX=0;entryY=0.5;")
    add_edge(cells, "c2", "auto", "core", "自主能力", main=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "c3", "human", "core", "人工授权", main=True, points=[(1170, 220), (875, 325)], extra="exitX=0.5;exitY=1;entryX=1;entryY=0.5;")
    add_edge(cells, "c4", "core", "deploy", "工程迁移", direct=True, points=[(450, 440), (210, 440)], extra="fontStyle=1;exitX=0;exitY=0.7;entryX=0.9166666667;entryY=0.5;entryPerimeter=0;")
    add_edge(cells, "c5", "core", "evidence", "实验数据", main=True, extra="exitX=0.5;exitY=1;entryX=0.9166666667;entryY=0.5;entryPerimeter=0;")
    add_edge(cells, "c6", "core", "obs", "运行记录", main=True, points=[(875, 450), (1170, 450)], extra="exitX=1;exitY=0.7;entryX=0.5;entryY=0;")
    add_edge(cells, "c7", "evidence", "sim", "场景反哺", dashed=True, points=[(445, 645), (25, 645), (25, 110)], extra="exitX=0;entryX=0;", label_offset=(0.35, -100))
    add_edge(cells, "c8", "obs", "human", "态势反馈", dashed=True, points=[(1350, 540), (1350, 110)], extra="exitX=1;entryX=1;")
    write("auv_system_capability_map", cells, page_height=670)


def system_subsystem_organization() -> None:
    cells: list[str] = []
    add_lane(cells, "ground", "地面与实验侧", 30, 30, 2400, 320, "orange")
    add_lane(cells, "onboard", "艇载自治侧", 30, 550, 2400, 450, "blue")
    add_lane(cells, "world", "环境与被控对象侧", 30, 1250, 2400, 400, "teal")
    cells[:] = [c.replace("startSize=38;", "startSize=60;") for c in cells]
    for spec in [
        ("g_task", "任务设计", "航线 / 场景 / 目标", 100, 100, 350, 160, "yellow", "io", "ground"),
        ("g_ops", "操作监督", "授权 / 接管 / 急停", 650, 100, 350, 160, "orange", "io", "ground"),
        ("g_exp", "实验管理", "启动 / 记录 / 评估", 1200, 100, 350, 160, "purple", "process", "ground"),
        ("g_viz", "可视化分析", "态势 / 图表 / 报告", 1750, 100, 350, 160, "purple", "data", "ground"),
        ("o_comm", "通信接入", "上行感知 / 下行控制", 60, 140, 340, 160, "blue", "module", "onboard"),
        ("o_state", "状态理解", "定位 / 健康 / 置信度", 550, 140, 340, 160, "green", "process", "onboard"),
        ("o_task", "任务智能", "模式 / 行为选择", 1040, 140, 340, 160, "yellow", "process", "onboard"),
        ("o_ctrl", "运动执行", "控制 / 安全限幅", 1530, 140, 340, 160, "green", "process", "onboard"),
        ("o_safe", "安全治理", "权限 / 故障回退", 2020, 80, 330, 280, "red", "decision", "onboard"),
        ("w_sim", "虚拟海洋", "场景 / 扰动注入", 150, 100, 480, 180, "teal", "io", "world"),
        ("w_auv", "真实 AUV", "传感 / 执行 / 动力学", 960, 100, 480, 180, "teal", "io", "world"),
        ("w_env", "外部环境", "水流 / 地形 / 通信", 1770, 100, 480, 180, "gray", "io", "world"),
    ]:
        add_shape(cells, *spec)
    add_edge(cells, "s1", "g_task", "o_task", "", points=[(305, 400), (1104, 400)], extra="exitX=0.5;exitY=1;entryX=0.1;entryY=0;")
    add_edge(cells, "s2", "g_ops", "o_safe", "", main=True, points=[(855, 435), (2215, 435)], extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "s3", "g_exp", "o_comm", "", points=[(1405, 470), (260, 470)], extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    for i, (a, b, label) in enumerate(
        [("o_comm", "o_state", "感知"), ("o_state", "o_task", "态势"), ("o_task", "o_ctrl", "目标")], 4
    ):
        add_edge(cells, f"s{i}", a, b, label, main=True, extra="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    add_edge(cells, "s7", "o_safe", "o_ctrl", "约束", main=True, extra="exitX=0;exitY=0.5;entryX=1;entryY=0.5;")
    add_edge(cells, "s8", "o_ctrl", "w_auv", "控制作用", main=True, points=[(1730, 1150), (1398, 1150)], extra="exitX=0.5;exitY=1;entryX=0.85;entryY=0;")
    add_edge(cells, "s9", "w_auv", "o_comm", "传感反馈", dashed=True, points=[(1230, 1690), (10, 1690), (10, 770)], extra="exitX=0.5;exitY=1;entryX=0;entryY=0.5;")
    add_edge(cells, "s10", "w_sim", "o_comm", "仿真替身", dashed=True, points=[(420, 1080), (209, 1080)], extra="exitX=0.5;exitY=0;entryX=0.35;entryY=1;")
    add_edge(cells, "s11", "w_env", "o_state", "扰动", dashed=True, points=[(2040, 1040), (750, 1040)], extra="exitX=0.5;exitY=0;entryX=0.5;entryY=1;")
    add_edge(cells, "s12", "o_state", "g_viz", "", dashed=True, points=[(750, 510), (1955, 510)], extra="exitX=0.5;exitY=0;entryX=0.5;entryY=1;")
    write("auv_system_subsystem_organization", cells, page_width=2480, page_height=1740)


def autonomy_functional_loop() -> None:
    cells: list[str] = []
    for spec in [
        ("env", "环境与艇体", "水流 / 地形<br>艇体动力学", 65, 60, 290, 180, "teal", "io"),
        ("sense", "感知采集", "运动 / 姿态 / 深度 / 健康", 455, 75, 290, 150, "blue", "process"),
        ("state", "状态理解", "位置 / 速度<br>置信度 / 风险", 845, 75, 290, 150, "green", "process"),
        ("decision", "任务决策", "目标选择 / 模式管理", 1235, 75, 290, 150, "yellow", "process"),
        ("control", "运动控制", "跟踪 / 约束 / 平滑输出", 845, 420, 290, 150, "green", "process"),
        ("safety", "安全治理", "权限与限幅<br>回退与急停", 1235, 390, 340, 210, "red", "decision"),
        ("operator", "人工监督", "授权 / 接管 / 任务调整", 65, 405, 290, 180, "orange", "io"),
        ("evidence", "运行证据", "记录 / 回放 / 评估", 455, 420, 290, 150, "purple", "data"),
    ]:
        add_shape(cells, *spec, extra="fontSize=28;spacingLeft=28;spacingRight=28;")
    for i, (a, b, label) in enumerate(
        [("env", "sense", "观测"), ("sense", "state", "融合"), ("state", "decision", "态势")], 1
    ):
        add_edge(cells, f"l{i}", a, b, label, main=True, extra="fontSize=24;exitX=1;entryX=0;")
    add_edge(
        cells,
        "l4",
        "decision",
        "control",
        "",
        main=True,
        points=[(1380, 330), (990, 330)],
        extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;",
    )
    add_edge(cells, "l5", "control", "env", "控制作用", main=True, points=[(990, 700), (25, 700), (25, 150)], extra="fontSize=24;exitX=0.5;exitY=1;entryX=0;entryY=0.5;")
    add_edge(cells, "l6", "operator", "safety", "授权/接管", main=True, points=[(210, 640), (1405, 640)], extra="fontSize=24;exitX=0.5;exitY=1;entryX=0.5;entryY=1;")
    add_edge(cells, "l7", "safety", "control", "安全边界", main=True, extra="fontSize=24;exitX=0;entryX=1;")
    add_edge(cells, "l8", "state", "safety", "健康与风险", dashed=True, points=[(990, 270), (1405, 270)], extra="fontSize=24;exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "l9", "control", "evidence", "执行记录", dashed=True, extra="fontSize=24;exitX=0;entryX=1;")
    add_edge(cells, "l10", "evidence", "operator", "复盘", dashed=True, extra="fontSize=24;exitX=0;entryX=1;")
    write("auv_system_autonomy_functional_loop", cells, page_width=1610, page_height=750)


def thesis_technical_route() -> None:
    cells: list[str] = []
    stages = [
        ("problem", "任务约束", "弱磁目标 / 近底安全 / 感知退化", 75, "blue", "process"),
        ("observe", "主动形成观测", "声磁协同 / 主动横切", 245, "yellow", "process"),
        ("state", "形成可信状态", "融合定位 / 不确定性 / 可信度", 415, "green", "process"),
        ("action", "采取安全行动", "行为选择 / 约束控制 / 分层保护", 585, "orange", "process"),
        ("evidence", "分层验证", "仿真 / 孪生 / 部署接口", 755, "purple", "process"),
    ]
    for id_, title, detail, y, color, kind in stages:
        add_shape(cells, id_, title, detail, 35, y, 390, 120, color, kind, extra="fontSize=27;")
    for i, (source, target, label) in enumerate(
        [
            ("problem", "observe", "问题 A"),
            ("observe", "state", "问题 B"),
            ("state", "action", "问题 C"),
            ("action", "evidence", "问题 D"),
        ],
        1,
    ):
        add_edge(cells, f"tr{i}", source, target, "", main=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
        add_note(cells, f"tr{i}_label", label, 55, 205 + (i - 1) * 170, 110, 36, 23, True)

    add_lane(cells, "support", "工程支撑与迁移边界", 515, 35, 420, 865, "teal")
    cells[-1] = cells[-1].replace("startSize=38;", "startSize=54;")
    supports = [
        ("s1", "双脑异步架构", "Jetson 决策 / PC104 执行", 100),
        ("s2", "统一数据契约", "时间 / 坐标 / 置信度", 360),
        ("s3", "虚实共享算法", "可替换接口后端", 530),
        ("s4", "证据边界", "成立条件 / 失效范围", 700),
    ]
    for id_, title, detail, y in supports:
        add_shape(cells, id_, title, detail, 35, y, 350, 130 if id_ == "s1" else 100, "blue" if id_ == "s1" else "teal", "module", "support", extra="fontSize=27;")
    add_edge(cells, "support_state", "s2", "state", "接口", dashed=True, extra="exitX=0;entryX=1;fontSize=24;")
    add_edge(cells, "support_action", "s3", "action", "部署", dashed=True, extra="exitX=0;entryX=1;fontSize=24;")
    add_edge(cells, "support_evidence", "s4", "evidence", "边界", dashed=True, extra="exitX=0;entryX=1;fontSize=24;")
    write("auv_thesis_technical_route", cells, page_width=970, page_height=930)


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
    for index, (pid, title, detail, evidence, _, color) in enumerate(stages):
        x = 30 + (index % 3) * 260
        y_shift = (index // 3) * 450
        add_shape(cells, pid, title, detail, x, 85 + y_shift, 220, 90, color, "process")
        add_shape(cells, f"g_{pid}", "准入门", "风险受控", x + 10, 205 + y_shift, 200, 110, color, "gate")
        add_shape(cells, f"e_{pid}", evidence, "指标 / 日志", x, 345 + y_shift, 220, 78, color, "module")
        add_edge(cells, f"gate_{pid}", pid, f"g_{pid}", "", dashed=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
        add_edge(cells, f"evidence_{pid}", f"g_{pid}", f"e_{pid}", "", dashed=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    for i in range(1, 6):
        if i == 3:
            add_edge(cells, "up3", "p3", "p4", "", main=True,
                     points=[(805, 130), (805, 460), (140, 460)],
                     extra="exitX=1;exitY=0.5;entryX=0.5;entryY=0;entryPerimeter=0;")
        else:
            add_edge(cells, f"up{i}", f"p{i}", f"p{i+1}", "", main=True,
                     extra="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    add_note(cells, "goal_note", "能力逐级释放 → 右端为目标，不表示全部阶段已完成", 25, 925, 780, 45, 22, True)
    # 2026-10-23: reduce boxes/text by 20%, retaining the border line width.
    # Its paper width is reduced by the same factor, preserving stroke scale.
    write("auv_system_verification_deployment_ladder", compact_cells(cells, x=.8, y=.8, font=.8), page_width=680, page_height=800)


def dual_brain_async_hardware() -> None:
    cells: list[str] = []
    for spec in [
        ("jetson", "Jetson Orin：非实时感知与决策", 30, 40, 500, 820, "blue"),
        ("pc104", "PC104 / VxWorks：硬实时执行与保护", 900, 40, 500, 820, "teal"),
    ]:
        add_lane(cells, *spec)
        # Hardware platforms are containers, visibly distinct from functions.
        cells[-1] = cells[-1].replace("startSize=38;", "startSize=64;")
        cells[-1] = cells[-1].replace("fillColor=" + PALETTE[spec[-1]][0], "fillColor=#31566F;swimlaneFillColor=#FFFFFF")
        cells[-1] = cells[-1].replace("fontColor=#26323D;", "fontColor=#FFFFFF;")
    add_shape(cells, "gcs", "操作员上位机", "任务配置 / 授权 / 急停", 565, 70, 280, 140, "yellow", "io", extra="fontSize=26;spacingLeft=28;spacingRight=28;")
    add_shape(cells, "bus", "双脑协议接口", "命令下行 $CKTH 72 B<br>状态上行 $AUV 145 B", 565, 265, 300, 190, "gray", "module", extra="fontSize=26;dashed=1;dashPattern=8 5;fontStyle=1;")
    add_shape(cells, "sensors", "航行与健康传感", "IMU、DVL<br>深度、故障字", 565, 520, 280, 150, "green", "io", extra="fontSize=26;spacingLeft=28;spacingRight=28;")
    add_shape(cells, "actuators", "执行机构", "主推 / 舵机", 565, 750, 280, 100, "orange", "io", extra="fontSize=26;")
    for spec in [
        ("j0", "运行环境", "Ubuntu / ROS2", 55, 90, 390, 100, "gray", "io", "jetson"),
        ("j1", "感知与估计", "融合定位（ES-EKF）", 55, 250, 390, 110, "green", "process", "jetson"),
        ("j2", "任务决策", "行为树选择任务", 55, 440, 390, 110, "yellow", "process", "jetson"),
        ("j3", "路径与控制意图", "约束优化控制（UA-MPC）", 55, 630, 390, 110, "purple", "process", "jetson"),
        ("p0", "运行环境", "VxWorks", 55, 90, 390, 100, "gray", "io", "pc104"),
        ("p1", "姿态内环", "硬实时 PID", 55, 250, 390, 110, "green", "process", "pc104"),
        ("p2", "执行器驱动", "电机 / 舵机", 55, 440, 390, 110, "orange", "process", "pc104"),
        ("p3", "本地失效保护", "看门狗 / 防触底", 55, 600, 390, 200, "red", "decision", "pc104"),
    ]:
        add_shape(cells, *spec, extra="fontSize=26;")
    add_edge(cells, "d1", "j1", "j2", "", main=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "d2", "j2", "j3", "", main=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "d3", "p1", "p2", "", main=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "d4", "p2", "p3", "", main=True, extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "d5", "j3", "bus", "", main=True, points=[(545, 725), (545, 400)], extra="exitX=1;exitY=0.5;entryX=0;entryY=0.75;")
    add_edge(cells, "d6", "bus", "p1", "下行", main=True, points=[(880, 320)], extra="fontSize=24;exitX=1;exitY=0.25;entryX=0;entryY=0.25;")
    add_edge(cells, "d7", "p3", "bus", "", dashed=True, points=[(910, 740), (910, 400)], extra="exitX=0;exitY=0.5;entryX=1;entryY=0.75;")
    add_edge(cells, "d8", "bus", "j1", "上行", dashed=True, points=[(515, 312), (515, 345)], label_offset=(-0.35, -15), extra="fontSize=24;exitX=0;exitY=0.2;entryX=1;entryY=0.5;")
    add_edge(cells, "d9", "gcs", "j2", "", main=True, points=[(500, 140), (500, 535)], extra="exitX=0;exitY=0.5;entryX=1;entryY=0.5;")
    add_edge(cells, "d10", "sensors", "p1", "", main=True, points=[(930, 595), (930, 372.5)], extra="exitX=1;exitY=0.5;entryX=0;entryY=0.75;")
    add_edge(cells, "d11", "p2", "actuators", "", main=True, points=[(880, 535), (880, 800)], extra="exitX=0;exitY=0.5;entryX=1;entryY=0.5;")
    write("auv_v2_dual_brain_async_hardware", cells, page_width=1440, page_height=900)


def uncertainty_highway() -> None:
    cells: list[str] = []
    for spec in [
        ("m", "观测质量", "时延 / 信噪比 SNR / 缺测", 30, 30, 470, 190, "orange", "io"),
        ("r", "分源量测噪声", "质量分 → 量测噪声<br>协方差 R<sub>s</sub>", 750, 30, 500, 190, "purple", "process"),
        ("e", "状态与协方差", "ES-EKF：状态估计 x<br>与估计协方差 P", 30, 380, 470, 190, "green", "process"),
        ("u", "分源置信度", "协方差 P + 源健康<br>→ 分源置信度 c<sub>s</sub>", 750, 380, 500, 190, "purple", "process"),
        ("bt", "行为路由", "精准巡检 / 搜索回落", 0, 800, 530, 300, "yellow", "decision"),
        ("ctrl", "控制调制", "跟踪权重 / 控制代价<br>速度", 750, 820, 500, 240, "blue", "process"),
    ]:
        add_shape(cells, *spec, extra="fontSize=26;")
    add_edge(cells, "u1", "m", "r", "质量分", main=True, extra="fontSize=26;exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    add_edge(cells, "u2", "r", "e", "量测噪声协方差 R_s", main=True, points=[(1000, 300), (265, 300)], extra="fontSize=26;exitX=0.5;exitY=1;entryX=0.5;entryY=0;entryPerimeter=0;")
    add_edge(cells, "u3", "e", "u", "协方差 P / 源状态", main=True, extra="fontSize=26;exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    add_edge(cells, "u4", "u", "bt", "阈值与迟滞", main=True, points=[(1000, 720), (265, 720)], extra="fontSize=26;exitX=0.5;exitY=1;entryX=0.5;entryY=0;entryPerimeter=0;")
    add_edge(cells, "u5", "u", "ctrl", "连续参数调度", main=True, extra="fontSize=26;exitX=0.8;exitY=1;entryX=0.8;entryY=0;entryPerimeter=0;")
    # Keep text size; tighten vertical box dimensions and gaps conservatively.
    write("auv_v2_uncertainty_highway", compact_cells(cells, y=.85), page_width=1300, page_height=969)


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
    source = THESIS_OUT / "auv_v2_five_layer_functional_architecture.drawio"
    split_drawio(source)
    # Both paper panels are 20% smaller; compensate border strokes so their
    # final printed thickness remains unchanged. Native graph/text stay intact.
    tree = ET.parse(source)
    for cell in tree.iter('mxCell'):
        style = []
        for part in cell.get('style', '').split(';'):
            key, sep, value = part.partition('=')
            if sep and key == 'strokeWidth':
                value = f'{float(value)/.8:g}'
            style.append(key + sep + value)
        if 'style' in cell.attrib:
            cell.set('style', ';'.join(style))
    tree.write(source, encoding='utf-8', xml_declaration=True)


def behavior_tree_illustration() -> None:
    cells: list[str] = []
    add_lane(cells, "priority_lane", "根节点优先级与调试级联", 30, 30, 1320, 620, "purple")
    cells[-1] = cells[-1].replace("startSize=38;", "startSize=54;")
    add_lane(cells, "mission_lane", "主任务与置信度路由", 30, 690, 1320, 900, "yellow")
    cells[-1] = cells[-1].replace("startSize=38;", "startSize=54;")

    for spec in [
        ("root", "根选择器", "memory=False；逐 tick 重查", 470, 80, 380, 110, "purple", "bt_control", "priority_lane"),
        ("emergency_seq", "紧急顺序", "优先级 1", 55, 255, 300, 100, "red", "bt_control", "priority_lane"),
        ("standby", "待命检查", "未授权 / 链路不可用", 505, 230, 310, 150, "gray", "decision", "priority_lane"),
        ("debug_selector", "调试级联", "优先级 3", 965, 255, 300, 100, "yellow", "bt_control", "priority_lane"),
        ("emergency_condition", "紧急条件", "漏水 / 低电 / 穿底", 25, 420, 280, 160, "red", "decision", "priority_lane"),
        ("emergency_surface", "紧急上浮", "", 330, 445, 180, 110, "red", "process", "priority_lane"),
        ("idle_goal", "IDLE 目标", "安全悬停", 555, 445, 210, 110, "gray", "state", "priority_lane"),
        ("hold_seq", "保持", "调试等级 1", 785, 445, 165, 110, "blue", "bt_control", "priority_lane"),
        ("path_seq", "解析轨迹", "调试等级 2", 965, 445, 165, 110, "teal", "bt_control", "priority_lane"),
        ("main_entry", "主任务", "调试等级 0 / 3", 1145, 445, 165, 110, "green", "bt_control", "priority_lane"),
    ]:
        add_shape(cells, *spec, extra="fontSize=20;")

    add_edge(cells, "bt1", "root", "emergency_seq", "1", main=True, safe=True)
    add_edge(cells, "bt2", "root", "standby", "2", main=True)
    add_edge(cells, "bt3", "root", "debug_selector", "3", main=True)
    add_edge(cells, "bt4", "emergency_seq", "emergency_condition", "", safe=True)
    add_edge(cells, "bt5", "emergency_seq", "emergency_surface", "", safe=True)
    add_edge(cells, "bt6", "standby", "idle_goal", "")
    add_edge(cells, "bt7", "debug_selector", "hold_seq", "1")
    add_edge(cells, "bt8", "debug_selector", "path_seq", "2")
    add_edge(cells, "bt9", "debug_selector", "main_entry", "0 / 3", main=True)

    for spec in [
        ("main_seq", "主任务顺序", "Sequence；memory=False", 470, 80, 380, 110, "green", "bt_control", "mission_lane"),
        ("dive", "定深下潜", "目标深度 4 m", 80, 280, 250, 110, "blue", "process", "mission_lane"),
        ("seabed", "海底安全限制", "穿底约束；降速 0.5", 480, 260, 320, 150, "red", "gate", "mission_lane"),
        ("route", "路线路由", "失败回落搜索", 970, 280, 300, 110, "yellow", "bt_control", "mission_lane"),
        ("precise", "精准巡检顺序", "优先分支", 530, 480, 320, 110, "green", "bt_control", "mission_lane"),
        ("zigzag", "之字形搜索", "低置信度分支", 1040, 500, 230, 110, "orange", "process", "mission_lane"),
        ("confidence", "置信度门控", "定位可用且通过门限", 330, 680, 340, 170, "teal", "decision", "mission_lane"),
        ("tracking", "异常限速", "0.4 × 并行跟踪", 800, 710, 320, 110, "green", "process", "mission_lane"),
    ]:
        add_shape(cells, *spec, extra="fontSize=20;")

    add_edge(cells, "bt10", "main_entry", "main_seq", "", main=True, dashed=True, points=[(1380, 530), (1380, 670), (450, 670), (450, 825)], extra="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    add_edge(cells, "bt11", "main_seq", "dive", "", main=True, points=[(595, 920), (235, 920)], extra="exitX=0.25;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "bt12", "main_seq", "seabed", "", main=True, extra="exitX=0.6;exitY=1;entryX=0.9333333333;entryY=0.5;entryPerimeter=0;")
    add_edge(cells, "bt13", "seabed", "route", "", main=True, safe=True, extra="exitX=0.5;exitY=1;exitPerimeter=0;entryX=0;entryY=0.5;")
    add_edge(cells, "bt14", "route", "precise", "", main=True, points=[(1075, 1140), (930, 1140), (930, 1225)], extra="exitX=0.25;exitY=1;entryX=1;entryY=0.5;")
    add_edge(cells, "bt15", "route", "zigzag", "回落", extra="exitX=0.6;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "bt16", "precise", "confidence", "", points=[(672, 1330), (530, 1330)], extra="exitX=0.35;exitY=1;entryX=0.5;entryY=0;")
    add_edge(cells, "bt17", "precise", "tracking", "", main=True, points=[(800, 1345), (990, 1345)], extra="exitX=0.75;exitY=1;entryX=0.5;entryY=0;")
    write("auv_v2_behavior_tree_illustration", compact_final_lane(cells, "mission_lane", .85), page_width=1420, page_height=1495)


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
    for spec in [("trigger_lane", "触发条件", 30, 25, 400, 1190, "red"),
                 ("layer_lane", "处置层级", 500, 25, 400, 1190, "purple"),
                 ("action_lane", "目标动作", 970, 25, 400, 1190, "teal")]:
        add_lane(cells, *spec)
        cells[-1] = cells[-1].replace("startSize=38;", "startSize=54;")
    for spec in [
        ("g1", "链路或授权异常", "命令陈旧 / 授权撤销", 55, 120, 310, 140, "red", "io", "trigger_lane"),
        ("g2", "定位置信不足", "门控未通过", 55, 400, 310, 140, "orange", "io", "trigger_lane"),
        ("g3", "独立紧急条件", "漏水 / 低电 / 穿底", 55, 680, 310, 140, "red", "io", "trigger_lane"),
        ("g4", "人工急停", "地面站 ESTOP", 55, 960, 310, 140, "red", "io", "trigger_lane"),
        ("arb", "ROS2 权限仲裁", "新鲜度 / 授权", 20, 70, 360, 240, "purple", "decision", "layer_lane"),
        ("task", "行为树任务路由", "置信门控逐 tick 判定", 20, 350, 360, 240, "yellow", "decision", "layer_lane"),
        ("emergency", "行为树 / PC104 保护", "故障字抢占 / 本地覆盖", 20, 630, 360, 240, "red", "decision", "layer_lane"),
        ("estop", "ROS2 / PC104 急停链", "锁存并回零", 20, 910, 360, 240, "red", "decision", "layer_lane"),
        ("zero", "回零与 REMOTE 锁定", "停止释放自主指令", 45, 130, 310, 120, "gray", "state", "action_lane"),
        ("search", "搜索回落", "低置信度不触发上浮", 45, 410, 310, 120, "yellow", "state", "action_lane"),
        ("surface", "紧急上浮 / 防触底", "独立安全条件", 45, 690, 310, 120, "orange", "state", "action_lane"),
        ("kill", "急停截止", "锁存零执行量", 45, 955, 310, 150, "red", "terminal", "action_lane"),
    ]:
        add_shape(cells, *spec)
    rows = [
        ("g1", "arb", "zero", "新鲜度 /<br>授权", "回零"),
        ("g2", "task", "search", "置信门控", "任务降级"),
        ("g3", "emergency", "surface", "安全字 /<br>本地检测", "安全抢占"),
        ("g4", "estop", "kill", "ESTOP", "锁存"),
    ]
    for i, (trigger, layer, action, in_label, out_label) in enumerate(rows, 1):
        add_edge(cells, f"eg{i}a", trigger, layer, in_label, safe=i in {3, 4}, main=i in {1, 2}, extra="exitX=1;entryX=0;")
        add_edge(cells, f"eg{i}b", layer, action, out_label, safe=i in {3, 4}, main=i in {1, 2}, extra="exitX=1;entryX=0;")
    write("auv_v2_emergency_transition", cells, page_width=1400, page_height=1250)


def mission_lifecycle_flow() -> None:
    cells: list[str] = []
    for spec in [("op", "操作员 / 地面站", 30, 25, 350, 1410, "orange"),
                 ("arb", "安全守卫 / 权限仲裁", 440, 25, 350, 1410, "red"),
                 ("brain", "决策与控制", 850, 25, 350, 1410, "blue"),
                 ("exec", "执行与反馈", 1260, 25, 350, 1410, "teal")]:
        add_lane(cells, *spec)
        cells[-1] = cells[-1].replace("startSize=38;", "startSize=54;")
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
    heights = {"io": 160, "gate": 170, "decision": 230, "process": 130, "data": 145, "terminal": 160}
    for nodes, parent in [(op_nodes, "op"), (ar_nodes, "arb"), (br_nodes, "brain"), (ex_nodes, "exec")]:
        for index, (id_, title, detail, kind, color) in enumerate(nodes):
            height = heights[kind]
            center = 190 + index * 260
            width = 300 if kind == "decision" else 280
            size = 22 if kind == "decision" else 24
            add_shape(cells, id_, title, detail, (350 - width) / 2, center - height / 2, width, height, color, kind, parent,
                      extra=f"fontSize={size};spacingLeft=20;spacingRight=20;")
    for prefix in ["op", "ar", "br"]:
        for i in range(1, 5):
            source, target = f"{prefix}{i}", f"{prefix}{i+1}"
            gates = {"op2", "ar3", "ar5"}
            # North-oriented draw.io trapezoids rotate normalized ports. The
            # sloped top/bottom midpoints are inset 10 u from their bbox.
            source_port = "exitX=0.0588235294;exitY=0.5;exitPerimeter=0;" if source in gates else "exitX=0.5;exitY=1;"
            target_port = "entryX=0.9411764706;entryY=0.5;entryPerimeter=0;" if target in gates else "entryX=0.5;entryY=0;"
            add_edge(cells, f"{prefix}_flow_{i}", source, target, "", main=i in {1, 2, 4}, extra=source_port + target_port)
    add_edge(cells, "ml1", "op2", "ar2", "", main=True, extra="exitX=0.5;exitY=1;exitPerimeter=0;entryX=0;entryY=0.5;")
    add_edge(cells, "ml2", "ar3", "br2", "", main=True, points=[(820, 735), (820, 475)], extra="exitX=0.5;exitY=1;exitPerimeter=0;entryX=0;entryY=0.5;")
    add_edge(cells, "ml3", "br3", "ex2", "", main=True, points=[(1230, 735), (1230, 475)], extra="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    add_edge(cells, "ml4", "ex1", "br1", "", main=True, extra="exitX=0;exitY=0.5;entryX=1;entryY=0.5;")
    add_edge(cells, "ml5", "ex3", "br4", "", dashed=True, points=[(1245, 735), (1245, 975.5)], extra="exitX=0;exitY=0.5;entryX=1;entryY=0.35;")
    add_edge(cells, "ml6", "ex4", "br4", "", safe=True, extra="exitX=0;exitY=0.5;entryX=1;entryY=0.65;")
    add_edge(cells, "ml7", "br4", "ar4", "", safe=True, extra="exitX=0;exitY=0.5;entryX=1;entryY=0.5;")
    add_edge(cells, "ml8", "ar4", "op4", "", dashed=True, extra="exitX=0;exitY=0.5;entryX=1;entryY=0.5;")
    add_edge(cells, "ml9", "op5", "ar5", "", main=True, extra="exitX=1;exitY=0.5;entryX=0.5;entryY=0;entryPerimeter=0;")
    add_edge(cells, "ml10", "ar5", "br5", "", main=True, extra="exitX=0.5;exitY=1;exitPerimeter=0;entryX=0;entryY=0.5;")
    add_edge(cells, "ml11", "br5", "ex5", "", main=True, extra="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    write("auv_v2_mission_lifecycle_flow", cells, page_width=1650, page_height=1470)


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
