"""A high body floor at the axle (cars 44130/0, 50002/0): the pod's strip went above the
roof as a loose slab. Now the support switches to a floor-high rod, set FLOOR_EMBED_MM
into the floor and inside the wheel's cylinder, or says why it cannot."""
import dataclasses

import numpy as np
import pytest
import trimesh

import beam_support as bsm
import wheel as wh

X, R, Y_IN, W = 166.3, 14.123, 16.25, 17.25
Z = R - 0.3
CEILING = Z + R - 0.3 - bsm.FLOOR_EMBED_MM          # the highest floor any support can hold


def _build(floor_mm, top_mm=40.0, bs=None):
    body = trimesh.creation.box(bounds=[[0.030, 0.0, floor_mm / 1e3], [0.222, 0.016, top_mm / 1e3]])
    bs = bs or bsm.BeamSupport()
    ch = bsm.pod_channel(bs, body, X, Z, R)
    _, hub = wh.hub_span_mm()
    out = bsm.build(bs, X, Z, Y_IN, W, True, hub_mm=hub, R_mm=R, channel=ch)
    return out, bsm.gates(bs, out, X, Z, R, "rear")


def _common(out, g):
    part = out["support"]
    assert part.is_watertight and len(part.split(only_watertight=False)) == 1
    v = part.vertices * 1e3
    assert np.hypot(v[:, 0] - X, v[:, 2] - Z).max() <= R - 0.05            # T7.12.1, margin 0.05
    assert g["T7.13_rear_support_clear_of_claw"] >= 0.05                  # T7.13, margin 0.05
    load = {k: m for k, m in g.items() if k.startswith("load_")}
    assert all(m >= 0 for m in load.values()), load                       # strong enough


def test_floor_of_44130_gets_a_legal_floor_high_rod():
    out, g = _build(24.5)
    assert out["_floor_high"] and not out["_pod"]
    _common(out, g)
    assert g["fit_rear_floor_rod_embed"] >= 0                             # 3 mm into the foam


def test_floor_of_50002_is_above_any_legal_support_and_says_why():
    out, g = _build(26.6)
    assert out["_floor_high"]
    _common(out, g)                                                       # still one legal solid
    assert g["fit_rear_floor_rod_embed"] < -1.5                           # only ~1 mm of foam in reach
    assert "body floor at the axle" in out["_struct"]["floor_embed_note"]


def test_rod_embed_just_inside_and_just_outside_the_ceiling():
    for floor, ok in ((CEILING - 0.05, True), (CEILING + 0.05, False)):
        out, g = _build(floor)
        _common(out, g)
        assert (g["fit_rear_floor_rod_embed"] >= 0) is ok, floor


def _switch_floor():
    lo, hi = 3.0, CEILING
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if _build(mid)[0]["_pod"]:
            lo = mid
        else:
            hi = mid
    return lo


def test_pod_to_rod_switch_just_inside_and_just_outside():
    f0 = _switch_floor()
    assert 3.0 < f0 < CEILING                                             # measured 9.5 on this body
    below, gb = _build(f0 - 0.05)
    above, ga = _build(f0 + 0.05)
    assert below["_pod"] and not below["_floor_high"]
    assert above["_floor_high"] and not above["_pod"]
    for out, g in ((below, gb), (above, ga)):
        _common(out, g)
        assert all(m >= 0 for k, m in g.items() if k.startswith("fit_")), g


def test_a_loose_piece_stops_the_build():
    # the guard build() runs on every support: one solid passes, two raise
    a = trimesh.creation.box(extents=[0.01, 0.01, 0.01])
    b = a.copy()
    b.apply_translation([0.05, 0, 0])
    bsm.require_one_piece(a)
    with pytest.raises(ValueError, match="pieces"):
        bsm.require_one_piece(trimesh.util.concatenate([a, b]))


def test_floor_high_car_is_built_milled_judged_and_timed_as_one_rod():
    """A car with a pod at the front and a floor-high rod at the rear, through assembly and
    joints: the rod's slot is milled into the body the referee judges, the rod sits in it
    with no overlap, and the CFD surface (supports.stl) is the rod as built."""
    import tempfile
    import assembly
    import joints
    with tempfile.TemporaryDirectory() as td:
        hi = trimesh.creation.box(bounds=[[0.030, -0.017, 0.0245], [0.222, 0.017, 0.040]])   # floor 24.5
        lo = trimesh.creation.box(bounds=[[0.030, -0.017, 0.004], [0.090, 0.017, 0.040]])    # front: low floor
        full = trimesh.boolean.union([hi, lo], engine="manifold")
        body = trimesh.intersections.slice_mesh_plane(full, [0, 1, 0], [0, 0, 0], cap=True)
        body.export(f"{td}/body.stl", file_type="stl_ascii")
        a = assembly.build(120.3, 46.0, 43.72, f"{td}/body.stl", f"{td}/asm", support=bsm.BeamSupport())
        g = a["gates"]
        assert "front" in a["info"].get("pod", {}) and "rear" not in a["info"].get("pod", {})
        assert g["fit_rear_floor_rod_embed"] >= 0 and g["load_rear_floor_rod_stress"] >= 0, g
        assert g["T7.12.1_rear_support_in_cylinder"] >= 0.05 and g["T7.13_rear_support_clear_of_claw"] >= 0.05, g
        # timed = judged: the CFD surface holds the rod, top 3 mm into the floor, inside R - 0.3
        sup = trimesh.load(f"{td}/asm/supports.stl", force="mesh")
        rear = [p for p in sup.split(only_watertight=False) if p.bounds[:, 0].mean() > 0.1][0]
        assert abs(rear.bounds[1, 2] * 1e3 - (24.5 + bsm.FLOOR_EMBED_MM)) < 0.02, rear.bounds
        rep = joints.make_all(body, a, 30.0, 222.0, f"{td}/mfg/manufacture")
        made = rep["manufactured"]
        for k, v in made.items():
            assert v["closed"] and v["pieces"] == v["pieces_expected"], (k, v)
        mb = trimesh.load(made["machined_body"]["file"], force="mesh")
        sr = trimesh.load(made["printed_support_rear"]["file"], force="mesh")
        # the slot is in the judged body: no foam where the rod is, and foam removed there
        inter = joints._bool("intersection", [mb, sr])
        assert inter is None or inter.is_empty or abs(inter.volume) < 1.0           # mm3
        x = 166.3
        cut = trimesh.creation.box(bounds=[[x - 4, -20, 24.5], [x + 4, 20, 27.5]])
        foam = joints._bool("intersection", [mb, cut])
        assert foam is None or abs(foam.volume) < 0.9 * 8 * 34 * 3.0               # some foam milled away there
