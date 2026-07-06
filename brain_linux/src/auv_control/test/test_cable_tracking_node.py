from types import SimpleNamespace

import pytest
import rclpy

from auv_decision_ros.cable_tracking_node import CableTrackingNode


def _summary_node() -> CableTrackingNode:
    node = CableTrackingNode.__new__(CableTrackingNode)
    node.acceptance_cfg = {
        "burial_target_m": 1.5,
        "max_route_offset_m": 2.0,
        "max_burial_sigma_m": 0.15,
        "min_confidence": 0.65,
    }
    return node


def _tracking(**overrides) -> SimpleNamespace:
    defaults = {
        "cross_track_m": 0.4,
        "burial_depth_m": 1.6,
        "burial_sigma_m": 0.08,
        "confidence": 0.9,
        "diagnostics": {"industrial_ready": True},
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_node_registers_dlt1278_monitoring_publishers():
    rclpy.init()
    node = None
    try:
        node = CableTrackingNode()
        topics = {name for name, _types in node.get_topic_names_and_types()}
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()

    assert "/auv/cable/dlt1278_summary" in topics
    assert "/auv/cable/dlt1278_state" in topics
    assert "/auv/cable/dlt1278_total_score" in topics
    assert "/auv/cable/industrial_acceptance_pass" in topics


def test_dlt1278_runtime_summary_scores_current_report_items():
    node = _summary_node()
    tracking = _tracking(cross_track_m=2.4, burial_depth_m=1.2, burial_sigma_m=0.22)

    summary = node._build_dlt1278_runtime_summary(
        tracking=tracking,
        acceptance_flags=["route_offset_over_limit", "burial_uncertainty_over_limit"],
        quality_flags=["low_snr"],
        industrial_ready=False,
    )

    assert summary["state"] == "注意状态"
    assert summary["total_score"] == 32
    assert summary["worst_single_score"] == 16
    assert summary["industrial_conclusion_readiness"] == "limited"
    assert summary["industrial_acceptance_pass"] is False
    assert [item["item"] for item in summary["score_items"]] == [
        "海缆位移",
        "海缆埋深不足",
        "埋深估计精度未达 0.15m",
    ]
    assert "operator_view/*.png" in summary["output_products"]


def test_dlt1278_summary_text_contains_operator_fields():
    node = _summary_node()
    summary = {
        "state": "注意状态",
        "total_score": 24,
        "industrial_conclusion_readiness": "ready",
        "industrial_acceptance_pass": True,
        "acceptance_flags": [],
        "score_items": [
            {"item": "海缆埋深不足", "level": "III", "score": 16},
            {"item": "埋深估计精度未达 0.15m", "level": "II", "score": 8},
        ],
        "output_products": [
            "tracking.jsonl",
            "inspection_summary.json",
            "dlt1278_report.md",
            "operator_view/*.png",
        ],
    }

    text = node._build_dlt1278_summary_text(summary)

    assert "DL/T 1278风格状态: 注意状态" in text
    assert "总分: 24" in text
    assert "pass: True" in text
    assert "海缆埋深不足(III, 16分)" in text
    assert "验收标志: none" in text
    assert "dlt1278_report.md" in text


def test_acceptance_flags_block_industrial_ready_and_pass():
    node = _summary_node()
    tracking = _tracking(confidence=0.4)

    acceptance_flags = node._acceptance_flags(tracking)
    industrial_ready = bool(tracking.diagnostics["industrial_ready"]) and not acceptance_flags
    summary = node._build_dlt1278_runtime_summary(
        tracking=tracking,
        acceptance_flags=acceptance_flags,
        quality_flags=[],
        industrial_ready=industrial_ready,
    )

    assert acceptance_flags == ["confidence_below_limit"]
    assert industrial_ready is False
    assert summary["industrial_conclusion_readiness"] == "limited"
    assert summary["industrial_acceptance_pass"] is False
