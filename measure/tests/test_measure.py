"""Each measurement script on synthetic data with a known answer (bible Part 3)."""
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))


def _thrust(tt, peak=9.2, tau=0.25, rise=0.005):
    """A cartridge-like curve: a 5 ms rise, exponential decay, cut at 0.5 s."""
    on = (tt >= 0) & (tt < 0.5)
    tc = np.clip(tt, 0, None)
    return np.where(on, peak * np.exp(-tc / tau) * (1 - np.exp(-tc / rise)), 0.0)


def _write_thrust_folder(d: Path, fs=2000, onset=0.4, ring_hz=700.0, seed=0):
    rng = np.random.default_rng(seed)
    slope, intercept = 0.01, -0.05            # reading -> N
    with open(d / "calibration.csv", "w") as fh:
        fh.write("mass_g,mean_reading,sd_reading\n")
        for m in (0, 100, 200, 500, 1000):
            F = m * 1e-3 * 9.80665
            fh.write(f"{m},{(F - intercept) / slope},0.1\n")
    for k in range(3):
        t = np.arange(0, 2.5, 1 / fs)
        tt = t - onset
        F = _thrust(tt) + 0.02 * np.sin(2 * np.pi * ring_hz * t) + rng.normal(0, 0.01, len(t))
        reading = (F - intercept) / slope
        np.savetxt(d / f"run{k + 1:02d}.csv", np.c_[t, reading], delimiter=",", header="t_s,reading", comments="")


def test_thrust_recovers_impulse_and_peak(tmp_path):
    _write_thrust_folder(tmp_path)
    out = tmp_path / "thrust.csv"
    subprocess.run([sys.executable, str(HERE / "thrust.py"), str(tmp_path), "--charge-g", "8.0", "--out", str(out)],
                   check=True, capture_output=True)
    s = json.loads((tmp_path / "summary.json").read_text())
    fine = np.linspace(0, 0.6, 600001)
    expect, peak = float(np.trapezoid(_thrust(fine), fine)), float(_thrust(fine).max())
    assert abs(s["impulse_Ns_mean"] - expect) / expect < 0.02
    assert abs(s["peak_N_mean"] - peak) / peak < 0.03
    rows = out.read_text().splitlines()
    assert rows[0] == "time (s),force (N),mass (kg)"
    first, last = rows[1].split(","), rows[-1].split(",")
    assert abs(float(first[2]) - 0.008) < 1e-6 and float(last[2]) < 1e-6


def test_coastdown_recovers_resistances(tmp_path):
    from coastdown import simulate
    car = {"mass_g": 69.0, "added_mass_g_by_run": {"run04": 20.0, "run05": 20.0, "run06": 20.0},
           "wheel_I_total_kgm2": 5.5e-7, "wheel_r_m": 0.01412}
    (tmp_path / "car.json").write_text(json.dumps(car))
    rng = np.random.default_rng(1)
    for k in range(6):
        name = f"run{k + 1:02d}"
        m = (car["mass_g"] + car["added_mass_g_by_run"].get(name, 0.0)) * 1e-3
        m_eff = m + car["wheel_I_total_kgm2"] / car["wheel_r_m"] ** 2
        t = np.linspace(0, 1.5, 200)
        x = simulate(t, 0.0, 3.0 + 0.2 * k, m, m_eff, 0.004, 0.008, 0.41 / 400) + rng.normal(0, 0.002, len(t))
        np.savetxt(tmp_path / f"{name}.csv", np.c_[t, x], delimiter=",", header="t_s,x_m", comments="")
    subprocess.run([sys.executable, str(HERE / "coastdown.py"), str(tmp_path), "--D20", "0.41"],
                   check=True, capture_output=True)
    f = json.loads((tmp_path / "fit.json").read_text())
    assert abs(f["R0_N"] - 0.004) / 0.004 < 0.2
    assert abs(f["mu"] - 0.008) / 0.008 < 0.2


def test_air_density_standard_day():
    from air import air_density
    assert abs(air_density(15.0, 1013.25, 0.0) - 1.225) < 0.001
    assert air_density(30.0, 1013.25, 50.0) < 1.17


def test_spindown_recovers_torques():
    from spindown import fit
    I, tau0, k = 1.2e-7, 2e-6, 1e-9
    t = np.linspace(0, 5, 300)
    w0 = 1000.0
    # I dw/dt = -(tau0 + k w): w(t) = (w0 + tau0/k) e^(-k t / I) - tau0/k
    w = (w0 + tau0 / k) * np.exp(-k * t / I) - tau0 / k
    keep = w > 0
    got = fit(t[keep], w[keep] * 60 / (2 * np.pi), I)
    assert abs(got[0] - tau0) / tau0 < 0.05 and abs(got[1] - k) / k < 0.05


def test_block_density_subtracts_bore_and_slot():
    from density import block_density
    sys.path.insert(0, str(HERE.parent / "body"))
    from geometry_contract import MODEL_BLOCK_BORE_DEPTH_MM, MODEL_BLOCK_BORE_DIA_MM
    vol_cm3 = (223 * 65 * 50 - math.pi * (MODEL_BLOCK_BORE_DIA_MM / 2) ** 2 * MODEL_BLOCK_BORE_DEPTH_MM
               - 6 * 6 * 223) / 1000.0
    assert abs(block_density(0.163 * vol_cm3, 223, 65, 50) - 0.163) < 1e-9


def test_inertia_scaling_is_identity_at_cad_mass():
    from inertia import scale
    assert abs(scale(1.23e-7, 1.15, 1.15, 0.30) - 1.23e-7) < 1e-15
    assert scale(1.23e-7, 1.15, 1.30, 0.30) > 1.23e-7


def test_tether_capstan(tmp_path):
    from tether import mu_rows
    W = 0.1 * 9.80665
    with open(tmp_path / "pulls.csv", "w") as fh:
        fh.write("angle_deg,hanging_g,pull_N\n")
        for ang in (0, 3, 6):
            fh.write(f"{ang},100,{W * math.exp(0.3 * math.radians(ang))}\n")
    assert all(abs(m - 0.3) < 1e-9 for m in mu_rows(tmp_path / "pulls.csv"))


def test_record_marks_measured(tmp_path):
    from record import record, unmeasured
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"mu_roll": {"value": 0.01, "measured": False}, "x": {"value": 1, "measured": False}}))
    record("mu_roll", 0.008, sd=0.001, n=5, source="test", path=p)
    assert unmeasured(p) == ["x"]
    assert json.loads(p.read_text())["mu_roll"]["value"] == 0.008
