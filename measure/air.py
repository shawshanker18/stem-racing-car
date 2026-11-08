"""Air density from temperature, pressure and humidity (CIPM-2007 simplified, adequate to 0.1%)."""
import math


def air_density(temp_c: float, pressure_hpa: float, rh_pct: float) -> float:
    T = temp_c + 273.15
    p = pressure_hpa * 100.0
    es = 6.1078 * 10 ** (7.5 * temp_c / (temp_c + 237.3)) * 100.0     # Tetens, Pa
    pv = rh_pct / 100.0 * es
    Rd, Rv = 287.058, 461.495
    return (p - pv) / (Rd * T) + pv / (Rv * T)


assert abs(air_density(15.0, 1013.25, 0.0) - 1.2250) < 0.001
