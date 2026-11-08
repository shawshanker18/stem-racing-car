import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import param_body as pb

X0, XR = 46.0, 192.0


def _grid():
    x = np.arange(40.0, 200.0, 2.0)
    y = np.arange(-30.0, 30.0, 2.0)
    z = np.arange(0.0, 60.0, 1.0)
    return np.meshgrid(x, y, z, indexing="ij")


def _inside(bp):
    X, Y, Z = _grid()
    return pb.phi_mm(bp, X, Y, Z, X0, XR) < 0


def test_tunnel_off_by_default_and_old_records_load():
    assert pb.BodyParams().ft_h == 0.0
    d = pb.BodyParams().as_dict()
    for k in ("ft_h", "ft_w", "ft_x0", "ft_x1", "ft_ramp"):
        d.pop(k)
    assert pb.BodyParams.from_dict(d) == pb.BodyParams()


def test_tunnel_only_removes_material_under_the_floor_between_its_ends():
    X, Y, Z = _grid()
    base = _inside(pb.BodyParams())
    bp = replace(pb.BodyParams(), ft_h=6.0, ft_w=8.0, ft_x0=60.0, ft_x1=160.0, ft_ramp=20.0)
    cut = _inside(bp)
    assert not (cut & ~base).any()                      # never adds material
    removed = base & ~cut
    assert removed.any()
    assert (np.abs(Y[removed]) <= 8.0 + 1e-9).all()
    assert (X[removed] >= 60.0).all() and (X[removed] <= 160.0).all()
    _, _, zb = pb._fuselage(bp, X, X0, XR)
    assert (Z[removed] <= zb[removed] + 6.0 + 1e-9).all()


def test_tunnel_bounds_respect_the_cutter():
    lo, hi = pb.BOUNDS["ft_w"]
    assert 2 * lo >= 6.25 - 1e-9


def test_a_tunnel_keeps_its_height_at_any_skin():
    import numpy as np
    x, y = np.array([110.0]), np.array([5.0])
    for skin in (0.0, 2.0, 4.0):
        bp = pb.BodyParams(ft_h=3.0)
        _, _, zb = pb._fuselage(bp, x, 30.0, 222.0)
        floor = float(zb[0]) - skin
        at = lambda z: float(pb.phi_mm(bp, x, y, np.array([z]), 30.0, 222.0, skin_mm=skin)[0])
        assert at(floor + 2.0) > 0, f"inside the tunnel at skin {skin}"
        assert at(floor + 4.0) < 0, f"foam above the tunnel at skin {skin}"


def test_close_pinches_fills_an_edge_only_contact():
    from types import SimpleNamespace
    grid = np.full((4, 4, 3), 1e-3, dtype=np.float32)
    grid[1, 1, :] = grid[2, 2, :] = -1e-3            # two columns touching only along an edge
    g = SimpleNamespace(phi=SimpleNamespace(grid=grid, hard_mask_air=np.zeros(grid.shape, bool)))
    assert pb._close_pinches(g, 1e-3) > 0
    S = g.phi.grid < 0
    assert S[2, 1, :].all() or S[1, 2, :].all()
    assert pb._close_pinches(g, 1e-3) == 0            # nothing left to fill
