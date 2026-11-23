import streamlit as st

from pharma_intake import repository, workflow
from pharma_intake.schemas import ApprovalDecisionArgs
from pharma_intake.ui import disclaimer, get_conn, page_setup
from pharma_intake.validation import validate_with

page_setup("Review Approvals (HITL gate)", "✅")
conn = get_conn()
st.caption("In Review -> Closed requires an explicit human decision. The reviewer must differ from the requester. Assistants cannot approve.")

pending = repository.pending_approvals(conn)
if not pending:
    st.info("No closure requests are pending.")
for ap in pending:
    with st.container(border=True):
        st.markdown(f"**{ap['ref_id']}** - {ap['product_name']} ({ap['batch_id']}) - requested by `{ap['requested_by']}` at {ap['requested_at']}")
        code = st.text_input("Reviewer code", key=f"code_{ap['id']}", placeholder="REV-02")
        a, b = st.columns(2)
        for label, approve, col in (("Approve closure", True, a), ("Reject", False, b)):
            if col.button(label, key=f"{label}_{ap['id']}"):
                out = validate_with(ApprovalDecisionArgs, {"ref_id": ap["ref_id"], "reviewer_code": code, "approve": approve})
                if not out.ok:
                    st.error("\n".join(out.errors))
                    continue
                try:
                    r = workflow.decide_approval(conn, ap["ref_id"], out.model.reviewer_code, approve)
                    st.success(f"Decision recorded. Status: {r['status']}")
                    st.rerun()
                except workflow.WorkflowError as exc:
                    st.error(str(exc))
disclaimer()
