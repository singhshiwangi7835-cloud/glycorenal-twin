# GlycoRenal Twin: FAST TRACK (build by Friday 16 Oct night)

Use this file **instead of** the 15 prompts in `BUILD_PROMPTS.md`. Same product, 7 bigger prompts.
`CLAUDE.md` stays the spec. Step 0 setup from `BUILD_PROMPTS.md` still applies.

## Rules for speed

1. **Let Claude Code run without stopping.** Switch Claude Code's permission mode to auto-accept edits, so it doesn't stop to ask before every file. Start each prompt and come back when it's done.
2. **Work in parallel.** While Claude Code builds, you do your 🧑‍⚕️ checks and your teammate does Docker/deploy.
3. **Time-box each prompt.** If a prompt runs past its slot, type: *"We're out of time on this step. Finish the minimum that works, leave TODOs, commit, and move on."*
4. **Never fix the same error more than twice.** If it fails twice, type: *"Replace this with the simplest working version or a stub, and note it in README limitations."*
5. **Push to GitHub after every prompt** (`git push`), so nothing is lost.

## What's cut for now (slide / "next steps" only)

- Dexcom live OAuth: show a "Connect Dexcom (coming soon)" button. Libre upload + simulator cover live data.
- Synthea via Java: use ready-made sample FHIR bundles instead.
- Separate admin polish: a minimal admin page only.
- Deployment and CI: your teammate does these on Saturday from Prompt 7.

## Schedule

| When | Prompt | You do meanwhile |
|---|---|---|
| Thu 6–8 PM | Step 0 + **FT1** Foundation | Fill `.env` with Kimi key/URL/model |
| Thu 8 PM–midnight | **FT2** Data + models (start downloads before sleeping) | Verify `clinical_rules.yaml` + `indian_foods.csv` 🧑‍⚕️ |
| Fri 9 AM–12 PM | **FT3** Twin engine + treatments + alerts + EHR | Verify eligibility test cases 🧑‍⚕️ |
| Fri 12–3 PM | **FT4** Live data + reminders + meals | Prepare demo patient story |
| Fri 3–7 PM | **FT5** AI assistant + all screens | Verify guideline notes 🧑‍⚕️ |
| Fri 7–10 PM | **FT6** PDFs + demo mode + full dry run | Click through as every role |
| Fri 10 PM+ | **FT7** Tests + README + Docker (teammate can take over) | Start deck outline |

---

## FT1: Foundation (Prompts 1 + 2)

```
Read CLAUDE.md fully. We are on FAST TRACK: the full prototype must work by Friday night. Work through
everything below without stopping to ask, except when you need something only I can provide
(keys, accounts, manual downloads). Keep code simple.

1. Skeleton exactly per CLAUDE.md section 4: folders, pinned requirements.txt, .gitignore, .env.example
   (section 13), config/settings.py (pydantic-settings), a .venv with requirements installed.
2. SQLModel tables (section 5), auth with bcrypt + JWT and roles, api/main.py with /health + auth router.
3. Streamlit app/Home.py login that routes by role to placeholder pages, plus a "Demo accounts" expander.
4. scripts/seed_demo.py with the demo users (section 11); the DB seeds itself if empty on API startup.
5. src/clinical: egfr.py (CKD-EPI 2021 race-free), kdigo.py, cgm_metrics.py, units.py, with unit tests.
6. config/clinical_rules.yaml (targets, KDIGO, eligibility, effect sizes, each with source + verified:false),
   config/alerts.yaml, data/reference/loinc_map.csv, data/reference/indian_foods.csv (~50 Indian foods).
Then: help me copy .env.example to .env and tell me which lines to fill (I type my Kimi key, base URL and
model name myself, never in chat). Generate JWT_SECRET for me. Give me the two commands to start API and UI
and what I should see. Run tests. Commit and push.
```

✅ Log in as `dr.mehta / doctor123` and `ramesh / patient123`.

## FT2: Data and models (Prompts 3 + 4)

```
FAST TRACK, work without stopping. Per CLAUDE.md section 7:
1. scripts/download_data.py for NHANES 2017-Mar 2020 (DEMO, DIQ, GHB, GLU, BIOPRO, ALB_CR, BPXO or BPX, BMX,
   SMQ), UCI CKD and CGMacros. Print clear manual instructions if a download fails. Start the downloads
   now and tell me how long they'll take.
2. NHANES pipeline: adults with diabetes, eGFR via our egfr.py, DKD label -> data/processed.
3. scripts/build_synthetic_cohort.py: 2000 Indian T2DM patients, quarterly visits for 4 years, seeded,
   baseline values from a `cohort` section in clinical_rules.yaml (ICMR-INDIAB-informed, verified:false).
   Also generate synthetic 5-min CGM traces for demo patients so the simulator works EVEN IF CGMacros
   is not downloaded yet.
4. scripts/train_models.py: dkd_current (NHANES), dkd_onset + dkd_progression (synthetic, sanity check on
   UCI CKD), hba1c_forecast (synthetic), glucose_forecast (+30/+60 min; CGMacros if present, else the
   synthetic CGM). Keep training under 10 minutes total on a laptop. Save models + models/model_card.md
   with honest limitations + plots in docs/.
5. src/models/t2dm.py and dkd.py predict functions.
Explain results to me as a pharmacist: what's good, what's weak, what to tell judges. Commit and push.
```

## FT3: Twin engine, treatments, alerts, EHR (Prompts 5 + 6)

```
FAST TRACK, work without stopping. Per CLAUDE.md sections 6, 8, 9:
1. src/twin/state.py TwinState builder.
2. src/treatment eligibility/simulate/rank using clinical_rules.yaml, with source citations; unit tests
   (e.g. eGFR 25 -> metformin not eligible, SGLT2i eligible; finerenone needs UACR>=30, K<=5.0, eGFR>=25).
3. src/alerts with de-duplication.
4. src/ingestion/translator.py with the living-twin loop (DKD re-run only on new lab/med change/daily job).
5. fhir_import.py: import ready-made Synthea sample FHIR R4 bundles (download public samples into
   data/fhir_samples, no Java) AND fetch by patient id from FHIR_BASE_URL (HAPI R4); map Patient,
   Condition, Observation via loinc_map.csv, MedicationRequest -> Medication; export GET /patients/{id}/fhir.
   Manual lab entry + lab CSV upload.
6. API routers: patients, twin, treatments, alerts, ehr, with role checks (patients see only their own data).
7. seed_demo.py: ~10 patients with 6 months of labs/meds and 14 days of CGM, incl. "Ramesh" (54 M, T2DM 9 yrs,
   HbA1c 8.4, eGFR ~63, UACR 85, metformin + telmisartan, poor adherence).
Give me 3 lines explaining FHIR for the video. Run tests. Commit and push.
```

## FT4: Live data, reminders, meals (Prompts 7 + 8)

```
FAST TRACK, work without stopping. Per CLAUDE.md sections 8 and 9:
1. simulator.py: replay CGM + heart rate + steps for a patient time-shifted to now (CGMacros if available,
   else the synthetic traces), start/stop per patient, inject "meal spike" and "hypo" scenarios.
2. libre_csv.py with a sample LibreView file in data/fhir_samples/sample_libre.csv.
3. dexcom.py: stub only (interface + "coming soon"); no OAuth now.
4. Manual vitals endpoint (BP, weight, fingerstick glucose, sleep) + stale-data alert.
5. Reminders: DoseEvents from Medication times, taken/skipped/missed, adherence 7d/30d into TwinState;
   doctor prescribing updates reminders.
6. Meals from indian_foods.csv, auto carbs, 2-h spike from CGM, top spiking foods.
7. API routers devices, reminders, meals. Seed taken/missed doses and meals for Ramesh.
Tests for adherence and spike. Commit and push.
```

## FT5: AI assistant and all screens (Prompts 9 + 10)

```
FAST TRACK, work without stopping. Per CLAUDE.md sections 10 and 11:
1. src/llm: OpenAI-compatible client (primary = my Kimi from LLM_* env, optional backup LLM_FALLBACK_*,
   then template fallback), 20 s timeout, LLMCache, prompts for 6 modes in English/Hindi, guardrails
   (patient mode: no medicine/dose changes; fixed hypo safety message), TF-IDF RAG over 6-8 short notes in
   data/guidelines (marked verify, with sources), fallback.py templates, scripts/test_llm.py, llm router.
2. Full Streamlit UI through app/api_client.py: doctor portal (all tabs), patient app (all tabs, Hindi/English
   toggle with all strings in one translations file), minimal admin page. Live tabs auto-refresh every 5 s
   with st.fragment(run_every=5); toasts for new alerts and due medicines. Clean clinical design, KDIGO colours
   for risk only, disclaimer footer on every page.
Then tell me to run scripts/test_llm.py, and give me a click-through checklist per role. Commit and push.
```

## FT6: PDFs, demo mode, dry run (Prompts 11 + 12)

```
FAST TRACK, work without stopping. Per CLAUDE.md section 12:
1. Doctor PDF + one-page bilingual patient PDF (fpdf2, text shaping on, Noto Sans + Noto Sans Devanagari in
   assets/fonts with licence). Download buttons in both portals. Samples in docs/samples/.
2. Admin "Demo mode" button: resets data and sets up the story in one click.
3. docs/demo_script.md: a 15-18 min narration script for me (admin imports EHR patient -> live CGM -> patient
   logs rice meal -> spike + alert -> missed dose -> doctor sees risk rise -> ranked treatments -> add SGLT2i ->
   risk drops -> both PDFs), with what to click and what to say.
4. Dry-run the whole story yourself through the API, fix every error you find, then list anything still rough.
Commit and push.
```

## FT7: Tests, README, Docker (teammate can run this)

```
Make it submission-ready per CLAUDE.md sections 13-14: all tests pass, Dockerfile + docker-compose (API + UI,
self-seeding), .github/workflows/ci.yml running pytest, secret scan (.env not tracked), README.md and
docs/architecture.md (mermaid + simple version + model card summary + limitations/next steps: Dexcom live
OAuth, real-world validation, CDSCO SaMD, DPDP-compliant hosting, WhatsApp reminders). Export the
architecture diagram to docs/ as PNG/SVG. Recommend the simplest free deploy (Render or Hugging Face Spaces)
and list exactly where to enter env variables. Commit and push.
```

---

**If you're behind on Friday evening:** FT1–FT5 give you a working, demoable prototype. FT6 makes the video easy. FT7 can slip to Saturday morning, since your deadline is Tuesday.
