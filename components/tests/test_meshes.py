"""Final meshes and the nose mass rollup."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for _p in ("body", "race", "cfd"):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / _p))

import numpy as np
import trimesh


def test_remesh_gives_even_triangles_on_the_same_closed_solid(tmp_path):
    import mesh_fairing
    box = trimesh.creation.box(extents=(100.0, 20.0, 10.0))       # 12 very long triangles
    p = tmp_path / "part.stl"
    box.export(str(p))
    rep = mesh_fairing.remesh_file(p, 2.0)
    out = trimesh.load(str(p), force="mesh")
    assert rep["remeshed"] and rep["closed"] and rep["pieces"] == 1 and out.is_watertight
    assert rep["max_edge_mm"] < 8.0 and rep["faces"] > 1000
    assert abs(abs(out.volume) - abs(box.volume)) < 0.002 * abs(box.volume)
    assert np.allclose(out.bounds, box.bounds, atol=0.06)


def test_solid_nose_weighs_its_volume():
    import nose as ns
    cone = trimesh.creation.cone(radius=0.012, height=0.03)
    solid = ns.NoseCone(wall_mm=99.0, material="PA12")
    m, _ = ns.nose_mass_com(solid, cone)
    assert abs(m - abs(cone.volume) * 1010.0) < 1e-9              # PA12, 1.01 g/cm3
    shell, _ = ns.nose_mass_com(ns.NoseCone(wall_mm=0.8, material="PA12"), cone)
    assert shell < m


def test_a_solid_touching_itself_along_a_line_is_written_closed(tmp_path):
    import joints
    # 1 m units in, as the joints work: two cubes (mm size) sharing exactly one edge.
    a = trimesh.creation.box(bounds=[[0, 0, 0], [0.01, 0.01, 0.01]])
    b = trimesh.creation.box(bounds=[[0.01, 0.01, 0], [0.02, 0.02, 0.01]])
    two = trimesh.util.concatenate([a, b])
    rep = joints._export_mm(two, tmp_path / "pinch.stl")
    out = trimesh.load(str(tmp_path / "pinch.stl"), force="mesh")
    assert rep["closed"] and out.is_volume
    assert abs(rep["file_cm3"] - 2.0) < 0.01          # the bridge adds next to nothing


def test_a_sealed_void_is_not_a_part():
    import trimesh
    import joints
    box = lambda a, b: trimesh.creation.box(bounds=[[a, a, a], [b, b, b]])
    hollow = trimesh.boolean.difference([box(0.0, 10.0), box(4.0, 6.0)], engine="manifold")
    apart = box(20.0, 21.0)
    shells = joints._solid_shells(trimesh.util.concatenate([hollow, apart]))
    assert [round(float(s.volume)) for s in shells] == [1000, 1]


def test_the_remesh_leaves_no_edge_over_the_limit(tmp_path):
    import numpy as np
    import mesh_fairing
    # A long thin bar: a coarse target keeps edges of 30 mm along it.
    bar = trimesh.creation.box(bounds=[[0, 0, 0], [60, 4, 4]])
    bar.export(str(tmp_path / "bar.stl"))
    rep = mesh_fairing.remesh_file(tmp_path / "bar.stl", 30.0, max_edge_mm=8.0)
    out = trimesh.load(str(tmp_path / "bar.stl"), force="mesh")
    assert rep["remeshed"] and out.is_volume and abs(out.volume - 960.0) < 1.0
    assert out.edges_unique_length.max() <= 8.0 and rep["max_edge_mm"] <= 8.0


def test_a_sealed_void_is_filled_into_one_solid():
    import joints
    box = lambda a, b: trimesh.creation.box(bounds=[[a, a, a], [b, b, b]])
    hollow = trimesh.boolean.difference([box(0.0, 10.0), box(2.0, 8.0)], engine="manifold")
    assert abs(hollow.volume - 784.0) < 1e-6
    full = joints._fill_voids(hollow)
    assert full.is_volume and abs(full.volume - 1000.0) < 1e-6
    assert len(full.split(only_watertight=False)) == 1
    assert joints._fill_voids(box(0.0, 1.0)).volume == 1.0
