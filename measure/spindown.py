"""measure/spindown.py -- bearing drag from a wheel spinning down (M4).

    python measure/spindown.py inputs/raw/M4_spindown/<date>/run01.csv [run02.csv ...] --I 1.23e-7 [--write]

Reads   t_s, rpm   (tachometer readings against time)
Fits    I dw/dt = -(tau0 + k w)  by linear regression of dw/dt on w (w smoothed first)
Prints  tau0 (N m) and k (N m s), and the equivalent drag at the tread at 5 and 20 m/s.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np


def fit(t: np.ndarray, rpm: np.ndarray, I: float) -> tuple[float, float]:
    """(tau0, k) for I dw/dt = -(tau0 + k w)."""
    from scipy.signal import savgol_filter
    w = np.asarray(rpm, float) * 2 * np.pi / 60.0
    order = np.argsort(t)
    t, w = np.asarray(t, float)[order], w[order]
    win = max(5, (len(t) // 5) | 1)
    ws = savgol_filter(w, win, 2) if len(t) > win else w
    dw = np.gradient(ws, t)
    A = np.c_[np.ones_like(ws), ws]
    (a0, a1), *_ = np.linalg.lstsq(A, dw, rcond=None)
    return float(-a0 * I), float(-a1 * I)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="+")
    ap.add_argument("--I", type=float, required=True, help="the wheel's inertia, kg m2 (M5)")
    ap.add_argument("--r", type=float, default=0.01412, help="wheel radius, m")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    fits = []
    for p in a.csv:
        d = np.genfromtxt(p, delimiter=",", names=True)
        fits.append(fit(d["t_s"], d["rpm"], a.I))
    tau0, k = (float(np.mean([f[i] for f in fits])) for i in (0, 1))
    for v in (5.0, 20.0):
        print(f"at {v:4.1f} m/s: {(tau0 + k * v / a.r) / a.r * 1e3:.3f} mN per wheel")
    print(f"tau0 {tau0:.3e} N m, k {k:.3e} N m s ({len(fits)} runs)")
    if a.write:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from record import record
        src = str(Path(a.csv[0]).parent)
        record("bearing_tau0_Nm", tau0, n=len(fits), source=src)
        record("bearing_k_Nms", k, n=len(fits), source=src)


if __name__ == "__main__":
    main()
