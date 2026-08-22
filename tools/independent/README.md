# Independent magnetic-field visualizations

These scripts generate the qualitative figures used in thesis Section 2.3.
They do not import project simulation modules or read experiment data.

## Requirements

- Python 3.9+
- NumPy
- Matplotlib

## Run

```bash
python3 tools/independent/plot_single_phase_field.py
python3 tools/independent/plot_three_phase_helical_field.py
python3 tools/independent/plot_fwhm_depth_principle.py
```

Each script writes PDF and 300 dpi PNG files to
`docs/thesis/figures/magnetics/` by default. Use `--output-dir PATH` to select
another directory.

## Models and scope

- `plot_single_phase_field.py` uses the analytic infinite-wire field
  `B = mu0 I / (2 pi r)`.
- `plot_three_phase_helical_field.py` discretizes seven pitches of three
  helical conductor centerlines and directly sums finite current elements with
  the Biot-Savart law. Only the central three pitches are plotted to reduce end
  effects. The cable is ideal, balanced, unarmored, and noise-free.
- `plot_fwhm_depth_principle.py` uses the far-field dipole envelope
  `B(x) = C / (x^2 + z^2)`. It is an analytic illustration, not an estimator
  accuracy experiment.

All parameters are fixed in the scripts and no random input is used.
