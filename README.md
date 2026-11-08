# STEM Racing car optimiser

Software that designs, checks and measures a STEM Racing Professional Class car
(UAE Technical Regulations 2025-26): the body, the printed parts, the airflow, the race
time, the rule checks, and the search for the fastest legal car.

**Start here:** `bible/BRIEFING.md` (what every part is and where it stands), then
`bible/00_START_HERE.md` (the full instructions). `bible/REVIEW.md` is the architecture
review that started the rebuild. `agents/` holds the prompts for the Claude chats that carry
the work forward.

| Folder | What it does | Bible Part |
|---|---|---|
| `body/` | the milled body as one level-set field: rule zones, 94-setting parametric body, machining with a 6.25 mm ball end, mass sizing, surfaces | 5 |
| `components/` | wheels, wings, nose, wheel supports, tether guides, the joints that make the manufacturing files | 5 |
| `cfd/` | OpenFOAM v2412 half-car case, solve and force health; mesh morphing; the optional adjoint | 6 |
| `race/` | the 20 m race model and the whole-car mass rollup | 4 |
| `car/` | one car end to end (`run_car.py`), the rule checks (`legality.py`), the search space (`space.py`) | 5, 8 |
| `compute/`, `docker/`, `batches/`, `results/` | CFD on GitHub Actions across team accounts with the GitHub CLI | 1 |
| `measure/`, `inputs/` | lab measurement processing and every physical input, with provenance | 3 |
| `search/` | the noise-aware search (Gaussian process, morph polish) | 7 |
| `golden/` | fingerprints of reference cars: a change must not alter them unless it says why | 2 |
| `docs/HISTORY.md`, `archive/` | retired methods, what they measured, and their old data | 2 |

All folders sit side by side; modules import each other by name (`car/paths.py` puts the
folders on the import path). Every push runs every folder's tests, the golden-car check and
whole cars in parallel (`.github/workflows/tests.yml`).

```bash
cd car && python run_car.py --out ../out/start --body-json '{}'          # the start car, no CFD
cd car && python run_car.py --out ../out/start --body-json '{}' --cfd --res medium
```

Status: the car has not been built or track-tested. Race times are model numbers. Until
`inputs/measured.json` is filled in from the lab (bible Part 3) they use a synthetic thrust
curve with about 60 % of a real cartridge's impulse, and every report says so.

The separate repositories `part1-simulation` … `part5-simulation` are superseded by this
layout (their folders became `body`, `cfd` + `race`, the retired part 3, `components` and
`car`). The STEM Racing regulations PDF is not in this public repository.

No licence is granted. All rights reserved.
