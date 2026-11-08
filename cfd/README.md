# cfd — OpenFOAM airflow for a half car, and mesh morphing

Part of the STEM Racing car optimiser; see the repository README and `bible/`.

| module | what |
|---|---|
| `openfoam_case.py` | the forward CFD case for a half car on ESI OpenFOAM v2412: domain (3 lengths ahead, 8 behind, symmetry plane, moving ground), snappyHexMesh with wake boxes, k-omega SST, Spalding wall function or a wall-resolved (y+ <= 2) layer stack, every component as its own patch (wheels as rotating walls), forces per patch, y+ distribution per patch |
| `cfd_wrapper.py` | `run_half_car_cfd`: validate the STL, run the case, return full-car drag and lift with health (residual, standard error and drift of the force mean); `run_half_car_adjoint` for the drag adjoint |
| `openfoam_adjoint.py` | the adjoint case (`adjointOptimisationFoam`, frozen turbulence); it failed its gradient check, so it is kept only for an optional sensitivity map (bible Part 7 section 7.5.3) |
| `morph.py` | deforms a family base mesh onto a nearby candidate car, for low-noise paired CFD (bible Part 6) |

Resolutions (`resolution=`): `coarse`, `medium` (the search, ~0.65 M cells with the wake
boxes), `fine`, `resolved` (~5 M cells, wall-resolved).

```bash
pip install -r ../body/requirements.txt
python -m pytest tests -q
```
