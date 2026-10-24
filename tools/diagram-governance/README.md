# draw.io 图源治理工具

本工具按 [`DRAWIO_GOVERNANCE.md`](../../相关附件和参照/DRAWIO_GOVERNANCE.md) 检查当前自有图源。权威图源仍为 `.drawio`，生成器分别是 `docs/thesis/figures/architecture/generate_architecture_diagrams.py` 与 `AUV-Master-Mag/docs/figure/generate_drawio_method_figures.py`；`AUV-Master-Mag/thesis/figures/architecture` 是由 `sync_mag_architecture_copies.py` 产生的只读快照。21 份冻结历史备份不计入当前清点。

工具在 Linux 上以 draw.io Desktop 24.7.17、Playwright 1.63.0 / Chromium 153.0.8010.12、Pillow 9.5.0、Noto Serif CJK SC 验证。Python 包安装在忽略的 `.diagram-governance/pydeps`；Chromium 安装在 `.diagram-governance/browsers`；字体映射见 `config/diagram-governance/fonts.conf`。`requirements.lock` 锁定 Python 包，`environment.json` 记录本机工具版本和字体解析结果。draw.io 32.4.1 的 CLI 导出试验超时，因此当前使用可稳定导出的 24.7.17；本轮层级图采用固定层序与规则网格，没有依赖 ELK。

在已安装 `drawio`、XeLaTeX、Poppler 和 Noto CJK 字体的 Linux 环境里，项目依赖可按下列命令复原：

```bash
python3 -m pip install --target .diagram-governance/pydeps -r tools/diagram-governance/requirements.lock
PYTHONPATH="$PWD/.diagram-governance/pydeps" PLAYWRIGHT_BROWSERS_PATH="$PWD/.diagram-governance/browsers" python3 -m playwright install chromium-headless-shell
node tools/diagram-governance/cli.mjs doctor
```

重新生成**已批准修复的图源、正式导出物、快照、论文 PDF 和全仓报告**：

```bash
bash tools/diagram-governance/rebuild-approved.sh
```

只读验收图源（仅写入忽略的检查目录，不改图源或正式导出物）：

```bash
node tools/diagram-governance/cli.mjs verify --all --fresh
```

单页定位可以运行 `node tools/diagram-governance/cli.mjs verify --file 路径.drawio`。缺陷、合法和变异用例由 `selftest` 检查；本轮为 17/17。检查器用 Chromium 实际渲染的文字 Range、SVG 形状填充区域、文本裁剪、容器边界和连线路径做判定，并要求全部标签映射与测量。`docs/thesis/diagram-governance/semantic-baseline.json` 锁定本轮开始前的语义；五层图的两页拆分只允许完整原节点集合、一次显式重复的 `b2` 续接节点和接触 `e2` 左边界的 `f4` 端口。

当前报告、逐页前后图像、人工看图记录、论文阅读字号和幂等性记录在 [`docs/thesis/diagram-governance/`](../../docs/thesis/diagram-governance/)。原件与完整临时轨迹在忽略的 `.diagram-governance/runs/20261018_governance/backup`；不要删除该目录。PDF 二进制含导出元数据，重导后哈希可能变化；已用文本抽取和 72 dpi 渲染比较验证内容一致，详见 `idempotence.json`。

当前仍有 19/34 页 FAIL，15/34 页 NEEDS_REVIEW。`verify` 的非零退出码是预期的验收失败信号；没有完成实际看图、论文阅读尺寸或正式产物一致性检查的页面不得标记 PASS。继续治理的精确入口见 [`RESUME.md`](../../docs/thesis/diagram-governance/RESUME.md)。
