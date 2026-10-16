"""Shared PDF pieces (fpdf2): fonts, header/footer, tables, KDIGO grid, charts (matplotlib PNG).

Fonts: Noto Sans + Noto Sans Devanagari (assets/fonts, SIL Open Font License), with text shaping
on so Hindi conjuncts render correctly. Noto Sans has no arrows or tick marks, so clean()
replaces them with plain text and ticks are drawn as coloured dots.
"""

from __future__ import annotations

import io
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from fpdf import FPDF  # noqa: E402
from fpdf.enums import XPos, YPos  # noqa: E402

from config.settings import get_settings  # noqa: E402

FONTS = Path(__file__).resolve().parents[2] / "assets" / "fonts"
ACCENT = (11, 110, 153)
GREY = (82, 96, 109)
INK = (31, 41, 51)
GREEN, RED = (46, 125, 50), (198, 40, 40)
BAND_RGB = {"low": (46, 125, 50), "moderate": (249, 168, 37), "high": (239, 108, 0), "very_high": (198, 40, 40)}
GRID = {"G1": ["low", "moderate", "high"], "G2": ["low", "moderate", "high"],
        "G3a": ["moderate", "high", "very_high"], "G3b": ["high", "very_high", "very_high"],
        "G4": ["very_high"] * 3, "G5": ["very_high"] * 3}
DISCLAIMER = ("Prototype - decision support only, not for clinical use. Not a medical device. "
              "The treating clinician decides all treatment.")
_REPLACE = {"→": "to", "≥": ">=", "≤": "<=", "✓": "", "✗": "", "●": "*", "⚠️": "!", "⚠": "!",
            "🔺": "+", "🔻": "-", "🟠": "", "🟢": "", "**": ""}


def clean(text) -> str:
    s = "" if text is None else str(text)
    for k, v in _REPLACE.items():
        s = s.replace(k, v)
    return re.sub(r"(?<![A-Za-z0-9])_|_(?![A-Za-z0-9])", "", s)  # drop markdown _italics_, keep dkd_onset


def local_now() -> datetime:
    return datetime.now(ZoneInfo(get_settings().timezone))


class ReportPDF(FPDF):
    def __init__(self, title: str, subtitle: str = ""):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.title_text, self.subtitle = title, subtitle
        self.add_font("Noto", "", str(FONTS / "NotoSans-Regular.ttf"))
        self.add_font("Noto", "B", str(FONTS / "NotoSans-Bold.ttf"))
        self.add_font("Deva", "", str(FONTS / "NotoSansDevanagari-Regular.ttf"))
        self.add_font("Deva", "B", str(FONTS / "NotoSansDevanagari-Bold.ttf"))
        self.set_text_shaping(True)
        self.set_fallback_fonts(["Deva"])
        self.set_auto_page_break(True, margin=18)
        self.set_margins(14, 14, 14)

    def header(self):
        self.set_font("Noto", "B", 13)
        self.set_text_color(*ACCENT)
        self.cell(90, 7, "GlycoRenal Twin", new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.set_font("Noto", "", 8)
        self.set_text_color(*GREY)
        self.cell(0, 7, clean(f"{self.title_text}   {local_now():%d %b %Y %H:%M}"), align="R",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if self.subtitle:
            self.set_font("Noto", "", 9)
            self.cell(0, 5, clean(self.subtitle), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*ACCENT)
        self.set_line_width(0.5)
        self.line(14, self.get_y() + 1, 196, self.get_y() + 1)
        self.set_line_width(0.2)
        self.ln(4)
        self.set_text_color(*INK)

    def footer(self):
        self.set_y(-14)
        self.set_font("Noto", "", 7)
        self.set_text_color(*GREY)
        self.multi_cell(0, 3.5, f"{DISCLAIMER}   Page {self.page_no()}", align="C",
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def h2(self, text: str, size: float = 11):
        self.ln(2)
        self.set_font("Noto", "B", size)
        self.set_text_color(*ACCENT)
        self.multi_cell(0, 6, clean(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*INK)

    def para(self, text: str, size: float = 9, h: float = 4.6, w: float = 0, bold: bool = False):
        self.set_font("Noto", "B" if bold else "", size)
        self.multi_cell(w, h, clean(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def table(self, header: list[str], rows: list[list], widths: list[float], size: float = 8,
              status_colours: list[tuple | None] | None = None):
        self.set_font("Noto", "B", size)
        self.set_fill_color(243, 246, 248)
        for h, w in zip(header, widths):
            self.cell(w, 6, clean(h), border="B", fill=True)
        self.ln()
        self.set_font("Noto", "", size)
        for i, r in enumerate(rows):
            if self.get_y() > 268:
                self.add_page()
            colour = status_colours[i] if status_colours else None
            for j, (v, w) in enumerate(zip(r, widths)):
                if colour and j == len(r) - 1:
                    self.set_text_color(*colour)
                self.cell(w, 5.5, clean(v)[:90], border="B")
                self.set_text_color(*INK)
            self.ln()

    def dot(self, x: float, y: float, ok: bool | None):
        self.set_fill_color(*((158, 158, 158) if ok is None else (GREEN if ok else RED)))
        self.ellipse(x, y, 3, 3, style="F")

    def kdigo_grid(self, x: float, y: float, g: str | None, a: str | None, cw: float = 11, ch: float = 5):
        self.set_font("Noto", "B", 7)
        self.set_text_color(*INK)
        for j, a_s in enumerate(["A1", "A2", "A3"]):
            self.set_xy(x + 9 + j * cw, y)
            self.cell(cw, 4, a_s, align="C")
        for i, gs in enumerate(GRID):
            yy = y + 4 + i * ch
            self.set_xy(x, yy)
            self.cell(9, ch, gs, align="R")
            for j, a_s in enumerate(["A1", "A2", "A3"]):
                self.set_fill_color(*BAND_RGB[GRID[gs][j]])
                self.set_draw_color(255, 255, 255)
                self.rect(x + 9 + j * cw, yy, cw, ch, style="DF")
                if gs == g and a_s == a:
                    self.set_draw_color(*INK)
                    self.set_line_width(0.9)
                    self.rect(x + 9 + j * cw, yy, cw, ch, style="D")
                    self.set_line_width(0.2)
        self.set_xy(x, y + 4 + 6 * ch + 1)
        self.set_font("Noto", "", 6)
        self.cell(45, 3, "rows eGFR, columns UACR (KDIGO)", align="C")

    def image_png(self, png: bytes, x: float | None = None, w: float = 90):
        self.image(io.BytesIO(png), x=x, w=w)


def _png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def chart_png(points: list[dict], title: str, unit: str, target: float | None = None,
              size=(4.2, 2.2)) -> bytes:
    fig, ax = plt.subplots(figsize=size, dpi=150)
    if points:
        df = pd.DataFrame(points)
        df["time"] = pd.to_datetime(df["time"], format="ISO8601", utc=True)
        ax.plot(df["time"], df["value"], marker="o", color="#0b6e99", lw=1.6, ms=3)
    if target is not None:
        ax.axhline(target, color="#2e7d32", ls="--", lw=0.8)
    ax.set_title(title, fontsize=9)
    ax.set_ylabel(unit, fontsize=7)
    ax.tick_params(labelsize=6)
    ax.grid(alpha=0.25)
    fig.autofmt_xdate()
    fig.tight_layout()
    return _png(fig)


def agp_png(rows: list[dict], size=(7.6, 2.4)) -> bytes:
    """AGP-style daily profile: median and 25-75 / 5-95 percentile bands by time of day."""
    fig, ax = plt.subplots(figsize=size, dpi=150)
    if rows:
        df = pd.DataFrame(rows)
        t = pd.to_datetime(df["time"], format="ISO8601", utc=True).dt.tz_convert(get_settings().timezone)
        df["hour"] = t.dt.hour + (t.dt.minute // 30) * 0.5
        q = df.groupby("hour")["value"].quantile([0.05, 0.25, 0.5, 0.75, 0.95]).unstack()
        ax.fill_between(q.index, q[0.05], q[0.95], color="#0b6e99", alpha=0.12, label="5-95%")
        ax.fill_between(q.index, q[0.25], q[0.75], color="#0b6e99", alpha=0.3, label="25-75%")
        ax.plot(q.index, q[0.5], color="#0b6e99", lw=1.8, label="median")
    ax.axhspan(70, 180, color="#2e7d32", alpha=0.07)
    ax.axhline(70, color="#c62828", lw=0.7, ls="--")
    ax.axhline(180, color="#ef6c00", lw=0.7, ls="--")
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 3))
    ax.set_xlabel("hour of day", fontsize=7)
    ax.set_ylabel("mg/dL", fontsize=7)
    ax.set_title("Ambulatory glucose profile (14 days)", fontsize=9)
    ax.tick_params(labelsize=6)
    ax.legend(fontsize=6, loc="upper right")
    fig.tight_layout()
    return _png(fig)
