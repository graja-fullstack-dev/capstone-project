import pandas as pd
import streamlit as st

from pharma_intake import audit, repository, workflow
from pharma_intake.schemas import ReportType, Status
from pharma_intake.ui import disclaimer, get_conn, page_setup
from pharma_intake.validation import validate_with
from pharma_intake.schemas import UpdateStatusArgs

page_setup("Dashboard", "📊")
conn = get_conn()

f1, f2 = st.columns(2)
statuses = f1.multiselect("Status", [s.value for s in Status])
types = f2.multiselect("Report type", [t.value for t in ReportType])
rows = repository.list_reports(conn, statuses or None, types or None)

st.caption(f"{len(rows)} report(s)")
if rows:
    df = pd.DataFrame(rows)[["ref_id", "report_type", "product_name", "batch_id", "date_received", "reporter_type", "status", "updated_at"]]
    st.dataframe(df, width="stretch", hide_index=True)
else:
    st.info("No reports match the filters.")

st.divider()
st.subheader("Report detail & status")
if rows:
    ref = st.selectbox("Select report", [r["ref_id"] for r in rows])
    rep = repository.get_report(conn, ref)
    with st.expander("Details", expanded=True):
        st.write({k: v for k, v in rep.items() if v is not None})
    with st.expander("Audit history"):
        st.dataframe(pd.DataFrame(audit.list_events(conn, ref)), width="stretch", hide_index=True)

    allowed = workflow.ALLOWED[Status(rep["status"])]
    pending = conn.execute("SELECT 1 FROM approvals WHERE ref_id=? AND state='PENDING'", (ref,)).fetchone()
    if pending:
        st.warning("Frozen: closure is awaiting human reviewer approval (see Review Approvals).")
    elif not allowed:
        st.info("This report is Closed (terminal).")
    else:
        target = st.selectbox("Next status", [s.value for s in allowed])
        code = st.text_input("Your reviewer code", placeholder="REV-01")
        if st.button("Apply transition"):
            out = validate_with(UpdateStatusArgs, {"ref_id": ref, "target_status": target, "reviewer_code": code})
            if not out.ok:
                st.error("\n".join(out.errors))
            else:
                try:
                    r = workflow.request_transition(conn, ref, Status(target), actor=out.model.reviewer_code)
                    st.success("Closure requested - awaiting human approval." if r["pending_approval"] else f"Status is now {r['status']}.")
                    st.rerun() if r["applied"] else None
                except workflow.WorkflowError as exc:
                    st.error(str(exc))
disclaimer()
