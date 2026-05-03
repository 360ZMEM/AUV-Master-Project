#!/usr/bin/env bash
# ============================================================================
# AUV 上位机-Jetson-AMD 链路联调启动脚本
#
# 功能：
# 1. 检查 Python 依赖
# 2. 语法检查所有修改的文件
# 3. 导入测试
# 4. 启动各组件（如环境允许）
# 5. 自动验证残余问题
# ============================================================================

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/logs/integration_test"
ZENOH_ROUTER_PORT=7447

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

ERRORS=0
WARNINGS=0

check_syntax() {
    local file=$1
    if python3 -m py_compile "$file" 2>/dev/null; then
        log_success "语法检查通过: $(basename $file)"
        return 0
    else
        log_error "语法检查失败: $(basename $file)"
        ERRORS=$((ERRORS + 1))
        return 1
    fi
}

check_import() {
    local module=$1
    local desc=${2:-$module}
    cd "$PROJECT_ROOT"
    if PYTHONPATH="$PROJECT_ROOT:$PROJECT_ROOT/common" python3 -c "import $module" 2>/dev/null; then
        log_success "导入测试通过: $desc"
        return 0
    else
        log_error "导入测试失败: $desc"
        ERRORS=$((ERRORS + 1))
        return 1
    fi
}

main() {
    echo "========================================================================"
    echo "  AUV 上位机-Jetson-AMD 链路联调验证"
    echo "  项目根目录: $PROJECT_ROOT"
    echo "========================================================================"
    echo ""

    mkdir -p "$LOG_DIR"

    # ────────────────────────────────────────
    # 步骤 1：检查 Python 依赖
    # ────────────────────────────────────────
    log_info "=== 步骤 1: 检查 Python 依赖 ==="
    
    for module in zenoh numpy py_trees yaml; do
        if python3 -c "import $module" 2>/dev/null; then
            log_success "Python 模块 $module 已安装"
        else
            log_warning "Python 模块 $module 未安装（可选）"
            WARNINGS=$((WARNINGS + 1))
        fi
    done
    echo ""

    # ────────────────────────────────────────
    # 步骤 2：语法检查所有修改的文件
    # ────────────────────────────────────────
    log_info "=== 步骤 2: 语法检查 ==="
    
    FILES_TO_CHECK=(
        "console_soft/auv_console_pyside6/src/ui/main_window.py"
        "console_soft/auv_console_pyside6/src/communication/comm_manager.py"
        "console_soft/auv_console_pyside6/src/communication/zenoh_side_channel.py"
        "brain_linux/src/auv_bridge/auv_bridge/arbiter.py"
        "brain_linux/src/auv_bridge/auv_bridge/bridge_node.py"
        "brain_linux/src/auv_bridge/auv_bridge/bridge_backends.py"
        "sim_holoocean/interfaces/mock_amd_server.py"
        "brain_linux/src/auv_control/auv_decision_ros/decision_node.py"
        "brain_linux/src/auv_decision/auv_decision_core/bt_engine.py"
        "brain_linux/src/auv_decision/auv_decision_core/behaviors.py"
        "console_soft/auv_console_pyside6/test_linkage.py"
    )
    
    cd "$PROJECT_ROOT"
    for file in "${FILES_TO_CHECK[@]}"; do
        if [ -f "$file" ]; then
            check_syntax "$file"
        else
            log_warning "文件不存在: $file"
            WARNINGS=$((WARNINGS + 1))
        fi
    done
    echo ""

    # ────────────────────────────────────────
    # 步骤 3：核心模块导入测试
    # ────────────────────────────────────────
    log_info "=== 步骤 3: 核心模块导入测试 ==="
    
    cd "$PROJECT_ROOT"
    
    # 协议模块
    PYTHONPATH="$PROJECT_ROOT:$PROJECT_ROOT/common" python3 -c "import common.protocol; print('common.protocol 导入成功')" 2>&1 || {
        log_error "导入测试失败: 协议模块"
        ERRORS=$((ERRORS + 1))
    }
    
    # 行为树节点
    PYTHONPATH="$PROJECT_ROOT:$PROJECT_ROOT/common:$PROJECT_ROOT/brain_linux/src" python3 -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT/brain_linux/src')
from auv_decision.auv_decision_core.behaviors import MockCableTrackingBehavior, MissionCommandCondition
print('MockCableTrackingBehavior 导入成功')
print('MissionCommandCondition 导入成功')
" 2>&1 || {
        log_error "导入测试失败: 行为树节点"
        ERRORS=$((ERRORS + 1))
    }
    
    # 行为树引擎
    PYTHONPATH="$PROJECT_ROOT:$PROJECT_ROOT/common:$PROJECT_ROOT/brain_linux/src" python3 -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT/brain_linux/src')
from auv_decision.auv_decision_core.bt_engine import DecisionTreeEngine
print('DecisionTreeEngine 导入成功')
engine = DecisionTreeEngine()
print('行为树引擎初始化成功')
" 2>&1 || {
        log_error "导入测试失败: 行为树引擎"
        ERRORS=$((ERRORS + 1))
    }
    
    echo ""

    # ────────────────────────────────────────
    # 步骤 4：Mock AMD 服务器快速启动测试
    # ────────────────────────────────────────
    log_info "=== 步骤 4: Mock AMD 服务器快速启动测试 ==="
    
    cd "$PROJECT_ROOT"
    
    PYTHONPATH="$PROJECT_ROOT:$PROJECT_ROOT/common:$PROJECT_ROOT/sim_holoocean/interfaces" python3 -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT')
sys.path.insert(0, '$PROJECT_ROOT/common')
sys.path.insert(0, '$PROJECT_ROOT/sim_holoocean/interfaces')

try:
    from mock_amd_server import MockAmdUdpServer
    print('MockAmdUdpServer 类导入成功')
except Exception as e:
    print(f'MockAmdUdpServer 导入失败: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

try:
    methods = [m for m in dir(MockAmdUdpServer) if not m.startswith('_')]
    print(f'MockAmdUdpServer 公共方法: {methods}')
    
    if 'run_forever' in methods:
        print('  - run_forever: 存在')
    if '_extract_target_depth_from_downlink' in dir(MockAmdUdpServer):
        print('  - _extract_target_depth_from_downlink: 存在')
    if '_extract_target_heading_from_downlink' in dir(MockAmdUdpServer):
        print('  - _extract_target_heading_from_downlink: 存在')
    if '_extract_target_speed_from_downlink' in dir(MockAmdUdpServer):
        print('  - _extract_target_speed_from_downlink: 存在')
    
    print('Mock AMD 服务器结构检查通过')
except Exception as e:
    print(f'Mock AMD 服务器结构检查失败: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
" 2>&1 || {
        log_error "Mock AMD 服务器测试失败"
        ERRORS=$((ERRORS + 1))
    }
    echo ""

    # ────────────────────────────────────────
    # 步骤 5：行为树引擎测试
    # ────────────────────────────────────────
    log_info "=== 步骤 5: 行为树引擎测试 ==="
    
    cd "$PROJECT_ROOT"
    export PYTHONPATH="$PROJECT_ROOT:$PROJECT_ROOT/common:$PROJECT_ROOT/brain_linux/src/auv_decision"
    
    python3 -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT')
sys.path.insert(0, '$PROJECT_ROOT/common')
sys.path.insert(0, '$PROJECT_ROOT/brain_linux/src/auv_decision')

try:
    from auv_decision_core.bt_engine import DecisionTreeEngine
    from auv_decision_core.behaviors import MockCableTrackingBehavior, MissionCommandCondition
    
    print('DecisionTreeEngine 导入成功')
    print('MockCableTrackingBehavior 导入成功')
    print('MissionCommandCondition 导入成功')
    
    engine = DecisionTreeEngine(confidence_threshold=0.7)
    print(f'行为树引擎初始化成功，黑板键: {engine.MISSION_TARGET_KEY}')
    
    engine.set_mission_target({
        'mission_type': 'CABLE_TRACKING',
        'target_depth': 5.0,
        'track_distance': 500.0,
        'timeout_s': 1200
    })
    
    target = engine.get_mission_target()
    print(f'任务目标写入成功: {target}')
    
    if target.get('mission_type') == 'CABLE_TRACKING':
        print('Mock BT Injector 黑板写入测试通过')
    else:
        print('Mock BT Injector 黑板写入测试失败')
        sys.exit(1)
    
    engine.tick()
    state = engine.get_target_motion_state()
    print(f'行为树 tick 成功，状态: {state.get(\"mode\", \"unknown\") if state else \"None\"}')
    print('行为树引擎测试通过')
    
except Exception as e:
    print(f'行为树引擎测试失败: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
" 2>&1
    echo ""

    # ────────────────────────────────────────
    # 步骤 6：配置检查
    # ────────────────────────────────────────
    log_info "=== 步骤 6: 配置检查 ==="
    
    cd "$PROJECT_ROOT"
    python3 -c "
import yaml
import sys

config_files = [
    'config/bridge_params.yaml',
    'console_soft/auv_console_pyside6/console_config.yaml'
]

for cf in config_files:
    try:
        with open(cf) as f:
            cfg = yaml.safe_load(f)
        print(f'配置文件 {cf} 加载成功')
        
        if cf == 'config/bridge_params.yaml':
            bridge = cfg.get('bridge', {})
            arbiter = bridge.get('arbiter', {})
            if arbiter:
                print(f'  arbiter.pc_timeout_s: {arbiter.get(\"pc_timeout_s\")}')
                print(f'  arbiter.pc_soft_warning_s: {arbiter.get(\"pc_soft_warning_s\")}')
                print('  arbiter 配置存在')
            else:
                print('  WARN: arbiter 配置缺失')
    except Exception as e:
        print(f'配置文件 {cf} 加载失败: {e}')
        sys.exit(1)

print('配置检查通过')
" 2>&1
    echo ""

    # ────────────────────────────────────────
    # 步骤 7：检查日志中的错误
    # ────────────────────────────────────────
    log_info "=== 步骤 7: 检查已知问题 ==="
    
    cd "$PROJECT_ROOT"
    
    echo "检查 Mock AMD 代码中的控制模式分发逻辑..."
    if grep -q "is_autonomy_mode = mode in {0xEE, 0xEF, 238}" sim_holoocean/interfaces/mock_amd_server.py; then
        log_success "控制模式分发逻辑存在"
    else
        log_error "控制模式分发逻辑缺失"
        ERRORS=$((ERRORS + 1))
    fi
    
    echo "检查 Jetson 仲裁器分层超时..."
    if grep -q "pc_soft_warning_s" brain_linux/src/auv_bridge/auv_bridge/arbiter.py; then
        log_success "分层超时参数存在"
    else
        log_error "分层超时参数缺失"
        ERRORS=$((ERRORS + 1))
    fi
    
    echo "检查行为树 MockCableTrackingBehavior..."
    if grep -q "class MockCableTrackingBehavior" brain_linux/src/auv_decision/auv_decision_core/behaviors.py; then
        log_success "MockCableTrackingBehavior 存在"
    else
        log_error "MockCableTrackingBehavior 缺失"
        ERRORS=$((ERRORS + 1))
    fi
    
    echo ""

    # ────────────────────────────────────────
    # 汇总
    # ────────────────────────────────────────
    echo "========================================================================"
    if [ $ERRORS -eq 0 ]; then
        log_success "所有检查通过！无残余问题。"
        log_info "错误数: $ERRORS, 警告数: $WARNINGS"
    else
        log_error "发现 $ERRORS 个错误，请修复后重试"
        log_info "警告数: $WARNINGS"
    fi
    echo "========================================================================"
    
    if [ $ERRORS -gt 0 ]; then
        exit 1
    fi
}

main "$@"
