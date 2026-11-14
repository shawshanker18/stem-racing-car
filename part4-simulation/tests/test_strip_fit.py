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
        assert (g["fit_rear_floor_rod_embed"] >= -1e-6) is ok, floor     # the gate's own pass rule (_entry)


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
        assert all(m >= 0 for k, m in g.items() if k.startswith("fit_")), {k: m for k, m in g.items() if k.startswith("fit_") and m < 0}


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


def test_low_floor_with_a_thick_plate_drops_the_strip_not_into_a_rod():
    # cars 50105/0 ... 50322/0 (aade33c): a low floor, but the plate too thick for the strip
    # to fit under it; the rod went to the track (0.87 mm below it, 14.7 mm from the axle)
    out, g = _build(12.0, top_mm=27.0, bs=bsm.BeamSupport(beam_h_mm=6.0))   # strip at 14.5 cannot fit under a 6 mm plate
    assert out["_pod"] and not out["_floor_high"]
    assert "strip_dropped_note" in out["_struct"]
    _common(out, g)
    v = out["support"].vertices * 1e3
    assert v[:, 2].min() >= 1.5                                           # T3.7
    assert all(m >= 0 for k, m in g.items() if k.startswith("fit_")), {k: m for k, m in g.items() if k.startswith("fit_") and m < 0}


@pytest.mark.parametrize("floor_mm", [6.0, 9.4, 13.8, 20.0])
def test_held_design_never_flips_for_a_small_skin_change(floor_mm):
    # sizing moves the body's skin ~0.1 mm per pass; the design chosen on the first build
    # is held, so a +-0.2 mm floor change cannot flip it (start car: +0.5 <-> +3.5 g per pass)
    first, _ = _build(floor_mm)
    mode = first["support_mode"]
    for d in (-0.2, 0.2):
        body = trimesh.creation.box(bounds=[[0.030, 0.0, (floor_mm + d) / 1e3], [0.222, 0.016, 0.040]])
        bs = bsm.BeamSupport()
        ch = bsm.pod_channel(bs, body, X, Z, R)
        _, hub = wh.hub_span_mm()
        out = bsm.build(bs, X, Z, Y_IN, W, True, hub_mm=hub, R_mm=R, channel=ch, mode=mode)
        assert out["support_mode"] == mode, (floor_mm, d, mode, out["support_mode"])


def test_a_held_design_that_no_longer_fits_is_refused_by_name():
    out, _ = _build(5.0)
    assert out["support_mode"] in ("pod_strip", "pod_plate")
    body = trimesh.creation.box(bounds=[[0.030, 0.0, 0.0245], [0.222, 0.016, 0.040]])   # floor 24.5
    bs = bsm.BeamSupport()
    _, hub = wh.hub_span_mm()
    held = bsm.build(bs, X, Z, Y_IN, W, True, hub_mm=hub, R_mm=R,
                     channel=bsm.pod_channel(bs, body, X, Z, R), mode="pod_strip")
    g = bsm.gates(bs, held, X, Z, R, "rear")
    assert held["support_mode"] == "pod_strip"                            # not silently switched
    assert g["fit_rear_strip_under_plate_on_disc"] < 0                     # refused, with its reason
