"""The one carve path: a layout and a list of edits to a carved field (2026-11-14).

    g, reports = carve(layout, edits)          # cutter geometry, every rule kept
    save(layout, edits, "carved.npy")          # the same, saved for run_car --phi-npy

Every caller that turns "start block + changes" into a body goes through here: the stress
tests (stress_cars.carve_field), the loop and compass step items, and any "rebuild this car".
Same layout and edits give the identical field (and so the identical STL) on any machine.
Before this, four paths built four different bodies from the same seed: raw Hamilton-Jacobi
moves (stress_cars), cutter.cut (the Part 1 lab), Gaussians added straight onto the field
(the step items, which skipped the zones and the milling) and a rebuild from --body-json.

Each edit is one cutter.cut, applied in order:
    {"bias_mm": b,                                        uniform grow (+) or thin (-)
     "bumps": [{"c_mm": [x, |y|, z], "amp_mm": a, "sigma_mm": s}, ...]   or "u": [0-1]*3,
                                                          a point in the current half body's box
     "unit": True,      True: the speed is scaled to peak 1 and the cut moves at most trust_mm
                        (the stress recipe); False: the speed is the move in mm, as given
     "trust_mm": 1.0, "substeps": 6}
    {"tunnel": {"ft_h": h, "ft_w": w, "ft_x0": x0, "ft_x1": x1, "ft_ramp": r}}   the underfloor
                        tunnel of param_body as one cut: the underside (downward faces) with
                        |y| < ft_w moves up ft_h mm in the middle, easing to 0 over ft_ramp mm at
                        x0 and x1 (car x, mm). The cutter keeps the rules and the ball-end reach,
                        so the channel is the legal, millable version of the loft tunnel
The surface speed at each half-surface vertex is bias + sum amp * exp(-d^2 / 2 sigma^2); the
cutter grows the solid where it is positive. A refused cut leaves the field as it was and is
named in its report.
"""
from __future__ import annotations

import warnings

import numpy as np


def _tunnel_mm(V_mm, N, t: dict) -> np.ndarray:
    r = max(float(t.get("ft_ramp", 25.0)), 1e-3)
    x = V_mm[:, 0]
    ease = np.minimum(np.clip((x - t["ft_x0"]) / r, 0, 1), np.clip((t["ft_x1"] - x) / r, 0, 1))
    under = (N[:, 2] < -0.5) & (np.abs(V_mm[:, 1]) < t.get("ft_w", 8.0))
    return -float(t["ft_h"]) * ease * under                   # thinning: the floor moves up


def _speed_mm(V_mm: np.ndarray, e: dict) -> np.ndarray:
    lo, hi = V_mm.min(0), V_mm.max(0)
    s = np.full(len(V_mm), float(e.get("bias_mm", 0.0)))
    for b in e.get("bumps", []):
        c = np.asarray(b["c_mm"], float) if "c_mm" in b else lo + np.asarray(b["u"], float) * (hi - lo)
        s += b["amp_mm"] * np.exp(-((V_mm - c) ** 2).sum(1) / (2.0 * b["sigma_mm"] ** 2))
    return s


def carve(layout: dict, edits: list, spacing_mm: float = 1.0):
    import cutter
    from unified_phi import extract_half_surface
    lay = {k: float(layout[k]) for k in ("W", "x_front", "d_halo")}
    g = cutter.start_block(lay, spacing_mm=spacing_mm)
    reports = []
    for e in edits:
        h = extract_half_surface(g)
        V = np.asarray(h.vertices)                               # metres
        if "tunnel" in e:
            N = np.asarray(h.vertex_normals) * (1.0 if h.volume >= 0 else -1.0)   # outward
            s = _tunnel_mm(V * 1e3, N, e["tunnel"])
            e = {"unit": False, **{k: v for k, v in e.items() if k != "tunnel"}}
        else:
            s = _speed_mm(V * 1e3, e)
        peak = float(np.abs(s).max())
        if peak == 0.0:
            reports.append({"status": "refused", "reason": "no_motion"})
            continue
        unit = e.get("unit", True)
        dT_dn = -(s / peak if unit else s * 1e-3)                # descent is -dT_dn: grow where s > 0
        trust = float(e.get("trust_mm", 1.0 if unit else peak)) * 1e-3
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            g, rep = cutter.cut(g, dT_dn, type("M", (), {"vertices": V})(), step_m=1.0,
                                max_substeps=int(e.get("substeps", 6)), trust_radius_m=trust)
        reports.append(rep)
    return g, reports


def save(layout: dict, edits: list, path, spacing_mm: float = 1.0) -> list:
    import cutter
    g, reports = carve(layout, edits, spacing_mm)
    cutter.save_field(g, path)
    return reports
