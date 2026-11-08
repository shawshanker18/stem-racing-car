"""morph.py -- deform a family base mesh onto a nearby candidate car (bible Part 6, 6.5).

    python morph.py --family <dir> --candidate-surfaces <dir with part STLs> --case <out dir>
Reads   <family>/case/constant/polyMesh (ASCII), <family>/case/surfaces/*.stl (anchor),
        candidate STLs (same file names, metres, half car)
Writes  <case>/constant/polyMesh/points (moved), morph.json (max/mean displacement, solver info)
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import numpy as np
import scipy.sparse as sp
import trimesh
from scipy.sparse.linalg import cg
from scipy.spatial import cKDTree

FIXED_PATCHES = ("inlet", "outlet", "top", "side", "front", "back")   # adjust to the case's names
DELTA_M = 5e-5
R_FREE_M = 0.020


def _body(text: str) -> str:
    """The list body of an OpenFOAM ASCII list file: between the first '(' after the size line
    and the matching last ')'."""
    i = text.index("(", text.index("\n", re.search(r"^\s*\d+\s*$", text, re.M).start()))
    return text[i + 1:text.rindex(")")]


def read_points(poly: Path) -> np.ndarray:
    body = _body((poly / "points").read_text())
    return np.array(body.replace("(", " ").replace(")", " ").split(), dtype=np.float64).reshape(-1, 3)


def read_faces(poly: Path) -> list:
    text = (poly / "faces").read_text()
    if "faceCompactList" in text[:3000]:
        lists = re.findall(r"\n(\d+)\s*\n\(\s*\n?([\d\s]*?)\n?\)", text)
        offs = np.array(lists[0][1].split(), dtype=np.int64)
        labs = np.array(lists[1][1].split(), dtype=np.int64)
        return [labs[offs[k]:offs[k + 1]] for k in range(len(offs) - 1)]
    return [np.array(m.split(), dtype=np.int64) for m in re.findall(r"\d+\(([\d\s]+)\)", text)]


def read_boundary(poly: Path) -> dict:
    out = {}
    for m in re.finditer(r"(\w+)\s*\{([^}]*)\}", (poly / "boundary").read_text()):
        nf, sf = re.search(r"nFaces\s+(\d+)", m.group(2)), re.search(r"startFace\s+(\d+)", m.group(2))
        tp = re.search(r"\btype\s+(\w+)", m.group(2))
        if nf and sf:
            out[m.group(1)] = (int(sf.group(1)), int(nf.group(1)), tp.group(1) if tp else "")
    return out


def edges_of(faces: list) -> np.ndarray:
    pairs = []
    for f in faces:
        pairs.append(np.stack([f, np.roll(f, -1)], axis=1))
    e = np.sort(np.concatenate(pairs), axis=1)
    return np.unique(e, axis=0)


def patch_points(faces: list, start: int, n: int) -> np.ndarray:
    return np.unique(np.concatenate(faces[start:start + n])) if n else np.array([], dtype=np.int64)


def write_points(poly: Path, P: np.ndarray) -> None:
    src = (poly / "points").read_text()
    head = src[:re.search(r"^\s*\d+\s*$", src, re.M).start()]
    head = re.sub(r"format\s+\w+;", "format      ascii;", head)
    lines = "\n".join(f"({x:.10g} {y:.10g} {z:.10g})" for x, y, z in P)
    (poly / "points").write_text(f"{head}{len(P)}\n(\n{lines}\n)\n")


def solve_component(n: int, edges: np.ndarray, gamma: np.ndarray, fixed: np.ndarray, value: np.ndarray):
    i, j = edges[:, 0], edges[:, 1]
    w = 0.5 * (gamma[i] + gamma[j])
    A = sp.coo_matrix((np.r_[w, w], (np.r_[i, j], np.r_[j, i])), shape=(n, n)).tocsr()
    L = sp.diags(np.asarray(A.sum(axis=1)).ravel()) - A
    free = ~fixed
    d = np.where(fixed, value, 0.0)
    if not free.any():
        return d
    Lff = L[free][:, free].tocsr()
    rhs = -(L[free][:, fixed] @ value[fixed])
    import pyamg
    M = pyamg.smoothed_aggregation_solver(Lff).aspreconditioner()
    x, info = cg(Lff, rhs, rtol=1e-10, maxiter=2000, M=M)
    if info != 0:
        raise RuntimeError(f"morph CG did not converge (info={info})")
    d[free] = x
    return d


def morph(family: Path, cand_dir: Path, case: Path) -> dict:
    shutil.copytree(family / "case", case, dirs_exist_ok=True)
    poly = case / "constant" / "polyMesh"
    P = read_points(poly)
    faces = read_faces(poly)
    bnd = read_boundary(poly)
    n = len(P)
    disp = np.zeros((n, 3))
    moving = np.zeros(n, bool)
    shared = {}
    for name, (start, nf, typ) in bnd.items():
        stl = cand_dir / f"{name}.stl"
        if not stl.exists():
            continue
        ids = patch_points(faces, start, nf)
        cand = trimesh.load(str(stl), force="mesh")
        cp, _dist, _tri = trimesh.proximity.closest_point(cand, P[ids])
        d = cp - P[ids]
        for k, pid in enumerate(ids):
            shared.setdefault(pid, []).append(d[k])
        moving[ids] = True
    for pid, ds in shared.items():
        disp[pid] = np.mean(ds, axis=0)
    conflict = max((float(np.ptp(np.array(ds), axis=0).max()) for ds in shared.values() if len(ds) > 1), default=0.0)

    fixed_all = np.zeros(n, bool)
    fix_c = [np.zeros(n, bool) for _ in range(3)]
    for name, (start, nf, typ) in bnd.items():
        ids = patch_points(faces, start, nf)
        if name in FIXED_PATCHES or typ == "patch":
            fixed_all[ids] = True
        elif typ == "symmetryPlane":
            fix_c[1][ids] = True
        elif name == "lowerWall":
            fix_c[2][ids] = True
    mov_ids = np.nonzero(moving)[0]
    dist, _ = cKDTree(P[mov_ids]).query(P)
    far = dist > R_FREE_M
    gamma = 1.0 / np.maximum(dist, DELTA_M) ** 2
    edges = edges_of(faces)
    out = np.zeros((n, 3))
    for c in range(3):
        fixed = moving | fixed_all | far | fix_c[c]
        out[:, c] = solve_component(n, edges, gamma, fixed, np.where(moving, disp[:, c], 0.0))
    write_points(poly, P + out)
    info = {"n_points": n, "n_moving": int(moving.sum()), "max_disp_mm": float(np.abs(disp[moving]).max() * 1e3),
            "mean_disp_mm": float(np.linalg.norm(disp[moving], axis=1).mean() * 1e3),
            "shared_conflict_mm": conflict * 1e3}
    (case / "morph.json").write_text(json.dumps(info, indent=1))
    return info
