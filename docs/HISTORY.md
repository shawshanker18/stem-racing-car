# History of retired methods

This file records the methods the project tried and retired, what each measured, and why it
was retired. The code for them was deleted in the rebuild (bible Part 2); it remains in git
history (commit `3332323` on `main` and the `fix/rules-and-block` branches of the
`partN-simulation` repositories are the last versions that contain it).

All race times below are **model time** on the synthetic thrust curve
(`part2-simulation/co2_thrust_data.csv`, about 60% of a real cartridge's impulse), not real
time.

## Level-set carving with the drag adjoint

Repo folders `part1-simulation` (`phi_updater.py`), `part3-simulation` (`inner_loop.py` and
its contract, convergence, gradient-combiner, stability and penalty modules). Retired on
2026-09-30, briefly revived on 2026-11-08 (`run_car.py --phi-npy`, `stress_cars.py --carve`).

The body was a signed-distance field on a voxel grid, started as the full legal block, and
moved by a Hamilton-Jacobi update driven by the adjoint drag sensitivity plus mass and
centre-of-mass gradients.

- The sign of the aero term was flipped twice. The surface did not move until a redistancing
  fix. For a long period the drag term was dead and the mass term carried about 94% of every
  update.
- On coarse and medium meshes, with 1 mm and 0.3 mm trust radii, 12 of 12 drag steps raised
  drag by 2.7-5%. One 0.3 mm step on the medium mesh ranked correctly (descent −1.3%,
  zero-size step −0.7%, ascent +0.9%), a signal the size of the noise.
- Body drag was not monotonic in carve depth (0.5 g reserve 0.389 N, 1.5 g 0.405 N, 3 g
  0.394 N, 5 g 0.400 N, 8 g 0.400 N).
- The November 2026 review found two numerical bugs in the operator: the upwind branch was
  chosen by the sign of φ instead of the sign of the velocity (`_godunov_gradient` reused by
  `hj_update`), and the velocity extension was built on unsigned gradient magnitudes, so
  its "normals" were never negative.
- The "full block" start field (`build_unified_geometry(init_mode="full")`) was a constant
  −dx, not a signed distance, so mass sizing by skin offset either did nothing or flipped all
  air to solid (+9.5 g off target in a 2 mm test).
- The legal envelope after mandatory air weighs about 50.3 g of foam at 1 mm grid against a
  body target of about 33 g: there was little block to carve.

## The drag adjoint as a gradient

Repo folder `part2-simulation` (`openfoam_adjoint.py`, `adjoint_contract.py`).

`adjointOptimisationFoam` (ESI v2412), kOmegaSST primal, adjoint turbulence frozen
(`adjointLaminar`) after `adjointkOmegaSST` crashed with SIGFPE at adjoint iteration 277.

- Gradient check 2026-09-28: right sign on 3 of 8 settings, r = 0.45.
- Pre-registered check November 2026 (sign share ≥ 0.8 and r ≥ 0.8 on 12 settings): r ≈ 0.
  Failed. The solver state then recorded a pass on a different test (a nine-point line test
  along the adjoint direction: drag fell overall from −2 to +2 mm but was non-monotone at
  0.5-1 mm). The bible treats the original test as the verdict.
- 21% of surface vertices had no sensitivity point within 5 mm on the medium mesh.

`openfoam_adjoint.py` is kept for one optional use: a map of where on the body drag is
sensitive (bible Part 7 section 7.5.3), never to move the car.

## Pattern search

`part5-simulation/pattern.py`, 2026-09-28 to 2026-10-26.

Screen every setting of one group at ± a step with the skin held fixed, confirm candidates
re-sized to 48.2 g, accept if better by twice the noise. It found front-wing and support
improvements of 2.6-7%. Four rear-wing changes each tested 2-5 ms faster but did not add up
when combined (the rear wing's height floated with the body; bible Part 5 F24).

The parameter definitions moved to `part5-simulation/space.py`; the search logic was deleted.

## Adjoint-plus-CFD solver

`part5-simulation/solver.py`, November 2026.

8 chains from random starts; adjoint slopes projected onto the body and part settings, plus
brute-force layout steps; a step accepted when better than the chain's base by twice a 1 ms
noise floor.

- 40 rounds, 16 accepted steps (9 layout, 7 adjoint).
- Chain end times 1.5412-1.5734 s; best 1.5412 s.
- The review estimated about 8 of the 16 acceptances could be noise: accepting the best of
  about 10 candidates at 2σ accepts pure noise about 21% of the time, and the "repeat"
  measurement re-used the same mesh, so the noise was always the 1 ms floor.
- The start car mattered more (32 ms spread between chains) than the climb (0.4-23 ms).

State and batches are archived in `archive/search-2026-11/`.

## Noise experiments

`noise.yml`, `noise_var.yml`, `noise_long.yml`, `repeat.yml`, November 2026.

- The same car on 6 machines: within 0.28 ms.
- Skins 0.01 mm apart, 8 runs each: σ 1.3 ms with layers, 2.2 ms with "better" layers,
  1.0 ms with no layers. 5,000 iterations changed nothing.
- Fine mesh without layers: σ ≈ 0.95 ms, about 4.4 hours per car.
- Conclusion: the noise comes from remeshing, not from the solver. Bible Part 6 replaces
  remeshing between neighbours with mesh morphing.

## Lab workflows

`.github/lab/*.py` and their workflows (`adj_lab`, `line_lab`, `impact`, `impact_wheels`,
`body_lab`, `pinch_lab`, `smooth`, `car_debug`, `car_libs`, `render_lab`).

- `adj_lab`: adjoint slopes weighted several ways (as-is, × area, / area, clipped) against
  CFD slopes, with and without layers; none correlated well.
- `line_lab`: the line test above.
- `impact`: rear-wing variants, support discs, wheel rounding. Rounded wheels are illegal
  under T7.4 (contact width is measured without fillets).
- `pinch_lab`, `body_lab`, `smooth`: builder robustness fixes (pinches, welds, fairing).

## Body generation decision

The team's 2026-09-27/28 decision (hybrid parametric body, no ballast) and its reasoning are
in `part5-simulation/docs/BODY_GENERATION_DECISION.md`, kept unchanged as the record.
