import pandas as pd
import streamlit as st

from pharma_intake import audit
from pharma_intake.ui import disclaimer, get_conn, page_setup

page_setup("Audit Log (read-only)", "🧾")
conn = get_conn()

ok, bad = audit.verify_chain(conn)
st.success("Hash chain verified: no tampering detected.") if ok else st.error(f"Hash chain broken at entry #{bad}.")

ref = st.text_input("Filter by reference ID", placeholder="REF-2026-0001")
events = audit.list_events(conn, ref.strip() or None)
if events:
    df = pd.DataFrame(events)
    st.dataframe(df, width="stretch", hide_index=True)
    st.download_button("Export CSV", df.to_csv(index=False), "audit_log.csv", "text/csv")
else:
    st.info("No audit entries.")
st.caption("Entries record actions, timestamps, status changes and field names only - never free-text content.")
disclaimer()
