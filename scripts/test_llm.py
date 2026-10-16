"""Check the LLM connection: sends "Say OK" to each configured provider and prints who answered.

Usage:  .\.venv\Scripts\python.exe scripts/test_llm.py
Reads LLM_* (primary, Kimi) and LLM_FALLBACK_* (backup, Gemini) from .env. Keys are never printed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openai import OpenAI  # noqa: E402

from src.llm.client import TIMEOUT_S, providers  # noqa: E402

found = providers()
if not found:
    print("No LLM configured. Open .env and fill LLM_BASE_URL, LLM_API_KEY and LLM_MODEL "
          "(from your Kimi dashboard). Until then the twin uses built-in templates.")
    sys.exit(1)
ok = False
for name, base_url, key, model in found:
    print(f"[{name}] {model} at {base_url} ...", end=" ", flush=True)
    try:
        r = OpenAI(base_url=base_url, api_key=key, timeout=TIMEOUT_S, max_retries=0).chat.completions.create(
            model=model, max_tokens=10, messages=[{"role": "user", "content": "Say OK"}])
        print(f"answered: {r.choices[0].message.content.strip()!r}")
        ok = True
    except Exception as e:  # noqa: BLE001
        print(f"FAILED: {e.__class__.__name__}: {str(e)[:200]}")
sys.exit(0 if ok else 1)
