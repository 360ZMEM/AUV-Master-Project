# Mock AMD 真实性增强 & 硬件合约测试 — 实施蓝图

> **状态**: 📋 文档冻结，待实施  
> **创建日期**: 2025-07  
> **范围**: AUV_Master_Project 的 Mock AMD 仿真器

---

## 1. 项目目标

将 `mock_amd_server.py` 从"即时透传"升级为"物理缺陷注入器"，同时建立 Python codec 与 VxWorks 固件之间的协议合同测试套件。

**核心价值**:
- 仿真更接近真实硬件通信环境（延迟、丢包、传感器异步采样）
- 协议字段级合同测试保证 Python ↔ VxWorks 字节一致性
- 混沌注入能力支持上层决策逻辑的鲁棒性验证

## 2. 范围与边界

### 在范围内

- Mock AMD 传输延迟模拟（FIFO 队列）
- 传感器异步采样缓存（独立时钟）
- 7 种混沌注入行为（DVL 冻结、IMU 漂移、深度跳变、磁饱和、上行断电、丢包、乱序）
- $CKTH (72B) / $AUV (145B) 协议合同测试
- 仲裁器 / 自治守卫硬件行为测试扩展
- 攻击站（双主竞争模拟）
- YAML 配置扩展

### 不在范围内

- `common/protocol.py` 代码修改（7 处偏差标记为 KNOWN_DEVIATION，保持现状）
- VxWorks 固件修改
- ROS2 节点修改
- HoloOcean 仿真器修改
- Foxglove 面板修改

## 3. 关键发现

### 3.1 协议一致性

| 帧 | 大小 | 状态 |
|----|------|------|
| $CKTH (下行) | 72B | ✅ Python 与 VxWorks 完全一致 |
| $AUV (上行) | 145B | ⚠️ 7 处偏差（详见偏差分析） |

### 3.2 偏差摘要

| ID | 位置 | 严重度 | 描述 |
|----|------|--------|------|
| D1 | byte 35-37 | 🔴 高 | Python: orientation (3×i16) vs VxWorks: pressure (u32) |
| D2 | byte 114-115 | 🟡 中 | Python: temperature vs VxWorks: reserved |
| D3 | byte 60-63 | 🟡 中 | 舵角编码差异 (i16×10 vs u16°) |
| D4 | byte 20-21 | 🟢 低 | 深度缩放差异 (×10 vs ×1) |
| D5 | byte 14-17 | 🟢 低 | GPS 速度编码差异 (×10 vs raw mm/s) |
| D6 | byte 28-35 | 🟢 低 | GPS 经纬度字节序差异 |
| D7 | byte 126-141 | 🟡 中 | 异常位图差异 (3×u8 vs 4×u32) |

**决策**: 全部标记为 `KNOWN_DEVIATION_*`，不在本次修改 `protocol.py`。

## 4. 实施步骤

```
Step 1 ─ 新增核心模块（纯代码，无侵入）
  │     TransportDelayQueue + SensorSampleCache + ChaosInjector
  ▼
Step 2 ─ 集成到 MockAmdUdpServer
  │     修改 mock_amd_server.py 的 4 个方法
  ▼
Step 3 ─ YAML 配置扩展
  │     新增 mock_amd: 配置节
  ▼
Step 4 ─ Phase 1 协议合同测试
  │     T1.1-T1.9（端序、缩放、校验和、往返）
  ▼
Step 5 ─ Phase 2 硬件行为测试
  │     T2.1-T2.10（极性、零位、死区、超时、混沌）
  ▼
Step 6 ─ 攻击站脚本
        scripts/attacker_station.py
```

## 5. 依赖关系

```
Step 1 (新模块)
  ├─► Step 2 (集成)
  │     ├─► Step 3 (配置)
  │     └─► Step 5 (混沌测试)
  └─► Step 4 (协议测试，与 Step 1-3 并行)

Step 4 ◄──► Step 5 (可并行)

Step 6 (攻击站，独立)
```

## 6. 风险矩阵

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| Step 2 集成破坏现有行为 | 低 | 高 | Step 2 前后运行冒烟测试 |
| KNOWN_DEVIATION 导致测试假失败 | 中 | 低 | 测试中标记 skip 或 xfail |
| 混沌注入参数不当导致仿真崩溃 | 低 | 中 | 默认全部关闭，需显式启用 |
| 攻击站抢走 Mock AMD 响应 | 确定 | 低 | 这正是测试目的，文档说明 |

## 7. 子文档索引

| # | 文档 | 路径 | 内容 |
|---|------|------|------|
| 1 | 协议合同映射 | [`docs/mock_amd_hw/协议合同映射.md`](mock_amd_hw/协议合同映射.md) | $CKTH/$AUV 完整字节偏移表、类型、缩放因子 |
| 2 | 偏差分析 | [`docs/mock_amd_hw/偏差分析.md`](mock_amd_hw/偏差分析.md) | 7 处 Python↔VxWorks 偏差的根因与决策 |
| 3 | 真实性增强设计 | [`docs/mock_amd_hw/真实性增强设计.md`](mock_amd_hw/真实性增强设计.md) | 延迟队列、传感器缓存、混沌注入器架构 |
| 4 | 配置扩展方案 | [`docs/mock_amd_hw/配置扩展方案.md`](mock_amd_hw/配置扩展方案.md) | YAML `mock_amd:` 节完整 schema 与加载逻辑 |
| 5 | 攻击站设计 | [`docs/mock_amd_hw/攻击站设计.md`](mock_amd_hw/攻击站设计.md) | attacker_station.py 的模式、接口、报告 |
| 6 | 测试用例清单 | [`docs/mock_amd_hw/测试用例清单.md`](mock_amd_hw/测试用例清单.md) | Phase 1/2 共 19 个测试用例 + 优先级矩阵 |
| 7 | 文件变更清单 | [`docs/mock_amd_hw/文件变更清单.md`](mock_amd_hw/文件变更清单.md) | 6 新增 + 5 修改 + 依赖图 + 实施顺序 |
| 8 | 验证方案 | [`docs/mock_amd_hw/验证方案.md`](mock_amd_hw/验证方案.md) | pytest 命令、Wireshark 过滤、检查清单 |

## 8. 实施前检查

- [ ] 已通读本蓝图全部 8 份子文档
- [ ] 已确认 `common/protocol.py` 不在修改范围
- [ ] 已确认 7 处 `KNOWN_DEVIATION` 标记策略
- [ ] 已准备测试运行环境（pytest + python3）
- [ ] 已确认 `config/bridge_params.protocol_udp.yaml` 路径
