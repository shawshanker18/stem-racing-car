"""p1_stage_mem_lab: peak memory and time of each stage of run_car's build (no CFD), for
splitting the build across jobs only where it lowers the peak (2026-11-15).

    python ../.github/lab/p1_stage_mem_lab.py <start|round2|parts>    (from part5-simulation)

Each stage function is wrapped: a thread samples this process's RSS every 50 ms during the
call. Prints one "LAB stage {json}" line per call (name, call number, seconds, RSS before,
after and peak during, GB), then the run's overall peak."""
import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path.cwd().parent
for p in ("part1-simulation", "part2-simulation", "part3-simulation", "part4-simulation"):
    sys.path.insert(0, str(ROOT / p))
sys.path.insert(0, str(Path.cwd()))


def rss_gb() -> float:
    with open("/proc/self/statm") as f:
        return int(f.read().split()[1]) * 4096 / 1e9


_count = {}


def wrap(mod, name):
    fn = getattr(mod, name, None)
    if fn is None:
        return
    label = f"{mod.__name__}.{name}"

    def w(*a, **k):
        _count[label] = _count.get(label, 0) + 1
        peak, stop = [rss_gb()], threading.Event()

        def sample():
            while not stop.is_set():
                peak[0] = max(peak[0], rss_gb())
                time.sleep(0.05)
        th = threading.Thread(target=sample, daemon=True)
        before, t0 = rss_gb(), time.time()
        th.start()
        try:
            return fn(*a, **k)
        finally:
            stop.set()
            th.join()
            print("LAB stage " + json.dumps({"stage": label, "call": _count[label],
                                             "s": round(time.time() - t0, 1), "before_gb": round(before, 2),
                                             "after_gb": round(rss_gb(), 2), "peak_gb": round(max(peak[0], rss_gb()), 2)}),
                  flush=True)
    setattr(mod, name, w)


import machining  # noqa: E402
import param_body  # noqa: E402
import run_car  # noqa: E402
import unified_phi  # noqa: E402

for mod, names in ((run_car, ["build_body", "export_body", "parts_and_joints", "make_bindings", "mass_state"]),
                   (param_body, ["build", "_stamp_bore", "_shave_to"]),
                   (machining, ["make_machinable"]),
                   (unified_phi, ["build_unified_geometry", "extract_half_surface", "extract_unified_surface"])):
    for n in names:
        wrap(mod, n)
# param_body imported these by name from machining: wrap its own reference too
if hasattr(param_body, "machining"):
    param_body.machining = machining

car = sys.argv[1]
args = {"start": ["--body-json", "{}"],
        "round2": ["--body-json", Path("checks/round2_car.json").read_text()],
        "parts": ["--body-json", Path("checks/round2_car.json").read_text(), "--fwing-json", '{"aoa_deg": 8.0}',
                  "--support-json", '{"disc_front": true}', "--nose-json", '{"length_mm": 25.0, "wall_mm": 99.0}']}[car]
t0 = time.time()
try:
    run_car.main(["--out", f"../out/{car}"] + args)
except SystemExit as e:
    print(f"LAB exit {e}", flush=True)
import resource  # noqa: E402
print("LAB total " + json.dumps({"car": car, "s": round(time.time() - t0, 1),
                                 "maxrss_gb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6, 2)}),
      flush=True)
