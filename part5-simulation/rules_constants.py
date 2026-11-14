"""
rules_constants.py -- the referee's own rule geometry, typed in from the 2026-27 Technical
Regulations (text identical to 2025-26; page numbers are the PDF's). Nothing here is
imported from Part 1: if Part 1 reads a drawing wrongly, the cutter and the referee must
not be wrong together. tests/test_independence.py compares these with Part 1's values.

Limits that are plain numbers in the rule text sit next to their checks in legality.py;
this file holds the shapes and sizes that come from the drawings.
"""

# Reference planes (T1.17.2, T1.17.3, p12-13).
REF_A_AHEAD_OF_FRONT_AXLE_MM = 16.0
REF_B_BEHIND_REAR_AXLE_MM = 16.0

# Official Model Block (Appendix ii, p48).
BLOCK_LENGTH_MM = 223.0
BLOCK_WIDTH_MM = 65.0
BLOCK_HEIGHT_MM = 50.0
BLOCK_BORE_DIA_MM = 18.15          # drawn 18.10-18.15; the larger, so the block is not undersized
BLOCK_BORE_DEPTH_MM = 52.0         # from the rear face
BLOCK_BORE_ABOVE_BOTTOM_MM = 29.0  # bore axis above the slotted face
BLOCK_SLOT_WIDTH_MM = 6.0          # centred, full length
BLOCK_SLOT_DEPTH_MM = 6.0

# Virtual cargo (T4.2, p22): a wedge in plan, constant height.
CARGO_LENGTH_MM = 60.0
CARGO_WIDE_MM = 55.0
CARGO_NARROW_MM = 10.0
CARGO_HEIGHT_MM = 10.0

# T7.9 keep-clear zones (p32 diagram), from each wheel's inner track-contact edge outward.
T79_WIDTH_Y_MM = 30.0              # every zone
T79_HEIGHT_MM = 65.0
T79_1_DEPTH_MM = 5.0               # ahead of the front wheels, rectangle
T79_2_NEAR_MM = 15.0               # behind the front wheels, at the inner edge ...
T79_2_ANGLE_DEG = 60.0             # ... far side at 60 deg to the car's axis, widening outward
T79_3_NEAR_MM = 5.0                # ahead of the rear wheels, at the inner edge ...
T79_3_ANGLE_DEG = 45.0             # ... far side at 45 deg, widening outward
T79_4_DEPTH_MM = 5.0               # behind the rear wheels, rectangle

# Halo pocket and legal ballast container (T4.4.4 p24, Appendix ix p56).
HALO_POCKET_FLOOR_Z_MM = 24.0      # T4.4.4: notch centre 34.0 +-1.0, 10.0 above the floor
HALO_NOTCH_ABOVE_FLOOR_MM = 10.0
HALO_POCKET_LENGTH_MM = 50.0
HALO_POCKET_WIDTH_MM = 25.0        # widest; the outline narrows to an R9 front (drawn as a box here)
HALO_POCKET_DEPTH_MM = 3.175
BALLAST_WIDTH_MM = 12.7            # 2 x R6.35
BALLAST_DEPTH_MM = 6.35            # below the pocket floor
# Not dimensioned directly on p56: measured off the drawing at scale (the pocket's 50 mm
# is 160 px there; the slot runs about 23.4-43.8 mm from the pocket's front).
BALLAST_LENGTH_MM = 20.0
BALLAST_CENTRE_FROM_POCKET_FRONT_MM = 34.0

# Wheel safety test claw (T7.13, p34 figure): the lip that hooks the wheel's inner corner.
CLAW_LIP_MM = 1.5

# Shortest legal cartridge (Appendix vi, p54): 65.00 -0.5 mm.
CARTRIDGE_LENGTH_MIN_MM = 64.5

# Machining (team limit, relayed 2026-11-14): the thinnest foam wall the team mills.
# Part 1's geometry_contract.MIN_MACHINED_WALL_MM carries the same value; the referee keeps
# its own (it imports nothing from Part 1) and tests/test_independence.py checks they agree.
MACHINED_MIN_WALL_MM = 3.0
