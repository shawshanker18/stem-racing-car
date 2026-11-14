"""
unified_phi.py --- ONE level-set field for the whole car, with component labels.

WHY THIS EXISTS
---------------
The original representation gave each of the four components its own phi grid
on its own axis-aligned box, extracted each with its own marching-cubes pass,
and concatenated the four meshes (the old `stl_assembler.assemble_stl` was just
`trimesh.util.concatenate`). Three consequences, all structural:

  1. NO SURFACE COULD CROSS A COMPONENT BOUNDARY. The halo-canister loft --
     the continuous top surface running from the cartridge chamber at the rear,
     forward over the halo mount and down toward Ref Plane A -- spans main_body
     and rearpod. It was not representable at all. 01_generative_geometry.md
     says "the halo-canister loft region sits within the main body phi grid",
     but nothing implemented a loft and the boxes forbade one.

  2. COMPONENTS NEEDED ATTACHMENT-FACE HACKS TO STAY CONNECTED. Each grid
     forced a strip of cells solid at whichever face touched a neighbour, and
     the extraction still routinely produced disconnected pieces (sandbox
     finding 7: `init="sphere"` gave four separate lumps totalling 8.5 g against
     a 48 g minimum, and they passed the gates). With one field, connectivity is
     a property of the field, not a constraint bolted onto four of them.

  3. main_body AND rearpod OVERLAPPED (main_body ran to rear_axle +
     rearpod_max_length, rearpod started at rear_axle + wheel clearance), so
     cells in the overlap were counted toward BOTH components' mass.

This module replaces that with a single phi field over the whole car envelope
plus a per-cell `labels` array. A label carries what the separate grids used to
carry structurally: which density the cell contributes at, and which tool
directions apply to it. The shape itself is free to be whatever the field wants.

WHAT DOES *NOT* CHANGE
----------------------
The step at Ref Plane A is NOT a modelling artifact and is not removed here.
T8.5.1 requires the nose and front wing support structure to be "no more than
25.0mm above the track surface and no wider than 15mm either side of the centre
line reference plane", while the body aft of Ref Plane A may be the full 65 mm
(T3.5). That discontinuity is legally mandated. What unification buys is
continuity *aft* of Ref Plane A -- main_body <-> sidepod <-> rearpod -- which is
exactly where the loft lives.

MEMORY
------
The unified envelope is bigger than any single old grid but smaller than their
sum plus the overlap. At the 0.3 mm spec spacing a full envelope is ~40M cells,
which is not interactively runnable -- same caveat as before, see
sandbox/coarse.py. Use coarse.use_spacing() for exploration.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from bounding_volumes import (
    BoundingRegion,
    BoundingVolumes,
    RuleEnvelope,
    compute_bounding_volumes,
    default_rule_envelope,
)
from geometry_contract import (
    GRID_SPACING_M,
    R_WHEEL_M,
    WHEEL_CLEARANCE_M,
    WHEEL_X_CLEARANCE_HALF_WIDTH_MM,
    get_density,
    grid_cells,
    mm_to_m,
)
from halo_pocket import (
    build_halo_pocket_forbidden_mask,
    build_ballast_container_forbidden_mask,
    pocket_floor_layer_mask,
)
from phi_grid import PhiGrid
from wheel_visibility_zones import build_t79_forbidden_mask

# Label values. 0 is "not part of any component" -- outside the legal envelope
# for every component, and therefore permanently air.
# Extra keep-out around each wheel, on top of the 2 mm assembly clearance, so
# the body stands clearly off the wheels (outrigger look, unambiguous top-view
# visibility) instead of crowding right against them.
WHEEL_KEEPOUT_MARGIN_M: float = 0.0     # was 4 mm (2026-09-25)
# The 4 mm was an aesthetic choice ("outrigger look"), not a rule, and it cut
# the T5.5 chamber wall to 1.25-2.0 mm at the rear axle (3.0 mm required,
# SAFETY). CFD with wheels (rnd-cfd round 2) showed the body's width around the
# wheels is an aerodynamic variable -- a narrower body let the rear wheels see
# more flow and the car got slower -- so the body is free to decide it.

LABEL_NONE: int = 0
LABEL_NOSE: int = 1
LABEL_SIDEPOD: int = 2
LABEL_REARPOD: int = 3
LABEL_MAIN_BODY: int = 4

LABEL_IDS: dict[str, int] = {
    "nose": LABEL_NOSE,
    "sidepod": LABEL_SIDEPOD,
    "rearpod": LABEL_REARPOD,
    "main_body": LABEL_MAIN_BODY,
}
LABEL_NAMES: dict[int, str] = {v: k for k, v in LABEL_IDS.items()}

# T3.1.2's model block bounds the MILLED components only. The nose is 3D
# printed (geometry_contract, user-confirmed 2026-07-14) and so is not block
# material -- confirmed with the project owner 2026-07-20. This is why the
# block is 223 x 65 x 50 mm while T3.5 permits a 65 mm tall car: the block
# constrains what is machined, not the assembled car.
MODEL_BLOCK_LENGTH_MM: float = 223.0
MILLED_COMPONENTS: frozenset[str] = frozenset({"sidepod", "rearpod", "main_body"})


@dataclass
class UnifiedGeometry:
    """One phi field for the whole car, plus the labels that give it meaning."""

    phi: PhiGrid                 # component name is "car"
    labels: np.ndarray           # uint8, same shape as phi.grid
    region: BoundingRegion
    landmarks: dict[str, float]  # metres: ref_plane_A, ref_plane_B, front_axle, ...
    bv: BoundingVolumes          # retained: callers need the per-component extents
    W_mm: float
    x_front_mm: float
    d_halo_mm: float
    fixed_hardware: object = None   # FixedHardwareResult, or None if Part 2 absent
    # Grid spacing this geometry was BUILT at, in metres. Recorded because
    # GRID_SPACING_M is a module global that sandbox/coarse.use_spacing rewrites
    # at runtime -- so by the time a geometry is remapped onto a finer grid, the
    # global no longer describes the geometry in hand. remap_geometry needs both.
    spacing_m: float = 0.0
    # Cells of the T5.5 wall that a design-choice void tried to delete and the
    # builder kept solid. Non-zero is fine (the wall won); it is reported so a
    # mask collision is visible rather than silent.
    t55_cells_protected: int = 0

    @property
    def shape(self) -> tuple[int, int, int]:
        return self.region.shape

    def component_mask(self, component: str) -> np.ndarray:
        """Bool mask of cells labelled as `component` (regardless of solid/air)."""
        if component not in LABEL_IDS:
            raise ValueError(
                f"Unknown component '{component}'. Valid: {sorted(LABEL_IDS)}"
            )
        return self.labels == LABEL_IDS[component]

    def solid_mask(self, component: Optional[str] = None) -> np.ndarray:
        """Solid cells (phi < 0), optionally restricted to one component."""
        solid = self.phi.grid < 0.0
        if component is None:
            return solid
        return solid & self.component_mask(component)

    def machined_length_mm(self) -> float:
        """x-extent of SOLID milled material, in mm.

        This is the quantity T3.1.2's 223 mm applies to -- see
        MODEL_BLOCK_LENGTH_MM. Returns 0.0 if no milled cell is solid.
        """
        milled = np.zeros(self.shape, dtype=bool)
        for name in MILLED_COMPONENTS:
            milled |= self.component_mask(name)
        solid_milled = milled & (self.phi.grid < 0.0)
        if not solid_milled.any():
            return 0.0
        xs = np.where(solid_milled.any(axis=(1, 2)))[0]
        return float((xs[-1] - xs[0] + 1) * GRID_SPACING_M * 1000.0)


# How much of the T4.2 virtual cargo may be eaten by REAL forced-air regions
# before the geometry is rejected.
#
# The one-cell border seal (hard_air[:,:,0] etc., which exists so the phi=0
# surface always closes) is excluded from this measurement, because the cargo
# sits on the track-clearance floor and always loses its bottom layer to it.
# That loss is structural, and crucially it is SPACING-DEPENDENT as a fraction:
# measured 2.94% at the 0.3 mm production spacing but 17.8% at 3 mm, where the
# 10 mm-tall wedge is only ~3 cells high. A flat fraction over the raw overlap
# would therefore pass production and reject every coarse-spacing run --
# including Stage 1, which evaluates at 2 mm. So we count only overlap with
# INTERIOR voids: wheel keep-clear, T7.9 zones, cartridge bore, ballast slot.
# Any of those is a genuine placement clash that leaves the mandatory keep-solid
# volume unfilled, and find_cargo_placement guards none of them (only the halo
# pocket).
# T4.2 wants all of it. 0.5 % was allowed here as "round-off", but that is 97 mm3: enough
# for two corners of the wedge to sit in a T7 zone, outside the body.
CARGO_MAX_ERODED_FRACTION = 0.0


def model_block_slot_mask(region) -> np.ndarray:
    """The slot the official block arrives with (Appendix ii): 6 x 6 mm, centred,
    along its whole underside. Nothing can be solid there, because there is no foam
    to cut it from. It is pre-cut, not milled, so machining must not try to reach it."""
    from geometry_contract import MODEL_BLOCK_SLOT_TOP_Z_MM, MODEL_BLOCK_SLOT_WIDTH_MM
    ys = region.origin_m[1] + np.arange(region.shape[1]) * GRID_SPACING_M
    zs = region.origin_m[2] + np.arange(region.shape[2]) * GRID_SPACING_M
    half = mm_to_m(MODEL_BLOCK_SLOT_WIDTH_MM) / 2.0 + 1e-9
    top = mm_to_m(MODEL_BLOCK_SLOT_TOP_Z_MM) + 1e-9
    yz = (np.abs(ys)[:, None] <= half) & (zs[None, :] <= top)
    return np.broadcast_to(yz[None, :, :], region.shape).copy()


def _mirror_right_onto_left(a: np.ndarray) -> np.ndarray:
    """Copy the y>=0 half of `a` onto the y<0 half, in place. Returns `a`.

    Every constraint in this module is symmetric about the centreline by
    construction (the T7.9 zones, wheel voids, halo pocket and cartridge bore
    are all defined on +/-y), but they are *rasterised* by float comparisons
    against cell coordinates, and those are not exactly symmetric: a cell at
    y=-15.0 mm and its partner at y=+15.0 mm can land on opposite sides of a
    `<= 0.015` test because -0.036 + 34*0.0015 != 0.015 in binary floating
    point. Measured effect before this was applied: the nose zone lost one of
    its two boundary columns and reported com_y = +0.75 mm instead of 0.

    Mirroring the masks makes the symmetry exact rather than approximate, so
    enforce_symmetry's field mirror survives apply_hard_constraints.
    """
    mid = a.shape[1] // 2
    a[:, : mid + 1, :] = a[:, mid:, :][:, ::-1, :]
    return a


def wheel_keepclear_mask(region, W_mm: float, x_front_mm: float) -> np.ndarray:
    """Cells the body must vacate around the four wheels.

    This enforces TWO regulations at once:

      - T7.2 lateral gap: the body must not touch a wheel. A wheel is a disc
        (radius R_WHEEL, circular in x-z) spinning about y, its inner face at
        the T7.2 minimum gap.
      - T7.9 wheel visibility: each wheel must be visible from the top AND
        bottom views, so NO bodywork may sit in a wheel's x-y footprint at ANY
        height -- not above it, not below it.

    The exclusion is therefore a FULL-HEIGHT COLUMN over each wheel's footprint
    (x within R_WHEEL+clearance of the axle, |y| across the wheel's y-band
    widened by clearance, every z), not merely the wheel's own disc volume.

    An earlier version carved only the x-z disc, which left the body free to
    arch OVER the wheels: 114 body cells sat directly above the rear wheel,
    hiding it from the top view. Carving the full column is what makes the
    wheels read as separate outriggers and keeps them visible.

    The T7.9 wedge masks (built separately) extend the keep-clear FORWARD of
    the front wheel and BEHIND the rear wheel; this column covers the wheel
    footprint itself. Together they are the sidepod/wheel exclusion zones.
    """
    from geometry_contract import (
        FRONT_WHEEL_INNER_Y_M, REAR_WHEEL_INNER_Y_M, WHEEL_CLEARANCE_M,
        WHEEL_WIDTH_M, R_WHEEL_M,
    )

    # A dedicated keep-out ON TOP of the 2 mm assembly clearance. With only the
    # 2 mm clearance the body sat right against every wheel, so the init="full"
    # block looked like the wheels were embedded in a slab rather than standing
    # on outriggers. This margin necks the body clearly away from each wheel
    # (inboard AND fore/aft), so the wheels read as separate and stay visible
    # from the top with unambiguous daylight around them.
    keepout = WHEEL_KEEPOUT_MARGIN_M

    nx, ny, nz = region.shape
    ox, oy, oz = region.origin_m
    dx = GRID_SPACING_M
    xs = ox + np.arange(nx) * dx
    ys = oy + np.arange(ny) * dx

    x_front_m = x_front_mm / 1000.0
    rear_axle_m = x_front_m + W_mm / 1000.0
    r_clear = R_WHEEL_M + WHEEL_CLEARANCE_M + keepout

    mask = np.zeros(region.shape, dtype=bool)
    axles = (
        (x_front_m, FRONT_WHEEL_INNER_Y_M),
        (rear_axle_m, REAR_WHEEL_INNER_Y_M),
    )
    for axle_x, inner_y in axles:
        # x-footprint of the wheel disc, plus clearance + keep-out margin
        in_x = (np.abs(xs - axle_x) <= r_clear)[:, None, None]
        # y-band: necked well INSIDE the inner face, out past the wheel
        y0 = inner_y - WHEEL_CLEARANCE_M - keepout
        y1 = inner_y + WHEEL_WIDTH_M + WHEEL_CLEARANCE_M
        in_y = ((np.abs(ys) >= y0) & (np.abs(ys) <= y1))[None, :, None]
        # full height: nothing above or below the wheel (top/bottom visibility)
        mask |= in_x & in_y
    return mask


def _zone_masks(
    region: BoundingRegion,
    bv: BoundingVolumes,
    re: RuleEnvelope,
) -> dict[str, np.ndarray]:
    """Per-component zone masks over the unified grid.

    A zone is where a component is ALLOWED to place material. Zones are
    mutually exclusive by construction (see the precedence note below) and
    their union is the legal envelope; everything outside is permanently air.

    Precedence, applied in order, so each test only sees cells no earlier zone
    claimed:
      nose      -- forward of Ref Plane A, inside T8.5.1's 15 mm half-width and
                   25 mm height limits
      sidepod   -- outboard of the body wall, within the wheel-free corridor
      rearpod   -- aft of the rear wheel's trailing edge
      main_body -- everything else between Ref Plane A and the rearpod
    """
    nx, ny, nz = region.shape
    ox, oy, oz = region.origin_m
    dx = GRID_SPACING_M

    xs = ox + np.arange(nx) * dx
    ys = oy + np.arange(ny) * dx
    zs = oz + np.arange(nz) * dx

    X = xs[:, None, None]
    absY = np.abs(ys)[None, :, None]
    Z = zs[None, None, :]

    ref_A = bv.ref_plane_A_m
    rearpod_x_start = bv.rearpod.origin_m[0]
    rearpod_x_end = bv.rearpod.x_max_m()

    zones: dict[str, np.ndarray] = {}

    zones["nose"] = (
        (X >= ox) & (X < ref_A)
        & (absY <= re.y_nose_half_m)
        & (Z >= re.z_floor_m) & (Z <= re.z_nose_top_m)
    )

    claimed = zones["nose"].copy()

    zones["sidepod"] = (
        ~claimed
        & (X >= bv.sidepod_x_min_m) & (X <= bv.sidepod_x_max_m)
        & (absY > re.y_sidepod_inner_m) & (absY <= re.y_sidepod_outer_m)
        & (Z >= re.z_floor_m) & (Z <= re.z_sidepod_top_m)
    )
    claimed |= zones["sidepod"]

    zones["rearpod"] = (
        ~claimed
        & (X >= rearpod_x_start) & (X <= rearpod_x_end)
        & (absY <= re.y_body_half_m)
        & (Z >= re.z_floor_m) & (Z <= re.z_rearpod_top_m)
    )
    claimed |= zones["rearpod"]

    zones["main_body"] = (
        ~claimed
        & (X >= ref_A) & (X < rearpod_x_start)
        & (absY <= re.y_body_half_m)
        & (Z >= re.z_floor_m) & (Z <= re.z_body_top_m)
    )

    return zones


# Support-design limit (3.0 mm embed; the rule-only ceiling is z_axle + R ~ 27.9 mm). Part 4,
# 2026-11-14: where the pod frame cannot fit, Part 4's support is a 6.27 mm rod in a slot in
# the body's floor, its top 3.0 mm into the foam and inside R - 0.3, so the floor at each axle
# must be <= z_axle + (R - 0.3) - 3.0 ~ 24.65 mm. Kept as body on the centreline
# (|y| <= 1.5 mm, x_axle +- 7 mm, z 23.5-24.5 mm): floor <= 23.5 mm, 1.1 mm under the ceiling.
# Referee gate P4.fit_<front|rear>_floor_rod_embed (e9afa43). Was z 14-23 for the pod frame
# (43b6d7a) until the rod support landed.
AXLE_SUPPORT_HALF_X_MM, AXLE_SUPPORT_HALF_Y_MM, AXLE_SUPPORT_Z_MM = 7.0, 1.5, (23.5, 24.5)


def _axle_support_mask(region, x_front_mm: float, W_mm: float):
    d = GRID_SPACING_M * 1e3
    o = np.asarray(region.origin_m) * 1e3
    x, y, z = (o[k] + d * np.arange(region.shape[k]) for k in range(3))
    m = np.zeros(region.shape, bool)
    yz = (np.abs(y) <= AXLE_SUPPORT_HALF_Y_MM)[:, None] & \
         ((z >= AXLE_SUPPORT_Z_MM[0]) & (z <= AXLE_SUPPORT_Z_MM[1]))[None, :]
    for ax in (x_front_mm, x_front_mm + W_mm):
        m[np.abs(x - ax) <= AXLE_SUPPORT_HALF_X_MM] |= yz
    return m


def _marking_room_mask(region, cargo_solid, ref_A_mm: float, d_halo_mm: float):
    """Body the carve must keep for the markings. T4.6: a 33 x 17 mm flat side wall (the
    30 x 15 mm decal plus a cell each way) over the middle of the cargo, as wide as the
    cargo. T4.7: a 17 x 11 mm deck (8 x 14 mm number plus margin) on the centreline between
    Ref A and the halo, its top under the halo's front shadow. Carving down to the cargo
    left a 10 mm side (44028/0) and no number deck (44016/0) on 54906c4 (2026-11-13)."""
    import fixed_hardware as fh
    import halo_pocket as hp
    from geometry_contract import HALO_MIN_Z_MM
    d = GRID_SPACING_M * 1e3
    o = np.asarray(region.origin_m) * 1e3
    x, y, z = (o[k] + d * np.arange(region.shape[k]) for k in range(3))
    X, Y, Z = np.meshgrid(x, np.abs(y), z, indexing="ij")
    m = np.zeros(region.shape, bool)
    i, j, k = np.nonzero(cargo_solid)
    if len(i):
        xc, zc, yo = x[i].mean(), z[k].mean(), np.abs(y[j]).max()
        m |= (np.abs(X - xc) <= 16.5) & (np.abs(Z - zc) <= 8.5) & (Y <= yo)
    x0 = hp.compute_halo_pocket_box_m(ref_A_mm / 1e3, d_halo_mm)["x_min_m"] * 1e3
    zf = HALO_MIN_Z_MM + fh.HALO_VISIBILITY_FILLET_MM
    xa = ref_A_mm + 3.0
    if x0 - 1.0 - xa >= 17.0:
        m |= (X >= xa) & (X <= x0 + 2.0) & (Y <= 5.5) & (Z <= zf - 1.0)
        # back to the halo pocket and down to the floor: a 17 mm deck carved free of the
        # body (which began at x 55, deck 35-52) came out as a second piece on 44016/0
    return m


def measure_cargo_erosion(cargo_solid, hard_air, region, ref_plane_A_m,
                          d_halo_mm) -> tuple[int, int]:
    """(eaten, requested) interior cargo cells lost to forced-air regions.

    Extracted so the FEASIBILITY SCREEN and the BUILD-TIME GUARD measure the
    same thing. They previously could not: find_cargo_placement screened only
    the halo pocket, while this measurement -- the actual authority -- also sees
    wheel keep-clears, T7.9 zones, the cartridge bore and the ballast slot. The
    screen therefore returned placements the builder then refused, and with a
    cargo scorer driving placement forward into the front wheel keep-clear that
    was EVERY candidate: Stage 1 returned best=None and the whole two-stage run
    died at `'NoneType' object has no attribute 'W_mm'`.

    The grid border seal is excluded (it is not a collision), and ballast
    overlap is exempt: T4.2 says the cargo "may coincide with the legal ballast
    container but not the halo pocket". With the cargo pinned to 14..24 mm and
    the ballast slot at 17.65..24 mm they overlap 6.35 mm BY DESIGN, so counting
    that as erosion would reject every car.
    """
    interior = np.ones(region.shape, dtype=bool)
    interior[0, :, :] = interior[-1, :, :] = False
    interior[:, 0, :] = interior[:, -1, :] = False
    interior[:, :, 0] = interior[:, :, -1] = False
    allowed = build_ballast_container_forbidden_mask(
        region.origin_m, region.shape, ref_plane_A_m, d_halo_mm,
    )
    _mirror_right_onto_left(allowed)
    requested = int((cargo_solid & interior).sum())
    eaten = int((cargo_solid & hard_air & interior & ~allowed).sum())
    return eaten, requested


def build_unified_geometry(
    W_mm: float,
    x_front_mm: float,
    d_halo_mm: float,
    rule_envelope: Optional[RuleEnvelope] = None,
    wheel_x_half_width_mm: float = WHEEL_X_CLEARANCE_HALF_WIDTH_MM,
    init_mode: str = "full",
    seed: int = 42,
    with_cargo: bool = True,
    cargo_placement: Optional[dict] = None,
) -> UnifiedGeometry:
    """Build the single labelled phi field for one (W, x_front, d_halo).

    init_mode defaults to "full" (everything inside the envelope starts solid).
    Topology optimisation should start full and carve away; the old "sphere"
    default inscribed a tiny sphere in each box that never reached the
    attachment faces, producing four disconnected lumps (sandbox finding 7).

    with_cargo=False drops the mandatory T4.2 solid region. The resulting
    geometry is NOT competition-legal; it exists to unblock exploration, same
    contract as the retired sandbox helper that disabled the cargo.
    """
    from fixed_hardware import (
        ForbiddenCylinder,
        compute_default_fixed_hardware_inputs,
        place_fixed_hardware,
    )
    from virtual_cargo import (CARGO_Z_BASE_MM, build_virtual_cargo_solid_mask,
                               find_cargo_placement)

    re = rule_envelope or default_rule_envelope()

    # Reuse the existing derivation for every landmark, rather than
    # re-deriving them here and risking drift from bounding_volumes.
    axle_z_m = R_WHEEL_M
    cyl_r_m = R_WHEEL_M + WHEEL_CLEARANCE_M
    x_half_m = mm_to_m(wheel_x_half_width_mm)
    front_cyl = ForbiddenCylinder(
        mm_to_m(x_front_mm), 0.0, axle_z_m, cyl_r_m, x_half_m
    )
    rear_cyl = ForbiddenCylinder(
        mm_to_m(x_front_mm) + mm_to_m(W_mm), 0.0, axle_z_m, cyl_r_m, x_half_m
    )
    bv = compute_bounding_volumes(
        W_mm, x_front_mm, d_halo_mm, front_cyl, rear_cyl, re,
        wheel_x_half_width_mm=wheel_x_half_width_mm,
    )

    # ── The single envelope ────────────────────────────────────────────────
    # x: nose tip to the rearmost machined face.
    # y: FULL width. The old sidepod grid was right-half-only with the left
    #    mirrored at STL time; carrying a half-width convention for one label
    #    inside a shared field would be a trap. Symmetry is enforced on the
    #    field instead (see enforce_symmetry).
    # z: track clearance floor to the T3.5 ceiling.
    x_span_mm = bv.rearpod.x_max_m() * 1000.0
    z_span_mm = (re.z_body_top_m - re.z_floor_m) * 1000.0

    # The y axis MUST be symmetric about the centreline with a cell centred
    # exactly at y=0. Two things depend on it and both fail silently otherwise:
    # the half-car slice at y=0 (Part 2's contract), and the sidepod pair's
    # com_y=0 convention that Part 2's mass_com_ingest expects. A naive
    # origin=-y_outer with an even cell count puts no cell at y=0 and biases
    # every COM by up to half a cell (measured: com_y up to -1.2 mm at 1.5 mm
    # spacing, which is not small next to a 71 mm wide car).
    n_half = int(np.ceil(re.y_sidepod_outer_m / GRID_SPACING_M))
    ny = 2 * n_half + 1

    region = BoundingRegion(
        component="car",
        origin_m=(0.0, -n_half * GRID_SPACING_M, re.z_floor_m),
        shape=(grid_cells(x_span_mm), ny, grid_cells(z_span_mm)),
    )

    # ── Labels ─────────────────────────────────────────────────────────────
    zones = _zone_masks(region, bv, re)
    labels = np.full(region.shape, LABEL_NONE, dtype=np.uint8)
    for name, mask in zones.items():
        labels[mask] = LABEL_IDS[name]
    _mirror_right_onto_left(labels)

    # ── Hard air ───────────────────────────────────────────────────────────
    # Everything not claimed by a zone is permanently outside the car.
    hard_air = labels == LABEL_NONE

    # T7.9 wheel-visibility keep-clear zones. Each builder positions its zone
    # in absolute coordinates, so all three can be rasterised onto the one grid.
    for comp in ("main_body", "sidepod", "rearpod"):
        zone = build_t79_forbidden_mask(
            comp, region.origin_m, region.shape,
            W_mm, x_front_mm,
        )
        if zone is not None:
            hard_air |= zone

    # T7.2 lateral wheel exclusion: keep the body clear of all four wheels.
    hard_air |= wheel_keepclear_mask(region, W_mm, x_front_mm)

    # T4.4.4 halo mounting pocket.
    hard_air |= build_halo_pocket_forbidden_mask(
        region.origin_m, region.shape, bv.ref_plane_A_m, d_halo_mm,
    )

    # Legal ballast container (Appendix ix): a mandatory empty slot under the halo aperture,
    # open to the pocket. Not drawn here: the rounding of a drawn slot's rim took the pocket
    # floor up to 0.025 mm under the T4.2 cargo top, even drawn 4 cells small (2026-11-10).
    # extract_half_surface cuts it exactly (exact_zones.cut_boxes), as Part 4 does, and
    # compute_mass_com takes it off the count.

    # Fixed hardware voids: axle holes, wheel discs, cartridge bore, halo.
    # place_fixed_hardware rasterises onto whatever grid it is handed, so the
    # unified region goes in where the main-body grid used to. This is also
    # what finally lets the cartridge bore carve main_body and rearpod as one
    # hole instead of two grids each carving their own half.
    fixed_hardware = None
    try:
        hw_inputs = compute_default_fixed_hardware_inputs(
            W_mm, x_front_mm, d_halo_mm,
            bv.ref_plane_A_m, bv.ref_plane_B_m,
            rear_face_x_m=bv.rearpod.x_max_m(),
        )
        hw_inputs["body_grid_shape"] = region.shape
        hw_inputs["body_grid_origin_m"] = region.origin_m
        fixed_hardware = place_fixed_hardware(
            W_mm=W_mm, x_front_mm=x_front_mm, **hw_inputs
        )
        hard_air |= fixed_hardware.combined_void_mask
        # T4.4.2 / T4.4.3: the halo must be visible in the front, side and top
        # views. Modelled as hard AIR over the halo's shadow in each view
        # direction, so the optimiser cannot fill it at any point in the
        # descent -- a rule that binds every candidate rather than one audited
        # after the fact. Measured before this existed, on a carved 79 g car:
        # 100% of halo cells obstructed in top view, 100% in front, 64.7% in
        # side. The rule was comprehensively violated and nothing forbade it.
        from fixed_hardware import halo_visibility_air_mask
        hard_air |= halo_visibility_air_mask(
            fixed_hardware.halo_void_mask,
            z_origin_m=region.origin_m[2],
            dz_m=GRID_SPACING_M,
        )

        # The halo->canister loft. Making a surface across the component
        # boundary REPRESENTABLE (this module's whole point) did not make one
        # get built: the visibility mask bounds only the halo's own shadow, so
        # aft of the halo the field filled to the envelope roof and left a
        # 28 mm cliff behind the halo. The loft is a ceiling, not a shape --
        # the optimiser still chooses everything under it.
        from fixed_hardware import halo_canister_loft_air_mask
        hard_air |= halo_canister_loft_air_mask(
            fixed_hardware.halo_void_mask,
            getattr(fixed_hardware, "canister_cylinder", None),
            x_origin_m=region.origin_m[0],
            y_origin_m=region.origin_m[1],
            z_origin_m=region.origin_m[2],
            d_m=GRID_SPACING_M,
        )
    except ImportError:
        # Part 2 supplies FixedHardwareSpec. Without it there are no hardware
        # voids -- loud in the returned object (fixed_hardware is None), not
        # silently substituted.
        pass

    _mirror_right_onto_left(hard_air)

    # One-cell border so the phi=0 surface is always closed. No attachment-face
    # strips: with a single field, connectivity is the field's own property.
    hard_air[0, :, :] = True
    hard_air[-1, :, :] = True
    hard_air[:, 0, :] = True
    hard_air[:, -1, :] = True
    hard_air[:, :, 0] = True
    hard_air[:, :, -1] = True

    # ── Hard solid ─────────────────────────────────────────────────────────
    hard_solid = np.zeros(region.shape, dtype=bool)
    if with_cargo:
        # cargo_placement lets Stage 1 inject a COM-scored (position, flip);
        # None falls back to the geometric default (corridor-centre, wide-fwd).
        def _cargo_fits(x_start_m, flip):
            # A cell's clearance all round: the grid only proves the cells are clear, and
            # the wedge's true corner can pass a rule zone between them (5-14 mm3, 4 cars
            # in 170). Same heights as the wedge: its top is the pocket floor, not a clash.
            z_base = max(mm_to_m(CARGO_Z_BASE_MM), region.origin_m[2])
            exact = build_virtual_cargo_solid_mask(region.origin_m, region.shape, x_start_m, z_base, flip=flip)
            cargo = build_virtual_cargo_solid_mask(region.origin_m, region.shape, x_start_m, z_base,
                                                   flip=flip, grow_cells=1)
            cargo[:, :, ~exact.any(axis=(0, 1))] = False
            eaten, requested = measure_cargo_erosion(
                cargo, hard_air, region, bv.ref_plane_A_m, d_halo_mm)
            return requested > 0 and eaten / requested <= CARGO_MAX_ERODED_FRACTION

        placement = cargo_placement or find_cargo_placement(
            x_front_mm, W_mm, bv.ref_plane_A_m, d_halo_mm, re.z_floor_m,
            is_valid=_cargo_fits,
        )
        # Clamp the cargo base to the grid floor. find_cargo_placement derives
        # z_base from the rule envelope's z_floor + margin (0.001 m), but the
        # grid ORIGIN is at z_floor itself (0.0015 m), so an unclamped base sat
        # below the first cell layer and the wedge's bottom row was silently
        # clipped by the border seal below (measured: 3.1% of cargo cells).
        z_base = max(placement["z_base_m"], region.origin_m[2])
        cargo_solid = build_virtual_cargo_solid_mask(
            region.origin_m, region.shape,
            placement["x_start_m"], z_base,
            flip=placement.get("flip", False),
        )
        hard_solid |= build_virtual_cargo_solid_mask(
            region.origin_m, region.shape, placement["x_start_m"], z_base,
            flip=placement.get("flip", False), grow_cells=1)
        hard_solid |= _marking_room_mask(region, cargo_solid, bv.ref_plane_A_m * 1e3, d_halo_mm)
        hard_solid |= _axle_support_mask(region, x_front_mm, W_mm)

    # T5.5's safety zone: model block that must remain around the chamber.
    # Without it the optimiser carved the pocket away and left the cartridge
    # floating 24.5 mm clear of the bodywork -- see
    # fixed_hardware.canister_safety_zone_solid_mask. It carries no separate
    # mass; it is the body's own foam.
    if fixed_hardware is not None:
        # T5.5's safety zone stays INSIDE the body field, and that is not a
        # double count. The zone is model block; DENSITY_BODY_KGM3 is 163.0,
        # i.e. 0.163 g/cm3, which is the same PUR foam density the zone itself
        # is quoted at. Its 10.712 cm3 therefore weighs 1.746 g whether it is
        # counted as body or as a separate component -- the same number, once.
        # Double counting would only start if something ALSO added a standalone
        # safety-zone mass on top, and nothing does.
        #
        # Carving it out was tried (2026-08-07) and is strictly worse: excluding
        # it from phi removed the body's reason to be there and the bodywork's
        # top on the centreline fell 46.5 -> 19.5 mm against a zone surface at
        # 47.0, putting the pocket back in mid-air; and as forced AIR the zone
        # eroded the T4.2 virtual cargo by 6.5%, over its tolerance. All of that
        # to arrive at an identical 1.746 g.
        #
        # No try/except: this import failing means the zone is not applied at
        # all. A deleted function once slipped through exactly here because
        # ImportError was swallowed. Let it raise.
        from fixed_hardware import canister_safety_zone_solid_mask
        t55_zone = canister_safety_zone_solid_mask(
            getattr(fixed_hardware, "canister_cylinder", None),
            region.origin_m, region.shape, GRID_SPACING_M,
        )
        hard_solid |= t55_zone

    # The lofted deck itself. The ceiling above (halo_canister_loft_air_mask)
    # only bounds the surface; with no aero term in Stage 1's proxy, mass
    # minimisation then pulls the deck well below it -- measured flat at 38.5 mm
    # against a 44.1 mm canister top, running past the cartridge instead of
    # arriving at it. "Lofts to the canister" describes a surface that exists,
    # so the skin is required material.
    if fixed_hardware is not None:
        try:
            from fixed_hardware import halo_canister_loft_solid_mask
            hard_solid |= halo_canister_loft_solid_mask(
                fixed_hardware.halo_void_mask,
                getattr(fixed_hardware, "canister_cylinder", None),
                x_origin_m=region.origin_m[0],
                y_origin_m=region.origin_m[1],
                z_origin_m=region.origin_m[2],
                d_m=GRID_SPACING_M,
            )
        except ImportError:
            pass

    _mirror_right_onto_left(hard_solid)
    hard_air |= model_block_slot_mask(region)
    # T4.4.4 pins the pocket floor at 24 mm: see pocket_floor_layer_mask.
    hard_air &= ~pocket_floor_layer_mask(region.origin_m, region.shape, bv.ref_plane_A_m, d_halo_mm)

    # Air wins on overlap, matching PhiGrid.build_hard_masks' resolution.
    # This is where T4.2's MANDATORY keep-solid cargo can be silently deleted:
    # find_cargo_placement only avoids the halo pocket, so a placement
    # overlapping any other void (wheel keep-clear, T7.9 zones, cartridge bore,
    # ballast slot) is eaten here with no diagnostic. PhiGrid's own overlap
    # check is dead code by this point — the `&=` has already run. Measure the
    # loss BEFORE resolving, and refuse to build a car that doesn't contain the
    # cargo the regs require.
    if with_cargo:
        eaten, requested = measure_cargo_erosion(
            cargo_solid, hard_air, region, bv.ref_plane_A_m, d_halo_mm,
        )
        if requested and eaten / requested > CARGO_MAX_ERODED_FRACTION:
            raise ValueError(
                f"virtual cargo (T4.2) is {100 * eaten / requested:.1f}% eroded by "
                f"interior forced-air regions at W={W_mm}, x_front={x_front_mm}, "
                f"d_halo={d_halo_mm} ({eaten}/{requested} cells, excluding the "
                "grid border seal). find_cargo_placement only avoids the halo "
                "pocket; this placement collides with a wheel keep-clear, T7.9 "
                "zone, cartridge bore or ballast slot. The car would not contain "
                "the mandatory cargo volume."
            )
    # T5.5 is a SAFETY regulation: the 3 mm wall around the chamber outranks
    # every design-choice void (wheel keep-clear, loft ceiling). Only the bore
    # itself may be air. Before this, "air wins" silently deleted 320 wall
    # cells and left a 1.25-2.0 mm wall at the rear axle.
    t55_overridden = 0
    if fixed_hardware is not None:
        _protect = t55_zone & ~fixed_hardware.canister_void_mask
        _protect[0, :, :] = _protect[-1, :, :] = False
        _protect[:, 0, :] = _protect[:, -1, :] = False
        _protect[:, :, 0] = _protect[:, :, -1] = False
        t55_overridden = int((_protect & hard_air).sum())
        hard_air &= ~_protect
    hard_solid &= ~hard_air

    phi = PhiGrid("car", region, np.zeros(region.shape, dtype=np.float32),
                  hard_solid, hard_air)
    _init_field(phi, init_mode, seed)
    phi.apply_hard_constraints()

    geom = UnifiedGeometry(
        phi=phi,
        labels=labels,
        region=region,
        landmarks={
            "ref_plane_A_m": bv.ref_plane_A_m,
            "ref_plane_B_m": bv.ref_plane_B_m,
            "front_axle_m": mm_to_m(x_front_mm),
            "rear_axle_m": mm_to_m(x_front_mm) + mm_to_m(W_mm),
            "rear_face_m": min(bv.rearpod.x_max_m(), bv.ref_plane_B_m + re.rearpod_max_length_m),   # exact: the cells overran Ref B + 40 by 0.08 mm (2026-11-11)
            "cargo_placement": placement if with_cargo else None,
        },
        bv=bv,
        W_mm=W_mm,
        x_front_mm=x_front_mm,
        d_halo_mm=d_halo_mm,
        fixed_hardware=fixed_hardware,
        spacing_m=GRID_SPACING_M,
        t55_cells_protected=t55_overridden,
    )
    apply_build_rules(geom)
    return geom


def apply_build_rules(geom: "UnifiedGeometry") -> None:
    """Rules every body obeys, lofted (param_body) or carved from the block, found by the
    stress rounds of 2026-11-07. Forced air and forced solid, so a carving step cannot undo
    them either.

    * T8.5.1: within a cell of Ref A the body stays inside 15 mm of the centreline and 25 mm
      of the track, 0.5 mm inside the rule, since the nose takes its root section from there.
      One cell further aft than the root slice: the surface between a capped node and the
      next free one leaned past 15 mm (11 of 1010 random cars).
    * A stub at Ref A for the nose to join, whatever the shape does up there.
    * T4.4.4: the halo sits on a floor at 24 mm. Under the pocket, 1.5 mm inside its outline,
      the body is solid from the cargo band up to (not into) the floor's own layer, so nothing
      leaves the halo over a hole (14 of 400 random cars). Part 4 cuts the exact pocket.
    * Across the pocket's rear edge, below the floor and, 2.5 mm behind the pocket, up into
      what stands behind it: cutting the exact pocket severed a body joined there only above
      the floor (2 of 400 random cars, the chamber end a loose piece)."""
    air, solid = build_rule_masks(geom)
    phi = geom.phi
    phi.hard_mask_air |= air
    phi.hard_mask_solid |= solid & ~phi.hard_mask_air
    phi.apply_hard_constraints()


def build_rule_masks(geom: "UnifiedGeometry"):
    """(forced air, forced solid) of apply_build_rules, y-symmetric by construction."""
    from halo_pocket import compute_halo_pocket_box_m
    r, d = geom.region, GRID_SPACING_M
    xs = (r.origin_m[0] + np.arange(r.shape[0]) * d) * 1e3
    ys = (r.origin_m[1] + np.arange(r.shape[1]) * d) * 1e3
    zs = (r.origin_m[2] + np.arange(r.shape[2]) * d) * 1e3
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    x_ref_a = geom.landmarks["ref_plane_A_m"] * 1e3
    air = (X <= x_ref_a + 1.0 + d * 1e3) & ((np.abs(Y) > 14.5) | (Z > 24.5))
    solid = (np.abs(Y) <= 4.0) & (Z >= 9.0) & (Z <= 18.0) & (X >= x_ref_a) & (X <= x_ref_a + 2.0)
    pk = compute_halo_pocket_box_m(geom.landmarks["ref_plane_A_m"], geom.d_halo_mm)
    in_y = np.abs(Y) <= min(-pk["y_min_m"], pk["y_max_m"]) * 1e3 - 1.5
    under = (Z >= 13.0) & (Z < pk["z_min_m"] * 1e3 - 1e-6)
    solid |= (X >= pk["x_min_m"] * 1e3 + 1.5) & (X <= pk["x_max_m"] * 1e3 - 1.5) & in_y & under
    xe = pk["x_max_m"] * 1e3
    solid |= (X >= xe - 3.0) & (X <= xe + 6.0) & in_y & (under | ((X > xe + 2.5) & (Z >= 13.0) & (Z <= 28.0)))
    # abs(Y) on float cell coordinates is not exactly symmetric: a limit on a grid line
    # (|y| <= 4 on a 2 mm grid) kept the cell on one side only. Mirror, like every other mask.
    return _mirror_right_onto_left(air), _mirror_right_onto_left(solid)


def close_pinches(geom: "UnifiedGeometry", spacing_m: float, rounds: int = 4) -> int:
    """Fill one cell of every 2 x 2 checkerboard (two solid cells meeting only along an
    edge). The surface there can have an edge shared by four faces, so the body STL is not
    watertight. Fill an empty cell of the pair where the rules allow it; where both are
    forced air, take away a solid one instead. Returns cells changed."""
    A = geom.phi.hard_mask_air
    H = getattr(geom.phi, "hard_mask_solid", None)
    total = 0
    for _ in range(rounds):
        S = geom.phi.grid < 0
        fill, carve = np.zeros_like(S), np.zeros_like(S)
        for a, b in ((0, 1), (0, 2), (1, 2)):
            def at(da, db):
                idx = [slice(None)] * 3
                idx[a] = slice(da, S.shape[a] - 1 + da)
                idx[b] = slice(db, S.shape[b] - 1 + db)
                return tuple(idx)
            for (s1, s2), (e1, e2) in ((((0, 0), (1, 1)), ((1, 0), (0, 1))), (((1, 0), (0, 1)), ((0, 0), (1, 1)))):
                pinch = S[at(*s1)] & S[at(*s2)] & ~S[at(*e1)] & ~S[at(*e2)]
                f1 = pinch & ~A[at(*e1)]
                f2 = pinch & ~f1 & ~A[at(*e2)]
                fill[at(*e1)] |= f1
                fill[at(*e2)] |= f2
                rest = pinch & ~f1 & ~f2
                c1 = rest & (~H[at(*s1)] if H is not None else True)
                carve[at(*s1)] |= c1
                carve[at(*s2)] |= rest & ~c1 & (~H[at(*s2)] if H is not None else True)
        if not (fill.any() or carve.any()):
            break
        geom.phi.grid[fill] = -0.25 * spacing_m          # just inside: the surface moves a quarter cell
        geom.phi.grid[carve & ~fill] = 0.25 * spacing_m
        total += int(fill.sum() + carve.sum())
    return total


def drop_thin_strips(geom: "UnifiedGeometry", spacing_m: float, rounds: int = 4) -> int:
    """Turn to air every solid cell with air on both sides along two or more axes: a strip
    (or speck) thinner than one cell. Carving left one at the T8.5.1 cap's edge; a remap to
    a finer grid then redistanced it to |phi| ~ 1e-3 cell and marching cubes gave 0-degree
    slivers (2026-11-09, remap_lab). Too thin to machine or survive a race, so nothing real
    is lost. One-cell plates (air on one axis only) are kept; forced solid is never touched."""
    H = getattr(geom.phi, "hard_mask_solid", None)
    total = 0
    for _ in range(rounds):
        S = geom.phi.grid < 0
        P = np.pad(S, 1, constant_values=False)          # outside the box is air

        def at(a, d):
            idx = [slice(1, -1)] * 3
            idx[a] = slice(1 + d, P.shape[a] - 1 + d)
            return tuple(idx)
        n = sum((~P[at(a, -1)] & ~P[at(a, 1)]).astype(np.int8) for a in range(3))
        drop = S & (n >= 2)
        if H is not None:
            drop &= ~H
        if not drop.any():
            break
        geom.phi.grid[drop] = 0.25 * spacing_m
        total += int(drop.sum())
    return total


def remap_geometry(
    prev_geom: "UnifiedGeometry",
    W_mm: float = None,
    x_front_mm: float = None,
    d_halo_mm: float = None,
    cargo_placement: dict = None,
    with_cargo: bool = True,
) -> "UnifiedGeometry":
    """Carry an evolved shape onto a grid at the CURRENT GRID_SPACING_M.

    This is what makes coarse-to-fine optimisation possible, and it is the
    thing warm_start_phi_grids explicitly does NOT do: that rebuilds a fresh
    field and throws the evolved shape away.

    Why it matters. Surface travel per Hamilton-Jacobi iteration is
    `CFL x grid_spacing`, while phi cost scales with spacing^-3. So spacing is a
    LINEAR lever on how far the shape can move and a CUBIC one on what that
    costs:

        0.5 mm, CFL 0.3   0.15 mm/iter   ~200 iters to move 30 mm   8.50M cells
        2.0 mm, CFL 0.9   1.80 mm/iter   ~17  iters to move 30 mm   0.13M cells

    Carving the gross shape on a coarse grid and then polishing on a fine one is
    therefore ~12x fewer iterations AND ~60x cheaper per iteration than doing it
    all at 0.5 mm. Without a remap you cannot do that at all, because dropping to
    a finer grid means starting from a brick again.

    Resampling is trilinear on the signed distance field, then the hard masks
    are re-applied and the field is re-distanced. Reinitialisation matters: an
    interpolated SDF no longer satisfies |grad phi| = 1, and every HJ step
    assumes it does.

    Args:
        prev_geom: the evolved geometry to carry over. Its own spacing is read
            from prev_geom.spacing_m, not from the module global -- the global
            has usually already been changed to the target by the caller.
        W_mm / x_front_mm / d_halo_mm: default to prev_geom's own scalars, so
            the common case (same car, finer grid) needs no arguments.

    Returns a new UnifiedGeometry at the current spacing whose zero level set
    matches prev_geom's, with all hard constraints freshly applied.
    """
    from scipy.ndimage import map_coordinates
    from phi_updater import reinitialise_sdf

    src_dx = prev_geom.spacing_m or GRID_SPACING_M
    W_mm = prev_geom.W_mm if W_mm is None else W_mm
    x_front_mm = prev_geom.x_front_mm if x_front_mm is None else x_front_mm
    d_halo_mm = prev_geom.d_halo_mm if d_halo_mm is None else d_halo_mm

    new = build_unified_geometry(
        W_mm, x_front_mm, d_halo_mm, init_mode="full",
        cargo_placement=cargo_placement, with_cargo=with_cargo,
    )
    dst_dx = new.spacing_m or GRID_SPACING_M

    # World coordinates of every destination cell centre, expressed in SOURCE
    # index space, so map_coordinates can sample the source field there.
    src_o = np.asarray(prev_geom.region.origin_m, dtype=np.float64)
    dst_o = np.asarray(new.region.origin_m, dtype=np.float64)
    idx = np.indices(new.region.shape, dtype=np.float32)
    coords = np.empty_like(idx)
    for ax in range(3):
        coords[ax] = ((dst_o[ax] + idx[ax] * dst_dx) - src_o[ax]) / src_dx

    resampled = map_coordinates(
        prev_geom.phi.grid.astype(np.float32), coords,
        order=1, mode="nearest",       # outside the old box -> nearest edge value
    ).astype(np.float32)

    new.phi.grid = resampled
    new.phi.apply_hard_constraints()
    reinitialise_sdf(new.phi)          # restore |grad phi| = 1 after interpolation
    new.phi.apply_hard_constraints()   # reinit can nudge cells across the masks
    enforce_symmetry(new)
    drop_thin_strips(new, dst_dx)      # reinit shrinks a sub-cell strip to ~0: slivers
    return new


def _init_field(phi: PhiGrid, mode: str, seed: int) -> None:
    """Initialise the unified field.

    "full" is the mode the other three do not offer and the one topology
    optimisation actually wants: start with every cell inside the envelope
    solid and let the optimiser carve. PhiGrid.init's own modes are delegated
    to for the rest.
    """
    if mode != "full":
        phi.init(mode, seed=seed)
        return
    # Signed distance to the envelope boundary would be ideal; a constant
    # negative interior is enough to start, and reinitialise_sdf will
    # redistance it on the first update.
    phi.grid = np.full(phi.bv.shape, -GRID_SPACING_M, dtype=np.float32)


def enforce_machinability(geom: "UnifiedGeometry") -> int:
    """Fill void no tool can reach. Returns how many cells were filled.

    The block is milled from the top, the bottom and the two sides only, so a
    pocket of air is REAL only if a straight run along +z, -z, +y or -y gets
    from it to the outside without passing through solid. Anything else is a
    cavity you would have to machine from inside a closed shell.

    THE FACE GATE DOES NOT CATCH THIS. _check_accessibility ray-casts surface
    normals, so on the 2026-08-06 car it flagged 239 faces / 96 mm^2 -- and all
    239 were +-x-facing, i.e. it was reporting "this face points down an axis
    that has no tool", which is trivially true of every x-normal face and says
    nothing about whether the shape can be cut. Meanwhile 8,310 air CELLS had
    no clear run out in any of the four real directions, spanning x 91-204 mm.
    Two orders of magnitude of unmakeable void, invisible to a normals test.

    So this is a projection applied during the descent, not a gate after it:
    unreachable void goes back to solid, the optimiser sees the mass it just
    regained, and carves again from a direction that exists. Same shape of fix
    as the halo visibility masks -- make the illegal state unrepresentable
    rather than detectable.

    Hardware voids are exempt. The cartridge bore is drilled along x and the
    halo pocket is a placed part; neither is milled from +-Y/+-Z and neither
    should be filled. They live in hard_mask_air, so exempting that covers the
    bore, the halo pocket, the axle zones, the halo visibility shadow and the
    loft ceiling in one go.
    """
    solid = geom.phi.grid < 0

    def _clear_run(axis: int, positive: bool) -> np.ndarray:
        """True where no solid lies strictly beyond this cell along the axis."""
        s = np.flip(solid, axis=axis) if positive else solid
        acc = np.cumsum(s, axis=axis) - s          # excludes the cell itself
        return np.flip(acc, axis=axis) == 0 if positive else acc == 0

    reachable = (_clear_run(2, True) | _clear_run(2, False)
                 | _clear_run(1, True) | _clear_run(1, False))
    stuck = (~solid) & (~reachable) & (~geom.phi.hard_mask_air)
    n = int(stuck.sum())
    if n:
        # One cell inside the surface, so reinitialisation has a sign to work
        # with rather than a plateau at exactly zero.
        geom.phi.grid[stuck] = -GRID_SPACING_M
        geom.phi.apply_hard_constraints()
    return n


def enforce_symmetry(geom: UnifiedGeometry) -> None:
    """Mirror the right half (y >= 0) onto the left, in place.

    The old representation got symmetry for free by optimising a right-half
    sidepod grid and reflecting it. With one full-width field, symmetry has to
    be imposed on the field. Doing it here keeps the half-car CFD contract
    honest: the y<0 half is exactly the mirror of y>0, so slicing at y=0 loses
    nothing.

    The y axis is built with an odd cell count centred on y=0 (see
    build_unified_geometry), so the mirror of index j is exactly ny-1-j and no
    interpolation is involved.
    """
    grid = geom.phi.grid
    ny = grid.shape[1]
    mid = ny // 2          # the cell sitting exactly at y = 0
    right = grid[:, mid:, :]
    grid[:, : mid + 1, :] = right[:, ::-1, :]
    geom.phi.apply_hard_constraints()


def density_field(geom: UnifiedGeometry) -> np.ndarray:
    """Per-cell density (kg/m^3) from component labels.

    The shape gradient multiplies dT/dmass by density; on the unified field the
    density varies by component (nose 1000, milled 163), so it must be an array.
    Cells outside every component (LABEL_NONE) get 0.
    """
    rho = np.zeros(geom.shape, dtype=np.float64)
    for lid, name in LABEL_NAMES.items():
        rho[geom.labels == lid] = get_density(name)
    return rho


def extract_half_surface(geom: UnifiedGeometry):
    """Watertight right-half (y >= 0) car mesh for Part 2's half-car CFD.

    Part 2 requires the half-car STL to be watertight AND have all vertices
    y >= -1e-6 (closed on the symmetry plane). Slicing the full mesh at y=0 and
    capping does NOT reliably produce a watertight result (trimesh's cap
    triangulation fails on this geometry -- the long-standing slice-watertight
    problem, PLACEHOLDERS.md item 11).

    Instead we build the half from the FIELD: copy it, force every cell with
    y < 0 to air, and marching-cube that. The zero level set then closes itself
    against the forced air right at the symmetry plane, giving a naturally
    watertight half with a flat y=0 cap -- no fragile mesh boolean. Residual
    sub-cell negative-y vertices are snapped to 0.
    """
    import surface_extraction as SE
    from phi_grid import PhiGrid

    ny = geom.shape[1]
    oy = geom.region.origin_m[1]
    ys = oy + np.arange(ny) * GRID_SPACING_M

    half_grid = geom.phi.grid.copy()
    air_value = float(np.abs(half_grid).max()) + GRID_SPACING_M
    half_grid[:, ys < -1e-9, :] = air_value          # everything left of y=0 -> air

    clone = PhiGrid("car", geom.region, half_grid.astype(np.float32),
                    geom.phi.hard_mask_solid, geom.phi.hard_mask_air)
    for eps_frac in (0.0, 1e-6, 1e-4):     # nudge only if the half body comes out open
        mesh = SE._repair_mesh(SE._marching_cubes(clone, eps_frac), pin_plane_y0=True)
        # Flatten any sub-cell overshoot onto the symmetry plane (y >= 0).
        mesh.vertices[mesh.vertices[:, 1] < 0.0, 1] = 0.0
        mesh.merge_vertices()
        if mesh.is_watertight:
            break
    # Smoothing rounds zone edges into the zones (the block slot's corners): put them back.
    try:
        import exact_zones
        # The target is the field's own volume (curvature-corrected cell fractions; half of it,
        # by symmetry). Marching cubes cuts chords across every curve and the repair only gave
        # back to its volume: spheres and an ellipsoid came out 0.4-2.1 % light at 1 mm, the
        # field 0.01-0.06 % (2026-11-10). What is milled is this mesh.
        target = 0.5 * float(fill_fraction(geom.phi.grid, GRID_SPACING_M).sum()) * GRID_SPACING_M ** 3
        v, _n = exact_zones.project_out(geom, mesh.vertices)
        v[v[:, 1] < 0.0, 1] = 0.0
        mesh.vertices = v
        # The repair gave back the smoothing's lost volume by an even outward move, on the
        # zone faces too, and the steps above took that back off them: the mesh came out
        # 0.47 cm3 under the field (2026-11-10). Give it back again through the faces that
        # are clear of every zone; the symmetry cap stays on y = 0.
        for _ in range(3):
            dv = target - abs(mesh.volume)
            if abs(dv) <= 1e-12:
                break
            V = np.asarray(mesh.vertices)
            free = (V[:, 1] > 1e-9) & (exact_zones.air_at_points(geom, V * 1e3) < -0.2)
            area = float(mesh.area_faces[free[mesh.faces].all(axis=1)].sum())
            if area <= 0:
                break
            v = V.copy()
            v[free] += (dv / area) * mesh.vertex_normals[free]
            mesh.vertices = v
        v, _n = exact_zones.project_out(geom, mesh.vertices)
        v[v[:, 1] < 0.0, 1] = 0.0
        mesh.vertices = v
        # The exact box cut last: projecting after it pushed vertices off one zone onto the
        # seam with the next (the halo's side shadow and the air above it, 2026-11-10).
        cut = exact_zones.cut_boxes(geom, mesh)
        # Uncut means the slot, halo, cap and wheel boxes keep marching cubes' chamfers: never
        # hand that on as legal. Counted, and the last one decides (cutter refuses it).
        br = getattr(geom, "build_report", None)
        if isinstance(br, dict):
            br["cut_failed"] = cut is mesh
            br["cut_failures"] = br.get("cut_failures", 0) + (cut is mesh)
        # The cut takes off the chords marching cubes lays across the body's inside corners
        # round the boxes (47 mm3 in the block slot, 99 in the halo pocket box at 1 mm), from a
        # mesh already at the field's volume, so the milled body weighed 0.024 g under its
        # count (2026-11-10). Give that back through faces 0.2 mm clear of every zone and box.
        # Only that: it is a microns-thick move, so anything larger is not this and is not
        # given back (an uncapped give-back here pushed 13 cm3 through a few faces, 9 mm into
        # the zones, on the block-start test body, 2026-11-10).
        # The ballast slot the cut also takes out is not drawn in the field (and so is in the
        # target) and is not given back: its own volume in the body, exactly, comes off dv.
        import halo_pocket as hp
        ref_A, dh = geom.landmarks["ref_plane_A_m"], geom.d_halo_mm
        slot = hp.ballast_capsule_mesh_m(ref_A, dh, above_floor_mm=0.0)
        dv = abs(mesh.volume) - abs(cut.volume) - abs(mesh.intersection(slot, engine="manifold").volume)
        mesh = cut
        if dv > 0:
            V = np.asarray(mesh.vertices)
            P = V * 1e3
            box_d = np.maximum.reduce([exact_zones._box(P[:, 0], np.abs(P[:, 1]), P[:, 2], x=b[0], y=b[1], z=b[2])
                                       for b in exact_zones._air_boxes(geom)]
                                      + [exact_zones.halo_pocket_and_ballast(P[:, 0], np.abs(P[:, 1]), P[:, 2],
                                                                             ref_A * 1e3, dh, 0)])
            free = (V[:, 1] > 1e-9) & (exact_zones.air_at_points(geom, P) < -0.2) & (box_d < -0.2)
            area = float(mesh.area_faces[free[mesh.faces].all(axis=1)].sum())
            step = dv / area if area > 0 else np.inf
            if step <= 2e-5:                       # 0.02 mm
                v = V.copy()
                v[free] += step * mesh.vertex_normals[free]
                mesh.vertices = v
            else:
                import warnings
                warnings.warn(f"extract_half_surface: the cut's {dv * 1e9:.1f} mm3 not given back "
                              f"({step * 1e3:.3f} mm move)", RuntimeWarning, stacklevel=2)
    except AttributeError:          # a bare test geometry without layout
        pass
    return mesh


def nearest_labels(geom: UnifiedGeometry) -> np.ndarray:
    """`geom.labels` with LABEL_NONE cells filled from their nearest labelled cell.

    Mesh vertices and face centroids sit ON the phi=0 surface, which can round
    to a cell just outside every component zone (LABEL_NONE). Those points still
    belong to a component for gate purposes -- a face on the main_body's outer
    skin is a main_body face. Filling by nearest non-NONE label resolves that
    without inventing a rule.
    """
    from scipy.ndimage import distance_transform_edt

    unlabelled = geom.labels == LABEL_NONE
    if not unlabelled.any():
        return geom.labels
    _, inds = distance_transform_edt(unlabelled, return_indices=True)
    return geom.labels[tuple(inds)]


def _points_to_labels(
    geom: UnifiedGeometry, points: np.ndarray, filled: np.ndarray
) -> np.ndarray:
    """Label each world-space point by the grid cell containing it."""
    origin = np.asarray(geom.region.origin_m)
    idx = np.rint((points - origin) / GRID_SPACING_M).astype(np.int64)
    for axis, n in enumerate(geom.shape):
        np.clip(idx[:, axis], 0, n - 1, out=idx[:, axis])
    return filled[idx[:, 0], idx[:, 1], idx[:, 2]]


def extract_unified_surface(
    geom: UnifiedGeometry,
    max_retries: int = 3,
    allow_inaccessible: bool = False,
):
    """Run the six extraction stages on the unified field, per-label.

    surface_extraction.extract_surface dispatches its manufacturing gates on
    `phi.component`, which worked when each component had its own grid and its
    own mesh. One mesh now spans several components, so the dispatch has to move
    from the mesh to the FACE: each face and vertex is attributed to a component
    by label, and each component's rules are applied only to its own geometry.

    What that changes, concretely:
      - the 3.15 mm machining radius is checked on milled vertices only; the
        nose is 3D printed and exempt (it gets the wall-thickness check instead)
      - tool accessibility is tested per component against ITS tool directions,
        but ray occlusion is computed against the WHOLE car -- a cutter reaching
        a main_body face can be blocked by the nose, which four separate meshes
        could not have discovered
      - fewer boundary exemptions. The four-box path exempted every face lying
        on a component's grid wall, which included the flat inter-component cut
        planes. Those planes no longer exist, so only the true outer envelope is
        exempt and the check is correspondingly stricter.

    Returns (mesh, report). `report` carries per-component inaccessible area so
    a large failure can be surfaced as a manufacturing penalty rather than
    silently swallowed -- 01_generative_geometry.md's failure table asks for
    "assign manufacturing penalty, continue" on large failures, which the
    original code never did (it raised on both sizes).
    """
    import surface_extraction as SE
    from geometry_contract import (
        LARGE_INACCESSIBLE_AREA_M2, MIN_RADIUS_M, NOSE_MIN_WALL_THICKNESS_M,
        TOOL_DIRECTIONS,
    )

    filled = nearest_labels(geom)
    milled_ids = {LABEL_IDS[n] for n in MILLED_COMPONENTS}

    def _mc():
        # Field samples exactly on phi = 0 (an exact zone stamp lands on a node) give
        # coincident triangles that the repair welds into edges shared by four faces: car L1,
        # z 4 mm, y +-8 mm, 194 such samples after the 0.5 mm milling (2026-11-12). Nudge them
        # off the level only when the mesh comes out open, as extract_half_surface does.
        for eps_frac in (0.0, 1e-4):
            m = SE._repair_mesh(SE._marching_cubes(geom.phi, eps_frac))
            if m.is_watertight:
                break
        return m

    mesh = _mc()

    # ── Stage 3a: machining radius, milled vertices only ───────────────────
    # range(max_retries + 1), not range(max_retries): the loop CHECKS at the
    # top and repairs at the bottom, so the old bound raised on its last pass
    # without ever attempting that repair -- 3 retries performed 2, while the
    # message said 3. The extra pass is a real attempt, not just honesty.
    for attempt in range(max_retries + 1):
        vlabels = _points_to_labels(geom, np.asarray(mesh.vertices), filled)
        is_milled = np.isin(vlabels, list(milled_ids))
        radii = SE._estimate_local_radii(mesh)
        bad = np.where(is_milled & (radii < MIN_RADIUS_M))[0]
        if bad.size == 0:
            break
        if attempt == max_retries:
            raise SE.RadiusViolation(
                f"car: min radius {radii[bad].min()*1000:.2f} mm < "
                f"{MIN_RADIUS_M*1000:.2f} mm on {bad.size} milled vertices "
                f"after {max_retries} retries."
            )
        SE._smooth_phi_neighbourhood(geom.phi, list(bad), mesh)
        mesh = _mc()

    # ── Stage 3b: nose wall thickness, nose cells only ─────────────────────
    nose_cells = geom.component_mask("nose")
    # range(max_retries + 1), not range(max_retries): the loop CHECKS at the
    # top and repairs at the bottom, so the old bound raised on its last pass
    # without ever attempting that repair -- 3 retries performed 2, while the
    # message said 3. The extra pass is a real attempt, not just honesty.
    for attempt in range(max_retries + 1):
        thin = (
            SE._thin_wall_mask(geom.phi, NOSE_MIN_WALL_THICKNESS_M)
            & nose_cells
            & ~geom.phi.hard_mask_solid
        )
        if not thin.any():
            break
        if attempt == max_retries:
            raise SE.WallThicknessViolation(
                f"nose: {int(thin.sum())} solid cells thinner than "
                f"{NOSE_MIN_WALL_THICKNESS_M*1000:.2f} mm (3D-printing shell "
                f"constraint) after {max_retries} retries."
            )
        SE._thicken_phi_at_thin_walls(geom.phi, thin, NOSE_MIN_WALL_THICKNESS_M)
        mesh = _mc()

    # ── Stage 4: accessibility, per component ──────────────────────────────
    flabels = _points_to_labels(geom, np.asarray(mesh.triangles_center), filled)
    boundary_exempt = SE._boundary_coincident_face_mask(mesh, geom.region)
    areas: dict[str, float] = {}
    for name, directions in TOOL_DIRECTIONS.items():
        own = flabels == LABEL_IDS[name]
        if not own.any():
            areas[name] = 0.0
            continue
        blocked = SE._find_inaccessible_faces(mesh, directions, boundary_exempt)
        if len(blocked) == 0:
            areas[name] = 0.0
            continue
        blocked_own = np.asarray(blocked)[own[np.asarray(blocked)]]
        areas[name] = float(mesh.area_faces[blocked_own].sum())

    worst = max(areas.values()) if areas else 0.0
    if worst >= LARGE_INACCESSIBLE_AREA_M2 and not allow_inaccessible:
        offender = max(areas, key=areas.get)
        raise SE.AccessibilityFailure(
            f"{offender}: large inaccessible area {worst*1e6:.1f} mm^2",
            is_large=True,
        )

    # ── Stages 5 and 6 ─────────────────────────────────────────────────────
    SE._check_rules(mesh, geom.region)
    SE._check_mesh_quality(mesh, "car")

    # T4.1 connectivity counted on the FIELD. The mesh count below is taken
    # after _repair_mesh keeps only the largest component, so it is always 1 --
    # a detached sidepod vanished from the STL while still counting as mass.
    from scipy.ndimage import label as _label
    _, n_field_bodies = _label(geom.phi.grid < 0)
    report = {
        "inaccessible_area_mm2": {k: v * 1e6 for k, v in areas.items()},
        "field_bodies": int(n_field_bodies),
        "connected_bodies": len(mesh.split(only_watertight=False)),
        "watertight": bool(mesh.is_watertight),
        "volume_cm3": float(mesh.volume * 1e6),
    }
    return mesh, report


def compute_mass_com(geom: UnifiedGeometry) -> list:
    """Per-component ComponentMassCOM from the one field, via labels.

    Same arithmetic as mass_com_calculator.compute_component_mass_com, but the
    component split comes from `labels` rather than from separate grids. Two
    real differences from the old path:

      - No double counting. main_body and rearpod used to overlap in x, so
        cells in the overlap contributed to both components' mass.
      - No sidepod doubling. The old code computed a right-half sidepod and
        multiplied its mass by 2; here both sidepods are actual cells.
    """
    from mass_com_calculator import ComponentMassCOM

    dx = GRID_SPACING_M
    ox, oy, oz = geom.region.origin_m
    out = []
    # SUB-CELL VOLUME (2026-09-30). A cell whose centre is within half a cell
    # of the surface is partly solid: its filled fraction is 0.5 - phi/dx.
    # Counting whole cells (phi < 0) over-stated the body that is actually
    # milled -- the exported mesh -- by 0.12-0.28 g on three 1 mm bodies,
    # more than the 0.2 g the car is sized above the 48.0 g T3.6 floor. The
    # fraction agrees with the mesh to 0.04 g. Where phi is not a distance
    # (|phi| >= dx/2 everywhere) this is exactly the old cell count.
    fill = fill_fraction(geom.phi.grid, dx)

    for name in ("nose", "sidepod", "rearpod", "main_body"):
        w = np.where(geom.component_mask(name), fill, 0.0)
        n = float(w.sum())
        if n == 0.0:
            out.append(ComponentMassCOM(name=name, mass_kg=0.0,
                                        com_x_m=ox, com_y_m=oy, com_z_m=oz))
            continue
        ix, iy, iz = (np.arange(k) for k in w.shape)
        out.append(ComponentMassCOM(
            name=name,
            mass_kg=n * dx ** 3 * get_density(name),
            com_x_m=ox + float(w.sum(axis=(1, 2)) @ ix) / n * dx,
            com_y_m=oy + float(w.sum(axis=(0, 2)) @ iy) / n * dx,
            com_z_m=oz + float(w.sum(axis=(0, 1)) @ iz) / n * dx,
        ))
    # The ballast slot: cut exactly from the milled body but not drawn in the field. Off
    # the count at its exact volume and centre, times the field's fill there (1 when solid).
    try:
        ref_A, dh = geom.landmarks["ref_plane_A_m"], geom.d_halo_mm
    except (AttributeError, KeyError):  # a bare test geometry without layout
        return out
    slot = build_ballast_container_forbidden_mask(geom.region.origin_m, geom.region.shape, ref_A, dh)
    cap = __import__("halo_pocket").ballast_capsule_mesh_m(ref_A, dh, above_floor_mm=0.0)
    for i, c in enumerate(out):
        inside = slot & geom.component_mask(c.name)
        if not inside.any():
            continue
        ms = abs(cap.volume) * float(fill[slot].mean()) * get_density(c.name) * inside.sum() / slot.sum()
        cs = cap.center_mass
        m = c.mass_kg - ms
        out[i] = ComponentMassCOM(name=c.name, mass_kg=m, com_x_m=(c.mass_kg * c.com_x_m - ms * cs[0]) / m,
                                  com_y_m=(c.mass_kg * c.com_y_m - ms * cs[1]) / m,
                                  com_z_m=(c.mass_kg * c.com_z_m - ms * cs[2]) / m)
    return out


def fill_fraction(phi, dx: float) -> np.ndarray:
    """Each cell's solid fraction from a distance field phi (negative inside)."""
    phi = np.asarray(phi, dtype=np.float64)
    fill = np.clip(0.5 - phi / dx, 0.0, 1.0)
    # CURVATURE (2026-11-10). The straight ramp over the half-cell band counts a curved
    # surface heavy by dx^2 (k1 + k2) / 24 per unit area -- the band cells outside a convex
    # surface sit on more area than those inside -- so a cell's fraction is dx (k1 + k2) / 24
    # high. A sphere of radius 9.3 cells read +9.7 cells (+0.29 %); once redistancing made
    # the field a true distance, the carved body's field read 0.10 cm3 over its mesh.
    # k1 + k2 = div(grad phi / |grad phi|), central differences; held to a radius of at
    # least one cell, below which the band has no smooth surface to correct for.
    band = (fill > 0.0) & (fill < 1.0)
    if band.any():
        g = np.gradient(phi, dx)
        mag = np.sqrt(sum(c * c for c in g))
        n = [c / np.maximum(mag, 1e-12) for c in g]
        kappa = sum(np.gradient(n[a], dx, axis=a) for a in range(3))
        kappa = np.clip(kappa, -2.0 / dx, 2.0 / dx)
        fill = np.where(band, np.clip(fill - dx * kappa / 24.0, 0.0, 1.0), fill)

    return fill
