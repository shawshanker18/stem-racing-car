"""A car that hangs or dies must become a result, not take its machine with it."""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "checks"))

from stress_cars import guarded


def test_a_normal_run_a_hang_and_a_death_are_told_apart():
    assert guarded(time.sleep, (0.0,), 30.0, 12.0, poll_s=0.05)[0] == "ok"
    assert guarded(time.sleep, (60.0,), 0.5, 12.0, poll_s=0.05)[0] == "over time"
    assert guarded(os._exit, (3,), 30.0, 12.0, poll_s=0.05)[0] == "died (exit 3)"
