"""Draw the architecture diagram -> docs/architecture.png and docs/architecture.svg (matplotlib).

Usage:  .\\.venv\\Scripts\\python.exe scripts/make_architecture_diagram.py
The same picture is in docs/architecture.md as a Mermaid diagram.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

DOCS = Path(__file__).resolve().parents[1] / "docs"
ACCENT, INK, GREY = "#0b6e99", "#1f2933", "#52606d"
FILL = {"src": "#eef6fa", "api": "#f3f6f8", "brain": "#e8f5e9", "out": "#fff4e5", "ui": "#f1eefa"}


def box(ax, x, y, w, h, title, lines=(), kind="api", fs=9):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
                                fc=FILL[kind], ec=ACCENT if kind != "brain" else "#2e7d32", lw=1.3))
    ax.text(x + w / 2, y + h - 0.22, title, ha="center", va="top", fontsize=fs, weight="bold", color=INK)
    for i, ln in enumerate(lines):
        ax.text(x + w / 2, y + h - 0.55 - i * 0.27, ln, ha="center", va="top", fontsize=fs - 2, color=GREY)


def arrow(ax, x1, y1, x2, y2, both=False):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="<|-|>" if both else "-|>",
                                 mutation_scale=12, color=ACCENT, lw=1.2))


def main():
    fig, ax = plt.subplots(figsize=(16, 9))
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 9)
    ax.axis("off")
    ax.text(8, 8.75, "GlycoRenal Twin: architecture", ha="center", fontsize=15, weight="bold", color=ACCENT)
    ax.text(8, 8.4, "Digital twin for type 2 diabetes and diabetic kidney disease. Decision support only.",
            ha="center", fontsize=9, color=GREY)

    # data sources (left column)
    ax.text(1.55, 7.95, "DATA SOURCES", ha="center", fontsize=8, weight="bold", color=GREY)
    sources = [("Hospital EHR", ["FHIR R4: HAPI, Synthea;", "labs, meds, genetics"]),
               ("Lab results", ["manual entry, lab CSV"]),
               ("Wearables", ["CGM, heart rate, steps,", "Libre CSV, Dexcom (soon)"]),
               ("Patient app", ["meals, doses taken,", "BP, weight, sleep"])]
    for i, (t, ln) in enumerate(sources):
        box(ax, 0.2, 6.55 - i * 1.6, 2.7, 1.3, t, ln, "src")
        arrow(ax, 2.9, 7.2 - i * 1.6, 3.6, 5.0)

    # backend: ingestion -> db -> state
    ax.add_patch(FancyBboxPatch((3.4, 0.6), 9.0, 7.5, boxstyle="round,pad=0.02,rounding_size=0.2",
                                fc="none", ec=GREY, ls="--", lw=1))
    ax.text(7.9, 7.9, "FASTAPI BACKEND (auth + roles: doctor, patient, admin)", ha="center", fontsize=8,
            weight="bold", color=GREY)
    box(ax, 3.6, 4.3, 2.6, 1.7, "Translator", ["LOINC map, units,", "de-duplicate,", "living-twin loop"])
    box(ax, 3.6, 2.3, 2.6, 1.4, "SQLite database", ["Observation, Medication,", "Meal, Alert, Prediction"])
    box(ax, 6.6, 4.3, 2.4, 1.7, "Twin state", ["eGFR CKD-EPI 2021, KDIGO,", "CGM metrics, adherence,", "genetics, personal twin"])
    arrow(ax, 4.9, 4.3, 4.9, 3.7)
    arrow(ax, 6.2, 3.0, 7.0, 4.3)

    # twin engine
    ax.add_patch(FancyBboxPatch((9.3, 1.0), 2.95, 6.6, boxstyle="round,pad=0.02,rounding_size=0.15",
                                fc="#f6fbf6", ec="#2e7d32", lw=1.2))
    ax.text(10.78, 7.45, "TWIN ENGINE", ha="center", fontsize=8, weight="bold", color="#2e7d32")
    eng = [("T2DM predictor", ["glucose +30/+60 min,", "spike 90 min ahead,", "HbA1c in 3 months"]),
           ("DKD predictor", ["onset / progression,", "3-year risk + drivers"]),
           ("Treatment advisor", ["eligibility, simulate,", "rank (trial HRs)"]),
           ("Alerts + reminders", ["hypo / spike predicted,", "UACR, doses, sensor"])]
    for i, (t, ln) in enumerate(eng):
        box(ax, 9.45, 5.95 - i * 1.6, 2.65, 1.3, t, ln, "brain")
    arrow(ax, 9.0, 5.15, 9.45, 5.15)
    arrow(ax, 10.78, 5.95, 10.78, 5.65)   # T2DM -> DKD (glycaemic features feed DKD)
    arrow(ax, 10.78, 4.35, 10.78, 4.05, both=True)  # DKD <-> advisor

    # outputs
    box(ax, 12.6, 5.2, 3.2, 1.6, "LLM assistant", ["Kimi -> Gemini -> templates,", "guardrails, RAG,",
                                                  "English + Hindi"], "out")
    box(ax, 12.6, 3.3, 3.2, 1.4, "PDF reports", ["doctor report,", "bilingual patient page"], "out")
    arrow(ax, 12.1, 5.6, 12.6, 6.0)
    arrow(ax, 12.1, 4.0, 12.6, 4.0)

    # UI
    box(ax, 12.6, 0.6, 3.2, 2.2, "Streamlit app", ["Login by role", "Doctor portal", "Patient app (Hindi/English)",
                                                   "Admin panel"], "ui")
    arrow(ax, 12.1, 2.0, 12.6, 1.7, both=True)
    ax.text(8, 0.2, "Every reading: save -> instant alerts -> CGM metrics -> short-term forecast.   "
                    "DKD risk re-runs on new labs, medicine changes, or daily.", ha="center", fontsize=8, color=GREY)
    fig.tight_layout()
    DOCS.mkdir(exist_ok=True)
    fig.savefig(DOCS / "architecture.png", dpi=140)
    fig.savefig(DOCS / "architecture.svg")
    print("Saved docs/architecture.png and docs/architecture.svg")


if __name__ == "__main__":
    main()
