"""Part 4 lab: which support decision flips between sizing passes on the sized start and
parts reference cars? Logs every beam_support.build call: axle, floor, arch, channel
length, plate thickness, strip fit and the design chosen."""
import sys
from pathlib import Path

sys.path[:0] = [str(Path.cwd()), str(Path.cwd().parent / "part4-simulation")]
import beam_support as bsm

_orig = bsm.build


def build(bs, x, z, y_in, w, disc, hub_mm=(5.25, 8.25), R_mm=14.12, channel=None, mode=None):
    out = _orig(bs, x, z, y_in, w, disc, hub_mm=hub_mm, R_mm=R_mm, channel=channel, mode=mode)
    st, ch = out["_struct"], channel or {}
    print(f"FLIP x {x:.1f} mode_in {mode} -> {out['support_mode']} | floor {ch.get('z_floor_mm', float('nan')):.3f} "
          f"arch {ch.get('z_arch_mm', float('nan')):.3f} len {ch.get('length_mm', float('nan')):.3f} "
          f"plate_h {st.get('plate_h_mm', float('nan')):.3f} strip_fit {st.get('strip_fit_mm', float('nan')):.3f} "
          f"dropped {'strip_dropped_note' in st} mass_g {bsm.mass_kg(bs, out) * 1e3 / 2:.3f}", flush=True)
    return out


bsm.build = build
import run_car
car = sys.argv[1] if len(sys.argv) > 1 else "start"
args = ["--out", f"../out/{car}"]
if car == "parts":
    args += ["--body-json", Path("checks/round2_car.json").read_text(), "--fwing-json", '{"aoa_deg": 8.0}']
else:
    args += ["--body-json", "{}"]
run_car.main(args)
