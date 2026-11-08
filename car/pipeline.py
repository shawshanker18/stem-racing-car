"""
pipeline.py -- the four steps run_car needs between the geometry and the race time:
quality-gated CFD-ready STL, mass report, CFD solve, race objective.

Copied from part3-simulation/pipeline_interface.unified_bindings (commit 3332323) when the
carving loop and repo folder part3-simulation were retired (bible Part 2, docs/HISTORY.md).
The carving-only bindings (initial field, adjoint weight, adjoint, level-set update,
candidate records) were dropped.
"""

from __future__ import annotations

import os
import warnings
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Optional

import paths  # noqa: F401  -- part1/2/4 on sys.path

ROOT = paths.ROOT
INPUTS = ROOT / "inputs" / "measured.json"

@dataclass(frozen=True)
class GateOutcome:
    """Part 3's view of Part 1's quality_gates.GateResult."""

    lifecycle_state: str
    phi_snapshot_paths: dict
    stl_path: Optional[str]
    stl_half_path: Optional[str]
    failure_reason: Optional[str]
    meshes: Optional[dict] = None
    # Surface area the cutter cannot reach, mm^2. None when not measured.
    #
    # extract_unified_surface computes this and run_quality_gates read it once,
    # to pick between the strings "geometry_repaired" and "valid_simulated", and
    # then dropped the number. So the one quantity that says HOW unmanufacturable
    # a candidate is never left the function that computed it: every record in
    # the 2026-07-29 sweep says "geometry_repaired" and none says by how much.
    # It matters more now that the optimiser actually carves -- an organic shape
    # has real accessibility problems where the starting envelope had few.
    inaccessible_area_mm2: Optional[float] = None


@dataclass(frozen=True)
class CFDOutcome:
    """Part 3's view of one Part 2 CFD run, already converted to FULL-CAR
    values per the Half-Car CFD Contract. Part 3 never sees half-car forces.
    """

    D20: float
    L: float
    Cm: float
    A: float
    converged: bool
    residual_final: float
    # Peak-to-peak swing of streamwise force over the averaged window, as a
    # fraction of its mean. None when not measured.
    #
    # Part 2 measures this and its comment states the contract: "The signal is
    # reported instead, and warned about. Whether an unsteady force is fatal is
    # a policy decision for the caller." The caller handed that decision never
    # received the number -- CFDOutcome had no field for it, so it died at the
    # Part 2 -> Part 3 boundary and survived only as a warning in a worker
    # thread. It is the reproducibility marker for D20 (measured 18-29% against
    # a 5% limit), so without it a candidate record cannot say how much to trust
    # its own race time, and merge_results ranks on a number whose error bar was
    # deliberately computed and then dropped.
    force_oscillation: Optional[float] = None
    # Standard error of the MEAN streamwise force, and how much that mean is
    # still drifting, both as fractions of it. These are the numbers that say
    # whether a drag DELTA is measurable -- force_oscillation is peak-to-peak,
    # which one outlier sets and which does not shrink with a longer window.
    # Carried here for the same reason force_oscillation had to be: Part 2
    # computes them and warns, but the caller holding the ranking decision
    # never saw them, so they died at this boundary and survived only as a
    # warning in a worker thread.
    force_mean_stderr: Optional[float] = None
    force_drift: Optional[float] = None
    # Half-car force per patch (car, wheels, wings, supports) when Part 4's
    # surfaces are in the case; None for a body-only case.
    patch_forces: Optional[dict] = None
    # Full-car pitching moment about the origin (0,0,0) = nose tip on the track
    # (physics_contract.MOMENT_REFERENCE_POINT_M), N m, at the reference speed. Cm above uses a
    # placeholder reference length; the race model needs the raw moment (bible Part 4 4.2.2).
    My: Optional[float] = None


@dataclass(frozen=True)
class MassReport:
    """Part 3's view of Part 2's FullCarMassCOM.

    total_mass_kg / com_*_m describe the car as it CROSSES THE LINE -- dry, all
    propellant spent. The CO2 charge is reported separately because it is only
    aboard at the start; race_model burns it over time. Use
    `launch_com()` for anything evaluated at t=0.
    """

    total_mass_kg: float
    com_x_m: float
    com_y_m: float
    com_z_m: float
    propellant_mass_kg: float = 0.0
    propellant_com: tuple = (0.0, 0.0, 0.0)
    # Legal ballast (Part 1 ballast.py), INCLUDED in total_mass_kg / com_*.
    ballast_kg: float = 0.0
    # "none" (ballast disabled), "absorbing" (body mass free: ballast takes up
    # any change), "heavy" (no ballast, too heavy), "full" (capsule full, light).
    ballast_regime: str = "none"

    @property
    def competition_mass_kg(self) -> float:
        return self.total_mass_kg - 0.02115

    def launch_com(self) -> tuple:
        """(mass, com_x, com_y, com_z) with a full propellant charge aboard."""
        m = self.total_mass_kg + self.propellant_mass_kg
        if m <= 0:
            return (0.0, self.com_x_m, self.com_y_m, self.com_z_m)
        px, py, pz = self.propellant_com
        w, p = self.total_mass_kg, self.propellant_mass_kg
        return (m,
                (w * self.com_x_m + p * px) / m,
                (w * self.com_y_m + p * py) / m,
                (w * self.com_z_m + p * pz) / m)




# Triangle budget for the half-car STL handed to OpenFOAM.
#
# Measured on a real production-spacing build (2026-07-24): marching cubes emits
# 1_057_912 triangles over 0.0467 m2 of half-car surface -- ~0.3 mm facets, a
# 235 MB ASCII file. The CFD mesh it feeds is 1.21 mm at "medium" resolution,
# i.e. ~32_000 surface cells. The STL was therefore ~16x FINER than any mesh
# built from it, buying nothing and costing: 1.67 GB of Python heap in
# _normalise_solid_name, 12.8 s to rewrite, 14.8 s to edge-manifold-check,
# 4.3 s per re-parse (it is parsed 4+ times per solve), snappy's triSurface
# search tree over a million facets, and surfaceFeatureExtract harvesting
# "features" off every marching-cubes staircase step.
#
# 120k triangles is ~0.63 mm facets on this car -- still finer than the 0.606 mm
# finest CFD cell at "medium" with underbody refinement, so nothing is lost.
# Measured: 235 MB -> ~27 MB, volume preserved to 0.01%.
#
# Why not lower: quadric decimation of a marching-cubes half-car OPENS the
# surface below ~120k faces (Euler number 2 -> 5 at 60k, i.e. holes), and Part 2
# hard-rejects a non-edge-manifold STL. _decimate_for_cfd backs off until the
# result is watertight rather than trusting this number blindly.
# ponytail: the rule of thumb is facet size <= finest CFD cell size; revisit if
# you move to "fine" resolution or raise underbody_refinement_level.
STL_TRIANGLE_BUDGET = 120_000

# Re-exported so the decimation warning can name the envelope it failed. One
# source of truth: surface_extraction owns these, set from real solver runs.
# (paths, imported at the top, has put body/ on sys.path.)
from surface_extraction import (  # noqa: E402
    MEASURED_SAFE_MIN_ANGLE_DEG, MEASURED_SAFE_SLIVER_FRACTION,
)


# How far below the symmetry plane a vertex may drift and still be treated as
# rounding rather than a broken half. Quadric decimation moves vertices to
# error-minimising positions, so a y=0 cap vertex lands microns either side; a
# millimetre-scale excursion would mean the half itself is wrong and must still
# fail loudly rather than be snapped into looking correct.
_SYMMETRY_SNAP_TOL_M = 1.0e-4


def _snap_symmetry_plane(mesh):
    """Re-impose y >= 0 after any operation that moves vertices.

    extract_half_surface already flattens sub-cell overshoot onto y=0, but
    DECIMATION RUNS AFTER IT and repositions vertices, which puts them back
    below the plane. Measured 2026-07-27: an aero-only iteration produced a
    vertex at y = -1.000000e-6 against Part 2's y >= -1e-6 contract, exactly on
    the tolerance edge, and the candidate died at the CFD gate with
    "Expected right-half only".

    This is the shared exit every CFD half-STL passes through, so the invariant
    is restored once here rather than at each caller.
    """
    import numpy as _np
    y = mesh.vertices[:, 1]
    below = y < 0.0
    if not below.any():
        return mesh
    worst = float(-y[below].min())          # largest excursion below the plane
    if worst > _SYMMETRY_SNAP_TOL_M:
        raise ValueError(
            f"half-car mesh has a vertex {worst * 1e3:.4f} mm below the y=0 "
            f"symmetry plane, far past the {_SYMMETRY_SNAP_TOL_M * 1e3:.4f} mm "
            f"rounding tolerance. This is a broken half, not decimation noise."
        )
    mesh.vertices[below, 1] = 0.0
    return mesh


def _within_measured_mesh_envelope(mesh) -> bool:
    """Is this mesh inside the envelope snappyHexMesh was actually measured on?

    The decimated STL is a DIFFERENT mesh from the one Part 1's
    _check_mesh_quality inspected, and it never passes back through that gate --
    so nothing checked it. Making decimation succeed (it had never accepted a
    result at all, see _repair_decimated) promptly handed OpenFOAM a mesh with
    min angle 0.08 deg and 3.71% of triangles under 10 deg, against a measured
    envelope of 8.6 deg and 0.01%. That is 371x the sliver fraction anything has
    been measured at, and it went out silently.

    Thresholds are imported, not copied: surface_extraction owns them, and they
    came from meshing real carved STLs on openfoam2412 (8.65-14.19 deg, 0-3
    slivers, "Detected 0 illegal faces" every time). Widen them there, with
    evidence from a solver run, never here.
    """
    import numpy as _np
    from surface_extraction import (MEASURED_SAFE_MIN_ANGLE_DEG,
                                    MEASURED_SAFE_SLIVER_FRACTION)
    try:
        worst_per_face = _np.degrees(mesh.face_angles).min(axis=1)
    except Exception:  # noqa: BLE001 -- cannot measure => cannot certify
        return False
    if not len(worst_per_face):
        return False
    min_angle = float(worst_per_face.min())
    sliver_fraction = float((worst_per_face < 10.0).mean())
    return (min_angle >= MEASURED_SAFE_MIN_ANGLE_DEG
            and sliver_fraction <= MEASURED_SAFE_SLIVER_FRACTION)


def _repair_decimated(reduced) -> None:
    """Close a decimated half-car in place. Order matters.

    Quadric decimation does not open holes here -- measured on the 81,688-face
    half-car, the 50% result had ZERO boundary loops yet is_watertight was
    False, because 4 degenerate (zero-area) triangles left edges shared by more
    than two faces. fill_holes on that mesh is a no-op: there is nothing to
    fill. Dropping the degenerate faces is what creates the holes, and only
    then does fill_holes close them.

    The previous version called fill_holes alone and so never repaired
    anything; every backoff target failed and OpenFOAM was handed the full
    325,204-triangle mesh, with the slow snappyHexMesh and high memory the
    warning describes.
    """
    try:
        import trimesh
        reduced.merge_vertices()
        reduced.update_faces(reduced.nondegenerate_faces())
        reduced.update_faces(reduced.unique_faces())
        reduced.remove_unreferenced_vertices()
        trimesh.repair.fill_holes(reduced)
    except Exception:  # noqa: BLE001 -- decimation is an optimisation, never fatal
        pass


def _decimate_for_cfd(mesh, budget: int = STL_TRIANGLE_BUDGET, _max_backoffs: int = 3):
    """Reduce a marching-cubes surface to a CFD-appropriate triangle count.

    Decimation is an optimisation, so it must never fail a candidate — but it
    must also never SILENTLY do nothing, which is what the first version did:
    it discarded any non-watertight result and returned the original, so a
    1.06M-triangle STL sailed through unchanged with no signal. Back off toward
    a coarser reduction instead, and say so if none of them hold.

    Returns a watertight mesh, always: either a reduced one or the original.
    """
    import warnings

    n = len(mesh.faces)
    if n <= budget:
        return _snap_symmetry_plane(mesh)
    target = budget
    for _ in range(_max_backoffs):
        if target >= n:
            break
        try:
            reduced = mesh.simplify_quadric_decimation(face_count=target)
        except Exception as exc:  # noqa: BLE001 -- optional, never fatal
            warnings.warn(f"STL decimation unavailable ({exc}); using {n} faces.",
                          RuntimeWarning, stacklevel=2)
            return _snap_symmetry_plane(mesh)
        if reduced is not None and len(reduced.faces):
            if not reduced.is_watertight:
                _repair_decimated(reduced)
            if reduced.is_watertight and _within_measured_mesh_envelope(reduced):
                return _snap_symmetry_plane(reduced)
        # Backing off means keeping MORE detail. Note this is not reliably the
        # safer direction: measured on the 81,688-face half-car, 25% decimation
        # came back watertight and 50% did not. Gentler targets leave sliver
        # triangles the aggressive pass would have collapsed outright.
        target *= 2
    warnings.warn(
        f"STL decimation produced no mesh inside the measured-safe envelope at "
        f"any target up to {target}; handing OpenFOAM the full {n}-triangle mesh "
        f"({budget} budget). Expect slow snappyHexMesh and high memory.\n"
        f"This is a real limit, not a tuning knob: quadric decimation targets "
        f"face count, not angle quality. Measured on the 81,688-face half-car, "
        f"a 50% reduction gives min angle 0.00 deg with 3.8% of triangles under "
        f"10 deg, against an envelope of "
        f"{MEASURED_SAFE_MIN_ANGLE_DEG} deg / "
        f"{100.0 * MEASURED_SAFE_SLIVER_FRACTION:.2f}%. Neither hole repair, "
        f"vertex merging (3.8% -> 3.5%, and it breaks watertightness) nor Taubin "
        f"smoothing (fraction 3.8% -> 0.4% but min angle only reaches 2.3 deg, "
        f"and >=10 iterations push vertices 0.375 mm past the y=0 plane) closes "
        f"the gap. The routes to a smaller STL are a coarser extraction grid or "
        f"a quality-preserving decimator -- or mesh one of these on the solver "
        f"and widen the envelope in surface_extraction with the evidence.",
        RuntimeWarning, stacklevel=2,
    )
    return _snap_symmetry_plane(mesh)



def bindings(
    thrust_csv_path: Optional[str],   # None = the curve inputs/measured.json names
    fixed_hardware_kwargs,          # dict, or callable(W_mm, x_front_mm, d_halo_mm) -> dict
    out_dir: str,
    cfd_kwargs: Optional[dict] = None,
    stl_triangle_budget: int = STL_TRIANGLE_BUDGET,
    ballast_material: Optional[str] = None,
):
    """The bindings run_car uses. cfd_kwargs go to Part 2's run_half_car_cfd verbatim.
    The race time comes from race/race_model.py with inputs/measured.json."""
    from unified_phi import compute_mass_com, extract_half_surface, extract_unified_surface
    from cfd_wrapper import run_half_car_cfd
    from mass_com_ingest import FixedHardwareSpec, ingest_mass_com
    import race_model as rm

    cfd_kwargs = dict(cfd_kwargs or {})

    if callable(fixed_hardware_kwargs):
        _build_fh = fixed_hardware_kwargs
    else:
        _build_fh = lambda *_a: fixed_hardware_kwargs  # noqa: E731
    _fh_cache: dict = {}

    def fixed_hardware_for(geom):
        # One spec per distinct (W, x_front, d_halo); a sweep visits a handful.
        key = (round(float(geom.W_mm), 6), round(float(geom.x_front_mm), 6),
               round(float(geom.d_halo_mm), 6))
        if key not in _fh_cache:
            _fh_cache[key] = FixedHardwareSpec(**_build_fh(*key))
        return _fh_cache[key]

    measured = rm.load_inputs(str(INPUTS))
    v = measured["values"]
    thrust = rm.Thrust.from_csv(thrust_csv_path or str(ROOT / v["thrust_csv"]),
                                delay_s=float(v.get("trigger_delay_ms") or 0.0) * 1e-3)
    # The propellant charge from the thrust file itself, so the mass rollup and the race model
    # burn the same charge.
    _propellant_kg = float(thrust.prop_kg[0])
    _COMPONENT_KEYS = ("nose", "sidepod", "rearpod", "main_body")

    def run_quality_gates(geom, candidate_id, run_out_dir):
        os.makedirs(run_out_dir, exist_ok=True)
        try:
            mesh, report = extract_unified_surface(geom, allow_inaccessible=True)
        except Exception as exc:  # noqa: BLE001
            return GateOutcome(
                lifecycle_state="geometry_rejected", phi_snapshot_paths={},
                stl_path=None, stl_half_path=None,
                failure_reason=f"unified extraction failed: {exc}", meshes=None,
            )
        stl_path = os.path.join(run_out_dir, f"{candidate_id}_full.stl")
        stl_half = os.path.join(run_out_dir, f"{candidate_id}_half.stl")
        mesh.export(stl_path, file_type="stl_ascii")
        # Decimate ONLY the half-STL — it is the one that goes to OpenFOAM.
        # The full STL is a deliverable/inspection artefact and keeps full
        # marching-cubes fidelity.
        half_mesh_cfd = _decimate_for_cfd(extract_half_surface(geom), stl_triangle_budget)
        half_mesh_cfd.export(stl_half, file_type="stl_ascii")
        # Report the quality of the mesh OpenFOAM actually receives.
        #
        # The triangle-quality gate in surface_extraction runs on the FULL
        # marching-cubes mesh. This decimated half is what goes to
        # snappyHexMesh, nothing measured it, and it is far worse -- measured on
        # real split6 output:
        #     dhalo16 iter1       120,000 tris  min angle 0.10 deg  6.44% < 10 deg
        #     dhalo43.72 iter6    240,000 tris  min angle 0.04 deg  0.90% < 10 deg
        # Both meshed and solved cleanly (converged=True, Mesh OK, 0 illegal
        # faces), as has every candidate for the life of the project.
        #
        # So the 10 deg gate is roughly two orders of magnitude stricter than
        # anything this pipeline has ever needed, AND it is checking a different
        # artefact than the one that matters. That is worth knowing rather than
        # acting on blind: the number is logged here per iteration so the
        # threshold can be set from evidence instead of assumption. Note the
        # second row also shows decimation backing off -- 240,000 triangles
        # against a 120,000 budget -- which _decimate_for_cfd does deliberately
        # when reduction would break watertightness.
        try:
            _a = np.degrees(half_mesh_cfd.face_angles)
            _a = _a[np.isfinite(_a) & (_a > 0)]
            print(f"[cfd-stl] {candidate_id}: {len(half_mesh_cfd.faces):,} tris "
                  f"(budget {stl_triangle_budget:,})  min angle {_a.min():.2f} deg  "
                  f"{100.0 * (_a < 10.0).mean():.2f}% below 10 deg  "
                  f"watertight={half_mesh_cfd.is_watertight}", flush=True)
        except Exception:  # noqa: BLE001 -- a report must never fail the gate
            pass
        snap = geom.phi.save(candidate_id, run_out_dir)
        # The record contract wants the four component keys; the unified field
        # is one file, so all four point at it (single-field snapshot).
        snaps = {k: snap for k in _COMPONENT_KEYS}
        # allow_inaccessible carries a manufacturing penalty rather than
        # rejecting -> a repaired-but-valid candidate, per the spec's failure
        # table (large accessibility failure = penalty, continue).
        # A per-COMPONENT dict {name: mm^2}, not a scalar -- the old
        # `if report["inaccessible_area_mm2"]` was testing a dict for
        # truthiness, which is why it never noticed. Summed for the record;
        # the breakdown stays in the extraction report.
        _areas = report["inaccessible_area_mm2"]
        inaccessible = float(sum(_areas.values())) if isinstance(_areas, dict)             else float(_areas or 0.0)
        state = "geometry_repaired" if inaccessible else "valid_simulated"
        return GateOutcome(
            lifecycle_state=state, phi_snapshot_paths=snaps,
            stl_path=stl_path, stl_half_path=stl_half,
            failure_reason=None, meshes={"car": mesh},
            inaccessible_area_mm2=inaccessible,
        )

    def compute_mass_report(geom):
        machined = compute_mass_com(geom)
        full = ingest_mass_com(machined, fixed_hardware_for(geom),
                               propellant_mass_kg=_propellant_kg)
        tot, cx, cy, cz = full.total_mass_kg, full.com_x_m, full.com_y_m, full.com_z_m
        b, regime = 0.0, "none"
        if ballast_material is not None:
            import ballast as _bl
            st = _bl.add_to_state({"total_mass_kg": tot, "com_x_m": cx, "com_z_m": cz},
                                  geom.landmarks["ref_plane_A_m"], geom.d_halo_mm,
                                  ballast_material)
            b = st["ballast_kg"]
            regime = _bl.describe(tot, ballast_material)["regime"]
            tot, cx, cz = st["total_mass_kg"], st["com_x_m"], st["com_z_m"]
        return MassReport(
            total_mass_kg=tot, com_x_m=cx, com_y_m=cy, com_z_m=cz,
            propellant_mass_kg=full.propellant_mass_kg,
            propellant_com=tuple(full.propellant_com),
            ballast_kg=b, ballast_regime=regime,
        )

    def run_cfd(stl_half_path):
        half, health = run_half_car_cfd(stl_half_path, **cfd_kwargs)
        full = half.to_full_car()
        return CFDOutcome(D20=full.D20, L=full.L, Cm=full.Cm, A=full.A,
                          converged=health.converged,
                          residual_final=health.residual_final,
                          force_oscillation=health.force_oscillation,
                          force_mean_stderr=getattr(health, "force_mean_stderr", None),
                          force_drift=getattr(health, "force_drift", None),
                          patch_forces=getattr(health, "patch_forces", None),
                          My=2.0 * half.pitching_moment_half)

    def make_car(cfd: CFDOutcome, mass: MassReport, m_car_kg: float, asm: dict,
                 x_front_mm: float, W_mm: float) -> "rm.Car":
        """The race model's car from the CFD, the mass rollup, the assembly and the inputs file.
        m_car_kg: the manufactured car without the cartridge (what the T3.6 scale reads)."""
        from geometry_contract import CHAMBER_AXIS_Z_MM
        wd = asm["wheel_design"]

        def measured_or(key, fallback):
            e = measured_raw.get(key, {})
            return float(e["value"]) if e.get("measured") else fallback

        px, _py, pz = mass.propellant_com
        return rm.Car(
            m_car=m_car_kg, m_shell=float(v["cartridge_shell_g"]) * 1e-3,
            D20=cfd.D20, L20=cfd.L, My20=cfd.My or 0.0,
            drag_exp=float(v.get("drag_exp") or 0.0),
            rho_ratio=float(v["air_density_kgm3"]) / 1.225,
            I_f=measured_or("wheel_I_front_kgm2", wd["front"]["I_gmm2"] * 1e-9),
            I_r=measured_or("wheel_I_rear_kgm2", wd["rear"]["I_gmm2"] * 1e-9),
            r_f=wd["front"]["R_mm"] * 1e-3, r_r=wd["rear"]["R_mm"] * 1e-3,
            mu=float(v["mu_roll"]), R0=float(v["R0_N"]),
            tau0=float(v["bearing_tau0_Nm"]), k_b=float(v["bearing_k_Nms"]),
            mu_guide=float(v["mu_guide"]),
            x_f=x_front_mm * 1e-3, x_r=(x_front_mm + W_mm) * 1e-3,
            x_g=mass.com_x_m, h_g=mass.com_z_m, x_prop=px, h_prop=pz,
            h_T=CHAMBER_AXIS_Z_MM * 1e-3)

    def race(car: "rm.Car") -> "rm.Result":
        return rm.race_time(car, thrust)

    def rates(car: "rm.Car") -> dict:
        return rm.exchange_rates(car, thrust)

    import json as _json
    measured_raw = _json.loads(INPUTS.read_text())

    return SimpleNamespace(run_quality_gates=run_quality_gates,
                           compute_mass_report=compute_mass_report, run_cfd=run_cfd,
                           make_car=make_car, race=race, rates=rates, thrust=thrust,
                           unmeasured=measured["unmeasured"])
