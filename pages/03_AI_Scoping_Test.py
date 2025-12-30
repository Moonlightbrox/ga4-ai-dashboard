import os

import pandas as pd
import streamlit as st
import anthropic


st.set_page_config(
    page_title="AI Scoping Test",
    layout="wide",
    initial_sidebar_state="expanded",
)


REPORT_CATALOG = [
    {
        "id": "traffic_source",
        "name": "Traffic Source Performance",
        "description": "Sessions, users, and revenue by source and medium",
    },
    {
        "id": "country_performance",
        "name": "Country Performance",
        "description": "Users, sessions, and revenue by country",
    },
    {
        "id": "landing_pages",
        "name": "Landing Pages",
        "description": "Top landing pages with sessions and engagement",
    },
    {
        "id": "device_performance",
        "name": "Device Performance",
        "description": "Performance split by device category and browser",
    },
    {
        "id": "daily_trends",
        "name": "Daily Trends",
        "description": "Time series for users, sessions, and revenue",
    },
    {
        "id": "ecommerce_funnel",
        "name": "Ecommerce Funnel",
        "description": "Key ecommerce events and conversion funnel steps",
    },
]


if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

if "last_prompt" not in st.session_state:
    st.session_state.last_prompt = None


st.title("AI Scoping Test")
st.caption("Prototype page for AI logic, report scoping, and user flow")
st.divider()

col_chat, col_reports = st.columns([3, 2])


with col_reports:
    st.subheader("\U0001F4CA Reports")
    st.caption("Select reports to include in AI analysis")

    selected_reports = []
    for report in REPORT_CATALOG:
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
        report_previews = {
            "traffic_source": pd.DataFrame(
                [
                    {"source": "google", "users": 1240, "sessions": 1680, "revenue": 15420.50},
                    {"source": "facebook", "users": 740, "sessions": 910, "revenue": 6420.00},
                    {"source": "email", "users": 310, "sessions": 420, "revenue": 3890.75},
                ]
            ),
            "country_performance": pd.DataFrame(
                [
                    {"country": "United States", "users": 980, "revenue": 11240.10},
                    {"country": "Canada", "users": 260, "revenue": 2940.00},
                    {"country": "Germany", "users": 190, "revenue": 1780.50},
                ]
            ),
            "landing_pages": pd.DataFrame(
                [
                    {"landing_page": "/home", "sessions": 820, "engagement_rate": "62%"},
                    {"landing_page": "/pricing", "sessions": 540, "engagement_rate": "58%"},
                    {"landing_page": "/blog/intro", "sessions": 310, "engagement_rate": "47%"},
                ]
            ),
            "device_performance": pd.DataFrame(
                [
                    {"device": "desktop", "users": 860, "sessions": 1120},
                    {"device": "mobile", "users": 620, "sessions": 790},
                    {"device": "tablet", "users": 120, "sessions": 150},
                ]
            ),
            "daily_trends": pd.DataFrame(
                [
                    {"date": "2024-01-01", "users": 210, "sessions": 280, "revenue": 1240.00},
                    {"date": "2024-01-02", "users": 240, "sessions": 310, "revenue": 1390.50},
                    {"date": "2024-01-03", "users": 195, "sessions": 260, "revenue": 980.25},
                ]
            ),
            "ecommerce_funnel": pd.DataFrame(
                [
                    {"step": "product view", "events": 1280},
                    {"step": "add to cart", "events": 410},
                    {"step": "checkout", "events": 180},
                ]
            ),
        }

        preview_tabs = st.tabs([report["name"] for report in selected_reports])
        for tab, report in zip(preview_tabs, selected_reports):
            with tab:
                # TODO: Replace mock data with real report data (Phase 2).
                preview_df = report_previews.get(report["id"], pd.DataFrame())
                st.dataframe(preview_df, use_container_width=True)
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




