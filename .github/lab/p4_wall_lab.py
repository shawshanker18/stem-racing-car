"""Part 4 lab: are the sub-0.7 mm walls the referee reads (0.001-0.5 mm on every car) real
geometry or the measure? For each printed file of a kept car: every thin reading (< 0.7 mm)
with where it is, how many samples are thin (area share), the angle between the two faces,
and a second measure at the same point (the largest ball inside the part there, from the
distance to the surface of points stepped inward)."""
import glob
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import trimesh

RUN, REPO = int(os.environ.get("WALL_RUN", "43621396051")), os.environ.get("WALL_REPO", os.environ["GITHUB_REPOSITORY"])
d = Path("../out/files/wall")
subprocess.run(["gh", "run", "download", str(RUN), "-R", REPO, "-D", str(d)], check=False)
for f in sorted(glob.glob(str(d / "**" / "printed_*.stl"), recursive=True)):
    m = trimesh.load(f, force="mesh")
    pts, fi = trimesh.sample.sample_surface_even(m, 8000, seed=1)
    nrm = m.face_normals[fi]
    loc, ray, tri = m.ray.intersects_location(pts - nrm * 1e-4, -nrm, multiple_hits=False)
    cosang = (m.face_normals[tri] * nrm[ray]).sum(axis=1)
    opp = cosang < -0.5
    dist = np.linalg.norm(loc - pts[ray], axis=1)
    thin = opp & (dist < 0.7)
    print(f"FILE {Path(f).name}: closed {m.is_volume} faces {len(m.faces)} samples {len(pts)} "
          f"opposite-hits {opp.sum()} thin(<0.7) {thin.sum()} ({100 * thin.sum() / max(opp.sum(), 1):.2f} %)", flush=True)
    if not thin.any():
        continue
    tp = pts[ray[thin]]
    print(f"  thin box mm {np.round([tp.min(0), tp.max(0)], 2).tolist()}", flush=True)
    order = np.argsort(dist[thin])[:12]
    for i in order:
        p, n = tp[i], nrm[ray[thin]][i]
        # second measure: step inward; the largest distance to the surface on the way is the
        # radius of the biggest ball that fits there (half the wall for a slab)
        steps = p - np.outer(np.linspace(0.01, 0.7, 70), n)
        inside = m.contains(steps)
        cd = trimesh.proximity.closest_point(m, steps)[1]
        ball = float(2 * cd[inside].max()) if inside.any() else 0.0
        print(f"   at {np.round(p, 3).tolist()} ray {dist[thin][i]:.4f} mm, faces at "
              f"{np.degrees(np.arccos(np.clip(-cosang[thin][i], -1, 1))):.1f} deg from antiparallel, "
              f"inscribed ball diameter {ball:.4f} mm, points inside {int(inside.sum())}/70", flush=True)
