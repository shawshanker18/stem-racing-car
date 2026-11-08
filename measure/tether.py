"""measure/tether.py -- guide-on-line friction coefficient (M7).

    python measure/tether.py inputs/raw/M7_tether/<date>/pulls.csv [--write]

Reads   angle_deg, hanging_g, pull_N   (line pulled through a clamped guide; a hanging weight on
        the far end keeps it taut; angle = how far the line bends in the guide)
Model   capstan: pull = W e^(mu theta) for a line bent by theta over the guide's edge, so
        mu = ln(pull / W) / theta. Rows at 0 degrees are the friction-free check (pull = W).
"""
from __future__ import annotations

import argparse
import csv
import math
import statistics as st
import sys
from pathlib import Path

G = 9.80665


def mu_rows(path: str) -> list:
    out = []
    for r in csv.DictReader(open(path)):
        th = math.radians(float(r["angle_deg"]))
        W = float(r["hanging_g"]) * 1e-3 * G
        if th > 0:
            out.append(math.log(float(r["pull_N"]) / W) / th)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    mus = mu_rows(a.csv)
    m, sd = st.mean(mus), (st.stdev(mus) if len(mus) > 1 else None)
    print(f"mu_guide {m:.3f} (sd {sd}, n {len(mus)})")
    if a.write:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from record import record
        record("mu_guide", m, sd=sd, n=len(mus), source=str(Path(a.csv).parent))


if __name__ == "__main__":
    main()
