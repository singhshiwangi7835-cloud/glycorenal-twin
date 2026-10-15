"""eGFR calculation using the CKD-EPI 2021 creatinine equation (race-free).

eGFR = 142 x min(Scr/k, 1)^a x max(Scr/k, 1)^-1.200 x 0.9938^age x 1.012 [if female]
  k = 0.7 (female) / 0.9 (male)
  a = -0.241 (female) / -0.302 (male)
Scr in mg/dL, result in mL/min/1.73 m^2.
"""

from __future__ import annotations


def egfr_ckd_epi_2021(creatinine_mg_dl: float, age: float, sex: str) -> float:
    if creatinine_mg_dl is None or creatinine_mg_dl <= 0:
        raise ValueError("creatinine must be a positive number (mg/dL)")
    if age is None or age < 18:
        raise ValueError("CKD-EPI 2021 is validated for adults (age >= 18)")

    female = str(sex).strip().upper() in {"F", "FEMALE"}
    kappa = 0.7 if female else 0.9
    alpha = -0.241 if female else -0.302

    ratio = creatinine_mg_dl / kappa
    egfr = (
        142
        * min(ratio, 1.0) ** alpha
        * max(ratio, 1.0) ** -1.200
        * 0.9938 ** age
    )
    if female:
        egfr *= 1.012
    return round(egfr, 1)


def egfr_slope_per_year(readings: list[tuple[float, float]]) -> float | None:
    """Least-squares slope of eGFR over time.

    readings: list of (years_from_first_reading, egfr). Needs >= 2 points.
    Returns change in mL/min/1.73m^2 per year (negative = decline).
    """
    if len(readings) < 2:
        return None
    n = len(readings)
    xs = [r[0] for r in readings]
    ys = [r[1] for r in readings]
    mx, my = sum(xs) / n, sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return None
    return round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom, 2)
