"""part_ranges.py -- the legal range of every part setting Part 5's loop may tune.

A setting's legal range is where ALL of that part's rule gates pass, with every
other setting at its default, on a given car (body, x_front, wheelbase, wheel R):
several limits (wing height, clear air, overhang) depend on the car, so the range
is found on the car, by bisection from the default outwards on the gates
themselves -- the same gates the assembly and the referee apply. A bound equal to
the search window's end means no rule limits the setting there (`limited` False).

    legal_range("front_wing", "aoa_deg", car) -> {"lo", "hi", "lo_gate", "hi_gate", ...}
    all_ranges(car) -> {part: {setting: range}}

RULES names the regulation each setting runs into; tests/test_part_ranges.py checks
every bound just inside (all gates pass) and just outside (the named gate fails).
"""
from __future__ import annotations

import dataclasses
import math

import numpy as np

import beam_support as bsm
import nose as nz
import wings

# setting -> search window (the tuner's sensible span; a rule bound inside it is found)
SETTINGS = {
    "front_wing": {"chord_mm": (5.0, 40.0), "t_frac": (0.02, 0.6), "aoa_deg": (-20.0, 30.0),
                   "half_span_mm": (10.0, 60.0), "z_chord_mm": (0.0, 30.0),
                   "flap_chord_mm": (0.0, 20.0), "flap_aoa_deg": (0.0, 60.0),
                   "gap_to_wheel_mm": (0.0, 20.0), "camber": (0.0, 0.12)},
    "rear_wing": {"chord_mm": (5.0, 40.0), "t_frac": (0.02, 0.6), "aoa_deg": (-20.0, 30.0),
                  "half_span_mm": (10.0, 45.0), "x_le_after_ref_b_mm": (-10.0, 40.0)},
    "nose": {"length_mm": (2.0, 60.0), "k": (0.2, 1.5), "p": (1.5, 6.0), "tip_z_mm": (0.0, 30.0)},
    "supports": {"disc_r_mm": (4.0, 16.0), "beam_w_mm": (4.0, 30.0), "beam_h_mm": (0.3, 10.0),
                 "strip_w_mm": (1.0, 20.0), "pod_wall_mm": (0.3, 5.0)},
}

# the regulations each setting's range runs into (for the write-up; the gates decide)
RULES = {
    ("front_wing", "chord_mm"): "T8.6.2 chord 15-25 mm (with the flap)",
    ("front_wing", "t_frac"): "T8.6.3 thickness 2-6 mm",
    ("front_wing", "aoa_deg"): "T8.5.2 height outboard <= 20 mm, T8.7 clear air >= 5 mm",
    ("front_wing", "half_span_mm"): "T8.6.1 span >= 50 mm; T8.5.2/T7.9 beyond the wheels",
    ("front_wing", "z_chord_mm"): "T8.7 clear air to the track >= 5 mm, T8.5.2 height <= 20 mm",
    ("front_wing", "flap_chord_mm"): "T8.6.2 total chord <= 25 mm, T8.6.3 flap thickness",
    ("front_wing", "flap_aoa_deg"): "T8.5.2 height outboard <= 20 mm",
    ("front_wing", "gap_to_wheel_mm"): "T7.9.1 / T8.7 clear of the front wheel, T8.2 overhang <= 40",
    ("rear_wing", "chord_mm"): "T9.5.2 chord 15-25 mm, T9.4.2 overhang <= 40 mm",
    ("rear_wing", "t_frac"): "T9.5.3 thickness 2-6 mm",
    ("rear_wing", "aoa_deg"): "T9.4.2 overhang, T9.4.3 height <= 65 mm, T9.6 clear air",
    ("rear_wing", "half_span_mm"): "T9.5.1 span >= 50 mm",
    ("rear_wing", "x_le_after_ref_b_mm"): "T9.4.1 aft of Ref B, T9.4.2 overhang <= 40 mm",
    ("nose", "length_mm"): "T8.2 overhang <= 40 mm from Ref A",
    ("nose", "k"): "T8.5.1 nose height / half width",
    ("nose", "p"): "T8.5.1 nose half width",
    ("supports", "disc_r_mm"): "T7.12.1 in the wheel's cylinder, rim fit, T7.13 claw, T3.7",
    ("supports", "beam_w_mm"): "T7.12.1 in the wheel's cylinder (the plate's chord)",
    ("front_wing", "camber"): "T8.5.2 height outboard, T8.7 clear air (the section's shape)",
    ("nose", "tip_z_mm"): "T8.5.1 nose height, T3.7 track clearance",
    ("supports", "beam_h_mm"): "T7.12.1 in the cylinder (raised by the load sizing; a floor/pod fit)",
    ("supports", "strip_w_mm"): "T7.12.1 in the cylinder, T7.13 claw",
    ("supports", "pod_wall_mm"): "T7.12.1 (the pod in the cylinder), foam over the pod",
}


@dataclasses.dataclass
class Car:
    """What the parts are fitted to. body: right half, metres (trimesh)."""
    body: object
    x_front_mm: float = 46.0
    W_mm: float = 120.3
    R_front_mm: float = 14.12
    R_rear_mm: float = 14.12
    y_inner_mm: float = 23.25
    wheel_w_mm: float = 13.25


def gates(part: str, obj, car: Car) -> dict:
    """The part's signed rule margins (>= 0 passes) for these settings on this car."""
    if part == "front_wing":
        m = wings.build_front_wing(obj, car.x_front_mm, car.R_front_mm, car.body)
        return wings.front_wing_gates(obj, m, car.x_front_mm, car.R_front_mm)
    if part == "rear_wing":
        m = wings.build_rear_wing(obj, car.x_front_mm, car.W_mm, car.body)
        return wings.rear_wing_gates(obj, {k: m[k] for k in ("wing", "pylon")}, car.x_front_mm,
                                     car.W_mm, car.body, [car.body])
    if part == "nose":
        return nz.nose_gates(obj, nz.build_nose(obj, car.x_front_mm, car.body), car.x_front_mm)
    if part == "supports":
        import wheel as wh
        hub, _ = wh.hub_span_mm()
        x, R = car.x_front_mm, car.R_front_mm
        z = R - 0.3
        ch = bsm.pod_channel(obj, car.body, x, z, R)
        out = bsm.build(obj, x, z, car.y_inner_mm, car.wheel_w_mm, True, hub_mm=hub, R_mm=R, channel=ch)
        g = bsm.gates(obj, out, x, z, R, "front")
        if out["_pod"]:                       # the pod's own gates, as assembly.build adds them
            half = ch["length_mm"] / 2
            corner = max(math.hypot(half, z - ch["z_floor_mm"]), math.hypot(half, ch["z_arch_mm"] - z))
            g["T7.12.1_front_pod_in_cylinder"] = R - corner
            g["machining_front_foam_over_pod"] = ch["z_body_top_mm"] - ch["z_arch_mm"] - 4.0
        return g
    raise KeyError(part)


DEFAULTS = {"front_wing": wings.FrontWing, "rear_wing": wings.RearWing,
            "nose": nz.NoseCone, "supports": bsm.BeamSupport}


def _first_fail(part, base, setting, v, car):
    try:
        g = gates(part, dataclasses.replace(base, **{setting: v}), car)
    except Exception as e:                       # a setting the builder cannot make is not legal
        return f"build_failed: {type(e).__name__}"
    bad = sorted((m, k) for k, m in g.items() if m < -1e-9)
    return bad[0][1] if bad else None


def legal_range(part: str, setting: str, car: Car, base=None, tol: float = 0.01) -> dict:
    base = base or DEFAULTS[part]()
    v0 = getattr(base, setting)
    bad0 = _first_fail(part, base, setting, v0, car)
    if bad0 is not None:
        raise ValueError(f"{part}: the default {setting}={v0} is not legal on this car ({bad0})")
    a, b = SETTINGS[part][setting]
    out = {"default": v0, "rule": RULES.get((part, setting), "")}
    for side, end in (("lo", a), ("hi", b)):
        bad = _first_fail(part, base, setting, end, car)
        if bad is None:
            out[side], out[f"{side}_gate"], out[f"{side}_limited"] = end, None, False
            continue
        good = v0
        while abs(end - good) > tol:             # good passes, end fails
            mid = 0.5 * (good + end)
            if _first_fail(part, base, setting, mid, car) is None:
                good = mid
            else:
                end = mid
        out[side], out[f"{side}_gate"], out[f"{side}_limited"] = good, _first_fail(part, base, setting, end, car), True
    return out


def all_ranges(car: Car) -> dict:
    return {p: {s: legal_range(p, s, car) for s in SETTINGS[p]} for p in SETTINGS}


# ---- for the loop: bounds every step, and a projection back inside -----------------
#
# The loop moves every part setting at once, so a setting's range is taken at the
# CURRENT values of the others (not the defaults), and a projected point is checked as
# a whole. Warm-started from the last step's bounds, a setting whose bounds did not move
# costs two builds per side (one just inside, one just outside), not a full bisection.

def _edge(part, base, setting, car, good, bad, tol):
    """good passes, bad fails: bisect to tol; return (last good, first failing gate)."""
    while abs(bad - good) > tol:
        mid = 0.5 * (good + bad)
        if _first_fail(part, base, setting, mid, car) is None:
            good = mid
        else:
            bad = mid
    return good, _first_fail(part, base, setting, bad, car)


def bounds(car: Car, current: dict, prev: dict | None = None, tol: float = 0.02) -> dict:
    """{(part, setting): (lo, hi)} on this car with the other settings at `current`
    ({part: dataclass instance}, which must itself be legal). `prev` is the last step's
    result: a bound that still holds within tol is kept after two builds."""
    out = {}
    for part, names in SETTINGS.items():
        base = current[part]
        for s in names:
            v0 = getattr(base, s)
            a, b = SETTINGS[part][s]
            lo_hi = []
            for side, end in ((0, a), (1, b)):
                sign = -1 if side == 0 else 1
                p = prev.get((part, s)) if prev else None
                if p is not None:
                    q = p[side]
                    inside, outside = q - sign * tol, q + sign * tol
                    ok_in = (sign * (inside - v0) <= 0) or _first_fail(part, base, s, inside, car) is None
                    if ok_in and sign * (outside - end) < 0 and _first_fail(part, base, s, outside, car) is not None:
                        lo_hi.append(q)
                        continue
                if _first_fail(part, base, s, end, car) is None:
                    lo_hi.append(end)                       # no rule limit inside the window
                    continue
                lo_hi.append(_edge(part, base, s, car, v0, end, tol)[0])
            hi = lo_hi[1]
            out[(part, s)] = (min(lo_hi[0], v0), max(hi, v0))
    return out


def project(car: Car, current: dict, proposed: dict, bnds: dict | None = None) -> dict:
    """Clip each proposed setting into its bounds, then check each part as a whole; a
    part that still breaks a rule moves only as far along the step as stays legal
    (bisection on the step length). Returns {part: dataclass instance}, all legal."""
    bnds = bnds or bounds(car, current)
    out = {}
    for part in SETTINGS:
        cur, new = current[part], proposed.get(part, current[part])
        clip = {s: float(np.clip(getattr(new, s), *bnds[(part, s)])) for s in SETTINGS[part]}
        cand = dataclasses.replace(new, **clip)
        if not [m for m in gates(part, cand, car).values() if m < -1e-9]:
            out[part] = cand
            continue
        t_good, t_bad = 0.0, 1.0
        for _ in range(12):
            t = 0.5 * (t_good + t_bad)
            mix = dataclasses.replace(cand, **{s: getattr(cur, s) + t * (clip[s] - getattr(cur, s))
                                                for s in SETTINGS[part]})
            if [m for m in gates(part, mix, car).values() if m < -1e-9]:
                t_bad = t
            else:
                t_good = t
        # t = 0 keeps the current numbers but the proposal's switches (e.g. supports.strip on/off);
        # if that alone is not legal, the switch is not taken either
        if t_good == 0.0:
            at_cur = dataclasses.replace(cand, **{s: getattr(cur, s) for s in SETTINGS[part]})
            if [m for m in gates(part, at_cur, car).values() if m < -1e-9]:
                out[part] = cur
                continue
        out[part] = dataclasses.replace(cand, **{s: getattr(cur, s) + t_good * (clip[s] - getattr(cur, s))
                                                 for s in SETTINGS[part]})
    return out
