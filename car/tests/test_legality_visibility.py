"""The sight-line rules, on boxes standing in for the car's parts (mm)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for _p in ("body", "race", "cfd", "components"):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / _p))

import trimesh

import legality


def _stl(tmp, name, lo, hi):
    """Parts' half meshes are stored in metres, right half."""
    m = trimesh.creation.box(bounds=[[v / 1e3 for v in lo], [v / 1e3 for v in hi]])
    p = tmp / f"{name}.stl"
    m.export(str(p))
    return {"name": name, "stl": str(p), "rotating": None}


def _assembly(tmp):
    return {"x_front_mm": 50.0, "extra_surfaces": [
        _stl(tmp, "halo", (100, 0, 24), (150, 12.5, 39)),
        _stl(tmp, "wheelF", (35, 20, 0), (65, 36, 30)),
        _stl(tmp, "wheelR", (165, 20, 0), (195, 36, 30)),
        _stl(tmp, "fwing", (20, 16, 6), (28, 38, 9)),
        _stl(tmp, "nose", (0, 0, 8), (40, 10, 20)),
    ]}


def _box(lo, hi):
    return trimesh.creation.box(bounds=[lo, hi])


def test_a_clear_car_passes_every_sight_line(tmp_path):
    r = legality._visibility_checks(_assembly(tmp_path), {"machined_body": _box((40, -18, 5), (200, 18, 23))})
    assert all(v["pass"] for v in r.values()), r
    assert len(r) == 10 and "T8.7_front_wing_clear_air_all_parts" in r and "T4.7_team_number_room" in r


def test_decal_and_team_number_need_room(tmp_path):
    # 10 mm tall: no 15 mm of side for the logo decal. Halo 5 mm behind Ref A: no 8 mm number.
    a = _assembly(tmp_path)
    a["x_front_mm"] = 111.0
    r = legality._visibility_checks(a, {"machined_body": _box((40, -18, 5), (200, 18, 15))})
    assert not r["T4.6_logo_decal_room"]["pass"] and not r["T4.7_team_number_room"]["pass"], r


def test_a_part_within_5_mm_of_the_front_wing_fails_clear_air(tmp_path):
    # The body reaching to 2 mm behind the wing's trailing edge, beside it.
    r = legality._visibility_checks(_assembly(tmp_path), {"machined_body": _box((30, -18, 5), (200, 18, 23))})
    c = r["T8.7_front_wing_clear_air_all_parts"]
    assert not c["pass"] and "machined_body" in c["note"], c


def test_each_sight_line_catches_what_blocks_it(tmp_path):
    a = _assembly(tmp_path)
    cases = {
        "T4.4.2_halo_seen_from_front": _box((80, -5, 30), (95, 5, 36)),
        "T4.4.2_halo_seen_from_side": _box((110, 40, 30), (120, 50, 36)),
        "T4.4.3_halo_seen_from_top": _box((110, -5, 45), (120, 5, 50)),
        "T7.10_wheelF_seen_from_side": _box((45, 40, 5), (55, 50, 25)),
        "T7.11_front_wheel_seen_from_front": _box((10, 25, 22), (20, 32, 28)),
        "T8.8_front_wing_seen_from_front": _box((5, 16, 5), (15, 38, 10)),
    }
    for rule, blocker in cases.items():
        assert not legality._visibility_checks(a, {"thing": blocker})[rule]["pass"], rule


def test_a_hub_behind_the_tread_does_not_hide_the_wheel(tmp_path):
    # Above 20 mm but behind the curve of the wheel; and a support may cover it from the side.
    hub = _box((45, 22, 21), (55, 34, 25))
    r = legality._visibility_checks(_assembly(tmp_path), {"printed_hubcaps_front": hub})
    assert r["T7.11_front_wheel_seen_from_front"]["pass"]
    side = _box((45, 40, 5), (55, 50, 25))
    assert legality._visibility_checks(_assembly(tmp_path), {"printed_hubcaps_front": side})["T7.10_wheelF_seen_from_side"]["pass"]


def test_batched_contains_and_gap_match_the_plain_answers():
    import numpy as np
    box = _box((0, 0, 0), (10, 10, 10))
    pts = np.random.default_rng(0).uniform(-5, 15, (1000, 3))
    assert (legality._contains(box, pts, chunk=70) == box.contains(pts)).all()
    outside = pts[~box.contains(pts)]
    assert abs(legality._nearest_gap_m(box, outside, chunk=70) - box.nearest.on_surface(outside)[1].min()) < 1e-12


def test_the_chamber_wall_is_measured_by_its_volume():
    import trimesh as tm
    # Metres: a body 60 mm long around a 52 mm bore at z = 31, as the machined half is.
    body = tm.creation.box(bounds=[[0.0, 0.0, 0.002], [0.06, 0.03, 0.052]])
    assert legality.t55_wall_fraction(body, rear_face_mm=60.0) > 0.999
    # A flat cut through the outer part of the wall, thin enough to slip between probe points.
    gouge = tm.creation.box(bounds=[[0.02, 0.0, 0.0425], [0.025, 0.03, 0.052]])
    cut = tm.boolean.difference([body, gouge], engine="manifold")
    assert legality.t55_wall_fraction(cut, rear_face_mm=60.0) < 0.999
