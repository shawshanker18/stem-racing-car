# body — the milled body and the rules that shape it

Part of the STEM Racing car optimiser; see the repository README and `bible/`.

The milled body of a STEM Racing car as ONE labelled level-set field on a 1 mm
grid, with every rule that shapes it applied as a hard mask, and the parametric
"hybrid" body the search draws into that field (94 settings: 8 loft stations x 3, 9 shape
scalars, 5 underfloor-tunnel settings, 56 sculpt modes of sigma 7 mm, 32 on the fuselage and
24 on the sidepods).

| module | what |
|---|---|
| `geometry_contract.py` | every dimension and density the parts share (grid spacing, wheel radius, cargo, densities) |
| `unified_phi.py` | the one field: build the envelope with the rule masks (T4.2 cargo, T5.5 cartridge wall, halo pocket, ballast area, T7.9 wheel zones, model block), symmetry, remap, mass from sub-cell volume fractions, half-surface extraction |
| `param_body.py` | the hybrid body: an 8-station superellipse loft, sidepods, a smooth blend, an underfloor tunnel and 56 sculpt modes, drawn into the field, made machinable, and sized by a uniform skin offset to a mass target |
| `machining.py` | the team's process on the grid: 6.25 mm ball end from top, bottom, left and right; every concave corner gets the cutter radius, rule-required air is grown until the ball can reach it |
| `fixed_hardware.py`, `hardware_geometry.py`, `halo_pocket.py`, `virtual_cargo.py`, `wheel_visibility_zones.py`, `bounding_volumes.py` | the fixed parts (cartridge, halo, wheels, cargo) and the masks they impose; `hardware_cad/` holds the team's STLs |
| `sdf.py` | signed-distance reinitialisation (used by the body sizing, the machining filter and grid remaps) |
| `surface_extraction.py` | marching-cubes surfaces and the CFD-ready half STL |
| `ballast.py` | the T3.6 target (48.2 g) and the ballast rules; the team adds no ballast, the body volume carries the mass |
| `coarse.py` | run the pipeline at another grid spacing (1 mm for the search, 0.3 mm production) |

The level-set carve was retired (see `docs/HISTORY.md` at the repository root): the
parametric body is the car. The original build spec, build report and placeholder list are in
`archive/part1-docs/`; they describe retired code. The regulations are the PDF; the numbers the
code checks are listed in the bible (`bible/00_START_HERE.md` section 0.6).

```bash
pip install -r requirements.txt
python -m pytest tests -q
```
