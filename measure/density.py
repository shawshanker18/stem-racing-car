"""measure/density.py -- cartridge masses (M2), Model Block foam density and printed-material
density (M6). Plain arithmetic; the value is in recording where each number came from.

    python measure/density.py cartridges inputs/raw/M2_cartridge_mass/<date>/masses.csv
        columns: cartridge, full_g, empty_g, temp_C
    python measure/density.py block inputs/raw/M6_density/<date>/block.csv
        columns: mass_g, length_mm, width_mm, height_mm   (one row per block; the official
        pre-bored hole and the underside slot are subtracted using the drawing values in
        part1-simulation/geometry_contract.py)
    python measure/density.py cubes inputs/raw/M6_density/<date>/cubes.csv --key pa12_density_gcm3
        columns: mass_g, x_mm, y_mm, z_mm

Add --write to record the result in inputs/measured.json.
"""
from __future__ import annotations

import argparse
import csv
import math
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "part1-simulation"))


def _rows(path: str) -> list:
    return [{k: (v if k == "cartridge" else float(v)) for k, v in r.items()} for r in csv.DictReader(open(path))]


def _sd(xs: list):
    return st.stdev(xs) if len(xs) > 1 else None


def cartridges(path: str) -> dict:
    rows = _rows(path)
    charge = [r["full_g"] - r["empty_g"] for r in rows]
    empty = [r["empty_g"] for r in rows]
    return {"charge_mass_g": (st.mean(charge), _sd(charge), len(rows)),
            "cartridge_shell_g": (st.mean(empty), _sd(empty), len(rows))}


def block_density(mass_g: float, length_mm: float, width_mm: float, height_mm: float) -> float:
    from geometry_contract import (MODEL_BLOCK_BORE_DEPTH_MM, MODEL_BLOCK_BORE_DIA_MM,
                                   MODEL_BLOCK_SLOT_DEPTH_MM, MODEL_BLOCK_SLOT_WIDTH_MM)
    outer = length_mm * width_mm * height_mm
    bore = math.pi * (MODEL_BLOCK_BORE_DIA_MM / 2) ** 2 * MODEL_BLOCK_BORE_DEPTH_MM
    slot = MODEL_BLOCK_SLOT_WIDTH_MM * MODEL_BLOCK_SLOT_DEPTH_MM * length_mm
    return mass_g / ((outer - bore - slot) / 1000.0)


def block(path: str) -> dict:
    rho = [block_density(r["mass_g"], r["length_mm"], r["width_mm"], r["height_mm"]) for r in _rows(path)]
    return {"foam_density_gcm3": (st.mean(rho), _sd(rho), len(rho))}


def cubes(path: str, key: str) -> dict:
    rho = [r["mass_g"] / (r["x_mm"] * r["y_mm"] * r["z_mm"] / 1000.0) for r in _rows(path)]
    return {key: (st.mean(rho), _sd(rho), len(rho))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=("cartridges", "block", "cubes"))
    ap.add_argument("csv")
    ap.add_argument("--key", default="pa12_density_gcm3")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    res = {"cartridges": lambda: cartridges(a.csv), "block": lambda: block(a.csv),
           "cubes": lambda: cubes(a.csv, a.key)}[a.what]()
    for k, (v, sd, n) in res.items():
        print(f"{k}: {v:.4f} (sd {sd if sd is None else round(sd, 4)}, n {n})")
        if a.write:
            from record import record
            record(k, round(v, 5), sd=None if sd is None else round(sd, 5), n=n, source=str(Path(a.csv).parent))


if __name__ == "__main__":
    main()
