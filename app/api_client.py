"""Small HTTP client the Streamlit pages use to talk to the FastAPI backend.

The login token is kept in st.session_state and sent as a Bearer header on every call.
Errors come back as APIError with a readable message (shown with st.error by the pages).
"""

from __future__ import annotations

import os

import httpx
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
TIMEOUT = 40


class APIError(Exception):
    pass


def _headers() -> dict:
    token = st.session_state.get("token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def _handle(r: httpx.Response):
    if r.status_code == 401 and st.session_state.get("token"):
        logout()
        raise APIError("Your session expired. Please log in again.")
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except ValueError:
            detail = r.text
        raise APIError(str(detail))
    return r.json()


def _call(method: str, path: str, **kw):
    try:
        return _handle(httpx.request(method, f"{API_URL}{path}", headers=_headers(), timeout=TIMEOUT, **kw))
    except httpx.HTTPError as e:
        raise APIError(f"Cannot reach the API at {API_URL}. Is it running? ({e.__class__.__name__})") from e


def get(path: str, **params):
    return _call("GET", path, params=params or None)


@st.cache_data(ttl=15, show_spinner=False)
def _cached(path: str, token: str, params: tuple):
    return _call("GET", path, params=dict(params) or None)


def cached_get(path: str, **params):
    """GET, cached for 15 s per user (any post/put/delete/upload clears the cache)."""
    return _cached(path, st.session_state.get("token", ""), tuple(sorted(params.items())))


def _changed():
    _cached.clear()


def post(path: str, json: dict | list | None = None, data: dict | None = None):
    out = _call("POST", path, json=json, data=data)
    if path != "/auth/login":
        _changed()
    return out


def put(path: str, json: dict):
    out = _call("PUT", path, json=json)
    _changed()
    return out


def delete(path: str):
    out = _call("DELETE", path)
    _changed()
    return out


def upload(path: str, filename: str, content: bytes, content_type: str = "text/csv"):
    out = _call("POST", path, files={"file": (filename, content, content_type)})
    _changed()
    return out


def login(username: str, password: str) -> dict:
    out = post("/auth/login", data={"username": username, "password": password})
    st.session_state["token"] = out["access_token"]
    st.session_state["user"] = out["user"]
    st.session_state["lang"] = out["user"].get("language", "en")
    return out["user"]


def logout() -> None:
    for k in list(st.session_state.keys()):
        del st.session_state[k]


def current_user() -> dict | None:
    return st.session_state.get("user")
