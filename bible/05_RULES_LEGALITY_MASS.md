# Part 5 — Rules, legality, mass and manufacturing margins

Read `00_START_HERE.md` first. This Part makes the legality checks at least as strict as the regulations, measures them on the files that actually get manufactured, puts every regulation number in one place, and gives the car a mass margin that survives real-world uncertainty.

A car that is fast in the model and fails scrutineering is worth nothing. Every check here is a hard gate in the search (Part 7): an illegal car is never measured in CFD.

**Compute budget for this Part:** two stress batches of random cars, built and checked without CFD: about 40 jobs × 10 cars each, twice (before and after the fixes), plus golden-car rebuilds. About 100 jobs, each under 2 hours.

---

## 5.0 Start of Part: the compute question

```
QUESTION (Part 5, compute 1): How many team members are confirming that their GitHub
accounts can be used for Part 5?
Why I need it: I build and rule-check about 800 random cars (no CFD) to prove the
stricter checks work and to find builder bugs.
Expected load for Part 5: about 100 jobs of up to 2 hours each. More accounts finish faster;
with 2 accounts it takes about half a day.
```

Then compute 2. Record in `STATUS.md`.

Then ask the regulation questions in 5.1 (all at once, one message).

---

## 5.1 Regulation questions to ask the user (the PDF is theirs)

Ask these together. Each is needed for a specific check below. Record the answers verbatim in `STATUS.md` and in comments in `regs.py`.

```
QUESTION (Part 5, rules): Please check these in the 2025-26 Technical Regulations PDF and
tell me the exact wording or numbers:
 1. T7.6-T7.8 "uniform rolling diameter": does it mean each wheel must be round (constant
    diameter around its circumference), or that all four wheels must have the same diameter?
 2. T7.9 keep-clear zones: please send a photo or screenshot of the diagram(s) with their
    dimensions. The code has 5 mm rectangles ahead of the front and behind the rear wheels,
    30 mm wide zones beside them, and trapezoids (15 mm at 60 degrees, 5 mm at 45 degrees)
    taken from the text only.
 3. T4.7 team number: the 8 mm height is known. Is there a rule for character width, count,
    or the area that must be readable from above?
 4. T4.6 logo decal: must the 30 x 15 area be flat, or only visible? Is there a minimum
    distance from edges?
 5. T4.4: where exactly is the "notch" on the halo part whose centre must be 34 +/- 1 mm
    above the track? (Which feature of hardware_cad/halo_helmet.stl?)
 6. T3.3 listed components: the exact list of allowed components.
 7. T1.22 / Appendix ix ballast: exact wording. Where may ballast go, how much, what material?
 8. T5.4 cartridge angle: measured relative to what (the track, the car's base)?
 9. T7.13 hang test: the claw drawing's dimensions (lip 1.5 x 1.5 mm is in the code).
10. The physical tests (2 kg halo load, 200 g tether guide pull, 100 g wheel hang): how
    and where is each load applied, and what counts as a failure?
```

---

## 5.2 One source of regulation numbers: `regs.py`

Today regulation numbers live in three places: `part4-simulation/component_contract.py` (Part 4's), `part5-simulation/legality.py` (`REGS` dict) and `part1-simulation/geometry_contract.py` (mixed with design choices). Two sources of truth drift (F38).

Create `part1-simulation/regs.py` (repo folder `part1-simulation` is already on every module's path). It holds **only regulation limits**, each with its rule number. Design choices (chamber axis at 31 mm, grid spacing, densities) stay in `geometry_contract.py`.

```python
"""regs.py -- every number from the STEM Racing UAE Professional Class Technical
Regulations 2025-26 that the code checks. Rule numbers in comments. mm and g unless stated.

ONLY regulation limits live here. Design choices (where the chamber axis is, densities, grid
spacing) live in geometry_contract.py. If a regulation number changes, change it here only.
Answers the team gave about ambiguous rules are quoted next to the number with the date.
"""

# --- reference planes
REF_A_AHEAD_OF_FRONT_AXLE = 16.0         # Ref A
REF_B_BEHIND_REAR_AXLE = 16.0            # Ref B

# --- whole car
WIDTH_MIN, WIDTH_MAX = 65.0, 85.0        # T3.4
HEIGHT_MAX = 65.0                        # T3.5
MASS_MIN_G = 48.0                        # T3.6, without the cartridge
TRACK_CLEARANCE_MIN = 1.5                # T3.7, every part except wheels

# --- model block (T1.14, Appendix ii)
BLOCK_LENGTH, BLOCK_WIDTH, BLOCK_HEIGHT = 223.0, 65.0, 50.0

# --- virtual cargo (T4.2)
CARGO_LENGTH = 60.0
CARGO_WIDTH_START, CARGO_WIDTH_END = 55.0, 10.0
CARGO_HEIGHT = 10.0

# --- halo (T4.4)
HALO_NOTCH_Z = 34.0                      # T4.4.4 notch centre above track
HALO_NOTCH_TOL = 1.0                     # +/-

# --- decals (T4.6, T4.7)
LOGO_W, LOGO_H = 30.0, 15.0              # T4.6, each side, 100 % visible from the side
TEAM_NUMBER_H = 8.0                      # T4.7

# --- cartridge chamber (T5)
CHAMBER_DIA_MIN, CHAMBER_DIA_MAX = 18.0, 18.5        # T5.1
CHAMBER_AXIS_Z_MIN, CHAMBER_AXIS_Z_MAX = 30.0, 40.0  # T5.2
CHAMBER_DEPTH_MIN, CHAMBER_DEPTH_MAX = 45.0, 58.0    # T5.3
CHAMBER_ANGLE_MAX_DEG = 3.0                          # T5.4
CHAMBER_WALL_MIN = 3.0                               # T5.5, block material all round
CARTRIDGE_PROTRUSION_MIN = 5.0                       # T5.6

# --- tether (T6)
TETHER_FROM_AXLE_MAX = 10.0              # T6.1
TETHER_ID_MIN, TETHER_ID_MAX = 3.5, 6.0  # T6.2

# --- wheels (T7)
WHEEL_COUNT = 4                          # T7.1
FRONT_INNER_GAP_MIN, REAR_INNER_GAP_MIN = 38.0, 30.0   # T7.2
WHEELBASE_MIN, WHEELBASE_MAX = 120.0, 140.0            # T7.3
FRONT_CONTACT_MIN, REAR_CONTACT_MIN = 13.0, 17.0       # T7.4, excluding fillets/chamfers
WHEEL_DIA_MIN, WHEEL_DIA_MAX = 28.0, 32.0              # T7.5
WHEEL_KEEPCLEAR_AHEAD_FRONT = 5.0        # T7.9 (confirm against the diagram: section 5.1 Q2)
WHEEL_KEEPCLEAR_BEHIND_REAR = 5.0        # T7.9
FRONT_WHEEL_HIDDEN_BELOW_Z = 20.0        # T7.11
HANG_CLAW_CLEARANCE = 1.5                # T7.13

# --- nose and front wing (T1.7, T8)
NOSE_AHEAD_OF_REF_A_MAX = 40.0           # T8.2
NOSE_SUPPORT_Z_MAX = 25.0                # T8.5.1
NOSE_SUPPORT_HALF_WIDTH_MAX = 15.0       # T8.5.1
FRONT_WING_Z_MAX_OUTBOARD = 20.0         # T8.5.2, where |y| > 15
FRONT_WING_OUTBOARD_Y = 15.0             # T8.5.2
ENDPLATE_W_MAX, ENDPLATE_Z_MAX = 10.0, 25.0   # T8.5.3
FRONT_SPAN_MIN, FRONT_SPAN_SEGMENT_MIN = 50.0, 25.0  # T8.6.1
WING_CHORD_MIN, WING_CHORD_MAX = 15.0, 25.0          # T8.6.2 / T9.5.2, horizontal, calipers
FRONT_ELEMENTS_MAX, REAR_ELEMENTS_MAX = 3, 2         # T8.6.2 / T9.5.2
WING_THICK_MIN, WING_THICK_MAX = 2.0, 6.0            # T8.6.3 / T9.5.3
CLEAR_AIR = 5.0                                      # T8.7 / T9.6

# --- rear wing (T9)
REAR_WING_BEHIND_REF_B = 0.0             # T9.4.1, entirely behind Ref B
REAR_OVERHANG_MAX = 40.0                 # T9.4.2, from Ref B
REAR_WING_Z_MAX = 65.0                   # T9.4.3
REAR_SPAN_MIN = 50.0                     # T9.5.1, one unbroken span
REAR_HEIGHT_DEVIATION_MAX = 15.0         # T9.5.4

# --- physical tests (scrutineering)
HALO_LOAD_KG = 2.0
TETHER_GUIDE_PULL_G = 200.0
WHEEL_HANG_G = 100.0
```

Then:

1. `component_contract.py`: replace every regulation literal with `from regs import ...`. Keep its helper functions (`ref_plane_A`, `ref_plane_B`).
2. `legality.py`: delete the `REGS` dict; import from `regs`.
3. `geometry_contract.py`: replace regulation literals with imports from `regs`; leave design choices.
4. Add `part1-simulation/tests/test_regs.py`: grep the code for any of the regulation literals (`48.0`, `65.0`, `85.0`, `1.5`, `223.0`, …) appearing next to a rule comment outside `regs.py`, and fail if found. This keeps the single source single.

---

## 5.3 The checks: fixes, one by one

Each fix is one commit with its finding ID. After each, rebuild the golden cars from Part 2; **differences are now expected** where a check became stricter or a builder stopped auto-shifting. Record every difference and show the user the before/after margins table before accepting new golden fingerprints.

### 5.3.1 F17 — T5.5 wall: check the full 3 mm, the full depth, and the closed end

Today (`legality.py:41-80`): the probe annulus runs from bore radius + 1.0 mm to + 2.9 mm, skipping 2 mm at each end, and it passes at 99.9% solid. It was loosened because a 1 mm voxel bore bulged. The manufactured body now has the exact bore cut (`joints.py:408-415`), so the excuse is gone.

New check, on `machined_body.stl` only (the file that is milled):

```python
def t55_wall(body_mm, rear_face_mm: float, depth_mm: float, bore_r_mm: float, axis_z_mm: float) -> dict:
    """T5.5: at least 3 mm of block material all round the chamber, along its whole depth and
    across its closed (front) end. body_mm: the machined body, closed mesh, millimetres, both halves.
    Returns {'side_fraction', 'end_fraction', 'min_wall_mm'}."""
    import trimesh
    x_open, x_end = rear_face_mm, rear_face_mm - depth_mm
    ring = trimesh.boolean.difference(
        [_x_cylinder_mm(bore_r_mm + 3.0, x_end, x_open, axis_z_mm),
         _x_cylinder_mm(bore_r_mm, x_end - 1.0, x_open + 1.0, axis_z_mm)], engine="manifold")
    endcap = _x_cylinder_mm(bore_r_mm + 3.0, x_end - 3.0, x_end, axis_z_mm)
    side = _volume_in(body_mm, ring) / ring.volume
    end = _volume_in(body_mm, endcap) / endcap.volume
    # thinnest point: distance from the bore surface to the body's outer surface, sampled
    ang = np.linspace(0, 2 * np.pi, 72, endpoint=False)
    xs = np.linspace(x_end + 0.5, x_open - 0.5, 40)
    pts = np.array([(x, (bore_r_mm + 0.01) * np.sin(a), axis_z_mm + (bore_r_mm + 0.01) * np.cos(a))
                    for x in xs for a in ang])
    dirs = np.array([(0.0, np.sin(a), np.cos(a)) for _x in xs for a in ang])
    loc, idx, _ = body_mm.ray.intersects_location(pts, dirs, multiple_hits=False)
    wall = np.full(len(pts), np.inf)
    wall[idx] = np.linalg.norm(loc - pts[idx], axis=1)
    return {"side_fraction": side, "end_fraction": end, "min_wall_mm": float(wall.min())}
```

`_x_cylinder_mm` is `legality._x_cylinder` in millimetres with 192 sections (polygon error under 0.01 mm at r = 12 mm). `_volume_in` already exists in `legality.py`.

Pass: `side_fraction ≥ 0.9995` and `end_fraction ≥ 0.9995` (tessellation tolerance only) and `min_wall_mm ≥ 3.0 − 0.02`. Margin reported = `min_wall_mm − 3.0`.

The ray from the bore surface outward finds the first exit from the body. On the open rear face, rays exit at the face; exclude points within 0.5 mm of the rear face (done by the `xs` range). Rays that hit nothing (inf) mean the body is open there: fail.

**ASK THE USER** (if not already answered): does T5.5 require 3 mm at the closed end of the chamber too? The check above assumes yes. If the answer is no, drop `end_fraction` from the pass condition and say so in a comment quoting their answer.

### 5.3.2 F18 — T7.4 contact width excluding fillets and chamfers

Today (`wheel.py:110`): `w = ext[ax]`, the wheel's whole extent along its axle, including the hub and bearing seat. The rule counts only the flat tread.

New measurement on the wheel mesh as printed:

```python
def contact_width_mm(mesh, axis: int, flat_tol_mm: float = 0.02) -> tuple[float, float]:
    """(contact width, rolling radius) of a wheel mesh in mm: the axial length of the tread
    that lies at the maximum radius within flat_tol_mm, i.e. excluding fillets and chamfers."""
    import numpy as np
    c = (mesh.bounds[0] + mesh.bounds[1]) / 2
    v = mesh.vertices - c
    r = np.hypot(*np.delete(v, axis, axis=1).T)
    R = float(r.max())
    on_tread = r >= R - flat_tol_mm
    # faces whose three vertices are on the tread and whose normals are radial
    f = mesh.faces
    face_on = on_tread[f].all(axis=1)
    n = mesh.face_normals[face_on]
    radial = np.abs(n[:, axis]) < 0.05
    zs = v[f[face_on][radial]][:, :, axis]
    if zs.size == 0:
        return 0.0, R
    return float(zs.max() - zs.min()), R
```

Use this in `wheel.design()` for `w` and `R` (rolling radius = maximum radius of the tread). Margin: `w − 13.0` front, `w − 17.0` rear. The current team wheels are 13.25 and 17.25 mm overall; if their tread edges are rounded, the new width will be smaller and the car may now fail. That is correct: tell the user immediately, with the measured width, because the wheels may need redesign before anything else.

Also measure the **printed** wheels with calipers (Part 3 M5 weighs them; add calipers on the tread) and record the measurement next to the CAD value.

### 5.3.3 F19 — one radius per axle, from the wheels themselves

Three radii coexist today: 14.13 (`geometry_contract.R_WHEEL_M`), 14.12 (`beam_support.py:298`), 14.05 (`legality.py:565`), and `assembly.py:138` averages front and rear (`R = 0.5 * (f.R + r.R)`).

Fix:

- `wheel.design()` returns each wheel's rolling radius from `contact_width_mm` (5.3.2).
- `assembly.build` uses `f.R` for the front axle and `r.R` for the rear axle everywhere: axle height (wheel bottom on the track), CFD drum radius, wheel rotation rate ω = −U/R per axle, T7.5, T7.9 zones, T7.13.
- Delete the constants at `beam_support.py:298` and `legality.py:565`; read the radius from the assembly record.
- `geometry_contract.R_WHEEL_M` stays only as a default for code that has no wheel yet, with a comment pointing to `wheel.design()`.
- If front and rear radii differ, the body sits at a slight pitch (the axle heights differ). The code today assumes level. **ASK THE USER** (5.1 Q1): if the rule requires the same diameter on all four wheels, add a check `|R_f − R_r| ≤ 0.05 mm` and resolve any difference in the wheel design. If not, model the pitch: rotate the car about the rear contact by asin((R_f − R_r)/W) before CFD, or check that the difference is below 0.1 mm and ignore it.

### 5.3.4 F20 — T4.1 single body must be able to fail

Today `joints.machined_body()` keeps the largest piece and moves the rest into `metadata["dropped_fragments_mm3"]`; `legality.py:515-517` counts bodies on the Part 1 field instead.

Fix:

- `machined_body()` keeps all pieces (do not drop them).
- `legality` T4.1: count closed shells in `machined_body.stl` with volume above 0.01 mm³ (numerical dust). Pass only if exactly one. Report the volumes of any extra pieces.
- If this makes cars fail, the failure is real: pockets or the nose cut-off are severing slivers. Report them; Part 1's `close_pinches` or the pocket geometry must fix them, not the check.

### 5.3.5 F21 — T4.4.4 halo notch: the rule's ±1.0 mm, measured on the right feature

Today the check allows 0.5 mm deviation of the pocket floor because a 0.43 mm dip at two of eight points failed a car.

Fix (after the user answers 5.1 Q5):

- Compute the notch centre height from the halo STL as placed in the assembly: notch centre z = (pocket floor z where the halo actually rests) + (notch offset above the halo's bottom, from the halo STL).
- Where the halo rests: the **highest** floor point under the halo's footprint (the halo sits on the highest points; a dip elsewhere does not lower it). Use the eight ray hits the check already computes; take the max.
- T4.4.4 margin = 1.0 − |notch_z − 34.0|.
- Separately, a **fit** check (not a rule): the floor's lowest point is within 0.5 mm of its highest under the footprint, so the halo is supported. Name it `fit_halo_floor_flat`; it is a manufacturing quality check and may stay at 0.5 mm because it is not a regulation.

### 5.3.6 F22 — constants compared with constants are not checks

Move these out of the legality report into **design assertions** in `regs.py`/`geometry_contract.py` that run at import time and raise if a design constant breaks a rule:

```python
# geometry_contract.py, after the design constants
from regs import (CHAMBER_DIA_MIN, CHAMBER_DIA_MAX, CHAMBER_AXIS_Z_MIN, CHAMBER_AXIS_Z_MAX,
                  CHAMBER_DEPTH_MIN, CHAMBER_DEPTH_MAX, TETHER_ID_MIN, TETHER_ID_MAX)
assert CHAMBER_DIA_MIN <= MODEL_BLOCK_BORE_DIA_MM <= CHAMBER_DIA_MAX, "T5.1"
assert CHAMBER_AXIS_Z_MIN <= CHAMBER_AXIS_Z_MM <= CHAMBER_AXIS_Z_MAX, "T5.2"
assert CHAMBER_DEPTH_MIN <= MODEL_BLOCK_BORE_DEPTH_MM <= CHAMBER_DEPTH_MAX, "T5.3"
```

and the tether guide constants in `component_contract.py`. Remove from the report: `T5.1_diameter`, `T5.2_height`, `T5.3_depth`, `T5.6_protrusion` (legality.py:453-457), `T6.1_front_guide`, `T6.1_rear_guide`, `T6.2_id_min`, `T6.2_id_max`, `T3.7_tether_clearance` (assembly.py:242-246; replace T6.1 with a **measured** check: distance from each guide's centre to its axle along x, from the built guide meshes), `T9.5.4_height_deviation` (wings.py:324; replace with a measured check: max − min of the wing's chord-line height along the span, from the mesh). Remove duplicate entries (T8.2 three times, T9.4.2 twice, T3.7 six times): one entry per rule, the strictest measurement.

The report's summary must then say: `N rule checks (measured on manufactured files), M design assertions (checked at import)`. Update READMEs with the real numbers.

### 5.3.7 F23 — front wing: no auto-shift; record what was built

Today `build_front_wing` (`wings.py:141-148`) raises or lowers the wing until it is 0.05 mm inside the 5 mm clear-air and 20 mm height limits, recursively, and `assembly.py:260` records the parameters that were requested, not the shifted ones.

Fix:

- Delete the auto-shift block. The wing is built exactly where its parameters put it.
- The legality checks T8.7 (5 mm clear air to the track and everything) and T8.5.2 (20 mm outboard height) decide. A wing that breaks them makes the car illegal; the search learns to avoid it.
- `assembly.py` records the built geometry's actual key values (lowest point, highest outboard point, chord line height) alongside the parameters.
- Margin requirement for manufacture: the search's legality gate requires every wing clearance margin ≥ 0.3 mm (not 0.05), to absorb SLS tolerance (0.1-0.2 mm) and assembly error. Put this design margin in `geometry_contract.py` as `MANUFACTURING_MARGIN_MM = 0.3` and apply it to every clearance-type check in the search's gate (not in the rule check itself: the report shows the true rule margin; the gate applies the extra 0.3 mm).

Why: an auto-shift makes two different parameter values build the same wing, and makes the response to a parameter discontinuous. Both break a surrogate model in Part 7.

### 5.3.8 F24 — rear wing: an absolute height, not a floating one

Today `build_rear_wing` places the wing at the body's top under it plus clearances, then lifts it to clear what is ahead. Its height changes with every body change, which is one reason the four rear-wing improvements did not add up.

Fix:

- Add `RearWing.z_chord_mm` (absolute chord-line height above the track) as a parameter with default equal to the current start car's built value.
- Build at that height. Pylon: from the wing down into the body, as today (2 mm in, never through the T5.5 wall).
- Legality: T9.6 clear air (5 mm to everything), T9.7 front view, T9.4.3 height. A body change that breaks clear air under the wing makes the car illegal; the search learns.
- Keep `clear_air_margin_mm` only as a way to compute the default.

### 5.3.9 F25 — rules with no check today

| Rule | New check | How |
|---|---|---|
| T7.6 uniform rolling diameter | per 5.1 Q1 | roundness: max − min radius of the tread vertices ≤ 0.05 mm on the CAD; equal diameters if required |
| T7.8 spin freely | `fit_wheel_free` | minimum distance from each wheel mesh to every other part except its own stub axle and bearing ≥ 0.5 mm (design margin for SLS tolerance; the rule itself is qualitative) |
| T5.4 angle ±3° | design assertion | the chamber axis is built along x; assert the bore direction vector in `fixed_hardware` is (±1, 0, 0) |
| T4.5 helmet fixed | design assertion | the halo part includes the helmet; assert the assembly's halo record names the combined part |
| T3.3 listed components | `T3.3_components` | the set of part names in the assembly ⊆ the allowed set from 5.1 Q6 |
| T8.6.2 / T9.5.2 element count | `T8.6.2_elements`, `T9.5.2_elements` | slice the wing mesh with planes y = const at 10 spanwise stations; count closed loops in each slice; max count ≤ 3 front, ≤ 2 rear |
| T8.6.2 / T9.5.2 chord measured horizontally | keep and strengthen | chord = x-extent of each slice's union (calipers along the track) at every station, min and max over stations |
| T8.6.3 / T9.5.3 thickness on the mesh | `T8.6.3_thickness` | in each slice, for each element, the maximum distance between upper and lower surface along z at fixed x (sample 50 x positions); min over stations of the max ≥ 2.0, max ≤ 6.0 |
| T9.5.1 one unbroken span | `T9.5.1_unbroken` | the wing mesh's slices exist at every station across ≥ 50 mm of span with no gap |
| T4.2 cargo inside the body | `T4.2_cargo` | cargo wedge mesh (from `virtual_cargo.py`) fully inside `machined_body.stl` and printed plugs: volume inside ≥ 99.95% of the cargo volume |

### 5.3.10 F26, F27 — T7.9 zones, decals

- After the user sends the T7.9 diagram (5.1 Q2): transcribe every dimension into `regs.py` with the figure number; rewrite `wheel_visibility_zones.py` to build exactly those shapes; add a test that builds the zones for the start car and compares their key coordinates with numbers worked out by hand from the diagram (write the hand calculation in the test's docstring).
- T4.6 logo: ray-cast from the side (−y direction, from y = 200 mm) on a 0.5 mm grid over a candidate 30 × 15 rectangle on the body's side surface; **100%** of rays must hit the body first (the current 0.5% allowance is removed). The location of the rectangle is searched (the check passes if any position on each side works); record the position for the build.
- T4.7 team number: implement after 5.1 Q3.

### 5.3.11 F33, F34 — keep-clear width and cargo growth in Part 1

- `unified_phi.py:286` uses `WHEEL_WIDTH_M` (the rear width, 17.25 mm) for both axles' keep-clear bands. Use `FRONT_WHEEL_WIDTH_M` for the front.
- `unified_phi.py:631-633` grows the forced-solid cargo by one grid cell. At 1 mm grid that adds about 0.6 g of mandatory foam; at 2 mm, 1.3 g; at 0.3 mm, less. The legality outcome then depends on grid spacing. Replace the growth with an exact rule: forced solid = cells whose centres are within the cargo wedge **or** within half a cell of its surface (sub-cell), and rely on the mesh-level T4.2 check (5.3.9) as the authority.

---

## 5.4 Machinability with the real tool (F31, F32)

Today `machining.reachable_air` models an infinitely long tool whose shank has the ball's diameter, reaching straight in along ±z and ±y. Real tools have a stick-out length and a wider holder.

Inputs (Part 3 M10, or **ASK THE USER**): `tool_stickout_mm` (length of tool from holder face to ball tip), `holder_diameter_mm`, and which faces the team machines from (today: top, bottom, left, right).

Algorithm (extends the existing one; keep its structure):

1. Existing: ball centres = air cells whose distance to solid (EDT) > tool radius r (3.125 mm); "usable" centres along direction d have an unobstructed straight line of centres to the block boundary.
2. New: along that same line, beyond distance `L = stickout − r` from the ball centre, the clearance must exceed the holder radius R_h instead of r. Compute a second EDT-threshold mask `EDT > R_h`; a centre is usable along d only if every cell on its line from distance L onward satisfies the holder mask.
3. Implementation detail: for each of the four directions, the line test is a cumulative AND along that axis (the existing `_visible` does this with `np.logical_and.accumulate` or equivalent). Do it twice: once with the ball mask from the centre, once with the holder mask shifted by L cells. Combine.
4. Keep the result re-quantised and redistanced as today.

Test: a synthetic block with a 25 mm deep, 8 mm wide side slot: with stick-out 30 mm the slot bottom is reachable; with stick-out 15 mm and a 20 mm holder it is not.

Delete `unified_phi.enforce_machinability` if Part 2 has not. Keep `surface_extraction._find_inaccessible_faces` as a report only, and make the legality report include `machining_unreachable_mm3` from `reachable_air` as a hard check (must be 0 outside rule-required air, which the existing code already treats separately).

---

## 5.5 Mass: a margin that survives reality (F09, F28)

### 5.5.1 The problem

The car must weigh at least 48.0 g without the cartridge. The code sizes it to 48.2 g, a 0.2 g margin. Unmeasured or unmodelled:

| Source | Size (estimate, replace with measured) |
|---|---|
| Foam density (0.163 assumed) | ±3% of ~33 g of foam ≈ ±1.0 g |
| Voxel mass at 1 mm grid (team's own figure) | ±0.3 g |
| Remesh accepts ±0.5% volume after the mass is computed | ±0.16 g |
| Glue | +0.1 to +0.5 g (unmodelled) |
| Decals, paint | +0.1 to +0.4 g (unmodelled) |
| Sanding | −0.1 to −0.5 g |
| SLS part density and size | ±2-5% of ~10 g ≈ ±0.3 g |

The total uncertainty is about ±1.2 g (root sum of squares). A 0.2 g margin fails at the scale roughly 4 times in 10.

### 5.5.2 Fix the computation order (F28)

`run_car.py` computes the manufactured mass (`joints.make_all`, line ~405) **before** `remesh_file` runs (lines ~408-411). Change the order: remesh first, then re-read each final STL file, compute its volume and mass from those files, then add every non-geometric mass from `inputs/measured.json`:

```
m_manufactured = Σ_files ρ_material · V_file
               + 4 · bearing_g + glue_g_per_joint · n_joints + decal_paint_g
               + halo_mass_g + wheel masses (measured, M5) − sanding loss (M10: area × loss per cm²)
               + ballast_g
```

### 5.5.3 The uncertainty budget and the T3.6 gate

Compute σ_m from `measured.json` sds by Monte Carlo (same pattern as Part 4 section 4.9) over: foam density, PA12 and PLA density, glue, decals, sanding, and the remesh volume tolerance as a uniform ±0.5% on each file.

Gate: `m_manufactured − 3 σ_m ≥ 48.0 g`. Report the margin at 3σ.

### 5.5.4 TEAM DECISION: ballast

The team decided on 2026-09-27/28 to add no ballast, so the body itself makes the car reach 48.2 g. Present this to the user with the numbers:

```
QUESTION (Part 5, mass policy — TEAM DECISION):
Today the body is sized so the car weighs 48.2 g with no ballast. The mass uncertainty is about
±<σ> g (1σ), so the car must be designed to <48.0 + 3σ> g to pass the scale reliably. Each
gram costs about <rate> real ms (Part 4 exchange rates).
Options:
 (A) No ballast; design to 48.0 + 3σ g. Heavier and slower by about <3σ × rate> ms, but simple.
 (B) Build light (about <48.0 − 1.0> g, the body's realistic minimum), weigh the finished car,
     and add lead ballast in the regulation capsule (T1.22, capacity about 15.8 g of lead) to
     reach 48.05-48.1 g on the day. The ballast capsule's position also lowers the centre of
     mass, which helps the launch (Part 4 section 4.2.2).
 (C) Let the search decide how much of the mass is ballast (a search parameter), with the
     final trim at the scale.
Default if you say "you decide": (C), because it gives the search the centre-of-mass lever
and the scale trim removes the mass uncertainty entirely.
```

(Fill in the numbers before asking.) Record the decision verbatim. Under (B) or (C), add `ballast_g` as a parameter in `run_car` (the option `--ballast-g` already exists) and size the body to `48.0 + scale margin − ballast_g − other parts`; under (C) Part 7 searches it.

---

## 5.6 Strength margins for the physical tests (F29, F30)

These are computed margins, not proofs. Every input comes from `measured.json` (materials, Part 3 M6) or the regulation answers (5.1 Q10). Use a safety factor of 2 on material strength. Report each as a margin in the legality report (pass if ≥ 0), named `phys_halo_load`, `phys_guide_pull`, `phys_wheel_hang`, `phys_wing_load`.

| Test | Load path | Calculation |
|---|---|---|
| Halo 2 kg (19.6 N) | halo presses into its foam pocket | bearing stress = F / (pocket floor contact area); margin = foam compressive strength / 2 − stress |
| Tether guide 200 g pull (1.96 N) | guide cantilever and its glue joint | guide: bending stress σ = M·c/I with M = F × (distance from load to root), c and I from the guide's root cross-section; margin vs PA12 strength / 2. Glue: shear stress = F / glued area vs glue shear strength / 2 (**ASK THE USER** which glue; use the datasheet value) |
| Wheel hang 100 g (0.98 N) per wheel | stub axle bending | stub: σ = M·c/I, M = F × stub length from support face to bearing centre, solid circle I = π d⁴/64, c = d/2 |
| Wing aerodynamic load | wing as a cantilever from its mount | load = 1.5 × max(|lift|) at 25 m/s from CFD patch forces (scale (25/20)²), distributed; root bending stress vs material / 2; tip deflection < 0.5 mm (E from datasheet) |

Replace `beam_support.py:37-43`'s back-fitted loads (3 N / 1.2 N chosen so the existing disc passes) with these regulation loads plus a stated race load (launch acceleration × wheel and support mass, about 130 m/s² × a few grams, which is small; and a side load from tether slap, **ASK THE USER** if the team has seen supports break).

Material strengths: PA12 (SLS) tensile about 45-50 MPa in-plane, lower (about 40) along the build direction; use the datasheet of the team's print service and the lower value. Foam: Part 3 M6.

---

## 5.7 Grid-spacing check (legality must not depend on the grid)

Build golden G3 at grid spacings 1.0, 0.5 and 0.3 mm (`--cfd-mm`; 0.3 mm is the production export). Every rule check must pass at all three, and every margin must agree within 0.3 mm (or 0.1 g for mass). If not, find which check depends on spacing and fix it (the cargo growth in 5.3.11 is the known case). The 0.3 mm build has never been run end to end; expect memory problems (about 28 M cells, about 220 MB per float64 array); if it does not fit in a 16 GB job, report it and run it on the largest machine available (Part 1 section 1.12).

---

## 5.8 Stress test: prove the builder and checks on random cars

Rewrite `checks/stress_cars.py` usage:

1. **Before the fixes** (after Part 2): 400 random cars across the full range of every setting, **sized** (mass loop on, not fixed skin). Record: crash rate, legal rate, and the failure reason histogram.
2. **After the fixes:** the same 400 seeds.
3. Every crash is a bug: fix it. Every legality failure is classified as "genuinely illegal parameters" (expected) or "builder produced something the parameters did not ask for" (bug).
4. Gate: zero crashes; zero builder bugs in a fresh set of 200 seeds after the fixes.

Batch: kind `car` with the stress script's argv, 10 cars per job, 40 jobs per run. Results go to `results/db.jsonl` like any other batch.

---

## 5.9 Exit gate for Part 5

- [ ] `regs.py` exists; no regulation literal remains elsewhere (test passes).
- [ ] F17-F34 each fixed and committed with its ID.
- [ ] The report counts rule checks and design assertions separately; READMEs show the true numbers.
- [ ] Mass gate at 3σ in place; the ballast decision recorded.
- [ ] Physical-test margins computed with stated inputs.
- [ ] Grid-spacing check passes at 1.0, 0.5 and (if feasible) 0.3 mm.
- [ ] Stress gate passed.
- [ ] New golden fingerprints accepted by the user, with the before/after margin table.

Now open `06_CFD_STOPWATCH.md`.
