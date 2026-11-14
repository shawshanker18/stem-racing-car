# Part 2 proof: results against BUILD_SPEC section 8

Every number here comes from a GitHub run (or a Codespace, where stated). Run IDs
are in the repo named with them. Model times are model times, not track times.

## Summary (2026-11-14)

| BUILD_SPEC section 8 test | result | mark |
| --- | --- | --- |
| Timing noise (16 cars, smooth ladder, each car timed from both frozen airflow states) | **PASS 0.091 ms, confirmed 0.087 ms** | ≤ 0.3 ms |
| Repeatability (same car, 9 machines, 2 cores, frozen reference) | **PASS 0.01 ms** | ≤ 0.1 ms |
| Ranking, search vs fine mesh | **PASS** Spearman 0.963–0.973, pairs 95.8–98.0 % | ≥ 0.9, ≥ 90 % |
| Chained long runs | **PASS** 0.0005 ms on one machine | within 0.1 % |
| Disk-saving change on fine/resolved | bit-identical on one core (slim2) | identical |
| Whole-car test with chained fine and resolved cars | **green**, shawshanker18/stem-racing-compute 43397841507 on 30d92d0 | all jobs pass |

Race model on the measured thrust; drag corrected by 1/1.09 ± 0.04 (Q11); friction, wheels and tether are stated constants (below). Model times are relative, not track times. Still open: drag-bias re-rank at 1.05/1.13 and friction 0.005/0.020 once Part 5 has top cars; noise and repeat on the fine mesh (the search now runs on fine); model vs a real timed run.

## Ranking agreement (Step 3): PASS

| | value | pass mark |
| --- | --- | --- |
| Spearman, all 20 cars | 0.965 | ≥ 0.9 |
| pairs > 3 ms apart on fine that agree, all 20 | 170 / 173 = 98.3 % | ≥ 90 % |
| Spearman, 18 converged cars (C4, C7 fine runs unconverged, left out) | 0.963 | ≥ 0.9 |
| pairs agreeing, 18 converged | 135 / 137 = 98.5 % | ≥ 90 % |

- Cars: Part 5's stress cars, 12 lofted (L0–L11, seed 47000) and 8 carved (C0–C7,
  seed 47001), built by `rank_study.py`, all at commit f5161e5.
- Search mesh (medium, no layers, 1000 iterations): mxnviir/stem-racing-car run
  42660880514 (rs3), 20 of 20.
- Fine mesh (1000 iterations): shawshanker18/stem-racing-car run 42660871261 (rf3),
  18 of 20. C0 and L0 needed more than the 5 h stage limit / 6 h job limit and were
  rerun on 4-core Codespaces (blackwingftc-lang, mxnviir) at the same commit with
  only the stage-runner `cd` fix (no effect on results) and stage_timeout_s 40000:
  C0 T = 1.61772 s, L0 T = 1.56052 s, both converged.
- Statistics: shawshanker18/stem-racing-car runs 42820976300 (20 cars) and
  42820970393 (18 converged), `rank_study.py stats`.
- Ranked on `T_at_target_s` (each car's race time at the mass target), so the order
  is set by aerodynamics, not by mass differences between the cars.

## Reshaped meshes on carved shapes (remesh limit)

Six local cuts from Part 1's cutter on the start block (nose, sidepod side, tail
top; 0.5 and 2 mm deep, Gaussian patch sigma 8 mm), each timed on a mesh reshaped
from a reference car and on a fresh mesh; reference = the start block through a
negligible cut, so it shares the cutter's milling (shawshanker18/stem-racing-car
run 42804229269, `cut_cars.py`, `p2_reshape_cuts.yml`):

| cut | D fresh N | D reshaped N | diff mN | diff ms | reshaped mesh |
| --- | --- | --- | --- | --- | --- |
| nose 0.5 mm | 0.5933 | 0.5938 | +0.43 | +0.22 | OK |
| nose 2 mm | 0.5939 | 0.5937 | -0.23 | -0.12 | OK |
| rear 0.5 mm | 0.5935 | 0.5949 | +1.36 | +0.70 | OK |
| rear 2 mm | 0.5936 | 0.5937 | +0.07 | +0.04 | OK |
| sidepod 0.5 mm | 0.5956 | 0.5917 | -3.85 | -1.99 | OK |
| sidepod 2 mm | 0.5897 | 0.5896 | -0.11 | -0.05 | OK |

- The same car on two fresh meshes differs by up to 1.8 mN (run 42713902174, where
  every reshape fell back to a fresh mesh), so 5 of 6 cuts agree within that.
- The sidepod 0.5 mm case (3.85 mN) is not explained yet.
- How the reshape got here: plain projection onto the new surface folded one face
  on every cut. Moving each point by the CHANGE of the surface, read from a
  16-digit ASCII copy of the reference mesh, fixed most of it. Smoothing that change
  over 0.5 mm removed the point-to-point jumps at sharp edges. A reference mesh
  reshaped onto itself (zero move) gives the identical drag (+0.04 mN, run 42767113050).

## Timing noise (Step 2; pass mark 0.3 ms): PASS on the search (medium) mesh — 0.091 ms, confirmed 0.087 ms (method A, below); fine mesh being measured

Residual SD of race time about a fitted line, ≥ 15 converged cars at skins
0.006–0.01 mm apart, search mesh (medium, no layers), with the 95 % chi-square
interval and the part explained by each car's own averaging error
(`noise_stats.py`). All after the SIMPLE early stop was removed.

| set-up | sigma ms (95 %) | averaging part ms | run |
| --- | --- | --- | --- |
| fresh mesh per car, 1000 it | 8.65 (6.27–13.93) | 0.61 | blackwingftc-lang 42654416947 |
| fresh mesh, 3000 it | 5.02 (3.68–7.92) | 0.28 | mxnviir 42670749731 |
| fresh mesh + warm start | 6.88 (4.93–11.35) | 0.44 | shawshanker18 42804234820 |
| reshaped mesh (first method, one face folded) | 4.09 (2.96–6.59) | 0.57 | blackwingftc-lang 42654555331 |
| **reshaped mesh + warm start, 1000 it** | **0.78 (0.56–1.25)** | 0.62 | shawshanker18 42830660133 |
| reshaped mesh + warm start, 3000 it (ref 3.945) | 0.71 (0.52–1.12) | 0.34 | shawshanker18 42855557668, stats 42915302504 |
| reshaped mesh only, 1000 it (ref 3.945) | 0.57 (0.41–0.89) | 0.54 | shawshanker18 42896269550, stats 42915322488 |

- **3000 iterations do shrink the averaging part**, from 0.62 to 0.34 ms. That is about
  1/√3, as expected for three times more averaged steps.
- **Both 2026-11-10 ladders show the same drag step** between skins 3.966 and 3.972 mm:
  about 3.7 mN lower, worth about 2 ms. Per part at 3.966 → 3.972 (reshaped only), body
  −2.2 mN and rear wheels −1.5 mN; every other part changes by less than 0.15 mN. A
  straight line fitted through a step leaves most of the residual SD.
- Inside the 12 cars below the step (3.900–3.966), the SD about their mean is about
  0.26 ms reshaped only and 0.33 ms reshaped plus warm start. This is for information
  only, not a pass: the test is the full ladder.
- **Is the step the shape or the mesh? It's the mesh, through a two-way flow.** The same
  ladder reshaped from 3.978 instead (shawshanker18 42915580709, stats 42937310306)
  gives **5.52 ms (4.04–8.70)**, with an averaging part of 0.41 ms. Drag jumps between
  levels about 0.413, 0.428, 0.442 and 0.454 N, and the step at 3.97 mm is gone.
- Same car (3.978), two references: 0.447 N reshaped from 3.945, 0.413 N on its own
  mesh. The difference is all in body drag (0.062 → 0.042 N) and rear wheels (0.116 →
  0.099 N); every other part is within 0.5 mN. That is the same body-and-rear-wheel
  switch the fresh meshes showed.
- So the flow behind the body and rear wheel has more than one steady solution, and
  the mesh picks which one. Reshaping keeps the mesh the same but doesn't stop the
  switch. The 3.945 reference happens to sit well inside one solution, so its ladders
  were quiet; the 3.978 reference sits near the switch.
- Reshape plus warm start from 3.978 (shawshanker18 42937465031, stats 43029712345):
  **4.95 ms**, with the same levels. Starting from one flow does not hold the cars on
  one solution on that older code.
- **On current main the levels are gone for reference 3.945.** Run mw7 (shawshanker18
  42899718105, both, 3000 it, stats 43029734107) gives **0.362 ms (0.265–0.571)**.
  The averaging part is only 0.059 ms. All 16 cars sit at 0.408–0.411 N with body drag
  about 0.034 N, on a different body from the older code.
- **Part of that 0.36 ms is real shape change.** Part 1's body is built on a grid, so
  the skin ladder isn't smooth. Six of the 16 cars (3.930, 3.936, 3.972–3.990) carry
  about 0.035 g less body and about 500 fewer removed cells. Fitting time against skin
  plus that family gives a family effect of −0.62 ms and a residual of 0.25 ms (13
  dof). That figure is fitted after looking at the data, so it is evidence, not a pass.
- Next, a clean test: one car stretched smoothly across its width in 16 steps of about
  0.01 mm (`body_scale_y`, `p2_noise_morph` input `scales`). Also mw10 (reference
  3.978 on main, run 43017128788), to check whether the levels are gone for that
  reference too.

- Fresh meshes put near-identical cars on different drag levels (up to 12 % apart:
  body and rear-wheel drag switch together). A time-accurate run (pimpleFoam, 0.12 s,
  about 11 flow-throughs, shawshanker18 42760508026) kept each car on its own level.
- With one reshaped mesh and a warm start, all 16 cars sit on one branch and drag
  falls smoothly with skin. What remains is mostly each car's averaging error. A
  3000-iteration run of that set-up is next.
- The skins 4.00–4.05 mm of the first runs also carried a Part 1 body step (fixed in
  Part 1 55696e3), so the later ladders stop at 3.99 mm.

| reshaped + warm, 3000 it, ref 3.960 (main code) | 0.42 (0.31–0.66) | 0.14 | mxnviir/stem-car-compute 43066031633 |
| reshaped + warm, 3000 it, ref 3.990 (main code) | 0.58 (0.43–0.92) | 0.21 | blackwingftc-lang/stem-car-compute 43066095540 |

| reshaped + warm, 3000 it, ref 3.978 (main code) | 0.86 (0.63–1.36) | 0.17 | shawshanker18/stem-racing-car 43066046473 |
| **smooth width ladder** (one car, body width x0.9968–1.0028, ~0.01 mm steps), reshaped + warm, 3000 it, ref 3.945 | **0.201 (0.147–0.316)** | 0.14 | blackwingftc-lang/stem-car-compute 43066000504 |

- **At the final stopwatch setting (2 cores, frozen reference p2-ref-3945, 1000 it): 0.093 ms (95 % 0.068–0.147)**, smooth 16-car ladder, mxnviir/stem-car-compute 43195805676. PASS vs 0.3 ms.
- **Confirmed on fresh machines: 0.119 ms (95 % 0.087–0.187)**, mxnviir/stem-car-compute 43142206299 (same set-up, 4 cores).
- **Smooth-change test meets the 0.3 ms mark: 0.20 ms** (upper 95 % bound 0.32). With a shape that truly changes smoothly, the stopwatch noise is 0.20 ms; the larger figures on skin ladders include real body-grid shape steps. Confirmation run ms5 (same set-up, fresh machines) and a no-warm-start variant ms4 are running.

## Repeatability (1 car x 6+ machines; pass mark spread ≤ 0.1 ms): PASS 0.01 ms on the frozen reference (history of the earlier failures kept below); fine mesh being measured

Start car at skin 3.95 mm, fresh search mesh, 1000 iterations, six GitHub machines
(shawshanker18/stem-racing-car run 42864304133): T_at_target 1.57259, 1.57293,
1.57265, 1.57200, 1.57234, 1.57199 s, all converged; **spread 0.94 ms**.

- The earlier 0.28 ms (2026-11) was measured with the SIMPLE early stop, which ended
  every solve at about 170 iterations.
- Run to its full length, the wake keeps moving, so small machine-to-machine
  arithmetic differences change each run's average. The spread is the size of one
  car's averaging error (rms about 0.6 ms on the noise ladders), so the same fix
  applies: longer averaging (3000 iterations running).
- At 0.6 ms per 200 averaged steps, reaching 0.1 ms by averaging alone would need
  about 36 times longer. If longer runs don't get there, this pass mark needs the
  team lead's decision, with this evidence.

- Reshaped + warm start, 1000 it, same car (3.945) on 6 machines (blackwingftc-lang/stem-car-compute 43068512344): T 1.55569–1.55599 s, **spread 0.30 ms** (FAIL vs 0.1 ms; was 0.94 ms on fresh meshes). Each run's averaging error is 0.26 ms, so the spread is still that. 3000 it repeat (rp3) running.

- Same at 3000 it (blackwingftc-lang/stem-car-compute 43066007386): T 1.55719–1.55748 s, **spread 0.29 ms** (FAIL). Averaging error halved (0.13 ms) but the spread did not: the machines differ by more than the averaging. Drag also still creeps between 1000 and 3000 it (0.413 → 0.416 N), so each run is still settling; next check whether the spread comes from parallel arithmetic order.

- **Cause found: running each car on 4 cores.** Same set-up on ONE core per machine (blackwingftc-lang/stem-car-compute 43118251223, 1000 it): all six machines give T = 1.55770 s and D20 = 0.41692 N to every printed digit, **spread 0.000 ms (PASS vs 0.1 ms)**. The 0.29–0.30 ms spread on 4 cores comes from the order the cores add up their parts, which changes run to run. Cost: about 70–80 min per car on one core vs 35–45 on four. Testing 4 cores with a fixed adding order next (rp9, shawshanker18/stem-racing-car 43148978484).
- Two cores (mxnviir/stem-car-compute 43142210991, 1000 it): T 1.55771–1.55772 s, **spread 0.01 ms (PASS)**, same answer as one core.
- Four cores with a fixed MPI adding order (shawshanker18/stem-racing-car 43148978484): spread 0.17 ms, still FAIL; the order of the parallel linear-solver sums is not fixed by that setting. **Decision: the stopwatch runs on 2 cores** (`stopwatch.py` default `--np 2`), which repeats to 0.01 ms. The smooth noise test is being redone at 2 cores (ms7) and 1 core (ms8).
- **Caution, not yet a pass:** one core on main (shawshanker18/stem-racing-car 43142201751): five machines at 1.55641–1.55648 s, one at 1.55773 s (the rp5 value), **spread 1.3 ms**. So one core is not machine-independent either; the likely cause is different processor models on GitHub machines. The 2-core 0.01 ms result may have drawn one processor model. Run rp10 (10 machines, 2 cores, processor model logged per car, 43169235738) tests this.
- **Not the processor.** 2 cores, 10 machines, five processor models (AMD EPYC 7763, 9V45, 9V74; Intel Xeon 8370C, 8573C), one shared reference: T 1.55771–1.55772 s, **spread 0.01 ms** (mxnviir/stem-car-compute 43171163246).
- **The reference case has two flow states ~1.3 ms apart.** Every repeat set agrees within itself, but whole sets land on ~1.5577 s (rp5, rp8, rp12) or ~1.5564 s (rp7, rp9, rp13 same-maths), and one rp7 car flipped. So repeating the whole pipeline, reference included, can differ by 1.3 ms. Proposed fix (QUESTIONS.md Q3): one frozen, stored reference case for all timings.
- **Repeat PASS on the frozen reference** (release p2-ref-3945, decision Q3 = A): same car, 9 machines on two accounts (mxnviir/stem-car-compute 43195799268, blackwingftc-lang/stem-car-compute 43195812140), 2 cores: T 1.55771–1.55772 s, **spread 0.01 ms (mark 0.1 ms)**, equal to the run the reference came from. Uncertainty kept on record: the other flow state of the reference is 1.3 ms away; which state is frozen is being chosen by a time-accurate run, and 10 cars are being timed from both states.
- **Start state matters for real cars too.** The same 10 cars started from state A (blackwingftc-lang/stem-car-compute 43208023025) and from state B (instagramshashank8-bot/stem-car-compute 43196008248): T(B) − T(A) per car +0.06, +0.16, −0.15, −0.39, +0.72, −1.11, −0.02, −0.74, −0.07, −0.04 ms (rms 0.50 ms, largest 1.11 ms). **Not a common shift:** mean −0.16 ms, de-meaned SD 0.50 ms, Spearman A vs B 0.77. Choosing the state moves cars relative to each other by more than the 0.3 ms mark, so the noise gate stays OPEN (QUESTIONS.md Q4). Meanwhile every car on record starts from the one frozen state (the stopwatch does this), and car-to-car differences are only valid within that state. The rms 0.50 ms is kept as the start-state uncertainty of a single comparison against cars timed from another state.
- **Method A (Q4 answer): each car timed from both states, time = mean, error bar from A − B.** Smooth 16-car ladder from A (msf1, mxnviir/stem-car-compute 43195805676) and from B (msf2, mxnviir/stem-car-compute 43246744093; alone 0.103 ms): residual SD of the per-car mean **0.091 ms (95 % 0.067–0.144, 14 dof) — PASS vs 0.3 ms**. On this smooth ladder A − B is almost a constant 1.41 ms (SD 0.13 ms); on the 15 skin-ladder cars it is not (above), which is what the per-car error bar carries. Confirmation pair msf3 (A) / msf4 (B) and test C (time-accurate on 3 cars) running.
- **Method A confirmed on fresh machines: 0.087 ms (95 % 0.064–0.137)**, msf3 (A, instagramshashank8-bot/stem-car-compute 43268052102) + msf4 (B, Jdiejei/stem-car-compute 43270621501).
- Cores on the frozen case, 3 repeats each (shawshanker18/stem-racing-car): 2 cores 1.55771, 1.55771, 1.55772 s (spread 0.01 ms, 59–63 min per car job, run 43279297287); 4 cores 1.55763, 1.55766, 1.55775 s (spread 0.12 ms, 31–40 min, run 43279305307). 4 cores is faster but not repeatable, so every timing job stays on 2 cores.
- Two more checks failed to run: the time-accurate state choice timed out (0.15 s too long for the job; superseded by method A), and car L1 does not build on current main ("Mesh is not watertight after repair", Part 1 geometry) so the mesh study has 19 cars.
- Skin ladders ref 3.930 (mxnviir 43066023520): 1.31 ms; ref 3.912 (mxnviir 43066015091): 0.67 ms.

## Mesh convergence (ranking must not change with the mesh): PASS

The 20 stress cars on the search mesh (medium, 2 cores; shawshanker18/stem-racing-car 43236112898, L1 rerun 43309030793 after Part 1 9984b8a) and the fine mesh (4 cores; blackwingftc-lang/stem-car-compute 43236121620, L1 43309051449). Fine missing: L9 (6 h job limit), C3 (failed).

| set | cars | Spearman | pairs > 3 ms apart that agree |
| --- | --- | --- | --- |
| all with both meshes | 18 | 0.963 | 138 / 144 = 95.8 % |
| converged on both | 11 | 0.973 | 50 / 51 = 98.0 % |

Stats: shawshanker18/stem-racing-car 43358478921, 43358483537. Pass marks 0.9 and 90 %.

## Race model against the measured facts (shawshanker18/stem-racing-car 43359829638; 68 race-model tests pass)

| fact (CONTEXT.md) | measured | model | 
| --- | --- | --- |
| thrust peak | 8.99 N at 59 ms | 8.986 N at 0.059 s |
| total impulse | 2.15 N·s | data 2.1542, fit 2.1533 N·s (fit 0–2 s 2.1534) |
| thrust fit error | | rms 0.083 N; largest 1.98 N at t = 0 (the first sample), 0.26 N after 10 ms |
| mass | 48.2 g target, 21.15 g cartridge shell | used as given |

Sensitivities on the measured thrust (times x 0.802, relative only), best search car of 2026-11-08 (D20 0.380 N; lift and COM assumed): **0.199 ms per mN of drag, 7.51 ms per g of mass**. The old 0.48 ms/mN and 16.6 ms/g were on the invented thrust curve and are replaced. Model time 0.946 s raw, 0.759 s calibrated; real top cars run 1.0–1.1 s, and model times are for comparison only.

**Still team placeholders, not measured:** rolling friction (mu 0.010), wheel spin-down / inertia (1.39e-7 kg m²), tether and guide friction (mu_guide), bearing load law, tether drag (not modelled), real part weights, and the timed track run that would set the time coefficient. These cannot be checked until the team measures them (CONTEXT.md section 12).

## Chained long runs (BUILD_SPEC Step 5; a solve longer than one 6 h job)

The solver stops at a time budget, writes its fields (binary), and the next job continues from the latest time (`openfoam_case` CHECKPOINTS); the force history is joined across the break. Same car from the frozen reference case, 1000 steps, 2 cores, link 1 stopped at a 600 s budget (step 163):

| comparison | D20 N | race time s | difference |
| --- | --- | --- | --- |
| unbroken vs chained, links on two machines (shawshanker18/stem-racing-car 43373052358) | 0.41695454 vs 0.41695062 | 1.5577195 vs 1.5577175 | 0.004 mN, 0.002 ms |
| unbroken vs chained, all on one machine (43388406547) | 0.41695037 vs 0.41694927 | 1.5577175 vs 1.5577170 | 0.001 mN, 0.0005 ms |

Not bit-identical: on one machine the restart moves the time by 0.0005 ms, 200 times below the 0.1 ms repeat mark and 20 times below the 0.01 ms machine-to-machine spread. **Pass mark (within 0.1 %): PASS** (0.0003 % on drag). The whole-car test now runs its fine and resolved cars this way (tests.yml long_fine_1..3, long_resolved_1..3).

## Drag bias against the wind tunnel (reviewer Q11 = A)

| benchmark | our Cd | published | gap |
| --- | --- | --- | --- |
| Ahmed 25°, fine mesh, still floor | 0.312 | 0.285 (Lienhart) | +9.5 % |
| Ahmed 25°, upstream ground plate | 0.321 | 0.285 | +12.6 % |
| Ahmed 25°, rolling floor, medium | 0.294 | 0.285 | +3.2 % |
| Ahmed 25°, wall-resolved mesh | 0.323 | 0.285 | +13.3 % |
| Ahmed 35°, wall-resolved mesh | 0.274 | 0.26 | +5.4 % |
| cube (Cd 1.05, Hoerner) | not finished | | |

The finer, wall-resolved mesh does not reduce the gap, so it is taken as the known k-omega SST over-prediction of the slant separation (a RANS limit), not a mesh error. The benchmark runs were on teammate accounts that are now suspended, so their run pages can no longer be opened. **Decision (Q11 = A): the race model uses D_true = D_cfd / 1.09, error bar ± 0.04** (`physics_contract.DRAG_BIAS`, `DRAG_BIAS_RANGE`; `race_objective.SmoothSheetModel.drag_bias`; test `test_drag_bias_divides_the_cfd_drag`; commit 4563d0b). Because the Ahmed bias may not carry over to the car, the top cars are to be re-ranked at 1.05 and 1.13 with the race model only; if the best body changes, that is reported.

## Fixed constants: wheels, friction, tether (user decision 2026-11-13: the same for every car)

No published measured value exists for F1 in Schools rolling friction, wheel inertia or tether drag (searched 2026-11-13). The best public source is a team engineering report (Hydron, Australia: https://offthetrack.net/img/t41_hydron_australia_engineering_compressed.pdf), which models wheel, aero and tether friction separately but publishes no coefficients. So these are stated engineering values, the same for every car:

| constant | value | basis |
| --- | --- | --- |
| rolling friction mu | 0.010 | between ball-bearing wheels on a smooth track (Engineering ToolBox rolling-resistance tables, low-resistance wheels 0.002–0.005 plus bearing and guide drag) |
| low / high for Part 3 | 0.005 / 0.020 | half and double the central value |
| wheel mass | 1.15 g front, 1.29 g rear (Part 4 parts) | consistent with a hollow 2 mm-wall PLA wheel of about 1.8 g (PCBWay worked example) |
| wheel inertia | 1.39e-7 kg m² per wheel | from those parts |
| tether drag | 0 (not modelled) | no published value; accepted by the reviewer (2026-11-14) because it is the same constant for every car (user decision), so it shifts all times equally and cannot change the order; mu_guide stays a placeholder |

Every car gets the same values, so they shift all times together and the ranking holds; the friction check at 0.005 and 0.020 tests that. The team's spin-down and slope tests replace them when they arrive.

## Disk-saving change on fine and resolved meshes (66de290)

One medium car solved twice in one job on ONE core, before and with the change forced on (P2_SLIM=1; shawshanker18/stem-racing-compute 43503249158): T 1.5390140296698798 s and D20 0.41139534964 N both times, **bit-identical**. On 2 cores the same pair differed by 0.008 ms (43475203170), the known 2-core run-to-run floor.

## Fine mesh: the one highly skewed face

Car C0 on the fine mesh (shawshanker18/stem-racing-compute 43441210212): max skewness 4.81, one face over the limit, face 13235499. The `car` patch (the machined body) holds faces 13234965–13287897, so the face is on the body surface, about the 534th body face; not on a wing, nose, support or wheel. One face out of 13.3 million, on a wall where the wall function sets the flow, so it is not expected to move the drag. Its exact position needs the face set written as points; that step did not find the file and is to be fixed if the face starts to matter.

## Fine mesh: fallbacks if the noise is over 0.3 ms (ranked; marks unchanged)

The fine set runs as p2_fine kind=car from one frozen fine reference, 1000 steps, 2 cores, one car per job, chained. If it fails:

| rank | fallback | evidence (medium mesh) | cost | ready to dispatch |
| --- | --- | --- | --- | --- |
| 1 | time every car from BOTH frozen states and average (method A) | one state: 0.57–0.86 ms on skin ladders; both states: 0.091 / 0.087 ms on the smooth ladder | 2 solves per car; needs a second fine reference in the other state (fr4 and fr5 are built on two machines for this) | p2_fine kind=car ref_tag=p2-ref-fine-B (same inputs) |
| 2 | longer averaging: 3000 steps | averaging part fell from 0.62 to 0.34 ms (1/sqrt 3) at 3000 steps; window length (last 20–80 %) made no difference | 3 x solve time (3–4 links per car) | p2_fine iters=3000 |
| 3 | finer wake region behind the base | the car-to-car spread came from the body and rear-wheel wake switching | more cells; the medium-plus recipe was stopped by the user, so needs a new decision | needs approval |
| 4 | time-accurate tail after the steady solve | 0.12 s pimpleFoam kept each car on its own state; 0.15 s did not fit one job | many hours per car | p2_transient (chained version not built) |

Ranks 1 and 2 need no new code: they are inputs of the same workflow, already exercised (p2_fine kind=car is the path the noise set itself uses).

## Still to prove

- Ahmed body benchmarks: 35° reported (RANS limit); 25° and the cube are the pass cases (decision 2026-11-09).
- Noise ≤ 0.3 ms: being fixed (reshaped meshes plus warm starts).
- Repeatability, warm start, chained long runs, race model on measured inputs, model vs track.
