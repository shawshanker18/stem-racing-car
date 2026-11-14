"""Part 4 lab: what makes the front assembly's thin spots at the nose top (car 44719/0,
x 20-22, z 18-19, 0.04-0.5 mm)? For each thin reading: its distance to the body's own
surface (body_half.stl), to the CFD cone (nose.stl) and to the wing, and whether it lies
inside each -- a sliver between two nearly coincident skins shows as ~0 to both."""
import glob
import os
import subprocess
from pathlib import Path

import numpy as np
import trimesh

RUN = 43621396051
d = Path("../out/files/nose")
subprocess.run(["gh", "run", "download", str(RUN), "-R", os.environ["GITHUB_REPOSITORY"], "-D", str(d)], check=False)
folder = Path(glob.glob(str(d / "**" / "assembly.json"), recursive=True)[0]).parent
fa = trimesh.load(folder / "printed_front_assembly.stl", force="mesh")             # mm
src = {}
for name in ("body_half", "nose", "fwing"):
    m = trimesh.load(folder / f"{name}.stl", force="mesh")
    m.apply_scale(1e3)                                                              # m -> mm
    full = m.copy()
    full.vertices[:, 1] *= -1
    full.invert()
    src[name] = trimesh.util.concatenate([m, full])
pts, fi = trimesh.sample.sample_surface_even(fa, 12000, seed=1)
nrm = fa.face_normals[fi]
loc, ray, tri = fa.ray.intersects_location(pts - nrm * 1e-4, -nrm, multiple_hits=False)
opp = (fa.face_normals[tri] * nrm[ray]).sum(axis=1) < -0.5
dist = np.linalg.norm(loc - pts[ray], axis=1)
thin = np.where(opp & (dist < 1.0))[0]
print(f"thin (<1.0) readings: {len(thin)} of {opp.sum()}", flush=True)
top = thin[(pts[ray[thin]][:, 2] > 17.5) & (pts[ray[thin]][:, 0] < 25)]
print(f"at the nose top (z > 17.5, x < 25): {len(top)}", flush=True)
for i in top[np.argsort(dist[top])][:15]:
    p, q = pts[ray[i]], loc[i]
    row = [f"at {np.round(p, 3).tolist()} wall {dist[i]:.3f}"]
    for name, m in src.items():
        dp = trimesh.proximity.closest_point(m, [p])[1][0]
        dq = trimesh.proximity.closest_point(m, [q])[1][0]
        row.append(f"{name}: near side {dp:.3f}, far side {dq:.3f}")
    print("  " + "; ".join(row), flush=True)
