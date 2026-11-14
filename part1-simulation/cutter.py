"""The cutter: Part 1's stand-alone cut API (BUILD_SPEC section 7, Step 1).

    g = start_block({"W": 120.3, "x_front": 46.0, "d_halo": 43.72})   # the legal block
    g2, rep = cut(g, dT_dn, half_mesh, step_m=5e-4)                   # one carving step
    save_field(g2, "carved_phi.npy"); g3 = load_field(layout, "carved_phi.npy")

A cut never decides what is faster: it moves the surface where it is told and keeps every
body rule true (forced air and solid, symmetry, one piece, no sub-cell strips, no pinches,
reachable by the 6.25 mm ball end from four sides). Mass sizing and the finished files
stay in param_body.build(..., field_mm=...).

dT_dn is Part 3's sensitivity on the half-body vertices: seconds of race time per metre of
OUTWARD surface move per square metre, positive where growing the body makes the car
slower. The carving step grows the solid where its speed is positive, so the descent is
-dT_dn (BUILD_SPEC 12.3, the sign trap); this module does the negation, callers must not.
"""
from __future__ import annotations

import copy

import numpy as np

import coarse


def start_block(layout: dict, spacing_mm: float = 1.0):
    """The whole legal Model Block envelope with every rule zone applied, at `spacing_mm`.
    Sets the module-wide grid spacing (coarse.use_spacing) before anything is built."""
    coarse.use_spacing(spacing_mm)
    import unified_phi as up
    g = up.build_unified_geometry(layout["W"], layout["x_front"], layout["d_halo"], init_mode="full")
    up.enforce_symmetry(g)
    return g


def save_field(geom, path) -> None:
    """The carved field as float32 metres, the exact in-memory format."""
    np.save(path, np.asarray(geom.phi.grid, dtype=np.float32))


def load_field(layout: dict, path, spacing_mm: float = 1.0):
    """A field saved by save_field, back on this layout's grid with the rules re-applied."""
    g = start_block(layout, spacing_mm)
    f = np.load(path)
    if f.shape != g.phi.grid.shape:
        raise ValueError(f"field {f.shape} does not fit this layout's grid {g.phi.grid.shape}")
    g.phi.grid = f.astype(np.float32)
    g.phi.apply_hard_constraints()
    return g


def cut(geom, dT_dn, half_mesh, step_m: float, max_substeps: int = 6,
        trust_radius_m: float = 1e-3, mass_report=None, dT_dscalars: dict | None = None,
        aero_smooth_m: float = 0.0):
    """One carving step. Returns (geometry, report); never changes `geom`.

    report["status"] is "ok" (the new geometry) or "refused" with a named reason, and then
    the geometry returned is `geom` itself, untouched:
      bad_input        sensitivity not one finite value per mesh vertex
      pinned_detached  forced-solid material is loose on entry, or the first sub-step
                       would cut it loose
      min_wall         the first sub-step would leave a wall under 3.0 mm (MIN_MACHINED_WALL_MM);
                       a later one just ends the step there (report["min_wall_stop"])
      no_motion        nothing moved (zero speed or zero step)
      rule_air_violated / rule_solid_violated   a rule zone ended up wrong (should never happen)

    dT_dscalars: the race model's dT_dmass, dT_dh_com, dT_dx_com (Part 2, via Part 5); they
    need the current mass_report (total_mass_kg, com_x_m, com_z_m). Without them the cut is
    aero only."""
    from phi_updater import apply_adjoint_to_unified

    if dT_dscalars and mass_report is None:
        raise ValueError("dT_dscalars need the current mass_report")
    g = copy.deepcopy(geom)
    try:
        rep = apply_adjoint_to_unified(
            g, right_half_sensitivity=-np.asarray(dT_dn, dtype=np.float64),
            right_half_mesh=half_mesh, dt=step_m,
            gradient_weights={"w_aero": 1.0, "w_mass": 1.0},
            objective_gradients=dict(dT_dscalars or {}),
            # with no scalar slopes the mass term is zero whatever the report says
            mass_report=mass_report or {"total_mass_kg": 1.0, "com_x_m": 0.0, "com_z_m": 0.0},
            max_substeps=max_substeps, trust_radius_m=trust_radius_m, aero_smooth_m=aero_smooth_m)
    except ValueError as exc:
        return geom, {"status": "refused", "reason": f"bad_input: {exc}"}

    solid = g.phi.grid < 0
    rep["rule_air_violated"] = int((solid & g.phi.hard_mask_air).sum())
    rep["rule_solid_violated"] = int((~solid & g.phi.hard_mask_solid).sum())
    # pinned material already loose on entry is a broken input (T4.1); a loose piece from a
    # later sub-step just ends the step there, keeping the sub-steps before it
    reason = ("pinned_detached" if rep["detached_at_start"] or (rep["substeps"] == 0 and rep["pinned_detached"])
              else "min_wall" if rep["substeps"] == 0 and rep.get("min_wall_stop")
              else "no_motion" if rep["substeps"] == 0 or rep["dt"] <= 0
              else "rule_air_violated" if rep["rule_air_violated"]
              else "rule_solid_violated" if rep["rule_solid_violated"]
              else "")
    rep["status"], rep["reason"] = ("refused", reason) if reason else ("ok", "")
    return (geom if reason else g), rep


def finish(geom, layout: dict, target_body_g: float, out_dir) -> dict:
    """A carved field to a finished body and its files (BUILD_SPEC section 6 output).

    param_body.build cuts it at Ref A, joins required pieces, mills it and sizes the skin to
    target_body_g. Writes into out_dir, all lengths in metres:
      carved_phi.npy   the carved field as given, to carry on carving from
      body_half.stl    watertight right half (y >= 0), for CFD (Part 4 adds the parts)
      body.stl         the whole finished body
      cut.json         the verdict and report below
    Returns the cut.json dict: status "ok" or "refused" with reason mass_unreachable,
    open_surface or mesh_quality; mass_g, com_m, skin_offset_mm and the build report."""
    import json
    from pathlib import Path

    from scipy.ndimage import label

    import param_body as pb
    import unified_phi as up

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    save_field(geom, out / "carved_phi.npy")
    body = pb.build(layout["W"], layout["x_front"], layout["d_halo"], pb.BodyParams(),
                    target_body_kg=target_body_g / 1e3, field_mm=geom.phi.grid * 1e3)
    br = dict(body.build_report)
    comps = up.compute_mass_com(body)
    m = sum(c.mass_kg for c in comps)
    res = {"status": "ok", "reason": "", "field": "carved_phi.npy", "body_half_stl": "body_half.stl",
           "body_stl": "body.stl", "units": "m", "mass_g": m * 1e3,
           "com_m": [sum(c.mass_kg * c.com_x_m for c in comps) / m, 0.0,
                     sum(c.mass_kg * c.com_z_m for c in comps) / m],
           "skin_offset_mm": br.get("skin_offset_mm"),
           "field_bodies": int(label(body.phi.grid < 0)[1]),
           "report": {k: v for k, v in br.items() if k != "sizing_tried"}}
    err = br.get("mass_error_g")
    # too light: the car carries ballast for the rest (330fae4), but only as much as the
    # capsule holds; a bigger shortfall stays a refusal (test_cutter, 400 g target, 2026-11-13)
    import ballast
    light = (br.get("mass_unreachable") and (err or 0.0) < 0
             and -err <= ballast.capacity_kg() * 1e3)
    if not light and (br.get("mass_unreachable") or err is None or abs(err) > 0.05):                  # the sizing tolerance (BUILD_SPEC 12.4)
        res.update(status="refused", reason=f"mass_unreachable: {err} g from target"
                   + (" (no skin reaches it)" if br.get("mass_unreachable") else ""))
    if res["status"] == "ok":
        half = up.extract_half_surface(body)
        half.vertices[half.vertices[:, 1] < 0, 1] = 0.0
        if not half.is_watertight:
            half.update_faces(half.nondegenerate_faces())
            half.remove_unreferenced_vertices()
            half.merge_vertices()
        br = body.build_report                     # the export cut just added to it
        res["report"]["cut_failures"] = br.get("cut_failures", 0)
        if br.get("cut_failed"):                   # exact_zones.cut_boxes gave no volume: uncut
            res.update(status="refused", reason=f"cut_failed: exact box cut left the body uncut "
                                                f"({br.get('cut_failures')} of the build's cuts)")
        elif not half.is_watertight:
            res.update(status="refused", reason="open_surface")
        else:
            half.export(str(out / "body_half.stl"))
            res["mesh_bodies"] = len(half.split(only_watertight=False))
            try:
                up.extract_unified_surface(body, allow_inaccessible=True)[0].export(str(out / "body.stl"))
            except Exception as exc:  # noqa: BLE001 -- a quality gate refusing is the answer
                res.update(status="refused", reason=f"mesh_quality: {str(exc)[:120]}")
    (out / "cut.json").write_text(json.dumps(res, indent=1, default=float))
    return res
