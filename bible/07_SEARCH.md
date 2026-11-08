# Part 7 — The search: finding the fastest legal car the model can describe

Read `00_START_HERE.md` first. Do not start this Part until the gates of Parts 4, 5 and 6 are passed: the search optimises the race model (Part 4) over legal cars (Part 5) measured by the stopwatch (Part 6). A search on a wrong objective finds the wrong car faster.

The search has four stages:

| Stage | What | Stopwatch tier | Why |
|---|---|---|---|
| A. Screening | Every setting moved a small step both ways around the start car | local (morph) | Find which of about 120 settings matter, cheaply and precisely |
| B. Global | Gaussian-process Bayesian optimisation over the 15-25 settings that matter | screen (fresh mesh) | Explore the whole legal space, with noise handled by the model instead of by repeat runs |
| C. Polish | Trust-region steps around the best car, on all important settings | local (morph) | Climb the last few tenths of a millisecond that the screen tier's noise hides |
| D. Robustness | The best car perturbed by manufacturing tolerances | local (morph) | Make sure the car is not on a knife edge that the real build will fall off |

**Compute budget for this Part:** the largest. Roughly A: 250-350 jobs, B: 300-500 CFD jobs plus 600-1,000 build-only jobs (legality filter), C: 100-200 jobs, D: 20-40 jobs. Total about 700-1,100 CFD jobs.

---

## 7.0 Start of Part: the compute question, the budget and the deadline

Ask the compute question (00 section 0.7), stage by stage: the user may confirm different accounts for different stages. Before Stage A:

```
QUESTION (Part 7, compute 1): How many team members are confirming that their GitHub
accounts can be used for Part 7, Stage A (screening)?
Why I need it: Stage A runs about 250-350 short CFD jobs (10-20 minutes each).
Expected load: about 300 jobs; with 80 parallel slots about half a day including queueing.
```

then compute 2. Ask again (both questions) at the start of Stages B, C and D, with each stage's expected load from the table above.

Also ask, once, before Stage A:

```
QUESTION (Part 7, budget): What is the competition date, and by when must the final car
design be frozen so it can be milled, printed, assembled and tested? And is there a cap on
how many CFD cars I should run in total?
Why I need it: Stage B's stopping rule includes a budget; Part 8 needs about 2-3 weeks
for confirmation runs, manufacture and testing.
Default if you say "you decide": freeze the design 4 weeks before the competition; no
cap other than that date.
```

Record both in `STATUS.md`. Plan the stage schedule backwards from the freeze date and tell the user the plan.

---

## 7.1 The objective and the constraints

**Objective:** `T_at_target_s` from the Part 4 race model with the measured inputs: the race time of the car at exactly the target competition mass, using CFD D20, L20, My20 and the drag exponent k, the car's centre of mass and its axle positions. In real ms. Lower is better.

Why "at target": every car is re-sized to the target mass, but the sizing loop stops within a tolerance, so two cars weigh slightly different amounts. Evaluating both at exactly the target removes that difference, which is not a design difference. (The existing `run_car.cfd_and_objective` does this; keep it.)

**Hard constraints** (a car that breaks one is never measured in CFD):

1. Every Part 5 rule check passes on the manufactured files, with the 0.3 mm manufacturing margin on clearance-type checks.
2. Mass gate at 3σ (Part 5 section 5.5), under the mass policy the team chose.
3. Machinability with the real tool (Part 5 section 5.4).
4. Physical-test strength margins ≥ 0 (Part 5 section 5.6).

**Soft information carried in the objective, not as a constraint:** launch pitch (through the guide-friction term in Part 4). Also report `launch_margin_N` for every car; if the team decides (TEAM DECISION) that no wheel may lift at all, make `launch_margin_N ≥ 0` a hard constraint instead.

---

## 7.2 The search space

### 7.2.1 Registry: `search/space.json`

Generated once from `part5-simulation/space.py` (Part 2 moved the parameter definitions there) plus the new parameters below, then edited by hand. One entry per setting:

```json
{"name": "fw.aoa_deg", "group": "front_wing", "type": "float", "lo": -2.0, "hi": 14.0,
 "step": 2.0, "start": 6.0, "morphable_step": 1.0, "notes": "trailing edge up"}
```

`type` is `float`, `int` or `bool`. `morphable_step` is the largest change that stays inside the morph range (Part 6 M-4); for `bool` and topology-changing settings it is `null` (fresh mesh only).

### 7.2.2 The settings

| Group | Settings | Count | Source |
|---|---|---|---|
| Layout | `W` 120.3-140, `x_front` 46-56, `d_halo` 25-75 | 3 | `space.LAYOUT` |
| Body loft | 8 stations × (`st_b`, `st_zt`, `st_zb`), `p`, `s_b`, `s_zt`, `s_zb`, `s_x0`, `s_x1`, `s_taper`, `s_p`, `blend_mm` | 33 | `space.LOFT`, bounds in `space.bounds` |
| Body sculpt modes | `mode0` … `mode55`, each −6 to +6 mm, σ 7 mm Gaussians | 56 | `param_body` |
| Floor tunnel | `ft_h`, `ft_w`, `ft_x0`, `ft_x1`, `ft_ramp` | 5 | `space.FLOOR` |
| Front wing | `aoa_deg`, `z_chord_mm`, `gap_to_wheel_mm`, `half_span_mm`, `flap_chord_mm`, `flap_aoa_deg`, `camber` | 7 | `space.PARTS` |
| Supports | `beam_w_mm`, `beam_h_mm`, `strip` (bool), `strip_w_mm`, `disc_recess_mm`, `pod_wall_mm` | 6 | `space.PARTS` |
| Nose | `length_mm`, `k`, `p`, `tip_z_mm` | 4 | `space.PARTS` |
| Rear wing (new) | `aoa_deg`, `camber`, `chord_mm`, `z_chord_mm` (absolute, Part 5 F24), `x_le_after_ref_b_mm`, `pylon_chord_mm`, `half_span_mm` | 7 | `wings.RearWing`; bounds from the rules (chord 15-25, span ≥ 50 → half-span ≥ 25, overhang ≤ 40 from Ref B, height ≤ 65) and the impact sweeps (aoa −4 to +8, pylon 6-20) |
| Mass placement (new, if the team chose ballast policy C) | `ballast_g` 0 to capacity − 1 g | 1 | Part 5 section 5.5.4 |
| Thrust line (new) | `chamber_axis_z_mm` 30.5-34.0 (block floor = axis − 29 must stay ≥ 1.5 mm, T3.7; T5.2 allows 30-40) | 1 | `geometry_contract.CHAMBER_AXIS_Z_MM` becomes a parameter |
| **Total** | | **≈ 123** | |

The thrust-line height and the mass placement are included because Part 4 shows the centre of mass relative to the thrust line is a first-order lever through the launch.

---

## 7.3 Stage A — Screening by morphing

### 7.3.1 What and why

Move each setting by a small step down and up around the start car, measure the race-time change precisely (morph tier, σ_paired ≈ 0.03 real ms), and rank settings by how much they can matter over their range. With 123 settings and a GP that can handle about 20-25 well, this decides what Stage B searches.

### 7.3.2 Procedure

1. **Family:** a `family` job on the start car (sized to the target mass; Part 6 section 6.10). Upload it; record its URL.
2. **Cases:** for each float or int setting i: two candidates, value ± h_i where h_i = min(`step` / 2, `morphable_step`). Each candidate is **re-sized** to the target mass (normal sizing loop: the skin changes slightly to pay for the volume the setting adds or removes; that skin change is part of the setting's true effect at constant mass, and it is small enough to stay within the morph range). Plus 3 identity controls.
3. **Bool and topology settings** (`sup.strip`, `ft_h` crossing 0, flap on/off): fresh-mesh screen tier, 4 jittered replicates each side (skin ±0.01 mm). These are noisier; mark them.
4. **Batch:** about 2 × 115 + 3 = 233 morph cases + about 16 fresh cases.
5. **Results per setting:** T_−, T_0 (from the family base and the controls), T_+.
   - slope g_i = (T_+ − T_−) / (2 h_i)
   - curvature c_i = (T_+ − 2 T_0 + T_−) / h_i²
   - potential E_i = |g_i| × (hi_i − lo_i) / 4 (what moving a quarter of the range could be worth, to first order)
   - a flag where the build at ± h_i was illegal (the setting is at a constraint on that side).
6. **Ranking:** sort by E_i. Also group sums (all 56 modes together, all loft settings together) to see which groups matter.

### 7.3.3 Selecting Stage B's settings (rule fixed before Stage A's results)

- Always include: the 3 layout settings, `chamber_axis_z_mm`, `ballast_g` (if policy C).
- Add settings in order of E_i until the cumulative E of the excluded settings is under 10% of the total E, or until d = 25, whichever comes first.
- Settings left out stay at their start value in Stage B. Stage C reconsiders all settings around the incumbent.

### 7.3.4 Re-screening

Repeat Stage A around one other, very different good car (the best car of the old solver re-evaluated with the new stopwatch, or the first Stage B incumbent). If the top-15 lists of the two screenings share fewer than 10 settings, the ranking depends on where you stand: widen Stage B's set to the union (up to 30).

---

## 7.4 Stage B — Global search with a Gaussian process

### 7.4.1 Method, plainly

A Gaussian process (GP) is a statistical model that, given the cars measured so far, predicts the race time of any untried car **and how uncertain that prediction is**. It treats measurement noise as part of the model instead of requiring repeats. Each round, it proposes the batch of cars whose measurement is expected to improve on the best predicted time the most (expected improvement), spreading the batch so the cars are not all in one place. After the round is measured, the GP is refitted and the next batch proposed.

This uses every evaluated car (a pattern search throws most away), handles noise properly (no best-of-N bias), runs in batches that fill the farm, and gives a posterior that says how confident the result is.

### 7.4.2 Data preparation (`search/ingest.py`)

- Read `results/db.jsonl`; keep rows from Stage B batches (and Stage A family bases and seeds) that are `ok`, legal, converged.
- X: the d selected settings, scaled to [0, 1] with the registry bounds. Bool → 0/1.
- y: `T_at_target_s` in real ms, minus the median (the GP fits differences).
- Noise sd: the screen-tier σ from Part 6 (6.4) converted to real ms. Rows that are averages of k replicates get noise σ/√k: pass per-row noise via the GP's `alpha` (variance per row, in standardised units) instead of a single white-noise level; the code below does this.

### 7.4.3 `search/gp.py`

```python
"""search/gp.py -- Gaussian-process model and batch expected improvement (minimisation).

Inputs are scaled to [0,1]^d. Outputs are standardised inside. Per-row noise variance is passed
as alpha (real ms^2), so averaged replicates count as less noisy.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import norm, qmc
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern


class GP:
    def __init__(self, X: np.ndarray, y: np.ndarray, noise_var: np.ndarray, kernel=None):
        self.mu_y, self.sd_y = float(y.mean()), float(y.std()) or 1.0
        ys = (y - self.mu_y) / self.sd_y
        alpha = noise_var / self.sd_y ** 2
        d = X.shape[1]
        if kernel is None:
            kernel = ConstantKernel(1.0, (1e-2, 1e2)) * Matern(
                length_scale=np.full(d, 0.3), length_scale_bounds=(0.02, 20.0), nu=2.5)
            self.m = GaussianProcessRegressor(kernel, alpha=alpha, n_restarts_optimizer=8, random_state=0)
        else:
            self.m = GaussianProcessRegressor(kernel, alpha=alpha, optimizer=None)
        self.m.fit(X, ys)
        self.X, self.y, self.noise_var = X, y, noise_var

    def predict(self, Xq: np.ndarray):
        """Latent mean and sd in real ms (noise not included: alpha only enters at training points)."""
        m, s = self.m.predict(Xq, return_std=True)
        return m * self.sd_y + self.mu_y, s * self.sd_y

    def incumbent(self):
        """The evaluated car with the lowest predicted mean (not the lowest noisy observation)."""
        m, s = self.predict(self.X)
        i = int(np.argmin(m))
        return i, float(m[i]), float(s[i])

    def ei(self, Xq: np.ndarray, best: float) -> np.ndarray:
        m, s = self.predict(Xq)
        s = np.maximum(s, 1e-9)
        z = (best - m) / s
        return (best - m) * norm.cdf(z) + s * norm.pdf(z)

    def fantasy(self, x: np.ndarray, y_fake: float, noise_var: float) -> "GP":
        """Same hyperparameters, one more (pretend) observation: for building a batch."""
        return GP(np.vstack([self.X, x]), np.append(self.y, y_fake),
                  np.append(self.noise_var, noise_var), kernel=self.m.kernel_)


def candidate_pool(d: int, X: np.ndarray, y: np.ndarray, n_sobol: int = 16384, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    sob = qmc.Sobol(d, scramble=True, seed=seed).random(n_sobol)
    top = X[np.argsort(y)[:10]]
    local = np.clip(np.repeat(top, 400, axis=0) + rng.normal(0, 0.05, (len(top) * 400, d)), 0, 1)
    return np.vstack([sob, local])


def propose_batch(gp: GP, q: int, noise_var: float, seed: int = 0, min_dist: float = 0.02) -> np.ndarray:
    """Kriging-believer batch: pick the max-EI point, pretend its outcome is the predicted mean,
    refit with fixed hyperparameters, repeat."""
    _, best, _ = gp.incumbent()
    pool = candidate_pool(gp.X.shape[1], gp.X, gp.y, seed=seed)
    chosen, g = [], gp
    for _ in range(q):
        e = g.ei(pool, best)
        if chosen:
            dmin = np.min(np.linalg.norm(pool[:, None, :] - np.array(chosen)[None], axis=2), axis=1)
            e[dmin < min_dist] = -1
        k = int(np.argmax(e))
        x = pool[k]
        chosen.append(x)
        g = g.fantasy(x[None], float(g.predict(x[None])[0][0]), noise_var)
    return np.array(chosen)
```

Test (`search/tests/test_gp.py`): f(x) = 10·|x − (0.3, 0.7, 0.55)|² on [0, 1]³ plus Gaussian noise of sd 0.3, a 16-point Sobol start, 6 rounds of 8 points each. Over seeds 0-4: every run must evaluate a point with noise-free value below 0.5, and the noise-free value of `incumbent()` must be within 0.1 (a third of the noise sd) of the best noise-free value evaluated. Verified when this bible was written: the best values were 0.001-0.011, the incumbents 0.001-0.043, about 3.5 s per run with scikit-learn 1.9. This guards against sign errors (minimisation) and scaling errors.

### 7.4.4 The legality filter (cheap builds before CFD)

A proposed car may be illegal. Building and rule-checking a car without CFD takes about 2-6 minutes (body sizing about 1 minute plus parts, joints, legality). So:

1. Propose 3q candidates (`propose_batch` with 3q).
2. Write a batch of kind `legal_only` (new worker kind: `run_car.py` without `--cfd`; returns legality, mass, launch margin geometry, CoM) and run it.
3. Keep the legal ones in the order they were proposed; take the first q.
4. Record every illegal candidate in `results/db.jsonl` too (with its failed checks). If more than half are illegal round after round, fit a simple classifier (a second GP on 0/1 legality, or nearest-neighbour on X) and multiply EI by the probability of legality.

### 7.4.5 Initial design

- The 8 chain-best cars from the old solver (`archive/search-2026-11/solver_state.json`), the start car and chain 2's best, re-built under Part 5's rules (some may now be illegal: that is information) and measured on the screen tier.
- Plus a scrambled Sobol design of 4d points (for d = 20: 80) in the d selected settings, others at start values, filtered by legality (top up from further Sobol points until 4d legal).

### 7.4.6 A round

1. `python search/round.py plan --stage B --round N`: fit the GP to all Stage B data, write the GP's predictions for the proposed batch **before** running it into `search/rounds/B<N>/predicted.json`, write the `legal_only` batch, commit, push.
2. Ask the compute question (if this is the first round of a stage, or the user said accounts may change), dispatch, collect.
3. `python search/round.py filter --stage B --round N`: take the first q legal; write the CFD batch (kind `fresh`); commit, push, dispatch, collect.
4. `python search/round.py ingest --stage B --round N`: append results, compute the **held-out score** (R² and mean absolute error of `predicted.json` against the measured times of this round), refit, write `search/rounds/B<N>/report.md` (incumbent, its predicted time and sd, the round's best measured, R², parameter length-scales — short length-scale = important setting).

Round size q: the number of parallel slots confirmed for this stage, capped at 60 (bigger batches dilute the benefit of refitting).

### 7.4.7 Stopping rule (write into `STATUS.md` before round 1)

Stop Stage B when any of these holds:

1. The maximum expected improvement over the whole pool is below 0.2 real ms in two consecutive rounds.
2. The incumbent's predicted mean improved by less than 0.3 real ms over the last two rounds **and** the held-out R² of those rounds is above 0.6.
3. The budget or the schedule (7.0) is exhausted.

**Validity gate:** if the held-out R² is below 0.6 after round 3, stop and investigate before spending more. Typical causes: the noise estimate is wrong (look at replicate spread), a setting has a discontinuity (a builder auto-adjusting something: Part 5 removed the known ones), illegal-but-measured cars leaked in, or the d settings are not the ones that matter (revisit 7.3.3).

### 7.4.8 Confirming the incumbent

At the end of Stage B: the incumbent and the next two distinct candidates (posterior means within 1 ms of the incumbent, and at least 0.2 apart in scaled distance) are each measured on 4 fresh screen-tier meshes with skins jittered by ±0.01 mm. Report each one's mean and standard error. The best of these by measured mean (not by GP) goes to Stage C. If two are within one standard error, both go to Stage C.

---

## 7.5 Stage C — Polish by morph trust region

### 7.5.1 Why

Stage B's resolution is limited by the screen tier's noise (about 0.5 real ms per car; the GP averages some of it away). Near the optimum, gains of 0.1-0.5 ms per step remain that only the morph tier can see.

### 7.5.2 Procedure (repeat until the stop condition)

1. **Family** at the current car.
2. **Gradient:** central differences, morph tier, on the top-40 settings from a re-screen at this car (7.3.2 steps 2 and 5, but only for 40 settings: 80 cases + 3 controls). Settings not in the top 40 keep their values.
3. **Direction:** in scaled coordinates (each setting divided by its `step`), p_dir = −g / |g|.
4. **Step sizes:** choose Δ so the largest surface displacement is about 1 mm (estimate from the screening: each setting's displacement per unit change is reported by `morph.json`'s `max_disp_mm`). Candidates at 0.5Δ, Δ and 2Δ (2Δ only if within the morph range), each re-sized, legal-filtered, morphed, measured; plus an identity control.
5. **Accept** the best candidate if its ΔT < −max(3 σ_paired, 0.1 ms) and it is legal. Move the car there. If the cumulative displacement from the family anchor exceeds half the morph range, make a new family at the new car.
6. **If no candidate is accepted,** halve Δ. Stop when Δ falls below the displacement equivalent of 0.25 mm, twice in a row.

Each iteration is about 90-100 morph jobs. Expect 3-8 iterations.

### 7.5.3 Optional: one adjoint map

`part2-simulation/openfoam_adjoint.py` can produce a surface drag sensitivity map. It failed as a gradient (Part 2 `docs/HISTORY.md`). It may still be useful as a **map** of where on the body drag is sensitive, to place new sculpt modes where the existing 56 do not reach. Only if the user wants it:

1. Run one adjoint at the Stage C car (medium, the chosen configuration).
2. Compare its projection onto the 56 modes with the morph-measured mode slopes from step 2 (that is a free, precise gradient check). Report the correlation.
3. If the map shows large sensitivity in regions no mode covers, add modes there (Gaussians centred on the high-sensitivity patches), screen them by morph, and include them in Stage C.

Never use the adjoint to move the car directly.

---

## 7.6 Stage D — Robustness to manufacturing tolerances

On the final Stage C car, morph tier, measure ΔT for each perturbation:

| Perturbation | Size | Source of the size |
|---|---|---|
| Whole-body skin | −0.2 and −0.4 mm | sanding loss (Part 3 M10) |
| Front wing angle | ±0.5° | assembly error |
| Front wing height | ±0.2 mm | SLS tolerance |
| Rear wing angle | ±0.5° | assembly error |
| Wheel position (each axle) | ±0.2 mm in x | support tolerance |
| Support beam thickness | ±0.1 mm | SLS tolerance |

Report each ΔT. If any single perturbation costs more than 1 ms, or the sum of the absolute costs exceeds 2 ms, the optimum is fragile: tell the user, and evaluate the two runners-up from 7.4.8 under the same perturbations; recommend the car with the best **expected** time under the perturbation distribution (each perturbation drawn uniformly within its range; 200 Monte Carlo samples using the measured linear sensitivities).

Also report for the final car: launch margin, mass at 3σ, every rule margin, every physical-test margin.

---

## 7.7 Reporting (`docs/SEARCH_REPORT.md`)

- Stage A ranking table (top 30 settings with slope, curvature, potential) and group totals.
- Stage B: per round, the incumbent's predicted time ± sd, the round's best measured, held-out R²; the GP's length-scales (importance); partial-dependence plots for the 6 most important settings (the GP's mean as each setting varies, others at the incumbent).
- Stage C: each step's ΔT with its uncertainty; total polish gain.
- Stage D: the robustness table.
- The final car's parameters, files, and predicted race time with the full uncertainty (Part 4 section 4.9), clearly separating: noise of the stopwatch, uncertainty of the inputs, and the systematic mesh/model uncertainty from Part 6's mesh study.
- A comparison: the old solver's best car (1.5412 s model time) re-evaluated under the new rules, stopwatch and race model, against the new best. Both in real ms.
- What the search **cannot** claim: a global optimum, or the fastest real car. It claims the fastest car found by a documented, noise-aware search of this parameterisation of the legal space, under this model.

---

## 7.8 Exit gate for Part 7

- [ ] Stage A ranking done (and re-screen); Stage B settings chosen by the pre-registered rule.
- [ ] Stage B stopped by its stopping rule; held-out R² ≥ 0.6 in the final rounds.
- [ ] Stage C stopped by its stop condition.
- [ ] Stage D robustness table; the recommended car chosen by the stated rule.
- [ ] `docs/SEARCH_REPORT.md` written.
- [ ] The user has seen the report and agreed which car (or cars, up to 3) go to Part 8.

Now open `08_CONFIRM_BUILD_RACE.md`.
