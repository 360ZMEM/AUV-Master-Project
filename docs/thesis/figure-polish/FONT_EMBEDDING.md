# 宋体来源与 PDF 嵌入复核

Matplotlib 采用 TeX Live 自带的 `FandolSong-Regular.otf` / `FandolSong-Bold.otf`，由 `tools/thesis_plot_style.py` 显式注册；与论文中文宋体体系一致。draw.io 原生仍为 Songti SC，通过项目 fontconfig 固定映射到 Noto Serif CJK SC；PDF实际嵌入另行检查。两套均为中文衬线字形，不允许意外文泉驿/中文黑体回退。

本轮额外发现：旧 Matplotlib 的 `pdf.fonttype=42` 会把 Fandol 的 CFF/OpenType 字体写为 `/CIDFontType2`、`/FontFile2`。Poppler 能显示中文但提示 `Mismatch between font type and embedded font file`；PyMuPDF 1.24.14 会显示错误字形。不能只看 Agg PNG 或仅核对字体名称。

当前共享样式改为 Matplotlib 支持的 `pdf.fonttype=3` / `ps.fonttype=3`，嵌入原宋体的矢量轮廓；没有把图像栅格化，也没有改变字号。最小样例在本轮运行目录 `type3-test.pdf/png`，由 PyMuPDF 实际栅格化后已打开查看。Type 3 的中文轮廓未全部保留可检索文本层，因此字体/标签完整性由源 renderer 的逐标签字体、字形与包围盒记录联合正式图像复核；不再把 PDF 文本抽取当作全部标签完整性的证明。原生 Python 和 draw.io 可编辑源仍保留。

依据：[Matplotlib 官方字体说明](https://matplotlib.org/stable/users/explain/text/fonts.html#fonts-in-pdf-and-postscript)说明 Type 3 与 TrueType 的 PDF 支持、OpenType 有限支持及矢量字体子集。上述兼容性问题为本仓库文件实测，并非将文档一般描述当成该缺陷证据。未重绘的旧资产单独标记，不能因共享样式已改便声称旧 PDF 已修复。
