"""
Tests for sdf.py (moved from test_phi_updater.py; the carving tests went with the carving)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from sdf import reinitialise_sdf, _godunov_gradient, _grad_magnitude
from phi_grid import PhiGrid
from bounding_volumes import BoundingRegion
from geometry_contract import GRID_SPACING_M

def _pass(n): print(f"PASS {n}")
def _fail(n, m): print(f"FAIL {n}: {m}"); sys.exit(1)

def _make_phi(nx=20, ny=20, nz=20):
    bv = BoundingRegion("main_body", (0.0, -0.003, 0.0), (nx, ny, nz))
    solid = np.zeros((nx, ny, nz), dtype=bool)
    air = np.zeros((nx, ny, nz), dtype=bool)
    air[0, :, :] = True; air[-1, :, :] = True
    air[:, 0, :] = True; air[:, -1, :] = True
    air[:, :, 0] = True; air[:, :, -1] = True
    phi = PhiGrid("main_body", bv, np.zeros((nx,ny,nz), dtype=np.float32), solid, air)
    phi.init("sphere")
    return phi

def test_godunov_gradient_returns_array():
    phi = _make_phi()
    g = _godunov_gradient(phi.grid, 0)
    assert g.shape == phi.grid.shape, f"Gradient shape {g.shape} != {phi.grid.shape}"
    _pass("test_godunov_gradient_returns_array")

def test_grad_magnitude_positive():
    phi = _make_phi()
    gm = _grad_magnitude(phi.grid)
    assert np.all(gm >= 0), "Gradient magnitude should be non-negative"
    _pass("test_grad_magnitude_positive")

def test_reinitialise_sdf_runs():
    phi = _make_phi()
    grid_before = phi.grid.copy()
    reinitialise_sdf(phi, n_steps=3, dt_reinit=0.1)
    assert phi.grid.shape == grid_before.shape
    _pass("test_reinitialise_sdf_runs")
