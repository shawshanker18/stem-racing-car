"""
legality.py -- the assembled car, measured the way a scrutineer measures it.

Part 1's hard masks keep the body legal DURING descent; this module is the
independent audit on the finished geometry. Two of those masks were found wrong
on 2026-09-25 (block envelope, T5.5 wall), which is exactly why the audit exists.

    check(body_half_stl, assembly_json, mass_state) -> {rule: {margin, pass, note}}

Margins are in mm (or g for mass). margin >= 0 passes.
"""
from __future__ import annotations

import math
import os

import numpy as np

import paths  # noqa: F401
import rules_constants as rc

# The chamber height of the usual layout: only for callers of t55_wall_fraction that do
# not pass the measured one. check() always measures it.
DEFAULT_AXIS_Z_MM = 31.0

REGS = {
    "T3.4_width_min": 65.0, "T3.4_width_max": 85.0, "T3.5_height": 65.0,
    "T3.7_clearance": 1.5, "T3.6_mass_g": 48.0, "T7.3_W_min": 120.0, "T7.3_W_max": 140.0,
    "T8.2_nose_overhang": 40.0, "T8.5.1_nose_z": 25.0, "T8.5.1_nose_half_width": 15.0,
    "T9.4.2_rear_overhang": 40.0, "T5.5_wall": 3.0,
    "block_length": 223.0, "block_width": 65.0, "block_height": 50.0,
}


def _entry(margin: float, note: str = "") -> dict:
    return {"margin": float(margin), "pass": bool(margin >= -1e-6), "note": note}


def _x_cylinder(r_m: float, x0_m: float, x1_m: float, z_m: float):
    import trimesh
    c = trimesh.creation.cylinder(radius=r_m, height=x1_m - x0_m, sections=96)
    c.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
    c.apply_translation([(x0_m + x1_m) / 2.0, 0.0, z_m])
    return c


def t55_wall_fraction(body_half, rear_face_mm: float, depth_mm: float | None = None,
                      bore_r_mm: float | None = None, axis_z_mm: float | None = None,
                      angle_deg: float = 0.0) -> float:
    """Fraction of probe points inside the body in the 3 mm annulus around the
    chamber, along the whole bore (T5.5). 1.0 = a full 3 mm wall."""
    depth_mm = rc.BLOCK_BORE_DEPTH_MM if depth_mm is None else depth_mm
    bore_r_mm = rc.BLOCK_BORE_DIA_MM / 2.0 if bore_r_mm is None else bore_r_mm
    axis_z_mm = DEFAULT_AXIS_Z_MM if axis_z_mm is None else axis_z_mm
    if not body_half.is_volume:             # a zero-volume sliver sends a good car to the points
        import trimesh
        shells = [p for p in body_half.split(only_watertight=False) if p.is_volume]
        if shells:
            body_half = trimesh.util.concatenate(shells)
    # The wall's own volume when the body is a true solid. With points, one of 468 misread
    # on one machine failed a good car (100 % here, 99.8 % there), and a real thin patch
    # between the points would pass.
    if body_half.is_volume:
        import trimesh
        x0, x1 = (rear_face_mm - depth_mm + 2.0) / 1e3, (rear_face_mm - 2.0) / 1e3
        tube = trimesh.boolean.difference(
            [_x_cylinder((bore_r_mm + 2.9) / 1e3, x0, x1, axis_z_mm / 1e3),
             _x_cylinder((bore_r_mm + 1.0) / 1e3, x0 - 1e-3, x1 + 1e-3, axis_z_mm / 1e3)], engine="manifold")
        if angle_deg:                                   # along a tilted bore, from its rim
            tube.apply_transform(trimesh.transformations.rotation_matrix(
                -math.radians(angle_deg), [0, 1, 0], [rear_face_mm / 1e3, 0.0, axis_z_mm / 1e3]))
        right = trimesh.creation.box(bounds=[[x0 - 1e-3, 1e-5, 0.0], [x1 + 1e-3, 0.1, 0.1]])
        tube = trimesh.boolean.intersection([tube, right], engine="manifold")
        return _volume_in(body_half, tube) / abs(tube.volume)
    xs = np.linspace(rear_face_mm - depth_mm + 2.0, rear_face_mm - 2.0, 12)
    # From 1 mm outside the bore: the bore is a fixed air mask the optimiser
    # cannot touch, and on a 1 mm voxel STL its facets bulge ~0.5 mm at 45 deg
    # (every miss on the 2026-09-26 optimised car was r = 9.5 at 47/133 deg).
    # The wall the optimiser CAN thin is the outside, probed to 2.9 mm.
    rs = (bore_r_mm + 1.0, bore_r_mm + 2.0, bore_r_mm + 2.9)
    # Right half, but NOT on the symmetry plane itself: a containment test on
    # the capped y=0 face is ambiguous and reported false misses at 0/180 deg.
    ang = np.linspace(0.08, math.pi - 0.08, 13)
    pts = np.array([(x, r * math.sin(a), axis_z_mm + r * math.cos(a))
                    for x in xs for r in rs for a in ang]) / 1e3
    pts[:, 1] = np.maximum(pts[:, 1], 1e-6)
    inside = _contains(body_half, pts)
    return float(inside.mean())


# Volumes below this (mm3, about 0.8 mg of foam) are mesh round-off, not material: a
# remesh may move a whole surface 0.05 mm.
_ROUND_OFF_MM3 = 5.0
CARTRIDGE_LENGTH_MIN_MM = rc.CARTRIDGE_LENGTH_MIN_MM
MESH_MAX_EDGE_MM = 8.0             # measured 1.9-7.6 after the remesh, 106 before it
MESH_MAX_SLIVER_BODY_PCT = 4.0     # measured 0.4-3.2 % after (highest at 0.3 mm), 3.3 % before
MESH_MAX_SLIVER_PRINTED_PCT = 12.0 # 5.7-11 % after, 25 % before: a wing's sharp trailing edge
PRINTED_MIN_WALL_MM = 1.0         # the print minimum (Part 4 component_contract.MIN_WALL_MM; typed here, the
#                                  referee imports nothing from the builders). Team printer figure to come.
WALL_MEASURE_TOL_MM = 0.0         # no tolerance (reviewer, 2026-11-14): walls are built at or above the minimum


def _contains(mesh, pts, chunk: int = 300):
    """mesh.contains in small batches. All at once, 8000 points took 7 GB on a 1 mm car and
    killed the 16 GB machine on a 0.5 mm one, when the ray cast gathered every candidate."""
    pts = np.asarray(pts)
    return np.concatenate([mesh.contains(pts[i:i + chunk]) for i in range(0, len(pts), chunk)])


def _nearest_gap_m(mesh, pts, chunk: int = 300) -> float:
    pts = np.asarray(pts)
    return min(float(mesh.nearest.on_surface(pts[i:i + chunk])[1].min()) for i in range(0, len(pts), chunk))


def _volume_in(mesh, region) -> float:
    import trimesh
    r = trimesh.boolean.intersection([mesh, region], engine="manifold")
    return 0.0 if r is None or r.is_empty else abs(float(r.volume))


def _where(mesh, n: int = 3) -> str:
    """"; at" the largest pieces of a mesh and their boxes (mm), so a failure can be traced."""
    if mesh is None or mesh.is_empty:
        return ""
    ps = sorted(mesh.split(only_watertight=False), key=lambda p: -abs(p.volume))[:n]
    return "; at " + "; ".join(f"{abs(p.volume):.1f} mm3 in {np.round(p.bounds, 1).tolist()}" for p in ps)


def _absent(volume_mm3: float, note: str) -> dict:
    return _entry(0.0 if volume_mm3 <= _ROUND_OFF_MM3 else -volume_mm3 / 1e3, note)


def _visibility_checks(assembly: dict, solids: dict) -> dict:
    """T4.4.2, T4.4.3, T7.10, T7.11, T8.7, T8.8, T9.6, T9.7, measured on the files that get made (mm)."""
    import math
    import trimesh
    stl = {s["name"]: s["stl"] for s in assembly.get("extra_surfaces", [])}
    r = {}

    def half(name):
        m = trimesh.load(stl[name], force="mesh")
        m.apply_scale(1e3)
        return m

    def in_box(lo, hi, among=solids):
        box = trimesh.creation.box(bounds=[lo, hi])
        hits = {k: _volume_in(m, box) for k, m in among.items()}
        return {k: v for k, v in hits.items() if v > _ROUND_OFF_MM3}

    def report(hits):
        return _absent(sum(hits.values()), ", ".join(f"{k} {v:.1f} mm3" for k, v in hits.items()) or "clear")

    if "halo" in stl:
        b = half("halo").bounds
        x0, x1, hy, zt = b[0, 0], b[1, 0], b[1, 1], b[1, 2]
        z_seen = b[0, 2] + 4.0                     # the outlines stop 4 mm above its base
        r["T4.4.2_halo_seen_from_front"] = report(in_box((-50.0, -hy, z_seen), (x0, hy, zt)))
        r["T4.4.2_halo_seen_from_side"] = report(in_box((x0, hy, z_seen), (x1, 150.0, zt)))
        # The pocket's walls stand on the halo's outline. On a very low body they are 0.3-1.4 mm
        # tall, and 0.6 mm triangles round that step off (6 mm3 in a 150 mm rim failed a good
        # car), so the outer 0.5 mm is not counted: far under what the 6.25 mm cutter can see.
        rim = 0.5
        # Nor the floor's own top 0.3 mm: the final remesh left a 0.2 mm skin over the whole
        # floor of one car (9.2 mm3, z 24.0-24.2). The halo just sits on it, inside T4.4.4's
        # +-1 mm, and nothing stands over the halo.
        skin = 0.3
        r["T4.4.3_halo_seen_from_top"] = report(in_box((x0 + rim, -hy + rim, b[0, 2] + skin), (x1 - rim, hy - rim, 150.0)))
        if not r["T4.4.3_halo_seen_from_top"]["pass"]:      # where, so a fault can be traced
            top = trimesh.creation.box(bounds=[(x0 + rim, -hy + rim, b[0, 2] + skin), (x1 - rim, hy - rim, 150.0)])
            where = [f"{k} in {np.round(i.bounds, 1).tolist()}" for k, m in solids.items()
                     if (i := trimesh.boolean.intersection([m, top], engine="manifold")) is not None and not i.is_empty]
            r["T4.4.3_halo_seen_from_top"]["note"] += f"; halo x {x0:.1f}-{x1:.1f} y +-{hy:.1f} base {b[0, 2]:.2f}; " + "; ".join(where)

    # Supports and hubcaps may cover a wheel from the side (T7.10); nothing else may.
    others = {k: m for k, m in solids.items() if not k.startswith(("printed_support", "printed_hubcaps"))}
    for name in ("wheelF", "wheelR"):
        if name not in stl:
            continue
        b = half(name).bounds
        rad, xc, zc, yo = (b[1, 2] - b[0, 2]) / 2.0, b[:, 0].mean(), b[:, 2].mean(), b[1, 1]
        cyl = trimesh.creation.cylinder(radius=rad, height=100.0, sections=64)
        cyl.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0]))
        cyl.apply_translation([xc, yo + 50.0, zc])
        hits = {k: _volume_in(m, cyl) for k, m in others.items()}
        r[f"T7.10_{name}_seen_from_side"] = report({k: v for k, v in hits.items() if v > _ROUND_OFF_MM3})
        if name == "wheelF":
            # Ahead of the tread above 20 mm. A hub behind the tread is hidden by the wheel.
            from shapely.geometry import Polygon
            arc = [(xc - math.sqrt(max(rad ** 2 - (z - zc) ** 2, 0.0)), z) for z in np.linspace(20.0, b[1, 2], 24)]
            ahead = trimesh.creation.extrude_polygon(Polygon([(-50.0, 20.0)] + arc + [(-50.0, b[1, 2])]), yo - b[0, 1])
            ahead.apply_transform([[1, 0, 0, 0], [0, 0, 1, b[0, 1]], [0, 1, 0, 0], [0, 0, 0, 1.0]])
            if ahead.volume < 0:
                ahead.invert()
            hits = {k: _volume_in(m, ahead) for k, m in solids.items()}
            r["T7.11_front_wheel_seen_from_front"] = report({k: v for k, v in hits.items() if v > _ROUND_OFF_MM3})

    # T8.8: nothing in front of the wing. A nose may split it (T8.6, T8.7's own figures),
    # so only the wing outside the nose counts; it is one file with the nose, so the wing
    # is taken from its own mesh and looks forward past the other parts.
    if "fwing" in stl:
        wing = half("fwing")
        ahead = dict(solids)
        ahead.pop("printed_front_assembly", None)
        nose_y = half("nose").bounds[1, 1] if "nose" in stl else 0.0
        if "nose" in stl:
            ahead["nose"] = half("nose")
        pts = trimesh.sample.sample_surface(wing, 3000, seed=2)[0]
        pts = pts[pts[:, 1] > nose_y + 0.5]
        if len(pts):
            r["T8.8_front_wing_seen_from_front"] = _hidden_from_front(pts, ahead, "the wing outside the nose")

    # T9.7: the same, for the rear wing. The pylon under it is not the wing.
    if "rwing" in stl:
        wing = max(half("rwing").split(only_watertight=False), key=lambda s: s.extents[1])
        ahead = {k: m for k, m in solids.items() if k != "printed_rwing"}
        if "halo" in stl:
            ahead["halo"] = half("halo")
        pts = trimesh.sample.sample_surface(wing, 3000, seed=2)[0]
        r["T9.7_rear_wing_seen_from_front"] = _hidden_from_front(pts, ahead, "the rear wing")

    # T8.7 and T9.6: 5 mm of clear air from each wing's surface to ANY other part of the car
    # or the track. The gates in Part 4 measure only the front wing to the track and its
    # wheel, and the rear wing to the body (a Mistral audit, checked against the rule text).
    # The wing's own support, where it joins, is the fillet the rule allows for: points within
    # 5 mm (sideways) of the nose or the pylon are left out.
    wheels = {k: half(k) for k in ("wheelF", "wheelR") if k in stl}
    if "fwing" in stl:
        pts = trimesh.sample.sample_surface(half("fwing"), 3000, seed=3)[0]
        nose_y = half("nose").bounds[1, 1] if "nose" in stl else 1.5
        pts = pts[pts[:, 1] > nose_y + 5.0]
        others = {k: m for k, m in solids.items() if k != "printed_front_assembly"}
        others.update(wheels)
        if "nose" in stl:
            others["nose"] = half("nose")
        if "halo" in stl:
            others["halo"] = half("halo")
        if len(pts):
            r["T8.7_front_wing_clear_air_all_parts"] = _clear_air(pts, others)
    if "rwing" in stl:
        wing = max(half("rwing").split(only_watertight=False), key=lambda s: s.extents[1])
        pts = trimesh.sample.sample_surface(wing, 3000, seed=3)[0]
        pts = pts[pts[:, 1] > 5.0 + 2.0]               # the pylon stands at |y| < 1 mm, give or take
        others = {k: m for k, m in solids.items() if k != "printed_rwing"}
        others.update(wheels)
        if "halo" in stl:
            others["halo"] = half("halo")
        if len(pts):
            r["T9.6_rear_wing_clear_air_all_parts"] = _clear_air(pts, others)

    # T4.6: the 30 x 15 mm logo decal (T1.12) wholly on each side, all of it seen from the
    # side. T4.7: the team number, 8 mm tall, on the body between Ref A and the halo's front,
    # seen from above. Looked for on a 1 mm grid of rays: a point counts where the first thing
    # the ray meets is the body, on a surface facing the viewer. The car is symmetric, so the
    # right side stands for both.
    if "machined_body" in solids:
        view = dict(solids)
        view.update(wheels)
        view.update({k: half(k) for k in ("halo", "nose") if k in stl})
        names = list(view)
        allm = trimesh.util.concatenate([view[k] for k in names])
        owner = np.repeat(np.arange(len(names)), [len(view[k].faces) for k in names])
        body_i = names.index("machined_body")
        lo, hi = solids["machined_body"].bounds

        # T4.6 puts the decal on "each side of the car": any part but a wheel or the halo.
        # T4.7 puts the number "on the car body".
        car_i = np.array([i for i, k in enumerate(names) if not k.startswith(("wheel", "printed_hubcaps", "halo"))])

        def on_body(xs, ys, zs, d, allowed=(body_i,)):
            X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
            o = np.c_[X.ravel(), Y.ravel(), Z.ravel()]
            d = np.asarray(d, float)
            tri, ray = allm.ray.intersects_id(o, np.tile(d, (len(o), 1)), multiple_hits=False)
            ok = np.zeros(len(o), bool)
            ok[ray] = np.isin(owner[tri], allowed) & (allm.face_normals[tri] @ -d >= 0.3)
            return ok.reshape(X.shape).squeeze()

        def fits(grid, a, b):          # an a x b window of grid points, either way round
            c = np.pad(grid.astype(int).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
            for h, w in ((a, b), (b, a)):
                if grid.shape[0] >= h and grid.shape[1] >= w:
                    s = c[h:, w:] - c[:-h, w:] - c[h:, :-w] + c[:-h, :-w]
                    if (s == h * w).any():
                        return True
            return False

        side = on_body(np.arange(lo[0] - 45.0, hi[0] + 45.0, 1.0), [hi[1] + 50.0], np.arange(0.5, 65.0, 1.0), (0, -1, 0),
                       allowed=car_i)
        def tallest(grid, w):          # tallest all-good run of rows across any w columns
            if grid.shape[0] < w:
                return 0
            col = np.lib.stride_tricks.sliding_window_view(grid, w, axis=0).all(axis=-1)   # (nx-w+1, nz)
            best = 0
            for c in col:
                run = 0
                for v in c:
                    run = run + 1 if v else 0
                    best = max(best, run)
            return best

        ok46 = fits(side, 31, 16)
        r["T4.6_logo_decal_room"] = _entry(
            0.0 if ok46 else -1.0,
            "30 x 15 mm decal fits on the side" if ok46 else
            f"no 30 x 15 mm patch of the car seen from the side: tallest 30 mm wide patch "
            f"{max(tallest(side, 31) - 1, 0)} mm, longest 15 mm tall {max(tallest(side.T, 16) - 1, 0)} mm, "
            f"{int(side.sum())} of {side.size} points usable")
        if "halo" in stl:
            ref_a = assembly["x_front_mm"] - 16.0
            xs = np.arange(ref_a, half("halo").bounds[0, 0], 1.0)
            top = on_body(xs, np.arange(lo[1], hi[1], 1.0), [hi[2] + 50.0], (0, 0, -1)) if len(xs) else np.zeros((0, 0))
            ok = top.ndim == 2 and fits(top, 9, 15)
            r["T4.7_team_number_room"] = _entry(0.0 if ok else -1.0,
                                                "8 mm number fits ahead of the halo" if ok
                                                else "no 8 x 14 mm patch of body between Ref A and the halo")
    return r


def _clear_air(pts, others: dict, need_mm: float = 5.0) -> dict:
    """Closest approach (mm) from points on a wing to the other parts and the track."""
    gaps = {k: _nearest_gap_m(m, pts) for k, m in others.items()}
    gaps["track"] = float(pts[:, 2].min())
    worst = min(gaps, key=gaps.get)
    return _entry(gaps[worst] - need_mm, f"{gaps[worst]:.2f} mm to {worst}")


def _hidden_from_front(pts, ahead: dict, what: str) -> dict:
    """Points on a part, looking forward: how many have another part in the way."""
    dirs = np.tile([-1.0, 0.0, 0.0], (len(pts), 1))
    blocked = np.zeros(len(pts), bool)
    for m in ahead.values():
        blocked |= m.ray.intersects_any(pts + dirs * 1e-3, dirs)
    return _entry(0.0 if blocked.mean() <= 0.005 else -float(blocked.mean()),
                  f"{100 * blocked.mean():.1f} % of {what} is hidden")


# --------------------------------------------------------------- wings, measured
# T8.5-T8.6 and T9.4-T9.5 on the wing meshes themselves, not Part 4's design values.
# A wing file holds separate solids: the wing elements (they run across the span),
# and supports or end plates (narrow sideways). Measurements are in mm on the right half.
WING_ELEMENT_MIN_Y_MM = 12.5    # a wing element spans >= 25 per side; an end plate <= 10


def _section_polys(mesh, y):
    """Vertical sections of a mesh at y, as shapely polygons in (x, -z)."""
    s = mesh.section(plane_origin=[0.0, y, 0.0], plane_normal=[0.0, 1.0, 0.0])
    if s is None:
        return []
    to2d = np.array([[1.0, 0, 0, 0], [0, 0, -1.0, 0], [0, 1.0, 0, -y], [0, 0, 0, 1.0]])
    p, _ = s.to_planar(to_2D=to2d, check=False)
    return list(p.polygons_full)


def _thickness(poly) -> float:
    """Largest thickness of a section: the widest circle that fits inside (calipers
    closed on the thickest point, whatever the wing's tilt)."""
    lo, hi = 0.0, max(poly.bounds[2] - poly.bounds[0], poly.bounds[3] - poly.bounds[1])
    for _ in range(30):
        mid = 0.5 * (lo + hi)
        if poly.buffer(-mid / 2.0).is_empty:
            hi = mid
        else:
            lo = mid
    return lo


def _clip(mesh, normal, origin):
    """The part of a mesh on the side `normal` points to, or None."""
    import trimesh
    try:
        m = trimesh.intersections.slice_mesh_plane(mesh, normal, origin, cap=False)
    except (ValueError, IndexError):
        return None
    return m if m is not None and len(m.vertices) else None


def _wing_split(mesh_mm):
    pieces = mesh_mm.split(only_watertight=False)
    el = [p for p in pieces if p.extents[1] >= WING_ELEMENT_MIN_Y_MM]
    rest = [p for p in pieces if p.extents[1] < WING_ELEMENT_MIN_Y_MM]
    return el, rest


def _span_blocker_y(elements, others) -> float | None:
    """Furthest y out at which another part passes through the wing (each element's
    convex hull, so the gap between its surfaces counts but not the air around a wing
    that slopes or tilts): the span is split there (T8.6.1's figures). None if nothing does."""
    import trimesh
    y = None
    for e in elements:
        hull = e.convex_hull
        for m in others:
            if not m.is_volume:
                continue
            i = trimesh.boolean.intersection([m, hull], engine="manifold")
            if i is not None and not i.is_empty and abs(i.volume) > 1e-3:
                y = max(y or 0.0, float(i.bounds[1, 1]))
    return y


def _wing_sections(elements, n: int = 9):
    """Across the span (where the longest element exists): per y, each element's sections."""
    main = max(elements, key=lambda e: e.extents[1])
    y0, y1 = main.bounds[:, 1]
    out = []
    for y in np.linspace(y0 + 0.01, y1 - 0.01, n):
        polys = [p for e in elements for p in _section_polys(e, y)]
        if polys:
            out.append((y, polys))
    return out


def _wing_measures(prefix: str, rule: dict, elements, blockers, n_vanes_max: int) -> dict:
    """Span, chord, vane overlap and thickness of one wing, against `rule`'s ids."""
    r = {}
    y_hi = min(float(e.bounds[1, 1]) for e in elements)          # the shortest edge
    y_lo = max(float(e.bounds[0, 1]) for e in elements)
    cut = _span_blocker_y(elements, blockers)
    if rule["span_segments"]:                                    # front: 1 x 50 or 2 x 25
        if cut is None and y_lo <= 0.05:
            r[rule["span"]] = _entry(2 * y_hi - 50.0, f"{2 * y_hi:.2f} mm, one piece")
        else:
            seg = y_hi - max(cut or 0.0, y_lo)
            r[rule["span"]] = _entry(seg - 25.0, f"two segments of {seg:.2f} mm")
    else:                                                        # rear: one unbroken 50
        span = 2 * y_hi if (cut is None and y_lo <= 0.05) else y_hi - max(cut or 0.0, y_lo)
        r[rule["span"]] = _entry(span - 50.0, f"{span:.2f} mm unbroken")
    chords, thick, gaps, tops = [], [], [], []
    for y, polys in _wing_sections(elements):
        iv = sorted((p.bounds[0], p.bounds[2]) for p in polys)
        chords.append(max(b for _, b in iv) - iv[0][0])          # horizontal, LE to last TE
        reach = iv[0][1]
        for a, b in iv[1:]:
            gaps.append(a - reach)                               # > 0: the vanes do not overlap
            reach = max(reach, b)
        thick += [_thickness(p) for p in polys]
        tops.append(-min(p.bounds[1] for p in polys))
    if chords:
        r[rule["chord"] + "_min"] = _entry(min(chords) - 15.0, f"shortest {min(chords):.2f} mm")
        r[rule["chord"] + "_max"] = _entry(25.0 - max(chords), f"longest {max(chords):.2f} mm")
        r[rule["thick"] + "_min"] = _entry(min(thick) - 2.0, f"thinnest {min(thick):.2f} mm")
        r[rule["thick"] + "_max"] = _entry(6.0 - max(thick), f"thickest {max(thick):.2f} mm")
        r[prefix + "_vanes_overlap"] = _entry(
            0.0 if (not gaps or max(gaps) <= 0.0) and len(elements) <= n_vanes_max else -1.0,
            f"{len(elements)} element(s); " + (f"widest gap {max(gaps):.2f} mm" if gaps else "one element"))
        if "deviation" in rule:
            dev = max(tops) - min(tops)
            r[rule["deviation"]] = _entry(15.0 - dev, f"top surface varies {dev:.2f} mm")
    return r


def _wing_checks(assembly: dict, body_mm, parts_mm: dict) -> dict:
    """The wing rules measured on the wing files (mm)."""
    W, xf = assembly["W_mm"], assembly["x_front_mm"]
    ref_a, ref_b = xf - 16.0, xf + W + 16.0
    r = {}
    others = {k: m for k, m in parts_mm.items() if not k.startswith(("wheel", "fwing", "rwing"))}
    if "fwing" in parts_mm:
        el, rest = _wing_split(parts_mm["fwing"])
        plates = [p for p in rest if p.bounds[0, 1] > 0.5]       # off the centreline
        mounts = [p for p in rest if p.bounds[0, 1] <= 0.5]
        if el:
            r.update(_wing_measures("T8.6.2_front", {"span": "T8.6.1_front_span", "span_segments": True,
                                                     "chord": "T8.6.2_front_chord", "thick": "T8.6.3_front_thickness"},
                                    el, [body_mm] + list(others.values()) + mounts, 3))
            front = max(float(m.bounds[1, 0]) for m in el + plates)
            r["T8.5.2_front_wing_ahead_of_ref_A"] = _entry(ref_a - front, f"reaches {front - ref_a:+.2f} mm past Ref A")
            out = [c for e in el if (c := _clip(e, [0, 1.0, 0], [0, 15.0, 0])) is not None]
            if out:
                z = max(float(c.bounds[1, 2]) for c in out)
                r["T8.5.2_front_wing_height_outboard"] = _entry(20.0 - z, f"{z:.2f} mm high beyond 15 mm out")
        wheel_y = parts_mm["wheelF"].bounds[1, 1] if "wheelF" in parts_mm else 0.0
        for i, p in enumerate(plates):
            w = float(p.extents[1])
            r[f"T8.5.3_endplate{i}_width"] = _entry(10.0 - w, f"{w:.2f} mm wide")
            r[f"T8.5.3_endplate{i}_outside_span"] = _entry(float(p.bounds[0, 1]) - 25.0,
                                                           f"starts {p.bounds[0, 1]:.2f} mm out")
            c = _clip(p, [0, 1.0, 0], [0, wheel_y, 0])
            if c is not None:
                r[f"T8.5.3_endplate{i}_height"] = _entry(25.0 - float(c.bounds[1, 2]),
                                                         f"{c.bounds[1, 2]:.2f} mm high beyond the wheel")
        others = dict(others, **{f"fwing_support{i}": m for i, m in enumerate(mounts)})
    if "rwing" in parts_mm:
        el, rest = _wing_split(parts_mm["rwing"])
        # The wing's own pylon stands under it and does not break the span (T9.5.1).
        if el:
            r.update(_wing_measures("T9.5.2_rear", {"span": "T9.5.1_rear_span", "span_segments": False,
                                                    "chord": "T9.5.2_rear_chord", "thick": "T9.5.3_rear_thickness",
                                                    "deviation": "T9.5.4_rear_height_deviation"},
                                    el, [body_mm] + list(others.values()), 2))
        back = float(parts_mm["rwing"].bounds[0, 0])
        r["T9.4.1_rear_wing_behind_ref_B"] = _entry(back - ref_b, f"starts {back - ref_b:+.2f} mm behind Ref B")
    # T8.5.1 for the printed nose and the front wing's supports (the body's own nose is
    # measured in check()).
    ahead = [c for k, m in others.items() if k == "nose" or k.startswith("fwing_support")
             if (c := _clip(m, [-1.0, 0, 0], [ref_a - 0.5, 0, 0])) is not None]
    r["_nose_parts_zy"] = (max((float(c.bounds[1, 2]) for c in ahead), default=None),
                           max((float(c.bounds[1, 1]) for c in ahead), default=None))
    return r


# --------------------------------------------------------------- wheels, measured
TREAD_TOL_MM = 0.05     # a tread vertex is within this of the largest radius


def wheel_measures(mesh_mm) -> dict:
    """A wheel's own file (mm): diameter on the tread, and the track contact width,
    the axial length of the tread at full radius, so chamfers and fillets fall out (T7.4).
    The axle is the shortest bounding-box direction."""
    ax = int(np.argmin(mesh_mm.extents))
    v = mesh_mm.vertices - mesh_mm.bounds.mean(axis=0)
    r = np.hypot(*np.delete(v, ax, axis=1).T)
    R = float(r.max())
    tread = v[r >= R - TREAD_TOL_MM, ax]
    return {"diameter_mm": 2.0 * R, "contact_mm": float(tread.max() - tread.min())}


TEAM_WHEELS = {"front": "front_wheel.stl", "rear": "rear_wheel.stl"}


def _wheel_checks(assembly: dict, parts_mm: dict) -> dict:
    """T7.2, T7.3, T7.4, T7.5 measured: the wheel files themselves, and where the car's
    wheels stand (mm). assembly["wheel_files"] may name other files than the team's."""
    import trimesh
    from paths import PARTS
    files = assembly.get("wheel_files") or {k: str(PARTS["part1-simulation"] / "hardware_cad" / f)
                                            for k, f in TEAM_WHEELS.items()}
    r = {}
    for tag, need in (("front", 13.0), ("rear", 17.0)):
        m = wheel_measures(trimesh.load(files[tag], force="mesh"))
        d, w = m["diameter_mm"], m["contact_mm"]
        r[f"T7.5_{tag}_diameter_min"] = _entry(d - 28.0, f"{d:.2f} mm")
        r[f"T7.5_{tag}_diameter_max"] = _entry(32.0 - d, f"{d:.2f} mm")
        r[f"T7.4_{tag}_contact_width"] = _entry(w - need, f"{w:.2f} mm at full diameter")
    r["T7.1_four_wheels"] = _entry(0.0 if {"wheelF", "wheelR"} <= set(parts_mm) else -1.0,
                                   "a front and a rear wheel each side" if {"wheelF", "wheelR"} <= set(parts_mm)
                                   else "wheels missing: " + ", ".join(sorted({"wheelF", "wheelR"} - set(parts_mm))))
    for tag, name, need in (("front", "wheelF", 38.0), ("rear", "wheelR", 30.0)):
        if name in parts_mm:
            b = parts_mm[name].bounds
            gap = 2.0 * float(b[0, 1])
            r[f"T7.2_{tag}_gap"] = _entry(gap - need, f"{gap:.2f} mm between the wheels")
            # T7.6: on the track (the CFD wheels sit 0.3 mm into it); 0.05 mm of round-off.
            r[f"T7.6_{tag}_on_track"] = _entry(0.05 - float(b[0, 2]), f"lowest point {b[0, 2]:+.2f} mm")
    # T7.12.1: each wheel support only inside the cylinder through its axle's wheels.
    if "supports" in parts_mm and {"wheelF", "wheelR"} <= set(parts_mm):
        axles = {}
        for tag, name in (("front", "wheelF"), ("rear", "wheelR")):
            b = parts_mm[name].bounds
            axles[tag] = (float(b[:, 0].mean()), float(b[:, 2].mean()), float(b[1, 2] - b[0, 2]) / 2.0)
        for p in parts_mm["supports"].split(only_watertight=False):
            xc = float(p.bounds[:, 0].mean())
            tag = min(axles, key=lambda t: abs(axles[t][0] - xc))
            x0, z0, R = axles[tag]
            v = p.vertices
            far = float(np.hypot(v[:, 0] - x0, v[:, 2] - z0).max())
            key = f"T7.12.1_{tag}_support_in_cylinder"
            m = R - far
            if key not in r or m < r[key]["margin"]:
                r[key] = _entry(m, f"reaches {far:.2f} mm from the axle, wheel radius {R:.2f} mm")
    return r


# --------------------------------------------------------------- chamber, measured
def _x_section_holes(body_mm, x):
    """Holes in the body's cross-section at x, as shapely polygons in (y, z). A right
    half is mirrored first, so a bore cut by the symmetry plane closes into a hole."""
    from shapely import affinity
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    s = body_mm.section(plane_origin=[x, 0.0, 0.0], plane_normal=[1.0, 0.0, 0.0])
    if s is None:
        return []
    to2d = np.array([[0, 1.0, 0, 0], [0, 0, 1.0, 0], [1.0, 0, 0, -x], [0, 0, 0, 1.0]])
    p, _ = s.to_planar(to_2D=to2d, check=False)
    polys = [q.buffer(0) for q in p.polygons_full]
    if body_mm.bounds[0, 1] > -0.01:                              # a right half
        polys += [affinity.scale(q, -1.0, 1.0, origin=(0, 0)) for q in polys]
    u = unary_union([q.buffer(1e-4) for q in polys]).buffer(-1e-4)
    geoms = getattr(u, "geoms", [u])
    return [Polygon(i) for g in geoms for i in g.interiors]


def chamber_measures(body_mm) -> dict | None:
    """The cartridge chamber as a scrutineer finds it on the milled body (mm): the hole
    open at the back, its diameter along the minimum depth, centre height, depth from
    the rim to the end, and its angle to the track. None when there is no chamber."""
    x_back = float(body_mm.bounds[1, 0])
    holes = _x_section_holes(body_mm, x_back - 3.0)
    if not holes:
        return None
    h = max(holes, key=lambda q: q.area)
    yc, zc = h.centroid.x, h.centroid.y
    r0 = math.sqrt(h.area / math.pi)
    # The end of the bore: rays from behind the car, all round at 60 % of the radius (as a
    # depth gauge's rod would sit; one ray down the axis met the milled file's seam).
    ends = []
    for a in np.linspace(0.3, 2 * math.pi - 0.3, 8):
        o = [x_back + 5.0, yc + 0.6 * r0 * math.sin(a), zc + 0.6 * r0 * math.cos(a)]
        if body_mm.bounds[0, 1] > -0.01:                         # a right half: its own side
            o[1] = abs(o[1]) + 0.01
        loc, _, _ = body_mm.ray.intersects_location([o], [[-1.0, 0, 0]])
        if len(loc):
            ends.append(float(loc[:, 0].max()))
    if not ends:
        return None
    x_end = float(np.median(ends))
    # The rim: rays in the wall, 1.5 mm out from the bore, all round; the rim is where
    # the wall starts (the depth is measured from the opening, T5.3).
    rims = []
    for a in np.linspace(0.1, math.pi - 0.1, 9):
        o = [x_back + 5.0, max(yc + (r0 + 1.5) * math.sin(a), 0.01), zc + (r0 + 1.5) * math.cos(a)]
        loc, _, _ = body_mm.ray.intersects_location([o], [[-1.0, 0, 0]])
        if len(loc):
            rims.append(float(loc[:, 0].max()))
    x_rim = min(rims) if rims else x_back
    depth = x_rim - x_end
    # T5.1 by plug gauges, as scrutineers check a bore: the 18.0 mm plug must go in all
    # through the minimum depth, the 18.5 mm one must go in nowhere. A plug sees the widest
    # circle that fits each section. Calipers would also catch a narrow notch: the milled
    # file has one, where its two halves meet at y = 0 along the bore's top and bottom (lab
    # 2026-11-09: 0.85 mm deep, widest across 19.85 mm on a bore whose area is that of an
    # 18.16 mm circle). The real bore comes drilled in the block, so that notch is in the
    # file only; it is reported in the note, and as `chamber_widest_across_mm`.
    plug, across, area_d, cz = [], [], [], []
    for x in np.linspace(max(x_rim - 45.0, x_end) + 1.0, x_rim - 1.0, 7):
        hs = [q for q in _x_section_holes(body_mm, x) if q.distance(h.centroid) < r0]
        if not hs:
            plug.append(0.0)
            continue
        q = max(hs, key=lambda q: q.area)
        c = q.centroid
        plug.append(_thickness(q))
        # Across the bore, where it is a bore: the last 2 mm is the mouth, whose edge the
        # remesh rounds (Part 1 scan, 2026-11-09: 18.15 mm to 2 mm from the face, 21 mm at 0.6 mm).
        if x <= x_rim - 2.0:
            across.append(2.0 * max(math.hypot(px - c.x, pz - c.y) for px, pz in q.exterior.coords))
        area_d.append(2.0 * math.sqrt(q.area / math.pi))
        cz.append((x, c.y))
    ang = (math.degrees(math.atan2(cz[-1][1] - cz[0][1], cz[-1][0] - cz[0][0]))
           if len(cz) >= 2 else 0.0)
    return {"rim_x_mm": x_rim, "depth_mm": depth, "axis_z_mm": zc, "axis_y_mm": yc,
            "diameter_min_mm": min(plug), "diameter_max_mm": max(plug),
            # the bore's own size: the median section (the mouth's rounded edge is wider)
            "diameter_area_mm": float(np.median(area_d)) if area_d else 0.0,
            "chamber_widest_across_mm": max(across) if across else 0.0, "angle_deg": ang}


def _chamber_checks(ch: dict | None) -> dict:
    if ch is None:
        return {"T5_chamber_found": _entry(-1.0, "no chamber open at the back of the body")}
    d0, d1, z, dep, a = (ch["diameter_min_mm"], ch["diameter_max_mm"], ch["axis_z_mm"],
                         ch["depth_mm"], ch["angle_deg"])
    return {
        "T5.1_diameter_min": _entry(d0 - 18.0, f"18.0 plug: the bore takes {d0:.3f} mm all through"),
        "T5.1_diameter_max": _entry(18.5 - d1, f"18.5 plug: widest {d1:.3f} mm fits; "
                                               f"widest across {ch['chamber_widest_across_mm']:.2f} mm"),
        "T5.2_height_min": _entry(z - 30.0, f"centre {z:.2f} mm above the track"),
        "T5.2_height_max": _entry(40.0 - z, f"centre {z:.2f} mm above the track"),
        "T5.3_depth_min": _entry(dep - 45.0, f"{dep:.2f} mm deep"),
        "T5.3_depth_max": _entry(58.0 - dep, f"{dep:.2f} mm deep"),
        "T5.4_angle": _entry(3.0 - abs(a), f"{a:+.2f} deg to the track"),
        "T5.6_protrusion": _entry(CARTRIDGE_LENGTH_MIN_MM - dep - 5.0,
                                  f"shortest cartridge sticks out {CARTRIDGE_LENGTH_MIN_MM - dep:.2f} mm"),
    }


# --------------------------------------------------------------- tether guides, measured
def _tether_checks(parts_mm: dict, x_front: float, x_rear: float) -> dict:
    """T6.1 and T6.2 on the guides as made (mm): exactly two, each a closed ring within
    10 mm of its axle (ahead of the front, behind the rear), the hole taking a 3.5 mm tool
    and no more than a 6.0 mm one (the widest circle that fits through it)."""
    if "tethers" not in parts_mm:
        return {"T6.1_two_guides": _entry(-1.0, "no tether guides")}
    pieces = parts_mm["tethers"].split(only_watertight=False)
    r = {"T6.1_two_guides": _entry(0.0 if len(pieces) == 2 else -1.0, f"{len(pieces)} guide(s)")}
    mid = 0.5 * (x_front + x_rear)
    for p in pieces:
        x = float(p.bounds[:, 0].mean())
        tag = "front" if x < mid else "rear"
        off = x_front - x if tag == "front" else x - x_rear          # >= 0: on the outer side
        r[f"T6.1_{tag}_guide_position"] = _entry(min(off, 10.0 - off),
                                                 f"{off:+.2f} mm {'ahead of the front' if tag == 'front' else 'behind the rear'} axle")
        holes = _x_section_holes(p, x)
        if not holes:
            r[f"T6.3_{tag}_guide_closed"] = _entry(-1.0, "no closed hole through the guide")
            continue
        d = _thickness(max(holes, key=lambda q: q.area))
        r[f"T6.2_{tag}_hole_min"] = _entry(d - 3.5, f"{d:.2f} mm tool fits")
        r[f"T6.2_{tag}_hole_max"] = _entry(6.0 - d, f"{d:.2f} mm tool fits")
    return r


# --------------------------------------------------------------- halo and helmet, unchanged
HALO_FILE = "halo_helmet.stl"     # the official download (T4.4.1, T4.5), kept with the team's CAD


def _halo_checks(parts_mm: dict) -> dict:
    """T1.21 / T4.4.1 / T4.5: the halo and helmet are on the car and unchanged: the car's
    file has the official file's size in every direction, within 0.1 mm."""
    import trimesh
    from paths import PARTS
    if "halo" not in parts_mm:
        return {"T4.4.1_halo_unchanged": _entry(-1.0, "no halo on the car (T1.21: it must be)")}
    off = trimesh.load(str(PARTS["part1-simulation"] / "hardware_cad" / HALO_FILE), force="mesh")
    h = parts_mm["halo"]
    # Length, full width (the car's file is the right half, or both halves on the centreline)
    # and height. Volume is not compared: the official file is not a closed solid.
    # The official file is itself one half: the left, y -12.5 to 0 (the drawn width is 25.0, p56).
    def full_width(m):
        lo, hi = float(m.bounds[0, 1]), float(m.bounds[1, 1])
        return 2.0 * max(abs(lo), abs(hi)) if lo > -0.01 or hi < 0.01 else hi - lo
    car = np.array([h.extents[0], full_width(h), h.extents[2]])
    ref = np.array([off.extents[0], full_width(off), off.extents[2]])
    dims = float(np.abs(car - ref).max())
    return {"T4.4.1_halo_unchanged": _entry(
        0.1 - dims, f"length, width, height {np.round(car, 2).tolist()} mm (y {h.bounds[0, 1]:.2f} to "
                    f"{h.bounds[1, 1]:.2f}); official {np.round(ref, 2).tolist()} mm (file y "
                    f"{off.bounds[0, 1]:.2f} to {off.bounds[1, 1]:.2f})")}


def official_block_mm(rear_face_mm: float, slack_mm: float = 0.06, axis_z_mm: float = DEFAULT_AXIS_Z_MM):
    """The Model Block as it arrives (Appendix ii), placed in the car: rear face
    at the car's rear face, bore on the chamber axis, slot along the underside.
    slack_mm: every face eased by this, as the final remesh may move a surface
    0.05 mm. That is well below what the mill can tell apart."""
    import trimesh
    L, y = rc.BLOCK_LENGTH_MM, rc.BLOCK_WIDTH_MM / 2.0 + slack_mm
    z0 = axis_z_mm - rc.BLOCK_BORE_ABOVE_BOTTOM_MM
    block = trimesh.creation.box(bounds=[[rear_face_mm - L - slack_mm, -y, z0 - slack_mm],
                                         [rear_face_mm + slack_mm, y, z0 + rc.BLOCK_HEIGHT_MM + slack_mm]])
    d = rc.BLOCK_BORE_DEPTH_MM - slack_mm
    bore = trimesh.creation.cylinder(radius=rc.BLOCK_BORE_DIA_MM / 2.0 - slack_mm, height=d + 2.0, sections=96)
    bore.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
    bore.apply_translation([rear_face_mm - d / 2.0 + 1.0, 0.0, axis_z_mm])
    s = rc.BLOCK_SLOT_WIDTH_MM / 2.0 - slack_mm
    slot = trimesh.creation.box(bounds=[[rear_face_mm - L - 1.0, -s, z0 - 1.0],
                                        [rear_face_mm + 1.0, s, z0 + rc.BLOCK_SLOT_DEPTH_MM - slack_mm]])
    return trimesh.boolean.difference([block, bore, slot], engine="manifold")


def zone_polygons_mm(wheels: dict) -> dict:
    """The four T7.9 zones on the right side, (x, y) outlines in mm, drawn from where the
    car's wheels stand: wheels = {"front"|"rear": (x_axle, R, y_inner)}."""
    xf, Rf, fy = wheels["front"]
    xr, Rr, ry = wheels["rear"]
    w = rc.T79_WIDTH_Y_MM
    fa, ra, ff, rr = xf + Rf, xr - Rr, xf - Rf, xr + Rr
    t2 = w / math.tan(math.radians(rc.T79_2_ANGLE_DEG))
    t3 = w / math.tan(math.radians(rc.T79_3_ANGLE_DEG))
    return {
        "T7.9.1": [(ff - rc.T79_1_DEPTH_MM, fy), (ff, fy), (ff, fy + w), (ff - rc.T79_1_DEPTH_MM, fy + w)],
        "T7.9.2": [(fa, fy), (fa + rc.T79_2_NEAR_MM, fy), (fa + rc.T79_2_NEAR_MM + t2, fy + w), (fa, fy + w)],
        "T7.9.3": [(ra, ry), (ra, ry + w), (ra - rc.T79_3_NEAR_MM - t3, ry + w), (ra - rc.T79_3_NEAR_MM, ry)],
        "T7.9.4": [(rr, ry), (rr + rc.T79_4_DEPTH_MM, ry), (rr + rc.T79_4_DEPTH_MM, ry + w), (rr, ry + w)],
    }


def halo_pocket_mm(assembly: dict) -> dict:
    """The halo pocket's box (Appendix ix), its front where the halo's own front is when
    there is a halo file, else at Ref A + d_halo; floor at 24.0 (T4.4.4)."""
    halo = next((s["stl"] for s in assembly.get("extra_surfaces", []) if s["name"] == "halo"), None)
    if halo:
        import trimesh
        x0 = float(trimesh.load(halo, force="mesh").bounds[0, 0]) * 1e3
    else:
        x0 = assembly["x_front_mm"] - rc.REF_A_AHEAD_OF_FRONT_AXLE_MM + assembly["d_halo_mm"]
    z = rc.HALO_POCKET_FLOOR_Z_MM
    return {"x0": x0, "x1": x0 + rc.HALO_POCKET_LENGTH_MM, "half_w": rc.HALO_POCKET_WIDTH_MM / 2.0,
            "z0": z, "z1": z + rc.HALO_POCKET_DEPTH_MM}


def ballast_capsule_mm(pocket: dict, above_floor_mm: float = 1.0):
    """The legal ballast container (Appendix ix) as a solid in mm, open to the pocket."""
    import trimesh
    from shapely.geometry import LineString
    cx = pocket["x0"] + rc.BALLAST_CENTRE_FROM_POCKET_FRONT_MM
    half = (rc.BALLAST_LENGTH_MM - rc.BALLAST_WIDTH_MM) / 2.0
    m = trimesh.creation.extrude_polygon(
        LineString([(cx - half, 0.0), (cx + half, 0.0)]).buffer(rc.BALLAST_WIDTH_MM / 2.0, 32),
        rc.BALLAST_DEPTH_MM + above_floor_mm)
    m.apply_translation([0.0, 0.0, pocket["z0"] - rc.BALLAST_DEPTH_MM])
    return m


LEAD_G_CM3 = 11.34     # T1.22 names fishing lead; the densest common choice, so the most that fits


def ballast_checks(body_mm, pocket: dict, ballast_g: float) -> dict:
    """T1.22: ballast only in the container under the halo, reached through the halo's
    aperture. With ballast on board the container must be cut out of the body (open to
    the pocket) and hold that much lead. No ballast: nothing to check."""
    if not ballast_g or ballast_g <= 0:
        return {}
    cap = ballast_capsule_mm(pocket, above_floor_mm=0.0)
    vol = abs(cap.volume)
    held_g = vol * 1e-3 * LEAD_G_CM3
    foam = _volume_in(body_mm, cap)
    return {
        "T1.22_ballast_fits_container": _entry(
            held_g - ballast_g, f"{ballast_g:.2f} g of lead is {ballast_g / LEAD_G_CM3 * 1e3:.0f} mm3; "
                                f"the container holds {vol:.0f} mm3 ({held_g:.2f} g)"),
        "T1.22_ballast_container_open": _absent(foam, f"{foam:.1f} mm3 of body left in the ballast container"),
    }


def manufactured_checks(assembly: dict) -> dict:
    """Rules measured on the files that get made, read back from disk: nothing in
    the T7.9 zones, the body inside the real block, the tether line clear, the
    printed parts clear of the foam."""
    import trimesh
    from shapely.geometry import Polygon
    W, xf = assembly["W_mm"], assembly["x_front_mm"]
    files = {k: v["file"] for k, v in assembly["joints"]["manufactured"].items() if "file" in v}
    solids = {k: trimesh.load(f, force="mesh") for k, f in files.items()}
    r = {}
    open_files = [k for k, m in solids.items() if not m.is_volume]
    if open_files:     # nothing can be measured on these; the car is rejected, not a crash
        r["manufactured_files_measurable"] = _entry(-1.0, "not a solid: " + ", ".join(open_files))
        return r

    # T7.9 from where the wheels stand (the CFD wheel files: axle, radius, inner face).
    stl = {s["name"]: s["stl"] for s in assembly.get("extra_surfaces", [])}
    wheels = {}
    for tag, name, x_ax in (("front", "wheelF", xf), ("rear", "wheelR", xf + W)):
        if name in stl:
            b = trimesh.load(stl[name], force="mesh").bounds * 1e3
            wheels[tag] = (float(b[:, 0].mean()), float(b[1, 2] - b[0, 2]) / 2.0, float(b[0, 1]))
        else:
            R = assembly["wheel_design"][tag]["R_mm"]
            wheels[tag] = (x_ax, R, None)
    if all(w[2] is not None for w in wheels.values()):
        for rule, outline in zone_polygons_mm(wheels).items():
            zone = trimesh.creation.extrude_polygon(Polygon(outline), rc.T79_HEIGHT_MM)
            hits = {k: _volume_in(m, zone) for k, m in solids.items()}
            hits = {k: v for k, v in hits.items() if v > _ROUND_OFF_MM3}
            r[f"{rule}_zone_clear"] = _absent(sum(hits.values()), ", ".join(
                f"{k} {v:.1f} mm3" for k, v in hits.items()) or "nothing in the zone")
    else:
        r["T7.9_zones_measurable"] = _entry(-1.0, "no wheel files to place the zones by")

    body = solids["machined_body"]
    ch = chamber_measures(body)
    # Where the block was: its bore is drilled 52 mm from its rear face (Appendix ii), and the
    # mill can take the rear face back but not move the bore's end. So the block's rear face is
    # the measured bore end + 52 mm. (The body's own back put the block 0.77 mm forward on a car
    # whose back was milled back that much, 181 mm3 "outside" it; lab 2026-11-09.)
    rear_face = (ch["rim_x_mm"] - ch["depth_mm"] + rc.BLOCK_BORE_DEPTH_MM if ch
                 else float(body.bounds[1, 0]))
    axis_z = ch["axis_z_mm"] if ch else DEFAULT_AXIS_Z_MM
    over = trimesh.boolean.difference([body, official_block_mm(rear_face, axis_z_mm=axis_z)], engine="manifold")
    outside = abs(float(over.volume)) if over is not None and not over.is_empty else 0.0
    r["block_body_inside_official_block"] = _absent(outside, f"{outside:.1f} mm3 outside the block"
                                                    + (_where(over) if outside > _ROUND_OFF_MM3 else ""))
    # T5.5: "the entire circumference and depth of the chamber must not be intersected by
    # any object": nothing made, other than the body round it, inside the measured bore.
    if ch:
        bore = _x_cylinder(ch["diameter_area_mm"] / 2.0 - 0.05, ch["rim_x_mm"] - ch["depth_mm"] + 0.5,
                           ch["rim_x_mm"], ch["axis_z_mm"])
        bore.apply_translation([0.0, ch["axis_y_mm"], 0.0])
        hits = {k: _volume_in(m, bore) for k, m in solids.items()}
        hits = {k: v for k, v in hits.items() if v > _ROUND_OFF_MM3}
        r["T5.5_chamber_clear"] = _absent(sum(hits.values()), ", ".join(
            f"{k} {v:.1f} mm3" for k, v in hits.items()) or "nothing in the chamber")

    pk = halo_pocket_mm(assembly)
    place = assembly.get("cargo_placement")
    if place:
        x0, z0 = place["x_start_m"] * 1e3, place["z_base_m"] * 1e3
        L_, a, b = rc.CARGO_LENGTH_MM, rc.CARGO_WIDE_MM / 2.0, rc.CARGO_NARROW_MM / 2.0
        if place.get("flip"):
            a, b = b, a
        wedge = trimesh.creation.extrude_polygon(
            # Its top is on the pocket floor; 0.1 mm off it for the remesh's own move.
            Polygon([(x0, -a), (x0 + L_, -b), (x0 + L_, b), (x0, a)]),
            rc.CARGO_HEIGHT_MM - 0.1)
        wedge.apply_translation([0.0, 0.0, z0])
        # The rule lets the cargo share space with the ballast container, nothing else.
        # Only the part of the container inside the wedge is excused: crediting all of it
        # hid 180 mm3 of cargo that was outside the body.
        wanted = trimesh.boolean.difference([wedge, ballast_capsule_mm(pk)], engine="manifold")
        missing = abs(wanted.volume) - _volume_in(body, wanted)
        gap = trimesh.boolean.difference([wanted, body], engine="manifold") if missing > _ROUND_OFF_MM3 else None
        r["T4.2_cargo_inside_body"] = _absent(max(missing, 0.0), f"{max(missing, 0.0):.1f} mm3 missing"
                                              + (_where(gap) if gap is not None else ""))
        # "Wholly positioned between the front and rear wheel centre lines" (T4.2).
        lo, hi = x0 - wheels["front"][0], wheels["rear"][0] - (x0 + L_)
        r["T4.2_cargo_between_axles"] = _entry(min(lo, hi), f"{lo:.1f} mm behind the front axle, "
                                                            f"{hi:.1f} mm ahead of the rear")

    # T4.4.4: the floor itself, ahead of and behind the ballast slot, and the halo fits.
    pk = {"x_min_m": pk["x0"] / 1e3, "x_max_m": pk["x1"] / 1e3, "z_min_m": pk["z0"] / 1e3}
    px0 = pk["x_min_m"] * 1e3
    o = np.array([(px0 + dx, y, 70.0) for dx in (8.0, 48.0) for y in (-8.0, -1.0, 1.0, 8.0)])
    loc, ray, _ = body.ray.intersects_location(o, np.tile([0.0, 0.0, -1.0], (len(o), 1)))
    tops = [loc[ray == i, 2].max() if (ray == i).any() else np.nan for i in range(len(o))]
    off = float(np.nanmax(np.abs(np.array(tops) - pk["z_min_m"] * 1e3))) if not np.isnan(tops).any() else np.inf
    # T4.4.4 allows the notch centre +-1.0 mm (34 mm, floor at 24). Half of that is allowed
    # here: a 0.43 mm dip at two of eight points failed a car whose halo sits on the rest.
    r["T4.4.4_pocket_floor"] = _entry(0.5 - off, "no floor under the halo" if np.isinf(off)
                                      else f"within {off:.3f} mm of {pk['z_min_m'] * 1e3:.1f} mm; tops "
                                      f"{[round(float(t), 2) for t in tops]} at x {px0 + 8.0:.1f}/{px0 + 48.0:.1f}, "
                                      f"pocket x {px0:.1f}-{pk['x_max_m'] * 1e3:.1f}")
    halo = next((s["stl"] for s in assembly.get("extra_surfaces", []) if s["name"] == "halo"), None)
    if halo:
        hm = trimesh.load(halo, force="mesh")
        hm.apply_scale(1e3)
        lost = _volume_in(body, hm)
        r["T4.4.4_halo_fits_pocket"] = _absent(lost, f"{lost:.1f} mm3 of one half of the halo in the foam")
        if not r["T4.4.4_halo_fits_pocket"]["pass"]:      # where, so the carver's zone can be fixed
            i = trimesh.boolean.intersection([body, hm], engine="manifold")
            if i is not None and not i.is_empty:
                parts = [np.round(p.bounds, 2).tolist() for p in i.split(only_watertight=False)]
                r["T4.4.4_halo_fits_pocket"]["note"] += (f"; halo bounds mm {np.round(hm.bounds, 2).tolist()}"
                                                         f"; foam in halo, bounds mm {parts}")
    r.update(ballast_checks(body, halo_pocket_mm(assembly), float(assembly.get("ballast_g") or 0.0)))
    r.update(_visibility_checks(assembly, solids))
    nose_row = assembly["joints"]["parts"].get("nose")
    if nose_row is not None:     # a nose only surface-bonded at Ref A has no tenon holding it
        r["nose_has_tenon"] = _entry(0.0 if "pocket_cm3_per_side" in nose_row else -1.0, nose_row["joint"])

    printed = {k: m for k, m in solids.items() if k != "machined_body"}
    hits = {k: _volume_in(body, m) for k, m in printed.items()}
    hits = {k: v for k, v in hits.items() if v > _ROUND_OFF_MM3}
    r["fit_printed_parts_clear_of_foam"] = _absent(sum(hits.values()), ", ".join(
        f"{k} {v:.1f} mm3" for k, v in hits.items()) or "no overlap")

    # T6.1: the line runs only through the two guides. A bundle 2 mm across, from
    # one guide's centre to the other's, must hit nothing on the way.
    guides = assembly.get("info", {}).get("tethers", [])
    if len(guides) == 2:
        x0, x1 = guides[0]["x_mm"], guides[1]["x_mm"]
        z = guides[0]["bottom_mm"] + guides[0]["od_mm"] / 2.0
        o = np.array([(x0, y, z + dz) for y, dz in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1))], float)
        dirs = np.tile([1.0, 0.0, 0.0], (len(o), 1))
        blocked = []
        for k, m in solids.items():
            loc, _, _ = m.ray.intersects_location(o, dirs)
            if len(loc) and (loc[:, 0] < x1).any():
                blocked.append(k)
        r["T6.1_tether_line_clear"] = _entry(0.0 if not blocked else -1.0,
                                             "blocked by " + ", ".join(blocked) if blocked else "clear")

    # Even triangles throughout: no long slivers left in any file that gets made.
    parts = assembly["joints"]["manufactured"]
    meshed = {k: v for k, v in parts.items() if "max_edge_mm" in v}
    if meshed:
        worst = max(v["max_edge_mm"] for v in meshed.values())
        r["mesh_longest_edge"] = _entry(MESH_MAX_EDGE_MM - worst, f"{worst:.1f} mm")
        body_s = parts["machined_body"].get("faces_under_5deg_pct", 0.0)
        r["mesh_slivers_body"] = _entry(MESH_MAX_SLIVER_BODY_PCT - body_s, f"{body_s:.2f} % of faces under 5 deg")
        sk = max((k for k in meshed if k != "machined_body"), key=lambda k: meshed[k]["faces_under_5deg_pct"])
        slivers = meshed[sk]["faces_under_5deg_pct"]
        r["mesh_slivers_printed"] = _entry(MESH_MAX_SLIVER_PRINTED_PCT - slivers,
                                           f"{slivers:.2f} % of faces under 5 deg in {sk}")
    # Measured wall of every printed file (construction floors it at the print minimum;
    # this measures it). The printer's figure is still to come from the team: until then
    # PRINTED_MIN_WALL_MM, raised by setting P4_MIN_WALL_MM.
    walls = {k: _min_wall_mm(v["file"]) for k, v in parts.items()
             if k.startswith("printed_") and v.get("file") and os.path.exists(v["file"])}
    if walls:
        lim = float(os.environ.get("P4_MIN_WALL_MM", PRINTED_MIN_WALL_MM))
        k = min(walls, key=lambda q: walls[q][0])
        t, where = walls[k]
        e = _entry(t - (lim - WALL_MEASURE_TOL_MM), f"{t:.3f} mm in {k} at {where} (print minimum {lim} mm)")
        if os.environ.get("P4_WALL_GATE") != "1":
            # NOT A GATE YET (reviewer, 2026-11-14): on the reference cars and the first 186
            # carved cars it read 0.001-0.5 mm on every car, at pod ends and in the front
            # assembly, not yet traced to real walls or to the measure. Reported on every car;
            # it gates only once traced (P4_WALL_GATE=1 turns it on).
            e = dict(e, pass_=e["pass"], **{"pass": True}, note="NOT GATING (validation pending): " + e["note"])
        r["P4.printed_min_wall"] = e
    # The milled body: its thinnest wall straight across (an opposite face, so convex edges
    # and corners are not counted), against the team's machining minimum, no tolerance.
    body_file = parts.get("machined_body", {}).get("file")
    if body_file and os.path.exists(body_file):
        t, where = _min_wall_mm(body_file, n=8000)
        r["machined_min_wall"] = _entry(t - rc.MACHINED_MIN_WALL_MM,
                                        f"{t:.3f} mm at {where} (machining minimum {rc.MACHINED_MIN_WALL_MM} mm)")
    # T5.1-T5.4 and T5.6 are measured on the milled body in check().
    return r


def check(body_half_stl: str, assembly: dict, mass_state: dict | None = None,
          field_bodies: int | None = None, machined_stl: str | None = None) -> dict:
    """machined_stl: the milled body (pockets cut, nose removed, Part 4
    joints.py). T5.5 is probed on it -- a pocket must not thin the wall."""
    import trimesh
    W, xf = assembly["W_mm"], assembly["x_front_mm"]
    ref_a, ref_b = xf - 16.0, xf + W + 16.0
    body = trimesh.load(str(body_half_stl), force="mesh")
    parts = {s["name"]: trimesh.load(s["stl"], force="mesh") for s in assembly["extra_surfaces"]}
    # T3.3 / T1.1: only the listed components (the halo file carries the helmet).
    listed = {"wheelF", "wheelR", "supports", "halo", "fwing", "nose", "rwing", "tethers"}
    extra = sorted(set(parts) - listed)
    r_t33 = _entry(0.0 if not extra else -1.0, "other parts: " + ", ".join(extra) if extra else "listed parts only")
    everything = [body] + list(parts.values())
    non_wheel = [body] + [m for n, m in parts.items() if not n.startswith("wheel")]
    bb = lambda ms: np.vstack([m.bounds for m in ms]) * 1e3  # noqa: E731
    allb, nwb = bb(everything), bb(non_wheel)
    wheels_bb = bb([m for n, m in parts.items() if n.startswith("wheel")]) if any(
        n.startswith("wheel") for n in parts) else allb

    r = {"T3.3_only_listed_parts": r_t33}
    width = 2 * allb[:, 1].max()
    r["T3.4_width_min"] = _entry(width - REGS["T3.4_width_min"], f"{width:.1f} mm")
    r["T3.4_width_max"] = _entry(REGS["T3.4_width_max"] - width, f"{width:.1f} mm")
    top = allb[:, 2].max()
    r["T3.5_height"] = _entry(REGS["T3.5_height"] - top, f"{top:.1f} mm")
    lows = {"body": body.bounds[0, 2] * 1e3}
    lows.update({n: m.bounds[0, 2] * 1e3 for n, m in parts.items() if not n.startswith("wheel")})
    low_part = min(lows, key=lows.get)
    clr = lows[low_part]
    r["T3.7_clearance"] = _entry(clr - REGS["T3.7_clearance"],
                                 f"lowest non-wheel part: {low_part} at {clr:.2f} mm")
    # Wheelbase between the wheels as they stand (the layout's W when there are none).
    if "wheelF" in parts and "wheelR" in parts:
        wb = float(parts["wheelR"].bounds[:, 0].mean() - parts["wheelF"].bounds[:, 0].mean()) * 1e3
    else:
        wb = W
    r["T7.3_W_min"] = _entry(wb - REGS["T7.3_W_min"], f"{wb:.2f} mm")
    r["T7.3_W_max"] = _entry(REGS["T7.3_W_max"] - wb, f"{wb:.2f} mm")
    front = nwb[:, 0].min()
    front_part = ["body"] + [n for n in parts if not n.startswith("wheel")]
    front_part = front_part[int(nwb[:, 0].argmin()) // 2]   # bb stacks 2 rows per mesh
    r["T8.2_nose_overhang"] = _entry(REGS["T8.2_nose_overhang"] - (ref_a - front),
                                     f"{ref_a - front:.1f} mm ahead of Ref A ({front_part})")
    rear = allb[:, 0].max()
    r["T9.4.2_rear_overhang"] = _entry(REGS["T9.4.2_rear_overhang"] - (rear - ref_b),
                                       f"{rear - ref_b:.2f} mm behind Ref B")

    # Wings measured on their own meshes; the printed nose and the wing mount ahead of Ref A.
    def mm(m):
        c = m.copy()
        c.apply_scale(1e3)
        return c
    wr =_wing_checks(assembly, mm(body), {n: mm(m) for n, m in parts.items()})
    pz, py = wr.pop("_nose_parts_zy")
    r.update(wr)
    r.update(_wheel_checks(assembly, {n: mm(m) for n, m in parts.items()
                                      if n.startswith("wheel") or n == "supports"}))
    xF = float(parts["wheelF"].bounds[:, 0].mean()) * 1e3 if "wheelF" in parts else xf
    xR = float(parts["wheelR"].bounds[:, 0].mean()) * 1e3 if "wheelR" in parts else xf + W
    r.update(_tether_checks({n: mm(m) for n, m in parts.items() if n == "tethers"}, xF, xR))
    r.update(_halo_checks({n: mm(m) for n, m in parts.items() if n == "halo"}))

    # Nose: body material forward of Ref A, and the printed nose and wing supports there.
    v = body.vertices * 1e3
    nose = v[v[:, 0] < ref_a - 0.5]
    zs = ([float(nose[:, 2].max())] if len(nose) else []) + ([pz] if pz is not None else [])
    ys = ([float(nose[:, 1].max())] if len(nose) else []) + ([py] if py is not None else [])
    if zs:
        r["T8.5.1_nose_z"] = _entry(REGS["T8.5.1_nose_z"] - max(zs), f"{max(zs):.2f} mm high")
        r["T8.5.1_nose_half_width"] = _entry(REGS["T8.5.1_nose_half_width"] - max(ys), f"{max(ys):.2f} mm out")

    # Model Block: milled body is everything aft of Ref A.
    milled = v[v[:, 0] >= ref_a - 0.5]
    L = milled[:, 0].max() - milled[:, 0].min()
    Wd = 2 * milled[:, 1].max()
    H = milled[:, 2].max() - milled[:, 2].min()
    r["block_length"] = _entry(REGS["block_length"] - L, f"{L:.1f} mm")
    r["block_width"] = _entry(REGS["block_width"] - Wd, f"{Wd:.1f} mm")
    r["block_height"] = _entry(REGS["block_height"] - H, f"{H:.1f} mm")

    # T4.1 one piece.
    n_mesh = len(body.split(only_watertight=False))
    n = field_bodies if field_bodies is not None else n_mesh
    r["T4.1_single_body"] = _entry(0.0 if n == 1 else -1.0, f"{n} bodies")

    # Every non-wheel part must touch the body. The mass term can carve the
    # printed nose away (seen 2026-09-26), leaving the front-wing mount in air.
    for name, m in parts.items():
        if name.startswith("wheel"):
            continue
        v = np.asarray(m.vertices)[:: max(1, len(m.vertices) // 4000)]
        # Over the surface as well as the vertices: a box has only its corners, and
        # none of them need be anywhere near where it meets the body.
        v = np.vstack([v, trimesh.sample.sample_surface(m, 4000, seed=1)[0]])
        # Embedded counts: an extruded strut has vertices only at its ends,
        # 2 mm inside the body and nowhere near its surface.
        gap = 0.0 if _contains(body, v).any() else _nearest_gap_m(body, v) * 1e3
        if name == "fwing" and "nose" in parts:      # printed as one with the nose
            gap = min(gap, _nearest_gap_m(parts["nose"], v) * 1e3)
        r[f"attached_{name}"] = _entry(0.3 - gap, f"closest {gap:.2f} mm to the body")

    # T5.5 chamber wall (probe points inside the body).
    # Measured on the file that is milled (mm, both halves) where there is one: the half-body
    # copy read 0 % on a car whose milled file has the full 3 mm wall (31015/8, 1 in 400).
    made = (assembly.get("joints", {}).get("manufactured", {}).get("machined_body") or {}).get("file")
    if made:
        probe_body = trimesh.load(made, force="mesh")
        probe_body.apply_scale(1e-3)
    else:
        probe_body = trimesh.load(machined_stl, force="mesh") if machined_stl else body
    # The chamber itself, found and measured on that body (T5.1-T5.4, T5.6); the wall
    # (T5.5) is then probed round the chamber that is there, not the one designed.
    pm = probe_body.copy()
    pm.apply_scale(1e3)
    ch = chamber_measures(pm)
    r.update(_chamber_checks(ch))
    if ch is not None:
        # T5.6: the protruding cartridge "visible in its entirety when viewed radially": no
        # part of the car round it, behind the body, over the length that sticks out.
        x0 = max(ch["rim_x_mm"], float(pm.bounds[1, 0])) + 0.1
        x1 = ch["rim_x_mm"] + CARTRIDGE_LENGTH_MIN_MM - ch["depth_mm"]
        if x1 > x0:
            slab = trimesh.creation.box(bounds=[[x0, -150.0, -10.0], [x1, 150.0, 150.0]])
            cart = _x_cylinder(ch["diameter_area_mm"] / 2.0, x0 - 1.0, x1 + 1.0, ch["axis_z_mm"])
            ring = trimesh.boolean.difference([slab, cart], engine="manifold")
            seen = {"body": body, **{n: m for n, m in parts.items()}}
            hits = {}
            for n, m in seen.items():
                mm_ = m.copy()
                mm_.apply_scale(1e3)
                if mm_.is_volume:
                    v = _volume_in(mm_, ring)
                    if v > _ROUND_OFF_MM3:
                        hits[n] = v
            r["T5.6_cartridge_seen_all_round"] = _absent(sum(hits.values()), ", ".join(
                f"{k} {v:.1f} mm3" for k, v in hits.items()) or "nothing round the cartridge")
        frac = t55_wall_fraction(probe_body, rear_face_mm=ch["rim_x_mm"], depth_mm=ch["depth_mm"],
                                 bore_r_mm=ch["diameter_area_mm"] / 2.0, axis_z_mm=ch["axis_z_mm"],
                                 angle_deg=ch["angle_deg"])
    else:
        frac = t55_wall_fraction(probe_body, rear_face_mm=W + xf + 16.0 + 40.0)
    r["T5.5_wall"] = _entry(0.0 if frac >= 0.999 else -(1 - frac) * REGS["T5.5_wall"],
                            f"{100*frac:.1f}% of the 3 mm annulus is solid")

    if mass_state is not None:
        # as manufactured when the joints report it: the scale reads the
        # parts that are made, not the model's rollup
        comp = mass_state.get("manufactured_mass_g", mass_state["competition_mass_g"])
        r["T3.6_mass"] = _entry(comp - REGS["T3.6_mass_g"],
                                f"{comp:.2f} g incl. {mass_state.get('ballast_g', 0):.2f} g ballast"
                                + (" (as manufactured)" if "manufactured_mass_g" in mass_state else ""))
        if "capacity_g" in mass_state:
            r["T1.22_ballast_capacity"] = _entry(mass_state["capacity_g"] - mass_state["ballast_g"])

    # T7.13 wheel safety test: a 3-finger claw hooks each wheel's inner corner
    # with a 1.5 x 1.5 mm lip (regulation figure, p.34). The annulus 1.5 mm
    # in from the inner face, over the outer 1.5 mm of radius, must be clear of
    # the body and every other part.
    # Where the wheels stand, measured on the car's wheels.
    lip = rc.CLAW_LIP_MM
    for tag in ("front", "rear"):
        wm = parts.get("wheelF" if tag == "front" else "wheelR")
        if wm is None:
            r[f"T7.13_{tag}_claw_clearance"] = _entry(-1.0, "no wheel to test")
            continue
        b = wm.bounds * 1e3
        x_ax, y_in, R, zc = b[:, 0].mean(), b[0, 1], (b[1, 2] - b[0, 2]) / 2.0, b[:, 2].mean()
        pts = []
        for yy in np.linspace(y_in - lip + 0.05, y_in - 0.05, 4):
            for rr in np.linspace(R - lip + 0.05, R - 0.05, 4):
                for t in np.linspace(0, 2 * math.pi, 36, endpoint=False):
                    pts.append((x_ax + rr * math.cos(t), yy, zc + rr * math.sin(t)))
        pts = np.array(pts) / 1e3
        pts = pts[pts[:, 2] > 0.0005]                    # above the track
        # Wings are exported as concatenated shells (wing + flap + mount), so
        # test each closed piece; an open piece cannot be tested and is named.
        hit, skipped, blocked = 0, [], {}
        for name, m in [("body", body)] + [(n, m) for n, m in parts.items()
                                           if not n.startswith("wheel")]:
            for piece in m.split(only_watertight=False):
                if piece.is_watertight:
                    inside = _contains(piece, pts)
                    if inside.any():
                        hit += int(inside.sum())
                        blocked.setdefault(name, []).extend(
                            np.round(pts[inside] * 1e3, 2).tolist())
                        blocked.setdefault(f"{name} piece bounds mm", []).append(
                            np.round(piece.bounds * 1e3, 2).tolist())
                else:
                    skipped.append(name)
        note = f"{hit} of {len(pts)} claw points blocked"
        if blocked:
            note += f"; blocked by {sorted(blocked)}; points mm {blocked}"
        if skipped:
            note += f"; open meshes not tested: {sorted(set(skipped))}"
        r[f"T7.13_{tag}_claw_clearance"] = _entry(0.0 if hit == 0 and not skipped else -1.0, note)

    j = assembly.get("joints")
    if j is not None and any("file" in v for v in j.get("manufactured", {}).values()):
        r.update(manufactured_checks(assembly))
    if j is not None:
        # every manufacturing file, RE-READ from disk, must be closed solids
        # and as many of them as the part has (an in-memory mesh can be closed
        # while the STL written from it is torn: 5 of 7 files were, 2026-09-30)
        bad = [k for k, v in j.get("manufactured", {}).items()
               if "closed" in v and not (v["closed"] and v["pieces"] == v["pieces_expected"])]
        r["manufacture_files_are_solids"] = _entry(
            0.0 if j["machined_body_watertight"] and not bad else -1.0,
            "not solid: " + ", ".join(       # short: car rows keep 80 characters
                f"{k} closed {j['manufactured'][k]['closed']} pieces {j['manufactured'][k]['pieces']}"
                f"/{j['manufactured'][k]['pieces_expected']} remeshed {j['manufactured'][k].get('remeshed')}" for k in bad)
            if bad else
            ("milled half not watertight before the fuse" if not j["machined_body_watertight"]
             else f"{len(j.get('manufactured', {}))} files"))
    for k, m in assembly.get("gates", {}).items():
        r[f"P4.{k}"] = _entry(m, (f"bare beam (no pod fits at this axle): tightest slot corner {m:+.3f} mm against the {3.175} mm ball"
                                  if k.endswith("slot_corner_radius") else f"margin {m:+.3f}"))
    return r


def summary(report: dict) -> dict:
    failed = {k: v for k, v in report.items() if not v["pass"]}
    return {"n_checks": len(report), "n_failed": len(failed), "failed": sorted(failed)}


def _min_wall_mm(path: str, n: int = 4000, seed: int = 1) -> tuple:
    """Thinnest wall of a closed part (file in mm): from n area-uniform surface points a
    ray goes straight in along the inward normal; where it leaves the part through a face
    turned back toward it (normals at least 120 deg apart, i.e. an opposite wall, not a
    side face met at an edge or corner, where a ray only grazes) the length is the wall
    there. Returns (thinnest wall, where it is in mm)."""
    import trimesh
    m = trimesh.load(path, force="mesh")
    pts, fi = trimesh.sample.sample_surface_even(m, n, seed=seed)
    nrm = m.face_normals[fi]
    origins = pts - nrm * 1e-4
    loc, ray, tri = m.ray.intersects_location(origins, -nrm, multiple_hits=False)
    if not len(ray):
        return float("inf"), None
    opposite = (m.face_normals[tri] * nrm[ray]).sum(axis=1) < -0.5
    if not opposite.any():
        return float("inf"), None
    d = np.linalg.norm(loc[opposite] - pts[ray[opposite]], axis=1)
    i = int(np.argmin(d))
    return float(d[i]), np.round(pts[ray[opposite]][i], 2).tolist()
