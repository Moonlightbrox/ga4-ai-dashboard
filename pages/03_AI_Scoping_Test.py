import os

import streamlit as st
import anthropic

from analytics.raw_reports import get_all_core_reports
from components.date_selector import get_date_range
from components.format import format_dataframe_numbers


st.set_page_config(
    page_title="AI Scoping Test",
    layout="wide",
    initial_sidebar_state="expanded",
)



if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

if "last_prompt" not in st.session_state:
    st.session_state.last_prompt = None


st.title("AI Scoping Test")
st.caption("Prototype page for AI logic, report scoping, and user flow")
st.divider()

col_chat, col_reports = st.columns([3, 2])

with st.sidebar:
    st.header("Date range")
    start_date, end_date = get_date_range()

try:
    core_reports = get_all_core_reports(start_date, end_date)
except Exception as exc:
    core_reports = {}
    st.sidebar.error(f"Failed to load reports: {exc}")


with col_reports:
    st.subheader("\U0001F4CA Reports")
    st.caption("Select reports to include in AI analysis")

    bulk_cols = st.columns(3)
    select_all = bulk_cols[0].button("Select all reports")
    select_basic = bulk_cols[1].button("Select basic reports")
    select_user = bulk_cols[2].button("Select user reports")

    if select_all or select_basic:
        for report in core_reports.values():
            st.session_state[f"report_{report['id']}"] = True

    if select_user:
        # TODO: Implement user-defined reports selection (Phase 3).
        st.info("User-defined reports are not available yet.")

    selected_reports = []
    for report in core_reports.values():
        checked = st.checkbox(
            report["name"],
            help=report["description"],
            key=f"report_{report['id']}",
        )
        if checked:
            selected_reports.append(report)

    st.divider()

    if selected_reports:
        st.markdown("**Report Preview:**")
        preview_tabs = st.tabs([report["name"] for report in selected_reports])
        for tab, report in zip(preview_tabs, selected_reports):
            with tab:
                # Data sourced from analytics/raw_reports.py (single source of truth).
                try:
                    preview_df = report.get("data")
                    if preview_df is None:
                        st.info("No data available for this report.")
                    elif getattr(preview_df, "empty", False):
                        st.info("No rows returned for this report.")
                    else:
                        # UI-only formatting for AI Scoping Test page.
                        # Raw report data remains unchanged.
                        formatted_df = format_dataframe_numbers(preview_df)
                        st.dataframe(formatted_df, use_container_width=True)
                except Exception as exc:
                    st.warning(f"Unable to load this report: {exc}")
    else:
        st.info("Select a report to preview its data.")

    st.divider()

    with st.expander("Advanced: Custom Report Builder (Coming Soon)"):
        st.caption("Build custom reports using metrics and dimensions")
        st.text_input("Dimensions", disabled=True)
        st.text_input("Metrics", disabled=True)
        st.button("Add report", disabled=True)


with col_chat:
    st.subheader("\U0001F4AC AI Analysis")
    st.caption("Ask questions about the selected reports")

    template_questions = [
        "What are the main performance highlights?",
        "Why did revenue change recently?",
        "Which channel is performing best?",
    ]

    template_cols = st.columns(len(template_questions))
    clicked_template = None
    for idx, question in enumerate(template_questions):
        with template_cols[idx]:
            if st.button(question, key=f"template_{idx}"):
                clicked_template = question

    for message in st.session_state.chat_messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    input_col, clear_col = st.columns([6, 1])
    with input_col:
        user_input = st.chat_input("Ask a question about your data")
    with clear_col:
        if st.button("\U0001F5D1", help="Clear chat"):
            st.session_state.chat_messages = []
            st.session_state.last_prompt = None
            st.rerun()

    if clicked_template:
        user_input = clicked_template

    if user_input:
        if not selected_reports:
            st.warning("Please select at least one report to continue.")
        else:
            st.session_state.chat_messages.append({
                "role": "user",
                "content": user_input,
            })

            selected_lines = [
                f"- {report['name']}: {report['description']}"
                for report in selected_reports
            ]
            prompt = (
                "You are an analytics assistant. You can only use the following reports:\n"
                f"{chr(10).join(selected_lines)}\n\n"
                f"User question:\n\"{user_input}\"\n\n"
                "Rules:\n"
                "- Only use selected reports.\n"
                "- If the question needs data that is not covered, respond exactly: "
                "\"This question requires a report that is not currently included.\"\n"
                "- Keep the response concise and actionable."
            )
            st.session_state.last_prompt = prompt

            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    api_key = os.getenv("ANTHROPIC_API_KEY")
                    if not api_key:
                        response_text = (
                            "AI is not configured. Set ANTHROPIC_API_KEY to enable responses.\n\n"
                            "Prompt preview:\n"
                            f"{prompt}"
                        )
                    else:
                        client = anthropic.Anthropic(api_key=api_key)
                        message = client.messages.create(
                            model="claude-sonnet-4-20250514",
                            max_tokens=800,
                            messages=[{
                                "role": "user",
                                "content": prompt,
                            }],
                        )
                        response_text = message.content[0].text

                    st.write(response_text)
                    st.session_state.chat_messages.append({
                        "role": "assistant",
                        "content": response_text,
                    })








