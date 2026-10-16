"""Dexcom connector: STUB for the prototype ("Connect Dexcom: coming soon").

Planned (CLAUDE.md section 8): OAuth2 against the Dexcom sandbox (DEXCOM_BASE_URL), then poll the
v3 EGVs endpoint every 5 minutes and save readings through translator.save(source="dexcom").
Cut from the prototype for time (see FAST_TRACK.md); Libre CSV upload and the simulator cover
live CGM data in the demo.
"""

from __future__ import annotations

from urllib.parse import urlencode

from config.settings import get_settings


def is_configured() -> bool:
    s = get_settings()
    return bool(s.dexcom_client_id and s.dexcom_client_secret)


def status() -> dict:
    return {"provider": "dexcom", "available": False, "configured": is_configured(),
            "message": "Connect Dexcom: coming soon. Use Libre CSV upload or the live simulator for now."}


def authorize_url(state: str) -> str:
    """The URL the patient would be sent to (not used until the OAuth flow is built)."""
    s = get_settings()
    return f"{s.dexcom_base_url}/v2/oauth2/login?" + urlencode(
        {"client_id": s.dexcom_client_id, "redirect_uri": s.dexcom_redirect_uri,
         "response_type": "code", "scope": "offline_access", "state": state})
