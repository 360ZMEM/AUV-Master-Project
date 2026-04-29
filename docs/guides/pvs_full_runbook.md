# 📋 PVS 全流程 Runbook

PVS（Physical Vehicle Simulator）高保真仿真完整操作手册。

---

## 前提条件

### 环境要求
- Python 3.10+
- PVS 物理引擎已安装
- 所有仿真依赖已安装

### 检查安装

```bash
# 检查 PVS 版本
python -c "import pvs; print(pvs.__version__)"

# 检查配置文件
ls -lh config/sim_params.pvs.yaml
```

---

## 启动流程

### 第一步：切换到 PVS 后端

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project

# 仿真 + Zenoh + PVS
bash scripts/start_lin_sim.sh both --sim-backend pvs

# 或指定完整配置路径
bash scripts/start_lin_sim.sh both --config config/sim_params.pvs.yaml
```

### 第二步：验证 PVS 初始化

查看日志中是否出现：

```
INFO: PVS backend initialized
INFO: Physics engine: Bullet
INFO: Water density: 1025.0 kg/m³
```

### 第三步：监控仿真运行

```bash
# 实时监控
tail -f log/sim_*.log

# 或在另一个终端查看统计数据
watch -n 1 'grep "Current state" log/sim_*.log | tail -5'
```

---

## 配置参数

### PVS 专用配置

```yaml
# config/sim_params.pvs.yaml
simulation:
  backend: pvs

pvs:
  # 物理引擎选择
  physics_engine: bullet      # bullet / ode / newton
  
  # 水环境参数
  water_density: 1025.0
  gravity: 9.81
  
  # 浮力模型
  buoyancy:
    enabled: true
    center_of_buoyancy: [0, 0, 0.1]
    margin: 0.01
  
  # 阻力模型
  drag:
    linear: 0.05
    quadratic: 0.01
    area: 0.5
```

---

## 常见任务

### 任务 1：对比 PVS 与 HoloOcean

```bash
# 运行 HoloOcean 基准
bash scripts/start_lin_sim.sh both --config config/sim_params.yaml --run-id holoocean

# 运行 PVS 对比
bash scripts/start_lin_sim.sh both --config config/sim_params.pvs.yaml --run-id pvs

# 对比结果
python tools/compare_runs.py log/holoocean/ log/pvs/
```

### 任务 2：调整物理参数

```bash
# 编辑配置
vim config/sim_params.pvs.yaml

# 修改某个参数（例如增加水密度）
pvs:
  water_density: 1028.0  # 原值 1025.0

# 重新运行
bash scripts/start_lin_sim.sh both --sim-backend pvs
```

### 任务 3：导出物理数据

```bash
# 仿真完成后，导出数据
python tools/export_physics_data.py \
  --input log/sim_2026-04-25_12-34-56/ \
  --output pvs_data.csv
```

---

## 故障排除

### 问题：PVS 启动失败

**检查项**：
```bash
# 1. 验证 PVS 安装
python -c "import pvs"

# 2. 检查配置文件语法
python -c "import yaml; yaml.safe_load(open('config/sim_params.pvs.yaml'))"

# 3. 查看详细错误
bash scripts/start_lin_sim.sh both --sim-backend pvs 2>&1 | grep -i error
```

### 问题：物理仿真不稳定（发散）

**解决**：
```yaml
# 降低时间步长
simulation:
  dt: 0.01          # 从 0.0333 降低到 0.01
  ticks_per_sec: 100  # 相应提高

# 或启用物理引擎的容错
pvs:
  enable_contact_solver: true
  contact_erp: 0.1
```

### 问题：性能太慢

**优化**：
```yaml
# 简化物理模型
pvs:
  physics_engine: bullet      # 选择更快的引擎
  enable_joint_damping: false # 禁用阻尼
  
  # 降低更新频率
simulation:
  dt: 0.05
  ticks_per_sec: 20
```

---

## 验证与基准测试

### 运行等价性检查

```bash
# 干跑模式（检查配置）
bash scripts/run_sim_equivalence_check.sh --dry-run

# 完整运行（10+ 分钟）
bash scripts/run_sim_equivalence_check.sh

# 查看结果
cat log/equivalence_check_*.log
```

### 性能基准

```bash
# 单独运行 PVS 并计时
time bash scripts/start_lin_sim.sh both --sim-backend pvs --duration 60

# 预期结果：~30-60 秒（取决于硬件）
```

---

## 下一步

- 详细的排坑记录：[docs_backup/PVS调试排坑记录.md](../docs_backup/PVS调试排坑记录.md)
- HoloOcean 调试指南：[PVS调试指南](pvs_debugging.md)

---

**更新日期**：2026-04-25
