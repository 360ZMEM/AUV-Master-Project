"""Regression for in-route rejoin samples omitted by the first draft audit."""
import csv
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'simulation_closure_audit', Path(__file__).resolve().parents[1]/'tools/audit_v2_simulation_closure.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def trace(tmp_path, *, hidden_rejoin_error=False, missing_track_sample=False):
    rows=[]
    for i,x in enumerate([-20.,-10.,4.9,5.,15.,25.,35.,45.,55.,65.,75.,80.]):
        mode = 'search' if i==0 else ('confirm' if i==1 else 'track')
        correction = hidden_rejoin_error and 5.<x<75.
        rows.append(dict(time_s=i*.25,x_m=x,y_m=7.5 if correction else 6.2,
            heading_deg=0.,speed_mps=.3,magnetic_nt=10.,estimated_cable_y_m=6.,
            encoded_rpm=0 if x==80. else 200,
            depth_valid='False',endpoint_complete='True' if x==80. else 'False',
            mode='hold' if missing_track_sample and x==35. else mode,
            stage='rejoin_estimated_cable' if correction else 'inspect_along_cable',
            lateral_valid='True' if mode=='track' else 'False',reason=''))
    p=tmp_path/'wire_seed_101.csv'
    with p.open('w',newline='') as s:
        writer=csv.DictWriter(s,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
    return dict(source=p.name,ticks=len(rows),completed=True,case='wire',seed=101)


def test_in_route_rejoin_error_cannot_be_hidden_by_stage_label(tmp_path):
    summary=trace(tmp_path,hidden_rejoin_error=True)
    # The inspection-labelled subset is accurate; the entire core exceeds 1 m.
    with pytest.raises(AssertionError):
        module.audit(summary,tmp_path)


def test_core_hold_cannot_be_dropped_from_complete_route(tmp_path):
    summary=trace(tmp_path,missing_track_sample=True)
    with pytest.raises(AssertionError):
        module.audit(summary,tmp_path)


def test_complete_core_is_checked_independently_of_summary_metrics(tmp_path):
    summary=trace(tmp_path)
    summary['tracking_mae_m']=999.  # Auditor recomputes from actual trajectory.
    result=module.audit(summary,tmp_path)
    assert result['core_mean_true_offset_m']==pytest.approx(.2)
    assert result['core_sample_count']==8
