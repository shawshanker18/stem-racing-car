"""
mesh_fairing.py -- triangle-quality clean-up for the milled body (mm units).

Booleans on a 1 mm body leave long thin triangles across flat faces (measured
on the start car: 6.6 % of triangles under 15 deg, 33 % of the area, edges up
to 35 mm), which shows as a patchy surface in renders and slicers. Two
topology-safe passes, neither of which adds or removes vertices:

  delaunay_flip   flips edges toward Delaunay where the surface is nearly flat.
  fair            Taubin smoothing of vertices that are not on a crease, with
                  the move clamped, so pocket edges and fits do not change.

Subdividing long edges was tried and made angles worse (40 % under 15 deg),
so it is not here; a real isotropic remesher would need a new dependency.
"""
from __future__ import annotations

import numpy as np


def _angle_at(P, a, b, c):
    u, v = P[b] - P[a], P[c] - P[a]
    cs = (u * v).sum(1) / (np.linalg.norm(u, axis=1) * np.linalg.norm(v, axis=1) + 1e-30)
    return np.arccos(np.clip(cs, -1.0, 1.0))


def delaunay_flip(mesh, max_dihedral_deg: float = 2.0, passes: int = 30):
    """Return (mesh, flips). Vertices never move; a closed mesh stays closed."""
    import trimesh
    P = np.asarray(mesh.vertices, float)
    F = np.asarray(mesh.faces).copy()
    total = 0
    for _ in range(passes):
        m = trimesh.Trimesh(P, F, process=False)
        fa, fb = m.face_adjacency[:, 0], m.face_adjacency[:, 1]
        e0, e1 = m.face_adjacency_edges[:, 0], m.face_adjacency_edges[:, 1]
        flat = m.face_adjacency_angles < np.radians(max_dihedral_deg)
        fa, fb, e0, e1 = fa[flat], fb[flat], e0[flat], e1[flat]
        if not len(fa):
            break
        oa = F[fa][(F[fa] != e0[:, None]) & (F[fa] != e1[:, None])]
        ob = F[fb][(F[fb] != e0[:, None]) & (F[fb] != e1[:, None])]
        if len(oa) != len(fa) or len(ob) != len(fb):     # a face with a repeated vertex
            break
        s = _angle_at(P, oa, e0, e1) + _angle_at(P, ob, e0, e1)
        existing = set(map(tuple, np.sort(m.edges_unique, axis=1)))
        used, done = set(), 0
        for k in np.argsort(-s):
            if s[k] <= np.pi + 1e-9:
                break
            c, d = int(oa[k]), int(ob[k])
            if c == d or tuple(sorted((c, d))) in existing:
                continue
            if fa[k] in used or fb[k] in used:
                continue
            tri = list(F[fa[k]])
            i = tri.index(int(e0[k]))
            u, v = (int(e0[k]), int(e1[k])) if tri[(i + 1) % 3] == e1[k] else (int(e1[k]), int(e0[k]))
            F[fa[k]], F[fb[k]] = [c, u, d], [c, d, v]
            used.update((fa[k], fb[k]))
            done += 1
        if not done:
            break
        total += done
    return trimesh.Trimesh(P, F, process=False), total


def fair(mesh, crease_deg: float = 25.0, iters: int = 12, lam: float = 0.5,
         mu: float = -0.53, max_move: float = 0.1):
    """Taubin smoothing off the creases. Vertices on a crease, a boundary or a
    non-manifold edge stay put; no vertex moves more than `max_move` (mesh units)."""
    import scipy.sparse as sp
    import trimesh
    V0 = np.asarray(mesh.vertices, float)
    V = V0.copy()
    n = len(V)
    frozen = np.zeros(n, bool)
    frozen[mesh.face_adjacency_edges[mesh.face_adjacency_angles > np.radians(crease_deg)].ravel()] = True
    edges, counts = np.unique(mesh.edges_sorted, axis=0, return_counts=True)
    frozen[edges[counts != 2].ravel()] = True
    E = mesh.edges_unique
    A = sp.coo_matrix((np.ones(2 * len(E)), (np.r_[E[:, 0], E[:, 1]], np.r_[E[:, 1], E[:, 0]])),
                      shape=(n, n)).tocsr()
    deg = np.maximum(np.asarray(A.sum(1)).ravel(), 1)
    free = ~frozen
    for _ in range(iters):
        for k in (lam, mu):
            V[free] += k * ((A @ V) / deg[:, None] - V)[free]
    d = np.linalg.norm(V - V0, axis=1)
    over = d > max_move
    V[over] = V0[over] + (V[over] - V0[over]) * (max_move / d[over])[:, None]
    return trimesh.Trimesh(V, mesh.faces, process=False)


def clean(mesh, max_move: float = 0.1):
    """Flip, then fair. Falls back to the input if the result is not closed
    when the input was."""
    out, _ = delaunay_flip(mesh)
    out = fair(out, max_move=max_move)
    if mesh.is_watertight and not out.is_watertight:
        return mesh
    return out


def remesh_file(path, target_edge_mm: float, max_move_mm: float = 0.05, max_edge_mm: float = 8.0) -> dict:
    """Rewrite a manufacturing STL (mm) with even triangles, keeping its creases.
    Boolean output is closed but full of long slivers (edges up to 106 mm, 25 % of
    a printed part's faces under 5 deg), which slicers, CAM and CFD meshers all
    handle badly. The surface may move at most max_move_mm. Returns what the file
    holds afterwards; if the result is not a clean closed solid the file is left
    as it was, and the report says so."""
    import pymeshlab as ml
    import trimesh
    before = trimesh.load(str(path), force="mesh")
    # The odd part comes out torn or flipped at one triangle size and clean at the next
    # (1 car in 400), which is a false rejection if only one size is tried.
    # Two more sizes for the rarer part that tears at all three (an 83 mm wing-span edge left
    # in a front assembly, 1 car in 1300).
    for target in (target_edge_mm, 1.25 * target_edge_mm, 0.8 * target_edge_mm,
                   0.6 * target_edge_mm, 1.6 * target_edge_mm):
        ms = ml.MeshSet()
        ms.add_mesh(ml.Mesh(before.vertices, before.faces))
        ms.apply_filter("meshing_isotropic_explicit_remeshing", iterations=6,
                        targetlen=ml.PureValue(target), featuredeg=25.0, adaptive=False,
                        checksurfdist=True, maxsurfdist=ml.PureValue(max_move_mm))
        o = ms.current_mesh()
        after = trimesh.Trimesh(o.vertex_matrix(), o.face_matrix(), process=False)
        after.merge_vertices()
        if after.is_watertight and not after.is_winding_consistent:
            trimesh.repair.fix_normals(after)
        same = (after.is_volume and len(after.split(only_watertight=False)) == len(before.split(only_watertight=False))
                and abs(abs(after.volume) - abs(before.volume)) <= 0.005 * abs(before.volume))
        if same:
            break
    if same and after.edges_unique_length.max() > max_edge_mm:
        # The odd edge survives the remesh (10-17 mm against 8, 1 car in 200). Splitting
        # just those keeps the surface exactly; another size only trades it for slivers.
        ms.apply_filter("meshing_surface_subdivision_midpoint", iterations=4,
                        threshold=ml.PureValue(0.9 * max_edge_mm))
        o = ms.current_mesh()
        split = trimesh.Trimesh(o.vertex_matrix(), o.face_matrix(), process=False)
        split.merge_vertices()
        if split.is_volume:
            after = split
    if not same and before.edges_unique_length.max() > max_edge_mm:
        # No size remeshed it cleanly: at least split the raw file's long edges. The surface
        # stays exactly where it was; only the triangles get shorter.
        ms = ml.MeshSet()
        ms.add_mesh(ml.Mesh(before.vertices, before.faces))
        ms.apply_filter("meshing_surface_subdivision_midpoint", iterations=6,
                        threshold=ml.PureValue(0.9 * max_edge_mm))
        o = ms.current_mesh()
        split = trimesh.Trimesh(o.vertex_matrix(), o.face_matrix(), process=False)
        split.merge_vertices()
        if split.is_watertight and not split.is_winding_consistent:
            trimesh.repair.fix_normals(split)
        same = (split.is_volume and abs(abs(split.volume) - abs(before.volume)) <= 0.005 * abs(before.volume)
                and len(split.split(only_watertight=False)) == len(before.split(only_watertight=False)))
        if same:
            after = split
    if same:
        after.export(str(path))
        # 32-bit floats can weld what the remesher kept apart (1 car in 1200).
        same = trimesh.load(str(path), force="mesh").is_volume
        if not same:
            before.export(str(path))
    final = after if same else before
    angles = np.degrees(final.face_angles).min(axis=1)
    return {"remeshed": bool(same), "faces": len(final.faces),
            "max_edge_mm": float(final.edges_unique_length.max()),
            "faces_under_5deg_pct": float(100 * (angles < 5).mean()),
            "file_cm3": abs(float(final.volume)) / 1e3, "closed": bool(final.is_watertight),
            "pieces": len(final.split(only_watertight=False))}
