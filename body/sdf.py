"""
sdf.py -- signed-distance reinitialisation of the level-set field.

Moved unchanged from phi_updater.py (bible Part 2): the body sizing (param_body),
the machining filter (machining) and grid remapping (unified_phi) redistance the
field after they change it. The Hamilton-Jacobi carving that phi_updater also
held was retired; see docs/HISTORY.md.
"""
from __future__ import annotations

import numpy as np

from geometry_contract import GRID_SPACING_M
from phi_grid import PhiGrid


def _godunov_gradient(phi: np.ndarray, axis: int) -> np.ndarray:
    """
    Compute Godunov upwind gradient magnitude along one axis.

    Returns array of same shape as phi with the Godunov gradient component.
    Interior cells use the Godunov scheme; boundary cells use one-sided differences.
    """
    dx = GRID_SPACING_M
    grad = np.zeros_like(phi, dtype=np.float64)

    # One-sided differences at boundaries
    if axis == 0:
        grad[0] = (phi[1] - phi[0]) / dx
        grad[-1] = (phi[-1] - phi[-2]) / dx
        D_minus = (phi[1:-1] - phi[:-2]) / dx   # shape (nx-2, ny, nz)
        D_plus = (phi[2:] - phi[1:-1]) / dx
    elif axis == 1:
        np.take(phi, 0, axis=1)
        grad_slice_0 = (phi[:, 1, :] - phi[:, 0, :]) / dx if phi.shape[1] > 1 else np.zeros_like(phi[:, 0, :])
        grad_slice_n = (phi[:, -1, :] - phi[:, -2, :]) / dx if phi.shape[1] > 1 else np.zeros_like(phi[:, -1, :])
        grad[:, 0, :] = grad_slice_0
        grad[:, -1, :] = grad_slice_n
        D_minus = (phi[:, 1:-1, :] - phi[:, :-2, :]) / dx
        D_plus = (phi[:, 2:, :] - phi[:, 1:-1, :]) / dx
    elif axis == 2:
        grad[:, :, 0] = (phi[:, :, 1] - phi[:, :, 0]) / dx if phi.shape[2] > 1 else 0.0
        grad[:, :, -1] = (phi[:, :, -1] - phi[:, :, -2]) / dx if phi.shape[2] > 1 else 0.0
        D_minus = (phi[:, :, 1:-1] - phi[:, :, :-2]) / dx
        D_plus = (phi[:, :, 2:] - phi[:, :, 1:-1]) / dx
    else:
        raise ValueError(f"axis must be 0, 1, or 2, got {axis}")

    # Godunov scheme for interior cells
    phi_interior = None
    if axis == 0:
        phi_interior = phi[1:-1]
    elif axis == 1:
        phi_interior = phi[:, 1:-1, :]
    elif axis == 2:
        phi_interior = phi[:, :, 1:-1]

    # phi > 0: G = max(max(D-, 0)^2, min(D+, 0)^2)
    # phi <= 0: G = max(min(D-, 0)^2, max(D+, 0)^2)
    D_minus_sq = D_minus ** 2
    D_plus_sq = D_plus ** 2

    pos_mask = phi_interior > 0
    G = np.where(
        pos_mask,
        np.maximum(np.maximum(D_minus, 0.0) ** 2, np.minimum(D_plus, 0.0) ** 2),
        np.maximum(np.minimum(D_minus, 0.0) ** 2, np.maximum(D_plus, 0.0) ** 2),
    )
    grad_val = np.sqrt(np.maximum(G, 0.0))

    if axis == 0:
        grad[1:-1] = grad_val
    elif axis == 1:
        grad[:, 1:-1, :] = grad_val
    elif axis == 2:
        grad[:, :, 1:-1] = grad_val

    return grad


def _grad_magnitude(phi: np.ndarray) -> np.ndarray:
    """Compute |grad phi| using Godunov scheme on all three axes."""
    gx = _godunov_gradient(phi, 0)
    gy = _godunov_gradient(phi, 1)
    gz = _godunov_gradient(phi, 2)
    return np.sqrt(gx ** 2 + gy ** 2 + gz ** 2)


def reinitialise_sdf(phi: PhiGrid, n_steps: int = 50, dt_reinit: float = None) -> None:
    """
    Reinitialise phi as a signed distance field.
    Solve dphi/dtau + sign(phi)(|grad phi| - 1) = 0 for n_steps pseudo-time steps.
    After reinit: |grad phi| should be ~1.0 everywhere.

    CFL STABILITY: The explicit pseudo-time scheme is conditionally stable.
    The stable time step is dt <= 0.5 * GRID_SPACING_M (CFL number = 0.5).
    dt_reinit=0.3 (the original value) equals ~1000 * GRID_SPACING_M — massively
    unstable; the grid explodes to 10^60 within 5 steps even in float64.

    dt_reinit defaults to 0.4 * GRID_SPACING_M (CFL number = 0.4, safely stable).
    n_steps defaults to 50 to give enough pseudo-time to propagate corrections
    across the grid from the zero level set.

    All computation runs in float64 to prevent float32 overflow in Godunov
    squared-difference terms. Result is cast back to float32 for storage.
    """
    if dt_reinit is None:
        dt_reinit = 0.4 * GRID_SPACING_M  # CFL-stable: 0.4 * dx

    # Work entirely in float64
    grid_f64 = phi.grid.astype(np.float64)

    # SMOOTHED sign, not np.sign. This is what stops redistancing from eating
    # the car.
    #
    # np.sign is discontinuous at the interface, so the cells that straddle
    # phi=0 -- exactly the ones that define where the surface IS -- get driven
    # by a full-magnitude +1 or -1 depending on which side of zero they land.
    # The zero level set drifts, and it drifts inward. Measured before this
    # change, at 1 mm spacing on a real car:
    #     reinit on the as-built field      -8.43 g
    #     reinit AGAIN on the result        -8.35 g   <- not converging
    #     reinit on a post-hj field         -2.38 g
    # A correct redistancing is idempotent: applied to a field that is already
    # a distance function it should change nothing. This one removed another
    # 8.35 g every time it was called.
    #
    # It mattered enormously, because apply_adjoint_to_unified redistances every
    # iteration. Of one full production step's mass loss, the redistancing
    # accounted for 68% at 1 mm and 90% at 2 mm -- so most of what looked like
    # the optimiser carving the car was numerical dissipation, and the T3.6 mass
    # barrier could never hold the floor because erosion outran its restoring
    # force (it settled 7.4 g under, at 40.5 g against an equilibrium of 47.9).
    #
    # phi / sqrt(phi^2 + dx^2) is the standard smoothing (Peng et al. 1999): it
    # tends to +/-1 away from the interface, where the sign is unambiguous, and
    # to 0 AT the interface, where it should not push at all. |grad phi| -> 1
    # just as before; the surface simply stops moving while it happens.
    eps = GRID_SPACING_M
    for _ in range(n_steps):
        grad_mag = _grad_magnitude(grid_f64)
        sign_phi = grid_f64 / np.sqrt(grid_f64 * grid_f64 + eps * eps)
        grid_f64 = grid_f64 - dt_reinit * sign_phi * (grad_mag - 1.0)

        # Clamp to prevent runaway in cells far from the zero level set.
        # SDF values should never exceed the grid diagonal in metres.
        max_sdf = 2.0 * max(phi.bv.shape) * GRID_SPACING_M
        grid_f64 = np.clip(grid_f64, -max_sdf, max_sdf)

        # Re-enforce hard constraints in float64 space each step.
        grid_f64[phi.hard_mask_solid] = np.minimum(
            grid_f64[phi.hard_mask_solid], -GRID_SPACING_M
        )
        grid_f64[phi.hard_mask_air] = np.maximum(
            grid_f64[phi.hard_mask_air], +GRID_SPACING_M
        )

    phi.grid = grid_f64.astype(np.float32)
    phi.apply_hard_constraints()
