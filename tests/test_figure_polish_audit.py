"""Fault-injection checks for the presentation figure inspector."""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from figure_polish_audit import inspect_figure


def test_text_overlap_and_legal_separation(tmp_path):
    fig, ax = plt.subplots()
    left = ax.text(.2, .4, "first label")
    right = ax.text(.2, .4, "second label")
    bad = inspect_figure(fig, tmp_path / "bad.json")
    assert any(x.get("left") == left.get_text() and x.get("right") == right.get_text()
               for x in bad["collisions"])
    right.set_position((.7, .8))
    legal = inspect_figure(fig, tmp_path / "legal.json")
    assert not any(x.get("left") == left.get_text() and x.get("right") == right.get_text()
                   for x in legal["collisions"])
    plt.close(fig)


def test_line_and_legend_overlap(tmp_path):
    fig, ax = plt.subplots()
    ax.plot([0, 1], [.5, .5], label="measurement")
    ax.text(.4, .5, "covers data", va="center")
    ax.legend(loc="center")
    result = inspect_figure(fig, tmp_path / "line.json")
    hits = {x.get("text") for x in result["collisions"] if x["kind"] == "line_text_or_legend"}
    assert "covers data" in hits
    assert "[legend]" in hits
    plt.close(fig)


def test_outside_locator_ticks_not_counted(tmp_path):
    fig, axes = plt.subplots(1, 2)
    for ax in axes:
        ax.set_xticks([-4, -2, 0, 2, 4])
        ax.set_xlim(-3.3, 3.3)
    result = inspect_figure(fig, tmp_path / "ticks.json")
    assert not any(x["text"] in ("-4", "4", "−4") for x in result["labels"])
    plt.close(fig)


def test_legend_covering_bar_rejected(tmp_path):
    fig, ax = plt.subplots()
    ax.bar([0], [1], width=1, label="data")
    ax.legend(loc="center")
    result = inspect_figure(fig, tmp_path / "bars.json")
    assert any(x["kind"] == "patch_legend_overlap" for x in result["collisions"])
    plt.close(fig)


def test_opposite_route_and_legal_tree_fork():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/figure-polish"))
    from check_drawio import coincident_routes
    cells = [{"role": "edge", "id": "in", "source": "a", "target": "b"},
             {"role": "edge", "id": "out", "source": "b", "target": "c"}]
    points = lambda a, b: [{"x": a, "y": 0}, {"x": b, "y": 0}]
    measured = {"cells": {"in": {"route": points(0, 100)}, "out": {"route": points(100, 40)}}}
    assert coincident_routes(cells, measured)[0]["shared_run_u"] == 60
    cells[1]["source"] = "a"
    assert not coincident_routes(cells, measured)


def test_arrow_dummy_vertex_is_not_a_painted_segment(tmp_path):
    from matplotlib.patches import FancyArrowPatch
    fig, ax = plt.subplots()
    ax.add_patch(FancyArrowPatch((.2, .8), (.8, .8), arrowstyle="-|>", mutation_scale=15))
    text = ax.text(.5, .2, "legal below arrow", ha="center", va="center")
    legal = inspect_figure(fig, tmp_path / "arrow_legal.json")
    assert not any(x["kind"] == "arrow_text" for x in legal["collisions"])
    text.set_position((.5, .8))
    bad = inspect_figure(fig, tmp_path / "arrow_bad.json")
    assert any(x["kind"] == "arrow_text" for x in bad["collisions"])
    plt.close(fig)


def test_unanchored_routes_not_treated_as_same_source_tree():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/figure-polish"))
    from check_drawio import coincident_routes
    cells = [{"role": "edge", "id": "a", "source": None, "target": None},
             {"role": "edge", "id": "b", "source": None, "target": None}]
    points = [{"x": 0, "y": 0}, {"x": 100, "y": 0}]
    measured = {"cells": {"a": {"route": points}, "b": {"route": points}}}
    assert coincident_routes(cells, measured)


def test_label_on_spine_rejected_and_margin_is_legal(tmp_path):
    fig, ax = plt.subplots()
    label = ax.text(.5, 1., "touches top border", transform=ax.transAxes, ha="center", va="center")
    bad = inspect_figure(fig, tmp_path / "spine_bad.json")
    assert any(x["kind"] == "spine_text_or_legend" for x in bad["collisions"])
    label.set_position((.5, .8))
    legal = inspect_figure(fig, tmp_path / "spine_legal.json")
    assert not any(x["kind"] == "spine_text_or_legend" for x in legal["collisions"])
    plt.close(fig)


def test_disabled_axis_spines_are_not_painted(tmp_path):
    fig, ax = plt.subplots()
    ax.axis('off')
    ax.text(.5, 0, 'legal text on invisible axis boundary', ha='center', va='center')
    legal = inspect_figure(fig, tmp_path / 'axis_off.json')
    assert not any(x['kind'] == 'spine_text_or_legend' for x in legal['collisions'])
    plt.close(fig)


def test_hidden_twin_axis_labels_not_counted(tmp_path):
    fig, ax = plt.subplots()
    ax.set_xticks([0, .5, 1])
    twin = ax.twinx()
    assert not twin.xaxis.get_visible()
    result = inspect_figure(fig, tmp_path / 'twin_axis.json')
    assert not any(x['kind'] == 'text_text' for x in result['collisions'])
    twin.xaxis.set_visible(True)
    result = inspect_figure(fig, tmp_path / 'mutated_twin_axis.json')
    assert any(x['kind'] == 'text_text' for x in result['collisions'])
    plt.close(fig)
