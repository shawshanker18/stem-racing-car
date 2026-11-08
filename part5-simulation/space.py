"""space.py -- the car's searchable settings: names, steps, bounds, and how to read
and change one in a car description.

Moved unchanged from pattern.py (bible Part 2); the pattern search itself was retired
(docs/HISTORY.md). A car description is
    d = {"params": body dict, "parts": {"fw": {...}, "sup": {...}, "nose": {...}},
         "layout": {"W": ..., "x_front": ..., "d_halo": ...}}   (layout optional)
"""
from __future__ import annotations

import paths  # noqa: F401

LOFT = ([f"st_b{i}" for i in range(8)] + [f"st_zt{i}" for i in range(8)]
        + [f"st_zb{i}" for i in range(8)]
        + ["p", "s_b", "s_zt", "s_zb", "s_x0", "s_x1", "s_taper", "s_p", "blend_mm"])
# The front-wheel program (2026-09-30): the printed parts that shape the flow
# onto the front wheels, which carry ~44 % of the drag. name: (step, lo, hi).
# Bounds are the searchable range, not the rules: every candidate is built
# and audited, and one failing any gate is dropped like any other bad car.
PARTS = {
    "fw.aoa_deg": (2.0, -2.0, 14.0), "fw.z_chord_mm": (1.0, 6.5, 14.0),
    "fw.gap_to_wheel_mm": (1.0, 5.0, 10.0), "fw.half_span_mm": (2.0, 34.0, 42.5),
    "fw.flap_chord_mm": (1.0, 8.0, 10.5), "fw.flap_aoa_deg": (5.0, 0.0, 45.0),
    "fw.camber": (0.02, 0.0, 0.08),
    # The support (Part 4 beam_support), what the air sees of it: the plate and strip
    # crossing the gap to the wheel, and where the disc stands. The pod's wall sets how
    # much of the car's mass sits low in plastic instead of in a fatter body.
    "sup.beam_w_mm": (2.0, 8.0, 24.0), "sup.beam_h_mm": (0.3, 0.7, 4.0),
    "sup.strip": (1.0, 0.0, 1.0), "sup.strip_w_mm": (1.0, 4.0, 12.0),
    "sup.disc_recess_mm": (1.0, -2.5, 1.5), "sup.pod_wall_mm": (0.5, 0.7, 3.0),
    "nose.length_mm": (5.0, 10.0, 40.0), "nose.k": (0.15, 0.3, 1.0),
    "nose.p": (0.5, 2.0, 4.0), "nose.tip_z_mm": (2.0, 4.0, 20.0),
}
# The underfloor tunnel (Part 1 param_body ft_*): name: (step, lo, hi). ft_h = 0
# is no tunnel, so ft_h- from a shallow start tests "is the tunnel worth having".
FLOOR = {"ft_h": (3.0, 0.0, 10.0), "ft_w": (3.0, 3.2, 14.0), "ft_x0": (15.0, 30.0, 120.0),
         "ft_x1": (15.0, 100.0, 190.0), "ft_ramp": (10.0, 5.0, 60.0)}
FLOOR_START = {"ft_h": 3.0}
PART_FLAGS = {"fw": "--fwing-json", "sup": "--support-json", "nose": "--nose-json"}
# The car's layout: name: (step, lo, hi), and run_car's defaults and flags.
LAYOUT = {"W": (2.0, 120.3, 140.0), "x_front": (2.0, 46.0, 56.0), "d_halo": (5.0, 25.0, 75.0)}
LAYOUT_START = {"W": 120.3, "x_front": 46.0, "d_halo": 43.72}
LAYOUT_FLAGS = {"W": "--W", "x_front": "--x-front", "d_halo": "--d-halo"}


def _pb():
    import param_body as pb
    return pb


def step0(name: str) -> float:
    if name in LAYOUT:
        return LAYOUT[name][0]
    if name in PARTS:
        return PARTS[name][0]
    if name.startswith("mode"):
        return 2.0
    if name in ("p", "s_p"):
        return 0.3
    if name in ("s_x0", "s_x1"):
        return 5.0
    if name in FLOOR:
        return FLOOR[name][0]
    if name == "blend_mm":
        return 1.0
    return 2.0


def bounds(name: str) -> tuple:
    pb = _pb()
    if name in LAYOUT:
        return LAYOUT[name][1:]
    if name in PARTS:
        return PARTS[name][1:]
    if name.startswith("mode"):
        return (-6.0, 6.0)
    if name.startswith("st_b"):
        return (6.0, 20.0)
    if name.startswith("st_zt"):
        return (14.0, 48.0)
    if name in ("st_zb0", "st_zb1"):    # the nose stays under 25 mm (T8.5.1), so the floor must too
        return (3.5, 15.0)
    if name.startswith("st_zb"):
        return (3.5, 23.0)
    if name == "blend_mm":
        return (0.0, 6.0)
    if name in FLOOR:
        return FLOOR[name][1:]
    return pb.BOUNDS[name]


def _part_default(name: str) -> float:
    import beam_support as bsm
    import nose as ns
    import wings as wg
    part, key = name.split(".")
    return float(getattr({"fw": wg.FrontWing(), "sup": bsm.BeamSupport(),
                          "nose": ns.NoseCone()}[part], key))


def get(d: dict, name: str) -> float:
    """d = {"params": body dict, "parts": {"fw": {...}, "sup": {...}, "nose": {...}},
    "layout": {"W": ..} (optional)}."""
    if name in LAYOUT:
        return float(d.get("layout", {}).get(name, LAYOUT_START[name]))
    if name in PARTS:
        part, key = name.split(".")
        return float(d["parts"].get(part, {}).get(key, _part_default(name)))
    bp = _pb().BodyParams.from_dict(d["params"])
    seq, i = _indexed(name)
    return float(getattr(bp, seq)[i]) if seq else float(getattr(bp, name))


def put(d: dict, name: str, v: float) -> dict:
    if name in LAYOUT:
        return dict(d, layout=dict(d.get("layout", {}), **{name: float(v)}))
    if name in PARTS:
        part, key = name.split(".")
        parts = {k: dict(x) for k, x in d["parts"].items()}
        parts.setdefault(part, {})[key] = bool(round(v)) if key == "strip" else float(v)
        return dict(d, parts=parts)
    from dataclasses import replace
    bp = _pb().BodyParams.from_dict(d["params"])
    seq, i = _indexed(name)
    if seq:
        vals = list(getattr(bp, seq))
        vals[i] = float(v)
        bp = replace(bp, **{seq: tuple(vals)})
    else:
        bp = replace(bp, **{name: float(v)})
    return dict(d, params=bp.as_dict())


def _indexed(name: str):
    """("st_b", 3) for "st_b3", ("modes", 7) for "mode7", (None, None) for a scalar."""
    for key, attr in (("st_b", "st_b"), ("st_zt", "st_zt"), ("st_zb", "st_zb"), ("mode", "modes")):
        if name.startswith(key) and name[len(key):].isdigit():
            return attr, int(name[len(key):])
    return None, None
