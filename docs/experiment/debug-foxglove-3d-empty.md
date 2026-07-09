# Debug Session: foxglove-3d-empty
- **Status**: [RUNTIME-VERIFIED]
- **Issue**: Foxglove 的 3D / 俯视图 panel 中没有稳定显示 AUV 主体与电缆先验图，当前只看到空背景或不可读区域。
- **Debug Server**: not-started-yet
- **Log File**: .dbg/trae-debug-log-foxglove-3d-empty.ndjson

## Reproduction Steps
1. 启动 `foxglove_bridge`，连接 `ws://localhost:8765`。
2. 回放 `/auv_data/bags/20260709_134856/rosbag`。
3. 在 Foxglove 中加载 `pilot-1366` 或 `acceptance-1366` layout。
4. 观察右侧 3D / top-view panel：当前没有稳定显示 AUV 主体与电缆先验图。

## Hypotheses & Verification
| ID | Hypothesis | Likelihood | Effort | Evidence |
|----|------------|------------|--------|----------|
| A | `/auv/visual/cable_marker` 在 bag 中没有有效几何内容，导致电缆先验线不可见 | High | Low | Pending |
| B | `/auv/state/filtered` 有数据，但在当前 Foxglove 3D 配置下没有被可视化出来 | High | Low | Pending |
| C | 3D 相机范围/坐标尺度不合适，图元存在但落在视野外 | Medium | Low | Pending |
| D | 缺少必要的 frame / TF 关系，Foxglove 无法把 Odometry/Marker 正确放到 `map` 下 | Medium | Medium | Pending |

## Log Evidence
- `ros2 topic echo /auv/state/filtered --once`:
  - `header.frame_id: world`
  - `child_frame_id: auv/base_link`
  - 说明当前 replay 至少有 AUV Odometry 主体数据。
- `ros2 topic list` only shows `/auv/state/filtered` among the expected 3D-related topics.
- `/auv_data/bags/20260709_134856/rosbag/metadata.yaml` contains `/auv/state/filtered`, but does **not** contain:
  - `/auv/visual/cable_marker`
  - `/auv/visual/history_trail`
  - `/auv/visual/view_range`
  - `/auv/visual/auv_body`
  - `/tf`
  - `/tf_static`
- Earlier generated layouts that used to visualize correctly were built around:
  - `fixedFrame=map`
  - `followTf=auv_base_link`
  - visible visual topics `/auv/visual/auv_body`, `/auv/visual/cable_marker`, `/auv/visual/history_trail`, `/auv/visual/view_range`
- Current 3f replay data instead exposes:
  - `fixed frame candidate = world`
  - `child frame candidate = auv/base_link`
  - no `/auv/visual/*` marker topics in the bag

## Verification Conclusion
- Hypothesis A: **CONFIRMED** for the current 3f bag. There is no `/auv/visual/cable_marker` topic in the bag, so the cable prior line cannot be shown by the current Foxglove 3D/top-view panels.
- Hypothesis B: **PARTIALLY CONFIRMED**. `/auv/state/filtered` exists and should be enough to draw an AUV glyph, but the current layout uses `fixedFrame=map` while the odometry is published in `world`.
- Hypothesis C: **INCONCLUSIVE** before frame fix. Camera/range may still need tuning after frame alignment.
- Hypothesis D: **CONFIRMED** for TF dependency. There is no `/tf` or `/tf_static` in the current bag, so any layout assumption that depends on TF alignment to `map` is unsafe for this replay.
- Additional finding: this is not just a rendering parameter regression. The successful older visualization path depended on `/auv/visual/*` topics that are absent from the current replay bag, while the frame naming also changed from `map/auv_base_link` to `world/auv/base_link`.
- Sidecar verification:
  - Added `tools/replay_visual_overlay_bridge.py` to republish `/auv/visual/auv_body`, `/auv/visual/history_trail`, `/auv/visual/cable_marker`, and `/auv/visual/view_range` from `/auv/state/filtered` + `heavy.yaml` prior.
  - `ros2 topic echo /auv/visual/auv_body --once` confirms marker replay with `frame_id: world`.
  - After reinjecting the acceptance layout, Foxglove 3D starts rendering the yellow cable line again, proving the old visual-topic contract was the missing path.
  - Fixed sidecar marker publishing in display/world frame instead of reusing old NED->display conversions. This removed the erroneous z sign flip on the AUV body marker.
  - Changed the replay AUV marker from a subtle cylinder to a larger arrow to improve top-view readability.
  - After hiding the Foxglove left settings sidebar and keeping the restored `/auv/visual/*` topics active, the 3D/top-view panel now visibly renders:
    - prior cable line
    - AUV body arrow
    - view range ring
    - trajectory line
  - Added a lightweight seabed mesh proxy on `/auv/visual/seabed_mesh` and a 10 m scale marker on `/auv/visual/scale_bar`.
  - Acceptance top-view now runs in `perspective=False` with explicit visible topics:
    - `/auv/visual/auv_body`
    - `/auv/visual/cable_marker`
    - `/auv/visual/history_trail`
    - `/auv/visual/view_range`
    - `/auv/visual/seabed_mesh`
    - `/auv/visual/scale_bar`
  - Generated offline 2D top-view artifact:
    - `results/visual_feedback/3f_visual_audit_20260709/foxglove/replay_top_view.png`
    - includes cable prior, AUV trajectory, start/latest points, heading arrow, and 10 m scale bar
  - `pilot-1366` was regenerated with the same restored visual-topic contract and now also renders:
    - seabed background
    - cable prior line
    - AUV body arrow
    - history trail
    - range ring
    - 10 m scale bar
  - Runtime verification on 2026-07-09 after restarting both rosbag replay and sidecar:
    - `ros2 bag play /auv_data/bags/20260709_134856/rosbag --rate 0.5 --loop`
    - `python3 tools/replay_visual_overlay_bridge.py`
    - `ros2 topic hz /auv/cable/dlt1278_summary` reports about `5.0 Hz`
    - `ros2 topic hz /auv/cable/dlt1278_summary_rewritten` reports about `15.0 Hz`
    - Raw summary sample:
      - `DL/T 1278风格状态: 注意状态 | 总分: 16 | ready: ready | pass: True`
    - Rewritten summary sample:
      - `DL/T 1278风格状态: 注意状态 | 扣分合计: 16 | ready: ready | pass: True`
    - Live marker probe observed continuous traffic on:
      - `/auv/visual/auv_body`
      - `/auv/visual/cable_marker`
      - `/auv/visual/seabed_mesh`
      - `/auv/visual/scale_bar`
    - Therefore the current replay chain has both:
      - restored 3D/top-view visual overlays
      - DLT wording rewrite for the Foxglove summary panel
  - Browser evidence capture on 2026-07-09:
    - Direct MCP browser refresh of the logged-in Foxglove tab could update layout metadata, but the page often fell back to `waiting for messages` / disconnected state after reload.
    - For stable evidence capture, reused `tools/foxglove_indexeddb_inject_layout.py` with `--headless` and the persistent profile at `tmp/foxglove_playwright_profile`.
    - Acceptance runtime screenshot:
      - `results/visual_feedback/3f_visual_audit_20260709/foxglove/acceptance_1366_playwright_runtime_verify.png`
    - Pilot runtime screenshot:
      - `results/visual_feedback/3f_visual_audit_20260709/foxglove/pilot_1366_playwright_runtime_verify.png`
    - Playwright injection receipts:
      - acceptance `existingConfigCount=11 -> configCount=11`, `name=auv_layout.acceptance_1366`
      - pilot `existingConfigCount=11 -> configCount=12`, `name=auv_layout.pilot_1366`
    - This confirms both 1366 layouts were re-injected from the latest local JSON artifacts during the current verification pass.
