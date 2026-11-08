"""measure/track.py -- timed runs of a real car (M9): mean, spread, air density per run.

    python measure/track.py inputs/raw/M9_track_runs/<date>/runs.csv [--write]

Reads   run, cartridge, full_g, time_s, temp_C, pressure_hPa, humidity_pct, notes
Prints  mean time, sd (the track noise), standard error, and the air density of each run.
--write records track_noise_s and the mean venue air density.
"""
from __future__ import annotations

import argparse
import csv
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from air import air_density  # noqa: E402


def summarise(path: str) -> dict:
    rows = list(csv.DictReader(open(path)))
    t = [float(r["time_s"]) for r in rows]
    rho = [air_density(float(r["temp_C"]), float(r["pressure_hPa"]), float(r["humidity_pct"])) for r in rows]
    sd = st.stdev(t) if len(t) > 1 else None
    return {"n": len(t), "mean_s": st.mean(t), "sd_s": sd, "se_s": sd / len(t) ** 0.5 if sd else None,
            "rho_by_run": rho, "rho_mean": st.mean(rho)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    s = summarise(a.csv)
    print(f"{s['n']} runs: mean {s['mean_s']:.4f} s, sd {s['sd_s']}, se {s['se_s']}; air {s['rho_mean']:.4f} kg/m3")
    if a.write:
        from record import record
        src = str(Path(a.csv).parent)
        if s["sd_s"] is not None:
            record("track_noise_s", s["sd_s"], n=s["n"], source=src)
        record("air_density_kgm3", s["rho_mean"], sd=st.stdev(s["rho_by_run"]) if s["n"] > 1 else None,
               n=s["n"], source=src)


if __name__ == "__main__":
    main()
