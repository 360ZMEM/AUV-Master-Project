# 🐛 HoloOcean 调试指南

快速排障与调试 HoloOcean 仿真环境的常见问题。

---

## 环境检查

### 验证 HoloOcean 安装

```bash
python -c "import holoocean; print(holoocean.__version__)"
```

预期输出：`3.x.x` 或更高

### 检查依赖

```bash
pip list | grep -E "(holoocean|zenoh|pyyaml)"
```

---

## 启动问题排查

### 问题：HoloOcean 环境立即崩溃

**原因**：
- 依赖缺失
- GPU 不兼容
- 场景文件丢失

**解决步骤**：
```bash
# 1. 重装 HoloOcean 客户端
cd holoocean/client
pip install -e . --upgrade

# 2. 验证场景文件
ls -la holoocean/worlds/

# 3. 检查 GPU 驱动
nvidia-smi  # 若无 GPU，需要 CPU 模式
```

### 问题：仿真速度极慢（< 1 FPS）

**解决**：
```yaml
# config/sim_params.yaml
simulation:
  ticks_per_sec: 10        # ← 降低目标速度
  dt: 0.1
```

或禁用不必要的可视化。

---

## 数据验证

### 检查传感器输出

```bash
# 在仿真启动后，查看仿真日志
grep -i "imu\|dvl\|depth" log/sim_*.log

# 或命令行查看当前状态
python -c "from sim_holoocean.apps.main import load_config; print(load_config('config/sim_params.yaml')['simulation'])"
```

### 验证坐标系转换

查看日志中是否有：
```
INFO: Frame transform UE4 -> NED: ...
```

若没有，检查 `frame_transform.py` 是否被正确调用。

---

## Zenoh 桥接问题

### 检查 Zenoh 是否运行

```bash
# 查看 Zenoh 进程
ps aux | grep zenoh

# 若无，手动启动
bash scripts/start_lin_sim.sh both  # 自动启动 Zenoh 桥接
```

### 验证 topic 数据流

```bash
# 查看所有 Zenoh topic
# 需要 Zenoh CLI 或 Python 客户端验证
python -c "
import zenoh
session = zenoh.open(zenoh.Config())
sub = session.declare_subscriber('rt/auv/**')
print(f'Subscribed to all rt/auv/* topics')
"
```

---

## 常见错误消息

| 错误 | 原因 | 解决 |
|------|------|------|
| `Module not found: holoocean` | 环境缺失 | `pip install holoocean` |
| `World file not found` | 场景路径错 | 检查 `config/sim_params.yaml` |
| `GPU out of memory` | 显存不足 | 降低 `ticks_per_sec` |
| `Zenoh bind failed` | 端口被占用 | 检查 `bridge_params.yaml` |

---

## 数据记录

### 启用详细日志

```yaml
# config/sim_params.yaml
simulation:
  log_level: DEBUG  # ← 改为 DEBUG
```

### 保存轨迹数据

```bash
# 运行后自动保存到 log/trajectory_*.npy
bash scripts/start_lin_sim.sh sim  # 自动保存
```

---

## 下一步

- 若仍无法解决，查看 [docs_backup/](../docs_backup/) 中的详细文档
- 或查看 [联调调试记录](../联调调试记录_2026-03-21.md) 获取更多示例

---

**更新日期**：2026-04-25
