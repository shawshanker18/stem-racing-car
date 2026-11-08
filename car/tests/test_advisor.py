"""Part 5 checks: legality engine, recommendations, and a no-CFD run of the whole chain."""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import paths  # noqa: E402,F401


def _box_car(td):
    import trimesh
    b = trimesh.creation.box(extents=[0.19, 0.056, 0.042])
    b.apply_translation([0.030 + 0.095, 0.0, 0.0025 + 0.021])
    half = trimesh.intersections.slice_mesh_plane(b, [0, 1, 0], [0, 0, 0], cap=True)
    half.export(f"{td}/body.stl", file_type="stl_ascii")
    return f"{td}/body.stl"


def test_legality_measures_width_height_overhang_and_block():
    import assembly
    import legality
    with tempfile.TemporaryDirectory() as td:
        body = _box_car(td)
        a = assembly.build(120.3, 46.0, 43.72, body, f"{td}/asm")
        r = legality.check(body, a, {"competition_mass_g": 48.2, "ballast_g": 3.0,
                                     "capacity_g": 15.8}, field_bodies=1)
        assert r["T3.4_width_min"]["pass"] and r["T3.5_height"]["pass"]
        assert abs(float(r["block_length"]["note"].split()[0]) - 190.0) < 0.5
        assert r["block_width"]["pass"] and r["T4.1_single_body"]["pass"]
        assert r["T3.6_mass"]["margin"] > 0
        # The v2 rear-support CAD bottoms at 1.40 mm; Part 4 trims it to 1.51.
        assert r["T3.7_clearance"]["pass"]
        r2 = legality.check(body, a, {"competition_mass_g": 47.8, "ballast_g": 15.8,
                                      "capacity_g": 15.8}, field_bodies=2)
        assert not r2["T3.6_mass"]["pass"] and not r2["T4.1_single_body"]["pass"]


def test_t55_probe_sees_a_missing_wall():
    import math
    import numpy as np
    import trimesh
    import legality
    solid = trimesh.creation.box(extents=[0.06, 0.04, 0.04])
    solid.apply_translation([0.19, 0.0, 0.035])
    half = trimesh.intersections.slice_mesh_plane(solid, [0, 1, 0], [0, 0, 0], cap=True)
    assert legality.t55_wall_fraction(half, rear_face_mm=220.0) > 0.999
    thin = trimesh.creation.box(extents=[0.06, 0.021, 0.04])      # 10.5 mm half-width
    thin.apply_translation([0.19, 0.0, 0.035])
    half2 = trimesh.intersections.slice_mesh_plane(thin, [0, 1, 0], [0, 0, 0], cap=True)
    assert legality.t55_wall_fraction(half2, rear_face_mm=220.0) < 0.95


def test_recommendations_follow_the_numbers():
    import run_car
    legal = {"T3.7_clearance": {"pass": False, "margin": -0.1, "note": ""}}
    cfd = {"D20_N": 0.40, "converged": True, "rates": {"ms_per_mN_drag": 0.45}, "launch_margin_N": -0.2,
           "parts": {"wheelF": {"D_N": 0.14}, "wheelR": {"D_N": 0.14}, "car": {"D_N": 0.07},
                     "fwing": {"D_N": 0.05}}}
    rec = run_car.recommend(legal, cfd)
    assert rec[0].startswith("FIX LEGALITY FIRST") and "T3.7" in rec[0]
    assert "Wheels carry 70 %" in " ".join(rec)
    assert "A wheel lifts at launch" in " ".join(rec)


def test_race_from_the_pipeline_bindings():
    """make_car + race on a made-up CFD result and mass report: the wiring between the
    pipeline, inputs/measured.json and race/race_model.py."""
    import pipeline
    b = pipeline.bindings(None, {}, tempfile.mkdtemp())
    cfd = pipeline.CFDOutcome(D20=0.41, L=0.0, Cm=0.0, A=0.001, converged=True, residual_final=1e-4, My=0.0)
    mass = pipeline.MassReport(total_mass_kg=0.06935, com_x_m=0.12, com_y_m=0.0, com_z_m=0.030,
                               propellant_mass_kg=0.008, propellant_com=(0.21, 0.0, 0.031))
    asm = {"wheel_design": {"front": {"I_gmm2": 123.2, "R_mm": 14.12}, "rear": {"I_gmm2": 150.4, "R_mm": 14.12}}}
    car = b.make_car(cfd, mass, 0.0482, asm, 46.0, 120.3)
    r = b.race(car)
    assert 1.4 < r.time_s < 1.7                      # synthetic thrust curve until Part 3 replaces it
    assert "mu_roll" in b.unmeasured and "thrust_csv" in b.unmeasured


def test_whole_chain_without_cfd():
    import run_car
    with tempfile.TemporaryDirectory() as td:
        S = run_car.main(["--out", td, "--cfd-mm", "2.0", "--skin-mm", "1.0"])
        assert (Path(td) / "report.md").exists() and (Path(td) / "summary.json").exists()
        assert S["legality"]["summary"]["n_checks"] > 40
        assert S["legality"]["checks"]["manufacture_files_are_solids"]["pass"]
        assert 35.0 < S["mass"]["manufactured_mass_g"] < 60.0     # a fixed skin, not sized
        assert len(json.loads((Path(td) / "parts" / "assembly.json").read_text())
                   ["extra_surfaces"]) == 8                       # + the printed nose



