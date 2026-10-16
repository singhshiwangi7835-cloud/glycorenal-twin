"""Safety rules around the LLM (CLAUDE.md section 10).

1. Patient asks about medicines -> fixed reply "please discuss this with your doctor" (no LLM).
2. Patient has low glucose or a critical alert -> fixed hypoglycaemia safety message (no LLM).
3. Patient-mode answers are checked for medicine-change advice (keyword filter, English + Hindi);
   on a violation the template answer is used instead.
4. Every answer ends with the "Decision support only" footer.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

DRUGS_CSV = Path(__file__).resolve().parents[2] / "data" / "reference" / "drug_classes.csv"

FOOTER = {"en": "Decision support only – not medical advice. Your doctor decides your treatment.",
          "hi": "यह केवल निर्णय-सहायता है, चिकित्सा सलाह नहीं। आपका इलाज आपके डॉक्टर तय करेंगे।"}
FOOTER_DOCTOR = "Decision support only. Suggestions with sources; the treating clinician decides."

ASK_DOCTOR = {"en": "Please discuss this with your doctor. I can explain your readings, but I can't advise "
                    "on starting, stopping or changing any medicine.",
              "hi": "कृपया इस बारे में अपने डॉक्टर से बात करें। मैं आपकी रीडिंग समझा सकता हूँ, लेकिन कोई दवा "
                    "शुरू करने, बंद करने या बदलने की सलाह नहीं दे सकता।"}

HYPO_SAFETY = {
    "en": ("⚠️ Your sugar is low or falling fast.\n1. Take 15 g of fast sugar now: 3 teaspoons of sugar or "
           "glucose in water, or half a glass of fruit juice.\n2. Wait 15 minutes and check again.\n3. If it "
           "is still below 70 mg/dL, repeat. Then eat a snack.\n4. Call your doctor. If you feel confused or "
           "faint, ask someone to call emergency help."),
    "hi": ("⚠️ आपकी शुगर कम है या तेज़ी से गिर रही है।\n1. अभी 15 ग्राम जल्दी असर करने वाली शक्कर लें: 3 चम्मच "
           "चीनी या ग्लूकोज़ पानी में, या आधा गिलास फलों का रस।\n2. 15 मिनट रुकें और दोबारा जाँचें।\n3. अगर अब भी "
           "70 mg/dL से कम है, तो फिर से लें। फिर कुछ नाश्ता करें।\n4. अपने डॉक्टर को फ़ोन करें। चक्कर या बेहोशी लगे "
           "तो किसी से इमरजेंसी मदद बुलवाएँ।"),
}

MED_WORDS_EXTRA = ["medicine", "medication", "tablet", "pill", "dose", "dosage", "insulin", "injection",
                   "दवा", "दवाई", "गोली", "खुराक", "इंसुलिन", "इंजेक्शन"]
ACTION_WORDS = ["start", "stop", "increase", "decrease", "reduce", "double", "halve", "skip", "change",
                "switch", "add", "discontinue", "more of", "less of", "take extra",
                "शुरू", "बंद", "बढ़ा", "घटा", "कम कर", "ज़्यादा ले", "छोड़", "बदल"]
DOCTOR_WORDS = ["doctor", "physician", "डॉक्टर"]


@lru_cache
def _med_words() -> list[str]:
    drugs = pd.read_csv(DRUGS_CSV)["drug"].str.lower().tolist()
    return drugs + MED_WORDS_EXTRA


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?।\n])\s*", text.lower()) if s.strip()]


def mentions_medicine(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in _med_words())


def asks_about_medicine(question: str | None) -> bool:
    """A patient question about taking/changing medicines (answered with the fixed reply)."""
    return bool(question) and mentions_medicine(question)


def violates_patient_rules(answer: str) -> bool:
    """True if a sentence pairs a medicine word with a change word and does not defer to the doctor."""
    for s in _sentences(answer):
        if any(m in s for m in _med_words()) and any(a in s for a in ACTION_WORDS) \
                and not any(d in s for d in DOCTOR_WORDS):
            return True
    return False


def needs_hypo_message(state: dict, alerts: list[dict]) -> bool:
    latest = (state["cgm"].get("latest") or {}).get("value")
    low = latest is not None and latest < 70
    hypo_alert = any(a["type"] in ("glucose_very_low", "glucose_low", "predicted_hypo") for a in alerts)
    return low or hypo_alert or any(a["severity"] == "critical" and "glucose" in a["type"] for a in alerts)


def with_footer(text: str, patient_view: bool, language: str) -> str:
    footer = FOOTER.get(language, FOOTER["en"]) if patient_view else FOOTER_DOCTOR
    return f"{text.rstrip()}\n\n_{footer}_"
