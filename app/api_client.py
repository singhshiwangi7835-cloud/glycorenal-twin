"""Small HTTP client the Streamlit pages use to talk to the FastAPI backend.

The login token is kept in st.session_state and sent as a Bearer header on every call.
"""

from __future__ import annotations

import os

import httpx
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
TIMEOUT = 30


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


def get(path: str, **params):
    try:
        return _handle(httpx.get(f"{API_URL}{path}", params=params, headers=_headers(),
                                 timeout=TIMEOUT))
    except httpx.HTTPError as e:
        raise APIError(f"Cannot reach the API at {API_URL}. Is it running? ({e})") from e


def post(path: str, json: dict | None = None, data: dict | None = None):
    try:
        return _handle(httpx.post(f"{API_URL}{path}", json=json, data=data, headers=_headers(),
                                  timeout=TIMEOUT))
    except httpx.HTTPError as e:
        raise APIError(f"Cannot reach the API at {API_URL}. Is it running? ({e})") from e


def login(username: str, password: str) -> dict:
    out = post("/auth/login", data={"username": username, "password": password})
    st.session_state["token"] = out["access_token"]
    st.session_state["user"] = out["user"]
    return out["user"]


def logout() -> None:
    for k in ("token", "user"):
        st.session_state.pop(k, None)


def current_user() -> dict | None:
    return st.session_state.get("user")
