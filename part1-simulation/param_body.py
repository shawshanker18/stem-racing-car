"""
param_body.py -- a parametric car body: lofted sections, sidepods and a floor.

The level-set carve (Stage 1) shapes the body for MASS only and the drag adjoint
cannot steer it (every drag-only step raised D20, 12 of 12, 2026-09-26), so the
body a designer would draw -- a smooth fuselage, sidepods around the cargo, a
floor -- was out of reach. This builds that body from ~20 numbers, then hands it
to the SAME rule machinery as every other body: build_unified_geometry's hard
masks (T4.2 cargo, T5.5 cartridge wall, halo pocket, ballast slot, T7.9 wheel
zones, the model-block envelope) are applied on top, so whatever the numbers
say, the result is as legal as a Stage-1 carve. A CFD search (part5
body_search.py) picks the numbers.

Shape, all in mm, car coordinates (x nose->tail, z up from the track):

  fuselage   superellipse sections |y/b|^p + |(z-zc)/h|^p <= 1 lofted through
             eight stations from Ref A to the rear face (half-width, top and
             bottom at each, monotone-cubic between them). The body ends at
             Ref A; the nose cone ahead of it is a printed part (Part 4).
  sidepods   a second, wide and low superellipse loft over [s_x0, s_x1] with
             `s_taper` mm ease at each end: what encloses the 52 mm T4.2 cargo.
  modes      32 smooth bumps (+) or dents (-) on the fuselage, mm.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, fields, replace
import numpy as np


@dataclass(frozen=True)
class BodyParams:
    # fuselage: half-width, top and bottom at STATIONS_U (the start car, from
    # the 2026-09-27 three-station loft n 10/20/6, max 18/32/5 at 0.35, rear 14/48/20)
    st_b: tuple = (10.0, 13.239184, 16.530612, 18.0, 17.786982, 17.147929, 15.908571, 14.0)
    st_zt: tuple = (20.0, 24.858776, 29.795918, 32.0, 32.852071, 35.408284, 40.365444, 48.0)
    st_zb: tuple = (6.0, 5.595102, 5.183673, 5.0, 5.798817, 8.195266, 12.842604, 20.0)
    p: float = 2.6                # section squareness: 2 ellipse, larger boxier
    # sidepods
    s_b: float = 28.0
    s_zt: float = 27.0
    s_zb: float = 12.0
    s_x0: float = 70.0
    s_x1: float = 142.0
    s_taper: float = 12.0
    s_p: float = 3.0
    # smooth blend radius where fuselage and sidepods meet (mm)
    blend_mm: float = 3.0
    # underfloor tunnel (inlet at x0, outlet at x1): a channel cut up into the
    # body's underside, |y| < ft_w, rising ft_h mm above the local floor in the
    # middle and easing to nothing over ft_ramp mm at each end. ft_h = 0 is off.
    ft_h: float = 0.0
    ft_w: float = 8.0
    ft_x0: float = 50.0
    ft_x1: float = 170.0
    ft_ramp: float = 25.0
    # sculpt modes: strengths (mm, + grows) of smooth bumps, mirrored left/right:
    # the first 32 on the fuselage (MODE_U x MODE_ANG_DEG), the rest on the sidepods
    # (SIDE_MODE_U x SIDE_MODE_ANG_DEG). A shorter list leaves the rest at zero.
    modes: tuple = (0.0,) * 56

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "BodyParams":
        d = {k: (tuple(v) if isinstance(v, list) else v) for k, v in d.items()
             if k not in _RETIRED}          # older search files still carry these
        unknown = set(d) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f"unknown body parameters {sorted(unknown)}")
        return cls(**d)


# parameters of the retired three-station loft, nose length and floor plate
# (2026-09-30): ignored when read, so older search records still load
_RETIRED = frozenset(("nose_len", "n_b", "n_zt", "n_zb", "x_max_frac", "m_b", "m_zt", "m_zb",
                      "r_b", "r_zt", "r_zb", "f_b", "f_z", "f_t"))

STATIONS_U = (0.0, 0.08, 0.2, 0.35, 0.5, 0.65, 0.82, 1.0)
MODE_U = (0.06, 0.18, 0.3, 0.42, 0.54, 0.66, 0.78, 0.9)
MODE_ANG_DEG = (15.0, 60.0, 120.0, 165.0)      # from the top, down the side
# On the sidepods too: most of the drag is in the wheels, and the flow onto and off
# them is shaped here. With fuselage modes only, these surfaces had 8 numbers.
SIDE_MODE_U = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)   # along s_x0..s_x1
SIDE_MODE_ANG_DEG = (20.0, 60.0, 100.0, 150.0)  # from the top, down the side
N_FUSELAGE_MODES = len(MODE_U) * len(MODE_ANG_DEG)      # 32
N_MODES = N_FUSELAGE_MODES + len(SIDE_MODE_U) * len(SIDE_MODE_ANG_DEG)   # 56
MODE_SIGMA_MM = 7.0


def _smin(a, b, k):
    """Polynomial smooth minimum (k = blend radius, mm); k = 0 is min()."""
    if k <= 0:
        return np.minimum(a, b)
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1 - h) + a * h - k * h * (1 - h)


# Search bounds (mm) of the scalar parameters, from the legal envelope
# (build_unified_geometry: y <= 20 ahead of x~80, <= 32 around the cargo) and
# the mandatory solids (cargo y +-27.5, z 14-24, 60 mm long, placed where it fits).
BOUNDS = {
    "p": (2.0, 4.0),
    "s_b": (26.5, 31.5), "s_zt": (24.5, 34.0), "s_zb": (4.0, 15.5),
    "s_x0": (55.0, 77.0), "s_x1": (137.0, 150.0), "s_taper": (4.0, 25.0), "s_p": (2.0, 5.0),
    # tunnel: 2 * ft_w >= 6.25 mm (the ball end cannot cut a narrower slot), and a
    # ceiling under the T4.2 cargo (z 16) wherever the floor is at 5 mm
    "ft_h": (0.0, 10.0), "ft_w": (3.2, 14.0), "ft_x0": (30.0, 120.0),
    "ft_x1": (100.0, 190.0), "ft_ramp": (5.0, 60.0),
}


def _superellipse_phi(y, z, b, zc, h, p):
    """Approximate signed distance (mm) to |y/b|^p + |(z-zc)/h|^p = 1."""
    b = np.maximum(b, 1e-3)
    h = np.maximum(h, 1e-3)
    r = (np.abs(y) / b) ** p + (np.abs(z - zc) / h) ** p
    return (r ** (1.0 / p) - 1.0) * np.minimum(b, h)


def phi_mm(bp: BodyParams, X, Y, Z, x_ref_a: float, x_rear: float, skin_mm: float = 0.0):
    """Signed distance field (mm, negative inside) on grids X, Y, Z (mm).

    skin_mm: the body grown by this. The tunnel is cut after the skin, from the skinned
    floor, so a 3 mm tunnel is 3 mm at any skin. Cut before it, the skin filled the tunnel
    in: at a 4 mm skin no tunnel under 4 mm existed, and its settings had no slope at all.

    The mandatory solids (T5.5 cartridge wall, halo deck) are NOT drawn here:
    build() adds them through the hard masks and the machining closing rounds
    them into the loft (on the start car the wall housing rises from the loft
    top 41.7 mm at x 150 to 47.8 mm at x 174, measured 2026-09-30). A loft
    that leaves one as a separate island fails T4.1 in the audit."""
    b, zt, zb = _fuselage(bp, X, x_ref_a, x_rear)
    zc, h = 0.5 * (zt + zb), 0.5 * (zt - zb)
    phi_f = _superellipse_phi(Y, Z, b, zc, h, bp.p)
    # The machined body ends at Ref A: the nose cone is a separate printed part
    # (Part 4 nose.py, team spec 2026-09-27). nose_len only rounds the body's
    # front face now; nothing is left ahead of Ref A.
    phi_f = np.maximum(phi_f, np.maximum(x_ref_a - X, X - x_rear))
    # sidepods
    ts = max(bp.s_taper, 1e-3)
    w = np.minimum(np.clip((X - bp.s_x0) / ts, 0, 1), np.clip((bp.s_x1 - X) / ts, 0, 1))
    w = np.sin(0.5 * np.pi * w)                      # smooth ends
    sb = bp.s_b * w
    sh = 0.5 * (bp.s_zt - bp.s_zb) * np.maximum(w, 0.35)
    phi_s = _superellipse_phi(Y, Z, sb, 0.5 * (bp.s_zt + bp.s_zb), sh, bp.s_p)
    phi_s = np.where(w > 0, phi_s, 1e3)
    phi = _smin(phi_f, phi_s, bp.blend_mm)
    if any(bp.modes):
        phi = phi - mode_field(bp, X, Y, Z, x_ref_a, x_rear)
    phi = phi - skin_mm
    if bp.ft_h > 0.0:
        phi = np.maximum(phi, -_tunnel_phi(bp, X, Y, Z, x_ref_a, x_rear, skin_mm))
    return phi


def _tunnel_phi(bp, X, Y, Z, x_ref_a, x_rear, skin_mm: float = 0.0):
    """Signed distance (mm, negative inside) of the underfloor tunnel: |y| < ft_w
    below a ceiling at the local floor + a height that eases in and out over
    ft_ramp mm, so inlet and outlet are open ramps. Cut from below, so the
    bottom setup of the team's process reaches all of it."""
    b, zt, zb = _fuselage(bp, X, x_ref_a, x_rear)
    r = max(bp.ft_ramp, 1e-3)
    e = np.minimum(np.clip((X - bp.ft_x0) / r, 0, 1), np.clip((bp.ft_x1 - X) / r, 0, 1))
    e = np.sin(0.5 * np.pi * e) ** 2
    # A tunnel never goes through the fuselage: 3 mm of roof and 2.5 mm of side wall are
    # left. Through a thin body it opened the top and sides, so there was no body left for the
    # T4.6 decal or the T4.7 number (6 of 7 rejections in 400 random cars, all with a tunnel).
    ceiling = np.minimum(zb - skin_mm + bp.ft_h * e, zt + skin_mm - 3.0)
    half_w = np.minimum(bp.ft_w, np.maximum(b + skin_mm - 2.5, 0.0))
    inside_x = np.maximum(bp.ft_x0 - X, X - bp.ft_x1)
    return np.maximum.reduce([np.abs(Y) - half_w, Z - ceiling, inside_x, -(bp.ft_h * e)])


def _fuselage(bp, X, x_ref_a, x_rear):
    """(half-width, top, bottom) of the fuselage along X (arrays like X)."""
    from scipy.interpolate import PchipInterpolator
    u = np.clip((X - x_ref_a) / (x_rear - x_ref_a), 0.0, 1.0)
    b, zt, zb = (PchipInterpolator(STATIONS_U, v)(u) for v in (bp.st_b, bp.st_zt, bp.st_zb))
    return b, zt, np.minimum(zb, zt - 4.0)           # always a section, whatever the numbers


def mode_centres(bp, x_ref_a: float, x_rear: float) -> np.ndarray:
    """(N_MODES, 3) mode centres, mm, on the right half of the fuselage."""
    xs = np.array([x_ref_a + u * (x_rear - x_ref_a) for u in MODE_U])
    b, zt, zb = (np.asarray(a, float).ravel() for a in _fuselage(bp, xs, x_ref_a, x_rear))
    zc, h = 0.5 * (zt + zb), 0.5 * (zt - zb)
    out = []
    for i, x in enumerate(xs):
        for ang in MODE_ANG_DEG:
            t = np.radians(ang)
            y = b[i] * abs(np.sin(t)) ** (2 / bp.p)
            z = zc[i] + h[i] * np.sign(np.cos(t)) * abs(np.cos(t)) ** (2 / bp.p)
            out.append((x, y, z))
    zc_s, h_s = 0.5 * (bp.s_zt + bp.s_zb), 0.5 * (bp.s_zt - bp.s_zb)
    for u in SIDE_MODE_U:
        x = bp.s_x0 + u * (bp.s_x1 - bp.s_x0)
        ts = max(bp.s_taper, 1e-3)
        w = np.sin(0.5 * np.pi * min(np.clip((x - bp.s_x0) / ts, 0, 1), np.clip((bp.s_x1 - x) / ts, 0, 1)))
        w = max(float(w), 0.5)            # the ends still have a nose and a tail to shape
        for ang in SIDE_MODE_ANG_DEG:
            t = np.radians(ang)
            y = bp.s_b * w * abs(np.sin(t)) ** (2 / bp.s_p)
            z = zc_s + h_s * np.sign(np.cos(t)) * abs(np.cos(t)) ** (2 / bp.s_p)
            out.append((x, y, z))
    return np.array(out)


def mode_field(bp, X, Y, Z, x_ref_a, x_rear):
    """sum_k a_k exp(-|P - c_k|^2 / 2 sigma^2) with |y| (mirrored). It is
    subtracted from phi, so a positive a_k grows the body ~a_k mm at c_k."""
    C = mode_centres(bp, x_ref_a, x_rear)
    Ya = np.abs(Y)
    out = np.zeros(np.shape(X), dtype=float)
    s2 = 2 * MODE_SIGMA_MM ** 2
    for a, (cx, cy, cz) in zip(bp.modes, C):
        if a:
            out += a * np.exp(-((X - cx) ** 2 + (Ya - cy) ** 2 + (Z - cz) ** 2) / s2)
    return out


def build(W_mm: float, x_front_mm: float, d_halo_mm: float, bp: BodyParams,
          target_body_kg: float | None = None, machinable: bool = True,
          skin_offset_mm: float | None = None, field_mm=None):
    """UnifiedGeometry whose body is `bp`, with every rule mask applied.

    field_mm: a body given as a signed distance field on this car's grid (mm, negative
      inside), e.g. one carved from the block, used instead of `bp`'s loft. It goes through
      the same rules, machining, joins and mass sizing (the skin offset grows or thins it).

    machinable: the team's 3-axis, 6.25 mm ball-end, top-and-bottom process
      (machining.make_machinable) is applied to the drawn shape.
    target_body_kg: no ballast, so the body itself carries the mass the T3.6
      floor needs. The drawn shape is offset by a uniform skin (grown or
      thinned, the design intent kept) until the machined body weighs this.
    """
    import unified_phi as up
    from sdf import reinitialise_sdf
    import machining
    base = up.build_unified_geometry(W_mm, x_front_mm, d_halo_mm, init_mode="full")
    # Read at call time: sandbox/coarse.use_spacing rewrites the module globals,
    # and an import-time copy drew the body at 0.3 mm on a 1 mm grid.
    r, d = base.region, up.GRID_SPACING_M
    xs = (r.origin_m[0] + np.arange(r.shape[0]) * d) * 1e3
    ys = (r.origin_m[1] + np.arange(r.shape[1]) * d) * 1e3
    zs = (r.origin_m[2] + np.arange(r.shape[2]) * d) * 1e3
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    x_ref_a = base.landmarks["ref_plane_A_m"] * 1e3
    x_rear_mm = base.landmarks["rear_face_m"] * 1e3
    if field_mm is not None:
        if np.shape(field_mm) != X.shape:
            raise ValueError(f"field_mm has shape {np.shape(field_mm)}, this car's grid is {X.shape}")
        # The machined body ends at Ref A: ahead of it is the printed nose cone (T1.7).
        phi0 = np.maximum(np.asarray(field_mm, dtype=float), x_ref_a - X)
        bp = replace(bp, ft_h=0.0)                 # the field is the whole body: no loft tunnel
    else:
        phi0 = phi_mm(bp, X, Y, Z, x_ref_a, x_rear_mm)
    # The rules every body obeys (Ref A end, T8.5.1 cap, nose stub, halo floor and pocket
    # bridge) are forced in build_unified_geometry (unified_phi.apply_build_rules), so a
    # carved body gets them too. The stub's section is reused below to join a split front.
    stub = (np.abs(Y) <= 4.0) & (Z >= 9.0) & (Z <= 18.0)

    def make(offset_mm, bar_to=None, bridges=None):
        import copy
        from scipy.ndimage import label
        g = copy.deepcopy(base)
        field = phi0 - offset_mm if not bp.ft_h else phi_mm(bp, X, Y, Z, x_ref_a, x_rear_mm, skin_mm=offset_mm)
        if bar_to is not None:
            g.phi.hard_mask_solid |= stub & (X >= x_ref_a) & (X <= bar_to)
        if bridges is not None:
            g.phi.hard_mask_solid |= bridges & ~g.phi.hard_mask_air
        g.phi.grid = (field / 1e3).astype(np.float32)
        g.phi.apply_hard_constraints()
        up.enforce_symmetry(g)
        reinitialise_sdf(g.phi)
        g.phi.apply_hard_constraints()
        rep = machining.make_machinable(g) if machinable else {}
        up.enforce_symmetry(g)
        rep["islands_removed_mm3"] = _drop_islands(g) * (d * 1e3) ** 3
        rep["pinch_cells_filled"] = _close_pinches(g, d)
        # The stub at Ref A must belong to the main body. Where sculpting, a thin skin or the
        # cutter leaves the front as its own piece, the mesh keeps only the biggest one, and
        # the nose loses its root (body from x 52.9 with Ref A at 39.7; 16 of 1010 random
        # cars, T4.1 or no nose). Then the stub's section runs aft into the main body.
        if bar_to is None:
            lab, n = label(g.phi.grid < 0)
            if n > 1:
                sizes = np.bincount(lab.ravel())
                sizes[0] = 0
                main = lab == sizes.argmax()
                if not (main & stub & (X <= x_ref_a + 2.0)).any():
                    reach = main & stub
                    if reach.any():
                        return make(offset_mm, bar_to=float(X[reach].min()) + 1.0)
        # The same for every other piece holding required material (the T5.5 wall round the
        # chamber came out on its own, smaller, piece and was lost: "0 % of the annulus solid",
        # 3 of 280 random cars): a 4 mm bar, mirrored, from its cell nearest the main body.
        if bridges is None:
            lab, n = label(g.phi.grid < 0)
            if n > 1:
                sizes = np.bincount(lab.ravel())
                sizes[0] = 0
                main_id = sizes.argmax()
                cut = [i for i in np.unique(lab[g.phi.hard_mask_solid & (lab > 0)]) if i != main_id]
                if cut:
                    from scipy.ndimage import distance_transform_edt
                    _, idx = distance_transform_edt(lab != main_id, return_indices=True)
                    bar = np.zeros(lab.shape, bool)
                    Ya = np.abs(Y)
                    for i in cut:
                        cells = np.argwhere(lab == i)
                        near = idx[:, cells[:, 0], cells[:, 1], cells[:, 2]].T
                        k = np.linalg.norm(cells - near, axis=1).argmin()
                        pa = np.array([X[tuple(cells[k])], abs(Y[tuple(cells[k])]), Z[tuple(cells[k])]])
                        pb = np.array([X[tuple(near[k])], abs(Y[tuple(near[k])]), Z[tuple(near[k])]])
                        v = pb - pa
                        t = np.clip(((X - pa[0]) * v[0] + (Ya - pa[1]) * v[1] + (Z - pa[2]) * v[2])
                                    / max(float(v @ v), 1e-9), 0.0, 1.0)
                        bar |= ((X - pa[0] - t * v[0]) ** 2 + (Ya - pa[1] - t * v[1]) ** 2
                                + (Z - pa[2] - t * v[2]) ** 2) <= 2.0 ** 2
                    return make(offset_mm, bar_to=bar_to, bridges=bar)
        g.spacing_m = d
        g.build_report = dict(rep, skin_offset_mm=offset_mm)
        return g

    def mass(g):
        return sum(c.mass_kg for c in up.compute_mass_com(g))

    if skin_offset_mm is not None:           # fixed skin: gradient checks, no mass sizing
        return make(skin_offset_mm)
    if target_body_kg is None:
        return make(0.0)
    # Secant on the skin offset; mass is monotone in it. 0.05 g is well inside
    # the voxel-count noise of the mass itself (~0.3 g at 1 mm).
    a, b = -2.0, 4.0
    ga, gb = make(a), make(b)
    fa, fb = mass(ga) - target_body_kg, mass(gb) - target_body_kg
    # Only the numbers are kept for the bisection, and the one best car: fourteen whole
    # geometries in memory at a fine grid was too much for a 16 GB machine.
    tried = [(a, fa), (b, fb)]
    best = min(((abs(fa), ga), (abs(fb), gb)), key=lambda t: t[0])
    del ga, gb
    for _ in range(6):
        if abs(fb - fa) < 1e-9:
            break
        c = float(np.clip(b - fb * (b - a) / (fb - fa), -8.0, 15.0))
        gc = make(c)
        fc = mass(gc) - target_body_kg
        if abs(fc) < best[0]:
            best = (abs(fc), gc)
        if abs(fc) < 5e-5:
            break
        a, fa, b, fb = b, fb, c, fc
        tried.append((c, fc))
    # Bisection fallback: a skin that grows the body into a rule zone changes
    # the mass in steps, and the secant can stall there (0.21 g short with the
    # v2 CAD supports, 2026-09-28). Bisect between the closest evaluated skins
    # either side of the target.
    for _ in range(8):
        if best[0] < 5e-5:
            break
        lo = max((t for t in tried if t[1] < 0), key=lambda t: t[1], default=None)
        hi = min((t for t in tried if t[1] > 0), key=lambda t: t[1], default=None)
        if lo is None or hi is None:
            break
        c = 0.5 * (lo[0] + hi[0])
        gc = make(c)
        fc = mass(gc) - target_body_kg
        tried.append((c, fc))
        if abs(fc) < best[0]:
            best = (abs(fc), gc)
    g = best[1]
    # The mass steps as flat faces cross grid cells, and the closest car can be the one
    # just under: 0.17 g short put the start car at 47.997 g, under the 48 g floor. Legal
    # comes first, so under the target it takes the lightest car over it, if that is near.
    if mass(g) - target_body_kg < -5e-5:
        over = min((t for t in tried if t[1] > 0), key=lambda t: t[1], default=None)
        if over is not None and over[1] < 1e-3:
            g = make(over[0])
    g.build_report["mass_error_g"] = (mass(g) - target_body_kg) * 1e3
    return g


def _close_pinches(geom, spacing_m: float, rounds: int = 4) -> int:
    import unified_phi as up
    return up.close_pinches(geom, spacing_m, rounds)


def _drop_islands(geom) -> int:
    """Remove solid pieces cut off from the main body that hold no mandatory
    solid (a swollen skin can poke through a rule zone and leave a sliver
    behind it, T4.1). Returns the number of cells removed."""
    from scipy.ndimage import label
    S = geom.phi.grid < 0
    lab, n = label(S)
    if n <= 1:
        return 0
    sizes = np.bincount(lab.ravel())
    sizes[0] = 0
    main = sizes.argmax()
    keep = np.zeros(n + 1, bool)
    keep[main] = True
    keep[np.unique(lab[geom.phi.hard_mask_solid & S])] = True
    keep[0] = True
    drop = ~keep[lab]
    geom.phi.grid[drop] = abs(geom.phi.grid[drop]) + 1e-4
    return int(drop.sum())
