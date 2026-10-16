"""One-page patient report, English and Hindi side by side (CLAUDE.md section 12).

Contents: today's numbers vs targets (green dot = on target, red = not), medicines and times,
top 3 lifestyle tips (report_patient mode in each language; templates when offline), when to
call the doctor, disclaimer. No medicine advice and no drug options.
"""

from __future__ import annotations

from fpdf.enums import XPos, YPos
from sqlmodel import Session

from src.db.models import Patient
from src.llm.assistant import ask
from src.llm.guardrails import FOOTER
from src.reports.common import INK, ReportPDF, clean
from src.twin.state import build_state

CALL_DOCTOR = {
    "en": ["Sugar below 70 mg/dL more than once in a week, or any time below 54",
           "Sugar above 300 mg/dL, or above 250 with vomiting or drowsiness",
           "Swelling of feet or face, much less urine, or breathlessness",
           "BP above 160/100 on two readings",
           "Before stopping or changing any medicine"],
    "hi": ["हफ़्ते में एक से ज़्यादा बार शुगर 70 mg/dL से कम हो, या कभी भी 54 से कम हो",
           "शुगर 300 mg/dL से ज़्यादा हो, या 250 से ज़्यादा हो और उल्टी या सुस्ती हो",
           "पैरों या चेहरे पर सूजन, पेशाब बहुत कम होना, या साँस फूलना",
           "दो बार BP 160/100 से ज़्यादा आए",
           "कोई भी दवा बंद करने या बदलने से पहले"],
}
HEAD = {"title": ("My health summary", "मेरी सेहत का सारांश"),
        "numbers": ("My numbers today", "आज मेरे आँकड़े"),
        "meds": ("My medicines", "मेरी दवाइयाँ"),
        "tips": ("What I can do", "मैं क्या कर सकता/सकती हूँ"),
        "call": ("Call your doctor if", "डॉक्टर को फ़ोन करें अगर")}


def _tips(text: str) -> list[str]:
    lines = [ln.strip("- ").strip() for ln in text.splitlines()]
    tips = [ln for ln in lines if ln and not ln.startswith(("_", "What you can do", "आप ये कर सकते हैं"))
            and "Decision support" not in ln and "निर्णय-सहायता" not in ln]
    return tips[:4]


def build(session: Session, patient_id: str) -> bytes:
    p = session.get(Patient, patient_id)
    s = build_state(session, patient_id)
    k, g, v = s["kidney"], s["glycaemia"], s["vitals"]
    m = s["cgm"].get("metrics") or {}
    adh = s["adherence"]["pct_7d"]
    tips = {lang: _tips(ask(session, patient_id, "report_patient", lang)["text"]) for lang in ("en", "hi")}

    pdf = ReportPDF("Patient report / मरीज़ रिपोर्ट", f"{p.display_name}  |  {p.id}")
    pdf.add_page()
    pdf.set_font("Noto", "B", 15)
    pdf.cell(0, 8, clean(f"{HEAD['title'][0]}  /  {HEAD['title'][1]}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ---- numbers vs targets ----
    pdf.h2(f"{HEAD['numbers'][0]} / {HEAD['numbers'][1]}")
    bp_t = s["bp"]["target"]
    rows = [
        ("HbA1c (3-month sugar)", "HbA1c (3 महीने की शुगर)", f"{g['hba1c']}%", f"< {g['target']}%", g["on_target"]),
        ("Time in healthy range", "सही दायरे में समय", f"{m['tir_pct']:.0f}%" if m else "n/a", "> 70%",
         m["tir_pct"] > 70 if m else None),
        ("Blood pressure", "ब्लड प्रेशर", f"{v['sbp']:.0f}/{v['dbp']:.0f}" if v["sbp"] else "n/a", f"< {bp_t}",
         s["bp"]["on_target"]),
        ("Kidney filter (eGFR)", "किडनी फ़िल्टर (eGFR)", f"{k['egfr']:.0f}" if k.get("egfr") else "n/a", "> 60",
         k["egfr"] >= 60 if k.get("egfr") else None),
        ("Urine protein (UACR)", "पेशाब में प्रोटीन (UACR)", f"{k['uacr']:.0f} mg/g" if k.get("uacr") is not None else "n/a",
         "< 30", k["uacr"] < 30 if k.get("uacr") is not None else None),
        ("Medicines taken (7 days)", "ली गई दवाइयाँ (7 दिन)", f"{adh:.0f}%" if adh is not None else "n/a", "> 80%",
         adh >= 80 if adh is not None else None),
    ]
    pdf.set_font("Noto", "B", 8)
    for label, w in [("Measure / माप", 100), ("Mine / मेरा", 30), ("Target / लक्ष्य", 30), ("", 12)]:
        pdf.cell(w, 6, label, border="B")
    pdf.ln()
    pdf.set_font("Noto", "", 9)
    for en, hi, mine, target, ok in rows:
        y = pdf.get_y()
        pdf.cell(100, 7, clean(f"{en}  /  {hi}"), border="B")
        pdf.cell(30, 7, clean(mine), border="B")
        pdf.cell(30, 7, clean(target), border="B")
        pdf.cell(12, 7, "", border="B")
        pdf.dot(178, y + 2, ok)
        pdf.ln()
    pdf.set_font("Noto", "", 7)
    pdf.cell(0, 5, "Green dot = on target / हरा = लक्ष्य पर.   Red dot = needs work / लाल = सुधार चाहिए.",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ---- two columns: English | Hindi ----
    def two_columns(title: tuple[str, str], en_lines: list[str], hi_lines: list[str], bullet: str = "-"):
        pdf.h2(f"{title[0]} / {title[1]}", size=10)
        y = pdf.get_y()
        pdf.set_font("Noto", "", 8.5)
        for x, lines in ((14, en_lines), (108, hi_lines)):
            pdf.set_xy(x, y)
            for ln in lines:
                pdf.set_x(x)
                pdf.multi_cell(86, 4.6, clean(f"{bullet} {ln}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            if x == 14:
                y_left = pdf.get_y()
        pdf.set_y(max(y_left, pdf.get_y()) + 1)
        pdf.set_text_color(*INK)

    meds = [f"{x['drug']} {x['dose']}: {', '.join(x['times'])}" + (" (with food)" if x["with_food"] else "")
            for x in s["medications"]]
    meds_hi = [f"{x['drug']} {x['dose']}: {', '.join(x['times'])}" + (" (खाने के साथ)" if x["with_food"] else "")
               for x in s["medications"]]
    two_columns(HEAD["meds"], meds or ["None"], meds_hi or ["कोई नहीं"])
    two_columns(HEAD["tips"], tips["en"], tips["hi"])
    two_columns(HEAD["call"], CALL_DOCTOR["en"], CALL_DOCTOR["hi"])

    pdf.ln(2)
    pdf.set_font("Noto", "", 8)
    pdf.multi_cell(0, 4.2, clean(f"{FOOTER['en']}\n{FOOTER['hi']}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    return bytes(pdf.output())
