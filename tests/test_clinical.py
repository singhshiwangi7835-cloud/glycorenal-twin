import pytest

from src.pipeline.cgm import cgm_metrics
from src.pipeline.egfr import egfr_ckd_epi_2021, egfr_slope_per_year
from src.pipeline.kdigo import kdigo_stage


@pytest.mark.parametrize("scr,age,sex,expected", [
    (1.0, 50, "M", 91.7),   # hand-calculated from the CKD-EPI 2021 formula
    (1.0, 50, "F", 68.6),
    (0.7, 40, "F", 112.1),
])
def test_egfr_ckd_epi_2021(scr, age, sex, expected):
    assert egfr_ckd_epi_2021(scr, age, sex) == pytest.approx(expected, abs=0.2)


def test_egfr_rejects_bad_input():
    with pytest.raises(ValueError):
        egfr_ckd_epi_2021(0, 50, "M")
    with pytest.raises(ValueError):
        egfr_ckd_epi_2021(1.0, 15, "M")


@pytest.mark.parametrize("egfr,uacr,stage,risk", [
    (95, 10, "G1-A1", "low"),
    (75, 100, "G2-A2", "moderate"),
    (50, 10, "G3a-A1", "moderate"),
    (50, 100, "G3a-A2", "high"),
    (35, 400, "G3b-A3", "very_high"),
    (10, 5, "G5-A1", "very_high"),
])
def test_kdigo(egfr, uacr, stage, risk):
    k = kdigo_stage(egfr, uacr)
    assert k["stage"] == stage and k["risk"] == risk


def test_kdigo_ckd_definition():
    assert not kdigo_stage(95, 10)["has_ckd"]
    assert kdigo_stage(95, 40)["has_ckd"]
    assert kdigo_stage(55, 10)["has_ckd"]


def test_egfr_slope():
    assert egfr_slope_per_year([(0, 90), (1, 85), (2, 80)]) == -5.0
    assert egfr_slope_per_year([(0, 90)]) is None


def test_cgm_metrics():
    m = cgm_metrics([60, 100, 150, 200, 250])
    assert m["tir_pct"] == 40.0
    assert m["tbr_pct"] == 20.0
    assert m["tar_pct"] == 40.0
    assert m["gmi_pct"] == pytest.approx(3.31 + 0.02392 * 152, abs=0.01)
