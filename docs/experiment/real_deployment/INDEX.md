# docs/experiment/real_deployment/ — 实物部署过程日志索引

> 与 [`docs/real_deployment/`](../../real_deployment/INDEX.md)（**SOP 体系，预先规约**）配对的**事后日志区**。
> SOP 文档回答 "怎么做"；本目录回答 "做了之后发生了什么"。每跑一次 dry-run / vxsim / real，落一份日志。
> 写作风格对齐既有的 [`benchmark_test_log.md`](../benchmark_test_log.md)：**命令 → 结果 → 关键发现 → 根因 → 规避/已修复**。

---

## 当前文件

| 文件 | 用途 | 何时写 |
|---|---|---|
| [`00_dryrun_log.md`](00_dryrun_log.md) | 静态 dry-run 验证（mock target，全栈不发实弹） | **每次修改 SOP 或 shell 脚本后** |
| `01_vxsim_log_<run_id>.md` *(占位)* | vxsim target 全程日志 | 每次 vxsim 全程跑通后 |
| `02_real_log_<run_id>.md` *(占位)* | real target 全程日志 | 每次真机部署后 |

---

## 文件命名规约

- `00_dryrun_log.md` — 单文件累积式，每次 dry-run 在文件顶部追加新段；保留近 5 次。
- `01_vxsim_log_<run_id>.md` — 一次一文件，`<run_id>` 取 `runs/real_deployment/<run_id>` 同名（形如 `20260609_153012_S4_vxsim`）。
- `02_real_log_<run_id>.md` — 同上，作为真机部署的最终交付物。

---

## 单次日志的最小骨架

每份日志至少包含以下 5 段：

```
1. 元信息 (日期/操作员/target/git commit/sha256)
2. 执行命令清单 (按 SOP 顺序)
3. 通过判据自评 (逐项打勾/打叉)
4. 异常与根因 (有就写没有写"无")
5. 后续动作 (是否改 yaml / 是否提 issue / 下次部署应注意)
```

骨架在 `00_dryrun_log.md` 顶部有一份**空模板**可直接复制。

---

## 与 SOP 文档的双向引用

- 每份日志在元信息段必须列出**对应 SOP 文档的 git 路径与 commit**，例如：
  > 对应 SOP: [`docs/real_deployment/04_stage4_closed_loop_single.md`](../../real_deployment/04_stage4_closed_loop_single.md) @ commit `<sha>`
- SOP 文档若因事故而修订，反向在本目录开 issue 引用，避免"SOP 已变但日志没记"的脱节。

---

## 关键引用

- SOP 体系总入口：[`docs/real_deployment/INDEX.md`](../../real_deployment/INDEX.md)
- 既有日志格式样板：[`docs/experiment/benchmark_test_log.md`](../benchmark_test_log.md)
- 公共 shell 库：[`scripts/real_deployment/_lib.sh`](../../../scripts/real_deployment/_lib.sh)
