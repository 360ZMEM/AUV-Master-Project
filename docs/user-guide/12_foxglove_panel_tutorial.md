# Foxglove 电缆跟踪面板教程

## 启动

生成稳定版布局：

```bash
python -m foxglove_layout_project.generator.build_layout --pretty
```

布局会写入 `foxglove_layout_project/output/auv_layout.generated.json`。

## 面板说明

- 3D 主视图：AUV 本体、真值位姿、电缆标记、地形和历史轨迹。
- 电缆跟踪曲线：来自 `/auv/cable/tracking` 的 cross-track、埋深和跟踪置信度。
- 电缆跟踪原始数据：`AUV-Master-Mag` 适配器输出的完整 JSON。
- 电缆诊断原始数据：限幅原因、fallback 状态、磁数据使用情况和路由诊断。
- DL/T 摘要：当 `/auv/cable/dlt1278_summary` 发布时，显示面向运维人员的评分摘要。

## AI 反馈闭环

使用：

```bash
python tools/foxglove_public_loop.py --url <foxglove_public_url> --wait-login
```

脚本会打开公网页面，等待人工登录，并把截图保存到 `results/visual_feedback/foxglove/`。它不会绕过登录，也不会修改云端布局。
