"""Part 4 lab: do the 10 thinnest pod readings of car 44719/0 (kept files, before 55b747f)
match the strip's or plate's superellipse thickness at those points (within 0.05 mm)?"""
import glob
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import trimesh

sys.path.insert(0, str(Path.cwd().parent / "part4-simulation"))
import beam_support as bsm
import component_contract as cc

RUN = 43621396051
d = Path("../out/files/proof")
subprocess.run(["gh", "run", "download", str(RUN), "-R", os.environ["GITHUB_REPOSITORY"], "-D", str(d)], check=False)
folder = Path(glob.glob(str(d / "**" / "assembly.json"), recursive=True)[0]).parent
asm = json.loads((folder / "assembly.json").read_text())
car = json.loads(Path(glob.glob(str(d / "**" / "car_*.json"), recursive=True)[0]).read_text())
sup = {k[4:]: v for k, v in car.get("moved", {}).items() if k.startswith("sup.")}
bs = bsm.BeamSupport(**{k: v for k, v in sup.items() if k in bsm.BeamSupport.__dataclass_fields__})
print("support settings moved:", sup, flush=True)


def thick(dx, a, b, p):
    u = min(abs(dx) / a, 1.0)
    return 2 * b * (1 - u ** p) ** (1 / p)


for tag, x_axle in (("front", asm["x_front_mm"]), ("rear", asm["x_front_mm"] + asm["W_mm"])):
    st = asm["info"]["support_structure"][tag]
    ch = asm["info"].get("pod", {}).get(tag, {})
    z_strip = max(ch.get("z_floor_mm", 0) + bs.strip_above_floor_mm, cc.TETHER_GUIDE_HOLE_TOP_Z + 0.3 + bs.strip_h_mm / 2)
    plate_h = st.get("plate_h_mm", bs.beam_h_mm)
    zc = ch.get("z_arch_mm", 0) - bs.pod_wall_mm / 2 - plate_h / 2
    print(f"{tag}: axle x {x_axle:.3f}, strip {bs.strip_w_mm} x {bs.strip_h_mm} at z {z_strip:.3f}; plate {bs.beam_w_mm} x {plate_h:.3f} at z {zc:.3f}; p {bs.p}", flush=True)
    m = trimesh.load(folder / f"printed_support_{tag}.stl", force="mesh")
    pts, fi = trimesh.sample.sample_surface_even(m, 8000, seed=1)
    nrm = m.face_normals[fi]
    loc, ray, tri = m.ray.intersects_location(pts - nrm * 1e-4, -nrm, multiple_hits=False)
    opp = (m.face_normals[tri] * nrm[ray]).sum(axis=1) < -0.5
    dist = np.linalg.norm(loc - pts[ray], axis=1)
    sel = np.where(opp)[0][np.argsort(dist[opp])[:10]]
    for i in sel:
        p = pts[ray[i]]
        dx = p[0] - x_axle
        ts = thick(dx, bs.strip_w_mm / 2, bs.strip_h_mm / 2, bs.p)
        tp = thick(dx, bs.beam_w_mm / 2, plate_h / 2, bs.p)
        member, t_model = ("strip", ts) if abs(p[2] - z_strip) < abs(p[2] - zc) else ("plate", tp)
        print(f"  at {np.round(p, 3).tolist()} measured {dist[i]:.4f} mm; {member} section there {t_model:.4f} mm; "
              f"diff {abs(dist[i] - t_model):.4f} {'MATCH' if abs(dist[i] - t_model) <= 0.05 else 'NO MATCH'}", flush=True)
