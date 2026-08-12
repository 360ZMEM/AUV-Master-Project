from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.summarize_adc_enob_evidence import build_summary


def test_enob_summary_preserves_sensitivity_accuracy_boundary() -> None:
    source_path = (
        Path(__file__).resolve().parent.parent
        / "hardware_wrappers"
        / "fangkong_adc"
        / "raw_data"
        / "enob"
        / "20260809T161036"
        / "ch4_enob_results.json"
    )
    source = json.loads(source_path.read_text(encoding="utf-8"))

    summary = build_summary(source, source_path)

    assert summary["wideband_noise"]["noise_enob_bits"] == pytest.approx(
        16.8768347044
    )
    assert summary["oversampling"]["noise_enob_bits"] == pytest.approx(
        18.3420861033
    )
    assert summary["adc"]["nominal_lsb_equivalent_nt"] == pytest.approx(
        0.0596046448
    )
    assert summary["lockin_45hz"]["vector_rms_below_target"] is True
    assert summary["lockin_45hz"]["quadrature_3sigma_below_target"] is False
    assert any(
        "absolute accuracy" in item
        for item in summary["interpretation"]["not_supported"]
    )
