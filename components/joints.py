"""
joints.py -- printed positives glued into machined negatives.

Team process (2026-09-27): wheel supports, nose cone and every other printed
part are POSITIVES glued ONTO NEGATIVES (pockets) in the main body, and the body
is 3-axis milled with a 6.25 mm ball-end cutter from the top and the bottom.

For each printed part P and the aero body B (right halves, metres):

    O      = P ∩ B                          the part's embedded volume
    fp     = O projected on the xy plane    its footprint
    plug   = prism(fp ⊕ r, from the open face to the far end of O)
    pocket = plug ∩ B                       what the mill removes

fp ⊕ r (a 3.125 mm buffer) is where the ball's CENTRE can go with its edge still
covering fp, so the milled pocket contains the plug; a straight prism to the
open face is what a vertical cutter can reach. The printed part is P ∪ pocket,
so the outside shape (and the CFD) is unchanged while plastic replaces foam
inside. The foam is then cut GLUE_GAP_MM larger than the plastic all round the
pocket: an exact fit does not go together, and glue needs somewhere to be.
Pockets never cut the T5.5 cartridge wall: parts are trimmed back from a keep-out
around it first.

    cut(parts, body_half, open_side, keep_out) -> JointResult per part
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

TOOL_R_MM = 3.125
FOAM_G_CM3 = 0.163
# Foam cut this much larger than the printed plug, per side. UNMEASURED: 0.1-0.2 mm
# is the usual SLS PA12 range. Set it from the first test print.
GLUE_GAP_MM = 0.15


@dataclass
class Joint:
    name: str
    open_side: str
    plug: object          # trimesh, right half, m
    pocket: object        # plug ∩ body
    printed: object       # (part - body) ∪ pocket
    pocket_cm3: float
    embedded_cm3: float
    fill: bool = True             # the printed part fills its pocket (a plug)
    plug_full: object = None      # the plug across BOTH halves
    cut_full: object = None       # what the mill removes: plug_full plus the glue gap
    part: object = None           # the part's right half as cut (one manifold, keep-out removed)
    printed_whole: object = None  # a pod: the whole printed solid, both halves, as made
    extra_plastic_cm3: float | None = None    # ... and what it adds to the part, both halves

    def mass_delta_kg(self, part_density_g_cm3: float) -> float:
        """Full-car (both halves) mass change vs 'foam body + whole part',
        which is what the mass rollup counted before joints existed."""
        if self.extra_plastic_cm3 is not None:
            # a pod: a hollow shell in place of the foam the channel removes
            return (self.extra_plastic_cm3 * part_density_g_cm3
                    - 2 * self.pocket_cm3 * FOAM_G_CM3) * 1e-3
        if not self.fill:
            # the part keeps its designed shape inside the slot (the team's
            # ribbed CAD beam): only the foam cut out of the slot changes
            return -2 * self.pocket_cm3 * FOAM_G_CM3 * 1e-3
        dv = self.pocket_cm3 * (part_density_g_cm3 - FOAM_G_CM3) \
            - self.embedded_cm3 * part_density_g_cm3
        return 2 * dv * 1e-3


def _bool(op, meshes):
    import trimesh
    return getattr(trimesh.boolean, op)(meshes, engine="manifold")


def _closed(pieces) -> list:
    """The shells a union can take. A sealed void in a part reads as a shell of negative
    volume, which stops the union (2 cars in 1200); without it the part is simply solid."""
    return [p for p in pieces if p.is_volume] or list(pieces)


def _machinable_outline(fp, r):
    """The pocket outline the ball clears around footprint fp. If fp is
    already a union of r-discs (every convex corner >= r) it is cut as is;
    otherwise it is grown by r so the milled pocket still contains it."""
    opened = fp.buffer(-r).buffer(r)
    if fp.area > 0 and fp.symmetric_difference(opened).area < 0.02 * fp.area:
        return fp
    return fp.buffer(r)


def _prism_y(poly_xz, y0_mm, y1_mm):
    import trimesh
    parts = [poly_xz] if poly_xz.geom_type == "Polygon" else list(getattr(poly_xz, "geoms", []))
    out = []
    for p in parts:
        if p.area < 1e-6:
            continue
        m = trimesh.creation.extrude_polygon(p.simplify(0.05), (y1_mm - y0_mm))
        # extrude along +z in (x, z)-as-(x, y) coordinates -> rotate so +z_local = +y
        m.apply_transform(np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1.0]]))
        m.apply_translation([0, y0_mm, 0])
        m.apply_scale(1e-3)
        if m.volume < 0:
            m.invert()
        out.append(m)
    return trimesh.util.concatenate(out) if out else None


def _footprint(mesh, axes=(0, 1)):
    """Projected outline of a mesh on two axes (mm). Holes are filled: the
    union of projected triangles leaves sliver gaps that are not real, and a
    pocket outline has none anyway."""
    from shapely.geometry import Polygon, MultiPolygon
    from shapely.ops import unary_union
    tri = mesh.vertices[mesh.faces][:, :, list(axes)] * 1e3
    polys = [Polygon(t) for t in tri if abs((t[1][0]-t[0][0])*(t[2][1]-t[0][1])-(t[1][1]-t[0][1])*(t[2][0]-t[0][0])) > 1e-9]
    u = unary_union(polys).buffer(0.02).buffer(-0.02)
    geoms = [u] if u.geom_type == "Polygon" else list(getattr(u, "geoms", []))
    filled = [Polygon(g.exterior) for g in geoms if g.area > 1e-6]
    return filled[0] if len(filled) == 1 else MultiPolygon(filled)


def _prism(poly, z0_mm, z1_mm, half: bool = True):
    """Extrude a footprint between two heights. half=False keeps both sides of
    the centreline: one solid with no seam on the symmetry plane."""
    import trimesh
    from shapely.affinity import scale
    from shapely.geometry import box
    # Close the outline with its own mirror image first: an edge that runs a
    # few um off the centreline (buffer round-off) would leave a paper-thin
    # foam wedge between the pocket and the symmetry plane.
    poly = poly.union(scale(poly, yfact=-1.0, origin=(0, 0))).buffer(0.05).buffer(-0.05)
    if half:
        poly = poly.intersection(box(-1e3, 0.0, 1e3, 1e3))   # right half only
    parts = [poly] if poly.geom_type == "Polygon" else list(getattr(poly, "geoms", []))
    out = []
    for p in parts:
        if p.area < 1e-6:
            continue
        m = trimesh.creation.extrude_polygon(p.simplify(0.05), z1_mm - z0_mm)
        m.apply_translation([0, 0, z0_mm])
        m.apply_scale(1e-3)
        out.append(m)
    return trimesh.util.concatenate(out) if out else None


def t55_keep_out(x0_mm: float, x1_mm: float):
    """Cylinder around the cartridge chamber a pocket may not enter (T5.5 wall
    plus the cutter radius plus 0.5 mm)."""
    import trimesh
    from geometry_contract import CHAMBER_AXIS_Z_MM as z_axis_mm, MODEL_BLOCK_BORE_DIA_MM as bore
    r_mm = bore / 2.0 + 3.0 + TOOL_R_MM + 0.5
    c = trimesh.creation.cylinder(radius=r_mm / 1e3, height=(x1_mm - x0_mm) / 1e3, sections=64)
    c.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
    c.apply_translation([(x0_mm + x1_mm) / 2e3, 0.0, z_axis_mm / 1e3])
    return c


def cut(name: str, part, body_half, open_side: str = "bottom", keep_out=None,
        tool_r_mm: float = TOOL_R_MM, embed_mm: float | None = 4.0,
        fill: bool = True, embed_probe=None) -> Joint | None:
    """embed_mm: how far into the body the printed part reaches, measured in
    from its outermost embedded point (in y for side parts, z for top/bottom).
    The rest of what the CAD buries in the body is dropped: a CAD support pod
    reaching the centreline would otherwise make a 16 g plug.
    embed_probe: measure the embedded volume with this instead of the part. A part made
    from the body itself shares its surfaces exactly, which a boolean can read as empty."""
    import trimesh
    # Parts are exported as concatenated shells (wing + pylon overlap); make
    # them one manifold first or the booleans see nothing.
    pieces = part.split(only_watertight=False)
    if len(pieces) > 1:
        part = _bool("union", _closed(pieces))
    if keep_out is not None:
        part = _bool("difference", [part, keep_out])
    O_full = _bool("intersection", [part if embed_probe is None else embed_probe, body_half])
    if O_full is None or O_full.is_empty or abs(O_full.volume) < 1e-12:
        return None
    O = O_full
    if embed_mm is not None and open_side != "side":   # a through-slot takes the whole beam
        b = O_full.bounds * 1e3
        if open_side == "top":           # parts on top: keep the top embed_mm
            slab = trimesh.creation.box(bounds=[[b[0, 0] - 1, -1, (b[1, 2] - embed_mm)],
                                                [b[1, 0] + 1, 1e3, b[1, 2] + 1]])
        elif b[1, 1] - b[0, 1] > b[1, 2] - b[0, 2]:   # side part: outermost y band
            slab = trimesh.creation.box(bounds=[[b[0, 0] - 1, b[1, 1] - embed_mm, b[0, 2] - 1],
                                                [b[1, 0] + 1, b[1, 1] + 1, b[1, 2] + 1]])
        else:                             # under the body: lowest z band
            slab = trimesh.creation.box(bounds=[[b[0, 0] - 1, -1, b[0, 2] - 1],
                                                [b[1, 0] + 1, 1e3, b[0, 2] + embed_mm]])
        slab.apply_scale(1e-3)
        O = _bool("intersection", [O_full, slab])
        if O is None or O.is_empty:
            O = O_full
    if open_side == "side":
        # Through-slot along y, machined from the left and right (team setups).
        fp = _machinable_outline(_footprint(O, (0, 2)), tool_r_mm)
        plug = _prism_y(fp, 0.0, body_half.bounds[1, 1] * 1e3 + 1.0)
        cut_full = _full(_prism_y(fp.buffer(GLUE_GAP_MM), 0.0, body_half.bounds[1, 1] * 1e3 + 1.0))
    else:
        fp = _machinable_outline(_footprint(O), tool_r_mm)
        zb, zt = body_half.bounds[:, 2] * 1e3
        oz0, oz1 = O.bounds[:, 2] * 1e3
        z0, z1 = (zb - 1.0, oz1) if open_side == "bottom" else (oz0, zt + 1.0)
        plug, plug_full = _prism(fp, z0, z1), _prism(fp, z0, z1, half=False)
        g = GLUE_GAP_MM
        cut_full = _prism(fp.buffer(g), z0 - (g if open_side != "bottom" else 0.0),
                          z1 + (g if open_side != "top" else 0.0), half=False)
    if plug is None:
        return None
    if open_side == "side":
        plug_full = _full(plug)
    if keep_out is not None:
        plug = _bool("difference", [plug, keep_out])
        plug_full = _bool("difference", [plug_full, keep_out])
        cut_full = _bool("difference", [cut_full, keep_out])
    pocket = _bool("intersection", [plug, body_half])
    if fill:
        outside = _bool("difference", [part, body_half])
        printed = _bool("union", [outside, pocket])
    else:
        printed = part
    return Joint(name, open_side, plug, pocket, printed,
                 pocket_cm3=abs(pocket.volume) * 1e6, embedded_cm3=abs(O_full.volume) * 1e6,
                 fill=fill, plug_full=plug_full, cut_full=cut_full, part=part)


def pod_joint(part, body_half, channels: dict, keep_out=None) -> Joint | None:
    """The supports as pods (beam_support.py): at each axle the channel is
    milled from below across the whole width, and the printed support is the
    body's own shape there, hollowed to the wall thickness, with the plate,
    strip, disc and stub joined on. Its two end walls, which only face the
    foam, are opened to a rim (the glue land): lighter, and the unsintered
    powder falls out."""
    import manifold3d as m3
    import trimesh
    import beam_support as bsm

    def man(t):
        return m3.Manifold(m3.Mesh(vert_properties=np.array(t.vertices, np.float32, order="C"),
                                   tri_verts=np.array(t.faces, np.uint32, order="C")))

    def tm(M):
        # as manifold made it: merging vertices by position would pinch it
        o = M.to_mesh()
        return trimesh.Trimesh(np.asarray(o.vert_properties)[:, :3], np.asarray(o.tri_verts),
                               process=False)

    pieces = part.split(only_watertight=False)
    if len(pieces) > 1:
        part = _bool("union", _closed(pieces))
    y_max = body_half.bounds[1, 1] * 1e3 + 1.0
    plug = trimesh.util.concatenate([_prism_y(bsm.channel_outline(ch), 0.0, y_max)
                                     for ch in channels.values()])
    plug_full = trimesh.util.concatenate([_prism_y(bsm.channel_outline(ch), -y_max, y_max)
                                          for ch in channels.values()])
    cut_full = trimesh.util.concatenate([_prism_y(bsm.channel_outline(ch).buffer(GLUE_GAP_MM), -y_max, y_max)
                                         for ch in channels.values()])
    if keep_out is not None:
        plug = _bool("difference", [plug, keep_out])
        plug_full = _bool("difference", [plug_full, keep_out])
        cut_full = _bool("difference", [cut_full, keep_out])
    pocket = _bool("intersection", [plug, body_half])
    if pocket is None or pocket.is_empty or abs(pocket.volume) < 1e-12:
        return None
    body_full = man(_full(body_half))
    shells = []
    for ch in channels.values():
        one = _prism_y(bsm.channel_outline(ch), -y_max, y_max)
        if keep_out is not None:
            one = _bool("difference", [one, keep_out])
        lump = body_full ^ man(one)
        cavity = lump.minkowski_difference(m3.Manifold.sphere(ch["wall_mm"] * 1e-3, 12))
        if cavity.is_empty():
            shells.append(lump)
            continue
        shell = lump - cavity
        # the window through both end walls: the cavity drawn in by the rim,
        # stretched along the car
        # On a detailed cavity this step ran past 15 minutes (4 cars in 400). The window
        # does not need the detail: it only has to leave the rim.
        inner = cavity.simplify(3e-4).minkowski_difference(m3.Manifold.sphere(ch.get("rim_mm", 3.0) * 1e-3, 12))
        if not inner.is_empty():
            bb = cavity.bounding_box()
            cx = (bb[0] + bb[3]) / 2
            shell = shell - inner.translate((-cx, 0, 0)).scale((4.0, 1.0, 1.0)).translate((cx, 0, 0))
        shells.append(shell)
    whole = m3.Manifold.batch_boolean(shells + [man(_full(part))], m3.OpType.Add)
    # crumbs (under 1 mm3) the hollowing leaves where the wall is thinner than itself
    whole = m3.Manifold.batch_boolean([c for c in whole.decompose() if c.volume() > 1e-9 * 1e-3],
                                      m3.OpType.Add)
    embedded = _bool("intersection", [part, body_half])
    return Joint("supports", "bottom", plug, pocket, None,
                 pocket_cm3=abs(pocket.volume) * 1e6,
                 embedded_cm3=0.0 if embedded is None or embedded.is_empty else abs(embedded.volume) * 1e6,
                 plug_full=plug_full, cut_full=cut_full, part=part, printed_whole=tm(whole),
                 extra_plastic_cm3=(whole.volume() - 2 * abs(part.volume)) * 1e6)


def machined_body(body_half, joints, x_ref_a_mm: float | None = None):
    """The body the mill makes: aero body minus every pocket, minus the nose
    ahead of Ref A (printed separately)."""
    import trimesh
    b = body_half
    pockets = [j.pocket for j in joints if j is not None]
    if pockets:
        b = _bool("difference", [b] + pockets)
    if x_ref_a_mm is not None:            # boolean, not slice_mesh_plane: keeps it closed
        keep = trimesh.creation.box(bounds=[[x_ref_a_mm / 1e3, -0.01, -0.01], [1.0, 0.2, 0.2]])
        b = _bool("intersection", [b, keep])
    pieces = sorted(b.split(only_watertight=False), key=lambda m: -abs(m.volume))
    b = pieces[0]
    b.metadata["dropped_fragments_mm3"] = float(sum(abs(m.volume) for m in pieces[1:]) * 1e9)
    return b


# Which way each printed part's pocket opens. The rear wing sits over the
# cartridge chamber, where the body is only the 3 mm T5.5 wall: no pocket is
# possible, so it is surface-bonded (cut() returns None after the keep-out).
# Supports are ONE piece per axle (team spec): discs and stubs at both ends are
# wider than the beam, so the beam cannot slide through a side slot -- it drops
# in from below into a full-width channel, and the printed part includes the
# keel that fills the channel under the beam (the v2 CAD beam already reaches
# down to z 4.5 mm, i.e. the team does this).
OPEN_SIDE = {"supports": "bottom", "fwing": "bottom", "tethers": "bottom",
             "rwing": "top", "nose": "bottom"}
DENSITY_G_CM3 = {"supports": 1.01, "fwing": 1.24, "rwing": 1.24, "tethers": 1.24,
                 "nose": 1.01}


def nose_part(body_half, x_ref_a_mm: float, tenon_mm: float = 8.0, tenon_half_w_mm: float = 4.0):
    """The printed nose: the body ahead of Ref A plus a tenon reaching
    `tenon_mm` aft of it (8 mm wide: the cutter needs >= 6.25)."""
    import trimesh
    ahead = trimesh.creation.box(bounds=[[-1.0, -0.01, -0.01], [x_ref_a_mm / 1e3, 0.2, 0.2]])
    nose = _bool("intersection", [body_half, ahead])
    if nose is None or nose.is_empty or abs(nose.volume) < 1e-12:
        return None
    zc = 0.5 * sum(nose.bounds[:, 2])
    ten = trimesh.creation.box(bounds=[[x_ref_a_mm / 1e3 - 0.001, 0.0, 0.0],
                                       [(x_ref_a_mm + tenon_mm) / 1e3, tenon_half_w_mm / 1e3, zc]])
    out = _bool("union", [nose, _bool("intersection", [ten, body_half])])
    out.metadata["tenon"] = ten
    return out


def make_all(body_half, assembly: dict, x_ref_a_mm: float, rear_face_mm: float,
             out_dir=None) -> dict:
    """Every joint on one car. Returns a report with the machined body, the
    printed parts and the full-car mass change per part (kg)."""
    import trimesh
    from pathlib import Path
    keep = trimesh.creation.box(bounds=[[x_ref_a_mm / 1e3, -0.01, -0.01], [1.0, 0.2, 0.2]])
    milled = _bool("intersection", [body_half, keep])          # aft of Ref A
    from geometry_contract import MODEL_BLOCK_BORE_DEPTH_MM
    ko = t55_keep_out(rear_face_mm - MODEL_BLOCK_BORE_DEPTH_MM - 4.0, rear_face_mm + 1.0)
    parts = {s["name"]: trimesh.load(s["stl"], force="mesh") for s in assembly["extra_surfaces"]
             if not s["name"].startswith("wheel") and s["name"] != "halo"}
    cone = parts.get("nose")                  # the CFD cone (Part 4 nose.py), if any
    np_ = nose_part(body_half, x_ref_a_mm)
    if np_ is not None:
        parts["nose"] = np_
    elif cone is not None:
        del parts["nose"]                     # no body ahead of Ref A: nothing to joint
    joints, report = [], {"parts": {}, "mass_delta_kg": {}}
    cad_supports = assembly.get("support") is None
    for name, mesh in parts.items():
        fill = not (name == "supports" and cad_supports)
        pods = assembly.get("info", {}).get("pod") if name == "supports" else None
        j = pod_joint(mesh, milled, pods, ko) if pods else cut(
            name, mesh, milled, OPEN_SIDE.get(name, "bottom"), ko,
            embed_mm=None if name == "supports" else 4.0, fill=fill,
            embed_probe=mesh.metadata.get("tenon") if name == "nose" else None)
        dm = 0.0
        if j is None:
            report["parts"][name] = {"joint": "surface bond (no pocket possible)"}
        else:
            joints.append(j)
            dm = j.mass_delta_kg(DENSITY_G_CM3.get(name, 1.24))
            if name == "nose":
                # The nose ahead of Ref A is already in the body's mass (Part 1's
                # nose density): only its tenon's pocket is new.
                dm = 2 * j.pocket_cm3 * (DENSITY_G_CM3["nose"] - FOAM_G_CM3) * 1e-3
            report["parts"][name] = {"joint": ("through-slot from the sides" if j.open_side == "side"
                                               else f"pocket from the {j.open_side}")
                                     + ("" if j.fill else " (part keeps its own shape)"),
                                     "pocket_cm3_per_side": j.pocket_cm3,
                                     "embedded_cm3_per_side": j.embedded_cm3}
        report["mass_delta_kg"][name] = dm
    mb = machined_body(milled, joints)
    report["machined_body_cm3_full"] = 2 * abs(mb.volume) * 1e6
    report["machined_body_watertight"] = bool(mb.is_watertight)
    report["dropped_fragments_mm3"] = mb.metadata.get("dropped_fragments_mm3", 0.0)

    # ---- what is actually made: one solid per file, both halves, in mm ----
    by = {j.name: j for j in joints}
    # The full body: the clean (un-pocketed) halves fused, THEN full-width
    # pockets cut. Fusing two pocketed halves left torn seams wherever a
    # pocket met the centreline (2026-09-30).
    body_full = _full(milled)
    if joints:
        body_full = _drop_dust(_bool("difference", [body_full] + [j.cut_full for j in joints]),
                               1e-9)
    # The block arrives with its bore. The 1 mm grid draws it slightly small, so the
    # exact one is cut here: this file is the car, and it must fit the real block.
    from geometry_contract import CHAMBER_AXIS_Z_MM, MODEL_BLOCK_BORE_DIA_MM
    bore_end = assembly["x_front_mm"] + assembly["W_mm"] + 56.0
    bore = trimesh.creation.cylinder(radius=MODEL_BLOCK_BORE_DIA_MM / 2e3,
                                     height=(MODEL_BLOCK_BORE_DEPTH_MM + 2.0) / 1e3, sections=96)
    bore.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
    bore.apply_translation([(bore_end - MODEL_BLOCK_BORE_DEPTH_MM / 2.0 + 1.0) / 1e3, 0.0,
                            CHAMBER_AXIS_Z_MM / 1e3])
    body_full = _bool("difference", [body_full, bore])
    # The halo pocket too, floor at exactly 24 mm (T4.4.4). Open to the top: T4.4.3 wants
    # the halo clear in plan view.
    from halo_pocket import ballast_capsule_mesh_m, compute_halo_pocket_box_m
    pk = compute_halo_pocket_box_m(x_ref_a_mm / 1e3, assembly["d_halo_mm"])
    body_full = _bool("difference", [body_full, trimesh.creation.box(
        bounds=[[pk["x_min_m"], pk["y_min_m"], pk["z_min_m"]], [pk["x_max_m"], pk["y_max_m"], 0.1]]),
        ballast_capsule_mesh_m(x_ref_a_mm / 1e3, assembly["d_halo_mm"])])
    made = {"machined_body": (body_full, FOAM_G_CM3, 1)}
    clean_body = _full(milled)

    def printed_full(j):
        """(part - body) U (plug n body), both halves. Computed as
        (part U (plug n body)) - machined body: the whole part overlaps the
        plug it sits in, so no two solids that merely TOUCH are ever unioned
        (that, and fusing pocketed halves, is what tore these files)."""
        if j.printed_whole is not None:           # a pod is already the whole printed solid
            return _drop_dust(_bool("difference", [j.printed_whole, body_full]), 1e-9)
        if not j.fill:
            return _full(j.printed)
        inside = _bool("intersection", [j.plug_full, clean_body])
        both = _bool("union", [_full(j.part), inside])
        return _drop_dust(_bool("difference", [both, body_full]), 1e-9)

    # every printed part's own solid ...
    P = {}
    for name, mesh in parts.items():
        if name in by:
            P[name] = printed_full(by[name])
        else:                     # surface-bonded: the part, trimmed at the body's surface
            pieces = mesh.split(only_watertight=False)
            whole = _full(_bool("union", _closed(pieces)) if len(pieces) > 1 else mesh)
            P[name] = _drop_dust(_bool("difference", [whole, clean_body]), 1e-9)
    if cone is not None:                             # the hollow cone joins the nose piece
        shell, drain = nose_shell(cone, assembly["nose"]["wall_mm"], x_ref_a_mm)
        P["nose"] = _bool("union", [P["nose"], shell]) if "nose" in P else shell
        if drain is not None:
            P["nose"] = _bool("difference", [P["nose"], drain])

    def front_rear(m):
        mid = 0.5 * (m.bounds[0, 0] + m.bounds[1, 0])
        out = []
        for side in (-1, 1):
            sel = [q for q in m.split(only_watertight=False) if side * (q.centroid[0] - mid) > 0]
            out.append(trimesh.util.concatenate(sel) if sel else None)
        return out

    # ... then the parts AS PRINTED. Around the front axle four of them want
    # the same space (the wing mount runs through the nose cone; the nose
    # tenon, the tether guide and the support keel overlap: 0.85 cm3 counted
    # twice, 2026-09-30). So: nose + front wing are one front assembly, each
    # tether guide is printed on its support, and the support wins any overlap.
    no_file = set()
    pa12 = DENSITY_G_CM3["supports"]
    if "supports" in P and not by["supports"].fill:
        # the team's own CAD supports keep their shape: their CAD is the file
        made["supports_team_cad"] = (P.pop("supports"), pa12, 2)
        no_file.add("supports_team_cad")
    elif "supports" in P:
        sup = front_rear(P.pop("supports"))
        teth = front_rear(P.pop("tethers")) if "tethers" in P else (None, None)
        pods = assembly.get("info", {}).get("pod", {})
        bare = front_rear(_full(parts["tethers"])) if pods and "tethers" in parts else (None, None)
        for tag, a_, b_, plain in zip(("front", "rear"), sup, teth, bare):
            if a_ is None:
                continue
            # In a pod the guide is just its ring and stalk. With its plug of body it brought
            # the body's own floor, lying on the pod's copy of that floor under 5 um away:
            # surfaces no STL can keep apart (a front support in 130 would not close).
            # Trimmed against the foam, as it may reach past the pod's channel.
            if b_ is not None and plain is not None and tag in pods:
                b_ = _drop_dust(_bool("difference", [plain, body_full]), 1e-9)
            u = _drop_dust(_bool("union", [a_, b_]), 1e-9) if b_ is not None else a_
            # The line runs through the supports too: a keel low enough to cross it gets the
            # guide's own bore, or the car is illegal for no reason (T6.1, 3 cars in 1600).
            guides = assembly.get("info", {}).get("tethers", [])
            if len(guides) == 2:
                z = (guides[0]["bottom_mm"] + guides[0]["od_mm"] / 2.0) / 1e3
                line = trimesh.creation.cylinder(radius=guides[0]["id_mm"] / 2e3, sections=32, segment=[
                    (guides[0]["x_mm"] / 1e3 - 2e-3, 0.0, z), (guides[1]["x_mm"] / 1e3 + 2e-3, 0.0, z)])
                u = _drop_dust(_bool("difference", [u, line]), 1e-9)
            pieces = _solid_shells(u)
            made[f"printed_support_{tag}"] = (pieces[0], pa12, 1)
            # A guide the support does not reach is its own part. A scrap of one under 1 % of
            # the support is not (2-11 mm3 files too small to remesh, 2 cars in 400).
            loose = [p for p in pieces[1:] if p.volume >= 0.01 * pieces[0].volume]
            if loose:
                made[f"printed_tether_{tag}"] = (trimesh.util.concatenate(loose),
                                                  DENSITY_G_CM3["tethers"], None)
    for tag, path in assembly.get("info", {}).get("hubcap_stls", {}).items():
        cap = trimesh.load(path, force="mesh")           # right side; the left is its mirror
        left = cap.copy()
        left.vertices[:, 1] *= -1
        left.invert()
        made[f"printed_hubcaps_{tag}"] = (trimesh.util.concatenate([cap, left]), pa12, 2)
    front = [P.pop(k) for k in ("nose", "fwing") if k in P]
    if front:
        solid = _bool("union", front) if len(front) > 1 else front[0]
        if "printed_support_front" in made:
            # end the tenon on a flat face 0.2 mm ahead of the support (its
            # channel takes the rest): a plane cuts cleanly, the keel's own
            # surface left a pinched edge
            x_cut = made["printed_support_front"][0].bounds[0, 0] - 2e-4
            if solid.bounds[1, 0] > x_cut:
                solid = _bool("intersection", [solid, trimesh.creation.box(
                    bounds=[[-1.0, -1.0, -1.0], [x_cut, 1.0, 1.0]])])
        # The solid nose or the wing mount can cut the cone's cavity off from its drain
        # (up to 2.2 cm3, 6 cars in 780). Sealed, it holds powder the mass doesn't count,
        # so it is printed solid, and the file and the mass both say so.
        solid = _fill_voids(_drop_dust(solid, 1e-9))
        made["printed_front_assembly"] = (solid, DENSITY_G_CM3["nose"], 1)
    for name, m in P.items():
        made[f"printed_{name}"] = (m, DENSITY_G_CM3.get(name, 1.24),
                                   2 if name == "tethers" else 1)
    report["manufactured"] = {k: {"cm3": abs(m.volume) * 1e6, "g": abs(m.volume) * 1e6 * rho,
                                  "pieces_expected": n} for k, (m, rho, n) in made.items()}
    report["manufactured_g"] = float(sum(v["g"] for v in report["manufactured"].values()))
    if out_dir is not None:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        # metres, right half: the analysis copy legality probes for T5.5
        report["machined_body_half_stl"] = str(out.parent / "machined_body_half.stl")
        mb.export(report["machined_body_half_stl"])
        for k, (m, _rho, _n) in made.items():
            if k not in no_file:
                done = report["manufactured"][k]
                done.update(_export_mm(m, out / f"{k}.stl", fair=(k == "machined_body")))
                if done["pieces_expected"] is None:   # a loose guide is as many pieces as it is
                    done["pieces_expected"] = done["pieces"]
        if assembly.get("wheel_design", {}).get("design") == "team_stl":
            # the team's wheels with the 6 mm bearing seat, in the STL's own frame (mm)
            import wheel as wh
            for tag, (mesh, *_rest) in zip(("front", "rear"), wh.team_wheel_meshes()):
                mesh.export(str(out / f"printed_wheel_{tag}_x2.stl"))
    return report


def nose_shell(cone_half, wall_mm: float, x_ref_a_mm: float):
    """The printed cone as it is printed: a hollow shell of `wall_mm`, both
    halves, ending at Ref A in a `wall_mm` bulkhead that glues to the body's
    front face and carries the tenon. A 3 mm hole through the bulkhead lets the
    SLS powder out of the cavity (a sealed shell keeps it: ~0.5 g/cm3). The
    CFD cone is a closed solid; printing THAT would weigh three times the
    shell the mass rollup assumes."""
    import trimesh
    outer = _full(cone_half)
    v = cone_half.vertices
    x_tip, x_root = v[:, 0].min(), v[:, 0].max()
    root = v[v[:, 0] > x_root - 1e-7]
    b0, z0, z1 = root[:, 1].max(), root[:, 2].min(), root[:, 2].max()
    h0, zc, w, L = (z1 - z0) / 2, (z1 + z0) / 2, wall_mm / 1e3, x_root - x_tip
    xa = x_ref_a_mm / 1e3
    ahead = trimesh.creation.box(bounds=[[-1.0, -0.2, -0.01], [xa, 0.2, 0.2]])
    if w >= 0.5 * min(b0, h0):
        # a wall this thick leaves no cavity worth printing: a SOLID cone.
        # With no ballast that is mass with no aero cost (the alternative is
        # a fatter body), and it needs no powder drain.
        return _bool("intersection", [outer, ahead]), None
    inner = outer.copy()
    inner.apply_translation([-x_root, 0.0, -zc])
    inner.apply_scale([(L - w) / L, (b0 - w) / b0, (h0 - w) / h0])
    inner.apply_translation([x_root, 0.0, zc])
    cavity = _bool("intersection", [inner, trimesh.creation.box(
        bounds=[[-1.0, -0.2, -0.01], [xa - w, 0.2, 0.2]])])
    drain = trimesh.creation.cylinder(radius=1.5e-3, height=0.02, sections=24)
    drain.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
    drain.apply_translation([xa, 0.0, zc + 0.5 * h0])      # above the tenon, on the centreline
    return _bool("difference", [_bool("intersection", [outer, ahead]), cavity]), drain


def _bridge_pinches(mesh_mm, written):
    """Fill the lines where a solid touches itself. An edge with four faces on it is not
    a solid in any STL, whatever the merge tolerance, so a box 0.1 mm past each such edge
    joins the two sides. None if the file has no such edge: it is open for some other
    reason. This closes a part touching itself along a line. It does not close surfaces
    lying under 5 um apart over a whole patch (some front supports, 1 car in 130)."""
    import trimesh
    edges, n = np.unique(written.edges_sorted, axis=0, return_counts=True)
    bad = edges[n > 2]
    if not len(bad):
        return None
    ends = written.vertices[bad]
    boxes = [trimesh.creation.box(bounds=[e.min(axis=0) - 0.1, e.max(axis=0) + 0.1]) for e in ends]
    return _bool("union", [mesh_mm] + boxes)


def _export_mm(mesh, path, fair: bool = False, bridges_left: int = 3) -> dict:
    """Write one manufacturing STL in MILLIMETRES (what CAM and slicers assume)
    and report what the file holds once re-read. Booleans leave vertices closer
    together than an STL's 32-bit floats can tell apart, which tears the
    surface on save; simplifying to 1 um in 32-bit first keeps it closed."""
    import manifold3d as m3
    import trimesh
    m = mesh.copy()
    m.apply_scale(1e3)
    # A very few cars still tear at 1 um (about 4 % of the search range): merging at
    # 10 and then 50 um closes them, far below what any machine here can make.
    for merge_mm in (1e-3, 1e-2, 5e-2):
        man = m3.Manifold(m3.Mesh(vert_properties=np.asarray(m.vertices, np.float32),
                                  tri_verts=np.asarray(m.faces, np.uint32))).simplify(merge_mm)
        o = man.to_mesh()
        tm = trimesh.Trimesh(np.asarray(o.vert_properties)[:, :3], np.asarray(o.tri_verts),
                             process=False)
        tm.merge_vertices()
        # a collapsed sliver is two triangles on the same three vertices, back to
        # back: zero volume, and four faces on each of its edges. Remove both.
        key = np.sort(tm.faces, axis=1)
        _u, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
        # Only faces that lost a vertex go: a zero-area triangle on three distinct
        # collinear vertices is what joins a T-junction, and dropping it opens the
        # surface along a line (front support at the pod's end, 2 Oct 2026).
        f = tm.faces
        kept = (f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])
        tm.update_faces((cnt[inv.ravel()] == 1) & kept)
        tm.remove_unreferenced_vertices()
        tm = _drop_dust(tm, 1.0)
        tm = _drop_crumbs(tm)
        if fair:                          # foam body only: printed parts stay exact
            import mesh_fairing
            tm = mesh_fairing.clean(tm)
        if not tm.is_winding_consistent:    # the merge can flip faces next to a pinch
            trimesh.repair.fix_normals(tm)
        tm.export(str(path))
        back = trimesh.load(str(path), force="mesh")
        # A volume, not just watertight: closed with flipped faces cannot be measured.
        if back.is_volume:
            break
    if not back.is_volume and bridges_left:
        whole = _bridge_pinches(m, back)    # a bridge can leave a new pinch beside it
        if whole is not None:
            whole.apply_scale(1e-3)
            return _export_mm(whole, path, fair, bridges_left - 1)
    return {"file": str(path), "closed": bool(back.is_volume),
            "pieces": len(back.split(only_watertight=False)),
            "file_cm3": abs(back.volume) / 1e3}


def _full(half, overlap_m: float = 1e-5):
    """Both halves as ONE solid. The halves only touch on the symmetry plane,
    and a boolean of two touching solids leaves them separate with coincident
    caps: once an STL merges the vertices every cap edge has four faces and
    the file is not a solid (measured 105 such edges on the front wing,
    2026-09-30). So each half is pushed 10 um through the plane first."""
    a = half.copy()
    a.vertices[np.abs(a.vertices[:, 1]) < 1e-9, 1] = -overlap_m
    b = a.copy()
    b.vertices[:, 1] *= -1
    b.invert()
    return _drop_dust(_bool("union", [a, b]), 1e-9)


def _fill_voids(mesh):
    """The mesh with its sealed voids filled, by a union with each void made solid and 0.2 %
    larger, so that it overlaps the walls round it instead of only touching them."""
    fills = []
    for shell in mesh.split(only_watertight=False):
        if shell.volume < 0 and shell.is_watertight:
            fill = shell.copy()
            fill.invert()
            centre = fill.centroid.copy()
            fill.apply_translation(-centre)
            fill.apply_scale(1.002)
            fill.apply_translation(centre)
            fills.append(fill)
    return _bool("union", [mesh] + fills) if fills else mesh


def _solid_shells(mesh) -> list:
    """The parts in a mesh, largest first. A shell of negative volume is a sealed void in
    another part, not a part: written alone it made a 2 mm3 inside-out file (1 car in 390).
    Leaving it out fills the void, which a print could not have emptied anyway."""
    shells = mesh.split(only_watertight=False)
    return sorted((s for s in shells if s.volume > 0), key=lambda s: -s.volume)


def _drop_crumbs(mesh, share: float = 0.01):
    """Remove shells under 1 % of the largest: a 2 mm3 scrap left inside a hollow nose
    by the wing mount's trim is not a part. Real second pieces (a pair of hubcaps) are
    the same size as the first, and a body cut in two stays in two, for T4.1 to reject."""
    import trimesh
    pieces = mesh.split(only_watertight=False)
    if len(pieces) < 2:
        return mesh
    big = max(abs(p.volume) for p in pieces)
    keep = [p for p in pieces if abs(p.volume) >= share * big]
    return mesh if len(keep) == len(pieces) else trimesh.util.concatenate(keep)


def _drop_dust(mesh, min_volume: float):
    """Remove closed shells smaller than `min_volume` (mesh units cubed).
    Pockets that meet the centreline leave foam slivers under 0.1 mm thick;
    each touches the body along an edge, which an STL cannot represent, and
    collapses to a zero-volume flap when written. 1 mm3 is dust, not a part."""
    import trimesh
    pieces = mesh.split(only_watertight=False)
    keep = [m for m in pieces if abs(m.volume) >= min_volume]
    return mesh if len(keep) == len(pieces) or not keep else trimesh.util.concatenate(keep)
