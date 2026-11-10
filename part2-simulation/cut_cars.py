"""Local cuts for the reshape-quality study: the shapes carving actually makes.

Starts from Part 1's legal start block (cutter.start_block, read only) and makes
one local cut per (place, depth) with cutter.cut: a Gaussian patch of "remove
material here" sensitivity (sigma 8 mm) centred on the nose tip, the side of
the sidepod at mid-length, or the top of the tail, moved up to `depth` mm.
Each field is saved for run_car --phi-npy; the uncut block is the reference.

    python cut_cars.py OUT_DIR          # writes ref.npy, <place>_<depth>.npy, cuts.json
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "part1-simulation"))

LAYOUT = {"W": 120.3, "x_front": 46.0, "d_halo": 43.72}
SIGMA_M = 0.008
CUTS = [(place, depth) for place in ("nose", "sidepod", "rear") for depth in (0.5, 2.0)]


def centre(v: np.ndarray, place: str) -> np.ndarray:
    """A surface point for each place, picked from the half-body's own vertices."""
    x, y, z = v[:, 0], v[:, 1], v[:, 2]
    if place == "nose":
        return v[np.argmin(x)]
    if place == "sidepod":
        mid = (x > np.quantile(x, 0.40)) & (x < np.quantile(x, 0.60))
        return v[mid][np.argmax(y[mid])]
    if place == "rear":
        high = z > np.median(z)
        return v[high][np.argmax(x[high])]
    raise ValueError(place)


def remove_here(v: np.ndarray, c: np.ndarray) -> np.ndarray:
    """dT_dn > 0 (growing there is slower) in a Gaussian patch, so the cutter removes it."""
    return np.exp(-np.sum((v - c) ** 2, axis=1) / (2 * SIGMA_M ** 2))


def main(out: Path) -> None:
    import cutter
    import unified_phi as up

    out.mkdir(parents=True, exist_ok=True)
    g = cutter.start_block(LAYOUT)
    half = up.extract_half_surface(g)
    v = np.asarray(half.vertices, float)
    report = {}
    # The reference must go through the same cut() machinery (milling for the 6.25 mm
    # ball, thin strips, pinches) as the cut cars, or every cut car differs from it
    # by that milling too (1.2 mm near x 75 mm in run rc6): a negligible cut does that.
    g_ref, rep0 = cutter.cut(g, remove_here(v, centre(v, "nose")), half, step_m=1e-6,
                             max_substeps=1, trust_radius_m=1e-6)
    report["ref"] = {k: rep0.get(k) for k in ("status", "reason", "disp_p90_m")}
    cutter.save_field(g_ref if rep0["status"] == "ok" else g, out / "ref.npy")
    for place, depth in CUTS:
        c = centre(v, place)
        d = depth / 1e3
        g2, rep = cutter.cut(g, remove_here(v, c), half, step_m=d, max_substeps=6, trust_radius_m=d)
        name = f"{place}_{depth:g}"
        report[name] = {"centre_mm": [float(t) * 1e3 for t in c], "depth_mm": depth,
                        **{k: rep.get(k) for k in ("status", "reason", "substeps", "disp_median_m", "disp_p90_m")}}
        if rep["status"] == "ok":
            cutter.save_field(g2, out / f"{name}.npy")
        print(name, json.dumps(report[name], default=float), flush=True)
    (out / "cuts.json").write_text(json.dumps(report, indent=1, default=float))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
