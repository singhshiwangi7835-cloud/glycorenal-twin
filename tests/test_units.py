import pytest

from src.clinical import units


def test_glucose():
    assert units.glucose_mmol_to_mg(10) == pytest.approx(180.2, abs=0.1)
    assert units.glucose_mg_to_mmol(180) == pytest.approx(9.99, abs=0.01)


def test_creatinine():
    assert units.creatinine_umol_to_mg(88.42) == pytest.approx(1.0, abs=0.001)


def test_hba1c_ifcc_to_ngsp():
    assert units.hba1c_mmol_mol_to_pct(53) == pytest.approx(7.0, abs=0.1)
    assert units.hba1c_pct_to_mmol_mol(7.0) == pytest.approx(53, abs=1)


def test_to_standard():
    assert units.to_standard("glucose", 5.5, "mmol/L", "mg/dL") == pytest.approx(99.1, abs=0.1)
    assert units.to_standard("uacr", 3.4, "mg/mmol", "mg/g") == pytest.approx(30.1, abs=0.1)
    assert units.to_standard("glucose", 120, "mg/dL", "mg/dL") == 120
    with pytest.raises(ValueError):
        units.to_standard("glucose", 1, "furlongs", "mg/dL")
