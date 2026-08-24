# 第一章前人巡检装备图片来源与核验记录

## 1. 用途与引用口径

本目录图片仅用于第 1 章 §1.2.4「典型探测装备与自主化沿革」的图文并茂展示，均为**前人/厂商公开工作**，正文图注一律以 `\cite{}` 标注来源，不作为本文自有成果。图片保持厂商官方原图，未做像素级修改（仅从 PDF 数据流无损抽取或直接下载）。

## 2. 来源与核验

| 文件 | 内容 | 来源（bib key / URL） | 抓取日期 | SHA-256 | 尺寸 |
|---|---|---|---|---|---|
| `hydropact350_coils.png` | Teledyne HydroPACT 350 双三轴感应线圈组（专用有源电磁探测载荷） | `teledyne2021hydropact350` / https://www.teledynemarine.com/en-us/products/SiteAssets/TSS/TSS%20HydroPACT%20350%20product%20leaflet.pdf | 2026-08-24 | 1f53df7875dc6c6169db0026a6bb4a73fee9ad4aa709658400609b85401490fd | 821×697 |
| `haiying_t180.jpg` | 海鹰 T180 海缆探测系统潜水/水面探测棒线圈阵列（国产有源电磁探测载荷） | `haiying_t180` / https://haiyingmarine.cn/index.php?a=shows&catid=141&id=304 | 2026-08-24 | d521adbca03cdfbaf658de158bacbaad571444d5f1504b1d1fc6e1b05b8168a9 | 474×474 |
| `fsea_p200.png` | 精灵 P200 模块化 AUV 平台（国产自主载体） | `fsea_p200` / https://www.f-sea.com/productinfo/105514.html | 2026-08-24 | ec853549f8d57491047e31762d00ada57f4c4f89722479af109634c24f231f78 | 750×750 |

## 3. 抓取方式

- HydroPACT 350：`curl` 下载官方产品规格书 PDF，`pdfimages -png` 无损抽取线圈组产品图（datasheet 第 1 页图 object 317）。
- 海鹰 T180：官方产品页图片经站点 CDN（`aka.doubaocdn.com/s/8HIb62Tpa6`）直取 JPEG 原图。
- 精灵 P200：官方产品页图片经站点 CDN（`aka.doubaocdn.com/s/sQEVC64dmj`）直取 PNG 原图（含厂商 HYPAI MARINE 水印，未去除以保真）。

## 4. 与 §1.2.4 能力分层表的对应

三幅图对应表~\ref{tab:ch01-cable-inspection-equipment} 的前三个能力层级：专用有源电磁载荷（HydroPACT 350 / 海鹰 T180）与通用自主调查平台（精灵 P200），用于以实物图佐证「专用探测载荷 → 自主载体」的装备演进主线。
