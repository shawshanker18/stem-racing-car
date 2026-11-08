# Part 6 — The CFD stopwatch: low-noise drag measurement

> **Status on 2026-11-08 (branch `rebuild/bible`). Owner: chat C.** `cfd/morph.py` exists: the Laplacian solver and the points file reader/writer are tested on small cases. Everything else not started.
> See `status/` for live progress and `agents/` for the chat prompts.

Read `00_START_HERE.md` first. This Part turns the CFD from a noisy stopwatch (σ ≈ 1 ms model, from remeshing) into one that can resolve the differences the search is looking for, and establishes how far its numbers can be trusted.

The core idea: **the noise comes from remeshing, so stop remeshing between neighbouring designs.** Build one high-quality base mesh per "family" of cars, then deform (morph) that mesh to each nearby candidate, warm-start from the base solution, and compare candidate and base on meshes with identical topology. For designs too far apart to morph, mesh fresh, but with every meshing input pinned to a fixed frame so the only remaining noise is surface snapping.

**Compute budget for this Part:** the biggest of all Parts except Part 7. About 150-250 jobs: mesh-configuration experiments (5 configurations × 8 cars), morph tests (about 40), a mesh study (about 15, some long), a speed sweep (about 9), geometry-fidelity tests (about 10). Each job 30 minutes to 6 hours.

---

## 6.0 Start of Part: the compute question

```
QUESTION (Part 6, compute 1): How many team members are confirming that their GitHub
accounts can be used for Part 6?
Why I need it: Part 6 runs about 150-250 CFD jobs to choose the search mesh and prove the
low-noise morphing method.
Expected load for Part 6: about 150-250 jobs of 0.5 to 6 hours. With 3 accounts (80 parallel
jobs) about 2 days; with 1 account (40) about 4 days.
```

Then compute 2. Record in `STATUS.md`.

---

## 6.1 What exists today (facts to start from)

All in `cfd/openfoam_case.py` and `cfd_wrapper.py` unless stated.

- ESI OpenFOAM v2412. Stages: `surfaceFeatureExtract` → `blockMesh` → `snappyHexMesh -overwrite` (serial) → `checkMesh` → `decomposePar` → `mpirun -np 4 simpleFoam -parallel` → `reconstructPar -latestTime`.
- Half car, symmetry plane at y = 0 (`symmetryPlane`), ground `lowerWall` at z = 0 moving at U (`fixedValue (U 0 0)`), inlet `fixedValue`, outlet `inletOutlet`, car `noSlip`, wheels `rotatingWallVelocity` with ω = −U/R about the axle (sign verified: the bottom of the wheel moves with the ground), other parts as separate wall patches.
- k-ω SST, inlet turbulence intensity 0.5% with ω from a viscosity ratio, Spalding wall function (`nutUSpaldingWallFunction`).
- Domain: 3 frame lengths upstream, 8 downstream, 5 heights/widths sideways and up. The "frame" passed from `run_car.make_bindings` is Ref A − 41 mm to Ref B + 41 mm in x, 43.5 mm half-width, 66 mm high.
- Refinement levels (min, max): coarse (2,3), medium (3,4), fine (4,5), resolved (5,5). Wake boxes ("near": car plus one length, surface-min level; "far": three more lengths, one level coarser). Underbody box one level finer. `nCellsBetweenLevels 3`. Background cell = frame length / 12.
- Layers: default 3 wall-function layers; the search turns them off (`nSurfaceLayers 0`). `resolved` builds a y+ ≤ 2 stack.
- Schemes: `bounded Gauss linearUpwind grad(U)` for U, upwind for k and ω, `cellLimited Gauss linear 1` for grad(U), `limited corrected 0.5` laplacian. SIMPLEC (`consistent yes`), U relaxation 0.9, k/ω 0.7, GAMG for p.
- `writeFormat binary`, fields written once at the end.
- Force: `forces` function object per patch group, averaged over the last 20% of iterations. Health: p residual ≤ 5e-3, drift ≤ 2%, standard error ≤ 1%.
- Measured noise and costs: see `00_START_HERE.md` section 0.9.

---

## 6.2 The three tiers of the stopwatch

| Tier | Used for | Mesh | Noise target | Cost per car |
|---|---|---|---|---|
| **Screen** | Global search (Part 7 stage B): cars far apart | fresh mesh, all meshing inputs pinned to one global frame; configuration chosen in 6.4 | σ as low as experiment shows (today 1 ms model ≈ 0.55 real ms) | 30-75 min |
| **Local** | Screening sensitivities (Part 7 stage A), local polish (stage C), confirming small steps | morphed from a family base mesh, warm-started | σ_paired < 0.1 real ms | 10-20 min |
| **Confirm** | Final candidates (Part 8) | fine and wall-resolved, real wheel geometry, chained jobs | bias check, not noise | 4-24 h |

---

## 6.3 Pin every meshing input to one global frame (fresh-mesh tier)

Today the frame is derived from each car's Ref A and Ref B, so a change of wheelbase or front axle position moves the domain, the background mesh, the refinement boxes and `locationInMesh`. That alone changes the mesh everywhere.

Fix: one **global** frame for every car in the legal layout range.

- Layout ranges (from `car/space.py`, formerly `pattern.LAYOUT`): x_front 46-56 mm, W 120.3-140 mm.
- Ref A ranges 30-40 mm; the nose reaches at most 40 mm ahead (T8.2), so the most forward point is at x ≥ −10 mm.
- Ref B ranges up to 56 + 140 + 16 = 212 mm; the rear wing overhangs at most 40 mm (T9.4.2): x ≤ 252 mm.
- Global frame: x from −11 mm to 253 mm; y from 0 to 43.5 mm; z from 0 to 66 mm. Put it in `geometry_contract.py` as `CFD_FRAME_MM = ((-11.0, 0.0, 0.0), (253.0, 43.5, 66.0))` and use it in `run_car.make_bindings` for every car.

Then audit `openfoam_case.build_case` and confirm each of these is computed from the frame and nothing else (read the code; the function `meshing_bounds` and `case_bounds` decide; make them return the frame when it is set):

| Input | Must come from |
|---|---|
| Domain box (`domain_box`) | frame |
| Background cell size (`cell_size = ref_len / 12`) | frame length (264 mm → 22 mm) |
| `locationInMesh` | frame |
| Underbody box | frame (not the car's lowest point) — today it uses `2 × z0` of the car; use a fixed 0-5 mm band |
| Wake boxes | frame |
| Frontal area (only used for coefficients) | car (harmless: not a meshing input) |

Also pin:

- `surfaceFeatureExtract`'s `includedAngle` and snappy's `resolveFeatureAngle`: fixed numbers in the dictionary (they are). Experiment C4 in 6.4 tests whether explicit feature snapping adds noise.
- STL triangulation: the body STL comes from marching cubes then decimation to `STL_TRIANGLE_BUDGET`. Decimation is deterministic for the same input, but a tiny shape change can change which edges collapse. Experiment C4 also tests a finer, undecimated STL.

---

## 6.4 Choosing the screen-tier mesh by experiment (pre-registered)

### 6.4.1 The configurations

| Config | Description |
|---|---|
| C0 | Today's search mesh: medium, no layers, 1,000 iterations, car-derived frame |
| C1 | C0 with the global frame (6.3) |
| C2 | C1 + 3 wall-function layers on every wall, first layer sized for y+ ≈ 30-50 at 20 m/s (about 0.15-0.25 mm; compute from the Spalding/log law with the local cell size), expansion 1.2 |
| C3 | C1 + wheels one refinement level finer than the body + 3 layers on wheels only |
| C4 | C2 with explicit feature snapping off for the body patch (rely on implicit snapping) and the undecimated body STL |

### 6.4.2 The protocol (write it in `STATUS.md` before running)

For each configuration:

1. **Noise:** the start car at 8 skins 0.01 mm apart (3.90 … 3.97 mm, fixed skin, no sizing), fresh mesh each. σ_D = sample standard deviation of D20 about a straight-line fit in skin (the true drag changes almost linearly over 0.07 mm; the residual is the noise).
2. **Bias and ranking:** three different cars (the start car, chain 2's best from `archive/search-2026-11/solver_state.json`, and a car with the front wing at +4° angle and no flap) on this configuration and on the **fine** mesh with 3 wall-function layers (the reference). For each pair of cars, the drag difference ΔD on this configuration and on the reference.
3. **Cost:** wall-clock minutes per car on 4 cores; cells.

Selection rule (fixed before the results):

- Discard any configuration whose absolute drag differs from the reference by more than 5% on any of the three cars.
- Discard any configuration that gets the sign of any car-to-car ΔD wrong relative to the reference (when the reference |ΔD| exceeds 2 σ_D of that configuration).
- Among the rest, choose the lowest σ_D. If two are within 20% of each other in σ_D, choose the cheaper.

Batch size: 5 configurations × (8 + 3) = 55 screen-tier cars + 3 fine reference cars (about 4.5 hours each; the fine run fits within one 6-hour job; if not, use chaining from Part 1 section 1.9).

### 6.4.3 How to express a configuration

`run_car.py` accepts `--cfd-json` and passes keys into `OpenFOAMRunConfig`. Add keys as needed (each a field on `OpenFOAMRunConfig`, with the default reproducing today's behaviour):

- `frame_mode`: `"car"` (today) or `"global"`;
- `layer_overrides`: exists;
- `wheel_extra_level`: integer, default 0;
- `feature_snap_body`: bool, default True;
- `stl_decimate`: bool, default True.

Each key needs one unit test in `cfd/tests/test_openfoam_case.py` checking the dictionary text it produces.

---

## 6.5 The local tier: mesh morphing

### 6.5.1 Concept

1. **Family base:** for an anchor car, build a fresh mesh with the chosen configuration (6.4) and solve it cold to full convergence (1,500 iterations). Keep the mesh, the final fields and the anchor's part STLs. This is a "family". Publish it as a release asset (`mesh-families`, Part 1 section 1.9).
2. **Candidate:** a car whose surfaces are within the family's morph range of the anchor (6.5.6). Build its STLs with the normal pipeline (no CFD). For every boundary point of the base mesh on a car part, compute how far it must move to lie on the candidate's surface. Move all interior points smoothly (a Laplacian with high stiffness near the walls, so the thin near-wall cells move almost rigidly). Write the new points. Check mesh quality. Warm-start from the base fields and solve.
3. **Paired comparison:** the candidate's drag minus the base's drag, both on the same mesh topology with the same solver protocol. The remeshing noise is gone; what remains is iterative and averaging noise, which is small and can be measured (6.5.8).

### 6.5.2 Data a family carries (`family-<id>.tar.zst`)

```
family.json            # anchor car parameters, config, D/L/My of the base, protocol, frame, git SHA
case/constant/polyMesh # points, faces, owner, neighbour, boundary   (ASCII: see below)
case/system/           # all dictionaries as used
case/0.base/           # final fields of the base solve (U p k omega nut), as the warm start
case/surfaces/         # the anchor's STLs per patch (car.stl, wheelF.stl, ...), metres, half car
```

The mesh must be ASCII for the Python morph code to read it. After `snappyHexMesh` and before solving, convert:

```bash
foamDictionary system/controlDict -entry writeFormat -set ascii
foamFormatConvert -constant
```

(Fields can stay binary; only `constant/polyMesh` is read by Python.)

### 6.5.3 Boundary point displacements

For each car-part patch P (`car`, `wheelF`, `wheelR`, `supports`, `halo`, `fwing`, `nose`, `rwing`, `tethers` — the names `assembly.py` gives the extra surfaces):

- Base points on P: from `constant/polyMesh/boundary` (start face, number of faces) and `faces`; the existing `openfoam_adjoint.car_patch_point_ids` does this for one patch; move it into `morph.py` and generalise.
- Candidate surface for P: the candidate's STL for the same part.
- Displacement of base point p: `closest_point(candidate_P, p) − p` (`trimesh.proximity.closest_point`). For small changes this is the normal projection.
- Rigid parts moved by a layout change (wheels and supports when W or x_front changes; wings when their position changes): the closest-point rule handles a pure translation correctly only if the move is smaller than the part's feature size. For layout changes, apply the known rigid translation to that patch's points exactly, then the closest-point correction for any shape change on top.
- Points shared by two patches (where a part meets the body): compute both displacements; if they differ by more than 0.05 mm, record it; use their mean.
- Non-car patches: inlet, outlet, top, side → fixed (zero displacement). `symmetry` → y-component fixed at 0, x and z free. `lowerWall` → z-component fixed at 0, x and y free (the wheels' contact patches can slide along the ground).

### 6.5.4 Interior point displacements (`cfd/morph.py`)

Solve, for each displacement component c separately, a weighted graph Laplacian over the mesh's point-edge graph:

```
Σ_j w_ij (d_j − d_i) = 0   for every free point i
d_i = prescribed           for every fixed point i (component c)
w_ij = (γ_i + γ_j) / 2,    γ_i = 1 / max(dist_i, δ)²
```

where `dist_i` is the distance from point i to the nearest moving boundary point and δ = 0.05 mm. The 1/dist² stiffness makes cells near the moving walls translate almost rigidly (preserving prism layers and near-wall cell shapes) and puts the deformation into the larger cells further out. This is the same idea as OpenFOAM's `displacementLaplacian` with `quadratic inverseDistance` diffusivity.

To keep the system small: points farther than `R_free = 20 mm` from every moving boundary point are fixed at zero.

Solver: conjugate gradient preconditioned by algebraic multigrid (`pyamg`; add `pyamg` to `docker/requirements.lock` and rebuild the image).

```python
"""morph.py -- deform a family base mesh onto a nearby candidate car (bible Part 6, 6.5).

    python morph.py --family <dir> --candidate-surfaces <dir with part STLs> --case <out dir>
Reads   <family>/case/constant/polyMesh (ASCII), <family>/case/surfaces/*.stl (anchor),
        candidate STLs (same file names, metres, half car)
Writes  <case>/constant/polyMesh/points (moved), morph.json (max/mean displacement, solver info)
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import numpy as np
import scipy.sparse as sp
import trimesh
from scipy.sparse.linalg import cg
from scipy.spatial import cKDTree

FIXED_PATCHES = ("inlet", "outlet", "top", "side", "front", "back")   # adjust to the case's names
DELTA_M = 5e-5
R_FREE_M = 0.020


def _body(text: str) -> str:
    """The list body of an OpenFOAM ASCII list file: between the first '(' after the size line
    and the matching last ')'."""
    i = text.index("(", text.index("\n", re.search(r"^\s*\d+\s*$", text, re.M).start()))
    return text[i + 1:text.rindex(")")]


def read_points(poly: Path) -> np.ndarray:
    body = _body((poly / "points").read_text())
    return np.array(body.replace("(", " ").replace(")", " ").split(), dtype=np.float64).reshape(-1, 3)


def read_faces(poly: Path) -> list:
    text = (poly / "faces").read_text()
    if "faceCompactList" in text[:3000]:
        lists = re.findall(r"\n(\d+)\s*\n\(\s*\n?([\d\s]*?)\n?\)", text)
        offs = np.array(lists[0][1].split(), dtype=np.int64)
        labs = np.array(lists[1][1].split(), dtype=np.int64)
        return [labs[offs[k]:offs[k + 1]] for k in range(len(offs) - 1)]
    return [np.array(m.split(), dtype=np.int64) for m in re.findall(r"\d+\(([\d\s]+)\)", text)]


def read_boundary(poly: Path) -> dict:
    out = {}
    for m in re.finditer(r"(\w+)\s*\{([^}]*)\}", (poly / "boundary").read_text()):
        nf, sf = re.search(r"nFaces\s+(\d+)", m.group(2)), re.search(r"startFace\s+(\d+)", m.group(2))
        tp = re.search(r"\btype\s+(\w+)", m.group(2))
        if nf and sf:
            out[m.group(1)] = (int(sf.group(1)), int(nf.group(1)), tp.group(1) if tp else "")
    return out


def edges_of(faces: list) -> np.ndarray:
    pairs = []
    for f in faces:
        pairs.append(np.stack([f, np.roll(f, -1)], axis=1))
    e = np.sort(np.concatenate(pairs), axis=1)
    return np.unique(e, axis=0)


def patch_points(faces: list, start: int, n: int) -> np.ndarray:
    return np.unique(np.concatenate(faces[start:start + n])) if n else np.array([], dtype=np.int64)


def write_points(poly: Path, P: np.ndarray) -> None:
    src = (poly / "points").read_text()
    head = src[:re.search(r"^\s*\d+\s*$", src, re.M).start()]
    head = re.sub(r"format\s+\w+;", "format      ascii;", head)
    lines = "\n".join(f"({x:.10g} {y:.10g} {z:.10g})" for x, y, z in P)
    (poly / "points").write_text(f"{head}{len(P)}\n(\n{lines}\n)\n")


def solve_component(n: int, edges: np.ndarray, gamma: np.ndarray, fixed: np.ndarray, value: np.ndarray):
    i, j = edges[:, 0], edges[:, 1]
    w = 0.5 * (gamma[i] + gamma[j])
    A = sp.coo_matrix((np.r_[w, w], (np.r_[i, j], np.r_[j, i])), shape=(n, n)).tocsr()
    L = sp.diags(np.asarray(A.sum(axis=1)).ravel()) - A
    free = ~fixed
    d = np.where(fixed, value, 0.0)
    if not free.any():
        return d
    Lff = L[free][:, free].tocsr()
    rhs = -(L[free][:, fixed] @ value[fixed])
    import pyamg
    M = pyamg.smoothed_aggregation_solver(Lff).aspreconditioner()
    x, info = cg(Lff, rhs, rtol=1e-10, maxiter=2000, M=M)
    if info != 0:
        raise RuntimeError(f"morph CG did not converge (info={info})")
    d[free] = x
    return d


def morph(family: Path, cand_dir: Path, case: Path) -> dict:
    shutil.copytree(family / "case", case, dirs_exist_ok=True)
    poly = case / "constant" / "polyMesh"
    P = read_points(poly)
    faces = read_faces(poly)
    bnd = read_boundary(poly)
    n = len(P)
    disp = np.zeros((n, 3))
    moving = np.zeros(n, bool)
    shared = {}
    for name, (start, nf, typ) in bnd.items():
        stl = cand_dir / f"{name}.stl"
        if not stl.exists():
            continue
        ids = patch_points(faces, start, nf)
        cand = trimesh.load(str(stl), force="mesh")
        cp, _dist, _tri = trimesh.proximity.closest_point(cand, P[ids])
        d = cp - P[ids]
        for k, pid in enumerate(ids):
            shared.setdefault(pid, []).append(d[k])
        moving[ids] = True
    for pid, ds in shared.items():
        disp[pid] = np.mean(ds, axis=0)
    conflict = max((float(np.ptp(np.array(ds), axis=0).max()) for ds in shared.values() if len(ds) > 1), default=0.0)

    fixed_all = np.zeros(n, bool)
    fix_c = [np.zeros(n, bool) for _ in range(3)]
    for name, (start, nf, typ) in bnd.items():
        ids = patch_points(faces, start, nf)
        if name in FIXED_PATCHES or typ == "patch":
            fixed_all[ids] = True
        elif typ == "symmetryPlane":
            fix_c[1][ids] = True
        elif name == "lowerWall":
            fix_c[2][ids] = True
    mov_ids = np.nonzero(moving)[0]
    dist, _ = cKDTree(P[mov_ids]).query(P)
    far = dist > R_FREE_M
    gamma = 1.0 / np.maximum(dist, DELTA_M) ** 2
    edges = edges_of(faces)
    out = np.zeros((n, 3))
    for c in range(3):
        fixed = moving | fixed_all | far | fix_c[c]
        out[:, c] = solve_component(n, edges, gamma, fixed, np.where(moving, disp[:, c], 0.0))
    write_points(poly, P + out)
    info = {"n_points": n, "n_moving": int(moving.sum()), "max_disp_mm": float(np.abs(disp[moving]).max() * 1e3),
            "mean_disp_mm": float(np.linalg.norm(disp[moving], axis=1).mean() * 1e3),
            "shared_conflict_mm": conflict * 1e3}
    (case / "morph.json").write_text(json.dumps(info, indent=1))
    return info
```

Points that are both on a moving patch and on the ground or symmetry plane (for example a wheel's contact region, a body point on y = 0): the moving patch's displacement wins, except that its y-component is forced to 0 on the symmetry plane and its z-component to 0 on the ground. Add those two lines after the shared-point loop and test them.

Notes the agent must verify on the first real family (each as a unit test or a logged check):

- Patch names and types: print `read_boundary` for a real case and set `FIXED_PATCHES` to the real inlet/outlet/far-field names from `build_blockmesh_dict`.
- Performance: a medium mesh of about 0.65 M cells has about 0.7-0.8 M points. Reading ASCII faces with regular expressions takes tens of seconds; acceptable. If it is too slow, parse `faceCompactList` (convert with `foamFormatConvert` writing compact) with `np.fromstring`.
- `rtol` is the SciPy ≥ 1.12 name for the CG tolerance; the image pins SciPy 1.17.

### 6.5.5 Quality check after morphing

```bash
checkMesh -constant > logs/checkMesh.morph.log
```

Parse: "Failed N mesh checks", max non-orthogonality, max skewness, min volume, negative volumes. Compare with the base mesh's own checkMesh (stored in the family). Accept the morphed mesh only if:

- no negative-volume cells,
- no **new** failed check that the base did not have,
- max non-orthogonality ≤ base + 5° and ≤ 70°,
- max skewness ≤ max(base × 1.2, 4).

If rejected, the candidate is too far from the anchor: mesh it fresh (screen tier) or create a new family anchored nearer to it.

### 6.5.6 Morph range

Measured in experiment M-4 (6.5.8). Initial guess: surface displacements up to 2 mm on the body and wings; layout translations up to 2 mm (one W or x_front step); any change that alters topology (a wing element appearing, the tunnel `ft_h` going to 0, the support `strip` switching on or off) is out of range and needs a fresh mesh.

### 6.5.7 Warm start and solver protocol

Base (family creation): cold start, 1,500 SIMPLE iterations, average the last 300.

Candidate (morph):

1. Copy `0.base/{U,p,k,omega,nut}` into the candidate case's `0/` (same mesh topology, so the internal fields map one-to-one). Do not copy `phi` (the face fluxes depend on the moved face areas; OpenFOAM recomputes them).
2. Update boundary entries that depend on geometry: each wheel's `rotatingWallVelocity` `origin` (axle position) and `omega` (−U/R with that wheel's radius). `foamDictionary 0/U -entry boundaryField/wheelF/origin -set "(x y z)"`.
3. Run 500 SIMPLE iterations; average the last 300.
4. Paired result: ΔD = D_candidate − D_base, ΔL, ΔMy likewise.

Every morph batch includes one **identity morph** (the anchor itself, zero displacement) as a control. Its ΔD measures the protocol bias (warm 500 versus cold 1,500) and must be ≈ 0 (M-0).

### 6.5.8 Acceptance experiments for morphing (pre-registered thresholds)

Write the thresholds into `STATUS.md` before running. Real ms use the Part 4 exchange rate (about 0.27 ms per mN on a 9.2 N curve; use the measured rate once Part 4 has it).

| Id | Experiment | Pass |
|---|---|---|
| M-0 | Identity morph of the anchor, run 3 times with different base-solve continuation lengths | \|ΔD\| < 0.02% of D |
| M-1 | Linearity: skins −0.04, −0.02, 0, +0.02, +0.04 mm by morph (fixed skin parameter changed, body rebuilt, morphed) | residual sd about a straight-line fit < 0.03% of D (≈ 0.12 mN ≈ 0.03 real ms) |
| M-2 | Warm versus cold on the same morphed mesh (+0.5 mm skin): warm 500 against cold 2,000 | difference < 0.05% |
| M-3 | Morph versus fresh: +0.5 mm skin, front wing +2°, mode 12 +2 mm: ΔD by morph against ΔD by fresh meshes (mean of 8 fresh meshes each, skins jittered by 0.01 mm to average the remesh noise) | agree within 2× the fresh-mesh standard error |
| M-4 | Range: skin +0.5, +1, +2, +3 mm and W +2, +4 mm by morph | the largest step where 6.5.5 accepts the mesh **and** M-3-style agreement holds defines the morph range |

If M-3 fails, morphing is biased (the morphed mesh is worse near some feature). Investigate (look at where the largest displacements and the worst cells are) before using morphing in Part 7.

---

## 6.6 Convergence protocol (both tiers)

- Keep the health gates: p residual, drift ≤ 2%, standard error ≤ 1%.
- Replace the fixed "last 20%" window with a check that the **mean** is settled: split the averaging window into halves; the two half-means must agree within 2 standard errors. If not, continue 500 iterations (budget permitting) and re-check. Report the iterations used.
- Report, per car: D, L, My (raw, full car), per-patch D and L, standard error of the mean, iterations, cells, y+ statistics per patch, wall time.

---

## 6.7 Mesh study: are car-to-car differences real?

Three cars that differ meaningfully (as in 6.4.2 step 2). Levels: the chosen screen configuration, fine with 3 layers, and resolved (wall-resolved, about 5 M cells; needs chaining, Part 1 section 1.9, about 2-4 segments of 5.5 hours, or a paid machine).

Report a table of ΔD between each pair of cars at each level, with standard errors. Pass (pre-registered): the sign of every ΔD whose magnitude exceeds 2 standard errors agrees across all levels, and magnitudes agree within 30% between the screen tier and fine.

If the sign flips between fine and resolved, the screen tier cannot rank those kinds of changes: write which kind (body, wing, wheel-region) and tell the user; Part 7 must then confirm such changes at fine level before accepting them.

---

## 6.8 Speed dependence (feeds Part 4)

For the same three cars at the screen configuration: CFD at 10, 15, 20 and 25 m/s (inlet, ground and wheel ω all scaled). Fit log D against log v; k = 2 − slope. Report k per car and whether a single k (mean) fits all three within ±0.03. Also lift and pitching moment versus speed (same exponent expected; check).

---

## 6.9 Geometry fidelity experiments

| Id | Question | Experiment | Use of the answer |
|---|---|---|---|
| G-1 | Do closed drum wheels misrepresent drag? (F35) | Start car at fine level with (a) drums, (b) the team's real wheel STLs (spokes, hub, bearing seat) as rotating walls (`wheel.team_wheel_meshes()` gives them) | If D differs by > 5% **or** a car-to-car difference changes sign between drums and real wheels, use real wheels at least in the confirm tier, and in the screen tier if the cost is acceptable |
| G-2 | Do hubcaps, the bore opening, pockets and glue gaps matter? (F36) | Start car fine: with and without hubcaps (stationary walls); with the chamber bore open at the rear | Same rule |
| G-3 | Is the boundary layer laminar enough to matter? | Two cars on the resolved mesh with `kOmegaSST` and with `kOmegaSSTLM` (transition; already configured in `TURBULENCE_MODELS`) | If ΔD between the cars changes sign between models, report it as a modelling uncertainty in Part 8; do not switch the search model (too expensive) |
| G-4 | Does the 0.3 mm sink of the wheels into the ground matter? | Sink 0.1, 0.3, 0.5 mm, start car, screen tier, 4 fresh meshes each | If drag changes by more than the noise, use the smallest sink that meshes reliably |

The CO2 jet (a supersonic-start, then subsonic CO2 jet from the cartridge during the first about 0.3 s, right where the rear wing sits) is not modelled. During thrust the car is slow, so aerodynamic drag then is small; the jet's main effect is probably on the base pressure behind the car during the thrust phase. Leave it unmodelled; mention it in Part 8's limitations.

---

## 6.10 New worker kinds (`compute/worker.py`)

| Kind | Inputs in the case | Does | Returns |
|---|---|---|---|
| `fresh` | car argv, config key | build car, fresh mesh, solve (= today's `car` with the config) | D, L, My, patches, health, cells, minutes |
| `family` | car argv, config key, family id | build anchor, fresh mesh, `foamFormatConvert -constant`, cold 1,500 iterations, pack `family-<id>.tar.zst` into `out/ckpt/` | base D, L, My, checkMesh summary, package size |
| `morph` | family id (release asset URL), candidate argv | download and unpack family, build candidate STLs (no CFD), `morph.py`, checkMesh gate, warm start, solve | D, L, My, ΔD, ΔL, ΔMy against base, morph info, mesh quality, accepted/rejected |
| `speed` | car argv, config, speed | `fresh` at that speed | as `fresh` |
| `chained` | see Part 1 section 1.9 | long runs in segments | per segment |

After a `family` job is collected, the coordinator uploads the package:

```bash
gh release upload mesh-families results/raw/<batch>/family-<id>.tar.zst -R shawshanker18/stem-racing-car
```

and records its public URL in `results/families.json` (`{"<id>": {"url": ..., "anchor": {...}, "config": ..., "D_base": ...}}`). `morph` cases carry that URL.

---

## 6.11 Exit gate for Part 6

- [ ] Global frame in place (6.3); unit test that two cars with different W produce identical `blockMeshDict` and refinement boxes.
- [ ] Screen configuration chosen by the pre-registered rule (6.4); σ_D recorded in model and real ms.
- [ ] Morph experiments M-0 … M-4 pass (6.5.8); morph range recorded.
- [ ] Mesh study done (6.7); any sign flips reported.
- [ ] Speed exponent k recorded (6.8) and copied into `inputs/measured.json` as a CFD-derived input with its source.
- [ ] G-1 … G-4 done and their decisions recorded.
- [ ] `family`, `morph`, `fresh`, `speed` worker kinds tested on the farm.

Now open `07_SEARCH.md`.
