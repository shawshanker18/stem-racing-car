"""Mesh morphing (noise fix 3) without OpenFOAM: moveMesh and foamFormatConvert are faked."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import openfoam_case as oc

HEAD = "FoamFile\n{\n    version 2.0;\n    format ascii;\n}\n// comment (1 2 3)\n"


def _plate_stl(path, z):
    v = [(0, 0, z), (1, 0, z), (1, 1, z), (0, 1, z)]
    tri = [(v[0], v[1], v[2]), (v[0], v[2], v[3])]
    path.write_text("solid car\n" + "".join(
        "facet normal 0 0 1\nouter loop\n" + "".join(f"vertex {a} {b} {c}\n" for a, b, c in t)
        + "endloop\nendfacet\n" for t in tri) + "endsolid car\n")


def _ref_case(tmp_path):
    """A 6-point mesh whose `car` patch is faces 1-2 (points 1,2,3,4,5 in that order)."""
    ref = tmp_path / "ref"
    pm = ref / "constant" / "polyMesh"
    pts = [(9, 9, 9), (0.2, 0.0, 0.0001), (0.4, 0.3, 0), (0.6, 0.6, 0), (0.8, 0.2, 0), (0.5, 0.5, 0)]
    oc._write(pm / "points", HEAD + f"{len(pts)}\n(\n" + "".join(f"({x} {y} {z})\n" for x, y, z in pts) + ")\n")
    oc._write(pm / "faces", HEAD + "3\n(\n3(0 1 2)\n4(1 2 3 4)\n3(4 5 1)\n)\n")
    oc._write(pm / "boundary", HEAD + "2\n(\n    inlet\n    {\n        type patch;\n        nFaces 1;\n"
              "        startFace 0;\n    }\n    car\n    {\n        type wall;\n        nFaces 2;\n"
              "        startFace 1;\n    }\n)\n")
    for f in ("owner", "neighbour"):
        oc._write(pm / f, HEAD + "0\n(\n)\n")
    (ref / "constant" / "triSurface").mkdir(parents=True)
    _plate_stl(ref / "constant" / "triSurface" / "car.stl", 0.0)
    return ref


def test_ascii_readers_and_patch_point_order(tmp_path):
    ref = _ref_case(tmp_path)
    pm = ref / "constant" / "polyMesh"
    pts = oc.read_ascii_points((pm / "points").read_text())
    faces = oc.read_ascii_faces((pm / "faces").read_text())
    assert pts.shape == (6, 3) and faces == [[0, 1, 2], [1, 2, 3, 4], [4, 5, 1]]
    assert oc.patch_range((pm / "boundary").read_text(), "car") == (1, 2)
    assert oc.patch_mesh_points(faces, 1, 2) == [1, 2, 3, 4, 5]          # first-appearance order


def test_points_move_by_the_change_of_the_surface_only(tmp_path):
    ref = _ref_case(tmp_path)
    _plate_stl(tmp_path / "same.stl", 0.0)
    _plate_stl(tmp_path / "up.stl", 0.002)
    pts = np.array([[0.2, 0.0, 0.0001], [0.5, 0.5, 0.0]])       # one point a little off the surface
    ref_stl = str(ref / "constant" / "triSurface" / "car.stl")
    assert np.allclose(oc.surface_change(pts, ref_stl, str(tmp_path / "same.stl")), 0)   # no change: no move
    d = oc.surface_change(pts, ref_stl, str(tmp_path / "up.stl"))
    assert np.allclose(d, [[0, 0, 0.002], [0, 0, 0.002]])        # exactly the change, even off-surface


def test_morph_writes_the_displacement_and_restores_the_case(tmp_path, monkeypatch):
    ref = _ref_case(tmp_path)
    cfg = oc.OpenFOAMRunConfig(max_iterations=1000, morph_from=str(ref))
    run = tmp_path / "run"
    oc._write(run / "system" / "controlDict", oc.build_control_dict(cfg, 1e-3))
    oc._write(run / "system" / "fvSolution", oc._FV_SOLUTION)
    (run / "constant" / "triSurface").mkdir(parents=True)
    _plate_stl(run / "constant" / "triSurface" / "car.stl", 0.001)
    control0 = (run / "system" / "controlDict").read_text()
    seen = []

    def fake_run(cmd, cwd, bashrc, log, timeout):
        seen.append((cmd, (cwd / "system" / "controlDict").read_text()))
        if cmd.startswith("moveMesh"):
            pd = (cwd / "0" / "pointDisplacement").read_text()
            seen.append(("pd", pd))
            oc._write(cwd / str(oc.MORPH_STEPS) / "polyMesh" / "points", "moved points")
        return ""

    monkeypatch.setattr(oc, "_run", fake_run)
    oc._morph(run, cfg, "bashrc", 60)
    cmds = [c for c, _ in seen]
    assert cmds == ["foamFormatConvert -constant -noFunctionObjects", "moveMesh -noFunctionObjects", "pd"]
    assert "writeFormat     ascii;" in seen[0][1] and "writePrecision  16;" in seen[0][1]
    pd = dict(seen)["pd"]
    assert "type            fixedValue;" in pd and "nonuniform List<vector> 5" in pd
    assert pd.count("1.000000000e-03)") == 5                    # every car point up by 1 mm
    assert (run / "constant" / "polyMesh" / "points").read_text() == "moved points"
    assert (run / "system" / "controlDict").read_text() == control0
    assert "points 5" in (run / "logs" / "morph_displacement.txt").read_text()
    assert not (run / str(oc.MORPH_STEPS)).exists() and not (run / "0" / "pointDisplacement").exists()


def test_morph_without_a_reference_mesh_fails_loudly(tmp_path):
    cfg = oc.OpenFOAMRunConfig(morph_from=str(tmp_path / "nowhere"))
    with pytest.raises(FileNotFoundError):
        oc._morph(tmp_path / "run", cfg, "bashrc", 60)



def test_snapping_is_unchanged_without_morph(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(oc, "_run", lambda cmd, *a: calls.append(cmd) or "")
    oc._mesh(tmp_path, oc.OpenFOAMRunConfig(), "bashrc", 60)
    assert calls == ["snappyHexMesh -overwrite", "checkMesh"]


def test_warm_start_maps_the_reference_field_after_meshing(tmp_path, monkeypatch):
    ref = tmp_path / "ref"
    oc._write(ref / "system" / "controlDict", "x")
    calls = []
    monkeypatch.setattr(oc, "_run", lambda cmd, *a: calls.append(cmd) or "")
    oc._mesh(tmp_path / "run", oc.OpenFOAMRunConfig(warm_from=str(ref)), "bashrc", 60)
    assert calls == ["snappyHexMesh -overwrite",
                     f"mapFields '{ref}' -sourceTime latestTime -consistent", "checkMesh"]


def test_warm_start_without_a_case_fails_loudly(tmp_path, monkeypatch):
    monkeypatch.setattr(oc, "_run", lambda cmd, *a: "")
    with pytest.raises(FileNotFoundError):
        oc._mesh(tmp_path, oc.OpenFOAMRunConfig(warm_from=str(tmp_path / "nope")), "bashrc", 60)



def _mesh_with(tmp_path, monkeypatch, check_text):
    calls = []
    monkeypatch.setattr(oc, "_morph", lambda *a: calls.append("morph"))
    def fake_run(cmd, cwd, bashrc, log, timeout):
        calls.append(cmd)
        return check_text if log == "checkMesh_morph.log" else "Mesh OK."
    monkeypatch.setattr(oc, "_run", fake_run)
    oc._mesh(tmp_path, oc.OpenFOAMRunConfig(morph_from=str(tmp_path / "ref")), "bashrc", 60)
    return calls


def test_a_good_reshape_is_kept(tmp_path, monkeypatch):
    calls = _mesh_with(tmp_path, monkeypatch, "Mesh OK.")
    assert calls == ["morph", "checkMesh", "checkMesh"] and not (tmp_path / "MORPH_FALLBACK").exists()


def test_a_bad_reshape_falls_back_to_a_fresh_mesh_and_says_so(tmp_path, monkeypatch):
    calls = _mesh_with(tmp_path, monkeypatch,
                       " ***Error in face pyramids: 1 faces are incorrectly oriented.\nFailed 1 mesh checks.\n")
    assert calls == ["morph", "checkMesh", "blockMesh", "snappyHexMesh -overwrite", "checkMesh"]
    assert "incorrectly oriented" in (tmp_path / "MORPH_FALLBACK").read_text()


def test_smoothing_removes_a_point_jump_but_keeps_a_smooth_change():
    rng = np.random.default_rng(0)
    pts = np.c_[rng.uniform(0, 0.02, 4000), rng.uniform(0, 0.02, 4000), np.zeros(4000)]
    smooth = np.c_[np.zeros(4000), np.zeros(4000), 1e-3 * np.exp(-np.sum((pts - 0.01) ** 2, 1) / (2 * 0.008 ** 2))]
    spiky = smooth.copy()
    spiky[0, 2] += 5e-4                                            # one point jumps 0.5 mm
    out = oc.smooth_displacement(pts, spiky, oc.MORPH_SMOOTH_M)
    assert abs(out[0, 2] - smooth[0, 2]) < 0.3 * 5e-4              # the jump is mostly gone
    inner = np.all((pts[:, :2] > 0.002) & (pts[:, :2] < 0.018), axis=1)
    assert np.abs(oc.smooth_displacement(pts, smooth, oc.MORPH_SMOOTH_M) - smooth)[inner, 2].max() < 3e-5   # < 3 % of a 1 mm cut
    assert oc.largest_jumps(pts, spiky, 1)[0][0] > 10 * oc.largest_jumps(pts, smooth, 1)[0][0]


def test_remesh_rule_tolerates_a_few_skewed_faces_but_never_inverted_ones():
    ok = oc.morph_mesh_acceptable
    assert ok("...\nMesh OK.\n")
    skew = (" ***Max skewness = 5.7316611, 1 highly skew faces detected which may impair the quality"
            " of the results\n  <<Writing 1 skew faces to set skewFaces\nFailed 1 mesh checks.\n")
    assert ok(skew)
    assert not ok(skew.replace("5.7316611", "9.1"))                          # too skewed
    assert not ok(skew.replace(", 1 highly", ", 40 highly"))                 # too many
    assert not ok(" ***Error in face pyramids: 1 faces are incorrectly oriented.\nFailed 1 mesh checks.\n")
    assert not ok(skew + " ***Zero or negative cell volume detected.\nFailed 2 mesh checks.\n")
