# 精简前完整论文备份

2026-09-28：236 页完整版，精简前保存。PDF 和全部原版源码的 SHA-256 校验通过；图像引用按原版 TeX 核对，96 个文件全部纳入完整归档。

- `auv-thesis_full_236p.pdf`：未删减 PDF。
- **`source_and_figures.complete.tar.gz`**：完整原版源码、参考文献、模板及图像依赖，共 450 个文件，保持仓库相对路径；恢复请使用此包。
- `manifest.json`：PDF、两份归档、完整包逐文件 SHA-256 与图像依赖检查。
- `source_and_figures.tar.gz`：首次按旧 `.fls` 收集的 402 文件快照，作为备份历史保留；缺少后来新增图像，完整恢复使用上面的 `.complete` 包。

在独立空目录解压完整归档后，先执行 `make -C thuthesis clean-auv-thesis` 清除归档中的历史辅助文件，再使用相同 TeX Live 环境执行 `make -C thuthesis auv-thesis`。系统宏包和字体由原环境提供。请勿直接解压覆盖当前精简稿。

实验收口归档中的论文哈希对应本次精简前版本；这些历史实验归档保持不变。

已在独立 `/tmp` 目录完成清理辅助文件后的重编译验证：236 页，无未定义引用/文献或 Overfull。原版备份 PDF 与当前 169 页精简稿均未被此验证覆盖。
