#!/bin/bash
# 录制PVS后端60秒MCAP数据

set -e

# 设置环境变量
export PVS_SIMULATION=true
export SIMULATION_DURATION=65
export PVS_BACKEND=true
export ENABLE_RECORDING=true
export MCAP_OUTPUT_DIR="/tmp/mcap_recordings"

mkdir -p "$MCAP_OUTPUT_DIR"

# 生成时间戳
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
MCAP_FILE="${MCAP_OUTPUT_DIR}/pvs_60s_dvl_fix_${TIMESTAMP}.mcap"

echo "========================================="
echo "PVS后端 60s MCAP录制（DVL坐标修复后）"
echo "========================================="
echo "输出文件: ${MCAP_FILE}"
echo ""

# 启动录制
cd /home/auv_user/auv_ws/AUV-Master-Project

# 先清理旧进程
pkill -f "ros2 run auv_localization" 2>/dev/null || true
pkill -f "ros2 run auv_bridge" 2>/dev/null || true
pkill -f "mcap record" 2>/dev/null || true
sleep 2

# 启动ROS2环境
source /opt/ros/humble/setup.bash
source install/setup.bash

# 启动录制
ros2 run mcap_recorder mcap_recorder_node --output "${MCAP_FILE}" &
MCAP_PID=$!
sleep 2

# 启动节点
ros2 run auv_bridge bridge_node &
BRIDGE_PID=$!
sleep 2

ros2 run auv_localization auv_localization_node &
LOCALIZATION_PID=$!
sleep 2

echo "等待${SIMULATION_DURATION}秒..."
sleep ${SIMULATION_DURATION}

echo "停止录制..."
kill ${MCAP_PID} 2>/dev/null || true
kill ${BRIDGE_PID} 2>/dev/null || true
kill ${LOCALIZATION_PID} 2>/dev/null || true

sleep 3

# 验证文件
if [ -f "${MCAP_FILE}" ]; then
    FILESIZE=$(du -h "${MCAP_FILE}" | cut -f1)
    echo "✓ MCAP文件录制完成: ${MCAP_FILE} (${FILESIZE})"
else
    echo "✗ MCAP文件录制失败"
    exit 1
fi

echo ""
echo "录制完成！"
