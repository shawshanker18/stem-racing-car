"""measure/thrust.py -- raw force-sensor runs -> one mean thrust curve for the race model.

    python measure/thrust.py inputs/raw/M1_thrust/2026-11-12 --charge-g 7.95 --out inputs/thrust_measured.csv

Reads   <dir>/calibration.csv (mass_g, mean_reading, sd_reading), <dir>/run*.csv (t_s, reading)
Writes  --out: columns "time (s)", "force (N)", "mass (kg)" on a 0.5 ms grid from 0 to 1.5 s,
        where "mass (kg)" is the PROPELLANT still on board (charge x (1 - impulse so far / total)).
        <dir>/summary.json: per run peak, time to peak, impulse, duration, ringing frequency;
        ensemble mean and standard deviation of impulse and peak.
The race model (race/race_model.py) reads the three columns by name.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.signal import butter, filtfilt

G = 9.80665
GRID_DT = 5e-4
GRID_END = 1.5


def calibration(path: Path) -> tuple[float, float, float]:
    d = np.genfromtxt(path, delimiter=",", names=True)
    force = d["mass_g"] * 1e-3 * G
    slope, intercept = np.polyfit(d["mean_reading"], force, 1)
    resid = force - (slope * d["mean_reading"] + intercept)
    return float(slope), float(intercept), float(np.abs(resid).max())


def uniform(t: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    dt = float(np.median(np.diff(t)))
    tu = np.arange(t[0], t[-1], dt)
    return tu, np.interp(tu, t, y), 1.0 / dt


def one_run(path: Path, slope: float, intercept: float, cutoff_hz: float) -> dict:
    d = np.genfromtxt(path, delimiter=",", names=True)
    t, f, fs = uniform(d["t_s"], slope * d["reading"] + intercept)
    if fs < 900:
        raise ValueError(f"{path.name}: {fs:.0f} samples/s, need >= 1000")
    n0 = int(0.3 * fs)                                   # first 0.3 s are baseline
    f = f - np.median(f[:n0])
    noise = float(np.std(f[:n0]))
    spec = np.abs(np.fft.rfft(f[:n0] - f[:n0].mean()))
    b, a = butter(4, cutoff_hz / (fs / 2))
    ff = filtfilt(b, a, f)
    thr = max(0.1, 5 * noise)
    on = int(np.argmax(ff > thr))
    if ff[on] <= thr:
        raise ValueError(f"{path.name}: no thrust found above {thr:.3f} N")
    # walk back to where the filtered signal left the noise band
    while on > 0 and ff[on - 1] > 2 * noise:
        on -= 1
    tt, F = t[on:] - t[on], np.clip(ff[on:], 0.0, None)
    peak = float(F.max())
    above = np.nonzero(F > 0.01 * peak)[0]
    end = int(above[-1]) + int(0.02 * fs)
    tt, F = tt[:end], F[:end]
    imp = float(np.trapezoid(F, tt))
    ring = np.abs(np.fft.rfft(f[on:on + int(0.5 * fs)] - ff[on:on + int(0.5 * fs)]))
    freqs = np.fft.rfftfreq(min(int(0.5 * fs), len(f) - on), 1 / fs)
    return {"file": path.name, "fs": fs, "noise_N": noise, "peak_N": peak,
            "t_peak_s": float(tt[np.argmax(F)]), "impulse_Ns": imp, "duration_s": float(tt[-1]),
            "ringing_hz": float(freqs[np.argmax(ring[1:]) + 1]) if len(ring) > 2 else None,
            "_t": tt, "_F": F}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--charge-g", type=float, required=True, help="mean propellant mass from M2")
    ap.add_argument("--cutoff-hz", type=float, default=300.0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    d = Path(a.folder)
    slope, intercept, cal_err = calibration(d / "calibration.csv")
    runs = [one_run(p, slope, intercept, a.cutoff_hz) for p in sorted(d.glob("run*.csv"))]
    if len(runs) < 3:
        raise SystemExit("need at least 3 runs (5 recommended)")
    grid = np.arange(0.0, GRID_END + GRID_DT / 2, GRID_DT)
    curves = np.array([np.interp(grid, r["_t"], r["_F"], right=0.0) for r in runs])
    mean = curves.mean(axis=0)
    imp_t = np.concatenate([[0.0], np.cumsum(0.5 * (mean[1:] + mean[:-1]) * GRID_DT)])
    prop_kg = a.charge_g * 1e-3 * (1.0 - imp_t / imp_t[-1])
    with open(a.out, "w") as fh:
        fh.write("time (s),force (N),mass (kg)\n")
        for t, F, m in zip(grid, mean, prop_kg):
            fh.write(f"{t:.6f},{F:.6f},{max(m, 0.0):.9f}\n")
    imps = np.array([r["impulse_Ns"] for r in runs])
    peaks = np.array([r["peak_N"] for r in runs])
    summary = {"calibration_max_error_N": cal_err, "n_runs": len(runs),
               "impulse_Ns_mean": float(imps.mean()), "impulse_Ns_sd": float(imps.std(ddof=1)),
               "peak_N_mean": float(peaks.mean()), "peak_N_sd": float(peaks.std(ddof=1)),
               "exhaust_velocity_ms": float(imps.mean() / (a.charge_g * 1e-3)),
               "runs": [{k: v for k, v in r.items() if not k.startswith("_")} for r in runs]}
    (d / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps({k: v for k, v in summary.items() if k != "runs"}, indent=1))


if __name__ == "__main__":
    main()
