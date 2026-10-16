"""The twin's assistant: explains the twin, never predicts (CLAUDE.md section 10).

ask() flow:
  1. build the de-identified context from TwinState + predictions + ranked options + alerts
  2. patient safety first: low glucose -> fixed hypo message; medicine question -> "discuss with
     your doctor" (neither goes to the LLM)
  3. cache: same mode + language + question + data within 30 minutes -> same answer
  4. retrieve 3 guideline snippets (TF-IDF) and call the LLM (Kimi -> Gemini) with a 20 s timeout
  5. patient answers are checked for medicine-change advice; violation or no LLM -> template
  6. add the "Decision support only" footer
The LLM is only called on a user action (button or chat), never per reading.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from sqlmodel import Session

from src.alerts.engine import active_alerts
from src.db.models import LLMCache
from src.llm import fallback, guardrails, prompts, rag
from src.llm.client import complete, providers
from src.meals.engine import top_spiking_foods
from src.treatment.rank import rank
from src.twin.engine import latest_predictions
from src.twin.state import build_state

CACHE_MINUTES = 30


def _alert_dicts(session: Session, pid: str) -> list[dict]:
    return [{"type": a.type, "severity": a.severity, "message": a.message} for a in active_alerts(session, pid)]


def _cache_key(mode: str, language: str, question: str | None, ctx: dict) -> str:
    """Hash of mode + language + question + the slow-moving picture of the patient.

    The live sensor changes the latest glucose every few seconds, so it is left out and CGM
    percentages are rounded; otherwise a live patient would never hit the cache.
    """
    stable = {k: v for k, v in ctx.items() if k != "latest_glucose"}
    if stable.get("cgm_14d"):
        stable["cgm_14d"] = {k: round(v) if isinstance(v, (int, float)) else v for k, v in stable["cgm_14d"].items()}
    raw = json.dumps([mode, language, question or "", stable], sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _result(text: str, *, provider: str | None, offline: bool, cached: bool = False,
            sources: list[dict] | None = None, guardrail: str | None = None) -> dict:
    return {"text": text, "provider": provider, "offline": offline, "cached": cached,
            "sources": [{"title": s["title"], "source": s["source"]} for s in (sources or [])],
            "guardrail": guardrail}


def ask(session: Session, patient_id: str, mode: str, language: str = "en",
        question: str | None = None) -> dict:
    if mode not in prompts.MODES:
        raise ValueError(f"mode must be one of {prompts.MODES}")
    patient_view = mode in prompts.PATIENT_MODES
    language = language if (patient_view and language in ("en", "hi")) else "en"

    state = build_state(session, patient_id)
    alerts = _alert_dicts(session, patient_id)
    treatments = rank(state, patient_view=patient_view)
    ctx = prompts.build_context(state, latest_predictions(session, patient_id), treatments, alerts,
                                top_spiking_foods(session, patient_id) if patient_view else None, patient_view)
    options = [o for o in treatments.get("options", []) if o["kind"] == "lifestyle"]

    # ---- fixed safety answers (never from the LLM) ----
    if patient_view and guardrails.needs_hypo_message(state, alerts):
        return _result(guardrails.with_footer(guardrails.HYPO_SAFETY[language], True, language),
                       provider="safety message", offline=False, guardrail="hypoglycaemia")
    if patient_view and mode == "chat_patient" and guardrails.asks_about_medicine(question):
        return _result(guardrails.with_footer(guardrails.ASK_DOCTOR[language], True, language),
                       provider="safety message", offline=False, guardrail="medicine question")

    # ---- cache ----
    key = _cache_key(mode, language, question, ctx)
    hit = session.get(LLMCache, key)
    now = datetime.now(timezone.utc)
    if hit and now - hit.created_at < timedelta(minutes=CACHE_MINUTES):
        cached = json.loads(hit.response)
        return {**cached, "cached": True}

    # ---- LLM with retrieved guideline notes ----
    query = question or ("kidney risk albuminuria eGFR SGLT2 ACE inhibitor blood pressure" if not patient_view
                         else "diet walking salt weight sugar targets")
    snippets = rag.retrieve(query, k=3)
    text, provider = complete(prompts.system_prompt(mode, language), prompts.user_prompt(ctx, snippets, question))
    guard = None
    if text and patient_view and guardrails.violates_patient_rules(text):
        text, guard = None, "medicine advice removed"
    offline = text is None
    if offline:
        if patient_view:
            text = fallback.patient(ctx, language, options, tips_only=(mode == "report_patient"))
        elif mode == "chat_doctor":
            text = fallback.chat(ctx, question or "", False, language, options)
        else:
            text = fallback.doctor(ctx, report=(mode == "report_doctor"))
        provider = "template"
    result = _result(guardrails.with_footer(text, patient_view, language), provider=provider,
                     offline=offline, sources=snippets if not offline else [], guardrail=guard)
    if not offline:  # only cache real LLM answers (templates are instant anyway)
        session.merge(LLMCache(key=key, response=json.dumps(result, ensure_ascii=False), created_at=now))
        session.commit()
    return result


def status() -> dict:
    p = providers()
    return {"configured": bool(p), "providers": [f"{n} ({m})" for n, _, _, m in p],
            "message": None if p else "No LLM key in .env: the assistant uses built-in templates (offline summary)."}
