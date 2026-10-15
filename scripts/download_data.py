"""Download the public datasets into data/raw/ (not pushed to GitHub).

Usage:  python scripts/download_data.py            # everything open-access
        python scripts/download_data.py nhanes     # just one

AI-READI needs an access request at https://fairhub.io/datasets/2 (download manually).
If a URL has moved, open the dataset page listed below and update it here.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import requests

RAW = Path("data/raw")

NHANES_BASE = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles"
NHANES_FILES = ["P_DEMO", "P_DIQ", "P_GHB", "P_BIOPRO", "P_ALB_CR", "P_BPXO", "P_BMX", "P_RXQ_RX"]

SOURCES = {
    # page: https://wwwn.cdc.gov/nchs/nhanes/continuousnhanes/default.aspx?Cycle=2017-2020
    "nhanes": [(f"{NHANES_BASE}/{f}.xpt", RAW / "nhanes" / f"{f}.xpt") for f in NHANES_FILES],
    # page: https://archive.ics.uci.edu/dataset/336/chronic+kidney+disease
    "uci_ckd": [("https://archive.ics.uci.edu/static/public/336/chronic+kidney+disease.zip",
                 RAW / "uci_ckd" / "uci_ckd.zip")],
    # page: https://physionet.org/content/cgmacros/1.0.0/
    "cgmacros": [("https://physionet.org/static/published-projects/cgmacros/cgmacros-1.0.0.zip",
                  RAW / "cgmacros" / "cgmacros.zip")],
}


def fetch(url: str, dest: Path) -> None:
    if dest.exists():
        print(f"  already have {dest}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  downloading {url}")
    with requests.get(url, stream=True, timeout=120,
                      headers={"User-Agent": "glycorenal-twin/0.1"}) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    if dest.suffix == ".zip":
        with zipfile.ZipFile(dest) as z:
            z.extractall(dest.parent)
        print(f"  extracted to {dest.parent}")


def main(names: list[str]) -> None:
    for name in names or SOURCES:
        print(f"[{name}]")
        for url, dest in SOURCES[name]:
            try:
                fetch(url, dest)
            except Exception as e:
                print(f"  FAILED: {e}. Check the dataset page and update the URL.")


if __name__ == "__main__":
    main(sys.argv[1:])
