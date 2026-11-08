# measure

Turns the team's lab files (`inputs/raw/<experiment>/<date>/`) into the physical inputs in
`inputs/measured.json`. Read `bible/03_PHYSICAL_MEASUREMENTS.md` first: it says what to build,
what to record, and the safety rules for cartridge firings.

| script | experiment | writes |
|---|---|---|
| `thrust.py` | M1 thrust curve on a force sensor | `inputs/thrust_measured.csv`, `summary.json` |
| `density.py cartridges` | M2 cartridge masses | `charge_mass_g`, `cartridge_shell_g` |
| `density.py block` / `cubes` | M6 foam and printed-material density | `foam_density_gcm3`, `pa12_density_gcm3`, `pla_density_gcm3` |
| `coastdown.py` | M3 coast-down | `fit.json` (R0, mu) |
| `spindown.py` | M4 bearing spin-down | `bearing_tau0_Nm`, `bearing_k_Nms` |
| `inertia.py` | M5 wheel inertia | `wheel_I_front_kgm2`, `wheel_I_rear_kgm2` |
| `tether.py` | M7 guide-on-line friction | `mu_guide` |
| `track.py` | M9 timed runs | `track_noise_s`, `air_density_kgm3` |
| `air.py` | air density from temperature, pressure, humidity | — |
| `record.py` | writes one value with its provenance; lists the unmeasured inputs | — |

`python -m pytest tests -q` checks every script on synthetic data with a known answer.
