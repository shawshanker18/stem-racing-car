# Part 2 — Cleanup: delete the retired methods, keep the engine

> **Status on 2026-11-08 (branch `rebuild/bible`). Owner: done.** Done on `rebuild/bible` before the agent chats started; kept as the record of what was removed and why. Evidence: `status/setup.md`, `docs/HISTORY.md`, `golden/`. The golden car was rebuilt after every step and after the folder restructure: identical.
> See `status/` for live progress and `agents/` for the chat prompts.

Read `00_START_HERE.md` first. This Part removes the code for methods that are retired (level-set carving, the adjoint-steered solver, the old pattern search, the four-grid geometry era) without changing what the remaining pipeline produces. Every later Part is easier and safer on a smaller codebase.

**Compute budget for this Part:** the test suite (8 jobs) on every push, plus one golden-car batch (3 builds, no CFD, plus 1 CFD car) at the start and at the end. Under 3 hours of wall time in total.

---

## 2.0 Start of Part: the compute question

Ask, word for word (from `00_START_HERE.md` section 0.7):

```
QUESTION (Part 2, compute 1): How many team members are confirming that their GitHub
accounts can be used for Part 2?
Why I need it: I run the golden-car check before and after the cleanup across confirmed accounts.
Expected load for Part 2: about 10 jobs, under 3 hours. One account is enough.
```

Then ask which accounts (compute 2), check `gh auth status`, and write `compute/confirmations/part2.json` with the usernames and the user's words.

---

## 2.1 Principle: delete, do not rewrite

- **Deletion over addition.** This Part writes almost no new logic. The one new file (`car/pipeline.py`) is assembled by copying existing functions.
- **Behaviour must not change.** A "golden car" is built before the first deletion. After every deletion step, the golden car is rebuilt and compared. If anything differs, the deletion removed something live: revert that step and investigate.
- **History is written before code is deleted.** Each retired method gets a paragraph in `docs/HISTORY.md` saying what it was, what it measured, and why it was retired, with the numbers. The team's portfolio needs this story; the code does not.
- **Data is archived, never deleted.** Search states, round files and lab results move to `archive/`.

---

## 2.2 The golden car (do this first)

### 2.2.1 What it is

Three builds of fixed, deterministic cars, without CFD, plus one with CFD:

| Golden id | Command (run from `car`) | Why |
|---|---|---|
| G1 | `python run_car.py --out ../golden/G1 --body-json '{}' --skin-mm 3.93` | Start car at a fixed skin: no mass-sizing loop, so it is fast and deterministic. |
| G2 | `python run_car.py --out ../golden/G2 --body-json "$(cat checks/round2_car.json)" --skin-mm 4.2` | A car with non-default body settings. |
| G3 | `python run_car.py --out ../golden/G3 --body-json '{}'` | Start car with the full mass-sizing loop (exercises sizing, joints, manufacturing files). |
| G4 | `python run_car.py --out ../golden/G4 --body-json '{}' --skin-mm 3.93 --cfd --res medium --np 4 --cfd-iters 1000 --cfd-json '{"layer_overrides":{"nSurfaceLayers":0}}'` | One CFD solve, to prove the CFD path still works end to end. |

### 2.2.2 `checks/golden.py` (new, in `car/checks/`)

```python
"""checks/golden.py -- fingerprint a built car so a refactor can prove it changed nothing.

    python checks/golden.py fingerprint ../golden/G1 > ../golden/G1.fp.json
    python checks/golden.py compare ../golden/G1.fp.json ../golden_after/G1
Exit 0 when identical (or within tolerance for floats), 1 otherwise, with the differences printed.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

FLOAT_TOL = 1e-9


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def fingerprint(d: Path) -> dict:
    S = json.loads((d / "summary.json").read_text())
    fp = {"stl": {p.relative_to(d).as_posix(): _sha(p) for p in sorted(d.rglob("*.stl"))},
          "legality": {k: round(v["margin"], 9) for k, v in S["legality"]["checks"].items()},
          "failed": S["legality"]["summary"]["failed"],
          "mass_g": S["mass"].get("manufactured_mass_g"),
          "skin": (S.get("body", {}).get("build") or {}).get("skin_offset_mm")}
    if S.get("cfd_initial"):
        fp["D20_N"] = S["cfd_initial"]["D20_N"]
    return fp


def compare(a: dict, b: dict) -> list:
    diffs = []
    for k in sorted(set(a) | set(b)):
        x, y = a.get(k), b.get(k)
        if isinstance(x, dict) and isinstance(y, dict):
            for kk in sorted(set(x) | set(y)):
                if x.get(kk) != y.get(kk) and not (
                        isinstance(x.get(kk), float) and isinstance(y.get(kk), float)
                        and abs(x[kk] - y[kk]) <= FLOAT_TOL):
                    diffs.append(f"{k}.{kk}: {x.get(kk)} -> {y.get(kk)}")
        elif x != y and not (isinstance(x, float) and isinstance(y, float) and abs(x - y) <= FLOAT_TOL):
            diffs.append(f"{k}: {x} -> {y}")
    return diffs


if __name__ == "__main__":
    if sys.argv[1] == "fingerprint":
        print(json.dumps(fingerprint(Path(sys.argv[2])), indent=1, sort_keys=True))
    else:
        d = compare(json.loads(Path(sys.argv[2]).read_text()), fingerprint(Path(sys.argv[3])))
        print("\n".join(d) or "identical")
        sys.exit(1 if d else 0)
```

CFD drag (G4) is allowed to differ by at most 0.01% (the same geometry gives the same mesh; the review measured 0.01 ms repeatability). STL hashes must be identical. Legality margins must be identical within 1e-9. If an STL hash differs but legality and mass are identical to 1e-9, inspect the difference (it is usually vertex order) and record it in `STATUS.md` before accepting.

### 2.2.3 Running the golden set

Run G1-G3 locally if the machine can (each is minutes), and G4 on the compute farm (Part 1 batch kind `car`). Or put all four in one batch:

```bash
git switch -c part2-cleanup
# write batches/p2-golden-<date>-before.json with 4 "car" cases carrying the argv above (with --out handled by the worker)
git add batches/ && git commit -m "Part 2: golden batch (before)" && git push -u origin part2-cleanup
python compute/dispatch.py --part 2 --batch batches/p2-golden-<date>-before.json
python compute/collect.py --batch-id p2-golden-<date>-before --wait
```

For the worker to return the fingerprints, extend `compute/worker.py`'s `run_car` to call `checks/golden.py`'s `fingerprint` on the output folder and put it in the result. Commit the four fingerprints to `golden/` in the repository. These are now the reference.

---

## 2.3 What is retired, and what depends on it

### 2.3.1 Dependency map (measured on commit 9fe27ca with grep)

The live pipeline is `car/run_car.py` → Part 1 (`param_body`, `unified_phi`, `machining`, `surface_extraction`, fixed hardware modules) → Part 4 (`assembly`, `joints`, `wings`, `nose`, `beam_support`, `wheel`, `mesh_fairing`) → Part 2 (`cfd_wrapper`, `openfoam_case`, `race_objective`, `race_objective_adapter`, `mass_com_ingest`, `physics_contract`) → `legality.py`.

Live code touches retired modules in exactly these places:

| Live file:line | Imports | What is actually used | Action |
|---|---|---|---|
| `body/machining.py:71` | `phi_updater.reinitialise_sdf` | reinitialisation only | Move `reinitialise_sdf` (and the helper it calls, `_godunov_gradient`) to a new `body/sdf.py`; change the three imports. |
| `body/param_body.py:238` | `phi_updater.reinitialise_sdf` | same | same |
| `body/unified_phi.py:873` | `phi_updater.reinitialise_sdf` | same | same |
| `body/unified_phi.py:79, 1023` | `phi_grid.PhiGrid` | the grid container class | Keep `phi_grid.py`, delete its unused methods (section 2.4 step 7). |
| `body/unified_phi.py:1212` | `mass_com_calculator.ComponentMassCOM` | a dataclass | Move the dataclass into `unified_phi.py` (or import the identical one from `cfd/physics_contract.py`, which defines `ComponentMassCOM` with the same fields: check field names match first). Then delete `mass_com_calculator.py`. |
| `body/surface_extraction.py:26` | `phi_grid.PhiGrid` | type use | Keep. |
| `car/run_car.py:392` | `optimizer_contract.DEFAULT_ROLLING_MU` | one constant | Read it from `inputs/measured.json` (Part 4 creates the file; in this Part, point it at `cfd/physics_contract.DEFAULT_ROLLING_MU`, which has the same value 0.010). |
| `car/run_car.py:440-441` | `inner_loop`, `optimizer_contract` | the `--optimise` carving loop | Delete the `--optimise`, `--final-cfd`, `--adj-iters`, `--substeps`, `--trust-mm`, `--smooth-mm`, `--phi-npy` options and their code paths. |
| `car/run_car.py:193-220` | `pipeline_interface.unified_bindings` | `run_quality_gates`, `compute_mass_report`, `run_cfd`, `evaluate_objective` | Replace with `car/pipeline.py` (section 2.5). |
| `cfd/cfd_wrapper.py:436-437` | `openfoam_adjoint`, `adjoint_contract` | `run_half_car_adjoint` | Keep `openfoam_adjoint.py` and `adjoint_contract.py` for now (Part 7 may use the adjoint once as an optional map). Remove the adjoint path from `run_car.py` only. |
| `car/merge_results.py:29` | `candidate_record` | ranks old adjoint-loop records | Delete `merge_results.py`. |
| `car/checks/stress_cars.py:114` | `phi_updater.hj_update` | the fake `--carve` mode (F43) | Delete the `--carve` option and `carve_field`. |
| `.github/lab/*.py` | `pattern`, `solver` | lab experiments | Delete after `docs/HISTORY.md` records their results. |
| `car/run_car.py`, `solver.py`, checks | `pattern` (bounds, `step0`, flags) | `pattern.LOFT`, `PARTS`, `FLOOR`, `LAYOUT`, `bounds`, `step0`, `get`, `put`, `PART_FLAGS`, `LAYOUT_FLAGS` | Move these definitions into a new `car/space.py` (they become Part 7's search space). Delete the search logic in `pattern.py`. |

### 2.3.2 Delete list

| Path | Reason |
|---|---|
| `part3-simulation/inner_loop.py`, `convergence.py`, `stability_check.py`, `gradient_combiner.py`, `objective_policy.py`, `optimizer_contract.py` and their tests | The retired carving loop (F13-F16). |
| `part3-simulation/pipeline_interface.py` and its tests | Replaced by `car/pipeline.py`. |
| `part3-simulation/` folder entirely, once empty (keep `part3-simulation/README.md` content in `docs/HISTORY.md`) | — |
| `body/phi_updater.py` (after moving `reinitialise_sdf`) and its tests | Carving operator with the upwinding (F14) and extension (F15) bugs. |
| `body/stl_assembler.py`, `quality_gates.py`, `mass_com_calculator.py` and their tests | Four-grid era, no live caller (verify with grep after the moves). |
| `body/BUILD_REPORT.md`, stale items in `PLACEHOLDERS.md` (1-4, 9, 11, 13), `SPEC_ASCII.md` (move to `archive/`) | Describe a pipeline that no longer exists (F39). |
| `body/hardware_cad/canister_safety_zone.stl` (if unreferenced) | Constant `CANISTER_SAFETY_ZONE_MM` unused. Check with grep first. |
| `cfd/candidate_record.py` and its tests | Old adjoint-loop records. |
| `car/solver.py`, `pattern.py` (after `space.py` exists), `merge_results.py` and their tests | Retired searches (F12, F13). |
| `car/search/*` → move to `archive/search-2026-11/` | Data: keep. |
| `.github/workflows/`: `solver.yml`, `pattern.yml` (if present), `adj_lab.yml`, `line_lab.yml`, `impact.yml`, `impact_wheels.yml`, `noise.yml`, `noise_long.yml`, `noise_var.yml`, `repeat.yml`, `body_lab.yml`, `pinch_lab.yml`, `smooth.yml`, `car_debug.yml`, `car_libs.yml` | Superseded by Part 1's batches and Part 6's experiments. Keep `tests.yml` and `stress.yml` (rewritten, section 2.6), and `image.yml` (Part 1). |
| `.github/lab/*.py` | Lab experiments; results go to `docs/HISTORY.md`. `render_lab.py` → keep only if `car/render.py` does not already do the same. |

Before deleting any file, run:

```bash
grep -rn "<module_name>" --include=*.py --include=*.yml . | grep -v "/tests/" | grep -v "^./<path of the file itself>"
```

If anything live still references it, fix that reference first.

---

## 2.4 Step-by-step procedure

Each step is one commit. After each step: run the affected test folders, rebuild G1 locally (fast), compare with `checks/golden.py compare`. Every few steps, run the full golden batch on the farm.

1. **Write `docs/HISTORY.md`** (section 2.7 has the content to start from). Commit: `Part 2: history of retired methods (F37)`.
2. **Archive data:** `git mv car/search archive/search-2026-11`. Fix any code path that reads `search/` (only `solver.py` and `pattern.py`, both being deleted). Commit.
3. **Create `body/sdf.py`:** move `reinitialise_sdf` and the private helpers it calls from `phi_updater.py` unchanged (copy the functions byte for byte, including docstrings). Change imports in `machining.py:71`, `param_body.py:238`, `unified_phi.py:873` to `from sdf import reinitialise_sdf`. Move the reinitialisation tests from `tests/test_phi_updater.py` into `tests/test_sdf.py`. Rebuild G1 → identical. Commit.
4. **Create `car/space.py`:** move `LOFT`, `PARTS`, `FLOOR`, `FLOOR_START`, `PART_FLAGS`, `LAYOUT`, `LAYOUT_START`, `LAYOUT_FLAGS`, `step0`, `bounds`, `get`, `put`, `_part_default` and anything they call from `pattern.py`, unchanged. Change `run_car.py` and checks to `import space`. Commit.
5. **Create `car/pipeline.py`** (section 2.5). Change `run_car.make_bindings` to use it. Rebuild G1, G3 → identical; run G4 on the farm → D20 identical. Commit.
6. **Strip `run_car.py`:** remove `--optimise`, `--final-cfd`, `--adj-iters`, `--substeps`, `--trust-mm`, `--smooth-mm`, `--phi-npy` and their code (the block from line ~438 to ~475 at commit 9fe27ca, and the `phi_npy` branch in `build_body`, lines 56-65). Read `DEFAULT_ROLLING_MU` from `physics_contract`. Commit.
7. **Delete the retired folder `part3-simulation`** entirely. Remove it from `car/paths.py` `PARTS` and from `tests.yml`. Commit.
8. **Delete `phi_updater.py`**, `stl_assembler.py`, `quality_gates.py`, `mass_com_calculator.py` (after moving `ComponentMassCOM`), `candidate_record.py`, `merge_results.py`, `solver.py`, the search logic left in `pattern.py` (then the file), and all their tests. After each file: grep, run tests. Commit per file.
9. **Prune `PhiGrid`** (`body/phi_grid.py`): use a dead-code finder to list unused methods, then confirm each with grep:
   ```bash
   pip install vulture
   vulture body cfd components car --min-confidence 60 --exclude "*/tests/*"
   ```
   The Part 1 audit identified these as uncalled from any pipeline: `PhiGrid.init`, `PhiGrid.remap`, `PhiGrid.build_hard_masks`, `PhiGrid._validate_masks`, `extract_surface` (the four-grid one), `_check_accessibility`, `_check_wall_thickness`, `cargo_placement_is_buildable`, `WHEEL_KEEPOUT_MARGIN_M`, `CANISTER_SAFETY_ZONE_MM`, `ATTACHMENT_STRIP_*`, `PHI_SNAPSHOT_COMPONENT_KEYS`, `LABEL_NOSE` and `DENSITY_NOSE_KGM3` (the nose zone is always forced air), the nose wall-thickness loop in `unified_phi.py:1134-1155`, the no-op `np.take(...)` at `phi_updater.py:51` (gone with the file), and the nonsense line `surface_extraction.py:726` (`nx, ny, nz = mesh.bounds[1]-mesh.bounds[0], 0, 0`: read its use; fix or delete). Delete each only after grep shows no live use. Commit in small groups.
10. **One machinability model.** `machining.reachable_air` is the live model. `unified_phi.enforce_machinability` (lines ~925-970) was used only by the adjoint path: delete it if grep shows no other caller. `surface_extraction._find_inaccessible_faces` reports inaccessible area to the gate: keep it for now as a report only; Part 5 decides. (F31)
11. **`stress_cars.py`:** delete `--carve` and `carve_field` (F43). Change its summary line to say what it measures: "builder robustness at fixed skin, no mass sizing, no CFD" (F42). Commit.
12. **Docs:** update every README to the code that remains. Specifically correct: "114 settings" → "94 body settings" (24 loft station values, 1 squareness, 7 sidepod settings, 1 blend, 5 floor/tunnel, 56 sculpt modes; recount from `BodyParams` and write the true breakdown), "32 modes" → "56 modes, σ = 7 mm", "72 checks" → the count printed by `legality.summary()` on G3, "four sides" machining is correct (top, bottom, left, right) and `param_body.py:231` saying "top-and-bottom" is wrong: fix the comment. (F39)
13. **Workflows:** delete the list in 2.3.2. Rewrite `tests.yml` and `stress.yml` (section 2.6). Commit.
14. **Final golden batch** on the farm: all four golden cars identical (or differences recorded and accepted by the user). Count lines removed:
    ```bash
    git diff --stat main...part2-cleanup | tail -1
    ```
15. **Pull request:** `Part 2: remove retired methods (F13-F16, F31, F37-F39, F42-F43)`. Body: lines removed, golden comparison table, list of moved functions. No AI attribution lines. Ask the user to approve the merge.

---

## 2.5 `car/pipeline.py` (replaces `pipeline_interface.unified_bindings`)

Build it by **copying**, not rewriting, from `part3-simulation/pipeline_interface.py` at commit 9fe27ca:

- the dataclasses `GateOutcome`, `MassReport` (including its `launch_com` method, used by `run_car.mass_state` and `cfd_and_objective`), `CFDOutcome`, `ObjectiveOutcome`;
- the constants and helpers `STL_TRIANGLE_BUDGET`, `_decimate_for_cfd`, `_add_sibling_packages_to_path` (or rely on `paths.py`);
- from inside `unified_bindings`: `fixed_hardware_for`, `_params`, `run_quality_gates`, `compute_mass_report`, `run_cfd`, `evaluate_objective`, and the model/propellant setup lines.

Drop: `initialize_phi_fields`, `compute_adjoint_weight`, `run_adjoint`, `update_phi`, `write_record`, `validate_bindings`, `PipelineBindings`, and the `hj_*` and `adjoint_kwargs` parameters.

Shape of the result:

```python
"""pipeline.py -- the four steps run_car needs between geometry and race time.

Copied from part3-simulation/pipeline_interface.unified_bindings at commit 9fe27ca
(the carving-loop bindings were dropped with the loop; see docs/HISTORY.md).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Optional

import paths  # noqa: F401  -- puts part1/2/4 on sys.path

# --- dataclasses copied verbatim: GateOutcome, MassReport (with launch_com), CFDOutcome, ObjectiveOutcome
# --- STL_TRIANGLE_BUDGET and _decimate_for_cfd copied verbatim


def bindings(thrust_csv_path: str, fixed_hardware_kwargs, out_dir: str,
             cfd_kwargs: Optional[dict] = None, ballast_material: Optional[str] = None,
             stl_triangle_budget: int = STL_TRIANGLE_BUDGET, cargo_placement: Optional[dict] = None):
    from unified_phi import compute_mass_com, extract_half_surface, extract_unified_surface
    from cfd_wrapper import run_half_car_cfd
    from mass_com_ingest import FixedHardwareSpec, ingest_mass_com
    from race_objective import build_smooth_sheet_model, sheet_mass
    from race_objective_adapter import race_value_and_grad_guarded
    import numpy as np
    import jax.numpy as jnp

    cfd_kwargs = dict(cfd_kwargs or {})
    model = build_smooth_sheet_model(thrust_csv_path)
    propellant_kg = float(sheet_mass(jnp.float64(0.0), model) - model.mass_sheet_final)
    # ... fixed_hardware_for, _params, run_quality_gates, compute_mass_report, run_cfd,
    #     evaluate_objective: copied verbatim from unified_bindings ...
    return SimpleNamespace(run_quality_gates=run_quality_gates, compute_mass_report=compute_mass_report,
                           run_cfd=run_cfd, evaluate_objective=evaluate_objective, model=model)
```

`run_car.make_bindings` keeps its frame computation (the fixed meshing frame from Ref A − 41 mm to Ref B + 41 mm, 43.5 mm half-width, 66 mm high: it removes domain-size noise and stays) and calls `pipeline.bindings(...)` with the same `cfd_kwargs` it builds today.

Add `car/tests/test_pipeline.py`: build the bindings with the real CSV, call `evaluate_objective(D20=0.41, L=0.0, m_total=0.0482+0.02115, h_com=0.03, x_com=0.1, mu=0.010, wheel_moi=1.39e-7)` and assert `T_raw` is within 1e-6 s of the value the old `unified_bindings` returns for the same inputs (compute that value once before deleting Part 3 and paste it into the test as a constant with a comment saying where it came from).

---

## 2.6 Rewritten workflows

### 2.6.1 `tests.yml`

Use the Part 1 container so tests run in the same environment as the farm:

```yaml
name: tests
on:
  push:
  workflow_dispatch:
permissions:
  contents: read
jobs:
  tests:
    runs-on: ubuntu-24.04
    timeout-minutes: 60
    container:
      image: ghcr.io/shawshanker18/stem-cfd@sha256:<digest from compute/accounts.json>
      options: --user 0
    strategy:
      fail-fast: false
      matrix:
        include:
          - { part: body, shard: 0, of: 4 }
          - { part: body, shard: 1, of: 4 }
          - { part: body, shard: 2, of: 4 }
          - { part: body, shard: 3, of: 4 }
          - { part: cfd, shard: 0, of: 1 }
          - { part: components, shard: 0, of: 1 }
          - { part: car, shard: 0, of: 1 }
          - { part: compute,          shard: 0, of: 1 }
    steps:
      - uses: actions/checkout@v4
      - name: pytest
        working-directory: ${{ matrix.part }}
        env:
          PART2_PATH: ${{ github.workspace }}/cfd
        run: |
          files=$(ls tests/test_*.py | awk -v s=${{ matrix.shard }} -v n=${{ matrix.of }} 'NR % n == s')
          python -m pytest $files -q -p no:cacheprovider --tb=short -W ignore
  golden:
    runs-on: ubuntu-24.04
    timeout-minutes: 60
    container:
      image: ghcr.io/shawshanker18/stem-cfd@sha256:<digest>
      options: --user 0
    steps:
      - uses: actions/checkout@v4
      - working-directory: car
        run: |
          python run_car.py --out ../out/G1 --body-json '{}' --skin-mm 3.93
          python checks/golden.py compare ../golden/G1.fp.json ../out/G1
```

The `golden` job makes every future change prove it did not alter the reference car, or forces the author to update the fingerprint on purpose (with a commit message saying why).

### 2.6.2 `stress.yml`

Same as today, minus the `carve` input, plus the container. It now reports "builder robustness at fixed skin" in its summary line.

---

## 2.7 `docs/HISTORY.md` — content to start from

Write it in plain sentences. One section per retired method. Use these facts (all from the repository at commit 9fe27ca); add dates from `git log` where useful.

**Level-set carving with the drag adjoint (Parts 1-3, retired 2026-09-30, briefly revived 2026-11-08).** The body was a signed-distance field on a voxel grid, started as the full legal block, and moved with a Hamilton-Jacobi update driven by the adjoint drag sensitivity plus mass and centre-of-mass gradients. The sign of the aero term was flipped twice. The surface did not move until a redistancing fix. For a long period the drag term was dead and the mass term carried about 94% of every update. On coarse and medium meshes, with 1 mm and 0.3 mm trust radii, 12 of 12 drag steps raised drag by 2.7-5%. One 0.3 mm step on the medium mesh ranked correctly (descent −1.3%, zero step −0.7%, ascent +0.9%). A November 2026 review found two numerical bugs in the operator (upwind branch chosen by the sign of φ instead of the velocity; velocity extension built on unsigned normals) and that the "full block" start field was a constant rather than a signed distance, so mass sizing could not work on it. The legal block after mandatory air weighs about 50 g of foam against a ~33 g body target, so there is little block to carve.

**Drag adjoint as a gradient (Part 2 `openfoam_adjoint.py`, kept for optional use).** `adjointOptimisationFoam`, kOmegaSST primal, adjoint turbulence frozen (`adjointLaminar`, after `adjointkOmegaSST` crashed with SIGFPE at adjoint iteration 277). Gradient check 2026-09-28: right sign on 3 of 8 settings, r = 0.45. Pre-registered check November 2026 (sign share ≥ 0.8 and r ≥ 0.8 on 12 settings): r ≈ 0, failed. A later line test along the adjoint direction (drag at −2…+2 mm) went downhill overall but was non-monotone at the 0.5-1 mm scale. 21% of surface vertices had no sensitivity point within 5 mm on the medium mesh.

**Pattern search (Part 5 `pattern.py`, 2026-09-28 to November).** Screen every parameter of one group at ± a step with the skin held fixed, confirm candidates resized to 48.2 g, accept if better by twice the noise. Found front-wing and support improvements of 2.6-7%. Four rear-wing changes each tested 2-5 ms faster but did not add up when combined.

**Adjoint-plus-CFD solver (Part 5 `solver.py`, November 2026).** 8 chains from random starts, adjoint slopes projected onto the body and part settings, plus brute-force layout steps, steps accepted when better than the base by twice a 1 ms noise floor. 40 rounds, 16 accepted steps (9 layout, 7 adjoint), chain end times 1.5412-1.5734 s (model time, synthetic thrust curve). The review estimated about 8 of the 16 acceptances could be noise (best-of-about-10 at 2σ accepts noise about 21% of the time) and showed the start car mattered more (32 ms spread) than the climb.

**Noise experiments (`noise*.yml`, `repeat.yml`, November 2026).** Same car on 6 machines: within 0.28 ms. Skins 0.01 mm apart (8 runs): σ 1.3 ms with layers, 2.2 ms with "better" layers, 1.0 ms without layers; 5,000 iterations changed nothing. Fine mesh without layers σ ≈ 0.95 ms, ~4.4 hours per car. Conclusion: the noise comes from remeshing, not from the solver.

**Impact sweeps (`impact.yml`).** Rear-wing variants, support discs, wheel rounding; rounded wheels found illegal under T7.4 (contact width measured without fillets).

**Body generation decision (2026-09-27/28, `car/docs/BODY_GENERATION_DECISION.md`).** Move this document to `docs/` unchanged and link it. It records the team's reasons for the hybrid parametric body and no ballast.

---

## 2.8 Exit gate for Part 2

All must be true; write each with evidence into `STATUS.md`:

- [ ] `docs/HISTORY.md` exists and covers every retired method.
- [ ] Repo folder `part3-simulation` is gone; `paths.py` no longer lists it.
- [ ] `grep -rn "phi_updater\|inner_loop\|pipeline_interface\|optimizer_contract\|candidate_record\|stl_assembler\|quality_gates\|mass_com_calculator\|import solver\|import pattern" --include=*.py .` returns nothing outside `archive/`.
- [ ] All test suites pass in the container (`tests.yml` green).
- [ ] Golden G1-G4 identical to the "before" fingerprints, or each difference recorded and accepted by the user.
- [ ] Line count removed recorded.
- [ ] Pull request merged by the user.

Now open `03_PHYSICAL_MEASUREMENTS.md` (the team should already be doing it in parallel).
