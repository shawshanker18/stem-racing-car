# race — the 20 m race model

Part of the STEM Racing car optimiser; see the repository README and `bible/04_RACE_MODEL.md`.

| file | what |
|---|---|
| `race_model.py` | the 20 m race model (NumPy): measured thrust curve, aero drag and lift with a speed exponent, rolling resistance on each axle, constant and bearing resistance, tether-guide rub when a wheel lifts, launch pitch from thrust-line height against centre-of-mass height, wheel inertia per axle; exchange rates (ms per mN, per gram, ...); Monte Carlo uncertainty |
| `mass_com_ingest.py` | mass and centre of mass of the whole car from the body's components and the fixed hardware |
| `co2_thrust_data.csv` | the SYNTHETIC thrust curve in use until `inputs/measured.json` names a measured one (bible Part 3) |

Inputs come from `inputs/measured.json`; every report lists the ones that are not measured yet.

```bash
python -m pytest tests -q
```
