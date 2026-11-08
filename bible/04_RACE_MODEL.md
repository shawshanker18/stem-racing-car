# Part 4 — The race model: from car properties to a 20 m time

> **Status on 2026-11-08 (branch `rebuild/bible`). Owner: chat A (validation).** `race/race_model.py` done (sections 4.2-4.5, 4.8, 4.9), wired into `car/pipeline.py` and `car/run_car.py`; the JAX model is retired. Not yet done: CFD at several speeds (4.6) and validation against real runs (4.7), which need lab data and the reference car.
> See `status/` for live progress and `agents/` for the chat prompts.

Read `00_START_HERE.md` first. This Part rebuilds the 1-D race model so that it runs on measured inputs, contains only physics, includes the resistances that were missing (constant and bearing resistance, tether guides, launch pitch), and is validated against real timed runs.

**Compute budget for this Part:** a few CFD cars (the reference car from Part 3 M9 at two or three speeds, plus its pitching moment). About 6-10 jobs, under 3 hours. Everything else runs locally in seconds.

---

## 4.0 Start of Part: the compute question

```
QUESTION (Part 4, compute 1): How many team members are confirming that their GitHub
accounts can be used for Part 4?
Why I need it: I run CFD on the reference car at 2-3 speeds to validate the race model.
Expected load for Part 4: about 6-10 jobs, under 3 hours. One account is enough.
```

Then compute 2 (which accounts). Record in `STATUS.md`.

---

## 4.1 What exists today and what is wrong with it

File: `race_objective.py (retired in Part 4)` (649 lines, JAX), wrapped by `race_objective_adapter.py`, called through `pipeline.evaluate_objective` (after Part 2).

What it does: integrates the car's motion in the distance domain (state: time t and q = v²) with RK4 over 1,000 steps on a grid clustered near the start, from x = 1e-4 m to 20 m.

```
a = [F_thrust(t) − D20·q/400 − μ·(m(t)·g − L20·q/400)] / [m(t) + N·I/r²]
dt/dx = 1/√q,  dq/dx = 2a
```

Defects:

| Id | Defect | Effect |
|---|---|---|
| F01 | Thrust curve synthetic (Part 3 replaces it) | absolute times about 0.5 s too slow; every exchange rate about 1.8× too large |
| F02 | Thrust and propellant mass fitted with 80 Gaussian basis functions, width ≈ 47 ms | a real curve's 10-20 ms rise would be smeared; the fit also rings below zero (the code clamps the propellant term because of it) |
| F03 | COM-height penalty: a degree-4 polynomial through 9 invented points, up to 28 ms | not physics; also asymmetric in the wrong direction (see 4.5) |
| F04 | COM-x penalty: quadratic distance from x = 0, the nose tip on the ground | meaningless target |
| F05 | μ = 0.010 unmeasured | rolling resistance unknown |
| F06 | No constant resistance, no bearing drag, no tether | missing physics |
| F07 | Drag only as D20·(v/20)²; one speed; ρ = 1.225 | Reynolds-number dependence and venue air density ignored |
| F08 | No axle-load / launch-pitch calculation | the most likely real-world loss is invisible |
| — | JAX `value_and_grad` re-traces every call (about 1 s per call) and leaks memory mappings (documented in the file; mitigated by raising `vm.max_map_count`) | slow and fragile, for a gradient nothing needs any more |
| — | One wheel inertia and one radius for all four wheels | front and rear wheels differ (13.25 vs 17.25 mm wide) |

Decision: **replace the JAX model with a NumPy model** in a new file `race/race_model.py`. Gradients are no longer used by any search (the adjoint loop is gone). Where an exchange rate is wanted (ms per mN of drag, ms per gram), it is computed by central finite differences, which on this smooth model are accurate to better than 0.1%. This deletes the JAX dependency, its memory leak, the RBF fit and the hash-locking ritual.

Keep `race_objective.py` only until `pipeline.py` and the tests point at `race_model.py`, then delete it, `race_objective_adapter.py`, `race_objective_hash.txt`, `adjoint_contract.py` (if Part 7 does not need it) and their tests. Remove `jax` and `jaxlib` from `docker/requirements.lock` and rebuild the image (Part 1 section 1.6).

---

## 4.2 The physics, written out

Coordinates for the dynamics: s is distance travelled along the track (0 to 20 m), v = ds/dt.

### 4.2.1 Forces along the track

```
m_eff(t) · dv/dt = T(t) − D(v) − F_roll(t, v) − F_bear(v) − F_guide(t, v)
```

| Term | Formula | Inputs (from `inputs/measured.json` unless stated) |
|---|---|---|
| Mass | m(t) = m_car + m_shell + m_prop(t) | m_car: manufactured mass without cartridge (Part 5 mass rollup); m_shell: `cartridge_shell_g`; m_prop(t): the third column of `thrust_csv` |
| Effective mass | m_eff = m(t) + 2·I_f/r_f² + 2·I_r/r_r² | `wheel_I_front_kgm2`, `wheel_I_rear_kgm2`; r_f, r_r measured wheel radii (Part 5 unifies the radius constants) |
| Thrust | T(t) = linear interpolation of the measured curve, 0 after its end; shifted by `trigger_delay_ms` only if timing starts at the trigger (**ASK THE USER**, Part 3 M1) | `thrust_csv` |
| Aero drag | D(v) = ρ_r · D20 · (v/20)^(2 − k) | D20 from CFD at 20 m/s; k from CFD at two speeds (section 4.6), default 0; ρ_r = `air_density_kgm3` / 1.225 |
| Lift | L(v) = ρ_r · L20 · (v/20)^(2 − k) (positive up) | L20 from CFD |
| Rolling | F_roll = μ · max(N_f, 0) + μ · max(N_r, 0) | `mu_roll`; axle loads N_f, N_r from 4.2.2 |
| Constant | R0 | `R0_N` (M3; includes guide rub at rest attitude and constant bearing torque if M4 was folded in) |
| Bearings | F_bear = Σ_wheels (τ0 + k_b·v/r)/r | `bearing_tau0_Nm`, `bearing_k_Nms` (M4); zero if not measured |
| Guides | F_guide = μ_g · (max(−N_f, 0) + max(−N_r, 0)) | `mu_guide` (M7) |

### 4.2.2 Axle loads and launch pitch (new; this was missing)

Frame: the CFD frame (x rearward from the nose tip, z up from the track). Rear contact point P_r = (x_r, 0), front P_f = (x_f, 0), wheelbase W = x_r − x_f. Centre of mass at (x_g, h_g) at time t (including the propellant still aboard: `MassReport.com_with_propellant` mixes them). Thrust acts along the cartridge axis at height h_T (`CHAMBER_AXIS_Z_MM` = 31 mm today), pushing the car forward (−x). The car accelerates forward with magnitude a.

The car does not rotate while all four wheels are on the track, so the sum of moments about the rear contact point is zero. Taking moments about the y axis at P_r, using (r × F)_y = r_z·F_x − r_x·F_z with r measured from P_r:

| Force | Where | Moment about P_r |
|---|---|---|
| Weight (0, −m g) | (x_g − x_r, h_g) | (x_g − x_r)·m g = −s_g·m g, where s_g = x_r − x_g is how far the CoM is ahead of the rear axle |
| Front normal (0, N_f) | (−W, 0) | +W·N_f |
| Thrust (−T, 0) | (·, h_T) | −h_T·T |
| d'Alembert inertial force (+m a, 0) | (·, h_g) | +h_g·m a |
| Aerodynamic force and moment | from CFD | M_y + x_r·L, where M_y is the CFD pitching moment about the origin (0,0,0) (the code's `MOMENT_REFERENCE_POINT_M`), full car, scaled by (v/20)^(2−k)·ρ_r |
| Ground friction | at z = 0 | 0 |

Setting the sum to zero:

```
N_f = [ s_g·m g + h_T·T − h_g·m a − (M_y + x_r·L) ] / W
N_r = m g − L − N_f
```

Reading it:

- **A thrust line above the centre of mass (h_T > h_g) pushes the nose down and unloads the rear wheels.** Thrust is applied high, the car's inertia resists low: the car tips forward. During thrust, m a ≈ 0.95 T (the rest of T goes into spinning the wheels and overcoming resistance), so the thrust contribution is roughly T·(h_T − 0.95 h_g)/W.
- With T ≈ 9 N, W = 0.12 m and h_T − h_g = 10 mm, the change in front load is about 0.75 N. The whole car weighs about 0.68 N (69 g with cartridge), so the static rear load is roughly 0.3-0.4 N. **The rear wheels lift at peak thrust unless the centre of mass is within about 4-5 mm of the thrust line.**
- When a rear wheel lifts, the rear tether guide (within 10 mm of the rear axle, T6.1) is pulled up against the line. The line holds the rear down, and the guide rubs: that is F_guide = μ_g·|N_r| when N_r < 0.
- The current code's placeholder penalty claimed that a centre of mass **below** the thrust line makes the nose go **up**, and made that the costlier side. The moment balance says the opposite: a centre of mass below the thrust line puts the nose **down** and the tail **up**. The placeholder is deleted (F03), and the balance above replaces it. **The earlier architecture review (REVIEW.md section 7) also stated the front wheels unload; that was wrong in sign and is corrected here: it is the rear that unloads.**
- Size of the effect, computed with the code in 4.3 (start car, D20 0.41 N, a 9.2 N / 0.25 s thrust curve, guide friction coefficient 0.3 as a placeholder): with the CoM 10 mm below the thrust line (h_g 21 mm, h_T 31 mm) the rear unloads to −0.34 N and the run is **5.3 ms slower** than with the CoM 2 mm below it (h_g 29 mm, rear load stays positive, no guide rub). That is as large as the best body-shape gains the old search found. CoM height relative to the thrust line is a first-order lever, and it is decided by where the mass sits, not by aerodynamics.
- This is a model. Part 3's launch video (M8) is the check: if the rear visibly lifts at launch, the model's sign and size are confirmed; if the front lifts, something else (for example the striker's push or the line's tension) dominates and the agent must investigate before trusting this term.

Wheel spin-up torque (I·α at each axle) also moves load between axles; it is about 4·I/r² ≈ 2.8 g of effective mass, about 4% of m a, and is neglected here. Mention it in the report if the launch margin is within 10% of zero.

### 4.2.3 Integration

Same scheme as today, which is sound: distance domain, state (t, q = v²), RK4, a power-2 grid in distance clustered at the start, starting at s_0 = 1e-4 m with t_0 and q_0 from a constant-acceleration start (a_0 from the forces at t = 0, v = 0). Use 2,000 steps (the measured curve rises faster than the synthetic one). A convergence test (4.8) proves the step count.

Because N_f and N_r depend on a, and F_guide depends on N, and a depends on F_guide: at each force evaluation, compute a once without guide friction, compute N_f and N_r with that a, add F_guide, recompute a. One fixed-point pass is enough because F_guide changes a by a few percent.

The car does not move until thrust exceeds static resistance; with a 9 N thrust and resistances of a few hundredths of a newton this happens within the first sample of thrust and needs no special handling.

---

## 4.3 `race/race_model.py` (complete)

```python
"""race_model.py -- 20 m race time of a CO2 car from measured inputs. NumPy only.

Replaces race_objective.py (JAX, RBF thrust fit, invented COM penalties). See bible Part 4.

    from race_model import Car, Thrust, race_time, exchange_rates
    th = Thrust.from_csv("inputs/thrust_measured.csv")
    car = Car.from_inputs(measured, mass_report, cfd)      # or construct directly
    r = race_time(car, th)          # r.time_s, r.v_finish, r.launch_margin_N, r.trace (optional)

All SI units. Axle loads use the CFD frame: x rearward from the nose tip, z up from the track.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

G = 9.80665
TRACK_M = 20.0


@dataclass(frozen=True)
class Thrust:
    t: np.ndarray                 # s, increasing, starts at 0 (thrust onset)
    F: np.ndarray                 # N
    prop_kg: np.ndarray           # propellant still aboard, kg; ends at 0
    delay_s: float = 0.0          # added to the race time if timing starts at the trigger

    @staticmethod
    def from_csv(path: str, delay_s: float = 0.0) -> "Thrust":
        rows = list(csv.DictReader(open(path)))
        t = np.array([float(r["time (s)"]) for r in rows])
        F = np.array([float(r["force (N)"]) for r in rows])
        m = np.array([float(r["mass (kg)"]) for r in rows])
        prop = np.maximum(m - m[-1], 0.0)          # works for the old file (car+prop) and the new (prop only)
        return Thrust(t - t[0], np.maximum(F, 0.0), prop, delay_s)

    def force(self, t: float) -> float:
        return float(np.interp(t, self.t, self.F, left=0.0, right=0.0))

    def prop(self, t: float) -> float:
        return float(np.interp(t, self.t, self.prop_kg, left=self.prop_kg[0], right=0.0))

    @property
    def impulse(self) -> float:
        return float(np.trapezoid(self.F, self.t))


@dataclass(frozen=True)
class Car:
    m_car: float                  # kg, manufactured car without cartridge
    m_shell: float                # kg, empty cartridge
    D20: float                    # N, full car drag at 20 m/s, rho = 1.225
    L20: float = 0.0              # N, full car lift at 20 m/s (+ up)
    My20: float = 0.0             # N m, CFD pitching moment about (0,0,0) at 20 m/s, full car
    drag_exp: float = 0.0         # k in D ~ v^(2-k)
    rho_ratio: float = 1.0        # venue density / 1.225
    I_f: float = 1.25e-7          # kg m2, ONE front wheel
    I_r: float = 1.53e-7          # kg m2, ONE rear wheel
    r_f: float = 0.01413          # m
    r_r: float = 0.01413          # m
    mu: float = 0.010
    R0: float = 0.0               # N
    tau0: float = 0.0             # N m per wheel, constant bearing torque
    k_b: float = 0.0              # N m s per wheel, viscous bearing torque
    mu_guide: float = 0.0
    x_f: float = 0.062            # m, front axle (CFD frame)
    x_r: float = 0.182            # m, rear axle
    x_g: float = 0.12             # m, CoM of the car without propellant, incl. shell
    h_g: float = 0.025            # m
    x_prop: float = 0.208         # m, propellant CoM (cartridge)
    h_T: float = 0.031            # m, thrust line height (chamber axis)
    h_prop: float = 0.031         # m

    @property
    def W(self) -> float:
        return self.x_r - self.x_f


@dataclass
class Result:
    time_s: float
    v_finish: float
    v_max: float
    launch_margin_N: float        # min over the run of min(N_f, N_r); < 0 means a wheel lifted
    guide_impulse_Ns: float       # integral of guide friction over time
    trace: dict = field(default_factory=dict)


def _forces(car: Car, th: Thrust, t: float, v: float, a_prev: float):
    m_p = th.prop(t)
    m = car.m_car + car.m_shell + m_p
    m_eff = m + 2 * car.I_f / car.r_f ** 2 + 2 * car.I_r / car.r_r ** 2
    vr = max(v, 0.0) / 20.0
    aero = car.rho_ratio * vr ** (2.0 - car.drag_exp) if vr > 0 else 0.0
    D, L, My = car.D20 * aero, car.L20 * aero, car.My20 * aero
    T = th.force(t)
    x_g = (car.x_g * (m - m_p) + car.x_prop * m_p) / m
    h_g = (car.h_g * (m - m_p) + car.h_prop * m_p) / m
    s_g = car.x_r - x_g

    def loads(a):
        Nf = (s_g * m * G + car.h_T * T - h_g * m * a - (My + car.x_r * L)) / car.W
        return Nf, m * G - L - Nf

    bear = 2 * (car.tau0 + car.k_b * v / car.r_f) / car.r_f + 2 * (car.tau0 + car.k_b * v / car.r_r) / car.r_r
    a = a_prev
    for _ in range(2):                                   # one fixed-point pass on a <-> loads
        Nf, Nr = loads(a)
        roll = car.mu * (max(Nf, 0.0) + max(Nr, 0.0))
        guide = car.mu_guide * (max(-Nf, 0.0) + max(-Nr, 0.0))
        a = (T - D - roll - car.R0 - bear - guide) / m_eff
    return a, min(Nf, Nr), guide


def race_time(car: Car, th: Thrust, n_steps: int = 2000, s0: float = 1e-4, keep_trace: bool = False) -> Result:
    a0, _, _ = _forces(car, th, 0.0, 0.0, 0.0)
    if a0 <= 0:
        raise ValueError(f"the car does not start: a0 = {a0:.3f} m/s2")
    u = np.linspace(0.0, 1.0, n_steps + 1)
    xs = s0 + (TRACK_M - s0) * u ** 2
    t, q = np.sqrt(2 * s0 / a0), 2 * a0 * s0
    a_last, margin, guide_imp, vmax = a0, np.inf, 0.0, 0.0
    tr = {"s": [], "t": [], "v": [], "a": [], "margin": []} if keep_trace else {}

    def deriv(t_, q_):
        nonlocal a_last
        v_ = np.sqrt(max(q_, 1e-12))
        a_, m_, g_ = _forces(car, th, t_, v_, a_last)
        return 1.0 / v_, 2.0 * a_, a_, m_, g_

    for i in range(n_steps):
        dx = xs[i + 1] - xs[i]
        k1t, k1q, a1, m1, g1 = deriv(t, q)
        k2t, k2q, *_ = deriv(t + 0.5 * dx * k1t, q + 0.5 * dx * k1q)
        k3t, k3q, *_ = deriv(t + 0.5 * dx * k2t, q + 0.5 * dx * k2q)
        k4t, k4q, *_ = deriv(t + dx * k3t, q + dx * k3q)
        dt = dx / 6.0 * (k1t + 2 * k2t + 2 * k3t + k4t)
        q = max(q + dx / 6.0 * (k1q + 2 * k2q + 2 * k3q + k4q), 1e-12)
        guide_imp += g1 * dt
        t += dt
        a_last = a1
        margin = min(margin, m1)
        vmax = max(vmax, np.sqrt(q))
        if keep_trace:
            for k, val in zip(tr, (xs[i + 1], t, np.sqrt(q), a1, m1)):
                tr[k].append(val)
        if q <= 1e-10:
            raise ValueError(f"the car stops at {xs[i + 1]:.2f} m")
    return Result(t + th.delay_s, float(np.sqrt(q)), float(vmax), float(margin), float(guide_imp),
                  {k: np.array(v) for k, v in tr.items()})


def exchange_rates(car: Car, th: Thrust) -> dict:
    """Race-time sensitivities by central differences (ms per unit stated in the key)."""
    def T(**kw):
        return race_time(replace(car, **kw), th).time_s
    h = {"D20": 0.005, "m_car": 0.0005, "mu": 0.002, "R0": 0.002, "h_g": 0.001}
    out = {}
    for name, step in h.items():
        v = getattr(car, name)
        out[name] = (T(**{name: v + step}) - T(**{name: v - step})) / (2 * step)
    I = car.I_f
    out["I_wheels_minus20pct_ms"] = (T(I_f=0.8 * I, I_r=0.8 * car.I_r) - T()) * 1e3
    return {"ms_per_mN_drag": out["D20"], "ms_per_g_mass": out["m_car"], "ms_per_0.001_mu": out["mu"],
            "ms_per_mN_R0": out["R0"], "ms_per_mm_com_height": out["h_g"],
            "wheel_I_minus20pct_ms": out["I_wheels_minus20pct_ms"]}


def load_inputs(path: str = "inputs/measured.json") -> dict:
    d = json.loads(Path(path).read_text())
    unmeasured = sorted(k for k, v in d.items() if isinstance(v, dict) and not v.get("measured"))
    return {"values": {k: (v["value"] if isinstance(v, dict) else v) for k, v in d.items()},
            "unmeasured": unmeasured}
```

Notes on the code:

- `exchange_rates` returns seconds per SI unit internally; the key names say ms per mN, ms per g and so on because 1 s/N = 1 ms/mN and 1 s/kg = 1 ms/g. Check this conversion in the test (4.8) rather than trusting the key names.
- `Car.from_inputs(...)` is a small constructor the agent writes that fills the fields from `inputs/measured.json`, the mass report (`MassReport` in `pipeline.py`: total mass, CoM; propellant CoM from `com_with_propellant`), the assembly (axle positions: `x_front_mm`, `x_front_mm + W_mm`; wheel radii), and the CFD outcome (D20, L, raw pitching moment). The pipeline currently converts the pitching moment into a coefficient with a placeholder reference length (`physics_contract.to_full_car`, `ref_length = sqrt(A_full)`); carry the raw full-car moment `2 × pitching_moment_half` through `CFDOutcome` as a new field `My_Nm` instead.
- The CoM of the car without propellant must include the empty cartridge shell at the cartridge's position. `mass_com_ingest` already sums the shell into the totals; check that `x_g` and `h_g` come from those totals.

---

## 4.4 Wiring it in

1. `pipeline.evaluate_objective` → replace with `pipeline.race(car_inputs)` that builds a `Car` and calls `race_time`. Return `time_s`, `v_finish`, `v_max`, `launch_margin_N`, `guide_impulse_Ns`, and the list of unmeasured inputs.
2. `run_car.cfd_and_objective` → compute two times as today: at the car's actual manufactured mass (`T_s`) and at exactly the mass target (`T_at_target_s`, used to compare cars sized to slightly different masses). Add `launch_margin_N` and `rates` (from `exchange_rates`, once per car, about 1 s).
3. `run_car.write_report` → first line: the warning banner if any input is unmeasured:
   ```
   WARNING: these inputs are not measured: mu_roll, R0_N, ... Times are model estimates.
   ```
4. `run_car.what_if` → use `exchange_rates`.
5. Delete `race_objective.py`, `race_objective_adapter.py`, `race_objective_hash.txt` and their tests once nothing imports them (grep).

---

## 4.5 Before and after: what the replacement must reproduce

Before switching, run both models on the same inputs (old synthetic CSV, μ = 0.010, I = 1.39e-7 for every wheel, r = 14.13 mm, no new terms, D20 = 0.41 N, m_car = 48.2 g, m_shell = 21.15 g, L20 = 0) and compare:

| Quantity | Old JAX model | Independent NumPy check in the review | New `race_model.py` must give |
|---|---|---|---|
| Race time | (run it) | 1.5556 s | within 2 ms of the old model (the RBF fit and the linear interpolation differ slightly) |
| dT/dD | (old `gradients`) | 0.480 ms/mN | within 2% |
| dT/dm | (old) | 16.6 ms/g | within 2% |

Put this comparison in `race/tests/test_race_model.py` as a regression test with the numbers from the old model pasted in as constants (computed once, before deleting it, with a comment saying so).

---

## 4.6 CFD inputs the race model needs (the compute part of this Part)

For the reference car (Part 3 M9) and, from Part 7 on, for every car:

| Input | How | Batch |
|---|---|---|
| D20, L20 | CFD at 20 m/s (the normal run) | normal |
| My20 (raw pitching moment) | already computed by OpenFOAM's `forces` function object; read `pitching_moment_half` and carry it | normal |
| drag exponent k | CFD of the same car at 10 m/s and 20 m/s (and 25 m/s once, to check the fit). k = 2 − ln(D25/D10) / ln(2.5) style fit on log D versus log v | 2-3 extra solves per geometry; do it on 3 different cars once, then use the mean k for all cars if the three agree within 0.03 |

How to run the CFD at another speed: `OpenFOAMRunConfig.reference_speed_mps` sets the inlet velocity, the moving-ground velocity and the wheel rotation rate together (the wheel ω is computed in `assembly.py` from `SPEED_MPS`; check it is passed through and change it so ω = −U/R uses the run's speed, not a module constant). Write a batch with kind `car` and the extra argv `--cfd-json '{"reference_speed_mps": 10.0}'` after adding that key to `run_car`'s `--cfd-json` handling. Verify on the first run that the inlet, ground and wheel boundary conditions in the case's `0/U` all show the new speed.

---

## 4.7 Validation against real runs (Part 3 M9)

1. Build the reference car's geometry in the pipeline (from its STLs; **ASK THE USER** for them). If its body cannot be expressed by `param_body`, run CFD directly on its STLs (the CFD case builder takes any watertight half-car STL plus part STLs via `extra_surfaces`).
2. Inputs: measured mass, CoM (Part 3 3.7.4), wheel inertias, μ, R0, μ_g, the measured thrust curve, the venue air density for each run, D20, L20, My20 and k from 4.6.
3. Predict each run's time (different air density per run). Compare with the measured times.

Acceptance (write these thresholds into `STATUS.md` **before** computing the prediction):

- |mean predicted − mean measured| ≤ 5% of the measured mean, **and**
- the measured mean lies within the prediction's ±2σ band from the uncertainty propagation (4.9).

If it fails, diagnose in this order, changing one thing at a time and writing down each result:

1. Timing start convention (trigger versus beam) and `trigger_delay_ms`.
2. Thrust impulse: compare the M1 impulse with the impulse implied by the measured finish speed if M9 filmed it (momentum: impulse ≈ ∫(m_eff a + resistances) dt).
3. Tether and launch: does the M8 video show wheel lift? Is `mu_guide` measured?
4. Drag: ρ at the venue, drag exponent, CFD mesh level (Part 6 mesh study).
5. Only then consider a calibration factor. If one is used, it is a single multiplier on the thrust curve's force (the least-known input), fitted to the M9 mean, reported prominently, and re-checked on a second car in Part 8.

Never fit more than one free parameter to one car's runs.

---

## 4.8 Tests (`race/tests/test_race_model.py`)

Each test states its expected value analytically.

1. **Constant thrust, nothing else.** F = 5 N for all t, m_eff = m = 0.1 kg, no losses → t = √(2·20·0.1/5) = 1.2649 s. Tolerance 1e-4 s.
2. **Constant thrust with rolling.** F = 5 N, μ = 0.05, m = 0.1 kg, axle loads equal (h_T = h_g, x_g mid-wheelbase) → a = 50 − 0.4903 = 49.5097 m/s², t = √(40/a). Tolerance 1e-4 s.
3. **Effective mass.** F = 5 N, I such that 4·I/r² = m → t multiplies by √2. Tolerance 1e-4 relative.
4. **Axle loads at rest.** T = 0, a = 0, v = 0 → N_f = m g·s_g/W, N_r = m g·(W − s_g)/W.
5. **Pitch sign.** T = 9 N, h_T = h_g + 10 mm → N_r(t) < N_r(static) during thrust; h_T = h_g − 10 mm → N_f decreases instead.
6. **Step-count convergence.** Measured-like curve (9.2 e^(−t/0.25), 0.5 s), the full model: time with 2,000 steps versus 8,000 steps differ by less than 0.05 ms.
7. **Regression against the old model** (4.5).
8. **Exchange-rate units.** `exchange_rates(...)["ms_per_mN_drag"]` equals (T(D + 1 mN) − T(D − 1 mN))/2 in milliseconds computed by hand in the test.

---

## 4.9 Uncertainty propagation

Every input in `measured.json` has an `sd`. Propagate by Monte Carlo:

```python
def time_with_uncertainty(car: Car, th_runs: list[Thrust], sds: dict, n: int = 500, seed: int = 0):
    """sds: {field_name: sd} for Car fields; th_runs: the individual M1 runs (thrust varies run to run)."""
    rng = np.random.default_rng(seed)
    times = []
    for _ in range(n):
        kw = {k: getattr(car, k) + rng.normal(0.0, s) for k, s in sds.items()}
        th = th_runs[rng.integers(len(th_runs))]
        times.append(race_time(replace(car, **kw), th).time_s)
    return float(np.mean(times)), float(np.std(times))
```

Use each individual M1 run (not the mean curve) as a sample of the thrust: cartridge-to-cartridge variation is likely the largest single uncertainty in a real race, and it is common to every car, so it **cancels** in a comparison between two cars raced with the same cartridge batch. For **ranking cars**, use the mean curve and ignore thrust uncertainty. For **predicting a real time**, include it.

Write `measure/tests` or `cfd/tests` coverage for this function with a trivial car where the answer is known (sd = 0 → zero spread).

---

## 4.10 Outputs of this Part

1. `race/race_model.py` and its tests.
2. Exchange rates on the measured curve for the start car, in a table in `STATUS.md`:

   | Rate | Value (real ms) |
   |---|---|
   | per mN of drag at 20 m/s | |
   | per gram of car mass | |
   | per 0.001 of μ | |
   | per mN of constant resistance | |
   | per mm of CoM height (through the launch term) | |
   | wheel inertia −20% | |

   These rates replace every "model ms" estimate in the bible from here on. Part 7 uses them to decide which levers matter.
3. The validation result (4.7) with plots: predicted versus measured time per run; speed trace if M9 filmed the finish.
4. The launch margin for the start car: if it is negative (a wheel lifts), report how many mm of CoM height change would make it zero. This is likely a first-order design lever (moving mass low and forward, or lowering the chamber axis toward 30 mm, the T5.2 minimum).

---

## 4.11 Exit gate for Part 4

- [ ] `race_model.py` passes every test in 4.8.
- [ ] The old JAX model, adapter and hash file are deleted; `jax` removed from the image.
- [ ] Every report prints the unmeasured-input banner when needed.
- [ ] Validation against M9 passes the pre-registered thresholds, or the failure and its diagnosis are written down and the user has decided how to proceed.
- [ ] Exchange-rate table written to `STATUS.md` using the measured thrust curve.

Now open `05_RULES_LEGALITY_MASS.md`.
