"""
实时仿真可视化 - matplotlib 交互式绘图。

该模块提供仿真运行时的实时可视化面板，显示 6 个子图：
  1. 3D 轨迹：参考路径 vs AUV 实际轨迹
  2. XY 平面轨迹：俯视图
  3. Z 轴深度：随时间变化的深度曲线
  4. 前向速度：u vs 目标 u
  5. 控制命令：推力和 4 个舵角的时序图
  6. （预留）可用于其他可视化

使用方式：
  >>> from plot_runtime import initialize_plot, update_live_plot, render_plot
  >>>
  >>> # 初始化
  >>> fig, lines, storage = initialize_plot(ref_bundle, dpi=140)
  >>> plt.ion()
  >>> plt.show()
  >>>
  >>> # 每个时间步更新
  >>> update_live_plot(fig, lines, storage, ref_points)
  >>> plt.pause(0.001)
  >>>
  >>> # 仿真结束
  >>> render_plot(fig, "output.pdf")
"""

import matplotlib.pyplot as plt
import numpy as np


def initialize_plot(ref_bundle, dpi):
    """
    初始化实时绘图面板。

    创建 2x3 子图布局，初始化所有线条和数据存储。

    参数：
        ref_bundle (dict)：参考轨迹信息，包含：
          - points (ndarray[N, 3])：参考路径点
        dpi (int)：图像分辨率

    返回值：
        tuple：(fig, lines, storage)
          - fig (matplotlib.figure.Figure)：图形对象
          - lines (dict)：所有可更新的线条对象
          - storage (dict)：数据存储（t, x, y, z, u, target_u, ref_z）
    """
    fig = plt.figure(figsize=(11, 7), dpi=dpi)

    # ────────────────────────────────────────────────
    # 子图 1️⃣：3D 轨迹
    # ────────────────────────────────────────────────
    ax3d = fig.add_subplot(2, 3, 1, projection="3d")
    ref_line_3d, = ax3d.plot([], [], [], "k--", lw=1.0, label="Ref path")
    live_line_3d, = ax3d.plot([], [], [], "tab:blue", lw=1.2, label="AUV")
    ax3d.set_title("3D Track")
    ax3d.set_xlabel("X (m)")
    ax3d.set_ylabel("Y (m)")
    ax3d.set_zlabel("Z (m, NWU)")
    ax3d.legend()

    # ────────────────────────────────────────────────
    # 子图 2️⃣：XY 平面轨迹
    # ────────────────────────────────────────────────
    ax_xy = fig.add_subplot(2, 3, 2)
    ref_line_xy, = ax_xy.plot(ref_bundle["points"][:, 0], ref_bundle["points"][:, 1], "k--", lw=1.1, label="Ref path")
    live_line_xy, = ax_xy.plot([], [], "tab:blue", lw=1.2, label="AUV")
    ax_xy.set_title("XY Track")
    ax_xy.set_xlabel("X (m)")
    ax_xy.set_ylabel("Y (m)")
    ax_xy.grid(True, alpha=0.3)
    ax_xy.legend()

    # ────────────────────────────────────────────────
    # 子图 3️⃣：深度 (Z) 时序
    # ────────────────────────────────────────────────
    ax_z = fig.add_subplot(2, 3, 3)
    live_ref_z, = ax_z.plot([], [], "k--", lw=1.1, label="Ref Z")
    live_pos_z, = ax_z.plot([], [], "tab:orange", lw=1.2, label="AUV Z")
    ax_z.set_title("Depth(Z) Track")
    ax_z.set_xlabel("Time (s)")
    ax_z.set_ylabel("Z (m, NWU)")
    ax_z.grid(True, alpha=0.3)
    ax_z.legend()

    # ────────────────────────────────────────────────
    # 子图 4️⃣：前向速度
    # ────────────────────────────────────────────────
    ax_u = fig.add_subplot(2, 3, 4)
    live_u, = ax_u.plot([], [], "tab:green", lw=1.2, label="u")
    live_u_tgt, = ax_u.plot([], [], "tab:red", ls="--", lw=1.1, label="u_target")
    ax_u.set_title("Surge Speed")
    ax_u.set_xlabel("Time (s)")
    ax_u.set_ylabel("u (m/s)")
    ax_u.grid(True, alpha=0.3)
    ax_u.legend()

    # ────────────────────────────────────────────────
    # 子图 5️⃣：控制命令
    # ────────────────────────────────────────────────
    ax_cmd = fig.add_subplot(2, 3, 5)
    live_cmd_thrust, = ax_cmd.plot([], [], lw=1.2, label="thrust")
    live_cmd_right, = ax_cmd.plot([], [], lw=1.0, label="right_fin")
    live_cmd_top, = ax_cmd.plot([], [], lw=1.0, label="top_fin")
    live_cmd_left, = ax_cmd.plot([], [], lw=1.0, label="left_fin")
    live_cmd_bottom, = ax_cmd.plot([], [], lw=1.0, label="bottom_fin")
    ax_cmd.set_title("Command")
    ax_cmd.set_xlabel("Time (s)")
    ax_cmd.set_ylabel("Command")
    ax_cmd.grid(True, alpha=0.3)
    ax_cmd.legend(ncol=2)

    fig.tight_layout()

    # ────────────────────────────────────────────────
    # 构建线条引用和数据存储
    # ────────────────────────────────────────────────
    lines = {
        "3d": live_line_3d,
        "ref3d": ref_line_3d,
        "xy": live_line_xy,
        "refxy": ref_line_xy,
        "z": (live_ref_z, live_pos_z),
        "u": (live_u, live_u_tgt),
        "cmd": (live_cmd_thrust, live_cmd_right, live_cmd_top, live_cmd_left, live_cmd_bottom),
    }
    storage = {k: [] for k in ["t", "x", "y", "z", "u", "target_u", "ref_z"]}
    return fig, lines, storage


def update_live_plot(fig_live, live_lines, live_storage, ref_points):
    """
    更新实时绘图数据。

    将 storage 中的最新数据更新到对应的线条对象。

    参数：
        fig_live (matplotlib.figure.Figure)：图形对象
        live_lines (dict)：initialize_plot 返回的线条字典
        live_storage (dict)：数据存储字典
        ref_points (ndarray)：参考路径点（用于 ref3d 和 refxy）
    """
    if len(live_storage["t"]) > 0:
        # ────────────────────────────────────────────────
        # 更新参考路径（显示到当前进度）
        # ────────────────────────────────────────────────
        idx = min(len(live_storage["t"]) - 1, len(ref_points) - 1)
        if idx >= 0:
            partial = ref_points[: idx + 1]
            live_lines["ref3d"].set_data(partial[:, 0], partial[:, 1])
            live_lines["ref3d"].set_3d_properties(partial[:, 2])
            live_lines["refxy"].set_data(partial[:, 0], partial[:, 1])

        # ────────────────────────────────────────────────
        # 更新 AUV 实时轨迹
        # ────────────────────────────────────────────────
        live_lines["3d"].set_data(live_storage["x"], live_storage["y"])
        live_lines["3d"].set_3d_properties(live_storage["z"])
        live_lines["xy"].set_data(live_storage["x"], live_storage["y"])

        # ────────────────────────────────────────────────
        # 更新深度曲线
        # ────────────────────────────────────────────────
        live_lines["z"][0].set_data(live_storage["t"], live_storage["ref_z"])
        live_lines["z"][1].set_data(live_storage["t"], live_storage["z"])

        # ────────────────────────────────────────────────
        # 更新速度曲线
        # ────────────────────────────────────────────────
        live_lines["u"][0].set_data(live_storage["t"], live_storage["u"])
        live_lines["u"][1].set_data(live_storage["t"], live_storage["target_u"])
        cmd = np.asarray(live_storage.get("cmd_history", []))
        if cmd.size:
            live_lines["cmd"][0].set_data(live_storage["t"], cmd[:, 4])
            live_lines["cmd"][1].set_data(live_storage["t"], cmd[:, 0])
            live_lines["cmd"][2].set_data(live_storage["t"], cmd[:, 1])
            live_lines["cmd"][3].set_data(live_storage["t"], cmd[:, 2])
            live_lines["cmd"][4].set_data(live_storage["t"], cmd[:, 3])

    xs = np.asarray(live_storage.get("x", []))
    ys = np.asarray(live_storage.get("y", []))
    zs = np.asarray(live_storage.get("z", []))
    if xs.size and ys.size and zs.size:
        ref_partial = ref_points[: min(len(live_storage["t"]) - 1, len(ref_points) - 1) + 1]
        ref_x = ref_partial[:, 0] if ref_partial.size else np.array([])
        ref_y = ref_partial[:, 1] if ref_partial.size else np.array([])
        ref_z = ref_partial[:, 2] if ref_partial.size else np.array([])
        all_x = np.concatenate([xs, ref_x]) if ref_x.size else xs
        all_y = np.concatenate([ys, ref_y]) if ref_y.size else ys
        all_z = np.concatenate([zs, ref_z]) if ref_z.size else zs
        xmin, xmax = float(np.min(all_x)), float(np.max(all_x))
        ymin, ymax = float(np.min(all_y)), float(np.max(all_y))
        zmin, zmax = float(np.min(all_z)), float(np.max(all_z))

        def margin(a, b):
            return 0.05 * max(b - a, 1.0)

        xm, ym, zm = margin(xmin, xmax), margin(ymin, ymax), margin(zmin, zmax)
        for ax in fig_live.axes:
            if hasattr(ax, "set_zlim"):
                ax.set_xlim(xmin - xm, xmax + xm)
                ax.set_ylim(ymin - ym, ymax + ym)
                ax.set_zlim(zmin - zm, zmax + zm)
            else:
                ax.relim()
                ax.autoscale_view()
    else:
        for ax in fig_live.axes:
            ax.relim()
            ax.autoscale_view()

    fig_live.canvas.draw()
    fig_live.canvas.flush_events()


def render_plot(history, ref_bundle, save_path, dpi):
    pos = np.asarray(history["pos"], dtype=float)
    ref = np.asarray(history["ref"], dtype=float)
    t = np.asarray(history["t"], dtype=float)

    fig = plt.figure(figsize=(11, 7), dpi=dpi)
    ax3d = fig.add_subplot(2, 3, 1, projection="3d")
    ax3d.plot(ref_bundle["points"][:, 0], ref_bundle["points"][:, 1], ref_bundle["points"][:, 2], "k--", lw=1.0, label="Ref path")
    if pos.size:
        ax3d.plot(pos[:, 0], pos[:, 1], pos[:, 2], "tab:blue", lw=1.2, label="AUV")
    ax3d.set_title("3D Track")
    ax3d.set_xlabel("X (m)")
    ax3d.set_ylabel("Y (m)")
    ax3d.set_zlabel("Z (m, NWU)")
    ax3d.legend()

    ax_xy = fig.add_subplot(2, 3, 2)
    ax_xy.plot(ref_bundle["points"][:, 0], ref_bundle["points"][:, 1], "k--", lw=1.1, label="Ref path")
    if pos.size:
        ax_xy.plot(pos[:, 0], pos[:, 1], "tab:blue", lw=1.2, label="AUV")
    ax_xy.set_title("XY Track")
    ax_xy.set_xlabel("X (m)")
    ax_xy.set_ylabel("Y (m)")
    ax_xy.grid(True, alpha=0.3)
    ax_xy.legend()

    ax_z = fig.add_subplot(2, 3, 3)
    if t.size and ref.size:
        ax_z.plot(t, ref[:, 2], "k--", lw=1.1, label="Ref Z")
    if t.size and pos.size:
        ax_z.plot(t, pos[:, 2], "tab:orange", lw=1.2, label="AUV Z")
    ax_z.set_title("Depth(Z) Track")
    ax_z.set_xlabel("Time (s)")
    ax_z.set_ylabel("Z (m, NWU)")
    ax_z.grid(True, alpha=0.3)
    ax_z.legend()

    ax_u = fig.add_subplot(2, 3, 4)
    if t.size:
        ax_u.plot(t, np.asarray(history.get("u", [])), "tab:green", lw=1.2, label="u")
        ax_u.plot(t, np.asarray(history.get("target_u", [])), "tab:red", ls="--", lw=1.1, label="u_target")
    ax_u.set_title("Surge Speed")
    ax_u.set_xlabel("Time (s)")
    ax_u.set_ylabel("u (m/s)")
    ax_u.grid(True, alpha=0.3)
    ax_u.legend()

    ax_cmd = fig.add_subplot(2, 3, 5)
    cmd = np.asarray(history.get("cmd", []))
    if t.size and cmd.size:
        ax_cmd.plot(t, cmd[:, 4], lw=1.2, label="thrust")
        ax_cmd.plot(t, cmd[:, 0], lw=1.0, label="right_fin")
        ax_cmd.plot(t, cmd[:, 1], lw=1.0, label="top_fin")
        ax_cmd.plot(t, cmd[:, 2], lw=1.0, label="left_fin")
        ax_cmd.plot(t, cmd[:, 3], lw=1.0, label="bottom_fin")
    ax_cmd.set_title("Command")
    ax_cmd.set_xlabel("Time (s)")
    ax_cmd.set_ylabel("Command")
    ax_cmd.grid(True, alpha=0.3)
    ax_cmd.legend(ncol=2)

    fig.tight_layout()
    fig.savefig(save_path)
    plt.close(fig)
