"""LLM client: any OpenAI-compatible endpoint (CLAUDE.md section 10).

Order: primary (Kimi / Moonshot, LLM_* in .env) -> backup (Gemini, LLM_FALLBACK_*) -> None
(the caller then uses the template fallback). Base URLs and model names come only from .env.
Timeout LLM_TIMEOUT_S (default 30 s; reasoning models such as Kimi K2.6 need 10-20 s), no
automatic retries: a slow answer falls back to the template instead of hanging the UI.
max_tokens is generous because reasoning models spend tokens thinking before they answer.
"""

from __future__ import annotations

import logging
import time

from openai import OpenAI

from config.settings import get_settings

log = logging.getLogger("glycorenal.llm")


def timeout_s() -> float:
    return get_settings().llm_timeout_s


def providers() -> list[tuple[str, str, str, str]]:
    """(name, base_url, api_key, model) for every provider that is fully configured."""
    s = get_settings()
    out = []
    if s.llm_base_url and s.llm_api_key and s.llm_model:
        out.append(("primary", s.llm_base_url, s.llm_api_key, s.llm_model))
    if s.llm_fallback_base_url and s.llm_fallback_api_key and s.llm_fallback_model:
        out.append(("backup", s.llm_fallback_base_url, s.llm_fallback_api_key, s.llm_fallback_model))
    return out


DEADLINE_S = 60  # stop retrying after this many seconds in total, then the template is used


def complete(system: str, user: str, max_tokens: int = 5000, attempts: int = 2) -> tuple[str | None, str | None]:
    """Returns (text, provider description) or (None, None) if every provider failed.

    A reasoning model sometimes uses its whole budget thinking and returns no text
    (finish_reason "length"); that case is retried (up to `attempts`, within DEADLINE_S).
    """
    start = time.monotonic()
    for name, base_url, key, model in providers():
        client = OpenAI(base_url=base_url, api_key=key, timeout=timeout_s(), max_retries=0)
        for attempt in range(attempts):
            if time.monotonic() - start > DEADLINE_S:
                return None, None
            try:
                r = client.chat.completions.create(
                    model=model, max_tokens=max_tokens, temperature=0.2,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
                text = (r.choices[0].message.content or "").strip()
                if text:
                    return text, f"{name} ({model})"
                log.warning("LLM %s returned no text (finish=%s), attempt %d", name, r.choices[0].finish_reason,
                            attempt + 1)
            except Exception as e:  # noqa: BLE001  (rate limit, timeout, bad key: try the next one)
                log.warning("LLM %s failed: %s", name, e.__class__.__name__)
                break
    return None, None
