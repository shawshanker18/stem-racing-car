<p align="center"><img src="assets/banner.png" alt="part2-simulation" width="100%"></p>

> How much the air costs a car, and what it means.

| | |
|---|---|
| **What it is** | Airflow simulation for a half car, and the race time model that turns drag into seconds. |
| **Source** | Private |
| **Public overview** | https://github.com/shawshanker18/stem-racing-car |

**The STEM Racing set**

| Part | Repository |
|---|---|
| 1 | [part1-simulation](https://github.com/shawshanker18/part1-simulation) |
| 2 | [part2-simulation](https://github.com/shawshanker18/part2-simulation) |
| 3 | [part3-simulation](https://github.com/shawshanker18/part3-simulation) (retired: its live code moved to part5 `pipeline.py`) |
| 4 | [part4-simulation](https://github.com/shawshanker18/part4-simulation) |
| 5 | [part5-simulation](https://github.com/shawshanker18/part5-simulation) |

---

| module | what |
|---|---|
| `openfoam_case.py` | the forward CFD case for a half car on ESI OpenFOAM v2412: domain (3 lengths ahead, 8 behind, symmetry plane, moving ground), snappyHexMesh with wake boxes, k-omega SST, Spalding wall function or a wall-resolved (y+ <= 2) layer stack, every Part 4 part as its own patch (wheels as rotating walls), forces per patch, y+ distribution per patch |
| `cfd_wrapper.py` | `run_half_car_cfd`: validate the STL, run the case, return full-car drag and lift with health (residual, standard error and drift of the force mean); `run_half_car_adjoint` for the drag adjoint |
| `openfoam_adjoint.py` | the adjoint case (`adjointOptimisationFoam`, frozen turbulence); it failed its gradient check, so it is kept only for an optional sensitivity map (bible Part 7 section 7.5.3) |
| `race_model.py` | the 20 m race model (NumPy): measured thrust curve, aero drag and lift with a speed exponent, rolling resistance on each axle, constant and bearing resistance, tether-guide rub when a wheel lifts, launch pitch from thrust height against centre-of-mass height, wheel inertia per axle; exchange rates; Monte Carlo uncertainty. Inputs come from `inputs/measured.json` (bible Part 4) |
| `morph.py` | deforms a family base mesh onto a nearby candidate car, for low-noise paired CFD (bible Part 6) |
| `physics_contract.py`, `mass_com_ingest.py` | units and the half-car contract, mass and COM of the whole car |

Resolutions (`resolution=`): `coarse`, `medium` (the search, ~0.65 M cells with the wake
boxes), `fine`, `resolved` (~5 M cells, wall-resolved).

```bash
pip install -r ../part1-simulation/requirements.txt
python -m pytest tests -q
```
