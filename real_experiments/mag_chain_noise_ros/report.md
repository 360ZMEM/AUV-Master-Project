# ADC-TMR measured replay ROS comparison

This report is generated from the Linux-side ROS2 Direction A cable-loop replay.
Noise is added only to `/auv/sensors/magnetic`; cable, terrain, current, and vehicle truth are unchanged.

## Summary

| mode | tracking samples | cross-track p95 (m) | confidence mean | mag SNR mean (dB) | noise p95 (nT) | prior observed | prior accepted | ready ratio | pass ratio | control-rate RMS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| none | 157 | 7.762 | 0.8472 | 108.3 | 0 | 1 | 1 | 0 | 0 | 0.06319 |
| covariance_gaussian | 159 | 7.766 | 0.8473 | 108.3 | 268.1 | 1 | 1 | 0 | 0 | 0.06329 |
| measured_replay | 158 | 7.767 | 0.8477 | 108.3 | 180 | 1 | 1 | 0 | 0 | 0.06346 |

## Provenance

- Source experiment package: `real_experiments/mag_chain_noise_ros/`.
- Default noise profile: `real_experiments/mag_chain_noise/data/noise_profile.json`.
- Default measured records: `hardware_wrappers/fangkong_adc/raw_data/1780675809_291477.npz`, `hardware_wrappers/fangkong_adc/raw_data/1780676130_241387.npz`.
- ROS entrypoint: `scripts/run_direction_a_decoupled_cable_sim.sh` with `AUV_MAG_NOISE_MODE`.
- Summary table: `real_experiments/mag_chain_noise_ros/data/summary.csv`.

## Thesis Anchors

- Chapter 5 table: `tab:ch05-mag-chain-noise-ros`.
- Chapter 5 figure: `fig:ch05-mag-chain-noise-ros`.
- Thesis figure source: `docs/thesis/figures/experiments/mag_chain_noise_ros/_SOURCE.md`.

## Boundaries

- This is a semi-physical observation replay, not a full AUV wet test.
- The Direction A decoupled loop is used as a ROS observation-injection gate, not as an industrial acceptance run; `industrial_ready` and `industrial_acceptance_pass` are not the conclusion metrics here.
- The measured background is a dorm-room full-chain record with a strong 50 Hz environmental component; it is a stress input, not a metrology-grade laboratory noise floor.
- Records shorter than the closed-loop run are explicitly looped in `measured_replay` mode.

## Figures

- `/home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/figures/experiments/mag_chain_noise_ros/mag_chain_noise_ros_comparison.png`
- `/home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/figures/experiments/mag_chain_noise_ros/mag_chain_noise_ros_comparison.pdf`
