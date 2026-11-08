"""
wheel_visibility_zones.py --- T7.9 "Visibility in top and bottom views" forbidden zones.

Four keep-clear zones around each wheel, per the STEM Racing UAE 2025-26 Technical
Regulations, Article T7.9 (page 32 diagram). No car body may exist within these
zones for any z in [0, 65mm] above the track surface -- this is what lets the wheel
be seen from directly above/below despite the sidepod/body sitting right next to it.

Coordinate system: x=0 at nose tip (see geometry_contract.py).
Front wheel centre at x_front_m, rear wheel centre at x_front_m + W_m.

Shapes in the x-y plane, extruded through z, read off the page 32 diagram:

  T7.9.1  In front of front wheels -- rectangle, 5.0mm (x), 30mm out from the inner edge
  T7.9.2  Behind front wheels      -- trapezoid, 15.0mm (x) at the inner edge, far side
                                      sloping aft at 60 deg from x over 30mm (y): 32.3mm
  T7.9.3  In front of rear wheels  -- trapezoid, 5.0mm (x) at the inner edge, far side
                                      sloping forward at 45 deg over 30mm (y): 35.0mm
  T7.9.4  Behind rear wheels       -- rectangle, 5.0mm (x), 30mm out from the inner edge

Component mapping (see bounding_volumes.py coordinate layout):
  T7.9.1 falls within main_body's forward stub (between Ref Plane A and the front
         axle) -- nose stops at Ref Plane A, well short of the wheel.
  T7.9.4 falls within rearpod's territory (rearpod starts exactly at the rear axle).
  T7.9.2 and T7.9.3 fall within the sidepod corridor -- these are the two zones
         that carve into the sidepod's leading and trailing inner corners.

These were right triangles until 2026-11-06, with 15 x 30 and 5 x 30 mm legs and
the point at the inner edge, which treated the 60 and 45 degree labels as rounding.
The drawn shapes are widest at the OUTER edge and cover about 3x and 8x the area;
real cars had body inside them with every check passing. The scrutineer's tools
are made to the diagram, so the diagram's dimensions are the ones used here.
"""
from __future__ import annotations
from typing import Optional
import numpy as np

from geometry_contract import GRID_SPACING_M, R_WHEEL_M, mm_to_m

# T7.2 minimum inner gaps between opposing wheels. Half of each gap is the
# distance from centerline to the wheel's inner track-contact edge, at the
# absolute legal minimum spacing. Actual gap is a free design choice >= this;
# callers may override via front_inner_gap_mm / rear_inner_gap_mm.
FRONT_INNER_GAP_MIN_MM: float = 38.0   # T7.2.1
REAR_INNER_GAP_MIN_MM: float = 30.0    # T7.2.2

# T7.9 is measured "from the inside edges of each wheels' track contact width",
# i.e. from where the wheels ACTUALLY are, not from the T7.2 minimum gap.
# Anchoring on the minimum put the front zones 4.25 mm too far inboard (wheel
# inner face at 23.25 mm, minimum half-gap 19.0) and the rear 1.25 mm, forbidding
# body volume the rule allows. Defaults now follow the fitted wheels.
from geometry_contract import FRONT_WHEEL_INNER_Y_MM as _FWY, REAR_WHEEL_INNER_Y_MM as _RWY  # noqa: E402
FRONT_INNER_GAP_ACTUAL_MM: float = 2.0 * _FWY
REAR_INNER_GAP_ACTUAL_MM: float = 2.0 * _RWY

# T7.9 zone dimensions (mm), read from the regulation diagram (T7.9, page 32).
T79_RECT_DEPTH_MM: float = 5.0     # T7.9.1 / T7.9.4 rectangle x-depth
T79_FRONT_NEAR_X_MM: float = 15.0  # T7.9.2 depth in x at the wheel's inner edge
T79_REAR_NEAR_X_MM: float = 5.0    # T7.9.3 depth in x at the wheel's inner edge
T79_FRONT_ANGLE_DEG: float = 60.0  # T7.9.2 far side, measured from the x axis
T79_REAR_ANGLE_DEG: float = 45.0   # T7.9.3 far side, measured from the x axis
T79_WIDTH_Y_MM: float = 30.0       # every zone, out from the wheel's inner edge
T79_ZONE_HEIGHT_MM: float = 65.0   # T7.9 zones span z: [0, 65mm] from track surface


def _axis_coords(origin_m: tuple, shape: tuple):
    ox, oy, oz = origin_m
    nx, ny, nz = shape
    dx = GRID_SPACING_M
    xs = ox + np.arange(nx) * dx
    ys = oy + np.arange(ny) * dx
    zs = oz + np.arange(nz) * dx
    return xs, ys, zs


def _rect_forbidden_mask(
    origin_m: tuple,
    shape: tuple,
    x_min_m: float,
    x_max_m: float,
    y_min_m: float,
    z_max_m: float,
) -> np.ndarray:
    """Rectangle forbidden zone: x in [x_min,x_max], y >= y_min (out to car's outer edge), z in [0,z_max]."""
    xs, ys, zs = _axis_coords(origin_m, shape)
    in_x = (xs >= x_min_m) & (xs <= x_max_m)
    in_y = ys >= y_min_m
    in_z = (zs >= 0.0) & (zs <= z_max_m)
    return in_x[:, None, None] & in_y[None, :, None] & in_z[None, None, :]


def _trapezoid_forbidden_mask(
    origin_m: tuple,
    shape: tuple,
    x_at_wheel_m: float,
    near_x_m: float,
    angle_deg: float,
    direction: str,
    y_inner_m: float,
    y_outer_m: float,
    z_max_m: float,
) -> np.ndarray:
    """
    T7.9.2 / T7.9.3: flush against the wheel from y_inner to y_outer, near_x deep
    at y_inner, and deepening with y along a far side at angle_deg from the x axis
    (direction "aft" = +x, for the front wheel; "fwd" = -x, for the rear wheel).
    The far side is grown by one cell so the surface extracted from the grid, which
    sits between an air cell and a solid one, stays outside the zone.
    """
    xs, ys, zs = _axis_coords(origin_m, shape)
    if direction == "aft":
        depth = xs - x_at_wheel_m
    elif direction == "fwd":
        depth = x_at_wheel_m - xs
    else:
        raise ValueError(f"direction must be 'aft' or 'fwd', got {direction!r}")
    reach = near_x_m + (ys - y_inner_m) / np.tan(np.radians(angle_deg)) + GRID_SPACING_M
    in_y = (ys >= y_inner_m) & (ys <= y_outer_m)
    in_z = (zs >= 0.0) & (zs <= z_max_m)
    inside = (depth[:, None] >= 0.0) & (depth[:, None] <= reach[None, :]) & in_y[None, :]
    return inside[:, :, None] & in_z[None, None, :]


def zone_polygons_mm(W_mm: float, x_front_mm: float, R_mm: float,
                     front_inner_y_mm: float = _FWY, rear_inner_y_mm: float = _RWY) -> dict:
    """The four zones on the right side as (x, y) outlines, mm, for measuring a
    finished car against them. The left side is the mirror image."""
    w = T79_WIDTH_Y_MM
    fa, ra = x_front_mm + R_mm, x_front_mm + W_mm - R_mm     # wheel edges facing the car
    ff, rr = x_front_mm - R_mm, x_front_mm + W_mm + R_mm     # wheel edges facing away
    fy, ry = front_inner_y_mm, rear_inner_y_mm
    d = T79_RECT_DEPTH_MM
    return {
        "T7.9.1": [(ff - d, fy), (ff, fy), (ff, fy + w), (ff - d, fy + w)],
        "T7.9.2": [(fa, fy), (fa + T79_FRONT_NEAR_X_MM, fy),
                   (fa + T79_FRONT_NEAR_X_MM + w / np.tan(np.radians(T79_FRONT_ANGLE_DEG)), fy + w),
                   (fa, fy + w)],
        "T7.9.3": [(ra, ry), (ra, ry + w),
                   (ra - T79_REAR_NEAR_X_MM - w / np.tan(np.radians(T79_REAR_ANGLE_DEG)), ry + w),
                   (ra - T79_REAR_NEAR_X_MM, ry)],
        "T7.9.4": [(rr, ry), (rr + d, ry), (rr + d, ry + w), (rr, ry + w)],
    }


def build_t79_forbidden_mask(
    component: str,
    origin_m: tuple,
    shape: tuple,
    W_mm: float,
    x_front_mm: float,
    front_inner_gap_mm: float = FRONT_INNER_GAP_ACTUAL_MM,
    rear_inner_gap_mm: float = REAR_INNER_GAP_ACTUAL_MM,
) -> Optional[np.ndarray]:
    """
    Build the T7.9 forbidden-zone mask for one component's grid.

    Returns a bool array (True = forbidden, must be phi > 0 / air) of shape `shape`,
    or None if this component has no T7.9 zone in this coordinate mapping (nose --
    see module docstring).

    component:
      "main_body" -> T7.9.1 (rectangle, in front of front wheels)
      "sidepod"   -> T7.9.2 + T7.9.3 (wedges, behind front / in front of rear wheels)
      "rearpod"   -> T7.9.4 (rectangle, behind rear wheels)
      "nose"      -> None
    """
    x_front_m = mm_to_m(x_front_mm)
    W_m = mm_to_m(W_mm)
    # The wheel's own edge. Zones were offset by the body's keep-clear margin, which
    # moved T7.9.2 and T7.9.3 a millimetre away from where the scrutineer's tool sits.
    wheel_half_m = R_WHEEL_M
    z_max_m = mm_to_m(T79_ZONE_HEIGHT_MM)

    front_wheel_fwd_m = x_front_m - wheel_half_m           # leading edge of front wheel
    front_wheel_aft_m = x_front_m + wheel_half_m           # trailing edge of front wheel
    rear_wheel_fwd_m = x_front_m + W_m - wheel_half_m      # leading edge of rear wheel
    rear_wheel_aft_m = x_front_m + W_m + wheel_half_m      # trailing edge of rear wheel

    y_bottom_front_m = mm_to_m(front_inner_gap_mm) / 2.0
    y_bottom_rear_m = mm_to_m(rear_inner_gap_mm) / 2.0
    y_top_front_m = y_bottom_front_m + mm_to_m(T79_WIDTH_Y_MM)
    y_top_rear_m = y_bottom_rear_m + mm_to_m(T79_WIDTH_Y_MM)

    rect_depth_m = mm_to_m(T79_RECT_DEPTH_MM)

    if component == "main_body":
        return _rect_forbidden_mask(
            origin_m, shape,
            x_min_m=front_wheel_fwd_m - rect_depth_m,
            x_max_m=front_wheel_fwd_m,
            y_min_m=y_bottom_front_m,
            z_max_m=z_max_m,
        )

    if component == "rearpod":
        return _rect_forbidden_mask(
            origin_m, shape,
            x_min_m=rear_wheel_aft_m,
            x_max_m=rear_wheel_aft_m + rect_depth_m,
            y_min_m=y_bottom_rear_m,
            z_max_m=z_max_m,
        )

    if component == "sidepod":
        wedge_front = _trapezoid_forbidden_mask(
            origin_m, shape,
            x_at_wheel_m=front_wheel_aft_m,
            near_x_m=mm_to_m(T79_FRONT_NEAR_X_MM),
            angle_deg=T79_FRONT_ANGLE_DEG,
            direction="aft",
            y_inner_m=y_bottom_front_m,
            y_outer_m=y_top_front_m,
            z_max_m=z_max_m,
        )
        wedge_rear = _trapezoid_forbidden_mask(
            origin_m, shape,
            x_at_wheel_m=rear_wheel_fwd_m,
            near_x_m=mm_to_m(T79_REAR_NEAR_X_MM),
            angle_deg=T79_REAR_ANGLE_DEG,
            direction="fwd",
            y_inner_m=y_bottom_rear_m,
            y_outer_m=y_top_rear_m,
            z_max_m=z_max_m,
        )
        return wedge_front | wedge_rear

    return None
