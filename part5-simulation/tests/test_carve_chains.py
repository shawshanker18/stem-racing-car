"""N search chains on a farm too small for all of them at once: every chain still finishes, the
result matches running with unlimited slots, and no tick starts more than the free slots."""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

import carve_loop as cl


def _f(x):
    return float(np.sum((np.asarray(x) - 0.3) ** 2))


def _farm(state, free, max_new):
    results, running, ticks = {}, [], 0
    while any(c["status"] == "running" for c in state["chains"]):
        cl.plan(state, lambda x: 2 * (np.asarray(x) - 0.3), lambda x, d, s: list(np.asarray(x) + s * d))
        new = cl.to_start(state, results, set(running), min(max_new, free - len(running)))
        assert len(new) <= max_new and len(running) + len(new) <= free
        running += new
        need = cl.needed(state)
        for k in running[:free // 2 or 1]:                 # half the running jobs finish each tick
            results[k] = _f(need[k][0]) if k in need else 0.0
        running = [k for k in running if k not in results]
        cl.advance(state, results, 1e-4, 1e-12)
        ticks += 1
        assert ticks < 20000
    return state


def _start(n):
    return {"chains": [cl.new_chain(i, list(np.full(3, 0.05 + 0.3 * i)), 0.1) for i in range(n)]}


def test_three_chains_share_a_small_farm():
    s = _farm(_start(3), free=4, max_new=2)
    for c in s["chains"]:
        assert c["status"] in ("converged", "out_of_rounds")
        assert _f(c["x"]) < _f(np.full(3, 0.05 + 0.3 * c["id"])) or _f(c["x"]) < 1e-3


def test_slots_do_not_change_the_answer():
    small, big = _farm(_start(3), 4, 2), _farm(_start(3), 10 ** 6, 10 ** 6)
    for a, b in zip(small["chains"], big["chains"]):
        assert np.allclose(a["x"], b["x"]) and a["round"] == b["round"]


def test_round_robin():
    s = _start(3)
    cl.plan(s, lambda x: [1.0, 0, 0], lambda x, d, z: list(np.asarray(x) + z * np.asarray(d)))
    first = cl.to_start(s, {}, set(), 3)
    assert sorted(k.split("_")[1] for k in first) == ["c0", "c1", "c2"]


def test_deterministic_stopwatch_false_keep():
    """Re-runs repeat a shape's own error (Part 2: repeat 0.01 ms, car-to-car 0.09 ms). With the
    measured shape noise in the keep rule, a flat function keeps <= 5 % of rounds."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "checks"))
    import bench
    fk, rounds = bench.false_keep_shape(0.09e-3, 150, repeat=1e-5, aware=True)
    assert rounds > 100 and fk <= 0.05, (fk, rounds)


def test_a_step_whose_hashes_differ_is_refused():
    import pytest
    good = {"legal": True, "T_s": 1.0, "expect_field_sha": "a", "field_sha": "a", "judged_field_sha": "a"}
    assert cl._t(good) == 1.0
    for bad in ({**good, "field_sha": "b"}, {**good, "judged_field_sha": "b"}, {**good, "legal": False},
                {**good, "expect_field_sha": None}):
        assert cl._t(bad) == float("inf")
        with pytest.raises(ValueError):
            cl._t(bad, current=True)
