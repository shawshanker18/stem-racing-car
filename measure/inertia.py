"""measure/inertia.py -- wheel inertia (M5).

Method A (always): scale the CAD inertia by the measured mass (a uniform-density print).
    python measure/inertia.py scale --cad-I 1.2317e-7 --cad-mass-g 1.152 --mass-g 1.10 --bearing-g 0.30 \
        [--key wheel_I_front_kgm2 --write]
  The CAD values come from components/wheel.py summary(); its mass and inertia include
  one bearing, which is taken out before scaling and put back after.

Method B (a check): trifilar pendulum, I = m g R^2 T^2 / (4 pi^2 L), the platform subtracted.
    python measure/inertia.py trifilar --m-platform 0.002 --T-platform 1.10 --m-wheel 0.0011 \
        --T-both 1.05 --R 0.03 --L 0.5
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

G = 9.80665
BEARING_OD_MM = 6.0


def bearing_I(bearing_g: float) -> float:
    """What wheel.py adds for one bearing: 0.45 x mass x (outer race radius)^2, kg m2."""
    return 0.45 * bearing_g * 1e-3 * ((BEARING_OD_MM / 2 - 0.4) * 1e-3) ** 2


def scale(cad_I: float, cad_mass_g: float, mass_g: float, bearing_g: float) -> float:
    part_I = cad_I - bearing_I(bearing_g)
    return part_I * (mass_g - bearing_g) / (cad_mass_g - bearing_g) + bearing_I(bearing_g)


def trifilar(m: float, T: float, R: float, L: float) -> float:
    return m * G * R ** 2 * T ** 2 / (4 * math.pi ** 2 * L)


def main() -> None:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="how", required=True)
    s = sp.add_parser("scale")
    for k in ("--cad-I", "--cad-mass-g", "--mass-g"):
        s.add_argument(k, type=float, required=True)
    s.add_argument("--bearing-g", type=float, default=0.30)
    s.add_argument("--key", default=None)
    s.add_argument("--write", action="store_true")
    t = sp.add_parser("trifilar")
    for k in ("--m-platform", "--T-platform", "--m-wheel", "--T-both", "--R", "--L"):
        t.add_argument(k, type=float, required=True)
    a = ap.parse_args()
    if a.how == "scale":
        I = scale(a.cad_I, a.cad_mass_g, a.mass_g, a.bearing_g)
        print(f"I = {I:.4e} kg m2 (CAD {a.cad_I:.4e}, ratio {I / a.cad_I:.3f})")
        if a.write and a.key:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from record import record
            record(a.key, I, n=1, source=f"measure/inertia.py scale, wheel mass {a.mass_g} g")
    else:
        Ip = trifilar(a.m_platform, a.T_platform, a.R, a.L)
        It = trifilar(a.m_platform + a.m_wheel, a.T_both, a.R, a.L)
        print(f"I_wheel = {It - Ip:.4e} kg m2 (platform {Ip:.4e})")


if __name__ == "__main__":
    main()
