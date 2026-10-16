"""Download the public datasets into data/raw/ (git-ignored, never pushed).

Usage:  python scripts/download_data.py              # everything
        python scripts/download_data.py cgmacros     # just one: nhanes | uci_ckd | cgmacros

Files that are already present are skipped. If a download fails, the script prints what to
download by hand and where to put it.

| Dataset | Size | Licence / access |
|---|---|---|
| NHANES 2017-Mar 2020 pre-pandemic (CDC) | ~40 MB | public domain |
| UCI Chronic Kidney Disease (Apollo Hospitals) | <1 MB | CC BY 4.0 |
| CGMacros v1.0.0 (PhysioNet) | ~630 MB zip | open access, ODC-BY |
"""

from __future__ import annotations

import sys
import time
import zipfile
from pathlib import Path

import requests

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"

NHANES_BASE = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles"
NHANES_FILES = ["P_DEMO", "P_DIQ", "P_GHB", "P_GLU", "P_BIOPRO", "P_ALB_CR", "P_BPXO", "P_BPQ",
                "P_BMX", "P_SMQ", "P_MCQ", "P_RXQ_RX"]

# name -> list of (url, destination, file that proves it is already there)
SOURCES = {
    "nhanes": [(f"{NHANES_BASE}/{f}.xpt", RAW / "nhanes" / f"{f}.xpt", RAW / "nhanes" / f"{f}.xpt")
               for f in NHANES_FILES],
    "uci_ckd": [("https://archive.ics.uci.edu/static/public/336/chronic+kidney+disease.zip",
                 RAW / "uci_ckd" / "uci_ckd.zip",
                 RAW / "uci_ckd" / "chronic_kidney_disease_full.arff")],
    "cgmacros": [("https://physionet.org/static/published-projects/cgmacros/cgmacros-1.0.0.zip",
                  RAW / "cgmacros" / "cgmacros-1.0.0.zip",
                  RAW / "cgmacros" / "_extracted.ok")],
}

MANUAL = {
    "nhanes": "Open https://wwwn.cdc.gov/nchs/nhanes/continuousnhanes/default.aspx?Cycle=2017-2020, "
              "download the .xpt files listed in NHANES_FILES and put them in data/raw/nhanes/",
    "uci_ckd": "Open https://archive.ics.uci.edu/dataset/336/chronic+kidney+disease, click Download, "
               "unzip into data/raw/uci_ckd/",
    "cgmacros": "Open https://physionet.org/content/cgmacros/1.0.0/, click 'Download the ZIP file', "
                "save it as data/raw/cgmacros/cgmacros-1.0.0.zip, then run this script again to unzip",
}


def fetch(url: str, dest: Path, done_marker: Path) -> None:
    if done_marker.exists():
        print(f"  already have {done_marker.relative_to(RAW)}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        print(f"  downloading {url}")
        part = dest.with_suffix(dest.suffix + ".part")
        start, done = time.time(), 0
        with requests.get(url, stream=True, timeout=120,
                          headers={"User-Agent": "glycorenal-twin/0.2"}) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            with open(part, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
                    done += len(chunk)
                    if total and done % (50 << 20) < (1 << 20):
                        rate = done / max(time.time() - start, 1) / 1e6
                        print(f"    {done / 1e6:.0f} / {total / 1e6:.0f} MB  ({rate:.1f} MB/s)",
                              flush=True)
        part.rename(dest)
    if dest.suffix == ".zip":
        print(f"  unzipping {dest.name}")
        with zipfile.ZipFile(dest) as z:
            z.extractall(dest.parent)
        if done_marker.name == "_extracted.ok":
            done_marker.write_text("ok")
    print(f"  done: {dest.parent.relative_to(RAW)}")


def main(names: list[str]) -> None:
    for name in names or SOURCES:
        print(f"[{name}]", flush=True)
        for url, dest, marker in SOURCES[name]:
            try:
                fetch(url, dest, marker)
            except Exception as e:  # keep going with the other datasets
                print(f"  FAILED: {e}\n  Manual step: {MANUAL[name]}")


if __name__ == "__main__":
    main(sys.argv[1:])
