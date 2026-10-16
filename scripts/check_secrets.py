"""Fail if anything that looks like a secret is tracked by git (run before committing, and in CI).

Checks: .env or *.db files tracked; strings that look like API keys or a filled JWT secret.
Usage:  .\.venv\Scripts\python.exe scripts/check_secrets.py
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "OpenAI/Moonshot-style key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    "filled JWT_SECRET": re.compile(r"^JWT_SECRET=\S{16,}", re.M),
    "filled LLM key": re.compile(r"^LLM_(FALLBACK_)?API_KEY=\S{8,}", re.M),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
SKIP_SUFFIX = {".ttf", ".png", ".pdf", ".joblib", ".zip", ".xpt", ".jpg"}

files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
problems = [f"tracked file should never be committed: {f}" for f in files
            if f == ".env" or f.endswith(".db") or f.endswith(".env")]
for f in files:
    p = ROOT / f
    if p.suffix in SKIP_SUFFIX or not p.is_file() or p.stat().st_size > 2_000_000:
        continue
    text = p.read_text(encoding="utf-8", errors="ignore")
    for name, rx in PATTERNS.items():
        if rx.search(text):
            problems.append(f"{f}: looks like a {name}")
print("\n".join(problems) if problems else f"No secrets found in {len(files)} tracked files.")
sys.exit(1 if problems else 0)
