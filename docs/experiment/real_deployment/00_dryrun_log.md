# 00 — Static Dry-Run 验证日志（mock target）

> 本文件累积所有 dry-run 记录。**最新一次写在最上方**；保留近 5 次。
> 对应 SOP：[`docs/real_deployment/INDEX.md`](../../real_deployment/INDEX.md) §五阶段总图。
> Dry-run 的目的：在不发实弹的前提下，验证 6 个 shell 脚本的"骨架"——`set -euo pipefail` 不会半路死、`_lib.sh` 各 helper 行为正确、Python 工具 import 不报错。

---

## 空模板（复制后填）

```
## Run <YYYYMMDD_HHMMSS>

**操作员**: <name>
**target**: mock
**git commit**: <sha>
**SOP 修订日期**: <YYYY-MM-DD>
**RD_DRY_RUN**: true

### 命令清单
1. `RD_DRY_RUN=true bash scripts/real_deployment/00_static_preflight.sh --target mock`
2. `RD_DRY_RUN=true bash scripts/real_deployment/01_link_audit.sh --target mock`
3. `RD_DRY_RUN=true bash scripts/real_deployment/02_static_actuator.sh --target mock`
4. `RD_DRY_RUN=true bash scripts/real_deployment/03_shadow_navigation.sh --target mock`
5. `RD_DRY_RUN=true bash scripts/real_deployment/04_closed_loop_single.sh --target mock`
6. `RD_DRY_RUN=true bash scripts/real_deployment/05_full_autonomy.sh --target mock`
7. `RD_DRY_RUN=true bash scripts/real_deployment/kill_switch.sh --target mock`

### 通过判据自评
- [ ] 7 个脚本全部以 exit 0 退出
- [ ] 无 unbound variable / set -e 半路死
- [ ] runs/real_deployment/<run_id>/ 下生成 banner.txt + dry_run.log
- [ ] 三个 Python 工具 `python3 -c "import ..."` 不报错
- [ ] kill_switch.sh dry-run 输出 `[dry-run] would loop: manual_protocol_injector.py ...`

### 异常与根因
（无 / ...）

### 后续动作
（无 / ...）
```

---

## Run 历史（最新在上）

### Run 20260609_110354 — 首次 SOP 体系交付后的 dry-run

**操作员**: trae-agent
**target**: mock
**git commit**: `5a8f3ec40e5ab4206f4ba57e2167978ed065929d`
**SOP 修订日期**: 2026-06-09
**RD_DRY_RUN**: true

#### 命令清单（按顺序执行）

```bash
RD_DRY_RUN=true bash scripts/real_deployment/00_static_preflight.sh --target mock   # → S0_static_preflight_mock, EXIT=0
RD_DRY_RUN=true bash scripts/real_deployment/01_link_audit.sh         --target mock   # → S1_link_audit_mock,         EXIT=0
RD_DRY_RUN=true bash scripts/real_deployment/02_static_actuator.sh    --target mock   # → S2_static_actuator_mock,    EXIT=0
RD_DRY_RUN=true bash scripts/real_deployment/03_shadow_navigation.sh  --target mock   # → S3_shadow_navigation_mock,  EXIT=0
RD_DRY_RUN=true bash scripts/real_deployment/04_closed_loop_single.sh --target mock   # → S4_closed_loop_single_mock, EXIT=0
RD_DRY_RUN=true bash scripts/real_deployment/05_full_autonomy.sh      --target mock   # → S5_full_autonomy_mock,      EXIT=0
RD_DRY_RUN=true bash scripts/real_deployment/kill_switch.sh           --target mock   # → KS_kill_switch_mock,        EXIT=0
```

#### 通过判据自评

- [x] 7 个脚本全部以 exit 0 退出
- [x] 无 unbound variable / set -e 半路死
- [x] log/real_deployment/<run_id>/ 下生成 metadata.txt（7 个目录已生成，git rev-parse 与 dry_run=true 已落盘）
- [x] 三个 Python 工具 `python3 -c "import ast; ast.parse(...)"` 不报错（actuator_polarity_recorder / shadow_diff_recorder / single_setpoint_driver 全部 syntax-ok）
- [x] `common.protocol` import-ok（roundtrip 路径可用）
- [x] kill_switch.sh dry-run 输出 `[dry-run] would loop: manual_protocol_injector.py --ctrl-mode 0x01 --work-cmd 0x02 --motor1 0 ...`
- [x] S1 含 "found previous 'S0_static_preflight' passed flag (proceed)."（阶段链路检测正常）

#### 异常与根因

**关键发现 — soft-warning（非阻塞）**：
S2..S5 在 dry-run 下均输出 `[WARN] no previous 'SX' passed flag found`。**根因**：dry-run 模式下脚本走 `[dry-run] skipping pass criteria` 分支，**不会调用 `rd_mark_stage_passed`**，因此 passed.flag 不落盘——后续阶段的 `rd_assert_prev_stage_done` 自然找不到。这是预期行为（dry-run 不应模拟"通过"），WARN 文案存在即正确。

**非阻塞性观察**：S0 的 dry-run **会** mark_stage_passed（因为 S0 没有 dry-run 早退分支），与 S1..S5 不一致。已记录待评估，不在本次范围内修。

#### 后续动作

- 无 SOP / 脚本变更；本次仅验证骨架。
- 若 S0 的 dry-run mark passed 行为引起 vxsim/real 阶段 chain 误判，回头改 S0 在 dry-run 下也跳过 mark_stage_passed（当前无问题，暂不动）。
- 下次 dry-run 触发条件：任一 SOP md 或 shell 修订；或 _lib.sh 发版。

---

