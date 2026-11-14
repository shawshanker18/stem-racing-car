"""The 3.0 mm machined wall (team limit, 2026-11-14): thin_wall_mask finds a 2.9 mm wall
wherever it sits on the grid, passes a 3.0 mm one, does not call a convex edge a wall, and a
carve never leaves a new wall under 3.0 mm."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pytest

D = 1e-3                                   # 1 mm cells, metres


def _slab(t_mm, z0_mm):
    z = (np.arange(24) + 0.5) * D
    c = (z0_mm + t_mm / 2.0) * 1e-3
    phi = np.abs(z - c) - t_mm * 1e-3 / 2.0
    return np.broadcast_to(phi, (8, 8, 24)).copy()


@pytest.mark.parametrize("z0", [5.0, 5.25, 5.5, 5.75])
def test_wall_29_fails_30_passes(z0):
    from phi_updater import thin_wall_mask
    assert thin_wall_mask(_slab(2.9, z0), D, 3.0e-3).any()
    assert not thin_wall_mask(_slab(3.0, z0), D, 3.0e-3).any()
    assert not thin_wall_mask(_slab(6.0, z0), D, 3.0e-3).any()


def test_oblique_wall():
    """A 2.9 mm wall at 30 deg to the grid is still found; a 3.2 mm one is not."""
    from phi_updater import thin_wall_mask
    X, Y, Z = np.meshgrid(*[(np.arange(30) + 0.5) * D] * 3, indexing="ij")
    nrm = np.array([0.0, np.sin(np.radians(30)), np.cos(np.radians(30))])
    s = X * nrm[0] + Y * nrm[1] + Z * nrm[2] - 15e-3
    for t, want in ((2.9, True), (3.2, False)):
        assert thin_wall_mask(np.abs(s) - t * 1e-3 / 2, D, 3.0e-3).any() == want


def test_convex_edge_is_not_a_wall():
    from phi_updater import thin_wall_mask
    X, Y, Z = np.meshgrid(*[(np.arange(20) + 0.5) * D] * 3, indexing="ij")
    phi = np.maximum(Y - 10e-3, Z - 10e-3)              # solid where y < 10 and z < 10 mm
    out = np.hypot(np.maximum(Y - 10e-3, 0), np.maximum(Z - 10e-3, 0))
    phi = np.where(phi > 0, out, phi)
    assert not thin_wall_mask(phi, D, 3.0e-3).any()


def test_carve_leaves_no_new_thin_wall():
    """Hard thinning through carve.carve (2 mm grid): no wall under 3.0 mm that the start
    block did not already have."""
    import carve
    import cutter
    from geometry_contract import GRID_SPACING_M
    from phi_updater import thin_wall_mask
    lay = {"W": 120.3, "x_front": 46.0, "d_halo": 43.72}
    g0 = cutter.start_block(lay, spacing_mm=2.0)
    t0 = thin_wall_mask(g0.phi.grid, GRID_SPACING_M, 3.0e-3)
    g, reps = carve.carve(lay, [{"bias_mm": -2.5, "trust_mm": 2.0}] * 4, spacing_mm=2.0)
    assert not (thin_wall_mask(g.phi.grid, GRID_SPACING_M, 3.0e-3) & ~t0).any()
    assert all(r["status"] == "ok" or r["reason"] == "min_wall" for r in reps), reps


def test_finished_body_reports_and_gates_its_wall(tmp_path):
    """cutter.finish measures the sized, milled body's thinnest wall and refuses it under
    3.0 mm; sizing never searched a skin below the wall-legal one."""
    import carve
    import cutter
    lay = {"W": 120.3, "x_front": 46.0, "d_halo": 43.72}
    g, _ = carve.carve(lay, [{"bias_mm": -1.5, "trust_mm": 2.0}], spacing_mm=2.0)
    res = cutter.finish(g, lay, target_body_g=50.0, out_dir=tmp_path)
    w = res["min_machined_wall_mm"]
    assert w is not None
    assert (res["status"] != "ok") or w >= 3.0, res
    if res["status"] == "refused" and res["reason"].startswith("min_wall"):
        assert w < 3.0
    tried = res["report"]["sizing_tried"]
    assert min(t[0] for t in tried) >= res["report"]["skin_lo_mm"] - 1e-9
