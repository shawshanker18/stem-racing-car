"""A carving-loop timing must never run on the medium (or coarse) mesh, and no timing may pick a mesh by default."""
import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "part3-simulation" / "checks"))
sys.path.insert(0, str(ROOT / "part5-simulation"))


def _cm(monkeypatch, res, loop):
    monkeypatch.setenv("P3_RES", res)
    if loop:
        monkeypatch.setenv("P5_LOOP", "1")
    else:
        monkeypatch.delenv("P5_LOOP", raising=False)
    import car_modes
    return importlib.reload(car_modes)


@pytest.mark.parametrize("res", ["", "coarse", "medium"])
def test_loop_timing_refuses_low_mesh(monkeypatch, res):
    with pytest.raises(SystemExit):
        _cm(monkeypatch, res, True).mesh()


@pytest.mark.parametrize("res", ["fine", "resolved"])
def test_loop_timing_allows_high_mesh(monkeypatch, res):
    assert _cm(monkeypatch, res, True).mesh() == res


def test_no_default_mesh(monkeypatch):
    with pytest.raises(SystemExit):
        _cm(monkeypatch, "", False).mesh()


@pytest.mark.parametrize("res", ["", "medium"])
def test_solver_eval_refuses_low_mesh(monkeypatch, tmp_path, res):
    monkeypatch.setenv("P5_RES", res)
    import solver
    monkeypatch.setattr(solver, "BATCH", tmp_path / "b.json")
    (tmp_path / "b.json").write_text('{"cases": [{"id": 0, "params": {}}]}')
    with pytest.raises(SystemExit):
        solver.evaluate(0, tmp_path)


def test_modes_and_steps_go_through_carve(monkeypatch, tmp_path):
    """car_modes' m and s items are carve.carve with the mode bumps: the same field, byte for byte."""
    import hashlib
    import json
    import numpy as np
    sys.path.insert(0, str(ROOT / "part1-simulation"))
    monkeypatch.setenv("P3_SPACING_MM", "2.0")
    (tmp_path / "steps.json").write_text(json.dumps({"s0": [[0, -0.5], [3, 0.5]]}))
    monkeypatch.setenv("P5_STEPS", str(tmp_path / "steps.json"))
    cm = _cm(monkeypatch, "fine", True)
    import carve
    h, V, N = cm.surface(cm.block())
    C, a, r = cm.centres(V, N) * 1e3, cm.A_M * 1e3, cm.R_M * 1e3
    sha = lambda x: hashlib.sha256(np.ascontiguousarray(np.asarray(x, np.float32)).tobytes()).hexdigest()
    want = {"m3-": [{"c_mm": list(C[3]), "amp_mm": -a, "sigma_mm": r}],
            "s0": [{"c_mm": list(C[0]), "amp_mm": -0.5 * a, "sigma_mm": r},
                   {"c_mm": list(C[3]), "amp_mm": 0.5 * a, "sigma_mm": r}]}
    for item, bumps in want.items():
        g, rep = carve.carve(cm.LAYOUT, [{"bumps": bumps, "unit": False}], spacing_mm=2.0)
        assert rep[0]["status"] == "ok"
        assert sha(cm.field(item)) == sha(g.phi.grid)


def test_more_modes_keep_the_old_ones(monkeypatch):
    """Raising NMODES 60 -> 96 appends centres: modes 0-59 are byte-identical before and after,
    on the plain block and on a body carved through carve.carve."""
    import numpy as np
    sys.path.insert(0, str(ROOT / "part1-simulation"))
    monkeypatch.setenv("P3_SPACING_MM", "2.0")
    cm = _cm(monkeypatch, "fine", False)
    import carve
    carved, rep = carve.carve(cm.LAYOUT, [{"bias_mm": -0.5, "bumps": [{"u": [0.4, 0.8, 0.6], "amp_mm": 2.0,
                                                                       "sigma_mm": 10.0}]}], spacing_mm=2.0)
    assert rep[0]["status"] == "ok"
    for g in (cm.block(), carved):
        _, V, N = cm.surface(g)
        out = {}
        for n in (60, 96):
            monkeypatch.setenv("P3_NMODES", str(n))
            out[n] = _cm(monkeypatch, "fine", False).centres(V, N)
        assert out[60].shape == (60, 3) and out[96].shape == (96, 3)
        assert np.ascontiguousarray(out[96][:60]).tobytes() == np.ascontiguousarray(out[60]).tobytes()
