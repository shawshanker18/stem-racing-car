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
