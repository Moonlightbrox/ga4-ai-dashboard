""" app.py

=====================================================================
PURPOSE
=====================================================================

Production-ready analytics platform with comprehensive GA4 reporting.

Features:
- 8 core GA4 reports
- Business Health Check (Claude)
- Interactive Chat (Claude)
- Multi-agent analysis (Groq)
"""

import streamlit as st
import pandas as pd

from analytics.raw_reports import get_all_core_reports, get_summary_statistics
from ai.agents.orchestrator import generate_ai_summary
from ai.claude_service import business_health_check, chat_with_data, quick_insights
from components.date_selector import get_date_range


# =====================================================================
# PAGE SETUP
# =====================================================================

st.set_page_config(
    page_title="GA4 AI Analytics Platform",
    layout="wide",
    initial_sidebar_state="expanded"
)


# =====================================================================
# SESSION STATE
# =====================================================================

if "reports_loaded" not in st.session_state:
    st.session_state.reports_loaded = False

if "all_reports" not in st.session_state:
    st.session_state.all_reports = {}

if "business_check_done" not in st.session_state:
    st.session_state.business_check_done = False
    
if "business_check_result" not in st.session_state:
    st.session_state.business_check_result = None

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

if "run_multiagent" not in st.session_state:
    st.session_state.run_multiagent = False


# =====================================================================
# SIDEBAR
# =====================================================================

with st.sidebar:
    st.header("⚙️ Settings")
    
    # Date selection
    start_date, end_date = get_date_range()
    
    # Check if date changed - reset reports
    current_dates = f"{start_date}_{end_date}"
    if "last_dates" not in st.session_state:
        st.session_state.last_dates = current_dates
    elif st.session_state.last_dates != current_dates:
        st.session_state.reports_loaded = False
        st.session_state.business_check_done = False
        st.session_state.last_dates = current_dates
    
    st.markdown("---")
    
    
    # Report loading status
    if st.session_state.reports_loaded:
        st.success("✅ Data loaded")
        if st.button("🔄 Refresh Data"):
            st.session_state.reports_loaded = False
            st.rerun()
    else:
        st.warning("⏳ Loading data...")


# =====================================================================
# LOAD ALL REPORTS (ONCE)
# =====================================================================

if not st.session_state.reports_loaded:
    with st.spinner("📊 Fetching comprehensive GA4 data..."):
        try:
            all_reports = get_all_core_reports(start_date, end_date)
            st.session_state.all_reports = all_reports
            st.session_state.reports_loaded = True
            st.rerun()
        except Exception as e:
            st.error(f"❌ Failed to load data: {str(e)}")
            st.stop()

reports = st.session_state.all_reports


# =====================================================================
# HEADER & QUICK METRICS
# =====================================================================

st.title("🔍 GA4 AI Analytics Platform")
st.caption(f"Analysis period: **{start_date}** to **{end_date}**")

# Calculate summary stats
summary = get_summary_statistics(reports)

if summary:
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("Total Users", f"{summary['total_users']:,.0f}")
    
    with col2:
        st.metric("Sessions", f"{summary['total_sessions']:,.0f}")
    
    with col3:
        st.metric("Revenue", f"${summary['total_revenue']:,.2f}")
    
    with col4:
        st.metric("Transactions", f"{summary['total_transactions']:,.0f}")
    
    with col5:
        st.metric("Conv. Rate", f"{summary['conversion_rate']:.2f}%")

st.markdown("---")


# =====================================================================
# MODE 1: BUSINESS HEALTH CHECK
# =====================================================================

# Available reports in expanders
with st.expander("📊 View Available Data"):
    tab1, tab2, tab3, tab4 = st.tabs(["Traffic", "Trends", "Landing Pages", "More Reports"])
    
    with tab1:
        st.dataframe(reports.get("traffic_overview", pd.DataFrame()), use_container_width=True)
    
    with tab2:
        st.dataframe(reports.get("daily_trends", pd.DataFrame()), use_container_width=True)
    
    with tab3:
        st.dataframe(reports.get("landing_pages", pd.DataFrame()), use_container_width=True)
    
    with tab4:
        report_choice = st.selectbox("Select report:", [
            "Device Performance",
            "Ecommerce Funnel",
            "Top Products",
            "Geographic Breakdown",
            "User Acquisition"
        ])
        
        report_map = {
            "Device Performance": "device_performance",
            "Ecommerce Funnel": "ecommerce_funnel",
            "Top Products": "top_products",
            "Geographic Breakdown": "geographic_breakdown",
            "User Acquisition": "user_acquisition"
        }
        
        st.dataframe(reports.get(report_map[report_choice], pd.DataFrame()), use_container_width=True)

"🔍 Business Health Check"
    
st.subheader("🔍 Comprehensive Business Health Check")
st.caption("Claude AI analyzes all your GA4 data to provide actionable insights")

col1, col2 = st.columns([1, 4])

with col1:
    if st.button("▶️ Run Analysis", type="primary", use_container_width=True):
        st.session_state.business_check_done = True
        with st.spinner("🤖 Claude is analyzing your business data..."):
            try:
                result = business_health_check(reports, start_date, end_date)
                st.session_state.business_check_result = result
            except Exception as e:
                st.error(f"❌ Analysis failed: {str(e)}")
                st.session_state.business_check_done = False

# Display results
if st.session_state.business_check_done and st.session_state.business_check_result:
    st.markdown("---")
    st.markdown(st.session_state.business_check_result)
elif not st.session_state.business_check_done:
    
    # Show quick insights while waiting
    with st.container():
        st.info("💡 Quick Preview")
        try:
            insights = quick_insights(reports)
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown("**🎯 Key Insight**")
                st.write(insights.get("key_insight", "N/A"))
            with col2:
                st.markdown("**🚨 Critical Issue**")
                st.write(insights.get("critical_issue", "N/A"))
            with col3:
                st.markdown("**💡 Opportunity**")
                st.write(insights.get("opportunity", "N/A"))
        except:
            pass
    
    st.markdown("---")


# =====================================================================
# MODE 2: MULTI-AGENT ANALYSIS
# =====================================================================

"🤖 Multi-Agent Analysis"
    
st.subheader("🤖 Multi-Agent AI Discussion")
st.caption("AI agents (Analyst + Critic + Synthesizer) discuss your data using Groq Llama 3.1")

# Prepare payload for multi-agent system
traffic = reports.get("traffic_overview", pd.DataFrame())

traffic_payload = {
    "table_name": "traffic_overview",
    "description": "Comprehensive traffic data by source, medium, device, and country",
    "date_range": f"{start_date} → {end_date}",
    "row_count": len(traffic),
    "columns": list(traffic.columns),
    "sample_rows": traffic.head(30).to_dict(orient="records"),
    "summary": get_summary_statistics(reports)
}

if st.button("▶️ Run Multi-Agent Discussion", type="primary"):
    st.session_state.run_multiagent = True

if st.session_state.run_multiagent:
    ai_input = {
        "raw_tables": {
            "traffic": traffic_payload
        }
    }
    
    with st.spinner("🤖 AI agents are analyzing..."):
        try:
            ai_output = generate_ai_summary(ai_input)
            
            st.markdown("### 🧾 Final Summary (Synthesizer)")
            st.markdown(ai_output["synthesizer"])
            
            col1, col2 = st.columns(2)
            
            with col1:
                with st.expander("🧠 Analyst AI", expanded=False):
                    st.markdown(ai_output["analyst"])
            
            with col2:
                with st.expander("🧐 Critic AI", expanded=False):
                    st.markdown(ai_output["critic"])
        except Exception as e:
            st.error(f"❌ Multi-agent analysis failed: {str(e)}")

# Show data
with st.expander("📊 View Traffic Data"):
    st.dataframe(traffic, use_container_width=True)


# =====================================================================
# MODE 3: CHAT WITH DATA
# =====================================================================

    
st.subheader("💬 Chat with Your Analytics Data")
st.caption("Ask specific questions about your GA4 data")

# Display chat history
for message in st.session_state.chat_messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat input
if prompt := st.chat_input("Ask a question about your analytics data..."):
    
    # Add user message to chat
    st.session_state.chat_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Get Claude response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                response = chat_with_data(
                    reports=reports,
                    user_question=prompt,
                    conversation_history=st.session_state.chat_history,
                    start_date=start_date,
                    end_date=end_date
                )
                st.markdown(response)
                
                # Update history
                st.session_state.chat_messages.append({"role": "assistant", "content": response})
                st.session_state.chat_history.append({"role": "user", "content": prompt})
                st.session_state.chat_history.append({"role": "assistant", "content": response})
                
            except Exception as e:
                st.error(f"❌ Chat error: {str(e)}")

# Suggested questions
if len(st.session_state.chat_messages) == 0:
    st.markdown("### 💡 Try asking:")
    
    col1, col2 = st.columns(2)
    
    questions = [
        "Why is my paid advertising not converting?",
        "Which traffic source has the best ROI?",
        "How can I improve mobile conversions?",
        "What are my top performing landing pages?",
        "Which countries should I focus on?",
        "What's causing revenue decline?",
    ]
    
    for i, question in enumerate(questions):
        col = col1 if i % 2 == 0 else col2
        with col:
            if st.button(question, use_container_width=True, key=f"q_{i}"):
                st.session_state.chat_messages.append({
                    "role": "user", 
                    "content": question
                })
                st.rerun()

# Clear chat button
if len(st.session_state.chat_messages) > 0:
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("🗑️ Clear Chat"):
            st.session_state.chat_messages = []
            st.session_state.chat_history = []
            st.rerun()


# =====================================================================
# FOOTER
# =====================================================================

st.markdown("---")

col1, col2, col3 = st.columns(3)
with col1:
    st.caption("🔍 GA4 AI Analytics Platform")
with col2:
    st.caption(f"📊 {len(reports)} reports loaded")
with col3:
    st.caption("🤖 Powered by Claude & Anthropic")