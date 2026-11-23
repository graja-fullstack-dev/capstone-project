import datetime as dt

import streamlit as st

from pharma_intake import repository
from pharma_intake.refgen import peek_next_ref_id
from pharma_intake.schemas import Channel, ReporterType, ReportType
from pharma_intake.ui import disclaimer, get_conn, page_setup
from pharma_intake.validation import validate_intake

page_setup("Intake Form", "📝")
conn = get_conn()

st.info(f"Next reference ID: **{peek_next_ref_id(conn)}** (assigned when the report is saved). Use fictional, de-identified text only.")

report_type = st.selectbox("Report category *", [t.value for t in ReportType])
is_ae = report_type == ReportType.AE.value

with st.form("intake", clear_on_submit=False):
    c1, c2 = st.columns(2)
    product = c1.text_input("Product name *", placeholder="Examplomab 50 mg Injection")
    lot = c2.text_input("Batch/Lot number *", placeholder="LOT-12345")
    date_received = c1.date_input("Date received *", value=dt.date.today(), max_value=dt.date.today())
    reporter = c2.selectbox("Reporter type *", [r.value for r in ReporterType])
    channel = c1.selectbox("Intake channel *", [c.value for c in Channel])
    description = st.text_area("Detailed description *", height=140, help="20-2000 characters. No patient names, initials, DOB or contact details.")
    event_description, onset = "", None
    if is_ae:
        st.subheader("Adverse event details")
        event_description = st.text_area("Event description *", height=90)
        onset = st.date_input("Event onset date *", value=None, max_value=dt.date.today())
    submitted = st.form_submit_button("Save report", type="primary")

if submitted:
    raw = {
        "report_type": report_type, "product_name": product, "batch_id": lot,
        "date_received": date_received.isoformat() if date_received else "",
        "reporter_type": reporter, "channel": channel, "description": description,
    }
    if is_ae:
        raw["event_description"] = event_description
        raw["event_onset_date"] = onset.isoformat() if onset else None
    outcome = validate_intake(raw)
    for note in outcome.repairs:
        st.info(f"Auto-corrected: {note}")
    if not outcome.ok:
        st.error("The report was NOT saved. Please fix the following:")
        for e in outcome.errors:
            st.write(f"- {e}")
    else:
        ref = repository.create_report(conn, outcome.model, actor="intake-operator")
        st.success(f"Report saved with reference **{ref}** (status: New).")
disclaimer()
