import streamlit as st

from pharma_intake.ui import disclaimer, get_orchestrator, page_setup

page_setup("Knowledge Assistant", "🔎")
orch = get_orchestrator()
st.sidebar.caption(f"Agent backend: {orch.backend.name}")
st.caption("Ask about SOPs or past reports (e.g. `LOT-88392`, `difficulty breathing`). Chat can also log reports or request status changes. "
           "First search needs the local models: run `python scripts/download_models.py` once.")

history = st.session_state.setdefault("chat", [])
for turn in history:
    with st.chat_message(turn["role"]):
        st.markdown(turn["text"])
        if turn.get("run"):
            run = turn["run"]
            st.caption(f"Route: {run.route.value}")
            if run.stages:
                with st.expander("Retrieval stages (BM25 -> dense -> RRF -> cross-encoder)"):
                    st.json(run.stages)
            with st.expander("ReAct trace (short-term memory)"):
                st.table(run.trace)

if prompt := st.chat_input("Ask a question or give an instruction"):
    history.append({"role": "user", "text": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Working..."):
            run = orch.handle(prompt)
        st.text(run.reply) if run.route.value == "hybrid_rag" else st.markdown(run.reply)
        st.caption(f"Route: {run.route.value}")
        if run.stages:
            with st.expander("Retrieval stages (BM25 -> dense -> RRF -> cross-encoder)"):
                st.json(run.stages)
        with st.expander("ReAct trace (short-term memory)"):
            st.table(run.trace)
    history.append({"role": "assistant", "text": run.reply, "run": run})
disclaimer()
