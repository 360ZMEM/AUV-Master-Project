# 🔧 PVS 调试指南

PVS（Physical Vehicle Simulator）是一个高保真仿真后端。本指南介绍如何使用和调试 PVS。

---

## 快速切换到 PVS

```bash
# 仿真 + Zenoh + PVS 后端
bash scripts/start_lin_sim.sh both --sim-backend pvs

# 或使用专门的配置文件
bash scripts/start_lin_sim.sh both --config config/sim_params.pvs.yaml
```

---

## 依赖与环境

### 检查 PVS 是否可用

```bash
python -c "
try:
    import pvs
    print(f'PVS version: {pvs.__version__}')
except ImportError:
    print('PVS not installed')
"
```

### 安装 PVS（若需要）

```bash
pip install pvs  # 或根据项目指定版本
```

---

## 配置文件与参数

### PVS 专用参数

在 `config/sim_params.pvs.yaml` 中修改：

```yaml
simulation:
  backend: pvs                 # ← 指定 PVS 后端
  
pvs:
  # PVS 特定参数
  physics_engine: bullet      # 物理引擎：bullet / ode
  water_density: 1025.0       # 水密度（kg/m³）
  gravity: 9.81               # 重力加速度
  
  # 浮力与阻力
  buoyancy:
    enabled: true
    margin: 0.01
  
  drag:
    linear: 0.05              # 线性阻力系数
    quadratic: 0.01           # 二次阻力系数
```

---

## 常见问题

### Q: PVS 启动很慢

**原因**：物理计算密集，特别是在高精度配置下

**解决**：
```yaml
pvs:
  physics_engine: bullet      # 使用更快的 Bullet
  time_step: 0.01             # 降低精度
```

### Q: 与 HoloOcean 结果不一致

**原因**：模型、参数、坐标系不同

**解决**：
1. 检查 `frame_transform.py` 是否正确处理坐标系
2. 对比两个后端的物理参数
3. 运行等价性检查：`bash scripts/run_sim_equivalence_check.sh`

### Q: 某些传感器在 PVS 中无法工作

**原因**：PVS 可能不支持所有虚拟传感器

**解决**：
1. 查看 `config/sim_params.pvs.yaml` 中的传感器配置
2. 禁用不支持的传感器
3. 使用综合传感器替代

---

## 等价性验证

### 运行对比测试

```bash
# 干跑模式（不执行，仅检查配置）
bash scripts/run_sim_equivalence_check.sh --dry-run

# 实际运行（耗时 10+ 分钟）
bash scripts/run_sim_equivalence_check.sh

# 结果位置
cat log/equivalence_check_*.log  # 对比结果
```

---

## 下一步

- 详细内容见 [docs_backup/PVS全流程runbook.md](../docs_backup/PVS全流程runbook.md)
- 排坑记录见 [docs_backup/PVS调试排坑记录.md](../docs_backup/PVS调试排坑记录.md)

---

**更新日期**：2026-04-25
