# 主论文构建目录迁移与根目录清理（2026-10-17）

主论文仍以仓库根目录的 `make auv-thesis` 构建，源码入口仍为 `thuthesis/auv-thesis.tex`。PDF、日志和 TeX 辅助文件现在统一位于 `thuthesis/build/auv-thesis/`，与中期报告的 `build/middle-main/`、`build/middle-school/` 并列。源章节、书目、图像和中期报告产物没有迁移或改写。

| 用途 | 路径或命令 |
|---|---|
| 当前主论文 | [build/auv-thesis/auv-thesis.pdf](../../thuthesis/build/auv-thesis/auv-thesis.pdf) |
| 当前编译日志 | `thuthesis/build/auv-thesis/auv-thesis.log` |
| 编译 | `make auv-thesis` |
| 清辅助缓存，保留 PDF | `make clean-auv-thesis` |
| 连 PDF 一起清理 | `make distclean-auv-thesis` |
| 迁移前冻结 PDF 与日志；9 月发布快照 | [backups/20261017_before_build_relocation](../../thuthesis/backups/20261017_before_build_relocation/manifest.json) |
| 逐文件清理清单 | [auv_thesis_root_cleanup_20261017.json](auv_thesis_root_cleanup_20261017.json) |
| 完整编译终端记录 | [auv_thesis_build_migration_20261017.log](auv_thesis_build_migration_20261017.log) |

首次在新输出目录编译时，根目录遗留的 `auv-thesis.bbl` 和 `.out` 被 TeX 优先读入，导致 Biber/BibTeX 规则误判。逐文件登记后清走旧根目录缓存，再编译成功。这是输出路径迁移时的缓存冲突，不是正文或书目缺失。共删除根目录 227 个已确认生成文件（含旧 PDF、日志、TeX/Biber 缓存、`xelatex*.fls`、示例缓存和 `missfont.log`）；`auv-thesis.tex`、`auvsetup.tex`、模板、图像、书目及备份未删。

迁移前已审阅的 PDF 为 170 页，SHA-256 `c622cee72099184f7f60bee99b2d512a25f1b25876bc9e44ce3924416e143977`，其日志 SHA-256 `9b0a59ce6ac0fe27985d2cf8c9ae5724049820b614e6f1462f57403b853fd154`。新目录经清缓存重编译的最终 PDF 仍为 170 页 A4，本次验收 SHA-256 `4d68c8ff006d278a1f140c4b479c67138252d44c480198cfdccbfd9e4c86f69b`。两版 `pdftotext -layout` 的 SHA-256 均为 `84d99f122f8e64ed52f3dc5cdf9835ad2a59a0c619375aa383a2887832e01ac3`，说明提取文本一致；PDF 字节差异来自重编译，不把新文件冒充旧哈希。新日志未检出未定义引用、待重跑 Biber、缺字或 `Overfull`。旧版哈希仍由原发布记录与备份校验，不回填历史 JSON。

2026-09-29 的稳健性发布还绑定更早一份 170 页论文，PDF SHA-256 为 `100e96e3eb9fcc29a6ce49de44f8d3908e56591f4410d6abb1181898c4ab0a77`。该 PDF/日志从已有 `docs/middle-defense/baseline/thuthesis-before.tar.gz` 中按原成员提取到同一备份，名称带 `_20260929_release`，以便历史发布审计按原哈希定位；它不代表当前论文版本。

Git 配置只让当前 PDF 和迁移前备份进入可见文件集合，二者均配置 LFS；`build/auv-thesis/` 内其他文件继续忽略。新 PDF 和备份需随本次变更一同提交，旧根目录 PDF 的删除也需纳入同一次提交，否则新克隆会同时出现两份。历史发布审计脚本在原路径消失时改为读取按旧哈希冻结的备份。
