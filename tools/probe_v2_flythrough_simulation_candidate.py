#!/usr/bin/env python3
"""Reuse the native-PVS fixture with the already documented F run-in policy.

The test-only factory supplies explicit parameters; magnetic production code,
PVS dynamics and PID equations are unchanged. The source is known and isolated.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import probe_v2_flythrough_pvs as fixture
from auv_mag_tracking.v2 import FlythroughConfig, write_experiment_manifest

POLICY = FlythroughConfig(
    side_hint_required=True, side_hint_min_m=2., side_hint_max_m=8.,
    side_hint_source='synthetic_test_fixture', minimum_halfmax_tail_m=7.,
    rejoin_runin_m=20., route_quality_mean_limit_m=1.,
    route_quality_max_limit_m=2., route_quality_min_samples=200,
)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seed-start',type=int,default=101)
    p.add_argument('--seeds',type=int,default=1)
    p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args()
    production_class=fixture.FlythroughInspectionPipelineV2
    def configured(*a,**kw):
        return production_class(*a,flythrough_config=POLICY,**kw)
    results=[]
    with patch.object(fixture,'FlythroughInspectionPipelineV2',configured):
        for case in ('wire','dipole','no_source'):
            for seed in range(args.seed_start,args.seed_start+args.seeds):
                result=fixture.run(case,seed,args.output_dir,1600.)
                results.append(result)
                print(json.dumps(result),flush=True)
    summary=args.output_dir/'summary.json'
    summary.write_text(json.dumps(results,indent=2)+'\n')
    config=fixture.manifest_config(['wire','dipole','no_source'],args.seed_start,args.seeds,1600.)
    config['flythrough_policy']=asdict(POLICY)
    config['source_sha256']['tools/probe_v2_flythrough_simulation_candidate.py']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    write_experiment_manifest(args.output_dir,experiment='current_F_runin_native_pvs_simulation',
        config=config,artifact_paths=[summary,*args.output_dir.glob('*.csv')],repository_root=fixture.ROOT)


if __name__=='__main__':
    main()
