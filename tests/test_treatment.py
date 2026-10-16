"""Eligibility and safety rules (clinical_rules.yaml -> eligibility). Shiwangi: check these cases."""

from src.treatment.eligibility import evaluate, safety_warnings

NO_MEDS = {f"on_{c}": 0 for c in ["metformin", "sglt2i", "glp1ra", "dpp4i", "sulfonylurea", "insulin",
                                  "acei_arb", "finerenone", "statin", "acei", "arb"]}


def make_state(egfr=70, uacr=10, potassium=4.5, hba1c=8.0, meds=None, sbp=135, dbp=85, bmi=26,
               steps=4000, smoker=False, htn=True):
    return {
        "kidney": {"egfr": egfr, "uacr": uacr},
        "labs": {"potassium": {"value": potassium} if potassium is not None else None},
        "glycaemia": {"hba1c": hba1c},
        "med_flags": {**NO_MEDS, **(meds or {})},
        "profile": {"hypertension": htn, "smoker": smoker},
        "vitals": {"sbp": sbp, "dbp": dbp, "bmi": bmi, "steps_per_day": steps},
        "bp": {"on_target": sbp < 130 and dbp < 80, "target": "130/80"},
    }


def opts(state):
    return {o["option"]: o for o in evaluate(state)["options"]}


def test_egfr_25_metformin_not_started_sglt2i_allowed():
    o = opts(make_state(egfr=25))
    assert not o["metformin"]["eligible"] and "do not start" in o["metformin"]["reason"]
    assert o["sglt2i"]["eligible"]


def test_egfr_18_no_new_sglt2i():
    assert not opts(make_state(egfr=18))["sglt2i"]["eligible"]


def test_metformin_safety_on_existing_prescription():
    assert any("contraindicated" in w for w in safety_warnings(make_state(egfr=25, meds={"on_metformin": 1})))
    assert any("reduce" in w for w in safety_warnings(make_state(egfr=40, meds={"on_metformin": 1})))
    assert not safety_warnings(make_state(egfr=60, meds={"on_metformin": 1}))


def test_finerenone_rules():
    on_arb = {"on_acei_arb": 1, "on_arb": 1}
    assert opts(make_state(uacr=100, egfr=40, potassium=4.6, meds=on_arb))["finerenone"]["eligible"]
    assert not opts(make_state(uacr=20, egfr=40, potassium=4.6, meds=on_arb))["finerenone"]["eligible"]
    assert not opts(make_state(uacr=100, egfr=22, potassium=4.6, meds=on_arb))["finerenone"]["eligible"]
    assert not opts(make_state(uacr=100, egfr=40, potassium=5.2, meds=on_arb))["finerenone"]["eligible"]
    assert not opts(make_state(uacr=100, egfr=40, potassium=None, meds=on_arb))["finerenone"]["eligible"]
    no_arb = opts(make_state(uacr=100, egfr=40, potassium=4.6))["finerenone"]
    assert not no_arb["eligible"] and "ACEi/ARB" in no_arb["reason"]


def test_acei_arb_rules():
    assert opts(make_state(uacr=100, htn=False))["acei_arb"]["eligible"]
    assert not opts(make_state(uacr=10, htn=False, sbp=125, dbp=78))["acei_arb"]["eligible"]
    assert not opts(make_state(uacr=100, meds={"on_acei_arb": 1, "on_acei": 1}))["acei_arb"]["eligible"]
    both = make_state(meds={"on_acei_arb": 1, "on_acei": 1, "on_arb": 1})
    assert any("do not combine" in w for w in safety_warnings(both))


def test_hypo_risk_flags():
    su = opts(make_state(egfr=35))["sulfonylurea"]
    assert su["eligible"] and any("High hypoglycaemia" in c for c in su["cautions"])
    assert any("Sulfonylurea" in w for w in safety_warnings(make_state(egfr=35, meds={"on_sulfonylurea": 1})))


def test_glucose_drugs_not_offered_at_target():
    o = opts(make_state(hba1c=6.5))
    assert not o["sulfonylurea"]["eligible"] and not o["insulin_basal"]["eligible"]


def test_lifestyle_levers():
    o = opts(make_state(bmi=24, steps=9000, smoker=True, sbp=128, dbp=78))
    assert o["weight_loss_5pct"]["eligible"]          # Asian cut-off 23
    assert not o["steps_plus_2000"]["eligible"]
    assert o["stop_smoking"]["eligible"]
    assert not o["bp_control"]["eligible"]


def test_every_option_has_a_source():
    assert all(o["source"] for o in evaluate(make_state())["options"])
