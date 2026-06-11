# S2 — 全静态硬件自检（上架不入水）

> 上电、开外部供电、推进器和舵机连线但**支架挂着不入水**。本阶段量化 5 路执行器的极性 (Polarity) 和死区 (Deadzone)。

---

## 1. 目的

- 确认每路通道的极性方向（"左转"在仿真和实机一致）；
- 测量推进器/舵机的起转点（dead-zone）；
- 把结果填回 [sim_holoocean/configs/physics_config.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/configs/physics_config.yaml) 与 [params.protocol_udp_arbiter.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/config/params.protocol_udp_arbiter.yaml)，让仿真与实机匹配。

> **危险**：推进器接通后即使在空气中也可能伤人。挂支架前清空周围 1 米半径。

---

## 2. 前置条件

| 项 | 要求 |
|----|------|
| S1 通过 | `log/real_deployment/*_S1_link_audit_*/passed.flag` 存在 |
| 物理（real） | AUV 上支架；推进器/舵机外置；电机供电启用；磁力计可读 |
| target=real 时 | 必须 `--i-have-physical-auv`；shell 会在每路前要求 ENTER 确认 |
| 急停 | 另一终端预先准备好 `kill_switch.sh` |

---

## 3. 命令清单

```bash
cd /home/auv_user/auv_ws/AUV-Master-Project

# 默认 mock：5 路串行各跑 6s（30s/5 通道）
bash scripts/real_deployment/02_static_actuator.sh --target mock --duration 30

# real：每路前 ENTER 确认；推荐 60s 总时长
bash scripts/real_deployment/02_static_actuator.sh \
     --target real --duration 60 --i-have-physical-auv

# 干跑
bash scripts/real_deployment/02_static_actuator.sh --target mock --duration 10 --dry-run
```

shell 流程：
1. 后台拉起 [tools/actuator_polarity_recorder.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/actuator_polarity_recorder.py) 抓 145B `$AUV` 上行帧到 CSV；
2. 顺序跑 5 路：`rudder_left → rudder_right → rudder_top → rudder_bottom → thrust`；
3. 每路用 [tools/manual_protocol_injector.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/manual_protocol_injector.py) `--headless --continuous` 注入；
4. 每路结束发一帧全 0 + `Work_Cmd=0x02` 防止指令保持；
5. 写 `report.md`。

---

## 4. 通过判据

- `polarity_samples.csv` 每路有 ≥ 30 行（非全零）；
- shell 末尾出现 `marked stage passed`；
- 报告里 `motor1_rpm |max|`、`heading_deg span`、`pitch_deg span` 都不为 0（否则表明执行器没真正动）。

**不要**等待 shell 自动判极性正负 — 那需要人工查表。下面给出读法。

---

## 5. 极性 / 死区读法

打开 `log/real_deployment/<RUN_ID>/polarity_samples.csv`：

| 通道 | 看哪一列 | 期望（与 sim 一致） |
|------|---------|-----|
| `rudder_left` (注入正值) | `heading_deg` 应**减小**（左转，绕 z 轴正方向 = 左舷下沉的右手系） | 单调下降 |
| `rudder_right` | `heading_deg` 应**增大** | 单调上升 |
| `rudder_top` | `pitch_deg` 应**增大**（抬头） | 单调上升 |
| `rudder_bottom` | `pitch_deg` 应**减小**（低头） | 单调下降 |
| `thrust` | `motor1_rpm` 应**正向**增大 | 单调上升 |

**死区估值**：找到 `motor1_rpm`/`heading_deg` 首次跨过 1 倍噪声地板（看前 1 秒静态时的 std）的那一刻对应的 `--motor1` / `--rudder-*` 注入值。把它填入 `physics_config.yaml`：

```yaml
# sim_holoocean/configs/physics_config.yaml（示例字段）
actuator_deadzones:
  thrust: 5.0          # 真机起转 RPM
  rudder_left: 0.05    # 真机起动 normalized cmd
  rudder_right: 0.05
  rudder_top: 0.05
  rudder_bottom: 0.05
actuator_polarity:
  rudder_left: -1      # 若上面读出反向：把 +1 改 -1
```

---

## 6. 失败回退

| Symptom | Likely Cause | Fix Step |
|---------|--------------|----------|
| 注入正值 → AUV 反向 | 物理装错 / 协议层符号约定反 | 改 `actuator_polarity` yaml；**不要**改算法层 |
| 5 路都没动 | 0xEE 控制模式未生效 / Work_Cmd ≠ 0 | 看 `inject_*.log`；确认 `--ctrl-mode 238` 进入 AMD |
| 转速越高磁场噪声越大 | 电机 EMC | 设计磁干扰补偿，或物理屏蔽；记录在 [07_param_diff_sim_vs_real.md](07_param_diff_sim_vs_real.md) |
| 起转点比仿真大很多 | 真机摩擦/水阻不同 | 把死区写进 yaml；后续 PID 也要调 |

---

## 7. 修复实施建议（顺序）

1. **先填 deadzone**（线性偏移），再调 `kp`；
2. **极性反**：改 yaml，**不要**回头改 [auv_control](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_control) 任何源码；
3. **5 路都同向反**：检查机体坐标系定义；查 [自主式水下航行器设计方案 2021.5.28](../../标准文档/自主式水下航行器设计方案2021.5.28.md) 安装图；
4. 完成后回到 S1 重跑一次，确认 yaml 改动没破坏字节序解析。

---

## 8. 关键引用

- [scripts/real_deployment/02_static_actuator.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/real_deployment/02_static_actuator.sh)
- [tools/actuator_polarity_recorder.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/actuator_polarity_recorder.py)
- [tools/manual_protocol_injector.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/manual_protocol_injector.py)
- [sim_holoocean/configs/physics_config.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/configs/physics_config.yaml)
- [自主式水下航行器设计方案 2021.5.28](../../标准文档/自主式水下航行器设计方案2021.5.28.md)
