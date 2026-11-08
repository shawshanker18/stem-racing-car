"""
reach_test.py -- how much of the shape space can the body settings reach?

The solver can only find a car the settings can describe. This fits the settings
to target surfaces they were not designed around and reports how far off the best
fit stays. A target that fits to a fraction of a millimetre is inside the family.

    python checks/reach_test.py --stl some_body_half.stl   # a real body, metres
    python checks/reach_test.py --random 5                 # smooth shapes unlike the modes

Fits the drawn shape only (no milling, no rule masks), so pockets and the chamber
wall in a real target are outliers: read the median and the 90th percentile.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import paths  # noqa: E402,F401
import param_body as pb  # noqa: E402
import space  # noqa: E402

X_REF_A, X_REAR = 30.0, 222.3
BODY = space.LOFT + [f"mode{i}" for i in range(pb.N_MODES)]


def to_params(v: np.ndarray) -> pb.BodyParams:
    d = {"params": pb.BodyParams().as_dict(), "parts": {}}
    for name, x in zip(BODY, v):
        d = space.put(d, name, float(x))
    return pb.BodyParams.from_dict(d["params"])


def start_vector() -> np.ndarray:
    d = {"params": pb.BodyParams().as_dict(), "parts": {}}
    return np.array([space.get(d, n) for n in BODY])


def fit(points_mm: np.ndarray, skin_mm: float = 0.0) -> dict:
    """The settings whose drawn surface comes closest to these points."""
    X, Y, Z = points_mm.T
    lo = np.array([space.bounds(n)[0] for n in BODY])
    hi = np.array([space.bounds(n)[1] for n in BODY])

    def residual(u):                 # phi is a distance in mm, zero on the surface
        return pb.phi_mm(to_params(u[:-1]), X, Y, Z, X_REF_A, X_REAR) - u[-1]

    u0 = np.r_[np.clip(start_vector(), lo, hi), skin_mm]
    r = least_squares(residual, u0, bounds=(np.r_[lo, -8.0], np.r_[hi, 15.0]),
                      loss="soft_l1", f_scale=1.0, max_nfev=40, diff_step=0.02)
    e = np.abs(residual(r.x))
    return {"median_mm": float(np.median(e)), "p90_mm": float(np.percentile(e, 90)),
            "p99_mm": float(np.percentile(e, 99)), "skin_mm": float(r.x[-1]), "evals": int(r.nfev)}


def random_target(seed: int, n_bumps: int = 24, sigma_mm: float = 5.0, amp_mm: float = 2.5,
                  n_points: int = 4000) -> np.ndarray:
    """Points on the start body with smooth bumps smaller than the modes, placed
    anywhere on it: a legal-looking shape the modes were not built for."""
    rng = np.random.default_rng(seed)
    bp = pb.BodyParams()
    xs = np.linspace(X_REF_A + 2, X_REAR - 2, 90)
    ys = np.linspace(0.3, 33.0, 36)
    zs = np.linspace(3.0, 50.0, 50)
    G = np.array(np.meshgrid(xs, ys, zs, indexing="ij"))
    phi = pb.phi_mm(bp, G[0], G[1], G[2], X_REF_A, X_REAR)
    surf = np.argwhere(np.abs(phi) < 0.8)
    pick = surf[rng.choice(len(surf), n_bumps)]
    centres = G[:, pick[:, 0], pick[:, 1], pick[:, 2]].T
    amps = rng.uniform(-amp_mm, amp_mm, n_bumps)
    pts = np.array([G[:, i, j, k] for i, j, k in surf[rng.choice(len(surf), n_points)]])
    grad = np.stack(np.gradient(phi, xs, ys, zs), axis=0)
    idx = [(np.abs(xs - p[0]).argmin(), np.abs(ys - p[1]).argmin(), np.abs(zs - p[2]).argmin()) for p in pts]
    normal = np.array([grad[:, i, j, k] for i, j, k in idx])
    normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-9)
    d2 = ((pts[:, None, :] - centres[None, :, :]) ** 2).sum(axis=2)
    move = (amps * np.exp(-d2 / (2 * sigma_mm ** 2))).sum(axis=1)
    return pts + normal * move[:, None]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stl", nargs="*", default=[])
    ap.add_argument("--random", type=int, default=0)
    ap.add_argument("--sigma", type=float, default=5.0)
    a = ap.parse_args()
    for path in a.stl:
        import trimesh
        m = trimesh.load(path, force="mesh")
        scale = 1.0 if m.bounds.max() > 1.0 else 1e3
        p = m.sample(4000, return_index=False) * scale
        p = p[(p[:, 0] > X_REF_A + 1) & (p[:, 0] < X_REAR - 1)]
        p[:, 1] = np.abs(p[:, 1])
        print(path[-50:], fit(p, 1.0), flush=True)
    for seed in range(a.random):
        print(f"random {seed} (bumps {a.sigma} mm across)", fit(random_target(seed, sigma_mm=a.sigma)), flush=True)


if __name__ == "__main__":
    main()
