"""Home page. Run with: streamlit run app.py"""
import streamlit as st

from pharma_intake import audit, repository
from pharma_intake.ui import disclaimer, get_conn, page_setup

page_setup("Pharma Safety Intake & Triage Tracker")
conn = get_conn()

reports = repository.list_reports(conn)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Reports", len(reports))
c2.metric("New", sum(r["status"] == "New" for r in reports))
c3.metric("In Review", sum(r["status"] == "In Review" for r in reports))
c4.metric("Closed", sum(r["status"] == "Closed" for r in reports))

ok, bad = audit.verify_chain(conn)
st.success("Audit chain verified") if ok else st.error(f"Audit chain broken at entry {bad}")

st.markdown(
    """
**Pages (sidebar):** Intake - Dashboard - Review Approvals - Knowledge Assistant - Audit Log

This local prototype captures *fictional* product quality complaints and suspected adverse event reports,
validates mandatory fields, tracks **New -> In Review -> Closed** (closure needs human approval),
keeps a tamper-evident audit trail, and answers SOP/history questions with a 4-stage hybrid RAG pipeline.
"""
)
disclaimer()
