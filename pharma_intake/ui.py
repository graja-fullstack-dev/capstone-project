"""Shared Streamlit helpers (connection, banner, agent wiring). No business rules here."""
from __future__ import annotations

import streamlit as st

from . import config, db
from .agent.orchestrator import Orchestrator
from .agent.tools import AgentContext
from .rag.pipeline import build_retriever


@st.cache_resource
def get_conn():
    return db.connect()


def banner() -> None:
    st.sidebar.warning("Training prototype - fictional data only - non-clinical.\n\nNo causality, treatment or reportability decisions.")


def page_setup(title: str, icon: str = "💊") -> None:
    st.set_page_config(page_title=f"{title} - Pharma Intake Tracker", page_icon=icon, layout="wide")
    banner()
    st.title(f"{icon} {title}")


def get_orchestrator() -> Orchestrator:
    if "orchestrator" not in st.session_state:
        conn = get_conn()
        ctx = AgentContext(conn=conn, retriever_factory=lambda: build_retriever(conn), actor="agent")
        st.session_state["orchestrator"] = Orchestrator(ctx)
    return st.session_state["orchestrator"]


def disclaimer() -> None:
    st.caption(config.DISCLAIMER)
