#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[TEST] 测试 /auv/state/filtered 等待机制"
echo ""

# 检查ROS2环境
if ! command -v ros2 &> /dev/null; then
    echo "[TEST][ERROR] ROS2 不可用，请先source ROS2环境"
    exit 1
fi

echo "[TEST] ROS2 环境已就绪"
echo ""

# 检查当前是否有运行中的节点
echo "[TEST] 检查当前运行的ROS2节点..."
NODE_COUNT=$(ros2 node list 2>/dev/null | wc -l || echo "0")
echo "[TEST] 当前运行节点数: $NODE_COUNT"
echo ""

if [[ $NODE_COUNT -eq 0 ]]; then
    echo "[TEST][INFO] 没有运行中的节点，等待机制将在节点启动时工作"
    echo "[TEST][INFO] 要测试等待机制，请先启动AUV栈："
    echo "  bash $ROOT_DIR/scripts/start_foxglove_holoocean_ros.sh --brain-mode stack"
    echo ""
    echo "[TEST][INFO] 然后在另一个终端运行此脚本进行验证"
    exit 0
fi

# 检查关键话题
echo "[TEST] 检查关键话题..."
TOPICS=("/auv/state/filtered" "/auv/diagnostics" "/auv/sensors/imu" "/auv/sensors/dvl" "/auv/sensors/depth")

for topic in "${TOPICS[@]}"; do
    if timeout 2 ros2 topic list | grep -q "$topic"; then
        PUB_COUNT=$(timeout 2 ros2 topic info "$topic" 2>/dev/null | grep "Publisher count:" | awk '{print $3}' || echo "0")
        SUB_COUNT=$(timeout 2 ros2 topic info "$topic" 2>/dev/null | grep "Subscription count:" | awk '{print $3}' || echo "0")
        echo "  ✓ $topic (发布者: $PUB_COUNT, 订阅者: $SUB_COUNT)"
    else
        echo "  ✗ $topic (不存在)"
    fi
done

echo ""
echo "[TEST] 完成。如果所有关键话题都显示 ✓，说明系统状态良好。"
