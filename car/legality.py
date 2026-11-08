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

import numpy as np

import paths  # noqa: F401

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
                      bore_r_mm: float | None = None, axis_z_mm: float | None = None) -> float:
    """Fraction of probe points inside the body in the 3 mm annulus around the
    chamber, along the whole bore (T5.5). 1.0 = a full 3 mm wall."""
    from geometry_contract import (CHAMBER_AXIS_Z_MM, MODEL_BLOCK_BORE_DEPTH_MM,
                                   MODEL_BLOCK_BORE_DIA_MM)
    depth_mm = MODEL_BLOCK_BORE_DEPTH_MM if depth_mm is None else depth_mm
    bore_r_mm = MODEL_BLOCK_BORE_DIA_MM / 2.0 if bore_r_mm is None else bore_r_mm
    axis_z_mm = CHAMBER_AXIS_Z_MM if axis_z_mm is None else axis_z_mm
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
CARTRIDGE_LENGTH_MIN_MM = 64.5     # Appendix vi: 65.00 -0.5
MESH_MAX_EDGE_MM = 8.0             # measured 1.9-7.6 after the remesh, 106 before it
MESH_MAX_SLIVER_BODY_PCT = 4.0     # measured 0.4-3.2 % after (highest at 0.3 mm), 3.3 % before
MESH_MAX_SLIVER_PRINTED_PCT = 12.0 # 5.7-11 % after, 25 % before: a wing's sharp trailing edge


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


def official_block_mm(rear_face_mm: float, slack_mm: float = 0.06):
    """The Model Block as it arrives (Appendix ii), placed in the car: rear face
    at the car's rear face, bore on the chamber axis, slot along the underside.
    slack_mm: every face eased by this, as the final remesh may move a surface
    0.05 mm. That is well below what the mill can tell apart."""
    import trimesh
    import geometry_contract as gc
    L, y = gc.MODEL_BLOCK_LENGTH_MM, gc.MODEL_BLOCK_WIDTH_MM / 2.0 + slack_mm
    block = trimesh.creation.box(bounds=[[rear_face_mm - L - slack_mm, -y, gc.MODEL_BLOCK_BOTTOM_Z_MM - slack_mm],
                                         [rear_face_mm + slack_mm, y, gc.MODEL_BLOCK_TOP_Z_MM + slack_mm]])
    d = gc.MODEL_BLOCK_BORE_DEPTH_MM - slack_mm
    bore = trimesh.creation.cylinder(radius=gc.MODEL_BLOCK_BORE_DIA_MM / 2.0 - slack_mm, height=d + 2.0, sections=96)
    bore.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
    bore.apply_translation([rear_face_mm - d / 2.0 + 1.0, 0.0, gc.CHAMBER_AXIS_Z_MM])
    s = gc.MODEL_BLOCK_SLOT_WIDTH_MM / 2.0 - slack_mm
    slot = trimesh.creation.box(bounds=[[rear_face_mm - L - 1.0, -s, gc.MODEL_BLOCK_BOTTOM_Z_MM - 1.0],
                                        [rear_face_mm + 1.0, s, gc.MODEL_BLOCK_SLOT_TOP_Z_MM - slack_mm]])
    return trimesh.boolean.difference([block, bore, slot], engine="manifold")


def manufactured_checks(assembly: dict) -> dict:
    """Rules measured on the files that get made, read back from disk: nothing in
    the T7.9 zones, the body inside the real block, the tether line clear, the
    printed parts clear of the foam."""
    import trimesh
    from shapely.geometry import Polygon
    import geometry_contract as gc
    from wheel_visibility_zones import zone_polygons_mm
    W, xf = assembly["W_mm"], assembly["x_front_mm"]
    files = {k: v["file"] for k, v in assembly["joints"]["manufactured"].items() if "file" in v}
    solids = {k: trimesh.load(f, force="mesh") for k, f in files.items()}
    r = {}
    open_files = [k for k, m in solids.items() if not m.is_volume]
    if open_files:     # nothing can be measured on these; the car is rejected, not a crash
        r["manufactured_files_measurable"] = _entry(-1.0, "not a solid: " + ", ".join(open_files))
        return r

    wd = assembly["wheel_design"]
    R = 0.5 * (wd["front"]["R_mm"] + wd["rear"]["R_mm"])
    for rule, outline in zone_polygons_mm(W, xf, R).items():
        zone = trimesh.creation.extrude_polygon(Polygon(outline), 65.0)
        hits = {k: _volume_in(m, zone) for k, m in solids.items()}
        hits = {k: v for k, v in hits.items() if v > _ROUND_OFF_MM3}
        r[f"{rule}_zone_clear"] = _absent(sum(hits.values()), ", ".join(
            f"{k} {v:.1f} mm3" for k, v in hits.items()) or "nothing in the zone")

    rear_face = xf + W + 16.0 + 40.0
    body = solids["machined_body"]
    outside = abs(float(trimesh.boolean.difference([body, official_block_mm(rear_face)],
                                                   engine="manifold").volume))
    r["block_body_inside_official_block"] = _absent(outside, f"{outside:.1f} mm3 outside the block")

    place = assembly.get("cargo_placement")
    if place:
        from virtual_cargo import (CARGO_HEIGHT_MM, CARGO_LENGTH_MM, CARGO_NARROW_WIDTH_MM,
                                   CARGO_WIDE_WIDTH_MM)
        x0, z0 = place["x_start_m"] * 1e3, place["z_base_m"] * 1e3
        L_, a, b = CARGO_LENGTH_MM, CARGO_WIDE_WIDTH_MM / 2.0, CARGO_NARROW_WIDTH_MM / 2.0
        if place.get("flip"):
            a, b = b, a
        wedge = trimesh.creation.extrude_polygon(
            # Its top is on the pocket floor; 0.1 mm off it for the remesh's own move.
            Polygon([(x0, -a), (x0 + L_, -b), (x0 + L_, b), (x0, a)]),
            CARGO_HEIGHT_MM - 0.1)
        wedge.apply_translation([0.0, 0.0, z0])
        # The rule lets the cargo share space with the ballast container, nothing else.
        # Only the part of the container inside the wedge is excused: crediting all of it
        # hid 180 mm3 of cargo that was outside the body.
        from halo_pocket import ballast_capsule_mesh_m
        capsule = ballast_capsule_mesh_m((xf - gc.D_HALO_REF_A_OFFSET_MM) / 1e3, assembly["d_halo_mm"])
        capsule.apply_scale(1e3)
        wanted = trimesh.boolean.difference([wedge, capsule], engine="manifold")
        missing = abs(wanted.volume) - _volume_in(body, wanted)
        r["T4.2_cargo_inside_body"] = _absent(max(missing, 0.0), f"{max(missing, 0.0):.1f} mm3 missing")

    # T4.4.4: the floor itself, ahead of and behind the ballast slot, and the halo fits.
    from halo_pocket import compute_halo_pocket_box_m
    pk = compute_halo_pocket_box_m((xf - gc.D_HALO_REF_A_OFFSET_MM) / 1e3, assembly["d_halo_mm"])
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
        slivers = max(v["faces_under_5deg_pct"] for k, v in meshed.items() if k != "machined_body")
        r["mesh_slivers_printed"] = _entry(MESH_MAX_SLIVER_PRINTED_PCT - slivers,
                                           f"{slivers:.2f} % of faces under 5 deg, worst file")

    bore, depth, axis = gc.MODEL_BLOCK_BORE_DIA_MM, gc.MODEL_BLOCK_BORE_DEPTH_MM, gc.CHAMBER_AXIS_Z_MM
    # These four compare design constants with the rule; they are not measurements.
    r["T5.1_diameter"] = _entry(min(bore - 18.0, 18.5 - bore), f"{bore} mm (constant)")
    r["T5.2_height"] = _entry(min(axis - 30.0, 40.0 - axis), f"{axis} mm (constant)")
    r["T5.3_depth"] = _entry(min(depth - 45.0, 58.0 - depth), f"{depth} mm (constant)")
    r["T5.6_protrusion"] = _entry(CARTRIDGE_LENGTH_MIN_MM - depth - 5.0, "constant")
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
    everything = [body] + list(parts.values())
    non_wheel = [body] + [m for n, m in parts.items() if not n.startswith("wheel")]
    bb = lambda ms: np.vstack([m.bounds for m in ms]) * 1e3  # noqa: E731
    allb, nwb = bb(everything), bb(non_wheel)
    wheels_bb = bb([m for n, m in parts.items() if n.startswith("wheel")]) if any(
        n.startswith("wheel") for n in parts) else allb

    r = {}
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
    r["T7.3_W_min"] = _entry(W - REGS["T7.3_W_min"])
    r["T7.3_W_max"] = _entry(REGS["T7.3_W_max"] - W)
    front = nwb[:, 0].min()
    r["T8.2_nose_overhang"] = _entry(REGS["T8.2_nose_overhang"] - (ref_a - front),
                                     f"{ref_a - front:.1f} mm ahead of Ref A")
    rear = allb[:, 0].max()
    r["T9.4.2_rear_overhang"] = _entry(REGS["T9.4.2_rear_overhang"] - (rear - ref_b),
                                       f"{rear - ref_b:.2f} mm behind Ref B")

    # Nose: body material forward of Ref A (the printed nose) and the wing mount.
    v = body.vertices * 1e3
    nose = v[v[:, 0] < ref_a - 0.5]
    if len(nose):
        r["T8.5.1_nose_z"] = _entry(REGS["T8.5.1_nose_z"] - nose[:, 2].max())
        r["T8.5.1_nose_half_width"] = _entry(REGS["T8.5.1_nose_half_width"] - nose[:, 1].max())

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
    from geometry_contract import FRONT_WHEEL_INNER_Y_MM as FY, REAR_WHEEL_INNER_Y_MM as RY
    wd = assembly.get("wheel_design", {})
    for tag, x_ax, y_in, key in (("front", xf, FY, "front"), ("rear", xf + W, RY, "rear")):
        R = wd.get(key, {}).get("R_mm", 14.05)
        zc = R - 0.3                                      # wheels sit 0.3 mm into the track
        pts = []
        for yy in np.linspace(y_in - 1.45, y_in - 0.05, 4):
            for rr in np.linspace(R - 1.45, R - 0.05, 4):
                for t in np.linspace(0, 2 * math.pi, 36, endpoint=False):
                    pts.append((x_ax + rr * math.cos(t), yy, zc + rr * math.sin(t)))
        pts = np.array(pts) / 1e3
        pts = pts[pts[:, 2] > 0.0005]                    # above the track
        # Wings are exported as concatenated shells (wing + flap + mount), so
        # test each closed piece; an open piece cannot be tested and is named.
        hit, skipped = 0, []
        for name, m in [("body", body)] + [(n, m) for n, m in parts.items()
                                           if not n.startswith("wheel")]:
            for piece in m.split(only_watertight=False):
                if piece.is_watertight:
                    hit += int(_contains(piece, pts).sum())
                else:
                    skipped.append(name)
        note = f"{hit} of {len(pts)} claw points blocked"
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
            "not one closed solid per part: " + ", ".join(bad) if bad else
            f"{len(j.get('manufactured', {}))} files")
    for k, m in assembly.get("gates", {}).items():
        r[f"P4.{k}"] = _entry(m)
    return r


def summary(report: dict) -> dict:
    failed = {k: v for k, v in report.items() if not v["pass"]}
    return {"n_checks": len(report), "n_failed": len(failed), "failed": sorted(failed)}
