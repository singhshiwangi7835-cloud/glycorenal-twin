"""Shared UI pieces: disclaimer footer, sidebar user box, KDIGO colour chip."""

from __future__ import annotations

import streamlit as st

import api_client

DISCLAIMER = "Prototype – decision support only, not for clinical use"

KDIGO_HEX = {"green": "#2e7d32", "yellow": "#f9a825", "orange": "#ef6c00", "red": "#c62828"}


def footer() -> None:
    st.divider()
    st.caption(f"⚕️ {DISCLAIMER}")


def sidebar_user() -> None:
    user = api_client.current_user()
    if not user:
        return
    with st.sidebar:
        st.markdown(f"**{user['full_name'] or user['username']}**  \n{user['role'].title()}")
        if st.button("Log out", width="stretch"):
            api_client.logout()
            st.rerun()
        st.caption(DISCLAIMER)


def kdigo_chip(stage: str, colour: str) -> str:
    """HTML chip for a KDIGO stage, coloured by the KDIGO heat map (use with unsafe_allow_html)."""
    hex_ = KDIGO_HEX.get(colour, "#607d8b")
    text = "#1f2933" if colour == "yellow" else "#ffffff"
    return (f"<span style='background:{hex_};color:{text};padding:2px 10px;"
            f"border-radius:12px;font-weight:600'>{stage}</span>")
