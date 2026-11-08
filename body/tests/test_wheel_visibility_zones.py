"""
Tests for wheel_visibility_zones.py (T7.9 visibility keep-clear zones).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from wheel_visibility_zones import (
    build_t79_forbidden_mask, _rect_forbidden_mask, _trapezoid_forbidden_mask,
    FRONT_INNER_GAP_MIN_MM, REAR_INNER_GAP_MIN_MM,
    T79_FRONT_NEAR_X_MM, T79_REAR_NEAR_X_MM, T79_FRONT_ANGLE_DEG, T79_REAR_ANGLE_DEG,
    T79_WIDTH_Y_MM, zone_polygons_mm,
)
from geometry_contract import mm_to_m, GRID_SPACING_M

def _pass(n): print(f"PASS {n}")
def _fail(n, m): print(f"FAIL {n}: {m}"); sys.exit(1)


def test_rect_mask_marks_correct_x_band():
    origin = (0.0, 0.0, 0.0)
    shape = (100, 50, 10)
    mask = _rect_forbidden_mask(
        origin, shape,
        x_min_m=mm_to_m(10.0), x_max_m=mm_to_m(15.0),
        y_min_m=mm_to_m(5.0), z_max_m=mm_to_m(65.0),
    )
    # A cell at x=12mm, y=10mm, z=1mm should be forbidden
    xi = round(mm_to_m(12.0) / GRID_SPACING_M)
    yi = round(mm_to_m(10.0) / GRID_SPACING_M)
    zi = round(mm_to_m(1.0) / GRID_SPACING_M)
    assert mask[xi, yi, zi], "Expected cell inside rectangle to be forbidden"
    # A cell at x=2mm (outside band) should not be forbidden
    xi2 = round(mm_to_m(2.0) / GRID_SPACING_M)
    assert not mask[xi2, yi, zi], "Expected cell outside x-band to be clear"
    _pass("test_rect_mask_marks_correct_x_band")


def test_rect_mask_respects_y_min():
    origin = (0.0, 0.0, 0.0)
    shape = (60, 150, 10)
    mask = _rect_forbidden_mask(
        origin, shape,
        x_min_m=mm_to_m(5.0), x_max_m=mm_to_m(10.0),
        y_min_m=mm_to_m(19.0), z_max_m=mm_to_m(65.0),
    )
    xi = round(mm_to_m(7.0) / GRID_SPACING_M)
    zi = round(mm_to_m(1.0) / GRID_SPACING_M)
    yi_below = round(mm_to_m(10.0) / GRID_SPACING_M)   # below y_min -> clear
    yi_above = round(mm_to_m(25.0) / GRID_SPACING_M)   # above y_min -> forbidden
    assert not mask[xi, yi_below, zi], "Cell below y_min should be clear"
    assert mask[xi, yi_above, zi], "Cell above y_min should be forbidden"
    _pass("test_rect_mask_respects_y_min")


def _trapezoid(near_mm, angle, direction):
    y_in = mm_to_m(19.0)
    d = GRID_SPACING_M * 1e3
    return _trapezoid_forbidden_mask(
        (0.0, 0.0, 0.0), (int(200 / d), int(80 / d), 10), x_at_wheel_m=mm_to_m(100.0),
        near_x_m=mm_to_m(near_mm),
        angle_deg=angle, direction=direction, y_inner_m=y_in,
        y_outer_m=y_in + mm_to_m(T79_WIDTH_Y_MM), z_max_m=mm_to_m(65.0))


def _at(mask, x_mm, y_mm):
    d = GRID_SPACING_M * 1e3
    return bool(mask[round(x_mm / d), round(y_mm / d), round(1.0 / d)])


def test_t792_is_the_drawn_trapezoid():
    """Page 32: 15 mm deep at the inner edge, 15 + 30/tan 60 = 32.3 mm at the outer."""
    m = _trapezoid(T79_FRONT_NEAR_X_MM, T79_FRONT_ANGLE_DEG, "aft")
    assert _at(m, 100 + 13, 19 + 1), "inside, near the inner edge"
    assert not _at(m, 100 + 20, 19 + 1), "beyond the 15 mm at the inner edge"
    assert _at(m, 100 + 30, 19 + 29), "the outer edge reaches about 32 mm aft"
    assert not _at(m, 100 + 38, 19 + 29), "beyond the sloped far side"
    _pass("test_t792_is_the_drawn_trapezoid")


def test_t793_is_the_drawn_trapezoid():
    """Page 32: 5 mm deep at the inner edge, 5 + 30/tan 45 = 35 mm at the outer."""
    m = _trapezoid(T79_REAR_NEAR_X_MM, T79_REAR_ANGLE_DEG, "fwd")
    assert _at(m, 100 - 4, 19 + 1), "inside, near the inner edge"
    assert not _at(m, 100 - 10, 19 + 1), "beyond the 5 mm at the inner edge"
    assert _at(m, 100 - 32, 19 + 29), "the outer edge reaches about 35 mm forward"
    assert not _at(m, 100 - 41, 19 + 29), "beyond the sloped far side"
    _pass("test_t793_is_the_drawn_trapezoid")


def test_outlines_match_the_drawing():
    """The outlines the finished car is measured against, read back as areas."""
    from shapely.geometry import Polygon
    z = zone_polygons_mm(120.0, 46.0, 14.0)
    assert abs(Polygon(z["T7.9.1"]).area - 150.0) < 1e-6
    assert abs(Polygon(z["T7.9.4"]).area - 150.0) < 1e-6
    assert abs(Polygon(z["T7.9.2"]).area - (15 + 15 + 30 / np.tan(np.radians(60))) / 2 * 30) < 1e-6
    assert abs(Polygon(z["T7.9.3"]).area - (5 + 35) / 2 * 30) < 1e-6
    _pass("test_outlines_match_the_drawing")


def test_build_t79_sidepod_combines_both_wedges():
    W_mm, x_front_mm = 130.0, 64.0
    W_m, x_front_m = mm_to_m(W_mm), mm_to_m(x_front_mm)
    origin = (x_front_m + mm_to_m(10.0), mm_to_m(19.0), 0.0)  # roughly sidepod start
    shape = (400, 150, 10)
    mask = build_t79_forbidden_mask("sidepod", origin, shape, W_mm, x_front_mm)
    assert mask is not None
    assert mask.shape == shape
    assert mask.any(), "Sidepod T7.9 mask should mark some cells forbidden"
    _pass("test_build_t79_sidepod_combines_both_wedges")


def test_build_t79_nose_returns_none():
    origin = (0.0, -0.03, 0.0)
    shape = (50, 50, 50)
    mask = build_t79_forbidden_mask("nose", origin, shape, 130.0, 64.0)
    assert mask is None, "Nose has no T7.9 zone in this coordinate mapping"
    _pass("test_build_t79_nose_returns_none")


def test_build_t79_main_body_forbidden_near_front_wheel():
    W_mm, x_front_mm = 130.0, 64.0
    x_front_m = mm_to_m(x_front_mm)
    origin = (x_front_m - mm_to_m(20.0), -mm_to_m(30.0), 0.0)
    shape = (200, 200, 10)
    mask = build_t79_forbidden_mask("main_body", origin, shape, W_mm, x_front_mm)
    assert mask is not None
    assert mask.any(), "main_body T7.9.1 mask should mark cells forbidden"
    _pass("test_build_t79_main_body_forbidden_near_front_wheel")


def test_build_t79_rearpod_forbidden_near_rear_wheel():
    W_mm, x_front_mm = 130.0, 64.0
    rear_axle_m = mm_to_m(x_front_mm + W_mm)
    origin = (rear_axle_m, -mm_to_m(30.0), 0.0)
    shape = (200, 200, 10)
    mask = build_t79_forbidden_mask("rearpod", origin, shape, W_mm, x_front_mm)
    assert mask is not None
    assert mask.any(), "rearpod T7.9.4 mask should mark cells forbidden"
    _pass("test_build_t79_rearpod_forbidden_near_rear_wheel")


def test_default_gap_constants_match_regs():
    assert FRONT_INNER_GAP_MIN_MM == 38.0   # T7.2.1
    assert REAR_INNER_GAP_MIN_MM == 30.0    # T7.2.2
    _pass("test_default_gap_constants_match_regs")
