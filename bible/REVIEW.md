# Brutal architecture review: STEM Racing car search

Reviewed: `shawshanker18/stem-racing-car`, branch `main`, commit `9fe27ca`, cloned and read on 2026-11-08. Every file in your reading list was opened. Where a number below is mine, I say so; I re-implemented your race model independently in plain NumPy and it reproduces your figures to three digits, so the race-model numbers here are checked, not quoted.

## 0. Verdict

The pipeline is a 21,700-line rules-and-manufacturing engine with a 1-D race model bolted to a noisy CFD stopwatch, driving a shape search over the one component (the milled body) that your own CFD says is worth about 12% of the drag. The thrust curve that every millisecond in the repository is computed from is a synthetic file with roughly 60% of a real cartridge's impulse. The adjoint has never passed the test you set for it. The carve-from-block path you want to make the core method is broken today, and the legal block after mandatory air is only about 50 g of foam against a ~33 g body target, so "carving" is mostly mass sizing wearing a different hat.

Replace the core method. Keep the rules engine, the legality harness, the CFD case builder, the race-model integrator and the GitHub automation. Delete the level-set carving loop, the adjoint-steered search and every placeholder penalty. Spend the next two weeks measuring the physical inputs, not writing code. Then run a noise-aware, low-dimensional surrogate search on the levers that are actually worth tens of milliseconds: wheels, supports, wing, nose, layout, mass placement.

What follows is the evidence.

## 1. Teardown: what is wrong, wasteful or unsound

### 1.1 The objective's inputs are not real

- **The thrust curve is a simulation output, not a measurement.** `co2_thrust_data.csv` has distance, velocity and acceleration columns, mass falling from exactly 56 g to 48 g (a 48 g car plus 8 g of CO2, no cartridge shell), and a thrust that starts at 0.22 N and ramps up to 8.52 N at t = 0.18 s. Real cartridges punch to peak within tens of milliseconds. Integrated impulse is 1.214 N·s. Your own decision document (`BODY_GENERATION_DECISION.md`, item 5) says the curve has ~60% of the real impulse. A published fit to measured Pitsco 8 g data (AeroTune) uses 9.2 N peak decaying with τ = 0.25 s, about 2.0 N·s.
- **Consequences, from my re-implementation of your ODE** (your start car: D20 = 0.41 N, 48.2 g + 21.15 g cartridge, μ = 0.010, I = 1.39e-7 kg·m²):

  | Thrust curve | Race time | Peak speed | dT/dD | dT/dm | μ 0.010→0.020 | Wheel inertia −20% |
  |---|---|---|---|---|---|---|
  | your CSV | 1.556 s | 16.1 m/s | 0.480 ms/mN | 16.6 ms/g | +7.4 ms | −9.2 ms |
  | 9.2 N, τ 0.25 s fit | 1.041 s | ~21 m/s | 0.270 ms/mN | 10.1 ms/g | +2.0 ms | −5.8 ms |

  Your 1.5412 s best is 40% slower than the 2023 World Finals fastest (1.090 s) and the record (~0.916 s), which is what a 60% thrust curve does. Every millisecond figure in the repository, including the 1 ms noise, the 2–6 ms gains and the 16.6 ms/g, is inflated about 1.8× in absolute terms. The drag-versus-mass exchange rate is roughly preserved (34.6 versus 37.4 mN per gram), so body-versus-mass rankings survive. The ranking of drag against rolling friction and wheel inertia does not.
- **The CFD reference speed is never reached.** D20 is drag at 20 m/s scaled as v². With your thrust curve the car peaks at 16 m/s, so D20 is an extrapolation of the whole race. With real thrust the car spends time above 20 m/s. Neither case is the one you simulate.
- **Two fabricated penalty terms sit inside the objective.** `race_objective.py:92-110`: a degree-4 polynomial through nine invented points costing up to 28 ms for a 12 mm COM-height offset, and a quadratic COM-x penalty whose target is x = 0, the nose tip on the ground (`physics_contract.py:64`, `race_objective.py:103-105`). The adapter subtracts them to recover `T_raw`, but the old carving loop steered on them (Part 3 README; `openfoam_adjoint.py:103`: "mass/COM carries 94%" of the shape update). The COM-x penalty is numerically negligible and physically meaningless; the COM-height penalty is a stand-in for real launch dynamics (section 7) and should be deleted, not tuned.
- **Rolling friction 0.010, wheel inertia from a CAD mean, cartridge shell 21.15 g, foam 0.163 g/cm³, bearing 0.30 g, glue gap 0.15 mm, rear wing 5 g: all placeholders.** `grep -i placeholder` finds 35 of them in code. With no ballast and a 0.2 g mass margin, the foam density alone decides legality (section 1.5).

### 1.2 The stopwatch cannot resolve what the search is looking for

- **Where the drag is**: wheels 67%, body 12% (your decision document, section 2). Body drag is ~49 mN of 0.41 N. At your dT/dD that is 24 ms of model time; at a real thrust curve, about 13 ms. The entire body is worth 13 ms real. A 25% body improvement is ~3 ms real. Your 1 ms model noise is ~0.55 ms real. The search's last accepted gains (2.1, 2.5, 3.3 ms model) are 1–2 ms real on a lever whose total value is 13 ms.
- **The search mesh has no boundary layers.** `solver.py:SEARCH_CFD = {"nSurfaceLayers": 0}` with surface cells 1.2–2.5 mm and Spalding wall functions at y+ 18–240 on a 28 mm wheel at Re ≈ 4e4, where the real boundary layer is laminar or transitional. Fully turbulent k-ω SST on that mesh gives the right order of magnitude of drag and the wrong separation on the one component that makes two-thirds of it. You chose this mesh because it was the quietest (1.0 ms versus 1.3–2.2 ms), not because it was the most right.
- **Steady SIMPLE on an unsteady wake.** `openfoam_case.py:926-960` documents 7–27% peak-to-peak force oscillation and a mean that drifts with the averaging window. You average the last 20% of 1000 iterations and gate on a 1% standard error and 2% drift. Fine as bookkeeping, but it means D20 is a time average of a steady solver pretending.
- **Mesh independence has not been shown at the scale of the signal.** Coarse/medium/fine: 0.404/0.413/0.410 N, a 2% spread, with the medium-to-layered difference at 5%. The signal you are chasing is 0.5%.
- **The CFD car is not the manufactured car.** Wheels are closed drums at a mean radius, sunk 0.3 mm into the track (`wheel.py:130-139`, `assembly.py:46,138`); the real wheel has 0.6 mm spokes, a bearing seat, a stationary hubcap (omitted: `assembly.py:188-189`) and a recessed support disc. Glue gaps, the exact bore, the halo pocket as cut, and the pod windows are absent. The body the CFD sees is `body_half.stl`; the body you mill is `machined_body.stl` after pockets, bore, remesh and fairing.

### 1.3 The noise is not noise, and the acceptance rule knows it

- **Your repeat measurement is deterministic.** The same geometry gives the same snappyHexMesh and the same number to 0.01 ms (your own comment, `solver.py:50-54`). So in 35 of the 40 solver rounds the "measured noise" is the 1 ms floor, and the acceptance threshold is a fixed 2 ms, not twice anything measured. The 1 ms figure comes from skins 0.01 mm apart: the objective has a ~0.5% hash-like discontinuity in shape, which is the real problem (section 3).
- **Best-of-N selection at 2σ is a 20% false-positive machine.** Each round measures ~10 candidate steps and accepts the best if it beats the base by 2 ms. With σ = 1 ms, the probability that the best of 10 pure-noise draws clears 2σ is 21% (13% for 6, 24% for 12). Over 40 rounds you accepted 16 steps; about 8 of those are expected to be noise. Chain 5 shows the signature: it accepted x_front = 50.16 (+12.0 ms), then 52.16 (+5.0 ms), then 51.66 (+6.1 ms): three "gains" walking the same parameter back and forth. The accepted T is also a best-of-N statistic, so every chain's reported time is biased low and the bias is never corrected because the re-measurement is the same mesh.
- **The climb is smaller than the start.** Final chain times span 1.5412–1.5734 s (32 ms); per-chain gains were 0.4–23 ms. Where you start decides more than the search does. Of the 16 accepted steps, 9 were layout steps (W, x_front, d_halo, tried by brute force) and 7 were adjoint steps. The adjoint machinery, with its 30-minute solve per chain per round, produced seven accepted steps across eight chains, several of which are statistically indistinguishable from the false-acceptance rate.

### 1.4 The adjoint has not earned its place, and the carving operator is broken

- **The pre-registered test failed and was replaced.** `solver.py:69-71` set the bar before seeing results: sign agreement ≥ 0.8 and correlation ≥ 0.8 on 12 settings. The result was r ≈ 0 (`solver_state.json: check.note`). The state file then records `"passed": true` on the strength of a nine-point line test that was not the pre-registered test. The line test itself: drag falls 0.441 → 0.404 N from −2 mm to +0.5 mm along the adjoint, then rises to 0.417 at +1 mm and falls to 0.400 at +2 mm. Downhill overall, non-monotone at the step sizes you actually take. That is consistent with a direction that is right in the large and unverifiable in the small, because the measurement has 0.5% discontinuities.
- **Frozen turbulence with two-thirds of drag in wheel wakes** (`openfoam_adjoint.py:233-244`) is the textbook case where frozen-turbulence sensitivities are wrong in magnitude and can be wrong in sign near separation. Your 3-of-8 sign result is not surprising.
- **Sensitivity mapping is lossy.** Nearest-neighbour mapping from snappy's points to STL vertices, 21% of vertices unmapped and frozen at `medium`, with the allowed unmapped fraction loosened from 0.05 to 0.30 to let the production path run (`openfoam_adjoint.py:115-126`). Mirror averaging in `phi_updater.py:861` halves the magnitude on both sides.
- **The level-set operator has two real bugs.** `_godunov_gradient` (`phi_updater.py:80-85`) picks the upwind branch by sign(φ), which is correct only for reinitialisation; `hj_update` reuses it for arbitrary-sign velocity, so cells where sign(F) ≠ sign(φ) are downwinded. `extend_velocity` (`:257-282`) builds its "normal" from the unsigned Godunov magnitudes, so every component is non-negative and the upwind choice ignores the true normal direction. The adjoint sign in `apply_adjoint_to_unified` is set by "1 of 4 paired coarse runs" (`:761`) and the comment block above it still argues for the opposite sign. This is the operator you intend to build the whole method on.
- **Carve-from-block does not work as wired.** `run_car.py:62` passes `build_unified_geometry(init_mode="full").phi.grid`, which is a constant −dx, not a signed-distance field. `param_body.make` then applies `phi0 − offset`: offsets below dx do nothing, offsets at or above dx flip all air to solid. Measured by my auditor at 2 mm: the secant sizing exits at +9.5 g. The "random carving" in `stress_cars.py --carve` applies random Gaussian velocity blobs through the HJ step; it tests the operators, not the method.
- **The legal block is small.** The full legal envelope after mandatory air weighs ~50.3 g at 1 mm; the body target after hardware is ~33 g. The default parametric body needs a +5.14 mm uniform skin to reach that target. The mass sizing, not the loft and not the adjoint, sets the shape. The design question is "where should 33 g of foam be", and uniform skin offset is the worst possible answer to it (it puts mass everywhere equally, including high and in the wake).

### 1.5 Legality and manufacturing margins are thinner than the checks say

From the Part 4 and legality audit, with line references:

- **"About 120 checks" is ~115 for beam supports, ~95 for CAD supports, and about 20 are constants compared to constants** (T5.1/5.2/5.3/5.6 at `legality.py:453-457`; tether T6.1/T6.2 at `assembly.py:242-246`; T9.5.4 height deviation hardcoded to 0 at `wings.py:324`). T8.2 appears three times, T3.7 six times. The README's "72" is stale.
- **T5.5 is checked as a 1.9 mm wall**, annulus from bore+1.0 to bore+2.9 with 2 mm skipped at each bore end (`legality.py:60-72`), on a pass threshold of 99.9% volume. The manufactured body has the exact bore, so the voxel-bulge excuse no longer applies.
- **T7.4 contact width is the bounding extent including hub and seat** (`wheel.py:110`) with a 0.25 mm margin; a tread chamfer makes the real contact patch illegal and the check will not see it.
- **Three wheel radii coexist**: 14.13, 14.12, 14.05 mm (`geometry_contract.py:125`, `beam_support.py:298`, `legality.py:565`).
- **T4.1 one-piece body cannot fail**: `machined_body()` keeps the largest shell and drops the rest into metadata (`joints.py:313-316`), ungated.
- **Tolerances were moved to pass specific cars**: T4.4.4 halved to 0.5 mm after a 0.43 mm dip failed a car (`legality.py:401-403`); the team-number footprint is a guessed 8 × 14 mm (`:293-296`); T7.9 zone shapes were changed on 2026-11-06 after real cars had body inside them with every check passing, and the decision document admits the dimensions come from diagrams you do not have.
- **The front wing is auto-shifted to a 0.05 mm margin and the recorded parameter is the requested one, not the built one** (`wings.py:141-148`, `assembly.py:260`). The search's parameter and the geometry disagree.
- **The rear wing is not fixed**: its height follows body top + clearances and pylon depth is clamped by the chamber wall (`wings.py:275-295`). It floats with every body change, which is one reason your four rear-wing gains did not add up.
- **Mass margin versus mesh tolerance**: target 48.2 g on a 48.0 g floor; `remesh_file` accepts ±0.5% volume (`mesh_fairing.py:132`) and fairing moves vertices 0.1 mm. On a ~200 cm³ body that is 0.16 g unmeasured, against a voxel mass error you put at ±0.3 g and a foam density you have not measured.
- **Not checked anywhere**: uniform rolling diameter, free spinning, bearing fit, helmet fixed, cartridge angle ±3°, "only listed components", wing thickness on the mesh, cutter stick-out and holder. Support loads were back-fitted so the team's existing disc passes (`beam_support.py:37-43`), with UTS rather than yield and no anisotropy or glue strength. No wing has any strength or deflection check.

### 1.6 Structural waste

- 21,700 lines of non-test Python, 9,150 lines of tests, 4,600 lines of Markdown, for a car. Four generations of method are live in the import graph (four-grid PhiGrid, adjoint HJ carve, Stage-1 proxy carve, parametric loft); three incompatible machinability models (`machining.reachable_air`, `unified_phi.enforce_machinability`, `surface_extraction._find_inaccessible_faces`); two `_drop_islands`; two sources of truth for regulation numbers (`legality.REGS` and `component_contract`); `BUILD_REPORT.md` describes a pipeline that no longer exists; `PLACEHOLDERS.md` items 1-4, 9, 11, 13 are stale.
- Part 3 is almost entirely dead weight: `inner_loop.py`, `gradient_combiner.py`, `convergence.py`, `stability_check.py`, `objective_policy.py`, `optimizer_contract.py` serve a retired loop. `pipeline_interface.py` survives as a binding layer that could be forty lines.
- The default grid is 0.3 mm and every caller monkey-patches ten modules' globals to get 1 mm (`coarse.use_spacing`). A build with mass sizing is 51 s at 1 mm (17 passes, each with two 50-step reinits and four EDTs); 0.3 mm is 37× the cells and has not been run end to end.
- Five "parts" that "must sit side by side", each with its own README, banner and private-repo links, for one program.

## 2. Is carving from the block with an adjoint the best way? No.

| Method | Fits this problem? | Why |
|---|---|---|
| Level-set carving + adjoint (yours) | **No** | Needs a smooth, differentiable objective; yours has 0.5% remeshing discontinuities. Needs a trustworthy gradient; yours failed its test. Needs freedom to carve; the legal block is 50 g against a 33 g target and 67% of drag is in parts you cannot carve. Your own record: 12 of 12 level-set steps raised drag. |
| FFD / `volumetricBSplines` + adjoint | Partly | Fixes the mesh-noise problem (the CFD mesh morphs, no remeshing) and gives consistent sensitivities, but it deforms the CFD body, not your rules-checked body, and your rules engine is the only thing in the repo that works. Worth it only as the noise tool in section 3. |
| Evolutionary (CMA-ES) | No | 100+ evaluations per generation at 35 min each; you cannot afford the population. |
| Surrogate / Bayesian optimisation over a parametric shape | **Yes, for ≤ 30 parameters** | Handles noise natively (GP with a noise term), uses every evaluation, is batch-parallel (your 40 machines), and gives you a posterior you can report instead of a "peak nothing nearby beats". Your decision document already reached this conclusion for the loft (3.8) and then built an adjoint solver anyway. |
| Multi-fidelity | **Yes, as the stopwatch policy** | Screen on medium, confirm on fine with layers, verify the top two wall-resolved in chained jobs, then on the track. |
| Combination | **This is the answer** | Surrogate search over a small parameter set that is mostly parts and layout, with the body as a loft plus a handful of modes placed where a single adjoint map says the body matters; multi-fidelity stopwatch; physical validation gate. |

The honest comparison is not between carving and Bayesian optimisation; it is between optimising a 13 ms lever and optimising 50 ms of levers. Your own measurements say wheel supports, wing, nose, hubcaps and the rear disc moved race time by 2.6–7%, body shaping by 0.5–3%. The adjoint is the right tool for a 500-parameter smooth problem with a quiet objective. You have a 30-parameter rough problem with a loud objective and a 6-hour job limit.

## 3. How to beat the noise

The noise is not solver noise (six machines agreed to 0.28 ms). It is remeshing noise: a 0.01 mm skin change produces a different snappyHexMesh and a 0.5% different drag. Averaging repeats of the same geometry measures nothing. In order of value:

1. **Stop remeshing between neighbours.** Mesh the base car once, then morph the mesh to each candidate with OpenFOAM's `moveDynamicMesh` and a `displacementLaplacian` or RBF motion solver driven by the surface displacement from your level-set/parametric change. Same topology, same cell count, smooth objective, and finite differences become meaningful. This is the single change that would have made your gradient check passable. Cost: the mesh must be good enough for the whole neighbourhood, so re-mesh every time the morph quality degrades (track `checkMesh` max non-orthogonality and skewness). Steps of ±2 mm on a 223 mm body are well within morphing range.
2. **If you must remesh, remesh deterministically against a fixed frame.** You already pin `domain_reference_bounds`; also pin the feature-edge extraction angle, `locationInMesh`, the refinement boxes and the background mesh to the frame, not the car. Then the hash noise shrinks to the surface-snapping noise.
3. **Average over geometry, not over repeats.** Your proposed "few tiny size offsets" is correct; three skins at ±0.01 mm halve σ to ~0.6 ms model (0.3 ms real). It triples cost. Mesh morphing gets you further for free.
4. **Use paired comparisons on the same mesh family.** With morphing, base and candidate share a mesh; the difference is the signal.
5. **Warm starts.** Map the base car's U/p/k/ω onto the candidate (morphed mesh: trivial; remeshed: `mapFields`). Convergence of the mean in 300–500 iterations instead of 1000, and the solutions are correlated, which reduces the difference noise further.
6. **Run the wake unsteady for the confirmation tier only.** For the final two cars, PIMPLE with time averaging over ≥ 20 shedding periods settles the mean the steady solver never will. Not for screening.
7. **Convergence gate on the quantity you use.** You gate on p-residual, standard error and drift of the mean, which is right. Drop the 5e-3 residual gate; it says nothing a steady solver on an unsteady wake can honour.
8. **Noise-aware acceptance.** Replace "best of N beats base by 2σ" with a GP posterior or at minimum a Bonferroni-style threshold (2.8σ for N = 10) and a held-out confirmation on a fine mesh before a step is kept.

## 4. Is the adjoint trustworthy enough to steer? Not today, and probably not worth fixing.

What would make it trustworthy:

- **Consistent discretisation**: morphing mesh (section 3) so that the sensitivity and the finite-difference check live on the same mesh. Until then no check can pass at the precision you need, and a check that fails for mesh reasons tells you nothing about the adjoint.
- **Turbulence**: with 67% of drag from wheel wakes, use `adjointkOmegaSST` fully differentiated (ESI ships it; you have it configured but then freeze it). Frozen turbulence in a separated-wake-dominated flow is not a small approximation.
- **Objective**: your objective is the race time, which depends on drag, lift and mass. You take a drag-only sensitivity and then correct for mass by a soft-volume estimate. If you keep the adjoint, differentiate the full race objective: the lift term and the constant-mass term should be in the adjoint's boundary condition, not in Python afterward.
- **Validation protocol**: pre-register it, run it once, do not move the bar. Directional derivative along the adjoint at steps of 0.1, 0.2, 0.5, 1.0 mm on a morphing mesh, both signs; require the predicted ΔD to match the measured one within 30% at the two smallest steps. Then the per-setting test on the 12 largest. Your current state file records a pass on a test that was invented after the pre-registered test failed; a reviewer will not accept that and neither should you.
- **Fix the operator before trusting any carve**: the Godunov upwinding and velocity-extension bugs in `phi_updater.py` (section 1.4) make even a perfect sensitivity move the surface wrongly.

Even fixed, the adjoint earns its 30 minutes per round only if the body is where the time is. It is not. Use one adjoint map, on the morphing mesh, once, to decide where to put sculpt modes. Then stop computing it.

## 5. Compute plan

What you have: ~100 concurrent 4-core jobs, 6 hours each, OpenFOAM installed from apt every job. What to change:

- **Stop installing OpenFOAM 100 times a day.** Use `container: opencfd/openfoam-default:2412` (or build one image with your Python deps and pull it) in the job. That returns 5–10 minutes of every 35-minute job and removes the apt flakiness your retry loop exists for.
- **Cache the mesh.** With morphing, the base mesh is built once per round and shipped as an artifact; candidates morph and solve. A candidate becomes ~15 minutes.
- **Chain long runs by checkpoint**, as you propose: write `latestTime`, upload as artifact, resume in the next job. The 6-hour limit then only costs you a restart, which makes the wall-resolved confirmation feasible.
- **Batch to the account structure.** One round = one dispatch per account; the main account plans, the others only evaluate. You already do this; keep the `advance` step reading artifacts rather than pushing state through commits every round (112 commits in three days of solver history is a repo being used as a message queue).
- **Risk**: GitHub's Actions terms allow usage related to the project's own development and testing. Multi-account CFD farming is a grey area and can be throttled without notice. Do not make it the only plan.
- **Should you pay?** Yes, a little, for two things only. (1) One dedicated 16–32 core box (Hetzner AX-class, ~€100–200/month, or a spot c7a/c7i instance at ~$1–2/hour used in bursts) for the confirmation tier: a 5 M cell wall-resolved case runs in 2–3 hours there instead of not at all, and the mesh family lives on local disk. (2) A load cell and a data logger (~$100–200) for the thrust and rolling measurements in section 6. Nothing you can buy makes the free farm a better search engine than a better objective does.

## 6. The workflow I would build

Order matters. Each phase has a test that must pass before the next starts.

**Phase 0, one week, no code: measure the inputs.**
- Thrust: fire ≥ 5 cartridges on a load cell at ≥ 1 kHz, in the team's launcher. Record mass before and after. Replace the CSV. Test: impulse and peak within 10% across cartridges; the race model's predicted time for a known car matches a stopwatch run within 5%.
- Rolling and bearing friction: coast-down of the rolling chassis on the track from ~5 m/s; fit μ and a speed-independent term. Replace 0.010.
- Wheel inertia: trifilar or torsion pendulum on the real printed wheel with bearing.
- Block density: weigh an official Model Block. Weigh a printed PA12 test coupon. Weigh glue per joint.
- Tether friction: tow a guide-and-line rig; measure. This decides whether the 1.5 mm ground clearance and guide geometry matter more than the body.

**Phase 1, one week: make the mass and legality story robust.**
- Design to ~47.0 g and trim with ballast at weigh-in. The ballast area exists in the rules for this reason; it is also your only free COM lever. The "no ballast" decision trades a free tuning knob for a 0.2 g margin against ±0.3 g voxel error, unmeasured foam density and ±0.5% remesh volume. That is a scrutineering failure waiting to happen.
- Fix the checks that are weaker than the rules (T5.5 wall, T7.4 contact width, T4.1 fragments, wing parameter recording), delete the constant-versus-constant checks, unify the wheel radius and the regulation constants into one module.
- Add the physical tests as computed margins: 2 kg halo load, 200 g guide pull, 100 g wheel hang, with the real section properties of PA12 and the glue line.

**Phase 2, one week: make the stopwatch honest.**
- Base mesh with layers (y+ ≤ 5 on wheels), morphing for candidates, warm starts, paired differences. Test: skins 0.01 mm apart agree to 0.1 ms model; ±0.5 mm steps along a chosen direction give a monotone drag curve.
- Mesh study on the morphing family: medium/fine/resolved on three cars; report the drag deltas between cars at each level, not the absolute drag. Test: deltas agree in sign and within 30% between medium and fine.

**Phase 3, two to three weeks: the search.**
- Parameters (~25): wheelbase, front axle position, halo position; front wing (angle, flap, height, span, camber); support (beam section, strip, disc recess, hubcap dome); nose (length, shape); rear wing (angle, height, pylon); body loft stations near the front wheels and sidepod leading edges; ballast position (COM). Freeze everything else at the current car.
- Round 0: a 40-point space-filling design across the box, screened on medium. Fit a GP with a noise term. Rounds 1–6: 40 candidates per round from expected improvement, batch-parallel. Confirm the top 5 of each round on fine with layers; keep only fine-confirmed gains. Test: the GP's predicted versus measured on held-out cars has R² > 0.6 by round 2; if not, the parameterisation or the stopwatch is wrong and you stop and fix that rather than running more rounds.
- Body modes: one adjoint map on the base car (morphing mesh, differentiated turbulence) to place 6–10 Gaussian modes where |sensitivity| is highest. Add them to the GP only after the part parameters have converged.

**Phase 4, one week: confirm.**
- Top two cars wall-resolved with chained jobs, then unsteady-averaged on the paid box. Build both. Race them. Compare to the model. Publish the comparison with the car.

**Delete now**: Part 3 (`inner_loop`, `gradient_combiner`, `convergence`, `stability_check`, `objective_policy`), the COM penalties, the four-grid remnants, two of the three machinability models, `pattern.py` (superseded by the solver, which is superseded by the above), the retired population search, `BUILD_REPORT.md`, stale `PLACEHOLDERS.md` items. Collapse the five folders into one package. You will lose roughly 12,000 lines and nothing the car needs.

## 7. What you are missing entirely

- **Launch dynamics.** The thrust acts 30–40 mm above the track (31 mm in this car), and the car's inertia acts at its centre of mass. If the thrust line sits above the centre of mass, the car tips nose-down at launch and the **rear** wheels unload. (An earlier version of this review said the front wheels unload; the moment balance shows the opposite. Corrected 2026-11-08.) With about 9 N of thrust, a 120 mm wheelbase and the centre of mass 10 mm below the thrust line, the front axle gains about 0.75 N, more than the whole static rear load of about 0.3–0.4 N, so the rear lifts until the rear tether guide catches the line and rubs. With a guessed guide friction coefficient of 0.3, that costs about 5 ms. Nothing in the model represents this except a polynomial through invented points (whose asymmetry also points the wrong way). Centre-of-mass height relative to the thrust line, ballast position and guide geometry are first-order levers; a slow-motion launch video checks the model.
- **Tether line.** Two guides, a line with sag and friction, lateral oscillation and yaw. No term, no measurement, no clearance analysis beyond the 10 mm placement rule.
- **The CO2 jet.** A ~200 m/s jet exits the rear 30–40 mm above the track and passes over the rear wing's position. Your rear-wing sweeps were run in a CFD with no jet.
- **Transition.** Body Re ≈ 2.6e5, wheel Re ≈ 4e4. Laminar separation bubbles and transition location decide the wheel drag. You have `kOmegaSSTLM` configured and never use it in the search because it needs the layers you turned off.
- **Unsteadiness and yaw.** Half-car symmetric steady RANS cannot see asymmetric shedding or any side-wind or line-induced yaw.
- **Manufacturing reality.** Cutter stick-out and holder (a 6.25 mm ball reaching 20 mm into a side feature), SLS tolerance (0.1–0.2 mm) on press fits and plugs, glue mass, foam density variance, finish sanding removing 0.1–0.3 mm of surface (and mass). The 1 mm voxel grid against a 3.125 mm cutter radius is coarse; the 0.3 mm production grid has never been run end to end.
- **Rules you have not encoded.** Decal visibility is a ray-cast heuristic with a 0.5% allowance; team number footprint guessed; T7.9 zone shapes from text, not the diagrams; competition regulations (weigh-in procedure, timing, reaction time handling) absent; drawings and paperwork absent, and judged.
- **Validation.** Not one physical run has been compared to the model. Until it has, "mathematical maximum" is a maximum of an unvalidated function with a fabricated input. Build the current car this month and race it; that single number is worth more than the next hundred CFD jobs.

## What to keep

The rules engine as masks on a field, the machining filter idea, the legality harness, the OpenFOAM case builder with its force-health reporting, the race-model integrator (it is correct; it is just fed the wrong curve), the manufacturing-file generation, the test discipline, and the GitHub orchestration pattern. These are the parts a team can hand to next year's team. The search sitting on top of them is not.

## Sources for external numbers

- AeroTune thrust fit (9.2 N, τ = 0.25 s, Pitsco 8 g): https://github.com/JP7000/AeroTune
- 2023 World Finals fastest time 1.090 s: https://www.physics.nat.fau.eu/2023/10/11/recoil-racing-world-champion-2023/
- 2016 record 0.916 s: https://www.formula1.com/en/latest/headlines/2018/8/f1-in-schools-world-finals-2018-set-to-take-pole-position-in-sin.html
