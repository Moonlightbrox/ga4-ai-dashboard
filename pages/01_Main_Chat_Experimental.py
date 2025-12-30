"""
EXPERIMENTAL MAIN PAGE – CHAT FIRST
==================================

Layout rules:
- No page scroll
- Chat + tables same height
- Tables wider than chat (60 / 40)
"""

import streamlit as st
import pandas as pd

from analytics.raw_reports import get_all_core_reports
from ai.claude_service import chat_with_data
from components.date_selector import get_date_range
from ai.claude_service import business_health_check
from ai.agents.orchestrator import generate_ai_summary




# =====================================================================
# PAGE CONFIG
# =====================================================================

st.set_page_config(
    page_title="GA4 AI – Chat First",
    layout="wide",
)

# Global layout + height control
st.markdown(
    """
    <style>
        body {
            overflow: hidden;
        }
        .block-container {
            padding-top: 1rem;
            padding-bottom: 0rem;
            height: 100vh;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# =====================================================================
# SESSION STATE
# =====================================================================

if "reports" not in st.session_state:
    st.session_state.reports = {}

if "reports_loaded" not in st.session_state:
    st.session_state.reports_loaded = False

if "last_date_key" not in st.session_state:
    st.session_state.last_date_key = None

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []


# =====================================================================
# HEADER
# =====================================================================

st.title("💬 GA4 AI Analytics")
st.caption("Chat with your data on the left. Explore raw reports on the right.")


# =====================================================================
# DATE SELECTION
# =====================================================================

start_date, end_date = get_date_range()
date_key = f"{start_date}_{end_date}"

if st.session_state.last_date_key != date_key:
    st.session_state.reports_loaded = False
    st.session_state.last_date_key = date_key


# =====================================================================
# LOAD REPORTS
# =====================================================================

if not st.session_state.reports_loaded:
    with st.spinner("📊 Loading GA4 data..."):
        core_reports = get_all_core_reports(start_date, end_date)
        st.session_state.reports = {
            report_id: report_info.get("data")
            for report_id, report_info in core_reports.items()
        }
        st.session_state.reports_loaded = True

reports = st.session_state.reports


# =====================================================================
# SHARED HEIGHT CALCULATION
# =====================================================================

# Header + date selector approx height ≈ 190px
CONTENT_HEIGHT = 600  # fallback for Streamlit container API


# =====================================================================
# MAIN LAYOUT (40% CHAT | 60% TABLES)
# =====================================================================

chat_col, table_col = st.columns([2, 3], gap="large")


# =====================================================================
# CHAT COLUMN
# =====================================================================

with chat_col:
    st.subheader("💬 Chat")

    # -----------------------------------------------------------------
    # ACTION BUTTONS (CHAT ACTIONS)
    # -----------------------------------------------------------------
    col_btn_1, col_btn_2 = st.columns([1, 3])

    with col_btn_1:
        run_health_check = st.button(
            "🩺 Business Health Check",
            use_container_width=True,
        )

    with col_btn_2:
        run_multi_agent = st.button(
            "🤖 Multi-Agent Discussion",
            use_container_width=True,
    )

    # -----------------------------------------------------------------
    # CHAT BOX (FIXED HEIGHT)
    # -----------------------------------------------------------------
    chat_box = st.container(height=CONTENT_HEIGHT)

    # -----------------------------------------------------------------
    # HANDLE BUSINESS HEALTH CHECK ACTION
    # -----------------------------------------------------------------
    if run_health_check:
        user_trigger = "Run a comprehensive business health check."

        # Add user-style message
        st.session_state.chat_messages.append({
            "role": "user",
            "content": user_trigger
        })

        with chat_box:
            with st.chat_message("assistant"):
                with st.spinner("Running business health check…"):
                    try:
                        result = business_health_check(
                            reports=reports,
                            start_date=start_date,
                            end_date=end_date,
                        )
                        st.markdown(result)
                    except Exception as e:
                        result = f"❌ Business health check failed: {e}"
                        st.error(result)

        # Save assistant response
        st.session_state.chat_messages.append({
            "role": "assistant",
            "content": result
        })

        st.session_state.chat_history.extend([
            {"role": "user", "content": user_trigger},
            {"role": "assistant", "content": result},
        ])

        st.rerun()

    # -----------------------------------------------------------------
    # HANDLE MULTI-AGENT DISCUSSION
    # -----------------------------------------------------------------
    if run_multi_agent:
        user_trigger = "Run a multi-agent discussion on my analytics data."

        st.session_state.chat_messages.append({
            "role": "user",
            "content": user_trigger
        })

        with chat_box:
            with st.chat_message("assistant"):
                with st.spinner("Running multi-agent analysis…"):
                    try:
                        # Minimal, safe payload (reuse what you already trust)
                        traffic = reports.get("traffic_overview")

                        payload = {
                            "traffic_overview": {
                                "row_count": len(traffic),
                                "columns": list(traffic.columns),
                                "sample_rows": traffic.head(30).to_dict("records"),
                            }
                        }

                        ai_output = generate_ai_summary(payload)

                        final_answer = f"""
                            ### 🧾 Final Summary
                            {ai_output["synthesizer"]}
                            🧠 Analyst
                            {ai_output["analyst"]}   
                            🧐 Critic
                            {ai_output["critic"]}
                        
                            """
                        st.markdown(final_answer)

                    except Exception as e:
                        final_answer = f"❌ Multi-agent analysis failed: {e}"
                        st.error(final_answer)

        st.session_state.chat_messages.append({
            "role": "assistant",
            "content": final_answer
        })

        st.session_state.chat_history.extend([
            {"role": "user", "content": user_trigger},
            {"role": "assistant", "content": final_answer},
        ])

        st.rerun()


    # -----------------------------------------------------------------
    # RENDER CHAT HISTORY
    # -----------------------------------------------------------------
    with chat_box:
        if st.session_state.chat_messages:
            for msg in st.session_state.chat_messages:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
        else:
            st.markdown(
                "<div style='color:#888; padding-top:1rem;'>Ask a question to start.</div>",
                unsafe_allow_html=True,
            )

    # -----------------------------------------------------------------
    # CHAT INPUT
    # -----------------------------------------------------------------
    prompt = st.chat_input("Ask about performance, conversions, issues…")

    if prompt:
        st.session_state.chat_messages.append(
            {"role": "user", "content": prompt}
        )

        with chat_box:
            with st.chat_message("assistant"):
                with st.spinner("Thinking…"):
                    response = chat_with_data(
                        reports=reports,
                        user_question=prompt,
                        conversation_history=st.session_state.chat_history,
                        start_date=start_date,
                        end_date=end_date,
                    )
                    st.markdown(response)

        st.session_state.chat_messages.append(
            {"role": "assistant", "content": response}
        )

        st.session_state.chat_history.extend([
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": response},
        ])

        st.rerun()


# =====================================================================
# TABLE COLUMN
# =====================================================================

with table_col:
    st.subheader("📊 Data Tables")

    report_map = {
        "Traffic Overview": "traffic_overview",
        "Daily Trends": "daily_trends",
        "Landing Pages": "landing_pages",
        "Device Performance": "device_performance",
        "Ecommerce Funnel": "ecommerce_funnel",
        "Top Products": "top_products",
        "Geographic Breakdown": "geographic_breakdown",
        "User Acquisition": "user_acquisition",
        "Page Performance": "page_performance",
    }

    selected_label = st.selectbox(
        "Select report",
        list(report_map.keys()),
    )

    report_key = report_map[selected_label]
    df = reports.get(report_key, pd.DataFrame())

    if not df.empty:
        st.download_button(
            "⬇️ Export CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name=f"{report_key}_{start_date}_{end_date}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.dataframe(
        df,
        use_container_width=True,
        height=CONTENT_HEIGHT,
    )
