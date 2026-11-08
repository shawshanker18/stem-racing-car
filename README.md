# STEM Racing car optimiser

Software that designs, checks and measures a STEM Racing Professional Class car.
The part folders must stay side by side. Start with `bible/00_START_HERE.md`: it is the
complete instruction set for the rebuild, and `bible/REVIEW.md` is the review that motivated it.

| Folder | What it does |
|---|---|
| `part1-simulation` | the milled body and the rules that shape it |
| `part2-simulation` | OpenFOAM airflow and the race-time model |
| `part4-simulation` | wheels, wings, supports, nose, joints and print files |
| `part5-simulation` | runs a whole car (`run_car.py`), checks it against the rules (`legality.py`) |
| `bible/` | the rebuild instructions, Part by Part, and the architecture review |
| `compute/`, `tools/`, `docker/`, `batches/`, `results/` | CFD on GitHub Actions across team accounts (bible Part 1) |
| `measure/`, `inputs/` | lab measurement processing and the measured physical inputs (bible Part 3) |
| `search/` | the noise-aware search (bible Part 7) |
| `docs/HISTORY.md`, `archive/` | retired methods, what they measured, and their old data |

Every push runs all the tests and builds whole cars in parallel (see the Actions
tab). The STEM Racing regulations are not included: get them from the organisers.

Status: the car has not been built or track-tested. Its race times are model
numbers, not measurements, and until `inputs/measured.json` is filled in (bible Part 3)
they use a synthetic thrust curve with about 60 % of a real cartridge's impulse.
The separate repositories `partN-simulation` hold the same folders; this repository is the
combined copy the code runs from (the folders import each other).

No licence is granted. All rights reserved.
