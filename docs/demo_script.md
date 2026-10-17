# GlycoRenal Twin: demo script (15-18 minutes)

For: Digital Twin Challenge 2026, Happiest Health Summit, Bengaluru. Presenter: Shiwangi.
Numbers below come from the dry run (`scripts/dry_run_demo.py`); yours will be within a few
points because the live sensor and dates change.

## Before you start (5 minutes, off camera)

1. Two PowerShell windows in the project folder:
   - `.\.venv\Scripts\python.exe -m uvicorn api.main:app` (wait for "Application startup complete")
   - `.\.venv\Scripts\python.exe -m streamlit run app/Home.py`
2. Open http://localhost:8501 in **two browser windows** side by side: left = doctor, right = patient
   (use a private window for the second login).
3. Log in as **admin / admin123** → Admin panel → **Demo data** tab → **▶ Start demo mode**.
   Wait for "Demo ready" (20-60 s). Download **ramesh_labs_today.csv** (also in `docs/demo/`).
4. Optional: put the Kimi key in `.env` and run `scripts/test_llm.py`. Without it everything works;
   AI answers show "offline summary". Kimi K2.6 is a "thinking" model: a summary takes 10-60 s and
   sometimes falls back to the template. **Warm the cache:** about 10 minutes before presenting, open
   Ramesh -> AI assistant -> Generate clinical summary once (answers are cached for 30 minutes and
   then appear instantly). Patient chat answers usually take 5-10 s.
5. Close other apps; set the screen zoom so the whole page fits.

---

## 0:00 - 1:30  The problem (no clicks; title slide)

> "India has over 100 million people with diabetes (ICMR-INDIAB 2023). About 1 in 3 develop diabetic kidney
> disease, and most find out late, when eGFR has already fallen. Doctors see a patient for five minutes
> every three months; the body changes every five minutes. We built a **digital twin**: a live copy of
> each patient that joins hospital records, sensors and daily habits, predicts what is coming, and lets the
> doctor test treatments on the twin before trying them on the patient."

## 1:30 - 3:30  Data in: hospital EHR (Admin)

Click: Admin panel → **EHR import** → **Import all Synthea samples** (or doctor portal → EHR tab →
Import sample).

> "Hospitals speak FHIR, the international standard for health records. Here the twin reads a FHIR R4
> bundle: diagnoses, lab results by LOINC code, prescriptions. It builds the patient's twin automatically:
> eGFR recalculated with the CKD-EPI 2021 race-free equation, KDIGO stage, medicines with reminders.
> It can also pull a record live from a FHIR server, here the public HAPI test server, and export the twin
> back as FHIR, so it fits into existing hospital software."

Point at the new patient (EHR-0001) with its risk score.

## 3:30 - 5:30  Doctor's view: one patient, Ramesh (Doctor)

Log in **dr.mehta / doctor123**. Show the patient list.

> "Every patient, sorted by predicted three-year kidney risk, coloured by the KDIGO heat map."

Open **IND-0042 · Ramesh Kumar**. Overview tab.

> "Ramesh, 54, nine years of diabetes. HbA1c 8.1 and rising, BP 146 over 88, kidneys still G2-A1: on
> paper, no kidney disease yet. But his twin says **77% chance of developing kidney disease in three
> years**, driven by his albuminuria, eGFR and glucose control. Note the KDIGO grid and the trends."

Open **🧬 Genetic markers (simulated test)**.

> "The twin also reads his genetic test from the EHR: a kidney polygenic score in the 82nd percentile
> raises his risk, and two gene variants (TCF7L2, CYP2C9) mean a sulfonylurea would work less well and
> carry more hypo risk, so the treatment advisor warns against it. These results are simulated."

## 4:30 - 5:30  His own twin, not an average (Doctor Personal twin tab)

Doctor → **Personal twin** tab.

> "This is not a population model. The twin has tuned itself to Ramesh's own body from 13 days of his
> CGM, 45 meals and his heart rate: his sugar rises about 13 mg/dL for every 10 grams of carbs and peaks
> 50 minutes after eating; two katoris of rice push him up about 140. To prove it is him: here it replays
> the last three days, which it never saw while learning; it matches his real sensor within about 8 mg/dL.
> It is progressive: it started from population values and gets more personal with every day of data;
> it knows him 90% now. His kidneys: his own eGFR is falling about 4.6 a year, faster than the 3.4 the
> population estimate expected; at this pace he reaches 45 in about 4 years, and with an SGLT2 inhibitor
> about 8."

Optional: change the what-if foods (e.g. jowar roti instead of rice) and show the lower peak.

## 5:30 - 8:00  Living twin: sensor + meal (Patient, then Doctor Live tab)

Right window: log in **ramesh / patient123** (opens in Hindi). Show **आज** (Today): big sugar number,
arrow, time-in-range ring, next medicine.

> "This is Ramesh's app, in Hindi. His CGM sends a reading every 5 minutes; in demo mode every 3 seconds."

Patient → **भोजन** (Meals) → pick **सफ़ेद चावल** (2 servings) + **अरहर दाल** → **भोजन सेव करें**.

Left window: doctor → **Live** tab. Within ~30 seconds glucose climbs past 250 (peak about 310) and an
alert appears.

> "He logged a typical lunch: two katoris of rice and dal, 99 grams of carbs. While his sugar is still
> normal, the twin raises a **spike early warning: above 250 likely within 90 minutes**. (Around his
> usual mealtimes it may appear even before he logs the meal; then say "it warned us before he ate".)
> It knows his habits: at this time of day he usually eats about 95 grams of carbs and went above 250 on
> most recent days. In our tests 3 out of 4 spikes were warned at least an hour ahead. His app shows the
> same warning in Hindi with a tip: a 15-minute walk. Then the live trace climbs past 250."

Patient → **भोजन**: show "आपकी शुगर सबसे ज़्यादा बढ़ाने वाले 3 खाने" (top 3 spiking foods).

## 8:00 - 9:00  Missed dose (Patient → Doctor Medications)

Patient → **दवाइयाँ** (Medicines): this morning's metformin shows **छूटी ✗** (missed); 7-day adherence ~67%.

> "Reminders come from his prescription times. He missed this morning's metformin; his adherence is 67%.
> That number feeds the twin, and the doctor sees it."

Doctor → **Medications** tab: adherence 7 and 30 days.

## 9:00 - 11:30  New lab results: the prediction comes true (Doctor EHR tab)

Doctor → **EHR** tab → **Add lab results** → upload **ramesh_labs_today.csv** → **Upload labs**.

> "Today's labs arrive from the lab: HbA1c 8.4, creatinine 1.34, urine albumin 85."

An alert appears: *Albuminuria rose from A1 to A2*. Go to **Overview**.

> "The twin's prediction came true: his albuminuria has crossed into A2. He now has diabetic kidney
> disease, KDIGO G2-A2. The twin switches from 'will he develop it' to 'will it get worse': **62% risk of
> worsening in three years** without a change."

## 11:30 - 14:00  Treatments simulated on the twin (Doctor Treatments tab)

Doctor → **Treatments** tab.

> "The treatment advisor checks eligibility from KDIGO 2022 and ADA rules: ACE-inhibitor or ARB: already on
> telmisartan, never combine. Then it simulates each eligible option on Ramesh's twin and ranks them.
> Top: **SGLT2 inhibitor, 62 to 38%**, source DAPA-CKD; then GLP-1 RA, finerenone, BP control. Every
> option shows its evidence and cautions. The doctor decides."

Tick **SGLT2 inhibitor** + **Bring BP to target** under *Apply to simulation*: bar chart 62% → ~34%.

Doctor → **Medications** tab → Prescribe **Dapagliflozin 10 mg at 08:00** → **Prescribe**.

> "She prescribes dapagliflozin. The reminder appears in Ramesh's app straight away, and the twin
> re-runs: **62 to 35%**, close to what the simulation predicted."

Patient → **दवाइयाँ**: Dapagliflozin 08:00 appears.

## 14:00 - 15:30  Safety: hypo predicted before it happens (Doctor Live tab)

Doctor → **Live** → **📉 Hypo**. Wait ~30 seconds.

> "Watch the alerts: *Low glucose likely within 30 minutes* fires while he is still above 120, before he
> actually drops to 64 and then 52. That warning is the twin's forecast plus a rule-based safety net."

Patient → **अपने ट्विन से पूछें** (Ask my twin): ask **क्या मैं मेटफॉर्मिन बंद कर दूँ?**

> "The AI assistant explains, it never prescribes. Ask it to stop a medicine and it says: please discuss
> this with your doctor. With low sugar it gives a fixed 15-15 first-aid message, never an AI answer."

## 15:30 - 17:00  Reports (Doctor Report tab + Patient Report tab)

Doctor → **Report** → **Prepare clinical report** → **Download**. Open the PDF: risk, KDIGO grid, labs
with stale-data flags, trends, 14-day glucose profile, ranked options with sources, AI summary.

Patient → **रिपोर्ट** → **मेरी रिपोर्ट बनाएँ**: one page, English and Hindi side by side, green and red
dots against targets, medicines, tips, when to call the doctor.

## 17:00 - 18:00  Honest close

> "What is real: the eGFR, KDIGO and CGM maths, FHIR in and out, a kidney model validated on 1,455 real
> NHANES patients (AUROC 0.72) and checked on Indian hospital data from Apollo (94% agreement with the
> diagnosis). What is simulated: the long-term models learn from a transparent synthetic Indian cohort,
> because no open Indian longitudinal dataset exists yet; that is our next step with hospital partners.
> GlycoRenal Twin is decision support only; the doctor decides. Thank you."

---

## If something goes wrong

| Problem | Fix |
|---|---|
| Page blank or "Cannot reach the API" | Check the API window is still running; restart it |
| Live tab not moving | Live tab → ▶ Start sensor (or Devices tab on the patient side) |
| Alerts missing in the hypo step | Same alert type is merged for 60 min: run **Start demo mode** again before recording |
| AI says "offline summary" | Fine: templates are the designed fallback (no internet / no key) |
| Slow screens | Normal on this laptop (emulation); click once and wait; read-only data is cached 15 s |

Rehearse with `.\.venv\Scripts\python.exe scripts/dry_run_demo.py` (34 s, prints every step).
