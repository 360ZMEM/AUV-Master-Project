"""
深度诊断PVS后端DVL速度定义与坐标系问题

目标：
1. 分析nu[0:3]的实际含义（body速度 vs world速度）
2. 验证Rzyx旋转矩阵的正确性
3. 找出DVL速度方向与真值运动方向相反的原因
"""

import numpy as np
import sys
from pathlib import Path
import mcap.reader
# from scipy.spatial.transform import Rotation as R

# 添加PVS路径
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PVS_ROOT = PROJECT_ROOT.parent / "PythonVehicleSimulator-master" / "src"
if str(PVS_ROOT) not in sys.path:
    sys.path.insert(0, str(PVS_ROOT))

from python_vehicle_simulator.lib.gnc import Rzyx

def test_Rzyx_definition():
    """测试Rzyx函数的定义"""
    print("="*80)
    print("测试1: 验证Rzyx旋转矩阵定义")
    print("="*80)
    
    # 测试纯yaw旋转（无roll/pitch）
    roll, pitch, yaw = 0.0, 0.0, np.pi/4  # 45度yaw
    R_body_to_ned = Rzyx(roll, pitch, yaw)
    
    print(f"\n输入: roll={roll}, pitch={pitch}, yaw={yaw} (45°)")
    print(f"Rzyx(roll, pitch, yaw) = \n{R_body_to_ned}")
    
    # 测试：body系x轴速度(1,0,0)经过旋转后应该是什么？
    v_body = np.array([1.0, 0.0, 0.0])
    v_ned = R_body_to_ned @ v_body
    print(f"\nBody速度 {v_body} 经过旋转后 -> NED速度: {v_ned}")
    
    # 对比scipy的ZYX欧拉角（需要scipy库，暂时注释）
    # scipy使用Rotation.from_euler('ZYX', [yaw, pitch, roll])
    # 注意：scipy的欧拉角顺序是ZYX = yaw-pitch-roll
    # R_scipy = R.from_euler('ZYX', [yaw, pitch, roll])
    # v_ned_scipy = R_scipy.apply(v_body)
    # print(f"Scipy ZYX旋转 -> NED速度: {v_ned_scipy}")
    # 
    # # 验证是否一致
    # if np.allclose(v_ned, v_ned_scipy, atol=1e-10):
    #     print("✓ Rzyx与Scipy ZYX一致")
    # else:
    #     print("✗ Rzyx与Scipy ZYX不一致！")
    
    # 关键测试：当yaw=0时，body前向速度应该对应NED的x轴
    roll, pitch, yaw = 0.0, 0.0, 0.0
    R_body_to_ned = Rzyx(roll, pitch, yaw)
    v_body = np.array([1.0, 0.0, 0.0])
    v_ned = R_body_to_ned @ v_body
    print(f"\n当yaw=0时，Body前向速度 {v_body} -> NED: {v_ned}")
    print("预期: [1.0, 0.0, 0.0] (NED X轴=北)")
    
    return Rzyx

def read_mcap_velocity_comparison(mcap_file):
    """读取MCAP文件，比较不同速度定义"""
    print("\n" + "="*80)
    print("测试2: 从MCAP读取真值和DVL速度进行对比")
    print("="*80)
    
    mcap_path = Path(mcap_file)
    if not mcap_path.exists():
        print(f"MCAP文件不存在: {mcap_file}")
        return
    
    # 读取话题
    truth_topic = "/truth_marker"
    dvl_topic = "/auv/dvl"
    truth_positions = []
    dvl_velocities = []
    truth_times = []
    dvl_times = []
    
    with open(mcap_file, "rb") as f:
        reader = mcap.reader.make_reader(f)
        for schema, channel, message in reader.iter_messages():
            if channel.topic == truth_topic:
                # 解析PositionStamped
                import struct
                stamp_sec = struct.unpack('<i', message.data[0:4])[0]
                stamp_nsec = struct.unpack('<i', message.data[4:8])[0]
                ts = stamp_sec + stamp_nsec / 1e9
                
                x = struct.unpack('<d', message.data[8:16])[0]
                y = struct.unpack('<d', message.data[16:24])[0]
                z = struct.unpack('<d', message.data[24:32])[0]
                
                truth_positions.append([x, y, z])
                truth_times.append(ts)
                
            elif channel.topic == dvl_topic:
                # 解析DVL速度
                import struct
                stamp_sec = struct.unpack('<i', message.data[0:4])[0]
                stamp_nsec = struct.unpack('<i', message.data[4:8])[0]
                ts = stamp_sec + stamp_nsec / 1e9
                
                vx = struct.unpack('<d', message.data[8:16])[0]
                vy = struct.unpack('<d', message.data[16:24])[0]
                vz = struct.unpack('<d', message.data[24:32])[0]
                
                dvl_velocities.append([vx, vy, vz])
                dvl_times.append(ts)
    
    if len(truth_positions) < 2:
        print("没有足够的真值数据")
        return
    
    truth_positions = np.array(truth_positions)
    dvl_velocities = np.array(dvl_velocities)
    truth_times = np.array(truth_times)
    dvl_times = np.array(dvl_times)
    
    # 计算真值的平均速度
    dt_truth = truth_times[-1] - truth_times[0]
    total_displacement = truth_positions[-1] - truth_positions[0]
    avg_velocity_truth = total_displacement / dt_truth if dt_truth > 0 else np.zeros(3)
    
    # DVL平均速度
    avg_velocity_dvl = np.mean(dvl_velocities, axis=0)
    
    print(f"\n真值分析:")
    print(f"  时间跨度: {dt_truth:.2f}s")
    print(f"  总位移: {total_displacement}")
    print(f"  平均速度(真值): {avg_velocity_truth}")
    
    print(f"\nDVL分析:")
    print(f"  样本数: {len(dvl_velocities)}")
    print(f"  平均速度(DVL): {avg_velocity_dvl}")
    
    # 关键：速度方向是否一致？
    for i, axis_name in enumerate(['X(北)', 'Y(东)', 'Z(下)']):
        truth_dir = "正" if avg_velocity_truth[i] > 0 else "负"
        dvl_dir = "正" if avg_velocity_dvl[i] > 0 else "负"
        match = "✓" if (avg_velocity_truth[i] * avg_velocity_dvl[i] > 0) else "✗ 方向相反！"
        print(f"  {axis_name}: 真值{truth_dir}({avg_velocity_truth[i]:.3f}), DVL{dvl_dir}({avg_velocity_dvl[i]:.3f}) {match}")
    
    # 如果DVL是body速度，需要知道姿态角才能比较
    # 但从平均值来看，如果AUV主要在yaw=0方向运动，body前向速度应该对应NED X正向
    # 如果真值X减小，说明AUV实际向南运动，但DVL的X速度为正（向北），这就是矛盾

def analyze_pvs_velocity_convention():
    """分析PVS后端的速度定义"""
    print("\n" + "="*80)
    print("测试3: 分析PVS后端的速度定义")
    print("="*80)
    
    print("""
PVS后端中的nu向量定义：
- nu[0:3]: 线速度 [u, v, w] 
- nu[3:6]: 角速度 [p, q, r]

关键问题：nu[0:3]是BODY坐标系速度还是WORLD坐标系速度？

根据PVS文档和海洋载具动力学标准：
- nu[0:3] = [u, v, w] 是BODY坐标系速度（相对于载体的前、右、下方向）
- eta[0:3] = [x, y, z] 是WORLD坐标系位置

因此，需要旋转矩阵将body速度转换到world NED：
  v_world = R(eta[3:6]) @ v_body

但问题是：Rzyx(roll, pitch, yaw)是否正确？
""")
    
    # 测试：当AUV向下看(pitch=90度)时
    roll, pitch, yaw = 0.0, np.pi/2, 0.0
    R_b2n = Rzyx(roll, pitch, yaw)
    v_body = np.array([1.0, 0.0, 0.0])  # body前向速度
    v_ned = R_b2n @ v_body
    print(f"\n当pitch=90°(AUV向下看)时:")
    print(f"  Body前向速度 [1,0,0] -> NED: {v_ned}")
    print(f"  预期: [0, 0, 1] (因为前向变成了向下)")
    
    # 测试：当AUV向右滚(roll=90度)时
    roll, pitch, yaw = np.pi/2, 0.0, 0.0
    R_b2n = Rzyx(roll, pitch, yaw)
    v_body = np.array([1.0, 0.0, 0.0])
    v_ned = R_b2n @ v_body
    print(f"\n当roll=90°(AUV向右滚)时:")
    print(f"  Body前向速度 [1,0,0] -> NED: {v_ned}")
    print(f"  预期: [1, 0, 0] (前向不变)")

def read_mcap_with_rpy(mcap_file):
    """读取包含姿态角的MCAP数据"""
    print("\n" + "="*80)
    print("测试4: 读取姿态角和速度数据进行完整分析")
    print("="*80)
    
    try:
        import struct
        
        truth_positions = []
        dvl_velocities = []
        
        with open(mcap_file, "rb") as f:
            reader = mcap.reader.make_reader(f)
            for schema, channel, message in reader.iter_messages():
                if channel.topic == "/truth_marker":
                    # 解析: stamp(8B) + position(24B)
                    stamp_sec = struct.unpack('<i', message.data[0:4])[0]
                    stamp_nsec = struct.unpack('<i', message.data[4:8])[0]
                    ts = stamp_sec + stamp_nsec / 1e9
                    
                    x = struct.unpack('<d', message.data[8:16])[0]
                    y = struct.unpack('<d', message.data[16:24])[0]
                    z = struct.unpack('<d', message.data[24:32])[0]
                    
                    truth_positions.append((ts, [x, y, z]))
                    
                elif channel.topic == "/auv/dvl":
                    # 解析: stamp(8B) + velocity(24B)
                    stamp_sec = struct.unpack('<i', message.data[0:4])[0]
                    stamp_nsec = struct.unpack('<i', message.data[4:8])[0]
                    ts = stamp_sec + stamp_nsec / 1e9
                    
                    vx = struct.unpack('<d', message.data[8:16])[0]
                    vy = struct.unpack('<d', message.data[16:24])[0]
                    vz = struct.unpack('<d', message.data[24:32])[0]
                    
                    dvl_velocities.append((ts, [vx, vy, vz]))
        
        if len(truth_positions) < 10:
            print("数据不足")
            return
        
        # 打印前10个数据点
        print("\n前10个真值数据点:")
        for i, (ts, pos) in enumerate(truth_positions[:10]):
            print(f"  t={ts:.3f}: pos={pos}")
        
        print("\n前10个DVL速度数据点:")
        for i, (ts, vel) in enumerate(dvl_velocities[:10]):
            print(f"  t={ts:.3f}: vel={vel}")
        
        # 计算真值位移
        pos0 = np.array(truth_positions[0][1])
        pos1 = np.array(truth_positions[1][1])
        dt = truth_positions[1][0] - truth_positions[0][0]
        actual_velocity = (pos1 - pos0) / dt if dt > 0 else np.zeros(3)
        
        # 对应时间的DVL速度
        ts_truth1 = truth_positions[1][0]
        dvl_at_truth1 = None
        for ts_dvl, vel_dvl in dvl_velocities:
            if abs(ts_dvl - ts_truth1) < 0.01:
                dvl_at_truth1 = vel_dvl
                break
        
        print(f"\n速度对比 (t={truth_positions[1][0]:.3f}):")
        print(f"  真值速度(从位移计算): {actual_velocity}")
        if dvl_at_truth1:
            print(f"  DVL报告速度: {dvl_at_truth1}")
            
            # 检查方向
            for i, axis in enumerate(['X(北)', 'Y(东)', 'Z(下)']):
                truth_dir = "正" if actual_velocity[i] > 0 else "负"
                dvl_dir = "正" if dvl_at_truth1[i] > 0 else "负"
                match = "✓" if (actual_velocity[i] * dvl_at_truth1[i] > 0) else "✗ 方向相反！"
                print(f"    {axis}: 真值{truth_dir}, DVL{dvl_dir} {match}")
        else:
            print("  未找到对应时间的DVL数据")
        
    except Exception as e:
        print(f"读取MCAP失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    import sys
    
    # 测试1: Rzyx定义
    test_Rzyx_definition()
    
    # 测试2: PVS速度定义分析
    analyze_pvs_velocity_convention()
    
    # 测试3和4: 从MCAP读取数据
    if len(sys.argv) > 1:
        mcap_file = sys.argv[1]
        read_mcap_velocity_comparison(mcap_file)
        read_mcap_with_rpy(mcap_file)
    else:
        print("\n用法: python3 debug_dvl_velocity.py <mcap_file>")
