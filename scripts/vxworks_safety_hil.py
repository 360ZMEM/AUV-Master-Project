#!/usr/bin/env python3
"""VxWorks 深度安全修复 — 空板 HIL 自动化验证脚本。

在 PC 端运行，通过 UDP 协议模拟上位机/Jetson 通信，接收 VxWorks 状态反馈，
辅助验证 BUG-1/3/4/5/6/7/8 安全修复的正确性。

三种运行模式:
  auto-udp : 纯 UDP 自动验证 (心跳/失联/状态回传)
  guided   : 交互式引导 (提示 Shell 操作, 自动验证反馈)
  telnet   : 全自动 Telnet 注入 (需 VxWorks 开启 telnetd)

使用:
    python scripts/vxworks_safety_hil.py --mode auto-udp
    python scripts/vxworks_safety_hil.py --mode guided
    python scripts/vxworks_safety_hil.py --mode telnet --host 192.168.0.101

网络拓扑:
    PC (192.168.0.11) ──UDP:21──> VxWorks (192.168.0.101)
    PC <──UDP:21───── VxWorks (上行状态帧, 当前 docker compose 映射)
    PC <──UDP:52367── VxWorks (UdpLogger 日志)
"""

from __future__ import annotations

import argparse
import socket
import struct
import sys
import telnetlib
import threading
import time
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# 协议常量 (与 common/protocol.py 一致, 这里独立定义避免导入链问题)
# ---------------------------------------------------------------------------

DOWNLINK_SIZE = 72
DOWNLINK_HEADER = b"$CKTH"
FRAME_TAIL = b"\xff\xff"

UPLINK_SIZE = 145
UPLINK_HEADER = b"$AUV\x91"

VXWORKS_IP = "192.168.0.101"
VXWORKS_PORT = 21
LOG_PORT = 52367
UPLINK_PORT = 21


# ---------------------------------------------------------------------------
# 协议编解码
# ---------------------------------------------------------------------------

def checksum(data: bytes) -> int:
    return sum(data) & 0xFF


def build_heartbeat_packet(
    *,
    ctrl_mode: int = 0xEE,
    motor_speed1: int = 0,
    motor_speed2: int = 0,
    depth_para1: int = 0,
    depth_para2: int = 0,
    set_course: int = 0,
    target_depth_x10: int = 0,
    frame_counter: int = 0,
) -> bytes:
    """构建 72 字节 $CKTH 下行帧 (简化版, 仅填充 HIL 测试需要的字段)。"""
    pkt = bytearray(DOWNLINK_SIZE)
    pkt[0:5] = DOWNLINK_HEADER
    pkt[5] = frame_counter & 0xFF
    pkt[6] = 0x01  # obj address
    pkt[7] = ctrl_mode & 0xFF

    struct.pack_into(">H", pkt, 8, depth_para1 & 0xFFFF)
    struct.pack_into(">H", pkt, 10, depth_para2 & 0xFFFF)

    pkt[22] = 0x00  # work_cmd

    struct.pack_into(">h", pkt, 23, _clamp16(motor_speed1))
    struct.pack_into(">h", pkt, 25, _clamp16(motor_speed2))

    struct.pack_into(">H", pkt, 35, set_course & 0xFFFF)
    struct.pack_into(">i", pkt, 37, target_depth_x10)

    pkt[69] = checksum(pkt[:69])
    pkt[70:72] = FRAME_TAIL
    return bytes(pkt)


def _clamp16(v: int) -> int:
    return max(-32768, min(32767, v))


@dataclass
class UplinkStatus:
    """从 $AUV 上行帧中提取的关键状态字段。"""
    ctrl_mode: int = 0
    motor1_rpm: int = 0
    motor2_rpm: int = 0
    depth_m: float = 0.0
    heading_deg: float = 0.0
    pitch_deg: float = 0.0
    roll_deg: float = 0.0
    altitude_m: float = 0.0
    sys_abnorm: int = 0
    dev_abnorm: int = 0
    raw: bytes = b""


def parse_uplink(packet: bytes) -> UplinkStatus | None:
    """解析 145 字节上行帧, 返回关键字段。校验失败返回 None。"""
    if len(packet) != UPLINK_SIZE:
        return None
    if packet[0:5] != UPLINK_HEADER:
        return None
    if packet[143:145] != FRAME_TAIL:
        return None
    expected_cs = checksum(packet[:142])
    if packet[142] != expected_cs:
        return None

    return UplinkStatus(
        ctrl_mode=packet[7],
        motor1_rpm=struct.unpack(">h", packet[23:25])[0],
        motor2_rpm=struct.unpack(">h", packet[25:27])[0],
        depth_m=struct.unpack(">H", packet[38:40])[0] * 0.1,
        heading_deg=struct.unpack(">h", packet[72:74])[0] * 0.1,
        pitch_deg=struct.unpack(">h", packet[74:76])[0] * 0.1,
        roll_deg=struct.unpack(">h", packet[76:78])[0] * 0.1,
        altitude_m=struct.unpack(">H", packet[84:86])[0] * 0.1,
        sys_abnorm=struct.unpack(">I", packet[126:130])[0],
        dev_abnorm=struct.unpack(">I", packet[130:134])[0],
        raw=packet,
    )


# ---------------------------------------------------------------------------
# Sys_Abnorm_Inf 位图解码
# ---------------------------------------------------------------------------

SYS_ABNORM_BITS = {
    0: "舱体漏水",
    1: "舱体温度超限",
    2: "舱体压力异常",
    3: "系统电源异常",
    4: "设备电源异常",
    5: "系统通信异常",
    6: "设备状态异常",
    7: "MCU-CPU通信异常",
    8: "CPU-MCU通信异常",
    9: "深度超限Para1 (BUG-4触发)",
    10: "深度超限Para2",
    11: "离底高度预警(软限) [BUG-5]",
    12: "离底高度危机(硬限) [BUG-5]",
    13: "DVL丢底降级 [BUG-6]",
    14: "Jetson通信超时",
    15: "水池深度超限 [BUG-7]",
    16: "水池Pitch超限 [BUG-7]",
    17: "水池Roll超限 [BUG-7]",
}


def decode_sys_abnorm(value: int) -> list[str]:
    active = []
    for bit, desc in SYS_ABNORM_BITS.items():
        if value & (1 << bit):
            active.append(f"  Bit{bit:2d}: {desc}")
    return active


# ---------------------------------------------------------------------------
# UDP 收发器
# ---------------------------------------------------------------------------

class UDPTransceiver:
    """管理与 VxWorks 的 UDP 通信。"""

    def __init__(
        self,
        vxworks_ip: str = VXWORKS_IP,
        bind_ip: str = "0.0.0.0",
        uplink_port: int = UPLINK_PORT,
        log_port: int = LOG_PORT,
    ):
        self.vxworks_ip = vxworks_ip
        self.bind_ip = bind_ip
        self.uplink_port = uplink_port
        self.log_port = log_port
        self._frame_counter = 0
        self._last_uplink: UplinkStatus | None = None
        self._log_lines: list[str] = []
        self._running = False
        self._lock = threading.Lock()

        # 下行发送 socket (目标: VxWorks:21)
        self._tx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # 上行接收 socket (默认监听: 21/udp, 对齐当前 docker compose 端口映射)
        self._rx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._rx_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._rx_sock.bind((bind_ip, uplink_port))
        self._rx_sock.settimeout(1.0)

        # 日志接收 socket (默认监听: 52367/udp)
        self._log_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._log_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._log_sock.bind((bind_ip, log_port))
        self._log_sock.settimeout(1.0)

    def start(self):
        self._running = True
        threading.Thread(target=self._rx_loop, daemon=True, name="uplink-rx").start()
        threading.Thread(target=self._log_loop, daemon=True, name="log-rx").start()

    def stop(self):
        self._running = False
        self._tx_sock.close()
        self._rx_sock.close()
        self._log_sock.close()

    def send_heartbeat(self, **kwargs):
        kwargs.setdefault("frame_counter", self._frame_counter)
        pkt = build_heartbeat_packet(**kwargs)
        self._tx_sock.sendto(pkt, (self.vxworks_ip, VXWORKS_PORT))
        self._frame_counter = (self._frame_counter + 1) & 0xFF

    def get_last_uplink(self) -> UplinkStatus | None:
        with self._lock:
            return self._last_uplink

    def get_log_lines(self, clear: bool = True) -> list[str]:
        with self._lock:
            lines = list(self._log_lines)
            if clear:
                self._log_lines.clear()
        return lines

    def wait_for_sys_abnorm_bit(self, bit: int, timeout: float = 15.0) -> bool:
        """等待指定 Sys_Abnorm 位被置位。"""
        t0 = time.time()
        while time.time() - t0 < timeout:
            st = self.get_last_uplink()
            if st and (st.sys_abnorm & (1 << bit)):
                return True
            time.sleep(0.2)
        return False

    def wait_for_sys_abnorm_clear(self, bit: int, timeout: float = 15.0) -> bool:
        """等待指定 Sys_Abnorm 位被清除。"""
        t0 = time.time()
        while time.time() - t0 < timeout:
            st = self.get_last_uplink()
            if st and not (st.sys_abnorm & (1 << bit)):
                return True
            time.sleep(0.2)
        return False

    def _rx_loop(self):
        while self._running:
            try:
                data, _ = self._rx_sock.recvfrom(4096)
                status = parse_uplink(data)
                if status:
                    with self._lock:
                        self._last_uplink = status
            except socket.timeout:
                continue
            except OSError:
                break

    def _log_loop(self):
        while self._running:
            try:
                data, _ = self._log_sock.recvfrom(4096)
                text = data.decode("utf-8", errors="replace").strip()
                with self._lock:
                    self._log_lines.append(text)
                    if len(self._log_lines) > 500:
                        self._log_lines = self._log_lines[-200:]
            except socket.timeout:
                continue
            except OSError:
                break


# ---------------------------------------------------------------------------
# Telnet Shell 控制器 (用于 telnet 全自动模式)
# ---------------------------------------------------------------------------

class VxWorksShell:
    """通过 telnet 连接 VxWorks shell 并执行命令。"""

    def __init__(
        self,
        host: str,
        port: int = 23,
        username: str = "target",
        password: str = "password",
        timeout: float = 5.0,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self._tn: telnetlib.Telnet | None = None

    def connect(self) -> bool:
        try:
            self._tn = telnetlib.Telnet(self.host, self.port, self.timeout)
            banner = self._tn.read_until(b"->", timeout=1.0)
            if b"->" in banner:
                return True

            # VxWorks telnetd may require username/password before shell prompt.
            if b"login" in banner.lower() or b"username" in banner.lower():
                self._tn.write((self.username + "\n").encode("ascii"))
                banner += self._tn.read_until(b"assword", timeout=self.timeout)

            if b"assword" in banner.lower():
                self._tn.write((self.password + "\n").encode("ascii"))

            shell_prompt = self._tn.read_until(b"->", timeout=self.timeout)
            if b"->" not in shell_prompt:
                print("  [ERROR] Telnet 已连接, 但未看到 VxWorks shell 提示符 '->'")
                return False
            return True
        except Exception as e:
            print(f"  [ERROR] Telnet 连接失败: {e}")
            return False

    def execute(self, cmd: str, wait: float = 0.3) -> str:
        """执行 VxWorks shell 命令并返回输出。"""
        if not self._tn:
            return ""
        self._tn.write((cmd + "\n").encode("ascii"))
        time.sleep(wait)
        try:
            output = self._tn.read_very_eager().decode("ascii", errors="replace")
        except EOFError:
            output = ""
        return output

    def write_float(self, var: str, value: float):
        self.execute(f"{var} = {value}")

    def write_int(self, var: str, value: int):
        self.execute(f"{var} = {value}")

    def write_nan(self, var: str):
        """将 float 变量设为 NaN (IEEE754 quiet NaN)。"""
        self.execute(f"*((unsigned int *)&{var}) = 0x7fc00000")

    def read_int(self, var: str) -> int | None:
        output = self.execute(f"printf(\"%d\\n\", {var})")
        for line in output.split("\n"):
            line = line.strip()
            if line.lstrip("-").isdigit():
                return int(line)
        return None

    def read_hex(self, var: str) -> int | None:
        output = self.execute(f"printf(\"0x%08x\\n\", {var})")
        for line in output.split("\n"):
            line = line.strip()
            if line.startswith("0x"):
                try:
                    return int(line, 16)
                except ValueError:
                    pass
        return None

    def read_float(self, var: str) -> float | None:
        output = self.execute(f"printf(\"%.6f\\n\", {var})")
        for line in output.split("\n"):
            line = line.strip()
            try:
                return float(line)
            except ValueError:
                continue
        return None

    def delay(self, seconds: float):
        ticks = int(seconds * 1000)
        self.execute(f"taskDelay({ticks})", wait=seconds + 0.5)

    def close(self):
        if self._tn:
            self._tn.close()
            self._tn = None


# ---------------------------------------------------------------------------
# 测试用例定义
# ---------------------------------------------------------------------------

@dataclass
class TestResult:
    name: str
    passed: bool
    detail: str


class HILTestSuite:
    """HIL 验证测试套件。"""

    def __init__(self, udp: UDPTransceiver, shell: VxWorksShell | None = None):
        self.udp = udp
        self.shell = shell
        self.results: list[TestResult] = []

    def run_all_auto_udp(self):
        """运行所有纯 UDP 可验证的测试。"""
        print("\n" + "=" * 60)
        print("  VxWorks 深度安全修复 — 自动 UDP 验证")
        print("=" * 60)

        self._test_uplink_alive()
        self._test_log_alive()
        self._test_heartbeat_keeps_jetson_alive()
        self._test_jetson_lost_triggers_bit14()
        self._test_sys_abnorm_readback()

        self._print_summary()

    def run_all_telnet(self):
        """运行所有测试 (Telnet 全自动)。"""
        if not self.shell:
            print("[ERROR] Telnet shell 未连接")
            return

        print("\n" + "=" * 60)
        print("  VxWorks 深度安全修复 — Telnet 全自动验证")
        print("=" * 60)

        self._test_uplink_alive()
        self._test_log_alive()
        self._test_heartbeat_keeps_jetson_alive()
        self._test_jetson_lost_triggers_bit14()

        # 需要 Shell 注入的测试
        self._test_bug3_counter_slide()
        self._test_bug4_emergency_ascent()
        self._test_bug5_soft_limit()
        self._test_bug5_hard_limit()
        self._test_bug6_dvl_lost()
        self._test_bug1_nan_defense()

        self._print_summary()

    def run_guided(self):
        """交互式引导模式。"""
        print("\n" + "=" * 60)
        print("  VxWorks 深度安全修复 — 交互式引导验证")
        print("=" * 60)
        print("  此模式会提示你在 VxWorks Shell 中执行命令,")
        print("  然后自动验证 UDP 反馈结果。\n")

        self._test_uplink_alive()
        self._test_log_alive()

        # Guided tests with shell instructions
        self._guided_bug3()
        self._guided_bug4()
        self._guided_bug5_soft()
        self._guided_bug5_hard()
        self._guided_bug6_dvl_lost()
        self._guided_bug1_nan()

        self._print_summary()

    # ------ 纯 UDP 测试 ------

    def _test_uplink_alive(self):
        """TEST-V1a: 确认能收到上行帧。"""
        print("\n[TEST] 上行帧接收...")
        t0 = time.time()
        while time.time() - t0 < 5.0:
            st = self.udp.get_last_uplink()
            if st:
                self._pass("上行帧接收", f"CtrlMode=0x{st.ctrl_mode:02X}, Depth={st.depth_m:.1f}m")
                return
            time.sleep(0.3)
        self._fail("上行帧接收", "5s 内未收到有效 $AUV 帧 (检查网线/IP)")

    def _test_log_alive(self):
        """TEST-V1b: 确认能收到 UdpLogger 日志。"""
        print("[TEST] UdpLogger 日志接收...")
        self.udp.get_log_lines(clear=True)
        time.sleep(2.0)
        lines = self.udp.get_log_lines()
        emergency_lines = [l for l in lines if "EmergencyTask" in l]
        if emergency_lines:
            self._pass("UdpLogger 日志", f"收到 {len(emergency_lines)} 条 EmergencyTask 打印")
        elif lines:
            self._pass("UdpLogger 日志", f"收到 {len(lines)} 条日志 (但无 EmergencyTask 关键字)")
        else:
            self._fail("UdpLogger 日志", "2s 内未收到任何 UDP 日志 (检查 UdpLogger 初始化)")

    def _test_heartbeat_keeps_jetson_alive(self):
        """TEST-V8a: 持续发送心跳保持 Jetson 看门狗不触发。"""
        print("[TEST] 心跳保活 (5s)...")
        for _ in range(50):
            self.udp.send_heartbeat(ctrl_mode=0xEE, motor_speed1=300)
            time.sleep(0.1)
        time.sleep(0.5)
        st = self.udp.get_last_uplink()
        if st and not (st.sys_abnorm & (1 << 14)):
            self._pass("心跳保活", f"Bit14=0, CtrlMode=0x{st.ctrl_mode:02X}")
        elif st:
            self._fail("心跳保活", f"Bit14 仍置位! Sys=0x{st.sys_abnorm:08X}")
        else:
            self._fail("心跳保活", "无上行帧反馈")

    def _test_jetson_lost_triggers_bit14(self):
        """TEST-V8b: 停止心跳后 Bit14 应被置位。"""
        print("[TEST] Jetson 失联 Bit14...")
        # 先发心跳让系统进入 Jetson 模式
        for _ in range(20):
            self.udp.send_heartbeat(ctrl_mode=0xEE, motor_speed1=300)
            time.sleep(0.1)
        # 停止发送, 等待 1.5s (看门狗 1.0s 超时 + 余量)
        time.sleep(2.0)
        st = self.udp.get_last_uplink()
        if st and (st.sys_abnorm & (1 << 14)):
            self._pass("Jetson 失联 Bit14", f"Sys=0x{st.sys_abnorm:08X} (Bit14 置位)")
        elif st:
            self._fail("Jetson 失联 Bit14", f"Bit14 未置位! Sys=0x{st.sys_abnorm:08X} (可能看门狗阈值更大)")
        else:
            self._fail("Jetson 失联 Bit14", "无上行帧反馈")

    def _test_sys_abnorm_readback(self):
        """TEST-V9: 确认 Sys_Abnorm 能通过上行帧正确回传。"""
        print("[TEST] Sys_Abnorm 回传一致性...")
        st = self.udp.get_last_uplink()
        if st:
            alerts = decode_sys_abnorm(st.sys_abnorm)
            detail = f"Sys=0x{st.sys_abnorm:08X}"
            if alerts:
                detail += "\n" + "\n".join(alerts)
            self._pass("Sys_Abnorm 回传", detail)
        else:
            self._fail("Sys_Abnorm 回传", "无上行帧")

    # ------ Telnet 自动测试 ------

    def _test_bug3_counter_slide(self):
        """BUG-3: 深度计数器递增+递减。"""
        print("[TEST] BUG-3: 深度计数器滑动窗口...")
        sh = self.shell

        # 复位
        sh.write_int("Depth_Exceed_FromUI12_Depth_Para1", 0)
        sh.write_int("UI_WIFI_Instruction.FromUI12_Depth_Para1", 5)
        sh.write_float("Current_State.Current_Dep", 10.0)

        # 等待 3s (6 cycles @2Hz)
        sh.delay(3.0)
        count_up = sh.read_int("Depth_Exceed_FromUI12_Depth_Para1")

        # 改为正常深度
        sh.write_float("Current_State.Current_Dep", 1.0)
        sh.delay(5.0)
        count_down = sh.read_int("Depth_Exceed_FromUI12_Depth_Para1")

        if count_up is not None and count_up > 0 and count_down is not None and count_down == 0:
            self._pass("BUG-3 滑动窗口", f"递增到 {count_up}, 递减回 {count_down}")
        elif count_up is not None and count_up > 0 and count_down is not None and count_down > 0:
            self._fail("BUG-3 滑动窗口", f"递增到 {count_up} 但递减未归零 ({count_down}), BUG-3 修复可能未生效")
        else:
            self._fail("BUG-3 滑动窗口", f"读取异常: up={count_up}, down={count_down}")

    def _test_bug4_emergency_ascent(self):
        """BUG-4: 超深自救 Motor=300 + 上浮舵。"""
        print("[TEST] BUG-4: 超深自救输出...")
        sh = self.shell

        # 注入超限状态
        sh.write_int("Depth_Exceed_FromUI12_Depth_Para1", 12)
        sh.write_int("UI_WIFI_Instruction.FromUI12_Depth_Para1", 5)
        sh.write_float("Current_State.Current_Dep", 10.0)
        sh.delay(1.0)

        motor1 = sh.read_int("Instruction_To_FMCU.McuFD_Motor1_Set_Speed")
        lh = sh.read_int("Instruction_To_FMCU.McuFD_LH_Set_Rud_Location")
        rh = sh.read_int("Instruction_To_FMCU.McuFD_RH_Set_Rud_Location")

        # 复位
        sh.write_int("Depth_Exceed_FromUI12_Depth_Para1", 0)
        sh.write_float("Current_State.Current_Dep", 0.0)

        if motor1 == 300 and lh is not None and lh > 2200 and rh is not None and rh < 1900:
            self._pass("BUG-4 超深自救", f"Motor1={motor1}, LH={lh}, RH={rh}")
        elif motor1 == 0:
            self._fail("BUG-4 超深自救", f"Motor1=0! 旧 bug 仍在 (推力归零)")
        else:
            self._fail("BUG-4 超深自救", f"Motor1={motor1}, LH={lh}, RH={rh} (预期 300/~2276/~1820)")

    def _test_bug5_soft_limit(self):
        """BUG-5: DVL 软限 Bit11 + 深度截断。"""
        print("[TEST] BUG-5: DVL 软限...")
        sh = self.shell

        # 保持心跳防止 Jetson 失联
        self._background_heartbeat(3.0)

        sh.write_int("Current_State.Current_Mode", 0xEE)
        sh.write_int("UI_WIFI_Instruction.FromUI12_Ctrl_Mode", 0xEE)
        sh.write_int("UI_WIFI_Instruction.FromUI12_Para1", 20000)
        sh.write_float("Current_State.Current_Dep", 15.0)
        sh.write_float("DVL_Prase_Data.BD_Check", 2.0)
        sh.write_float("DVL_Prase_Data.BD_Height", 2.5)

        sh.delay(3.0)

        sys_val = sh.read_hex("Sys_Abnorm_Inf_Judgement")
        para1 = sh.read_int("UI_WIFI_Instruction.FromUI12_Para1")

        # 复位
        sh.write_float("DVL_Prase_Data.BD_Check", 0.0)
        sh.write_float("DVL_Prase_Data.BD_Height", 0.0)

        bit11_set = sys_val is not None and (sys_val & 0x800)
        para1_clamped = para1 is not None and para1 <= 15000

        if bit11_set and para1_clamped:
            self._pass("BUG-5 软限", f"Sys=0x{sys_val:08X} (Bit11✓), Para1={para1} (截断✓)")
        else:
            self._fail("BUG-5 软限", f"Sys=0x{sys_val or 0:08X}, Para1={para1} (预期 Bit11+Para1<=15000)")

    def _test_bug5_hard_limit(self):
        """BUG-5: DVL 硬限 Bit12 + Motor=350。"""
        print("[TEST] BUG-5: DVL 硬限...")
        sh = self.shell

        self._background_heartbeat(3.0)

        sh.write_int("Current_State.Current_Mode", 0xEE)
        sh.write_float("DVL_Prase_Data.BD_Check", 2.0)
        sh.write_float("DVL_Prase_Data.BD_Height", 1.2)
        sh.write_float("Current_State.Current_IMU_Pitch", 2.0)
        sh.write_float("Current_State.Current_DVL_Velocity_Kn", 3.0)

        sh.delay(2.0)

        sys_val = sh.read_hex("Sys_Abnorm_Inf_Judgement")
        motor1 = sh.read_int("Instruction_To_FMCU.McuFD_Motor1_Set_Speed")

        sh.write_float("DVL_Prase_Data.BD_Check", 0.0)
        sh.write_float("DVL_Prase_Data.BD_Height", 0.0)

        bit12_set = sys_val is not None and (sys_val & 0x1000)
        motor_ok = motor1 == 350

        if bit12_set and motor_ok:
            self._pass("BUG-5 硬限", f"Sys=0x{sys_val:08X} (Bit12✓), Motor1={motor1}")
        else:
            self._fail("BUG-5 硬限", f"Sys=0x{sys_val or 0:08X}, Motor1={motor1} (预期 Bit12+Motor=350)")

    def _test_bug6_dvl_lost(self):
        """BUG-6: DVL 丢底模式降级 + Bit13。"""
        print("[TEST] BUG-6: DVL 丢底自救 (需等 ~11s @2Hz)...")
        sh = self.shell

        # 持续发心跳防止 Jetson 失联
        self._background_heartbeat(13.0)

        sh.write_int("Current_State.Current_Mode", 0xEE)
        sh.write_int("UI_WIFI_Instruction.FromUI12_Ctrl_Mode", 0xEE)
        sh.write_float("Current_State.Current_Dep", 10.0)
        sh.write_float("Current_State.Current_IMU_Pitch", 0.0)
        sh.write_float("Current_State.Current_DVL_Velocity_Kn", 3.0)
        sh.write_float("DVL_Prase_Data.BD_Check", 0.0)

        sh.delay(11.0)

        sys_val = sh.read_hex("Sys_Abnorm_Inf_Judgement")
        ctrl_mode = sh.read_int("UI_WIFI_Instruction.FromUI12_Ctrl_Mode")
        motor1 = sh.read_int("Instruction_To_FMCU.McuFD_Motor1_Set_Speed")

        sh.write_float("DVL_Prase_Data.BD_Check", 2.0)

        bit13_set = sys_val is not None and (sys_val & 0x2000)
        mode_degraded = ctrl_mode == 0x01

        if bit13_set and mode_degraded:
            self._pass("BUG-6 DVL丢底", f"Sys=0x{sys_val:08X} (Bit13✓), Mode=0x{ctrl_mode:02X}, Motor1={motor1}")
        else:
            self._fail("BUG-6 DVL丢底", f"Sys=0x{sys_val or 0:08X}, Mode=0x{ctrl_mode or 0:02X} (预期 Bit13+Mode=0x01)")

    def _test_bug1_nan_defense(self):
        """BUG-1: NaN 防御 — 舵角不溢出。"""
        print("[TEST] BUG-1: NaN 防御...")
        sh = self.shell

        # 确保在 Jetson 模式
        self._background_heartbeat(2.0)
        sh.write_int("Current_State.Current_Mode", 0xEE)
        sh.write_int("UI_WIFI_Instruction.FromUI12_Ctrl_Mode", 0xEE)
        sh.write_int("Not_Recv_From_Jetson_No", 0)

        # 注入 NaN
        sh.write_nan("CourseCtrl_para1")
        sh.delay(0.3)

        uv = sh.read_int("Instruction_To_FMCU.McuFD_UV_Set_Rud_Location")
        lv = sh.read_int("Instruction_To_FMCU.McuFD_LV_Set_Rud_Location")

        # 恢复
        sh.write_float("CourseCtrl_para1", 2.0)

        uv_ok = uv is not None and 1800 < uv < 2300
        lv_ok = lv is not None and 1800 < lv < 2300

        if uv_ok and lv_ok:
            self._pass("BUG-1 NaN防御", f"UV={uv}, LV={lv} (中位附近, 未溢出)")
        elif uv is not None and (uv == 0 or uv >= 65000):
            self._fail("BUG-1 NaN防御", f"UV={uv}! u16 溢出! NaN 检测未生效")
        else:
            self._fail("BUG-1 NaN防御", f"UV={uv}, LV={lv} (预期 ~2048)")

    # ------ 交互式引导测试 ------

    def _guided_bug3(self):
        print("\n" + "-" * 40)
        print("  [引导] BUG-3: 深度计数器滑动窗口")
        print("-" * 40)
        print("  请在 VxWorks Shell 中依次执行:")
        print("  -> Depth_Exceed_FromUI12_Depth_Para1 = 0")
        print("  -> UI_WIFI_Instruction.FromUI12_Depth_Para1 = 5")
        print("  -> Current_State.Current_Dep = 10.0")
        print("  然后等待 5 秒...")
        input("  按 Enter 确认已执行并等待完毕...")
        print("  请读取计数器:")
        print("  -> printf(\"%d\\n\", Depth_Exceed_FromUI12_Depth_Para1)")
        val = input("  输入显示的数值 (预期≈10): ").strip()
        try:
            count_up = int(val)
        except ValueError:
            count_up = -1

        print("  现在执行:")
        print("  -> Current_State.Current_Dep = 1.0")
        print("  等待 5 秒后再次读取...")
        input("  按 Enter 确认...")
        print("  -> printf(\"%d\\n\", Depth_Exceed_FromUI12_Depth_Para1)")
        val = input("  输入显示的数值 (预期=0): ").strip()
        try:
            count_down = int(val)
        except ValueError:
            count_down = -1

        if count_up > 0 and count_down == 0:
            self._pass("BUG-3 滑动窗口(引导)", f"up={count_up}, down={count_down}")
        else:
            self._fail("BUG-3 滑动窗口(引导)", f"up={count_up}, down={count_down}")

    def _guided_bug4(self):
        print("\n" + "-" * 40)
        print("  [引导] BUG-4: 超深自救验证")
        print("-" * 40)
        print("  请在 VxWorks Shell 中执行:")
        print("  -> Depth_Exceed_FromUI12_Depth_Para1 = 12")
        print("  -> UI_WIFI_Instruction.FromUI12_Depth_Para1 = 5")
        print("  -> Current_State.Current_Dep = 10.0")
        print("  -> taskDelay(sysClkRateGet()/2)")
        print("  -> printf(\"%d\\n\", Instruction_To_FMCU.McuFD_Motor1_Set_Speed)")
        input("  按 Enter 确认已执行...")
        val = input("  Motor1 值 (预期=300): ").strip()
        try:
            motor1 = int(val)
        except ValueError:
            motor1 = -1

        if motor1 == 300:
            self._pass("BUG-4 超深自救(引导)", f"Motor1={motor1}")
        elif motor1 == 0:
            self._fail("BUG-4 超深自救(引导)", "Motor1=0! 旧 bug 仍在!")
        else:
            self._fail("BUG-4 超深自救(引导)", f"Motor1={motor1} (预期 300)")

    def _guided_bug5_soft(self):
        print("\n" + "-" * 40)
        print("  [引导] BUG-5: DVL 软限")
        print("-" * 40)
        print("  请在 VxWorks Shell 中执行:")
        print("  -> Current_State.Current_Mode = 0xEE")
        print("  -> UI_WIFI_Instruction.FromUI12_Ctrl_Mode = 0xEE")
        print("  -> UI_WIFI_Instruction.FromUI12_Para1 = 20000")
        print("  -> Current_State.Current_Dep = 15.0")
        print("  -> DVL_Prase_Data.BD_Check = 2.0")
        print("  -> DVL_Prase_Data.BD_Height = 2.5")
        print("  -> taskDelay(sysClkRateGet()*3)")
        print("  -> printf(\"0x%08x\\n\", Sys_Abnorm_Inf_Judgement)")
        print("  -> printf(\"%d\\n\", UI_WIFI_Instruction.FromUI12_Para1)")
        input("  按 Enter 确认已执行...")
        sys_str = input("  Sys_Abnorm 值 (预期含 0x800): ").strip()
        para1_str = input("  Para1 值 (预期=15000): ").strip()

        try:
            sys_val = int(sys_str, 16) if sys_str.startswith("0x") else int(sys_str)
            para1 = int(para1_str)
        except ValueError:
            sys_val, para1 = 0, -1

        if (sys_val & 0x800) and para1 <= 15000:
            self._pass("BUG-5 软限(引导)", f"Sys=0x{sys_val:08X}, Para1={para1}")
        else:
            self._fail("BUG-5 软限(引导)", f"Sys=0x{sys_val:08X}, Para1={para1}")

    def _guided_bug5_hard(self):
        print("\n" + "-" * 40)
        print("  [引导] BUG-5: DVL 硬限")
        print("-" * 40)
        print("  请在 VxWorks Shell 中执行:")
        print("  -> DVL_Prase_Data.BD_Height = 1.2")
        print("  -> Current_State.Current_IMU_Pitch = 2.0")
        print("  -> Current_State.Current_DVL_Velocity_Kn = 3.0")
        print("  -> taskDelay(sysClkRateGet()*2)")
        print("  -> printf(\"%d\\n\", Instruction_To_FMCU.McuFD_Motor1_Set_Speed)")
        print("  -> printf(\"0x%08x\\n\", Sys_Abnorm_Inf_Judgement)")
        input("  按 Enter 确认已执行...")
        motor_str = input("  Motor1 值 (预期=350): ").strip()
        sys_str = input("  Sys_Abnorm 值 (预期含 0x1000): ").strip()

        try:
            motor1 = int(motor_str)
            sys_val = int(sys_str, 16) if sys_str.startswith("0x") else int(sys_str)
        except ValueError:
            motor1, sys_val = -1, 0

        if motor1 == 350 and (sys_val & 0x1000):
            self._pass("BUG-5 硬限(引导)", f"Motor1={motor1}, Sys=0x{sys_val:08X}")
        else:
            self._fail("BUG-5 硬限(引导)", f"Motor1={motor1}, Sys=0x{sys_val:08X}")

    def _guided_bug6_dvl_lost(self):
        print("\n" + "-" * 40)
        print("  [引导] BUG-6: DVL 丢底自救")
        print("-" * 40)
        print("  ⚠ 此测试需要等待 ~11s (DVL 丢底超时 @2Hz)")
        print("  请在 VxWorks Shell 中执行:")
        print("  -> Not_Recv_From_Jetson_No = 0")
        print("  -> Current_State.Current_Mode = 0xEE")
        print("  -> UI_WIFI_Instruction.FromUI12_Ctrl_Mode = 0xEE")
        print("  -> Current_State.Current_Dep = 10.0")
        print("  -> DVL_Prase_Data.BD_Check = 0.0")
        print("  -> taskDelay(sysClkRateGet()*11)")
        print("  -> printf(\"0x%08x\\n\", Sys_Abnorm_Inf_Judgement)")
        print("  -> printf(\"0x%02x\\n\", UI_WIFI_Instruction.FromUI12_Ctrl_Mode)")
        print("  ⚠ 注意: 每隔 0.5s 需要清零 Not_Recv_From_Jetson_No 防止 Jetson 看门狗抢先触发!")
        print("     或者先设置 Current_State.Current_Mode = 0x01 (非 Jetson 模式) 来绕过")
        input("  按 Enter 确认已执行...")
        sys_str = input("  Sys_Abnorm 值 (预期含 0x2000): ").strip()
        mode_str = input("  CtrlMode 值 (预期=0x01): ").strip()

        try:
            sys_val = int(sys_str, 16) if sys_str.startswith("0x") else int(sys_str)
            mode_val = int(mode_str, 16) if mode_str.startswith("0x") else int(mode_str)
        except ValueError:
            sys_val, mode_val = 0, -1

        if (sys_val & 0x2000) and mode_val == 0x01:
            self._pass("BUG-6 DVL丢底(引导)", f"Sys=0x{sys_val:08X}, Mode=0x{mode_val:02X}")
        else:
            self._fail("BUG-6 DVL丢底(引导)", f"Sys=0x{sys_val:08X}, Mode=0x{mode_val:02X}")

    def _guided_bug1_nan(self):
        print("\n" + "-" * 40)
        print("  [引导] BUG-1: NaN 防御")
        print("-" * 40)
        print("  请在 VxWorks Shell 中执行:")
        print("  -> Current_State.Current_Mode = 0xEE")
        print("  -> UI_WIFI_Instruction.FromUI12_Ctrl_Mode = 0xEE")
        print("  -> Not_Recv_From_Jetson_No = 0")
        print("  -> *((unsigned int *)&CourseCtrl_para1) = 0x7fc00000")
        print("  -> taskDelay(sysClkRateGet()/10)")
        print("  -> printf(\"%d %d\\n\", Instruction_To_FMCU.McuFD_UV_Set_Rud_Location, Instruction_To_FMCU.McuFD_LV_Set_Rud_Location)")
        print("  -> CourseCtrl_para1 = 2.0")
        input("  按 Enter 确认已执行...")
        val = input("  UV LV 值 (预期 2048 2048): ").strip()
        parts = val.split()
        try:
            uv = int(parts[0])
            lv = int(parts[1]) if len(parts) > 1 else int(parts[0])
        except (ValueError, IndexError):
            uv, lv = -1, -1

        if 1800 < uv < 2300 and 1800 < lv < 2300:
            self._pass("BUG-1 NaN防御(引导)", f"UV={uv}, LV={lv}")
        elif uv == 0 or uv >= 65000:
            self._fail("BUG-1 NaN防御(引导)", f"UV={uv}! u16 溢出!")
        else:
            self._fail("BUG-1 NaN防御(引导)", f"UV={uv}, LV={lv}")

    # ------ 辅助 ------

    def _background_heartbeat(self, duration: float):
        """后台持续发送心跳, 防止 Jetson 看门狗在测试期间触发。"""
        def _send():
            t0 = time.time()
            while time.time() - t0 < duration:
                self.udp.send_heartbeat(ctrl_mode=0xEE, motor_speed1=300)
                time.sleep(0.1)
        threading.Thread(target=_send, daemon=True).start()

    def _pass(self, name: str, detail: str):
        print(f"  ✓ PASS: {name}")
        if detail:
            for line in detail.split("\n"):
                print(f"          {line}")
        self.results.append(TestResult(name, True, detail))

    def _fail(self, name: str, detail: str):
        print(f"  ✗ FAIL: {name}")
        if detail:
            for line in detail.split("\n"):
                print(f"          {line}")
        self.results.append(TestResult(name, False, detail))

    def _print_summary(self):
        print("\n" + "=" * 60)
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)
        print(f"  结果: {passed}/{total} 通过")
        if passed < total:
            print("  失败项:")
            for r in self.results:
                if not r.passed:
                    print(f"    ✗ {r.name}: {r.detail}")
        print("=" * 60)


# ---------------------------------------------------------------------------
# 主程序
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VxWorks 深度安全修复 HIL 自动化验证",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
模式说明:
  auto-udp  纯 UDP 验证 (无需 Shell, 验证通信通路/心跳/失联)
  guided    交互式引导 (脚本提示操作, 你在 Shell 中执行, 脚本验证结果)
  telnet    全自动 (需 VxWorks telnetd, 脚本自动注入+验证)

示例:
  python scripts/vxworks_safety_hil.py --mode auto-udp
  python scripts/vxworks_safety_hil.py --mode guided
  python scripts/vxworks_safety_hil.py --mode telnet --host 192.168.0.101 --telnet-user target --telnet-password password
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["auto-udp", "guided", "telnet"],
        default="guided",
        help="运行模式 (默认: guided)",
    )
    parser.add_argument(
        "--host",
        default=VXWORKS_IP,
        help=f"VxWorks IP 地址 (默认: {VXWORKS_IP})",
    )
    parser.add_argument(
        "--bind",
        default="0.0.0.0",
        help="本地绑定地址 (默认: 0.0.0.0)",
    )
    parser.add_argument(
        "--uplink-port",
        type=int,
        default=UPLINK_PORT,
        help=f"$AUV 上行状态帧监听端口 (默认: {UPLINK_PORT}, 对齐 compose 的 21/udp)",
    )
    parser.add_argument(
        "--log-port",
        type=int,
        default=LOG_PORT,
        help=f"UdpLogger 日志监听端口 (默认: {LOG_PORT})",
    )
    parser.add_argument(
        "--telnet-port",
        type=int,
        default=23,
        help="Telnet 端口 (默认: 23)",
    )
    parser.add_argument(
        "--telnet-user",
        default="target",
        help="Telnet 用户名 (默认: target)",
    )
    parser.add_argument(
        "--telnet-password",
        default="password",
        help="Telnet 密码 (默认: password)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    print("╔══════════════════════════════════════════════════╗")
    print("║  VxWorks Safety HIL Automation                  ║")
    print(f"║  Mode: {args.mode:<10}  Target: {args.host:<15} ║")
    print("╚══════════════════════════════════════════════════╝")

    # 初始化 UDP 收发
    try:
        udp = UDPTransceiver(
            vxworks_ip=args.host,
            bind_ip=args.bind,
            uplink_port=args.uplink_port,
            log_port=args.log_port,
        )
        udp.start()
    except OSError as e:
        print(f"[ERROR] UDP 初始化失败: {e}")
        print(f"  提示: 确保端口 {args.uplink_port}/{args.log_port} 未被占用 (关闭其他 sniffer/log_receiver)")
        return 1

    shell = None

    if args.mode == "telnet":
        print(f"\n连接 Telnet: {args.host}:{args.telnet_port} (user={args.telnet_user})...")
        shell = VxWorksShell(
            args.host,
            args.telnet_port,
            username=args.telnet_user,
            password=args.telnet_password,
        )
        if not shell.connect():
            print("  Telnet 连接失败, 回退到 guided 模式")
            args.mode = "guided"
            shell = None
        else:
            print("  Telnet 连接成功!")

    suite = HILTestSuite(udp, shell)

    try:
        if args.mode == "auto-udp":
            suite.run_all_auto_udp()
        elif args.mode == "guided":
            suite.run_guided()
        elif args.mode == "telnet":
            suite.run_all_telnet()
    except KeyboardInterrupt:
        print("\n\n  中断退出")
    finally:
        udp.stop()
        if shell:
            shell.close()

    failed = sum(1 for r in suite.results if not r.passed)
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
