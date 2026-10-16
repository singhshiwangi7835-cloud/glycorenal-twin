"""LLM client: any OpenAI-compatible endpoint (CLAUDE.md section 10).

Order: primary (Kimi / Moonshot, LLM_* in .env) -> backup (Gemini, LLM_FALLBACK_*) -> None
(the caller then uses the template fallback). Base URLs and model names come only from .env.
20-second timeout, no automatic retries (a slow answer falls back instead of hanging the UI).
"""

from __future__ import annotations

import logging

from openai import OpenAI

from config.settings import get_settings

log = logging.getLogger("glycorenal.llm")
TIMEOUT_S = 20


def providers() -> list[tuple[str, str, str, str]]:
    """(name, base_url, api_key, model) for every provider that is fully configured."""
    s = get_settings()
    out = []
    if s.llm_base_url and s.llm_api_key and s.llm_model:
        out.append(("primary", s.llm_base_url, s.llm_api_key, s.llm_model))
    if s.llm_fallback_base_url and s.llm_fallback_api_key and s.llm_fallback_model:
        out.append(("backup", s.llm_fallback_base_url, s.llm_fallback_api_key, s.llm_fallback_model))
    return out


def complete(system: str, user: str, max_tokens: int = 700) -> tuple[str | None, str | None]:
    """Returns (text, provider description) or (None, None) if every provider failed."""
    for name, base_url, key, model in providers():
        try:
            client = OpenAI(base_url=base_url, api_key=key, timeout=TIMEOUT_S, max_retries=0)
            r = client.chat.completions.create(
                model=model, max_tokens=max_tokens, temperature=0.2,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
            text = (r.choices[0].message.content or "").strip()
            if text:
                return text, f"{name} ({model})"
        except Exception as e:  # noqa: BLE001  (rate limit, timeout, bad key: try the next one)
            log.warning("LLM %s failed: %s", name, e.__class__.__name__)
    return None, None
