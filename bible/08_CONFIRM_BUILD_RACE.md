# Part 8 — Confirm, build, scrutineer, race, compare

> **Status on 2026-11-08 (branch `rebuild/bible`). Owner: chat E.** Not started.
> See `status/` for live progress and `agents/` for the chat prompts.

Read `00_START_HERE.md` first. This Part takes the car (or up to three cars) chosen at the end of Part 7, checks the prediction with the most accurate CFD the team can afford, exports production files, supports manufacture and paperwork, and compares the built car's real races with the model.

**Compute budget for this Part:** confirmation runs: fine mesh with layers (about 4.5 h each, 9-12 jobs), wall-resolved meshes chained across 2-4 segments of 5.5 h (6-12 segments), unsteady averaging chained across several segments (10-30 segments), production builds at 0.3 mm grid (a few jobs, possibly too big for a 16 GB machine). About 40-60 long jobs. A paid machine (Part 1 section 1.12) may be worth it here; ask the user.

---

## 8.0 Start of Part: the compute question

```
QUESTION (Part 8, compute 1): How many team members are confirming that their GitHub
accounts can be used for Part 8?
Why I need it: Part 8 runs about 40-60 long confirmation jobs (4.5-6 hours each, many chained
one after another), plus production-resolution builds.
Expected load for Part 8: chained runs are sequential, so more accounts help only by running
the different cars and checks side by side; 2 accounts are enough. A rented 32-core machine
would cut the wall time from about a week to about 2 days (about <price>): do you want that?
```

Then compute 2. Record in `STATUS.md`.

---

## 8.1 Confirmation CFD

For each car going to Part 8 (from Part 7's report, at most 3):

| Run | Mesh | Geometry | Purpose |
|---|---|---|---|
| F1-F3 | fine, 3 wall-function layers | as searched (drum wheels unless Part 6 G-1 said otherwise), skins jittered ±0.01 mm | absolute drag on a finer mesh, with its own noise estimate |
| R1 | wall-resolved (`resolved`), chained | real wheel STLs (Part 6 G-1), hubcaps (G-2) | highest-fidelity steady result |
| U1 | fine, unsteady (below), chained | as R1 | mean drag of the real unsteady wake |
| S1 | screen tier at 10, 15, 25 m/s | as searched | the drag exponent for this car (Part 4 / Part 6 6.8) |

### 8.1.1 Unsteady averaging (U1)

The steady solver cannot converge on a shedding wake; its "mean" depends on the averaging window (`openfoam_case.py` documents 7-27% peak-to-peak force oscillation). An unsteady run averages the real time history.

Settings (write a `pimpleFoam` variant of the case; the mesh and boundary conditions are unchanged):

- Start from the converged steady solution of F1 (map it: same mesh, copy the fields).
- `pimpleFoam`, `nOuterCorrectors 2`, `nCorrectors 2`, `nNonOrthogonalCorrectors 1`, second-order time (`backward`), `adjustTimeStep yes`, `maxCo 2`.
- Time scales: car length about 0.26 m at 20 m/s gives a flow-through time of about 13 ms. Discard the first 0.05 s (about 4 flow-throughs), then average forces over at least 0.15 s (about 11 flow-throughs). Use the `fieldAverage` function object for the mean fields and average the `forces` output directly.
- Convergence of the mean: split the averaging period into thirds; the three means must agree within 1%. If not, extend.
- At Co ≤ 2 on a fine mesh (smallest cells about 0.3 mm) the time step is about 3e-5 s, so 0.2 s is about 7,000 steps. On 4 cores at roughly 4-8 s per step this is 8-16 hours: 2-3 chained segments, or a few hours on a 32-core machine.

### 8.1.2 What the confirmation decides

Write these rules into `STATUS.md` before the runs:

- **Predicted time of each car:** from R1 if it finished, else F1-F3 mean, with U1 replacing the steady mean drag if U1 finished. Always say which.
- **If two cars' order changes between the screen tier and the confirmation tier** (beyond their combined uncertainties): trust the higher-fidelity tier, tell the user, and recommend the car that is best at the higher fidelity.
- **Systematic offset:** the ratio D_confirm / D_screen for each car. If it is similar for all cars (within 2%), the search's ranking holds and only the absolute time shifts. Record it.

---

## 8.2 Production geometry

1. Rebuild the chosen car at the production grid spacing (0.3 mm; `--cfd-mm 0.3`; Part 5 section 5.7 measured whether this fits in a 16 GB job). If it does not fit, use 0.5 mm and report the difference in mass and every rule margin against 1.0 mm.
2. Run every Part 5 check on the production files. All must pass with the manufacturing margins. Mass at 3σ must pass.
3. Export, in millimetres, both halves, one closed solid per part (`joints.make_all` already does this into `manufacture/`):
   - `machined_body.stl` (foam, milled),
   - `printed_front_assembly.stl` (nose, front wing, flap, mount, tenon: one SLS PA12 part),
   - `printed_support_front.stl`, `printed_support_rear.stl` (SLS PA12, each with its tether guide),
   - `printed_rwing.stl` (rear wing and pylon),
   - `printed_wheel_front_x2.stl`, `printed_wheel_rear_x2.stl`.
4. Write `manufacture/MANIFEST.md`: each file, material, volume, expected mass (with σ), bounding box, the setups and tool for milling, and the glue gap used.
5. Ask the user to check the files open correctly in their CAM and slicer software before ordering prints.

---

## 8.3 Manufacturing support

Ask, once:

```
QUESTION (Part 8, manufacturing): Which CAM software and machine mill the body (for example
Denford QuickCAM Pro on a Denford router)? Which print service or printer makes the SLS PA12
parts, and what tolerance do they quote? Which glue joins the parts?
Why I need it: I prepare the files and setup notes in the form your tools need.
```

Then prepare:

- **Milling:** the four setups the machinability model assumes (top, bottom, left, right), the 6.25 mm ball-end, the stick-out from Part 3 M10. For each setup, note which faces it cuts and where the rule-required features are (chamber bore is pre-made in the official block; halo pocket; support channels from below; nose pocket at Ref A). List any region the machinability report flagged as needing a flat end mill or hand finishing (the decision document mentions about 0.37 cm³ where rule-required air meets mandatory solid).
- **Printing:** for each printed part, the recommended orientation (wings flat on their chord plane for surface finish and strength along the span; supports with the stub axles horizontal so the stubs are printed along their length; wheels flat on their face for roundness). SLS needs no supports, but orientation still affects strength and accuracy. Say where powder must drain from (the nose shell has a 3 mm drain in `joints.py`).
- **Bearings and stubs:** the stub diameter and the press-fit decision from Part 3 M11.
- **Ballast** (if the team's policy uses it): the capsule location and the expected amount.

---

## 8.4 Drawings and paperwork

The regulations require engineering drawings (the team's decision document cites T1.15, T7.12.2 and T8.1: hatched identification of wheel supports, nose and wing structures). The pipeline produces meshes, not drawings.

Ask:

```
QUESTION (Part 8, drawings): Which CAD package does the team use for the engineering drawings
(Fusion 360, SolidWorks, Onshape, other)? And can you send me the drawing requirements from
the regulations (which views, which dimensions, which hatching)?
```

Then provide:

1. The STLs (mm) and a **dimension sheet** (`manufacture/DIMENSIONS.md`) with every rule-relevant dimension measured on the production files and its rule limit: overall length, width, height, wheelbase, track widths (inner gaps), wheel diameters and contact widths, Ref A and Ref B positions, nose length ahead of Ref A, front-wing heights inboard and outboard, front-wing chord and thickness, rear-wing height, overhang behind Ref B, span, chord, thickness, chamber diameter, depth and axis height, halo notch height, tether guide positions and inner sizes, ground clearance of every part, mass breakdown.
2. Instructions for importing meshes into the CAD package as mesh bodies, and where meshes must be converted to solid bodies for sectioning and hatching (in Fusion 360: Mesh workspace → Convert Mesh, faceted, for small parts; prismatic conversion fails on organic surfaces, so convert only the parts that need sections).
3. A list of views that show each rule (front view for T4.4.2, T7.11, T8.8, T9.7; side view for T4.6, T7.10; top and bottom views for T4.7, T7.9).

The drawings themselves are the team's work.

---

## 8.5 Build quality checks (the team does them; the agent checks the numbers)

For every part as it arrives:

| Check | Tool | Pass |
|---|---|---|
| Mass | 0.01 g scale | within 2σ of `MANIFEST.md`'s expected mass; update `measured.json` with actual densities if not |
| Key dimensions | calipers | within ±0.2 mm of `DIMENSIONS.md` (printed), ±0.3 mm (milled), and inside the rule limit with margin |
| Wheel roundness and contact width | calipers at 4 angles; flat-face check against a straight edge | contact width ≥ 13.0 / 17.0 mm without the edge radii; diameters agree within 0.05 mm |
| Wheels spin freely | spin by hand on the assembled car | no rubbing; spin-down comparable to Part 3 M4 |
| Chamber | official cartridge fits; depth gauge | cartridge sticks out ≥ 5 mm (T5.6) |

After assembly: weigh the car without cartridge. Under ballast policy B or C, add ballast in the capsule to reach the team's target (48.05-48.1 g). Record the final mass and its centre of mass (Part 3 section 3.7.4 method).

---

## 8.6 Scrutineering self-check (before the competition)

Give the team a sheet, one line per rule from `00_START_HERE.md` section 0.6, with: the rule, how a scrutineer measures it (calipers, gauge, view photograph against a grid, the physical load tests), the value on this car, and a tick box. For view-based rules (halo visibility, wheel visibility, decals, wings visible in front view), photograph the car from exactly the front, side and top against a grid and check against the rules.

Do the physical tests the team can safely reproduce: the 100 g wheel hang (hang 100 g from each wheel as the rules describe and check nothing moves or breaks), the 200 g tether guide pull, and the 2 kg halo load (only if the team is confident the method matches the regulation's; a failed test destroys the car, so test on a spare body if possible).

---

## 8.7 Track testing

### 8.7.1 Protocol

- Use the same cartridge batch as Part 3 M1 (the thrust curve the model uses).
- Record per run: time, cartridge full mass, temperature, pressure, humidity (Part 3 section 3.7.3), anything observed.
- Alternate the new car with the reference car from Part 3 M9 (A-B-A-B…). Alternating cancels day and track effects (temperature, line tension, track dust) in the comparison.
- At least 10 runs of the new car and 5 of the reference car, cartridges permitting.
- Film the launch (M8 method) for the first 3 runs: confirm the launch behaviour the model predicts (Part 4 section 4.2.2).

### 8.7.2 What the track can and cannot show

The spread of repeat runs (Part 3 M9's track noise σ_track) limits what a track can distinguish. To detect a difference Δ between two cars with 80% power at the 5% level, each car needs about n ≈ 16 (σ_track / Δ)² runs. With σ_track = 10 ms and Δ = 5 ms, that is 64 runs per car: far more cartridges than the team has. So:

- The track **can** check the absolute predicted time (one car, 10 runs: the mean is known to σ_track/√10) and catch gross problems (launch instability, tether rub, a wheel binding).
- The track **cannot** confirm a few-millisecond ranking between two good cars. That ranking rests on the model and the confirmation CFD. Say this plainly in the final report.

### 8.7.3 Comparison and calibration

- Predicted (Part 4 model, measured inputs, confirmation-tier CFD, venue air density per run) against measured mean, with both uncertainties.
- Pass (write before testing): |predicted − measured| ≤ 3% of measured, or within the combined 2σ.
- If it fails: follow Part 4 section 4.7's diagnosis order on the new car's data. A single thrust-force multiplier fitted on the reference car in Part 4 may be applied here; if the new car needs a **different** multiplier from the reference car, the discrepancy is car-specific (aerodynamics, launch, tether rub), not thrust: investigate with the launch video and the CFD before changing anything.
- Feed every new measurement (part masses, densities, the car's CoM) back into `inputs/measured.json`.

---

## 8.8 Final report (`docs/FINAL_REPORT.md`)

Sections:

1. **Goal and rules:** the 20 m race, the regulations that shaped the car (from `00_START_HERE.md` 0.6).
2. **What changed and why:** the review's findings (00 section 0.2), what each Part fixed, with finding IDs.
3. **Measurements:** every Part 3 experiment, method, result, uncertainty, photos of the rigs.
4. **The race model:** physics (Part 4 section 4.2) including the launch-pitch finding, validation against the reference car.
5. **The stopwatch:** the noise problem and the morphing solution, the experiments that chose the mesh, the mesh study, the speed exponent.
6. **Legality:** the rule checks, how each is measured, the mass policy and its uncertainty budget.
7. **The search:** Stage A ranking, Stage B convergence, Stage C polish, Stage D robustness (from `docs/SEARCH_REPORT.md`).
8. **Confirmation:** fine, resolved and unsteady results; the systematic offset.
9. **The car:** parameters, files, mass breakdown, dimension sheet, photos.
10. **Track results:** runs, conditions, predicted against measured.
11. **Limitations:** steady RANS on the search tier, drum wheels on the search tier (if used), no CO2 jet in the CFD, no yaw, half-car symmetry, the launch model's simplifications, the track's inability to confirm small rankings.
12. **What next season should do first:** the three highest-value next steps, decided from the evidence.

This report is the team's engineering story. Write it plainly, with numbers and their uncertainties, and without overstating: "the fastest car our documented search found under this model", never "the fastest possible car".

---

## 8.9 Exit gate for Part 8 (and for the project)

- [ ] Confirmation runs done for each Part 8 car; the predicted time stated with which tier it comes from.
- [ ] Production files pass every check; `MANIFEST.md` and `DIMENSIONS.md` written.
- [ ] The car built; every part checked; final mass and CoM recorded.
- [ ] Scrutineering self-check sheet complete.
- [ ] Track tests done; predicted against measured written up.
- [ ] `docs/FINAL_REPORT.md` written and given to the user.
- [ ] `STATUS.md` shows every Part's gate passed or explicitly waived by the user with a reason.
