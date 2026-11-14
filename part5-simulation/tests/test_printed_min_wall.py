"""P4.printed_min_wall: the referee MEASURES each printed file's thinnest wall."""
import trimesh

import legality as lg


def _plate(tmp_path, t_mm, name="p.stl"):
    m = trimesh.creation.box(extents=[20.0, 12.0, t_mm])          # mm, like the made files
    p = tmp_path / name
    m.export(str(p))
    return str(p)


def test_measures_a_plate_and_ignores_its_edges(tmp_path):
    t, where = lg._min_wall_mm(_plate(tmp_path, 0.9))
    assert abs(t - 0.9) < 1e-3 and where is not None                 # not 0 at an edge, not 12 or 20


def test_just_inside_and_just_outside_the_print_minimum(tmp_path):
    lim = lg.PRINTED_MIN_WALL_MM
    for t_mm, ok in ((lim + 0.01, True), (lim - lg.WALL_MEASURE_TOL_MM - 0.02, False)):
        t, _ = lg._min_wall_mm(_plate(tmp_path, t_mm))
        assert (t - (lim - lg.WALL_MEASURE_TOL_MM) >= 0) is ok, (t_mm, t)


def test_a_thin_spot_in_a_thick_part_is_found(tmp_path):
    a = trimesh.creation.box(extents=[20.0, 12.0, 4.0])
    notch = trimesh.creation.box(extents=[4.0, 14.0, 3.6])
    notch.apply_translation([0, 0, 0.2 + 0.001])                    # leaves 0.4 mm under it
    m = trimesh.boolean.difference([a, notch], engine="manifold")
    p = tmp_path / "n.stl"
    m.export(str(p))
    t, where = lg._min_wall_mm(str(p), n=20000)
    assert abs(t - 0.4) < 0.01, t
