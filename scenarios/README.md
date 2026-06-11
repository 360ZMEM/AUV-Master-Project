# Thesis Experiment Scenarios

This directory contains scenario presets used by `tools/run_thesis_sweep.py` and forwarded by `scripts/start_experiment.sh --scenario <yaml> --seed <int>`.

A scenario yaml is consumed by:
- `sim_holoocean/interfaces/mock_amd_chaos.py` (chaos profile)
- `sim_holoocean/interfaces/perception_engine.py` (sensor noise)
- `algorithm/auv_mpc_controller.py` (MPC mode override; via `AUV_MPC_MODE`)

Schema:
```yaml
name: short-id          # used in output dir naming
description: free text
duration_s: 120         # default run length
sim_backend: pvs        # pvs|holoocean
mpc_mode: ua            # baseline|ua, optional
chaos:
  enabled: true
  packet_loss_prob: 0.0
  dvl_freeze:
    enabled: false
    drop_rate: 0.0
    freeze_window_s: [0.0, 0.0]
  imu_drift:
    enabled: false
    bias_rate: 0.0
  depth_spike:
    enabled: false
    rate_hz: 0.0
    amplitude_m: 0.0
  mag_saturation_threshold_t: null
perception:
  imu_acc_noise_scale: 1.0
  sonar_noise_scale: 1.0
  cable_current_amp: 500.0
flow:
  current_speed_mps: 0.0
```

Files in this directory:
- `scenario_baseline.yaml` — clean run, all chaos disabled
- `scenario_dvl_dropout_{10,30,60,90}.yaml` — DVL drop rate sweep
- `scenario_mag_distortion_{light,heavy}.yaml` — magnetic saturation
- `scenario_sonar_clutter.yaml` — sonar noise inflation
- `scenario_combined_stress.yaml` — composite stress test

Used by the sweep driver (`tools/run_thesis_sweep.py`):
```
python3 tools/run_thesis_sweep.py \
  --scenarios baseline,dvl_dropout_30 \
  --seeds 0,1,2,3,4 \
  --mpc-modes ua
```
