"""Generate low-saturation draw.io architecture diagrams for AUV docs."""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape


OUT = Path(__file__).resolve().parent
VERSION = "30.0.4"

FONT = "fontFamily=Noto Serif CJK SC,Times New Roman;fontSize=14;fontColor=#26323D;"
TITLE_FONT = "fontFamily=Noto Serif CJK SC,Times New Roman;fontSize=24;fontStyle=1;fontColor=#1E2732;"
SUB_FONT = "fontFamily=Noto Serif CJK SC,Times New Roman;fontSize=13;fontColor=#43525F;"
EDGE = (
    "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;"
    "html=1;strokeColor=#5F7690;fontColor=#3B4A57;fontSize=12;strokeWidth=2;"
    "labelBackgroundColor=#F6F7F8;labelBorderColor=none;"
    "endArrow=block;endFill=1;endSize=8;"
)
EDGE_DASH = EDGE + "dashed=1;dashPattern=6 4;"
EDGE_BOLD = (
    "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;"
    "html=1;strokeColor=#2F4A63;fontColor=#1E2732;fontSize=13;fontStyle=1;strokeWidth=3;"
    "labelBackgroundColor=#F6F7F8;labelBorderColor=none;"
    "endArrow=block;endFill=1;endSize=10;"
)

PALETTE = {
    "blue": ("#EAF2F8", "#8AA9C4"),
    "green": ("#EEF6EF", "#8DBA98"),
    "yellow": ("#FFF7E8", "#D8B46A"),
    "orange": ("#FBEFE5", "#D4A17B"),
    "purple": ("#F2EDF7", "#A996C0"),
    "red": ("#F8EEEE", "#C68C8C"),
    "gray": ("#F6F7F8", "#9AA7B2"),
    "teal": ("#EAF6F5", "#80B4AF"),
}


def value(text: str) -> str:
    return escape(text, {'"': "&quot;"}).replace("\n", "&#xa;")


def box_style(color: str = "blue", extra: str = "") -> str:
    fill, stroke = PALETTE[color]
    return (
        "rounded=1;whiteSpace=wrap;html=1;arcSize=12;"
        f"fillColor={fill};strokeColor={stroke};strokeWidth=2;spacing=8;shadow=0;"
        f"{FONT}{extra}"
    )


def lane_style(color: str = "gray") -> str:
    fill, stroke = PALETTE[color]
    return (
        "swimlane;whiteSpace=wrap;html=1;startSize=36;rounded=1;arcSize=8;"
        f"fillColor={fill};strokeColor={stroke};strokeWidth=2;"
        f"collapsible=0;childLayout=none;{FONT}fontStyle=1;fontSize=15;"
    )


def title_style() -> str:
    return (
        "text;html=1;strokeColor=none;fillColor=none;align=center;"
        f"verticalAlign=middle;whiteSpace=wrap;rounded=0;{TITLE_FONT}"
    )


def note_style() -> str:
    return (
        "text;html=1;strokeColor=none;fillColor=none;align=left;"
        f"verticalAlign=top;whiteSpace=wrap;rounded=0;{SUB_FONT}"
    )


def rect(cells, id_, label, x, y, w, h, color="blue", parent="1", extra=""):
    cells.append(
        f'<mxCell id="{id_}" value="{value(label)}" style="{box_style(color, extra)}" '
        f'vertex="1" parent="{parent}"><mxGeometry x="{x}" y="{y}" width="{w}" '
        f'height="{h}" as="geometry" /></mxCell>'
    )


def diamond(cells, id_, label, x, y, w, h, color="yellow", parent="1", extra=""):
    fill, stroke = PALETTE[color]
    style = (
        f"rhombus;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};"
        f"strokeWidth=2;{FONT}{extra}"
    )
    cells.append(
        f'<mxCell id="{id_}" value="{value(label)}" style="{style}" vertex="1" '
        f'parent="{parent}"><mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" '
        f'as="geometry" /></mxCell>'
    )


def ellipse(cells, id_, label, x, y, w, h, color="blue", parent="1", extra=""):
    fill, stroke = PALETTE[color]
    style = (
        f"ellipse;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};"
        f"strokeWidth=2;{FONT}{extra}"
    )
    cells.append(
        f'<mxCell id="{id_}" value="{value(label)}" style="{style}" vertex="1" '
        f'parent="{parent}"><mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" '
        f'as="geometry" /></mxCell>'
    )


def lane(cells, id_, label, x, y, w, h, color="gray"):
    cells.append(
        f'<mxCell id="{id_}" value="{value(label)}" style="{lane_style(color)}" '
        f'vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" '
        f'height="{h}" as="geometry" /></mxCell>'
    )


def text(cells, id_, label, x, y, w, h, title=False):
    style = title_style() if title else note_style()
    cells.append(
        f'<mxCell id="{id_}" value="{value(label)}" style="{style}" vertex="1" '
        f'parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" '
        f'as="geometry" /></mxCell>'
    )


def edge(cells, id_, source, target, label="", dashed=False, points=None, extra="", bold=False):
    base = EDGE_BOLD if bold else (EDGE_DASH if dashed else EDGE)
    style = base + extra
    if points:
        pts = "".join(f'<mxPoint x="{x}" y="{y}" />' for x, y in points)
        geometry = f'<mxGeometry relative="1" as="geometry"><Array as="points">{pts}</Array></mxGeometry>'
    else:
        geometry = '<mxGeometry relative="1" as="geometry" />'
    cells.append(
        f'<mxCell id="{id_}" value="{value(label)}" style="{style}" edge="1" '
        f'parent="{"1"}" source="{source}" target="{target}">{geometry}</mxCell>'
    )


def write(name: str, cells, page_width=1440, page_height=940) -> None:
    body = "\n        ".join(['<mxCell id="0" />', '<mxCell id="1" parent="0" />'] + cells)
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<mxfile host="drawio" version="{VERSION}">
  <diagram name="{value(name)}">
    <mxGraphModel dx="1200" dy="820" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{page_width}" pageHeight="{page_height}" math="0" shadow="0">
      <root>
        {body}
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
'''
    (OUT / f"{name}.drawio").write_text(xml, encoding="utf-8")


def code_layer_architecture():
    cells = []
    text(cells, "t1", "AUV 软件系统五层架构", 390, 20, 620, 40, True)
    text(cells, "s1", "面向 docs/internals/01_architecture 与 thesis 总览：从运行入口到共享协议的代码分层", 390, 62, 660, 34)
    for spec in [
        ("l_app", "应用层 apps/", 80, 120, 1240, 110, "blue"),
        ("l_if", "接口层 interfaces/", 80, 250, 1240, 120, "teal"),
        ("l_beh", "行为层 behavior/", 80, 390, 1240, 110, "yellow"),
        ("l_alg", "算法层 algorithm/", 80, 520, 1240, 120, "green"),
        ("l_common", "协议/基础层 common/", 80, 660, 1240, 120, "purple"),
    ]:
        lane(cells, *spec)
    for spec in [
        ("app1", "main.py\n独立仿真入口", 50, 46, 190, 46, "blue", "l_app"),
        ("app2", "main_loop.py\n单进程闭环", 285, 46, 190, 46, "blue", "l_app"),
        ("app3", "run_zenoh_bridge.py\n桥接运行入口", 520, 46, 210, 46, "blue", "l_app"),
        ("app4", "scripts/start_experiment.sh\n实验编排入口", 785, 46, 260, 46, "blue", "l_app"),
        ("if1", "sim_wrapper / pvs_sim_wrapper\nHoloOcean / PVS 后端", 50, 48, 255, 50, "teal", "l_if"),
        ("if2", "frame_transform.py\nUE4 ↔ NED 坐标统一", 345, 48, 250, 50, "teal", "l_if"),
        ("if3", "zenoh_bridge / protocol_udp\n跨进程通信桥接", 635, 48, 250, 50, "teal", "l_if"),
        ("if4", "mock_amd_server\n协议级硬件替身", 925, 48, 230, 50, "teal", "l_if"),
        ("beh1", "command_guard\n命令合法性过滤", 170, 45, 230, 46, "yellow", "l_beh"),
        ("beh2", "safety_monitor\n限幅 / 急停 / 保护", 505, 45, 230, 46, "yellow", "l_beh"),
        ("beh3", "state_machine\n任务运行状态", 840, 45, 230, 46, "yellow", "l_beh"),
        ("alg1", "guidance.py\nLOS 导引", 70, 50, 190, 46, "green", "l_alg"),
        ("alg2", "auv_pid_controller.py\n级联 PID", 310, 50, 220, 46, "green", "l_alg"),
        ("alg3", "auv_mpc_controller.py\nMPC / UA-MPC", 580, 50, 220, 46, "green", "l_alg"),
        ("alg4", "es_ekf.py\n状态估计", 850, 50, 190, 46, "green", "l_alg"),
        ("alg5", "trajectory_generator.py\n轨迹生成", 1090, 50, 120, 46, "green", "l_alg"),
        ("co1", "protocol.py\nTopic / Payload 契约", 125, 50, 240, 46, "purple", "l_common"),
        ("co2", "enums.py\n模式 / 指令 / 状态", 445, 50, 230, 46, "purple", "l_common"),
        ("co3", "physics.py\n物理限幅 / 饱和日志", 755, 50, 240, 46, "purple", "l_common"),
    ]:
        rect(cells, *spec)
    edge(cells, "e1", "app2", "if1", "组装后端", extra="exitX=0.5;exitY=1;entryX=0.25;entryY=0;", bold=True)
    edge(cells, "e2", "app3", "if3", "启动桥接", extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;", bold=True)
    edge(
        cells,
        "e3",
        "if2",
        "co3",
        "",
        points=[(470, 700), (875, 700)],
        extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;",
    )
    edge(
        cells,
        "e4",
        "if3",
        "co1",
        "",
        points=[(760, 490), (245, 490)],
        extra="exitX=0.35;exitY=1;entryX=0.5;entryY=0;",
        bold=True,
    )
    edge(
        cells,
        "e5",
        "beh2",
        "alg2",
        "",
        points=[(590, 510), (310, 510)],
        extra="exitX=0.35;exitY=1;entryX=0;entryY=0.5;",
    )
    edge(
        cells,
        "e6",
        "alg2",
        "co3",
        "",
        points=[(500, 640), (875, 640)],
        extra="exitX=0.5;exitY=1;entryX=0.5;entryY=0;",
    )
    write("auv_code_layer_architecture", cells)


def runtime_dataflow():
    cells = []
    text(cells, "t1", "AUV 双运行路径数据流", 360, 20, 680, 40, True)
    text(cells, "s1", "独立仿真闭环用于快速算法验证；桥接通信闭环用于 ROS2 集成和真机迁移前验证", 350, 62, 720, 34)
    lane(cells, "standalone", "路径一：独立仿真闭环（单进程）", 70, 120, 1260, 270, "green")
    lane(cells, "bridged", "路径二：桥接通信闭环（仿真/协议/ROS2 分进程）", 70, 450, 1260, 330, "blue")
    for spec in [
        ("st1", "TrajectoryGenerator\n目标路点", 60, 70, 180, 60, "green", "standalone"),
        ("st2", "guidance LOS\n期望航向/深度", 270, 70, 180, 60, "green", "standalone"),
        ("st3", "PIDController\n舵角/推力", 500, 70, 180, 60, "green", "standalone"),
        ("st4", "safety_monitor\n限幅保护", 725, 70, 180, 60, "yellow", "standalone"),
        ("st5", "sim_wrapper\nPVS/HoloOcean step", 950, 70, 180, 60, "teal", "standalone"),
        ("st6", "传感器状态\n位置/姿态/速度", 520, 175, 220, 55, "gray", "standalone"),
        ("br1", "PVS / HoloOcean\n仿真或 Mock AMD", 50, 75, 190, 58, "teal", "bridged"),
        ("br2", "frame_transform\nholoocean_physics_bridge", 270, 75, 205, 58, "teal", "bridged"),
        ("br3", "Zenoh JSON / Protocol UDP\n多 Topic / 二进制帧", 505, 75, 190, 58, "purple", "bridged"),
        ("br4", "auv_bridge\n协议 ↔ ROS2 Topic", 750, 75, 190, 58, "blue", "bridged"),
        ("br5", "localization\nES-EKF 融合状态", 985, 75, 190, 58, "green", "bridged"),
        ("br6", "decision\n行为树 Setpoint", 985, 190, 190, 58, "yellow", "bridged"),
        ("br7", "controller\nPID / MPC / Terrain", 750, 190, 190, 58, "green", "bridged"),
        ("br8", "cmd_vel / arbiter_cmd\n下行控制命令", 505, 190, 190, 58, "orange", "bridged"),
    ]:
        rect(cells, *spec)
    for spec in [
        ("se1", "st1", "st2", "ref", False, None, "exitX=1;entryX=0;", True),
        ("se2", "st2", "st3", "target", False, None, "exitX=1;entryX=0;", True),
        ("se3", "st3", "st4", "cmd[5]", False, None, "exitX=1;entryX=0;", True),
        ("se4", "st4", "st5", "safe cmd", False, None, "exitX=1;entryX=0;", True),
        ("se5", "st5", "st6", "readback", False, None, "exitX=0.5;exitY=1;entryX=1;entryY=0.5;", False),
        ("se6", "st6", "st2", "闭环反馈", True, [(360, 340), (360, 210)], "exitX=0;entryX=0.5;entryY=1;", False),
        ("be1", "br1", "br2", "raw state", False, None, "exitX=1;entryX=0;", True),
        ("be2", "br2", "br3", "NED + sensors", False, None, "exitX=1;entryX=0;", True),
        ("be3", "br3", "br4", "rt/auv/sensors/*", False, None, "exitX=1;entryX=0;", True),
        ("be4", "br4", "br5", "/auv/sensors/*", False, None, "exitX=1;entryX=0;", True),
        ("be5", "br5", "br6", "state + health", False, None, "exitX=0.65;exitY=1;entryX=0.65;entryY=0;", False),
        ("be6", "br6", "br7", "/auv/control/setpoint", False, None, "exitX=0;entryX=1;", True),
        ("be7", "br5", "br7", "/auv/state/filtered", False, None, "exitX=0.35;exitY=1;entryX=0.65;entryY=0;", False),
        ("be8", "br7", "br8", "/cmd_vel / mpc_cmd", False, None, "exitX=0;entryX=1;", True),
        ("be9", "br8", "br3", "encode command", False, None, "exitX=0.5;exitY=0;entryX=0.5;entryY=1;", False),
        ("be10", "br3", "br1", "actuator command", True, [(600, 750), (200, 750), (200, 555)], "exitX=0.15;exitY=1;entryX=0.5;entryY=1;", False),
    ]:
        edge(cells, *spec)
    write("auv_runtime_dataflow", cells)


def ros2_node_topology():
    cells = []
    text(cells, "t1", "ROS2 决策控制栈节点拓扑", 350, 20, 700, 40, True)
    text(cells, "s1", "对应 docs/internals/06_ros2_stack：Bridge → Localization → Controller，并由 Decision 产生 setpoint，Viz/Console 负责观测", 250, 62, 900, 34)
    lane(cells, "external", "外部系统 / 仿真 / 上位机", 70, 120, 1260, 120, "gray")
    lane(cells, "ros", "brain_linux ROS2 Humble 工作区", 70, 285, 1260, 330, "blue")
    lane(cells, "obs", "可视化与离线证据", 70, 660, 1260, 110, "purple")
    for spec in [
        ("ex1", "sim_holoocean / PVS\n传感器与执行器", 80, 45, 260, 52, "teal", "external"),
        ("ex2", "PySide6 Console\n遥控 / 授权 / ESTOP", 500, 45, 260, 52, "orange", "external"),
        ("ex3", "Protocol UDP / Zenoh\n跨进程链路", 920, 45, 260, 52, "purple", "external"),
        ("n1", "auv_bridge\nZenoh/UDP ↔ ROS2", 70, 75, 210, 60, "blue", "ros"),
        ("n2", "auv_localization\nES-EKF", 350, 75, 200, 60, "green", "ros"),
        ("n3", "auv_controller\nPID / MPC", 630, 75, 200, 60, "green", "ros"),
        ("n4", "auv_decision_ros\nBehavior Tree", 910, 75, 220, 60, "yellow", "ros"),
        ("n5", "auv_viz_bridge\nFoxglove / Console Stream", 350, 210, 260, 58, "purple", "ros"),
        ("n6", "auv_interfaces\nSetpoint / MpcCmd / Status", 680, 210, 300, 58, "gray", "ros"),
        ("o1", "Foxglove\nws://localhost:8765", 210, 35, 250, 48, "purple", "obs"),
        ("o2", "rosbag / MCAP\n实验黑匣子", 585, 35, 250, 48, "purple", "obs"),
        ("o3", "tools/analyze_bag.py\n离线图表与 KPI", 960, 35, 250, 48, "purple", "obs"),
    ]:
        rect(cells, *spec)
    for spec in [
        ("r1", "ex1", "ex3", "", False, [(380, 115), (920, 115)], "exitX=1;exitY=1;entryX=0;entryY=1;", True),
        ("r2", "ex2", "ex3", "manual / auth / estop", False, None, "exitX=1;entryX=0;", False),
        ("r3", "ex3", "n1", "/auv/sensors/*", False, None, "exitX=0.5;exitY=1;entryX=0.5;entryY=0;", True),
        ("r4", "n1", "n2", "/auv/sensors/*", False, None, "exitX=1;entryX=0;", True),
        ("r5", "n2", "n3", "/auv/state/filtered", False, None, "exitX=1;entryX=0;", True),
        ("r6", "n2", "n4", "state + health", False, None, "exitX=0.8;exitY=1;entryX=0.35;entryY=0;", False),
        ("r7", "n4", "n3", "/auv/control/setpoint", False, None, "exitX=0;entryX=1;", True),
        ("r8", "n3", "n1", "/cmd_vel / mpc_cmd", False, [(620, 425), (175, 425)], "exitX=0;exitY=1;entryX=0.5;entryY=1;", True),
        ("r9", "n1", "ex3", "encoded control", True, [(50, 260)], "exitX=0;exitY=0.5;entryX=0.05;entryY=1;", False),
        ("r10", "n2", "n5", "state/status/bt", False, None, "exitX=0.5;exitY=1;entryX=0.4;entryY=0;", False),
        ("r11", "n4", "n5", "bt_status", False, None, "exitX=0.3;exitY=1;entryX=0.8;entryY=0;", False),
        ("r12", "n5", "o1", "live view", False, None, "exitX=0.3;exitY=1;entryX=0.5;entryY=0;", False),
        ("r13", "n1", "o2", "record topics", True, [(175, 640)], "exitX=0.5;exitY=1;entryX=0.5;entryY=0;", False),
        ("r14", "o2", "o3", "offline analysis", False, None, "exitX=1;entryX=0;", False),
    ]:
        edge(cells, *spec)
    write("auv_ros2_node_topology", cells)


def safety_arbiter_deployment():
    cells = []
    text(cells, "t1", "真机部署安全链路与仲裁器", 350, 20, 700, 40, True)
    text(cells, "s1", "对应 docs/internals/07_arbiter 与 docs/real_deployment：控制权唯一、守卫检查、被动影子、急停回退", 280, 62, 850, 34)
    lane(cells, "pc", "地面站 PC", 70, 120, 300, 540, "orange")
    lane(cells, "jetson", "Jetson / brain_linux", 430, 120, 520, 540, "blue")
    lane(cells, "amd", "AMD PC104 / 执行器", 1010, 120, 320, 540, "teal")
    for spec in [
        ("pc1", "PySide6 Console\nMANUAL / AUTONOMY / ESTOP", 55, 60, 210, 65, "orange", "pc"),
        ("pc2", "通信新鲜度\nuplink age / watchdog", 55, 175, 210, 58, "yellow", "pc"),
        ("pc3", "操作员确认\nreal 需显式确认", 55, 300, 210, 58, "red", "pc"),
        ("j1", "protocol_udp_bridge\n上/下行协议编解码", 50, 60, 220, 58, "blue", "jetson"),
        ("j2", "AutonomyGuard\n漏水/电压/置信度/时延/磁盘", 50, 165, 220, 74, "red", "jetson"),
        ("j3", "Arbiter\nREMOTE ↔ AUTONOMOUS", 50, 300, 220, 62, "purple", "jetson"),
        ("j4", "Controller\nPID / MPC / Terrain", 310, 165, 160, 58, "green", "jetson"),
        ("j5", "Decision BT\n任务目标 / Setpoint", 310, 60, 160, 58, "yellow", "jetson"),
        ("j6", "passive_mode\n影子导航只记录不执行", 310, 300, 160, 62, "gray", "jetson"),
        ("j7", "Safety fallback\n零推力 / 锁回 REMOTE", 170, 420, 200, 58, "red", "jetson"),
        ("a1", "AMD 上行\n传感器/状态/健康", 55, 60, 210, 58, "teal", "amd"),
        ("a2", "5 路控制输出\n4 舵 + 推力", 55, 185, 210, 58, "teal", "amd"),
        ("a3", "执行器极性/死区\nS2 静态验证", 55, 310, 210, 58, "yellow", "amd"),
    ]:
        rect(cells, *spec)
    for spec in [
        ("sa1", "pc1", "j1", "manual cmd / auth byte", False, None, "exitX=1;entryX=0;", True),
        ("sa2", "pc2", "j2", "freshness check", False, None, "exitX=1;entryX=0;", False),
        ("sa3", "pc3", "j3", "release authority", True, None, "exitX=1;entryX=0;", False),
        ("sa4", "a1", "j1", "上行遥测", False, [(1170, 165), (700, 165)], "exitX=0.5;exitY=0;entryX=1;entryY=0;", True),
        ("sa5", "j1", "j2", "request AUTONOMY", False, None, "exitX=0.5;exitY=1;entryX=0.5;entryY=0;", True),
        ("sa6", "j2", "j3", "guard pass / deny", False, None, "exitX=0.5;exitY=1;entryX=0.5;entryY=0;", True),
        ("sa7", "j5", "j4", "setpoint", False, None, "exitX=0.5;exitY=1;entryX=0.5;entryY=0;", False),
        ("sa8", "j4", "j3", "", False, None, "exitX=0;entryX=1;", False),
        ("sa9", "j3", "a2", "selected command", False, [(955, 500)], "exitX=1;exitY=0.5;entryX=0;entryY=0.5;", True),
        ("sa10", "j3", "j7", "timeout / ESTOP", False, None, "exitX=0.5;exitY=1;entryX=0.35;entryY=0;", False),
        ("sa11", "j7", "a2", "zero thrust", True, [(920, 585), (1115, 585)], "exitX=1;exitY=0.5;entryX=0.5;entryY=1;", False),
        ("sa12", "j6", "j3", "shadow only", True, None, "exitX=0;entryX=1;", False),
        ("sa13", "a3", "a2", "polarity accepted", False, None, "exitX=0.5;exitY=0;entryX=0.5;entryY=1;", False),
    ]:
        edge(cells, *spec)
    write("auv_safety_arbiter_deployment", cells)


def system_capability_map():
    cells = []
    text(cells, "t1", "AUV 研发平台总体能力地图", 350, 20, 700, 40, True)
    text(cells, "s1", "宏观视角：围绕自主水下任务，组织仿真、自治、上位机、观测、实验与真机部署能力", 330, 62, 760, 34)
    rect(cells, "core", "自主水下任务平台\n任务执行 / 安全控制 / 数据闭环", 550, 365, 300, 90, "blue")
    rect(cells, "sim", "仿真与环境子系统\n场景构建 / 传感器生成 / 执行器响应", 110, 150, 290, 78, "teal")
    rect(cells, "autonomy", "自主决策与控制子系统\n状态估计 / 任务决策 / 运动控制", 555, 110, 290, 78, "green")
    rect(cells, "operator", "人机协同子系统\n遥控接管 / 自主授权 / 急停处置", 1000, 150, 290, 78, "orange")
    rect(cells, "obs", "可观测性子系统\n实时看板 / 运行日志 / 黑匣子记录", 1000, 555, 290, 78, "purple")
    rect(cells, "experiment", "实验验证子系统\n场景编排 / 指标评估 / 对比验证", 555, 600, 290, 78, "yellow")
    rect(cells, "deploy", "实物部署子系统\n分级试验 / 链路审计 / 安全回退", 110, 555, 290, 78, "red")
    for spec in [
        ("c1", "sim", "core", "仿真输入", False, [(255, 285), (470, 410)], "exitX=0.5;exitY=1;entryX=0;entryY=0.35;", True),
        ("c2", "autonomy", "core", "自主能力", False, None, "exitX=0.5;exitY=1;entryX=0.5;entryY=0;", True),
        ("c3", "operator", "core", "人工授权", False, [(1145, 285), (930, 410)], "exitX=0.5;exitY=1;entryX=1;entryY=0.35;", True),
        ("c4", "core", "obs", "运行证据", False, None, "exitX=1;entryX=0;", True),
        ("c5", "core", "experiment", "实验数据", False, None, "exitX=0.5;exitY=1;entryX=0.5;entryY=0;", True),
        ("c6", "core", "deploy", "工程迁移", False, None, "exitX=0;entryX=1;", True),
        ("c7", "experiment", "sim", "场景反哺", True, [(320, 715), (320, 250)], "exitX=0;entryX=0.5;entryY=1;", False),
        ("c8", "obs", "operator", "态势反馈", True, [(1260, 340)], "exitX=0.5;exitY=0;entryX=0.5;entryY=1;", False),
    ]:
        edge(cells, *spec)
    write("auv_system_capability_map", cells)


def system_subsystem_organization():
    cells = []
    text(cells, "t1", "AUV 系统组织与子系统边界", 350, 20, 700, 40, True)
    text(cells, "s1", "系统组织视角：强调职责边界、协作关系和从地面到水下平台的分工", 390, 62, 660, 34)
    lane(cells, "ground", "地面与实验侧", 80, 130, 1240, 150, "orange")
    lane(cells, "onboard", "艇载自治侧", 80, 335, 1240, 210, "blue")
    lane(cells, "world", "环境与被控对象侧", 80, 610, 1240, 150, "teal")
    for spec in [
        ("g1", "任务设计\n航线 / 场景 / 目标", 75, 55, 220, 58, "yellow", "ground"),
        ("g2", "操作监督\n授权 / 接管 / 急停", 370, 55, 220, 58, "orange", "ground"),
        ("g3", "实验管理\n启动 / 录制 / 评估", 665, 55, 220, 58, "purple", "ground"),
        ("g4", "可视化分析\n态势 / 图表 / 报告", 960, 55, 220, 58, "purple", "ground"),
        ("o1", "通信接入\n上行感知 / 下行控制", 85, 70, 220, 62, "blue", "onboard"),
        ("o2", "状态理解\n定位 / 健康 / 置信度", 375, 70, 220, 62, "green", "onboard"),
        ("o3", "任务智能\n模式切换 / 行为选择", 665, 70, 220, 62, "yellow", "onboard"),
        ("o4", "运动执行\n控制分配 / 安全限幅", 955, 70, 220, 62, "green", "onboard"),
        ("o5", "安全治理\n权限仲裁 / 故障回退", 520, 150, 260, 50, "red", "onboard"),
        ("w1", "虚拟海洋\n可重复场景 / 扰动注入", 150, 55, 260, 58, "teal", "world"),
        ("w2", "真实 AUV\n传感器 / 执行器 / 载体动力学", 570, 55, 260, 58, "teal", "world"),
        ("w3", "外部环境\n水流 / 地形 / 通信条件", 990, 55, 220, 58, "gray", "world"),
    ]:
        rect(cells, *spec)
    for spec in [
        ("s1", "g1", "o3", "任务意图", False, None, "exitX=0.5;exitY=1;entryX=0.4;entryY=0;", False),
        ("s2", "g2", "o5", "控制权约束", False, None, "exitX=0.5;exitY=1;entryX=0.35;entryY=0;", True),
        ("s3", "g3", "o1", "运行编排", False, None, "exitX=0.35;exitY=1;entryX=0.5;entryY=0;", False),
        ("s4", "o1", "o2", "感知输入", False, None, "exitX=1;entryX=0;", True),
        ("s5", "o2", "o3", "态势理解", False, None, "exitX=1;entryX=0;", True),
        ("s6", "o3", "o4", "行动目标", False, None, "exitX=1;entryX=0;", True),
        ("s7", "o5", "o4", "安全约束", False, None, "exitX=1;entryX=0.5;", True),
        ("s8", "o4", "w2", "控制作用", False, None, "exitX=0.5;exitY=1;entryX=0.5;entryY=0;", True),
        ("s9", "w2", "o1", "传感反馈", True, [(230, 590), (230, 285)], "exitX=0;entryX=0.5;entryY=1;", False),
        ("s10", "w1", "o1", "仿真替身", True, None, "exitX=0.5;exitY=0;entryX=0.35;entryY=1;", False),
        ("s11", "w3", "o2", "扰动与不确定性", True, None, "exitX=0.5;exitY=0;entryX=0.65;entryY=1;", False),
        ("s12", "o2", "g4", "观测证据", True, None, "exitX=0.35;exitY=0;entryX=0.5;entryY=1;", False),
    ]:
        edge(cells, *spec)
    write("auv_system_subsystem_organization", cells)


def autonomy_functional_loop():
    cells = []
    text(cells, "t1", "自主系统功能闭环", 390, 20, 620, 40, True)
    text(cells, "s1", "微观系统视角：不展开代码实现，只描述单个自主单元内部的信息加工与安全闭环", 350, 62, 720, 34)
    rect(cells, "env", "环境与艇体\n水流 / 地形 / 动力学", 560, 110, 280, 66, "teal")
    rect(cells, "sense", "感知采集\n运动 / 姿态 / 深度 / 健康", 150, 300, 260, 66, "blue")
    rect(cells, "estimate", "状态理解\n位置速度 / 置信度 / 风险", 560, 300, 280, 66, "green")
    rect(cells, "decide", "任务决策\n目标选择 / 模式管理", 970, 300, 260, 66, "yellow")
    rect(cells, "control", "运动控制\n跟踪 / 约束 / 平滑输出", 560, 510, 280, 66, "green")
    rect(cells, "safety", "安全治理\n权限 / 限幅 / 回退 / 急停", 970, 510, 260, 66, "red")
    rect(cells, "operator", "人工监督\n授权 / 接管 / 任务调整", 150, 510, 260, 66, "orange")
    rect(cells, "evidence", "运行证据\n记录 / 回放 / 评估", 560, 700, 280, 58, "purple")
    for spec in [
        ("l1", "env", "sense", "传感观测", False, [(140, 143), (140, 335)], "exitX=0;exitY=0.5;entryX=0;entryY=0.5;", True),
        ("l2", "sense", "estimate", "信息融合", False, None, "exitX=1;entryX=0;", True),
        ("l3", "estimate", "decide", "态势输入", False, None, "exitX=1;entryX=0;", True),
        ("l4", "decide", "control", "行动目标", False, None, "exitX=0.5;exitY=1;entryX=1;entryY=0;", True),
        ("l5", "control", "env", "控制作用", False, [(520, 543), (520, 143)], "exitX=0;exitY=0.5;entryX=0;entryY=0.5;", True),
        ("l6", "operator", "safety", "授权与接管", False, [(280, 620), (1100, 620)], "exitX=0.5;exitY=1;entryX=0.5;entryY=1;", False),
        ("l7", "safety", "control", "安全边界", False, None, "exitX=0;entryX=1;", True),
        ("l8", "estimate", "safety", "健康与风险", True, [(895, 405), (1110, 405)], "exitX=1;entryX=0.5;entryY=0;", False),
        ("l9", "control", "evidence", "执行记录", True, None, "exitX=0.5;exitY=1;entryX=0.5;entryY=0;", False),
        ("l10", "evidence", "operator", "复盘反馈", True, [(280, 740)], "exitX=0;entryX=0.5;entryY=1;", False),
    ]:
        edge(cells, *spec)
    write("auv_system_autonomy_functional_loop", cells)


def verification_to_deployment_ladder():
    cells = []
    text(cells, "t1", "从仿真验证到实物部署的系统演进", 320, 20, 760, 40, True)
    text(cells, "s1", "系统生命周期视角：以风险递减和证据累积为主线，逐级释放自主能力", 365, 62, 700, 34)
    lane(cells, "ladder", "能力释放路径", 70, 125, 1260, 330, "blue")
    lane(cells, "evidence_lane", "每级必须累积的系统证据", 70, 520, 1260, 190, "purple")
    for spec in [
        ("p1", "算法级仿真\n验证基本可控", 45, 80, 170, 70, "green", "ladder"),
        ("p2", "系统级仿真\n验证闭环协同", 250, 80, 170, 70, "teal", "ladder"),
        ("p3", "协议级联调\n验证通信边界", 455, 80, 170, 70, "blue", "ladder"),
        ("p4", "影子导航\n验证不夺权观测", 660, 80, 170, 70, "yellow", "ladder"),
        ("p5", "单回路闭环\n验证小范围执行", 865, 80, 170, 70, "orange", "ladder"),
        ("p6", "全自主试验\n验证任务完成", 1070, 80, 170, 70, "red", "ladder"),
        ("g1", "模型一致性\n轨迹误差 / 稳定性", 45, 65, 170, 58, "green", "evidence_lane"),
        ("g2", "闭环一致性\n状态 / 控制 / 延迟", 250, 65, 170, 58, "teal", "evidence_lane"),
        ("g3", "链路一致性\n字节 / 时延 / 丢包", 455, 65, 170, 58, "blue", "evidence_lane"),
        ("g4", "安全一致性\n影子输出 / 日志", 660, 65, 170, 58, "yellow", "evidence_lane"),
        ("g5", "执行一致性\n极性 / 死区 / 响应", 865, 65, 170, 58, "orange", "evidence_lane"),
        ("g6", "任务证据\n黑匣子 / 指标 / 回退", 1070, 65, 170, 58, "red", "evidence_lane"),
    ]:
        rect(cells, *spec)
    for i in range(1, 6):
        edge(cells, f"pe{i}", f"p{i}", f"p{i+1}", "风险受控后升级", False, None, "exitX=1;entryX=0;", bold=True)
        edge(cells, f"g{i}", f"p{i}", f"g{i}", "", True, None, "exitX=0.5;exitY=1;entryX=0.5;entryY=0;", bold=False)
    edge(cells, "g6edge", "p6", "g6", "", True, None, "exitX=0.5;exitY=1;entryX=0.5;entryY=0;", bold=False)
    rect(cells, "guard", "统一原则\n先观测、再接管、再释放自主；任何阶段保留回退通道", 360, 245, 620, 58, "gray", "ladder")
    write("auv_system_verification_deployment_ladder", cells)


def dual_brain_async_hardware_v2():
    cells = []
    text(cells, "t1", "双脑异步硬件架构", 390, 20, 620, 42, True)
    text(cells, "s1", "左脑负责高算力认知与规划，右脑负责硬实时执行与安全；二者通过轻量二进制协议解耦", 300, 66, 820, 34)

    lane(cells, "jetson", "左大脑：Jetson Orin", 130, 145, 390, 505, "blue")
    lane(cells, "pc104", "右小脑：PC104", 880, 145, 390, 505, "teal")
    rect(cells, "boundary", "UDP 二进制协议边界\n72B 上行 / 145B 下行", 610, 145, 180, 505, "gray", extra="dashed=1;dashPattern=10 6;strokeWidth=3;fontStyle=1;")

    rect(cells, "jet_env", "Ubuntu / ROS2\nNon-Real-Time", 75, 55, 240, 54, "gray", "jetson", extra="fontStyle=2;")
    rect(cells, "brain", "非实时高算力大脑\n想：理解、决策、规划", 50, 130, 290, 70, "blue", "jetson", extra="fontSize=16;fontStyle=1;")
    rect(cells, "perception", "感知估计\nES-EKF", 85, 245, 220, 56, "green", "jetson")
    rect(cells, "decision", "任务决策\nBehavior Tree", 85, 330, 220, 56, "yellow", "jetson")
    rect(cells, "planning", "路径生成\nUA-MPC", 85, 415, 220, 56, "purple", "jetson")

    rect(cells, "vx_env", "VxWorks\nHard Real-Time", 75, 55, 240, 54, "gray", "pc104", extra="fontStyle=2;")
    rect(cells, "cerebellum", "硬实时小脑 / 脊髓\n做：执行、保护、兜底", 50, 130, 290, 70, "teal", "pc104", extra="fontSize=16;fontStyle=1;")
    rect(cells, "inner", "内环姿态控制\nPID", 85, 245, 220, 56, "green", "pc104")
    rect(cells, "driver", "电机 / 舵机驱动\nDriver", 85, 330, 220, 56, "orange", "pc104")
    rect(cells, "failsafe", "安全失联保护\nFailsafe Watchdog", 85, 415, 220, 56, "red", "pc104")

    text(cells, "think", "高算力：估计 + 决策 + 优化", 175, 665, 310, 34)
    text(cells, "act", "低延迟：内环 + 驱动 + 故障保护", 920, 665, 340, 34)

    for spec in [
        ("db1", "perception", "decision", "", False, None, "exitX=0.5;exitY=1;entryX=0.5;entryY=0;", False),
        ("db2", "decision", "planning", "", False, None, "exitX=0.5;exitY=1;entryX=0.5;entryY=0;", False),
        ("db3", "inner", "driver", "", False, None, "exitX=0.5;exitY=1;entryX=0.5;entryY=0;", False),
        ("db4", "driver", "failsafe", "", False, None, "exitX=0.5;exitY=1;entryX=0.5;entryY=0;", False),
        ("db5", "planning", "inner", "轻量控制意图", False, [(610, 560), (790, 560), (880, 418)], "exitX=1;entryX=0;", True),
        ("db6", "failsafe", "perception", "状态与健康反馈", True, [(790, 610), (610, 610), (520, 273)], "exitX=0;entryX=1;", False),
    ]:
        edge(cells, *spec)
    write("auv_v2_dual_brain_async_hardware", cells)


def uncertainty_highway_v2():
    cells = []
    text(cells, "t1", "不确定性流向图：Uncertainty Highway", 300, 20, 800, 42, True)
    text(cells, "s1", "不确定性不是滤波器内部变量，而是贯穿估计、决策、控制与执行的一等系统信号", 320, 66, 760, 34)

    rect(cells, "disturb", "物理层干扰\nDVL 丢包 / 磁饱和 / 水流扰动", 85, 135, 250, 68, "red")
    rect(cells, "dirty", "受污染传感输入\n时延 / 噪声 / 缺测", 385, 135, 250, 68, "orange")
    rect(cells, "ekf", "状态估计层\nES-EKF", 685, 135, 230, 68, "green")
    rect(cells, "uq", "不确定性量化\n协方差 → 置信度", 965, 135, 260, 68, "purple")

    rect(cells, "highway", "Uncertainty Highway：置信度作为全局调度信号", 325, 285, 750, 62, "gray", extra="dashed=1;dashPattern=8 5;fontStyle=1;fontSize=16;")
    rect(cells, "bt", "行为树决策层\n低置信触发降级 / 上浮 / 保守策略", 260, 455, 340, 78, "yellow")
    rect(cells, "mpc", "安全控制层\n动态权重缩放 / 平滑惩罚约束", 800, 455, 340, 78, "blue")
    rect(cells, "amd", "底层执行器\n安全平滑指令", 550, 655, 300, 70, "teal")

    for spec in [
        ("u1", "disturb", "dirty", "原始数据变脏", False, None, "exitX=1;entryX=0;", False),
        ("u2", "dirty", "ekf", "融合估计", False, None, "exitX=1;entryX=0;", True),
        ("u3", "ekf", "uq", "协方差", False, None, "exitX=1;entryX=0;", True),
        ("u4", "uq", "highway", "标量置信度", False, None, "exitX=0.5;exitY=1;entryX=0.82;entryY=0;", True),
        ("u5", "highway", "bt", "决策阈值", False, None, "exitX=0.3;exitY=1;entryX=0.5;entryY=0;", True),
        ("u6", "highway", "mpc", "控制调度", False, None, "exitX=0.7;exitY=1;entryX=0.5;entryY=0;", True),
        ("u7", "bt", "amd", "安全模式", False, None, "exitX=0.5;exitY=1;entryX=0.35;entryY=0;", True),
        ("u8", "mpc", "amd", "平滑约束指令", False, None, "exitX=0.5;exitY=1;entryX=0.65;entryY=0;", True),
    ]:
        edge(cells, *spec)
    write("auv_v2_uncertainty_highway", cells)


def five_layer_functional_architecture_v2():
    cells = []
    text(cells, "t1", "五层软件功能架构", 390, 20, 620, 42, True)
    text(cells, "s1", "写功能，不写文件名：用数学与逻辑职责表达软件分层，而非实现清单", 380, 66, 660, 34)

    for spec in [
        ("l1", "系统入口与配置分发", 120, 125, 1160, 90, "blue"),
        ("l2", "硬件 / 仿真双工适配层\nGeneric AUV Interface", 120, 235, 1160, 100, "teal"),
        ("l3", "自治行为与安全治理层", 120, 355, 1160, 100, "yellow"),
        ("l4", "数学模型与优化算法层", 120, 475, 1160, 110, "green"),
        ("l5", "协议契约与物理约束层", 120, 605, 1160, 95, "purple"),
    ]:
        lane(cells, *spec)

    for spec in [
        ("a1", "实验模式选择\n仿真 / 协议 / 真机", 90, 36, 250, 40, "blue", "l1"),
        ("a2", "参数一致性分发\n场景 / 控制 / 安全", 455, 36, 250, 40, "blue", "l1"),
        ("a3", "运行生命周期管理\n启动 / 记录 / 收尾", 820, 36, 250, 40, "blue", "l1"),
        ("b1", "虚实统一接口\n同一控制语义", 90, 44, 250, 44, "teal", "l2"),
        ("b2", "坐标与时间对齐\n统一参考系", 455, 44, 250, 44, "teal", "l2"),
        ("b3", "传感与执行抽象\n输入输出对偶", 820, 44, 250, 44, "teal", "l2"),
        ("c1", "任务状态机\n阶段 / 模式 / 回退", 90, 44, 250, 44, "yellow", "l3"),
        ("c2", "安全仲裁\n权限 / 急停 / 降级", 455, 44, 250, 44, "yellow", "l3"),
        ("c3", "行为选择\n搜索 / 跟踪 / 保守", 820, 44, 250, 44, "yellow", "l3"),
        ("d1", "运动学递推阵\n状态演化", 45, 46, 210, 46, "green", "l4"),
        ("d2", "声学投影几何\n观测约束", 310, 46, 210, 46, "green", "l4"),
        ("d3", "误差状态滤波\n不确定性传播", 575, 46, 210, 46, "green", "l4"),
        ("d4", "非线性时域优化器\n安全平滑控制", 840, 46, 250, 46, "green", "l4"),
        ("e1", "轻量通信契约\n最小字节边界", 145, 38, 250, 40, "purple", "l5"),
        ("e2", "物理可行域\n限幅 / 死区 / 饱和", 455, 38, 250, 40, "purple", "l5"),
        ("e3", "共享语义基座\n模式 / 状态 / 指令", 765, 38, 250, 40, "purple", "l5"),
    ]:
        rect(cells, *spec)

    for spec in [
        ("fl1", "a2", "b1", "配置约束", False, [(580, 225), (210, 225)], "exitX=0.5;exitY=1;entryX=0;entryY=0.5;", True),
        ("fl2", "b2", "c2", "运行态势", False, [(580, 345), (430, 345), (430, 420)], "exitX=0.5;exitY=1;entryX=0;entryY=0.5;", True),
        ("fl3", "c3", "d4", "目标与边界", False, None, "exitX=0.5;exitY=1;entryX=0.5;entryY=0;", True),
        ("fl4", "d3", "e2", "可行域约束", False, [(845, 670)], "exitX=1;exitY=0.5;entryX=1;entryY=0.5;", True),
    ]:
        edge(cells, *spec)
    write("auv_v2_five_layer_functional_architecture", cells)


def behavior_tree_illustration():
    cells = []
    text(cells, "t1", "行为树决策核心示意", 390, 20, 620, 42, True)
    text(cells, "s1", "任务分层：主选择器优先安全，然后任务序列；安全分支具备最高优先级，可打断正常任务", 300, 66, 820, 34)

    rect(cells, "root", "Selector\n主根节点（优先级从左到右）", 560, 130, 320, 74, "purple", extra="fontStyle=1;fontSize=16;")

    rect(cells, "safety_seq", "Sequence\n安全监督分支", 130, 260, 260, 66, "red", extra="fontStyle=1;")
    rect(cells, "mission_seq", "Sequence\n任务执行分支", 610, 260, 260, 66, "yellow", extra="fontStyle=1;")
    rect(cells, "idle", "Idle\n待机 / 记录", 1090, 275, 220, 56, "gray")

    rect(cells, "s_low_batt", "Condition\n低电量 / 漏水 / 超时", 60, 405, 210, 60, "red")
    rect(cells, "s_surface", "Action\n上浮返航 (Failsafe)", 290, 405, 210, 60, "red")

    rect(cells, "m_pre", "Condition\n预检通过 / 授权 OK", 555, 405, 220, 60, "yellow")
    rect(cells, "m_seq", "Sequence\n巡线 → 到点 → 拍照", 795, 405, 220, 60, "yellow")

    rect(cells, "m_track", "Action\n巡线跟踪", 570, 540, 200, 56, "green")
    rect(cells, "m_reach", "Action\n到点悬停", 790, 540, 200, 56, "green")
    rect(cells, "m_shot", "Action\n拍照记录", 1010, 540, 200, 56, "green")

    text(cells, "legend", "图例：菱形样式在此以 Sequence/Selector 语义体现；红色=安全分支，黄色=任务分支，绿色=末端动作", 130, 690, 1160, 34)

    for spec in [
        ("bt1", "root", "safety_seq", "优先级 1", False, None, "exitX=0.25;exitY=1;entryX=0.5;entryY=0;", True),
        ("bt2", "root", "mission_seq", "优先级 2", False, None, "exitX=0.5;exitY=1;entryX=0.5;entryY=0;", True),
        ("bt3", "root", "idle", "回落", False, None, "exitX=0.85;exitY=1;entryX=0.5;entryY=0;", False),
        ("bt4", "safety_seq", "s_low_batt", "检测", False, None, "exitX=0.25;exitY=1;entryX=0.5;entryY=0;", False),
        ("bt5", "safety_seq", "s_surface", "触发", False, None, "exitX=0.75;exitY=1;entryX=0.5;entryY=0;", False),
        ("bt6", "mission_seq", "m_pre", "校验", False, None, "exitX=0.25;exitY=1;entryX=0.5;entryY=0;", False),
        ("bt7", "mission_seq", "m_seq", "展开", False, None, "exitX=0.75;exitY=1;entryX=0.5;entryY=0;", False),
        ("bt8", "m_seq", "m_track", "step 1", False, None, "exitX=0.2;exitY=1;entryX=0.5;entryY=0;", False),
        ("bt9", "m_seq", "m_reach", "step 2", False, None, "exitX=0.5;exitY=1;entryX=0.5;entryY=0;", False),
        ("bt10", "m_seq", "m_shot", "step 3", False, None, "exitX=0.8;exitY=1;entryX=0.5;entryY=0;", False),
    ]:
        edge(cells, *spec)
    write("auv_v2_behavior_tree_illustration", cells)


def mission_state_machine():
    cells = []
    text(cells, "t1", "任务状态机 (Mission FSM)", 480, 20, 640, 42, True)
    text(cells, "s1", "从空闲到全自主的运行阶段，每一步都有独立准入条件与回退回路", 460, 66, 720, 34)

    states = [
        ("st_idle",   "IDLE\n上电空闲",              60,  190, 180, 100, "gray"),
        ("st_pre",    "PREFLIGHT\n预检 / 授权",      290, 190, 200, 100, "yellow"),
        ("st_shadow", "SHADOW\n影子导航（不夺权）",   540, 190, 230, 100, "orange"),
        ("st_single", "SINGLE_LOOP\n单回路闭环",      820, 190, 220, 100, "blue"),
        ("st_full",   "FULL_AUTONOMY\n全自主任务",   1100, 190, 230, 100, "green"),
        ("st_done",   "COMPLETE\n收尾 / 回收",       380, 540, 230, 100, "purple"),
        ("st_hold",   "SAFE_HOLD\n安全保持 / 回退",  1100, 540, 230, 100, "red"),
    ]
    for spec in states:
        ellipse(cells, *spec)

    text(cells, "legend", "规则：任何一态在安全触发下都可直接迁移至 SAFE_HOLD；操作员可主动降级到 SHADOW；COMPLETE 后回到 IDLE", 100, 810, 1300, 40)

    for spec in [
        ("fs1", "st_idle",   "st_pre",    "操作员启动",   False, None, "exitX=1;exitY=0.5;entryX=0;entryY=0.5;", True),
        ("fs2", "st_pre",    "st_shadow", "预检通过",     False, None, "exitX=1;exitY=0.5;entryX=0;entryY=0.5;", True),
        ("fs3", "st_shadow", "st_single", "影子对齐 OK",  False, None, "exitX=1;exitY=0.5;entryX=0;entryY=0.5;", True),
        ("fs4", "st_single", "st_full",   "单点闭环稳定", False, None, "exitX=1;exitY=0.5;entryX=0;entryY=0.5;", True),
        # 任务完成：st_full → st_done, 长横线走 y=470
        ("fs5", "st_full",   "st_done",   "任务完成",     False,
            [(1160, 470), (495, 470)], "exitX=0.25;exitY=1;entryX=0.5;entryY=0;", True),
        # 安全触发：st_full → st_hold, 直下
        ("fs6", "st_full",   "st_hold",   "安全触发",     False,
            None, "exitX=0.85;exitY=1;entryX=0.85;entryY=0;", False),
        # 偏差过大：st_single → st_hold, 走 y=400 轨道
        ("fs7", "st_single", "st_hold",   "偏差过大",     True,
            [(985, 400), (1215, 400)], "exitX=0.75;exitY=1;entryX=0.5;entryY=0;", False),
        # 置信度不足：st_shadow → st_hold, 走 y=440 轨道，进入左上
        ("fs8", "st_shadow", "st_hold",   "置信度不足",   True,
            [(700, 440), (1150, 440)], "exitX=0.7;exitY=1;entryX=0.2;entryY=0;", False),
        # 复位再预检：st_hold → st_pre, 底部 y=740
        ("fs9", "st_hold",   "st_pre",    "复位再预检",   True,
            [(1160, 740), (390, 740)], "exitX=0.25;exitY=1;entryX=0.5;entryY=1;", False),
        # 回到空闲：st_done → st_idle, 底部 y=760
        ("fs10", "st_done",  "st_idle",   "回到空闲",     True,
            [(410, 760), (150, 760)], "exitX=0.15;exitY=1;entryX=0.5;entryY=1;", False),
    ]:
        edge(cells, *spec)
    write("auv_v2_mission_state_machine", cells, page_width=1440, page_height=900)


def emergency_transition():
    cells = []
    text(cells, "t1", "紧急情况下的状态切换与仲裁", 380, 20, 660, 42, True)
    text(cells, "s1", "AUTONOMOUS 运行中一旦触发关键守卫，Arbiter 立即将控制权切换到 HOLD 或 REMOTE / SURFACE", 260, 66, 900, 34)

    ellipse(cells, "auto", "AUTONOMOUS\n自主运行", 620, 130, 220, 100, "green", extra="fontStyle=1;fontSize=16;")

    rect(cells, "g1", "通信丢失\nuplink age > τ", 100, 300, 220, 66, "red")
    rect(cells, "g2", "EKF 发散\n协方差爆炸", 380, 300, 220, 66, "red")
    rect(cells, "g3", "电量告警\nSOC < 阈值", 660, 300, 220, 66, "red")
    rect(cells, "g4", "操作员 ESTOP\n地面站按下", 940, 300, 220, 66, "red")

    diamond(cells, "arb", "Arbiter\n权限仲裁", 620, 440, 220, 110, "purple", extra="fontStyle=1;")

    ellipse(cells, "hold", "SAFE_HOLD\n零推力保持", 130, 640, 220, 100, "gray")
    ellipse(cells, "remote", "REMOTE\n交还操作员", 470, 640, 220, 100, "orange")
    ellipse(cells, "surface", "SURFACE\n应急上浮", 810, 640, 220, 100, "yellow")
    ellipse(cells, "kill", "KILL\n执行器截止", 1140, 640, 200, 100, "red")

    text(cells, "legend", "阈值命中优先级：ESTOP > 通信丢失 > EKF 发散 > 电量告警；不同守卫映射到不同目标态", 130, 800, 1180, 34)

    for spec in [
        ("et1", "auto", "g1", "监听", True,
            [(730, 260), (210, 260)], "exitX=0.15;exitY=1;entryX=0.5;entryY=0;", False),
        ("et2", "auto", "g2", "监听", True,
            [(730, 275), (490, 275)], "exitX=0.4;exitY=1;entryX=0.5;entryY=0;", False),
        ("et3", "auto", "g3", "监听", True,
            [(730, 275), (770, 275)], "exitX=0.6;exitY=1;entryX=0.5;entryY=0;", False),
        ("et4", "auto", "g4", "监听", True,
            [(730, 260), (1050, 260)], "exitX=0.85;exitY=1;entryX=0.5;entryY=0;", False),
        ("et5", "g1", "arb", "触发", False,
            [(210, 400), (630, 400)], "exitX=0.5;exitY=1;entryX=0.05;entryY=0.4;", True),
        ("et6", "g2", "arb", "触发", False, None, "exitX=0.5;exitY=1;entryX=0.35;entryY=0;", True),
        ("et7", "g3", "arb", "触发", False, None, "exitX=0.5;exitY=1;entryX=0.65;entryY=0;", True),
        ("et8", "g4", "arb", "触发", False,
            [(1050, 400), (830, 400)], "exitX=0.5;exitY=1;entryX=0.95;entryY=0.4;", True),
        ("et9",  "arb", "hold",    "低电量 → 保持",     False,
            [(660, 600), (240, 600)], "exitX=0.2;exitY=1;entryX=0.5;entryY=0;", True),
        ("et10", "arb", "remote",  "通信丢失 → 遥控",   False,
            [(700, 600), (580, 600)], "exitX=0.4;exitY=1;entryX=0.5;entryY=0;", True),
        ("et11", "arb", "surface", "EKF 发散 → 上浮",   False,
            [(760, 600), (920, 600)], "exitX=0.6;exitY=1;entryX=0.5;entryY=0;", True),
        ("et12", "arb", "kill",    "ESTOP → 截止",      False,
            [(800, 600), (1240, 600)], "exitX=0.8;exitY=1;entryX=0.5;entryY=0;", True),
    ]:
        edge(cells, *spec)
    write("auv_v2_emergency_transition", cells, page_height=900)


def mission_lifecycle_flow():
    cells = []
    text(cells, "t1", "任务完整生命周期泳道", 370, 20, 660, 42, True)
    text(cells, "s1", "四方协同：操作员发起、Arbiter 授权、Brain 执行、AMD 反馈；红色为安全回退通道", 300, 66, 820, 34)

    lane(cells, "op", "操作员 / 地面站", 90, 130, 1260, 130, "orange")
    lane(cells, "arb", "Arbiter / 安全守卫", 90, 275, 1260, 130, "red")
    lane(cells, "brain", "Brain / 决策与控制", 90, 420, 1260, 170, "blue")
    lane(cells, "amd", "AMD / 执行与反馈", 90, 605, 1260, 130, "teal")

    rect(cells, "op1", "任务发起\n加载 yaml", 50, 55, 190, 58, "yellow", "op")
    rect(cells, "op2", "预检授权\n签发权限令牌", 275, 55, 190, 58, "yellow", "op")
    rect(cells, "op3", "任务监视\n看板 / 视频", 500, 55, 190, 58, "purple", "op")
    rect(cells, "op4", "干预窗口\n必要时接管", 725, 55, 190, 58, "orange", "op")
    rect(cells, "op5", "任务收尾\n复盘 / 归档", 950, 55, 220, 58, "gray", "op")

    rect(cells, "ar1", "权限锁定\n拒绝越权", 50, 50, 190, 58, "red", "arb")
    rect(cells, "ar2", "AutonomyGuard\n通信 / 电压 / 置信度", 275, 50, 220, 58, "red", "arb")
    rect(cells, "ar3", "权限迁移\nREMOTE → AUTONOMOUS", 525, 50, 240, 58, "purple", "arb")
    rect(cells, "ar4", "回退触发\nEStop / 超时", 795, 50, 220, 58, "red", "arb")
    rect(cells, "ar5", "结束确认\n关闭权限", 1045, 50, 190, 58, "gray", "arb")

    rect(cells, "br1", "状态估计\nES-EKF 初始化", 50, 70, 200, 60, "green", "brain")
    rect(cells, "br2", "行为树运行\n选择任务分支", 285, 70, 200, 60, "yellow", "brain")
    rect(cells, "br3", "MPC 控制\n生成安全指令", 520, 70, 200, 60, "blue", "brain")
    rect(cells, "br4", "健康自检\n置信度输出", 755, 70, 210, 60, "green", "brain")
    rect(cells, "br5", "任务总结\n生成运行报告", 1000, 70, 210, 60, "purple", "brain")

    rect(cells, "am1", "传感器上行\nDVL / IMU / DVL", 50, 50, 210, 58, "teal", "amd")
    rect(cells, "am2", "执行下行\n5 通道指令", 300, 50, 210, 58, "teal", "amd")
    rect(cells, "am3", "响应反馈\n姿态 / 位置", 550, 50, 210, 58, "teal", "amd")
    rect(cells, "am4", "故障上报\n漏水 / 短路", 800, 50, 210, 58, "red", "amd")
    rect(cells, "am5", "回收对接\n断开动力", 1050, 50, 210, 58, "gray", "amd")

    for spec in [
        ("ml1", "op1", "op2", "", False, None, "exitX=1;entryX=0;", True),
        ("ml2", "op2", "op3", "", False, None, "exitX=1;entryX=0;", True),
        ("ml3", "op3", "op4", "", False, None, "exitX=1;entryX=0;", False),
        ("ml4", "op4", "op5", "", False, None, "exitX=1;entryX=0;", True),
        ("ml5", "op2", "ar2", "签发", False, None, "exitX=0.5;exitY=1;entryX=0.5;entryY=0;", True),
        ("ml6", "ar1", "ar2", "", False, None, "exitX=1;entryX=0;", False),
        ("ml7", "ar2", "ar3", "", False, None, "exitX=1;entryX=0;", True),
        ("ml8", "ar3", "ar4", "", False, None, "exitX=1;entryX=0;", False),
        ("ml9", "ar4", "ar5", "", False, None, "exitX=1;entryX=0;", False),
        ("ml10", "ar3", "br2", "", False, [(610, 410), (470, 410)], "exitX=0.2;exitY=1;entryX=0.5;entryY=0;", True),
        ("ml11", "br1", "br2", "", False, None, "exitX=1;entryX=0;", True),
        ("ml12", "br2", "br3", "", False, None, "exitX=1;entryX=0;", True),
        ("ml13", "br3", "br4", "", False, None, "exitX=1;entryX=0;", False),
        ("ml14", "br4", "br5", "", False, None, "exitX=1;entryX=0;", True),
        ("ml15", "br3", "am2", "", False, None, "exitX=0.5;exitY=1;entryX=0.5;entryY=0;", True),
        ("ml16", "am1", "br1", "", False, None, "exitX=0.5;exitY=0;entryX=0.5;entryY=1;", True),
        ("ml17", "am3", "br4", "", False, None, "exitX=0.5;exitY=0;entryX=0.5;entryY=1;", False),
        ("ml18", "am4", "ar4", "故障", True, None, "exitX=0.5;exitY=0;entryX=0.5;entryY=1;", False),
        ("ml19", "ar4", "op4", "告警", True, None, "exitX=0.5;exitY=0;entryX=0.5;entryY=1;", False),
        ("ml20", "op5", "am5", "回收指令", False, [(1300, 630)], "exitX=1;exitY=0.5;entryX=1;entryY=0.5;", False),
    ]:
        edge(cells, *spec)
    write("auv_v2_mission_lifecycle_flow", cells)


def main() -> None:
    code_layer_architecture()
    runtime_dataflow()
    ros2_node_topology()
    safety_arbiter_deployment()
    system_capability_map()
    system_subsystem_organization()
    autonomy_functional_loop()
    verification_to_deployment_ladder()
    dual_brain_async_hardware_v2()
    uncertainty_highway_v2()
    five_layer_functional_architecture_v2()
    behavior_tree_illustration()
    mission_state_machine()
    emergency_transition()
    mission_lifecycle_flow()
    for path in sorted(OUT.glob("*.drawio")):
        print(path)


if __name__ == "__main__":
    main()
