# car — one car end to end, its rule checks, and the search space

Part of the STEM Racing car optimiser; see the repository README and `bible/`.

Runs one car through all five parts, audits it like a scrutineer, measures it in CFD
with every part in the flow, searches the body shape, and writes a report with ranked,
quantified recommendations.

The car as built today (team decisions 2026-09-27/28, see
`docs/BODY_GENERATION_DECISION.md`): a parametric "hybrid" body
(`body/param_body.py`: 8-station loft + 56 sculpt modes), milled with a 6.25 mm ball end
from four sides, printed PA12 positives glued into milled pockets
(`components/joints.py`), one-piece beam supports with printed stub axles and one 3x6x2.5 bearing
per wheel, the team's STL wheels in PA12, a PA12 nose shell, and NO ballast: the
body volume is sized so the car weighs 48.2 g.

| file | what |
|---|---|
| `run_car.py` | the pipeline: parametric body (body) sized so the car as manufactured weighs 48.2 g → parts, pockets and manufacturing files (components) → legality → CFD with every part (cfd) → report |
| `pipeline.py` | the four steps between geometry and race time (CFD-ready STL, mass report, CFD, race objective); was part3-simulation's binding layer |
| `space.py` | every searchable setting: name, step, bounds, and how to read or change it in a car description |
| `legality.py` | 117 entries on the start car (bible Part 5 separates rule checks from design constants) on the assembled car: T3.4–T3.7, T4.1, T5.5 (on the milled body), T7.3, T7.13 hang-test claw, T8.2, T8.5.1, T9.4.2, Model Block, T3.6 on the manufactured mass, every part attached, every manufacturing file a closed solid, plus every components gate |
| `render.py` | a picture of a built car |
| `checks/golden.py` | fingerprints a built car so a change can prove it altered nothing (`golden/` at the root holds the references) |
| `checks/stress_cars.py` | builder robustness on random cars at a fixed skin |

```bash
python run_car.py --out results/                                  # the start car, no CFD, ~6 min (sizing)
python run_car.py --out results/ --body-json "$(cat checks/round2_car.json)" --cfd --res medium
python -m pytest tests -q
```

The folders `body`, `cfd` and `components` must sit beside this one.
The old searches (`pattern.py`, `solver.py`) were retired; see `docs/HISTORY.md`.
