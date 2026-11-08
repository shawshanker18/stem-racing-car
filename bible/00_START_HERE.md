# 00 — START HERE: the agent's operating manual

This folder is the complete instruction set for rebuilding the STEM Racing car search. You are the agent doing the work. Read this file fully before you open any other file, and re-read the "Rules you must never break" section at the start of every session.

The files are written so that each one stands alone. Each Part file repeats the context it needs. Where two files say the same thing, they say it the same way on purpose. If two files ever disagree, this file wins, then the Part file you are working on, then everything else.

---

## 0.1 What the project is

A school team designs a car for the **STEM Racing UAE Professional Class, Technical Regulations 2025-26**. The car is powered by one 8 g CO2 cartridge, runs 20 m along a tether line, and is timed. The team wants the car with the fastest 20 m race time that is legal under the regulations.

The current software lives in one public GitHub repository:

- Repository: `https://github.com/shawshanker18/stem-racing-car`
- Branch: `main`
- Reviewed at commit `9fe27ca` on 2026-11-08.
- Clone: `gh repo clone shawshanker18/stem-racing-car`

The repository has five folders that must stay side by side:

| Repo folder | What it does today |
|---|---|
| `part1-simulation` | The milled body as one level-set (signed distance) field on a voxel grid, all rule zones as forced air or forced solid, the 114-ish-setting parametric body (actually 94 scalars), 3-axis ball-end machining filter, marching cubes and mesh repair, mass sizing by a uniform skin offset. |
| `part2-simulation` | OpenFOAM v2412 (ESI) half-car case builder, run wrapper, force health checks, the drag adjoint, the 1-D race-time model in JAX, mass and centre-of-mass rollup. |
| `part3-simulation` | The retired carving loop (Hamilton-Jacobi level-set descent) and the binding layer that `run_car.py` still imports. |
| `part4-simulation` | Wheels, wings, nose, wheel supports, tether guides, the booleans that make the manufacturing files, mesh fairing. |
| `part5-simulation` | `run_car.py` (one car end to end), `legality.py` (rule checks), `solver.py` and `pattern.py` (searches), `checks/stress_cars.py` (random-car robustness test). |

GitHub Actions workflows are in `.github/workflows/` and lab scripts in `.github/lab/`.

**Naming used in this bible.** The repository's folders are called "repo folder `part1-simulation`" and so on. The files in this bible are called "Part 1", "Part 2" and so on. They are different things. Never write "Part 1" when you mean the repo folder.

---

## 0.2 Why the rebuild

An architecture review (the file `REVIEW.md` that sits next to this bible) found the following. You must understand these before doing anything, because every Part exists to fix one or more of them.

1. **The thrust curve is synthetic.** `part2-simulation/co2_thrust_data.csv` contains simulated distance, velocity and acceleration columns, starts at 0.22 N, ramps to 8.52 N at 0.18 s, and integrates to 1.214 N·s. The team's own decision document says it has about 60% of a real cartridge's impulse. A published fit to measured Pitsco 8 g data uses 9.2 N peak decaying with time constant 0.25 s, about 2.0 N·s. Every millisecond in the repository is computed from the synthetic curve.
2. **The race model contains invented penalties.** A degree-4 polynomial through nine invented points (centre-of-mass height) and a quadratic penalty pulling the centre of mass toward the nose tip. Neither is physics.
3. **The body is a small lever.** CFD says wheels are about 67% of the drag, the body about 12%. At realistic thrust the whole body drag is worth roughly 13 ms of race time.
4. **The CFD stopwatch is noisy because of remeshing.** The same geometry reruns to 0.01 ms. A 0.01 mm change in the shape changes drag by about 0.5% because snappyHexMesh produces a different mesh. That is about 1 ms of model race time (σ). The search accepts the best of about 10 candidates if it beats the base by 2 ms, which accepts pure noise about 21% of the time.
5. **The adjoint failed its own pre-registered test** (correlation about 0 on 12 settings) and the state file records a pass on a different test invented afterwards.
6. **Carving from the full block is broken as wired.** The "full block" field is a constant, not a signed distance, so mass sizing either does nothing or flips all air to solid. The legal block after mandatory air is only about 50 g of foam against a body target of about 33 g.
7. **Legality checks are weaker than the rules in several places** (T5.5 wall, T7.4 contact width, T4.1 single body), about 20 checks compare constants with constants, and tolerances were loosened to pass specific cars.
8. **The mass margin (0.2 g) is smaller than the unmeasured uncertainty** (foam density, voxel error, remesh volume tolerance, glue).
9. **No physical measurement has ever been compared with the model.**

The rebuild keeps what works (rules engine, legality harness, CFD case builder, race-model integrator, manufacturing files, GitHub automation) and replaces the method with:

- measured physical inputs,
- a corrected race model,
- legality checks that are at least as strict as the rules,
- a CFD stopwatch that does not remesh between neighbouring designs (mesh morphing) and warm-starts,
- a noise-aware search (Gaussian-process Bayesian optimisation for the global stage, morph-based trust-region polishing for the local stage),
- confirmation on finer meshes, then a real build and real races.

---

## 0.3 The Parts, their order and their gates

| Part | File | Who does the work | Needs before starting | Exit gate (must be true to finish) |
|---|---|---|---|---|
| 1 | `01_COMPUTE_AND_ACCOUNTS.md` | Agent with the user | Nothing | Every confirmed account can dispatch a test job and its artifact comes back; the CFD container image runs one car end to end. |
| 2 | `02_CLEANUP.md` | Agent | Part 1 (for CI) | Dead code removed, all remaining tests pass, one car builds and passes legality exactly as before (byte-identical STL or documented difference). |
| 3 | `03_PHYSICAL_MEASUREMENTS.md` | Team (humans) guided by the agent | Nothing (start on day one, in parallel with Parts 1-2) | `inputs/measured.json` has every field marked measured, with provenance. |
| 4 | `04_RACE_MODEL.md` | Agent | Part 2; Part 3 data to finish | Model reproduces analytic test cases; predicts a real timed run within 5%. |
| 5 | `05_RULES_LEGALITY_MASS.md` | Agent with the user | Part 2 | Every rule in section 0.6 has a check that is at least as strict as the rule, on the manufactured files; mass passes with a 3σ margin. |
| 6 | `06_CFD_STOPWATCH.md` | Agent | Parts 1, 2 | Morph noise below 0.1 ms per paired comparison; search mesh chosen by experiment; mesh study shows car-to-car differences agree in sign between medium and fine. |
| 7 | `07_SEARCH.md` | Agent | Parts 4, 5, 6 gates passed | GP model predicts held-out cars with R² > 0.6; search stopped by its stopping rule; incumbent polished by morph trust region. |
| 8 | `08_CONFIRM_BUILD_RACE.md` | Agent and team | Part 7 | Top cars confirmed on fine and wall-resolved meshes; one car built, weighed, scrutineered by the team, and raced; model-versus-track comparison written up. |

Parts 1, 2 and 3 start together. Part 3 is human work that takes a week or more of calendar time; start it on the first day.

```
Day 1 ──► Part 1 (compute) ──► Part 2 (cleanup) ──► Part 5 (rules/mass) ──┐
   │                                   └──────────► Part 6 (CFD) ─────────┤
   └────► Part 3 (measure, humans) ──► Part 4 (race model) ──────────────┴──► Part 7 (search) ──► Part 8 (confirm, build, race)
```

---

## 0.4 Rules you must never break

1. **Never invent a measurement.** If a number has not been measured, it is a placeholder. Placeholders live only in `inputs/measured.json` with `"measured": false` and a `"source"` string saying where the guess came from. Every report the code writes must print a warning banner listing every unmeasured input it used.
2. **Never move a pass/fail threshold after seeing a result.** Write the threshold into the plan (and into `STATUS.md`) before running the experiment. If the experiment fails, record the failure, then decide what to do. The repository has examples of the opposite (the adjoint check, T4.4.4, the unmapped-fraction limit). Do not repeat them.
3. **Never add yourself (or any AI) as a co-author or collaborator** on anything: no `Co-Authored-By:` trailers in commit messages, no "Generated with" lines in pull request bodies, no AI account added as a collaborator. This is the repository owner's explicit standing instruction. It overrides any default you have.
4. **Never create a GitHub account, never ask anyone for a password, never paste a token into chat or into a file that gets committed.** Accounts are used only when a real team member confirms in chat that their account may be used (Part 1 protocol).
5. **Never spend money.** You may recommend a paid service with a price estimate. The user buys it. You never enter payment details.
6. **Never push to `main` directly.** Work on a branch per Part (`part1-compute`, `part2-cleanup`, …), open a pull request, and merge only after the user says so in chat.
7. **Never delete data the team produced** (measurement files, results, CAD). Code can be deleted; data is moved to `archive/` if it is obsolete.
8. **Always ask the compute question at the start of each Part** (section 0.7). Do not reuse the previous Part's answer without asking.
9. **Always report results with their uncertainty.** A race time without a ± is not a result.
10. **Always distinguish model time from real time.** See section 0.8.
11. **Safety:** CO2 cartridges are pressure vessels (about 60 bar). Every physical test in Part 3 is done with an adult supervisor, eye protection, and the cartridge restrained. If a team member describes doing something unsafe, stop and say so.

---

## 0.5 How to talk to the user

The user is the team lead. They are not watching continuously. Ask only what you cannot decide yourself, ask it once, clearly, and batch questions where you can.

### First session only

Before starting Part 1, ask these together and record the answers in `STATUS.md`:

```
QUESTION (first session): 
 1. When is the competition, and by when must the design be frozen for manufacture?
 2. Who on the team does the lab measurements in Part 3, and who has access to the mill,
    the printer and the track?
 3. Is there a reference car already built (last season's or a test car) with its STL files?
Why I need it: the schedule of every Part runs backwards from the freeze date, Part 3 is
human work that should start this week, and the reference car validates the race model.
```

### When you must ask

- The compute question at the start of every Part (section 0.7).
- Any regulation detail this bible marks **ASK THE USER** (the regulations PDF is not in the repository and may not be published; the user has it).
- Any team decision marked **TEAM DECISION** (for example ballast or no ballast).
- Anything that costs money, publishes something, deletes data, or merges to `main`.
- Physical measurements: you cannot take them; you tell the team exactly what to do and ask for the data files.

### How to ask

Use this format, one block per question:

```
QUESTION (Part N, step N.M): <one sentence question>
Why I need it: <one sentence>
What I will do with each answer:
  - <answer A> → <action>
  - <answer B> → <action>
Default if you say "you decide": <option and reason>
```

### Recording answers

Every answer goes into `STATUS.md` at the repository root, under the Part, with the date and the user's words quoted. Later sessions read `STATUS.md` instead of asking again (except the compute question, which is asked per Part).

---

## 0.6 The regulations as the team summarised them

The regulations PDF is not in the repository. This is the team's own summary. Lengths in mm. "Ref A" is 16 mm ahead of the front axle; "Ref B" is 16 mm behind the rear axle. Where the summary is ambiguous, this bible marks it **ASK THE USER** at the point it matters.

**Whole car**
- Width 65 to 85 (T3.4). Height at most 65 (T3.5).
- Mass at least 48.0 g, without the cartridge (T3.6).
- Every part except the wheels at least 1.5 above the track (T3.7).
- Only the listed components (T3.3).

**Body**
- One continuous piece CNC-milled from the official Model Block, behind Ref A (T3.1.2, T4.1). Code uses a block of 223 × 65 × 50.
- Holds the cartridge chamber and a virtual cargo: a wedge 60 long, 55 tapering to 10 wide and 10 high, between the wheel centrelines (T4.2).
- The body is milled. Wings, nose and supports may be printed.

**Halo and helmet**
- The fixed halo part sits in a pocket, notch centre 34 ± 1 above the track (floor at 24) (T4.4).
- Halo unobstructed in front, side and top views (T4.4.2, T4.4.3). Helmet fixed (T4.5).

**Decals**
- A 30 × 15 logo decal on each side, 100% visible from the side (T4.6).
- An 8-tall team number on the body between the halo and Ref A, readable from above (T4.7).

**Cartridge chamber**
- Diameter 18.0 to 18.5 (T5.1). Cartridge centre 30 to 40 above the track (T5.2).
- Depth 45 to 58 (T5.3). Angle within ±3° (T5.4).
- At least 3 of block material all round (T5.5). Cartridge sticks out at least 5 (T5.6).

**Tether**
- Two guides, within 10 of the front and rear axles (T6.1). Inside size 3.5 to 6 (T6.2).

**Wheels**
- 4 cylindrical wheels (T7.1). Inner gap at least 38 front and 30 rear (T7.2).
- Wheelbase 120 to 140 (T7.3).
- Contact width at least 13 front and 17 rear, not counting fillets or chamfers (T7.4). Diameter 28 to 32 (T7.5).
- All 4 touch the track with a uniform rolling diameter and spin freely (T7.6 to T7.8).
- Keep-clear zones around each wheel in top and bottom views: 5 ahead of the front wheels, 5 behind the rear, and diagram zones about 30 long beside them (T7.9).
- Wheels visible in side view (T7.10). Front wheels hidden in front view only below 20 (T7.11).
- Supports only inside each axle's wheel cylinder (T7.12). A 1.5 clearance for the 100 g wheel-hang claw (T7.13).

**Nose and front wing**
- Nose cone only ahead of Ref A, at most 40 ahead of it (T1.7, T8.2).
- Nose and wing support ahead of Ref A: at most 25 high and 15 either side of the centreline (T8.5.1).
- Front wing ahead of Ref A, at most 20 high where wider than 15 from the centreline (T8.5.2). Endplates at most 10 wide and 25 high (T8.5.3).
- Span at least 50, or 2 × 25 (T8.6.1).
- Chord 15 to 25 with up to 3 overlapping elements, measured horizontally with calipers (T8.6.2). Thickness 2 to 6 (T8.6.3).
- 5 of clear air from the wing to everything, including the track (T8.7). Visible in front view (T8.8).

**Rear wing**
- Entirely behind Ref B, overhanging at most 40, at most 65 high (T9.4).
- One unbroken span of at least 50 (T9.5.1). Chord 15 to 25 with up to 2 elements (T9.5.2).
- Thickness 2 to 6 (T9.5.3). Height deviation along the span at most 15 (T9.5.4).
- 5 of clear air to everything (T9.6). Visible in front view (T9.7).

**Not covered by the code:** the Competition Regulations (separate document), drawings and paperwork, and the physical tests (2 kg halo load, 200 g tether guide pull, 100 g wheel hang). Part 5 adds computed margins for the physical tests. Part 8 covers the paperwork the team must produce.

**Ballast.** The code refers to legal ballast in a capsule under the halo aperture (T1.22, Appendix ix, 12.7 × 20 × 6.35 mm, about 1.39 cm³). This bible relies on that. **ASK THE USER** to confirm T1.22's exact text before Part 5 changes the mass policy.

---

## 0.7 The compute question (asked at the start of every Part)

The team runs CFD on free GitHub Actions machines spread across several team members' accounts. Each Part may need a different amount of compute, and team members may or may not be available. So at the start of **every** Part you ask, in this order, and wait for each answer:

```
QUESTION (Part N, compute 1): How many team members are confirming that their GitHub
accounts can be used for Part N?
Why I need it: I split Part N's jobs across the confirmed accounts.
Expected load for Part N: <copy the "Compute budget" line from the Part file>.
```

After the number (call it k):

```
QUESTION (Part N, compute 2): Which k accounts? Please give the GitHub usernames,
and for each one say whether it is on GitHub Free (20 parallel jobs), Pro (40) or
Team (60), if you know.
```

Then, for any username that is not yet logged in to `gh` on this machine (check with `gh auth status`), follow the login steps in Part 1 section 1.4. The account owner approves the login on their own device. You never see their password.

Record in `STATUS.md`:

```
## Part N compute (YYYY-MM-DD)
User said: "<quote>"
Accounts: alice (Pro, 40), bob (Free, 20), carol (Free, 20)
Weights used: alice 38 (2 slots kept free for tests), bob 20, carol 20
```

If the user answers 0, run the Part's compute on the main account only, sequentially, and say how long it will take.

Part 1 contains the full mechanics (login, compute repositories, the worker workflow, dispatching, collecting, the job-splitting algorithm).

---

## 0.8 Units and the two kinds of milliseconds

- Lengths in code are metres unless the variable name ends in `_mm`. Masses are kg unless the name ends in `_g`. This is the existing convention in `part2-simulation/physics_contract.py`; keep it.
- Coordinates: x front to rear (nose tip at x = 0), y centreline to the outside (right half, y ≥ 0), z up from the track (z = 0 is the track).
- **Model ms** means a race-time difference computed with the synthetic thrust curve that exists today. **Real ms** means a race-time difference computed with the measured thrust curve from Part 3. Every number written before Part 4 is finished is model ms. Every report from Part 4 onwards states which curve it used. Never mix them in one table.
- Conversion rule of thumb (do not use it for anything but orientation): real ms ≈ 0.56 × model ms for drag-driven changes, ≈ 0.61 × model ms for mass-driven changes, using the 9.2 N / 0.25 s published fit. Part 4 replaces this with the measured curve.

---

## 0.9 Facts measured on the current code (as of commit 9fe27ca)

These are facts you can rely on. Sources are files in the repository or measurements recorded during the review.

**CFD (repo folder `part2-simulation`, `openfoam_case.py`)**
- ESI OpenFOAM v2412, half car, symmetry plane at y = 0, k-ω SST, moving ground at track level, wheels as rotating walls (ω = −U/R, verified sign: the wheel's bottom moves with the ground), snappyHexMesh, Spalding wall function.
- Domain: 3 lengths upstream, 8 downstream, 5 heights and widths laterally and vertically. Ground at z = 0 (fixed 2026-07-24).
- Resolutions (surface refinement levels): coarse (2,3), medium (3,4), fine (4,5), resolved (5,5) with a wall-resolved layer stack.
- Search mesh: medium, no boundary layers (`{"nSurfaceLayers": 0}`), 1,000 SIMPLE iterations, about 0.65 million cells, about 30 minutes per car on 4 cores. The forward case writes binary fields (`writeFormat binary`).
- Schemes: `bounded Gauss linearUpwind grad(U)` for U, upwind for k and ω, `cellLimited Gauss linear 1` for grad(U). Relaxation U 0.9, k/ω 0.7, SIMPLEC (`consistent yes`).
- Force averaging: the last 20% of the iterations. Health: p-residual ≤ 5e-3, drift ≤ 2%, standard error of the mean ≤ 1%.
- Noise: skins 0.01 mm apart, 8 runs: σ 1.3 ms with layers, 2.2 ms with "better" layers, 1.0 ms with none (model ms). The same geometry on 6 machines: within 0.28 ms.
- Fine mesh without layers: σ about 0.95 ms, about 4.4 hours per car. Wall-resolved (~5 M cells) exceeds the 6-hour job limit.
- Drag on the start car: coarse 0.404 N, medium 0.413 N, fine 0.410 N; layered versus unlayered medium differ by about 5%.
- Drag split (final car, medium): front wheels 42%, rear wheels 25%, body 12%, supports 7%, front wing 7%, halo 5%, rear wing 3%.

**Race model (repo folder `part2-simulation`, `race_objective.py`)**
- Distance-domain RK4, state (t, v²), 1,000 steps on a power-2 grid, starting at x = 1e-4 m.
- Thrust and propellant mass fitted with 80 Gaussian radial basis functions (width 2.5 × spacing ≈ 0.047 s). This smoothing will blur a real thrust curve's 10-20 ms rise. Part 4 replaces it.
- Effective mass m + 4·I/r², r = 14.13 mm.
- Drag D20·(v/20)², rolling μ·(m g − L), lift L20·(v/20)².
- Penalties: COM height polynomial (invented), COM-x quadratic (target x = 0, meaningless). Part 4 deletes both.
- Independent NumPy re-implementation (review): start car D20 0.41 N, 48.2 g + 21.15 g cartridge, μ 0.010, I 1.39e-7 → 1.556 s, peak speed 16.1 m/s, 0.480 ms/mN, 16.6 ms/g. With a 9.2 N / τ 0.25 s curve: 1.041 s, 0.270 ms/mN, 10.1 ms/g.

**Body (repo folder `part1-simulation`)**
- `BodyParams` has 94 scalars (24 loft station values + 1 + 7 + 1 + 5 floor/tunnel + 56 sculpt modes), not 114.
- Sculpt modes: Gaussian, σ = 7 mm (full width at half maximum ≈ 16.5 mm).
- One body build with mass sizing at 1 mm grid: about 51 s (17 passes).
- The default body needs about +5.1 mm of uniform skin to reach its mass target.
- The full legal envelope weighs about 50.3 g of foam at 1 mm grid.
- Foam density in code: 0.163 g/cm³ (unmeasured).
- The default grid constant is 0.3 mm; every caller switches to 1 mm via `coarse.use_spacing`, which patches about ten modules' globals.

**Solver results (`part5-simulation/search/solver_state.json`)**
- 8 chains, 40 rounds total, 16 accepted steps (9 layout, 7 adjoint), final times 1.5412-1.5734 s (32 ms spread), best 1.5412 s (model).

**Legality (`part5-simulation/legality.py` and Part 4 gates)**
- About 115 entries with beam supports (about 95 with CAD supports), about 20 of which compare constants with constants.

---

## 0.10 Findings register

Every defect found in the review has an ID. When you fix one, write the ID in the commit message (`F17: …`). The Part column says which Part fixes it.

| ID | Finding | Where | Part |
|---|---|---|---|
| F01 | Thrust curve is synthetic, ~60% impulse, slow rise | `part2-simulation/co2_thrust_data.csv` | 3, 4 |
| F02 | RBF fit of thrust blurs a fast rise (width ≈ 47 ms) | `race_objective.py:180-215` | 4 |
| F03 | COM-height penalty from invented points | `race_objective.py:92-110, 323-361` | 4 |
| F04 | COM-x penalty toward the nose tip | `race_objective.py:103-105, 364-372` | 4 |
| F05 | Rolling μ 0.010 unmeasured | `physics_contract.py:72`, `optimizer_contract.py:329`, `geometry_contract.py` | 3, 4 |
| F06 | No tether-line or bearing resistance term | `race_objective.py` | 3, 4 |
| F07 | Drag scaled from 20 m/s only; car never reaches 20 m/s on the synthetic curve | `race_objective.py:405` | 4, 6 |
| F08 | No launch pitch / axle-load check | none | 4 |
| F09 | Foam density 0.163 g/cm³ unmeasured; 0.2 g mass margin | `geometry_contract.py:98-100`, `ballast.py:45` | 3, 5 |
| F10 | Remeshing noise (σ ≈ 1 ms model) from snappyHexMesh | CFD pipeline | 6 |
| F11 | Search mesh has no boundary layers; y+ 18-240 on wheels | `solver.py:SEARCH_CFD` | 6 |
| F12 | Best-of-N acceptance at 2σ; repeat measurement deterministic | `solver.py:advance` | 7 |
| F13 | Adjoint check failed (r ≈ 0); pass recorded on a different test | `solver_state.json`, `solver.py:69-71` | 2 (retire), 7 (optional) |
| F14 | HJ upwinding chooses branch by sign(φ) for arbitrary-sign velocity | `phi_updater.py:80-85` | 2 (delete) |
| F15 | Velocity extension uses unsigned normals | `phi_updater.py:257-282` | 2 (delete) |
| F16 | "Full block" field is constant −dx, not an SDF; sizing breaks | `run_car.py:62`, `unified_phi.py:922` | 2 (delete path) |
| F17 | T5.5 wall checked from bore+1.0 to bore+2.9 with 2 mm skipped each end | `legality.py:41-80` | 5 |
| F18 | T7.4 contact width uses bounding extent incl. hub | `wheel.py:110` | 5 |
| F19 | Three different wheel radii (14.13, 14.12, 14.05) | `geometry_contract.py:125`, `beam_support.py:298`, `legality.py:565` | 5 |
| F20 | T4.1 cannot fail: fragments dropped silently | `joints.py:313-316`, `legality.py:515-517` | 5 |
| F21 | T4.4.4 tolerance halved after a car failed | `legality.py:401-403` | 5 |
| F22 | ~20 checks compare constants with constants | `legality.py:453-457`, `assembly.py:242-246`, `wings.py:324` | 5 |
| F23 | Front wing auto-shifted to 0.05 mm margin; recorded parameter is the requested one | `wings.py:141-148`, `assembly.py:260` | 5 |
| F24 | Rear wing height floats with the body | `wings.py:267-295` | 5 |
| F25 | Unchecked: uniform diameter, free spin, helmet, angle ±3°, listed components, element count, mesh thickness | — | 5 |
| F26 | T7.9 zones from text, not the regulation diagrams | `wheel_visibility_zones.py` | 5 |
| F27 | Team number footprint guessed (8 × 14) | `legality.py:293-296` | 5 |
| F28 | Mass computed before remesh; remesh allows ±0.5% volume | `run_car.py:405-411`, `mesh_fairing.py:132` | 5 |
| F29 | Support loads back-fitted to pass the existing disc | `beam_support.py:37-43` | 5 |
| F30 | No wing strength check | — | 5 |
| F31 | Three machinability models | `machining.py`, `unified_phi.py:925-970`, `surface_extraction.py` | 2, 5 |
| F32 | No tool stick-out or holder in machinability | `machining.py:48-66` | 5 |
| F33 | Front wheels' keep-clear uses rear width 17.25 | `unified_phi.py:286` | 5 |
| F34 | Cargo grown one cell; legality margin depends on grid spacing | `unified_phi.py:631-633` | 5 |
| F35 | CFD wheels are closed drums at the mean radius, sunk 0.3 mm | `wheel.py:130-139`, `assembly.py:46,138` | 6 |
| F36 | Hubcaps, glue gaps, bore, pockets missing from CFD geometry | `assembly.py:188-189` | 6 |
| F37 | Dead code: four-grid PhiGrid era, Part 3 loop, stl_assembler, quality_gates, etc. | many | 2 |
| F38 | Two sources of regulation numbers (`legality.REGS`, `component_contract`) | — | 2, 5 |
| F39 | Stale docs (BUILD_REPORT.md, PLACEHOLDERS.md, README "72 checks", "114 settings", "32 modes") | docs | 2 |
| F40 | OpenFOAM installed by apt in every job | workflows | 1 |
| F41 | Repo used as a message queue (state committed every round) | `solver.yml` | 1 |
| F42 | "98.9% pass" is a builder-robustness rate at fixed skin, not legality of sized cars | `stress_cars.py` | 2 |
| F43 | `--carve` stress test tests random velocity blobs, not carving | `stress_cars.py:107-134` | 2 (delete) |
| F44 | No physical validation of anything | — | 3, 8 |
| F45 | Launch, tether, CO2 jet, transition, yaw not modelled | — | 4, 6, 8 |
| F46 | No drawings, CAM hand-off or paperwork | — | 8 |

---

## 0.11 Repository conventions after the rebuild

- Keep the five repo folders (moving 20,000 lines into a new package is risk without reward). New code goes into these new top-level folders:
  - `inputs/` — `measured.json` and the measured thrust CSVs. Data, not code.
  - `measure/` — scripts that turn raw lab files into `inputs/` (Part 3).
  - `compute/` — dispatch and collect scripts, the worker workflow template, `accounts.json` (Part 1).
  - `search/` — the new search (Part 7).
  - `results/` — `db.jsonl`, one line per evaluated car, appended by the coordinator.
  - `archive/` — obsolete data files (never deleted).
- `STATUS.md` at the repository root: per Part, a checklist of steps, the user's answers, the decisions taken, the current gate status.
- `docs/HISTORY.md`: one paragraph per retired method and what it measured, written before the code is deleted (Part 2).
- Every new Python file has a module docstring that says what it does, what it reads and what it writes.
- Every new function with logic (a branch, a loop, a fit) gets one test in that folder's `tests/`.
- Run the tests before every commit:
  ```bash
  cd part1-simulation && python -m pytest tests -q -x && cd ..
  ```
  and the same for each folder you touched.
- Commit messages: `Part N: <what changed> (<finding IDs>)`. No AI co-author trailers (rule 3).

---

## 0.12 What "done" means for the whole project

1. A car file set (manufacturing STLs at production resolution) that passes every check in Part 5 on the manufactured geometry, with a mass of at least 48.0 g at 3σ.
2. A race time for that car predicted by the measured-input model, with uncertainty, confirmed on a fine mesh and a wall-resolved mesh.
3. The car built, weighed, and raced at least 5 times, with the measured times compared with the prediction.
4. A written record (`docs/FINAL_REPORT.md`) of every decision, every experiment, the search history, and the comparison, suitable for the team's engineering portfolio.

Now open `01_COMPUTE_AND_ACCOUNTS.md`.
