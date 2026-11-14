"""run_car.build_car sizes the car on its true manufactured mass, judges a car built at its
final target, and run_car refuses a car that does not reach 48.2 +- 0.05 g (2026-11-15).
A stand-in car: body as asked (sizing hits its target), parts that depend on the body."""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "part1-simulation"))

import pytest


def _fake(monkeypatch, parts_g):
    import run_car as rc
    import unified_phi as up
    built = []

    def build_body(a, out):
        body = a._body_target_kg if a._body_target_kg is not None else 0.030
        built.append(body)
        return types.SimpleNamespace(body=body), {}

    monkeypatch.setattr(rc, "build_body", build_body)
    monkeypatch.setattr(rc, "export_body", lambda g, p: {})
    monkeypatch.setattr(rc, "log", lambda *a, **k: None)
    monkeypatch.setattr(up, "compute_mass_com", lambda g: [types.SimpleNamespace(mass_kg=g.body)])
    monkeypatch.setattr(rc, "parts_and_joints", lambda a, out, g, *x, **k: {
        "body": g.body, "joints": {"mass_delta_kg": {}}, "info": {}})
    monkeypatch.setattr(rc, "manufactured_mass_kg", lambda asm: asm["body"] + parts_g(asm["body"]) * 1e-3)
    return rc, built


def test_smooth_parts_converge_and_judge_the_last_build(monkeypatch, tmp_path):
    # parts grow with the body (the keel under the support): 17 g + 10 % of the body
    rc, built = _fake(monkeypatch, lambda b: 17.0 + 0.1 * b * 1e3)
    a = types.SimpleNamespace(skin_mm=None)
    geom, info, asm = rc.build_car(a, tmp_path)
    assert info["mass_converged"] and abs(info["car_mass_error_g"]) <= 0.05
    assert geom.body == built[-1]                       # the judged car is the one built last
    assert rc.mass_refusal(info["car_mass_error_g"] * 1e-3, False) is None


def test_a_jump_across_the_target_is_refused(monkeypatch, tmp_path):
    # the support's design flips 3 g at a body of 30.0 g, right across 48.2 g
    rc, built = _fake(monkeypatch, lambda b: 16.5 if b < 0.030 else 19.5)
    a = types.SimpleNamespace(skin_mm=None)
    geom, info, asm = rc.build_car(a, tmp_path)
    assert not info["mass_converged"]
    assert geom.body == built[-1]
    assert rc.mass_refusal(info["car_mass_error_g"] * 1e-3, False).startswith("mass_not_converged")


@pytest.mark.parametrize("err_g,fixed,refused", [(0.049, False, False), (0.051, False, True),
                                                 (-0.06, False, True), (2.0, True, False)])
def test_mass_refusal(err_g, fixed, refused):
    import run_car as rc
    assert (rc.mass_refusal(err_g * 1e-3, fixed) is not None) == refused
