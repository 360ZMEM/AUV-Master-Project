# ADC-TMR full-chain noise integration replay

## Scope

This experiment uses the local `hardware_wrappers/fangkong_adc/raw_data` NPZ captures.
It is a dorm-room full-chain background/noise replay, not a calibrated lab noise-floor certification.
The 45 Hz target is kept separate from the 50 Hz mains component so the result can support the thesis simulation-to-hardware narrative.

## One-command reproduction

```bash
real_experiments/mag_chain_noise/run.sh
```

## Background records used for the default replay

| file | duration (s) | RMS after detrend (nT) | 45 Hz lock-in (nT) | 50 Hz lock-in (nT) | peak (Hz) | max axis corr |
|---|---:|---:|---:|---:|---:|---:|
| `1780675809_291477.npz` | 3.920 | 244.874 | 4.910 | 305.916 | 50.00 | 1.000 |
| `1780676130_241387.npz` | 9.184 | 80.234 | 0.258 | 32.652 | 50.00 | 0.844 |

## Derived replay profile

- background records: 2
- total background duration: 13.104 s
- median 45 Hz vector lock-in: 2.584 nT
- median 50 Hz vector lock-in: 169.284 nT
- median high-band vector ASD: 0.133 nT/sqrt(Hz)
- vector RMS after linear detrend: 149.825 nT

## Noise-injected Biot-Savart semi-physical replay

Reference plot uses `1780675809_291477.npz`.

| noise file | windows | clean peak (nT) | replay RMSE (nT) | Gaussian RMSE (nT) | replay error/peak |
|---|---:|---:|---:|---:|---:|
| `1780675809_291477.npz` | 59 | 2326.8 | 0.792 | 4.307 | 0.034% |
| `1780676130_241387.npz` | 164 | 2552.2 | 0.271 | 1.276 | 0.011% |

## Existing Biot-Savart joint inversion audit

- aligned lock-in/pose pairs: 777
- lock-in frequency: 45.0 Hz
- peak current used by fixed model: 2.614048 A
- complex I/Q free-scale R2: 0.8792
- complex I/Q fixed-current R2: 0.8711
- free-scale equivalent current: 2.8789 A

## Thesis-use boundary

- Use this as a semi-physical replay and full-chain background-noise support.
- Do not write it as a calibrated laboratory noise-floor or complete AUV field acceptance test.
- Keep the 50 Hz mains component as an environmental interference term; the controlled target remains 45 Hz.
