# FWHM 与海底电缆位置反演 v2 任务 Prompt

> 永久化日期：2026-09-18  
> 状态：需求基线；第一阶段只做现状审计和实施计划，不立即重构。  
> 主要作用域：`AUV-Master-Mag/` 独立磁探测算法，以及主仓 ROS2 全链路集成。  
> 约束：不修改现有代码和实验结果；后续实现采用独立 v2 模块或分支，保持接口兼容。

## 原始任务说明

现在请开始从 AUV-Master-Mag 磁探测子模块（大多数应该直接在这个子文件夹内，但是最终要在 ROS 做全链路分析），以及目前仓库目前背景信息开始，按照这个 prompt 的指引，完成 FWHM 的实现，并且结合阅读 thuthesis，实现海底电缆位置反演的更好估计，甚至是增大 zig-zag 幅度，或者改变 zig-zag 方式等，具体参见 prompt。注意先把这个 prompt 永久化。先阅读相关仓库内容，形成一个边界完整、目标较高、逐级的计划。

你现在需要在现有 AUV 海底电缆巡检算法代码（反演）基础上开发 v2 版本。

重要约束：

1. 不修改现有代码和实验结果；
2. 新建独立模块或分支实现；
3. 保持接口兼容；
4. 不过度增加复杂算法，优先提高可靠性和可解释性。

背景：

当前算法主要针对电缆附近磁感知和 FWHM 深度估计，但存在两个问题：

1. 缺少真实任务流程中的 Search 阶段；
2. FWHM 对信号质量敏感，可靠性不足。

目标：

构建一个更接近真实 AUV 海缆巡检流程的 v2 架构：

```text
Prior-guided Search
→ Magnetic Detection
→ Zig-zag Active Cross Scan
→ Explicit FWHM Estimation
→ Cable Tracking
```

请首先分析现有代码结构：

- 当前状态机在哪里？
- 当前磁场模型在哪里？
- 当前 FWHM 实现在哪里？
- 当前轨迹生成在哪里？
- 哪些模块可以复用？

然后设计 v2。

## 1. Search 模块

实现基于先验区域的规则搜索。

输入：

- cable prior path
- initial AUV position uncertainty
- search boundary

输出：

- search waypoint sequence

要求：不使用复杂优化规划算法。先实现以下可调参数：

- search width
- lane spacing
- velocity

并支持仿真评估：

- detection success rate
- detection time
- travelled distance

## 2. Magnetic Detection 模块

实现简单、可靠的检测。

输入：

- magnetic measurements

输出：

- detection score
- detected/not detected

优先使用：

- sliding window
- threshold
- hysteresis
- peak detection

不引入深度学习。

## 3. Confirm 模块

检测到电缆后，生成主动横切 zig-zag/cross-scan trajectory，以人为产生磁场空间变化。

要求输出 `B(x)`，并实现：

- peak detection
- half maximum calculation
- left/right crossing
- FWHM
- validity score
- confidence

## 4. Track 模块

输入：

- estimated cable offset

输出：

- heading correction
- lateral correction

优先保证稳定。

## 5. 实验设计

新增 simulation cases：

- Case A：大初始位置误差搜索；
- Case B：不同埋深；
- Case C：不同噪声；
- Case D：不同搜索间距。

评价指标：

- detection probability
- detection time
- FWHM error
- tracking error

## 6. 代码质量要求

后续实现应生成：

- v2 目录结构；
- README；
- 参数配置文件；
- 与 v1 区别说明；
- 实验运行方法。

不得删除旧代码。

## 当前阶段要求

第一步先阅读代码，输出当前架构分析和 v2 修改计划，不立即重构。

