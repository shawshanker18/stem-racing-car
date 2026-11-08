"""The official block (Appendix ii) sets where a car can be. These fail if the
chamber moves without the block moving with it."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

import geometry_contract as gc


def test_chamber_is_legal_and_the_block_clears_the_track():
    assert 30.0 <= gc.CHAMBER_AXIS_Z_MM <= 40.0                 # T5.2
    assert 18.0 <= gc.MODEL_BLOCK_BORE_DIA_MM <= 18.5           # T5.1
    assert 45.0 <= gc.MODEL_BLOCK_BORE_DEPTH_MM <= 58.0         # T5.3
    assert gc.MODEL_BLOCK_BOTTOM_Z_MM >= 1.5                    # T3.7
    assert gc.MODEL_BLOCK_TOP_Z_MM - gc.MODEL_BLOCK_BOTTOM_Z_MM == gc.MODEL_BLOCK_HEIGHT_MM


def test_envelope_is_the_block():
    from bounding_volumes import default_rule_envelope
    re = default_rule_envelope()
    assert abs(re.z_floor_m * 1e3 - gc.MODEL_BLOCK_BOTTOM_Z_MM) < 1e-9
    assert abs(re.z_body_top_m * 1e3 - gc.MODEL_BLOCK_TOP_Z_MM) < 1e-9


def test_cartridge_shell_plus_gas_is_the_official_full_weight():
    assert 28.9e-3 <= gc.CO2_MASS_KG + 8e-3 <= 29.4e-3          # Appendix vi


def test_a_built_body_keeps_the_slot_and_stays_in_the_block():
    from coarse import use_spacing
    use_spacing(1.0)
    import param_body as pb
    import unified_phi as up
    g = pb.build(120.3, 46.0, 43.72, pb.BodyParams(), skin_offset_mm=1.0)
    solid = g.phi.grid < 0
    assert not (solid & up.model_block_slot_mask(g.region)).any()
    zs = g.region.origin_m[2] + np.arange(g.region.shape[2]) * up.GRID_SPACING_M
    assert zs[solid.any(axis=(0, 1))].min() * 1e3 >= gc.MODEL_BLOCK_BOTTOM_Z_MM - 1e-6
    assert zs[solid.any(axis=(0, 1))].max() * 1e3 <= gc.MODEL_BLOCK_TOP_Z_MM + 1e-6
