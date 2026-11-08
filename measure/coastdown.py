"""measure/coastdown.py -- fit constant and rolling resistance to coast-down position data.

    python measure/coastdown.py inputs/raw/M3_coastdown/2026-11-14 --D20 0.41 --rho 1.17
Reads   <dir>/car.json: {"mass_g": ..., "added_mass_g_by_run": {"run06": 20.0, ...},
                         "wheel_I_total_kgm2": ..., "wheel_r_m": ...}
        <dir>/run*.csv: t_s, x_m
Writes  <dir>/fit.json: R0_N, mu, their standard errors, residual RMS (mm), per-run initial speed
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import least_squares

G = 9.80665


def simulate(t, x0, v0, m, m_eff, R0, mu, c):
    def rhs(_t, s):
        v = max(s[1], 0.0)
        return [v, -(R0 + mu * m * G + c * v * v) / m_eff if v > 0 else 0.0]
    sol = solve_ivp(rhs, (t[0], t[-1]), [x0, v0], t_eval=t, rtol=1e-8, atol=1e-10)
    return sol.y[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--D20", type=float, required=True, help="car drag at 20 m/s, N (CFD)")
    ap.add_argument("--rho", type=float, default=1.225)
    a = ap.parse_args()
    d = Path(a.folder)
    car = json.loads((d / "car.json").read_text())
    c = a.D20 / 400.0 * a.rho / 1.225
    runs = []
    for p in sorted(d.glob("run*.csv")):
        arr = np.genfromtxt(p, delimiter=",", names=True)
        m = (car["mass_g"] + car.get("added_mass_g_by_run", {}).get(p.stem, 0.0)) * 1e-3
        m_eff = m + car["wheel_I_total_kgm2"] / car["wheel_r_m"] ** 2
        runs.append((p.stem, arr["t_s"] - arr["t_s"][0], arr["x_m"], m, m_eff))

    # parameters: R0, mu, then (x0, v0) per run
    def resid(q):
        R0, mu = q[0], q[1]
        out = []
        for k, (_n, t, x, m, m_eff) in enumerate(runs):
            x0, v0 = q[2 + 2 * k], q[3 + 2 * k]
            out.append(simulate(t, x0, v0, m, m_eff, R0, mu, c) - x)
        return np.concatenate(out)

    q0 = [0.005, 0.01]
    for _n, t, x, *_ in runs:
        q0 += [x[0], (x[min(10, len(x) - 1)] - x[0]) / (t[min(10, len(t) - 1)] - t[0])]
    fit = least_squares(resid, q0, bounds=([0, 0] + [-np.inf] * (len(q0) - 2), np.inf))
    J = fit.jac
    dof = max(len(fit.fun) - len(q0), 1)
    cov = np.linalg.pinv(J.T @ J) * (fit.fun @ fit.fun) / dof
    se = np.sqrt(np.diag(cov))
    out = {"R0_N": fit.x[0], "R0_se": se[0], "mu": fit.x[1], "mu_se": se[1],
           "rms_mm": float(np.sqrt(np.mean(fit.fun ** 2)) * 1e3),
           "v0_by_run": {n: float(fit.x[3 + 2 * k]) for k, (n, *_r) in enumerate(runs)},
           "c_fixed": c}
    (d / "fit.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
