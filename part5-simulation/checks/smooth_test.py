"""
smooth_test.py -- does the body change smoothly with its settings?

A gradient solver needs a small setting change to make a small, proportionate change
to the shape. This sweeps settings in small steps at a fixed skin and fits a parabola
to the body's volume: what is left over is the builder's own noise. It is reported
against the volume a typical solver step moves, so it reads as "noise per step".
Also builds one car twice: the same settings must give the same body.

    python checks/smooth_test.py [--mm 1.0]
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

import paths  # noqa: F401,E402
import space  # noqa: E402

SETTINGS = ("mode6", "mode26", "mode41", "st_zt3", "st_b4", "s_b", "ft_h")
OFFSETS = np.linspace(-1.0, 1.0, 9)      # in units of the setting's own solver step


def body_cm3(d: dict, skin: float, tmp: Path) -> float:
    import param_body as pb
    import run_car as rc
    import trimesh
    g = pb.build(120.3, 46.0, 43.72, pb.BodyParams.from_dict(d["params"]), skin_offset_mm=skin)
    p = tmp / "b.stl"
    rc.export_body(g, p)
    return abs(float(trimesh.load(str(p), force="mesh").volume)) * 2e6      # both halves


def main() -> None:
    from coarse import use_spacing
    import param_body as pb
    ap = argparse.ArgumentParser()
    ap.add_argument("--mm", type=float, default=1.0)
    ap.add_argument("--skin", type=float, default=4.0)
    a = ap.parse_args()
    use_spacing(a.mm)
    tmp = Path(tempfile.mkdtemp())
    base = {"params": pb.BodyParams().as_dict(), "parts": {}}
    twice = abs(body_cm3(base, a.skin, tmp) - body_cm3(base, a.skin, tmp))
    print(f"grid {a.mm} mm. Same car built twice differs by {twice * 1e3:.4f} mm3", flush=True)
    print(f"{'setting':10s} {'step':>6s} {'volume per step mm3':>20s} {'noise mm3':>10s} {'noise/step':>11s}")
    for name in SETTINGS:
        lo, hi = space.bounds(name)
        v0, h = space.get(base, name), space.step0(name)
        x = np.clip(v0 + OFFSETS * h, lo, hi)
        y = np.array([body_cm3(space.put(base, name, float(v)), a.skin, tmp) for v in x]) * 1e3
        fit = np.polyval(np.polyfit(x, y, 2), x)
        noise, per_step = float(np.std(y - fit)), abs(float(np.polyfit(x, y, 1)[0])) * h
        print(f"{name:10s} {h:6.2f} {per_step:20.1f} {noise:10.2f} {noise / max(per_step, 1e-9):11.3f}", flush=True)


if __name__ == "__main__":
    main()
