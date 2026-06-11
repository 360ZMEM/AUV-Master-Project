# S1 — 通信协议与时钟审计

> 在剥夺 AMD 任何控制权之前，先把"我是不是真的能听懂对方"这件事确认清楚。本阶段**不插电机电缆**。

---

## 1. 目的

- 验证 Jetson ↔ AMD 之间的 UDP 链路确实通；
- 抓取 `$AUV` 上行帧的字节序、缩放因子、帧间隔均值/p95；
- 验证 `$CKTH` 下行帧 + 0xEF 模式握手反馈位 `Current_Cmd_State`。

---

## 2. 前置条件

| 项 | 要求 |
|----|------|
| S0 通过 | `log/real_deployment/*_S0_static_preflight_*/passed.flag` 存在；否则 shell 会软警告 |
| 网络（real） | PC=`192.168.0.11/24`，VxWorks=`192.168.0.101/24`，互通 ping |
| 网络（mock/vxsim） | 全部 `127.0.0.1`，无需任何配置 |
| 端口未被占用 | 21（下行）、52364（mock 绑定）、52365（上行）、52367（UDP 日志） |
| AMD 状态 | 真机 PC104 上电、运行最新 VxWorks 程序；电机断电（保持安全） |

---

## 3. 命令清单

```bash
cd /home/auv_user/auv_ws/AUV-Master-Project

# mock：本机回环（默认）
bash scripts/real_deployment/01_link_audit.sh --target mock --duration 30

# vxsim：在另一终端先启 csd_vx6.8_vxsim/，再跑：
bash scripts/real_deployment/01_link_audit.sh --target vxsim --duration 30

# real：必须显式确认有真机
bash scripts/real_deployment/01_link_audit.sh \
     --target real --duration 60 --i-have-physical-auv

# 干跑：不真启 mock AMD，仅打印将要执行的命令
bash scripts/real_deployment/01_link_audit.sh --target mock --duration 5 --dry-run
```

shell 内部做了以下 4 件事：
1. 后台拉起 [scripts/log_receiver.py](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/log_receiver.py) 抓 `52367` 的 VxWorks `printf`；
2. 若 `target=mock`，后台拉起 `sim_holoocean/apps/main.py --backend pvs --bridge protocol_udp` 充当假 AMD；
3. 用 `timeout ${DURATION_S} python3 vxworks_safety_hil.py --mode auto-udp --host $HIL_HOST` 注入下行 + 抓上行；
4. 解析日志，写 `log/real_deployment/<RUN_ID>/report.md`。

---

## 4. 通过判据

- `vxworks_safety_hil.py` 退出码 `0` 或 `124`（timeout 超时正常）；
- HIL 日志中 `grep -E "(uplink|UPLINK|\\\$AUV)"` 至少 1 命中；
- 帧间隔 p95 < 500 ms（真机；mock/vxsim 通常远低于此）；
- shell 末尾出现 `marked stage passed`。

不通过时**不会**写 `passed.flag`，下阶段会软警告。

---

## 5. 失败回退

| Symptom | Likely Cause | Fix Step |
|---------|--------------|----------|
| `bind 0.0.0.0:52365 failed` | 上次跑的进程没退干净 | `pkill -f vxworks_safety_hil`；或 `lsof -i :52365` |
| HIL log 一片空白 | mock_amd 没起来 / 真机 PC104 未上电 | 看 `mock_amd.stderr`；或在真机端 ping `192.168.0.11` |
| 收到帧但 heading 是 1234.5° | 大端/小端弄反 | 比对 [common/protocol.py](file:///home/auv_user/auv_ws/AUV-Master-Project/common/protocol.py) 与 [标准文档/软件通信协议.md](../../标准文档/软件通信协议.md) `>h` vs `<h` |
| heading 像是 0.1° 单位但乘了 10 | scale factor 乘错 | 同上文档；scale=0.1 已写在 actuator_polarity_recorder.py L53 |
| 帧间隔 p95 > 500 ms | VxWorks 高优先级任务阻塞 | 联系 PC104 端工程师调度任务优先级；或在 Jetson 端容忍更大抖动 |
| 0xEF 模式握手没回 `Current_Cmd_State` | AMD 端 ctrl_mode 未识别 | 比对 [VxWorks 最新协议](../../标准文档/VxWorks最新协议.md) 表 |

---

## 6. 修复建议（实施修复）

1. **字节序错**：永远只改 [common/protocol.py](file:///home/auv_user/auv_ws/AUV-Master-Project/common/protocol.py)（即 struct 格式串）；不要改算法层。
2. **scale 错**：把缩放因子修正写进协议层 parse 函数；不要在 EKF 里再乘一次。
3. **频率抖动**：如果 p95 ≥ 500 ms 但 mean < 150 ms，先记入 `report.md`，让 S3/S4 用更长的滑动窗滤波，而不是回退。

---

## 7. 关键源码与协议引用

- [scripts/real_deployment/01_link_audit.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/real_deployment/01_link_audit.sh) — 本阶段入口
- [scripts/vxworks_safety_hil.py](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/vxworks_safety_hil.py) — `--mode auto-udp` 直接征用
- [scripts/log_receiver.py](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/log_receiver.py) — 52367 UDP 日志
- [tools/actuator_polarity_recorder.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/actuator_polarity_recorder.py) — `parse_uplink` 145B 偏移参考
- [标准文档/软件通信协议.md](../../标准文档/软件通信协议.md) — 协议权威
