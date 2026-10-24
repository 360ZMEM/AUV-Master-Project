"""Measure actual Matplotlib text, clipping and line/legend collisions.

Reports are evidence for visual review; they do not silently move artists or
claim that all plotted geometry is supported. Numeric data are never changed.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.font_manager as fm
import numpy as np
from matplotlib.text import Text
from matplotlib.transforms import Bbox
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from matplotlib.path import Path as MplPath


def stroke_intersects_box(path, box):
    """Test painted stroke segments, ignoring CLOSEPOLY's dummy vertex."""
    current = start = None
    for vertices, code in path.iter_segments(curves=False):
        if code == MplPath.MOVETO:
            current = start = vertices[-2:]
            continue
        if code == MplPath.STOP:
            break
        end = start if code == MplPath.CLOSEPOLY else vertices[-2:]
        if current is not None and end is not None and MplPath([current, end]).intersects_bbox(box, filled=False):
            return True
        current = end
    return False


def inspect_figure(fig, output: Path) -> dict:
    fig.canvas.draw()
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    inactive_tick_labels = set()
    for ax in fig.axes:
        for name in ("xaxis", "yaxis", "zaxis"):
            axis = getattr(ax, name, None)
            if axis is None:
                continue
            # Axis.draw uses this same view-interval filter. Allocated ticks
            # outside xlim/ylim are not painted and must not create false hits.
            axes_enabled = getattr(ax, "_axis3don", ax.axison) and axis.get_visible()
            ticks = axis._update_ticks() if axes_enabled else []
            painted = {id(t.label1) for t in ticks} | {id(t.label2) for t in ticks}
            if not axes_enabled:
                inactive_tick_labels.add(id(axis.label))
                inactive_tick_labels.add(id(axis.offsetText))
            for tick in axis.get_major_ticks() + axis.get_minor_ticks():
                for label in (tick.label1, tick.label2):
                    if id(label) not in painted:
                        inactive_tick_labels.add(id(label))
    labels = []
    clipped_labels = []
    missing_cjk = []
    for text in fig.findobj(Text):
        if id(text) in inactive_tick_labels or not text.get_visible() or not text.get_text().strip():
            continue
        box = Text.get_window_extent(text, renderer)
        if not np.isfinite(box.bounds).all() or box.width <= 0 or box.height <= 0:
            continue
        font = fm.findfont(text.get_fontproperties(), fallback_to_default=False)
        face = fm.get_font(font)
        for char in set(text.get_text()):
            if '\u3400' <= char <= '\u9fff' and face.get_char_index(ord(char)) == 0:
                missing_cjk.append({"text": text.get_text(), "char": char, "font_file": font})
        clip = text.get_clip_box()
        if text.get_clip_on() and clip is not None:
            if box.x0 < clip.x0 - .5 or box.y0 < clip.y0 - .5 or box.x1 > clip.x1 + .5 or box.y1 > clip.y1 + .5:
                clipped_labels.append({"text": text.get_text(), "bbox_px": list(box.bounds), "clip_px": list(clip.bounds)})
        labels.append((text, box, {"text": text.get_text(), "bbox_px": list(box.bounds),
                                 "font_file": font, "font_size_pt": text.get_fontsize()}))
    collisions = []
    for i, (_, a, left) in enumerate(labels):
        for _, b, right in labels[i + 1:]:
            inter = Bbox.intersection(a, b)
            if inter is not None and inter.width > 0.75 and inter.height > 0.75:
                collisions.append({"kind": "text_text", "left": left["text"],
                                   "right": right["text"], "intersection_px": list(inter.bounds)})
    for ax in fig.axes:
        targets = [(t, b, d) for t, b, d in labels if t in ax.texts]
        legend = ax.get_legend()
        if legend is not None:
            targets.append((legend, legend.get_window_extent(renderer), {"text": "[legend]"}))
            box = legend.get_window_extent(renderer)
            for index, patch in enumerate(ax.patches):
                if patch.get_visible() and not isinstance(patch, FancyArrowPatch) and patch.get_fill():
                    path = patch.get_transform().transform_path(patch.get_path())
                    if path.intersects_bbox(box, filled=True):
                        collisions.append({"kind": "patch_legend_overlap", "patch_index": index, "bbox_px": list(box.bounds)})
        for target_artist, box, info in targets:
            for name, spine in ax.spines.items():
                if ax.axison and spine.get_visible() and stroke_intersects_box(spine.get_transform().transform_path(spine.get_path()), box):
                    collisions.append({"kind": "spine_text_or_legend", "text": info["text"], "spine": name})
            for line in ax.lines:
                if not line.get_visible() or line.get_linestyle() in ("None", "none", "", " "):
                    continue
                path = line.get_transform().transform_path(line.get_path())
                if stroke_intersects_box(path, box):
                    collisions.append({"kind": "line_text_or_legend", "text": info["text"],
                                       "line": line.get_label(), "bbox_px": list(box.bounds)})
            for index, patch in enumerate(ax.patches):
                path = patch.get_transform().transform_path(patch.get_path())
                if isinstance(patch, FancyArrowPatch) and stroke_intersects_box(path, box):
                    collisions.append({"kind": "arrow_text", "text": info["text"], "patch_index": index})
                if isinstance(patch, FancyBboxPatch):
                    area = path.get_extents()
                    owner = getattr(target_artist, "_figure_node_patch", None)
                    centered = abs((area.x0 + area.x1 - box.x0 - box.x1) / 2) < 2 and abs((area.y0 + area.y1 - box.y0 - box.y1) / 2) < 2
                    if owner is patch or (owner is None and centered):
                        corners = [(box.x0 - 2, box.y0 - 2), (box.x0 - 2, box.y1 + 2),
                                   (box.x1 + 2, box.y0 - 2), (box.x1 + 2, box.y1 + 2)]
                        if not all(path.contains_point(point) for point in corners):
                            collisions.append({"kind": "node_text_outside", "text": info["text"], "patch_index": index})
    record = {"schema_version": 1, "method": "Agg renderer text extents after two draws; line path intersections",
              "label_count": len(labels), "labels": [d for _, _, d in labels],
              "collisions": collisions, "clipped_text": clipped_labels, "missing_cjk_glyphs": missing_cjk,
              "unverified": ["3D depth occlusion", "non-line collections versus text", "visual review required"]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    return record
