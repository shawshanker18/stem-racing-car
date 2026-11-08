# setup — the rebuild's base branch (done before the agent chats)
Updated: 2026-11-08

## Done
- Bible (Parts 0-8), architecture review, briefing, agent prompts — `bible/`, `agents/`.
- **Part 1 code**: container image definition, worker, dispatch/collect across accounts, compute
  repository setup, batch format, job-split test. Not yet run on the farm (chat A does that).
- **Part 2 complete**: carving loop, adjoint solver, pattern search, four-grid modules and lab
  workflows retired; live pieces moved to `car/pipeline.py`, `car/space.py`, `body/sdf.py`;
  `docs/HISTORY.md`; golden fingerprints G1-G3. Evidence: G1 rebuilt after every step and after the
  folder restructure compares "same car".
- **Part 3 code**: `measure/` scripts (thrust, masses, densities, coast-down, spin-down, inertia,
  tether, track, air), `inputs/measured.json` with every input marked unmeasured. 8 tests on
  synthetic data with known answers.
- **Part 4 model**: `race/race_model.py` (NumPy), wired into `car/pipeline.py` and `car/run_car.py`;
  JAX model retired. Regression against the old model: 1.555837 s vs 1.555827 s, 0.475 ms/mN,
  16.63 ms/g. 9 tests including analytic cases and launch pitch.
- **Restructure**: `part1-simulation` → `body`, `part4-simulation` → `components`,
  `part5-simulation` → `car`, `part2-simulation` → `cfd` + `race`; `part3-simulation` retired.
- **Regulation answers** read from the PDF into `bible/05_RULES_LEGALITY_MASS.md` section 5.1.1.
- `cfd/morph.py` and `search/gp.py` exist as tested standalone modules (solver, file I/O, GP
  search on a known function).

## Test evidence (local, Windows, Python 3.13, `docker/requirements.lock`)
- race 19 passed; cfd 94 passed; components 15 passed; car 13 passed (includes a whole car built
  end to end); measure 8 passed; compute 2 passed; body 177 passed (after the symmetry fix below).

## Blocked on people
- Everything in Part 3 (lab measurements) and the Part 4 validation (timed runs of a real car).

## Gate
- [x] Part 2 exit gate (except "pull request merged by the user": the base branch is open as a PR).
- Fixed a test that already failed on the original code: `body/unified_phi.py` build rules used unrounded y coordinates, so the nose stub kept a column on one side only (`test_masks_and_labels_are_exactly_symmetric`). Golden G1 unchanged.
- CI on `rebuild/bible` at 1baa98f: every test shard and the golden check pass on Linux; the container image builds (`image.yml` run 42471594877, digest `sha256:8e03640afc61c8a15eeabf6a43d09ba400f33c21417f46737b72d7e82ee6eb0c`, pushed to `ghcr.io/shawshanker18/stem-cfd`, still private). Chat A: put that digest in `compute/accounts.json`, ask the user to make the package public, then continue Part 1 from step 5.
