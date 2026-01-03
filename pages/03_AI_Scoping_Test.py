# This Streamlit page provides a scoped AI analysis workflow for GA4 data.
# It mirrors the main app flow with report selection, preview, and AI chat.

import streamlit as st

from ai.cloud import analyze_selected_reports, get_estimated_tokens
from analytics.raw_reports import get_all_core_reports
from components.date_selector import get_date_range
from components.format import format_dataframe_numbers, format_token_estimate
from data.ga4_schema import CORE_REPORT_DIMENSIONS, CORE_REPORT_METRICS
from data.ga4_service import fetch_ga4_report
from data.preprocess import ga4_to_dataframe


# ============================================================================
# Page Configuration
# ============================================================================
# This section sets the page title and layout for the test page.

st.set_page_config(
    page_title="Test Page",                                                  # Browser tab title
    layout="wide",                                                           # Use full-width layout
    initial_sidebar_state="expanded",                                       # Keep sidebar open by default
)


# ============================================================================
# Session State Initialization
# ============================================================================
# This section initializes UI state so selections persist across reruns.

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []                                      # Stores chat history shown in the UI

if "user_reports" not in st.session_state:
    st.session_state.user_reports = {}                                       # Stores user-created custom reports

if "custom_report_error" not in st.session_state:
    st.session_state.custom_report_error = None                              # Stores custom report error messages

if "custom_report_success" not in st.session_state:
    st.session_state.custom_report_success = None                            # Stores custom report success messages

if "core_reports_cache" not in st.session_state:
    st.session_state.core_reports_cache = {}                                 # Caches GA4 report data by date

if "core_reports_date_key" not in st.session_state:
    st.session_state.core_reports_date_key = None                            # Tracks date range for cache validity

if "reload_core_reports" not in st.session_state:
    st.session_state.reload_core_reports = False                             # Flags when GA4 data should refresh

st.title("AI Scoping Test")
st.caption("Prototype page for AI logic, report scoping, and user flow")
st.divider()

AI_BUTTON_REPORTS = {
    "traffic_quality_assessment": [
        "traffic_overview",
        "daily_trends",
        "device_performance",
    ],
    "conversion_funnel_leakage": [
        "ecommerce_funnel",
        "top_products",
    ],
    "landing_page_optimization": [
        "landing_pages",
        "device_performance",
    ],
}


# ============================================================================
# Report Selection Utilities
# ============================================================================
# This helper maps report ids to full report objects.

# This function retrieves report objects by their IDs.
def get_reports_for_ids(
    report_map: dict,                                                        # Mapping of report_id to report payload
    report_ids: list[str],                                                   # List of report ids to select
) -> list[dict]:
    selected = []                                                            # Accumulator for found reports
    for report_id in report_ids:
        report = report_map.get(report_id)                                   # Look up report by id
        if not report:
            continue                                                         # Skip missing reports
        selected.append(report)                                              # Add report to the selection
    return selected                                                          # Return the list of selected reports


# ============================================================================
# Cached Data Loaders
# ============================================================================
# These functions cache GA4 data to reduce repeated API calls.

# This function fetches all core reports with Streamlit caching.
@st.cache_data(show_spinner=False)
def load_core_reports_cached(
    start_date: str,                                                         # GA4 start date
    end_date: str,                                                           # GA4 end date
) -> dict[str, dict]:
    return get_all_core_reports(start_date, end_date)                        # Return cached core report registry


# This function fetches a custom GA4 report with Streamlit caching.
@st.cache_data(show_spinner=False)
def load_custom_report_cached(
    start_date: str,                                                         # GA4 start date
    end_date: str,                                                           # GA4 end date
    metrics: tuple[str, ...],                                                # Metric names for the custom report
    dimensions: tuple[str, ...],                                             # Dimension names for the custom report
):
    response = fetch_ga4_report(
        start_date=start_date,                                               # Date range start
        end_date=end_date,                                                   # Date range end
        metrics=list(metrics),                                               # Convert tuple to list for API call
        dimensions=list(dimensions),                                         # Convert tuple to list for API call
    )
    return ga4_to_dataframe(response)                                        # Return DataFrame built from GA4 response


# ============================================================================
# Layout Columns
# ============================================================================
# This section defines the two-column layout for chat and report selection.

col_chat, col_reports = st.columns([3, 2])                                   # Left: chat, Right: reports


# ============================================================================
# Sidebar Controls
# ============================================================================
# This section drives date range selection and coverage settings.

with st.sidebar:
    st.header("Date range")
    start_date, end_date = get_date_range()                                  # Get user-selected date range
    if st.button("Refresh data"):
        st.session_state.reload_core_reports = True                          # Trigger a GA4 data refresh
    st.divider()
    st.subheader("AI Data Coverage")
    coverage_options = list(range(10, 101, 10))                              # Coverage options from 10% to 100%
    selected_coverage = st.selectbox(
        "AI Data Coverage",                                                  # Label for the selector
        options=coverage_options,                                            # Available percentage options
        index=8,                                                             # Default to 90%
        key="ai_data_coverage",                                              # Store value in session state
        format_func=lambda value: f"{value}%",                               # Show percentage labels
        label_visibility="collapsed",                                       # Hide duplicate label in sidebar
    )


# ============================================================================
# Core Report Loading
# ============================================================================
# This section loads or refreshes GA4 data based on date selection.

date_key = f"{start_date}_{end_date}"                                        # Cache key for the selected date range
if st.session_state.core_reports_date_key != date_key:
    st.session_state.reload_core_reports = True                              # Flag refresh when dates change

core_reports = st.session_state.core_reports_cache                           # Load cached reports
if st.session_state.reload_core_reports or not core_reports:
    try:
        core_reports = load_core_reports_cached(start_date, end_date)         # Fetch reports from GA4
        st.session_state.core_reports_cache = core_reports                    # Update cache
        st.session_state.core_reports_date_key = date_key                     # Store cache key
        st.session_state.reload_core_reports = False                          # Clear refresh flag
    except Exception as exc:                                                  # Handle GA4 fetch failures gracefully
        core_reports = {}
        st.session_state.core_reports_cache = {}
        st.sidebar.error(f"Failed to load reports: {exc}")

combined_reports = {**core_reports, **st.session_state.user_reports}          # Merge core + user reports


# ============================================================================
# Report Selection Panel
# ============================================================================
# This section lets users select reports and preview data.

with col_reports:
    st.subheader("\U0001F4CA Reports")
    st.caption("Select reports to include in AI analysis")

    bulk_cols = st.columns(3)
    select_all = bulk_cols[0].button("Select all reports")                   # Select all available reports
    select_basic = bulk_cols[1].button("Select basic reports")               # Select core reports only
    select_user = bulk_cols[2].button("Select user reports")                 # Select only user-created reports

    user_group_options = ["All user reports"]                                # Default user group option
    if st.session_state.user_reports:
        user_group_options.extend(sorted({
            report.get("group")
            for report in st.session_state.user_reports.values()
            if report.get("group")
        }))
    selected_user_group = st.selectbox(
        "User report group",                                                 # Label for grouping selector
        options=user_group_options,                                          # Available group options
        key="user_report_group",                                             # Store selection in session state
    )

    if select_all:
        for report in combined_reports.values():
            st.session_state[f"report_{report['id']}"] = True                # Mark every report as selected

    if select_basic:
        for report in combined_reports.values():
            st.session_state[f"report_{report['id']}"] = False               # Clear all selections first
        for report in core_reports.values():
            st.session_state[f"report_{report['id']}"] = True                # Select only core reports

    if select_user:
        for report in combined_reports.values():
            st.session_state[f"report_{report['id']}"] = False               # Clear all selections first
        if not st.session_state.user_reports:
            st.info("No user reports available yet.")                        # Inform user when none exist
        else:
            matched_group = False                                            # Track if any reports match the group
            for report in st.session_state.user_reports.values():
                if selected_user_group == "All user reports" or report.get("group") == selected_user_group:
                    st.session_state[f"report_{report['id']}"] = True        # Select reports in the chosen group
                    matched_group = True
            if selected_user_group != "All user reports" and not matched_group:
                st.info("No reports found in that group.")

    selected_reports = []                                                     # List of selected report payloads
    ordered_reports = list(core_reports.values()) + list(st.session_state.user_reports.values())
    for report in ordered_reports:
        is_user_report = report["id"] in st.session_state.user_reports        # Check if report is user-created
        if is_user_report:
            checkbox_col, delete_col = st.columns([6, 1])
            with checkbox_col:
                checked = st.checkbox(
                    report["name"],                                          # Report display name
                    help=report["description"],                               # Tooltip description
                    key=f"report_{report['id']}",                             # Persist selection state
                )
            with delete_col:
                if st.button("\U0001F5D1", key=f"delete_{report['id']}", help="Delete report"):
                    st.session_state.user_reports.pop(report["id"], None)    # Remove custom report
                    st.session_state.pop(f"report_{report['id']}", None)     # Remove selection state
                    st.rerun()                                                # Refresh the UI
        else:
            checked = st.checkbox(
                report["name"],                                              # Report display name
                help=report["description"],                                   # Tooltip description
                key=f"report_{report['id']}",                                 # Persist selection state
            )

        if checked:
            selected_reports.append(report)                                  # Add report to selected list

    st.divider()

    if selected_reports:
        st.markdown("**Report Preview:**")
        preview_tabs = st.tabs([report["name"] for report in selected_reports])
        for tab, report in zip(preview_tabs, selected_reports):
            with tab:
                try:
                    preview_df = report.get("data")                           # Report DataFrame to preview
                    if preview_df is None:
                        st.info("No data available for this report.")        # Inform when no data exists
                    elif getattr(preview_df, "empty", False):
                        st.info("No rows returned for this report.")          # Inform when DataFrame is empty
                    else:
                        formatted_df = format_dataframe_numbers(preview_df)  # Apply UI-only number formatting
                        st.dataframe(formatted_df, use_container_width=True)
                except Exception as exc:                                      # Handle preview errors gracefully
                    st.warning(f"Unable to load this report: {exc}")
    else:
        st.info("Select a report to preview its data.")

    st.divider()

    with st.expander("Advanced: Custom Report Builder"):
        st.caption("Build custom reports using metrics and dimensions")

        metric_options = list(CORE_REPORT_METRICS.keys())                     # Available metric IDs
        dimension_options = list(CORE_REPORT_DIMENSIONS.keys())               # Available dimension IDs

        def metric_label(
            metric_id,                                                      # GA4 metric id to label
        ):
            meta = CORE_REPORT_METRICS[metric_id]                             # Metadata for the metric
            return f"{meta['label']} - {meta['description']} ({metric_id})"    # Build a friendly label

        def dimension_label(
            dimension_id,                                                   # GA4 dimension id to label
        ):
            meta = CORE_REPORT_DIMENSIONS[dimension_id]                       # Metadata for the dimension
            return f"{meta['label']} - {meta['description']} ({dimension_id})" # Build a friendly label

        selected_dimensions = st.multiselect(
            "Dimensions",                                                     # Dimensions dropdown label
            dimension_options,                                                # Available dimensions
            format_func=dimension_label,                                      # Friendly display labels
        )
        selected_metrics = st.multiselect(
            "Metrics",                                                        # Metrics dropdown label
            metric_options,                                                   # Available metrics
            format_func=metric_label,                                         # Friendly display labels
        )
        report_name = st.text_input("Report name (optional)")                 # Optional custom report name
        report_group = st.text_input("Report group (optional)")               # Optional group label

        if st.button("Create report"):
            st.session_state.custom_report_error = None                       # Clear prior errors
            st.session_state.custom_report_success = None                     # Clear prior success message

            if not selected_dimensions or not selected_metrics:
                st.session_state.custom_report_error = (
                    "Select at least one dimension and one metric."           # Validate required fields
                )
            else:
                try:
                    report_df = load_custom_report_cached(
                        start_date=start_date,                               # Date range start
                        end_date=end_date,                                   # Date range end
                        metrics=tuple(selected_metrics),                     # Metrics for this report
                        dimensions=tuple(selected_dimensions),               # Dimensions for this report
                    )

                    report_id = f"user_{len(st.session_state.user_reports) + 1}"
                    display_name = report_name.strip() if report_name else f"Custom Report {len(st.session_state.user_reports) + 1}"
                    group_name = report_group.strip() if report_group else None
                    description = (
                        f"Dimensions: {', '.join(selected_dimensions)} | "
                        f"Metrics: {', '.join(selected_metrics)}"
                    )

                    st.session_state.user_reports[report_id] = {
                        "id": report_id,
                        "name": display_name,
                        "description": description,
                        "group": group_name,
                        "data": report_df,
                    }
                    st.session_state.custom_report_success = "Custom report created."
                    st.rerun()
                except Exception:                                            # Handle invalid metric/dimension combos
                    st.session_state.custom_report_error = (
                        "The selected metrics and dimensions are not compatible. "
                        "Please try a different combination."
                    )

        if st.session_state.custom_report_error:
            st.error(st.session_state.custom_report_error)                    # Show error message
        if st.session_state.custom_report_success:
            st.success(st.session_state.custom_report_success)                # Show success message


# ============================================================================
# AI Analysis Panel
# ============================================================================
# This section handles the AI chat UI and prompt execution.

with col_chat:
    st.subheader("\U0001F4AC AI Analysis")
    st.caption("Ask questions about the selected reports")

    template_questions = [
        {
            "label": "Traffic Analysis",
            "prompt_key": "traffic_quality_assessment",
        },
        {
            "label": "Conversion Funnel Leakage",
            "prompt_key": "conversion_funnel_leakage",
        },
        {
            "label": "Landing Page Optimization",
            "prompt_key": "landing_page_optimization",
        },
    ]

    template_cols = st.columns(len(template_questions))
    clicked_template = None                                                   # Stores the selected template button
    for idx, question in enumerate(template_questions):
        with template_cols[idx]:
            required_report_ids = AI_BUTTON_REPORTS.get(question["prompt_key"], [])
            required_reports = get_reports_for_ids(combined_reports, required_report_ids)
            estimated_tokens = get_estimated_tokens(
                selected_reports=required_reports,                            # Reports required for this template
                user_question=question["label"],                              # Label used for prompt
                prompt_key=question["prompt_key"],                            # Template key
            )
            display_tokens = int(estimated_tokens * (selected_coverage / 100))
            button_label = f"{question['label']}  {format_token_estimate(display_tokens)}"
            if st.button(button_label, key=f"template_{idx}"):
                clicked_template = question                                  # Store clicked template

    for message in st.session_state.chat_messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])                                     # Render each prior message

    input_col, cost_col, clear_col = st.columns([6, 1, 1])
    with input_col:
        user_input = st.chat_input("Ask a question about your data", key="scoping_chat_prompt")
    chat_prompt_preview = st.session_state.get("scoping_chat_prompt", "")    # Live input value for token estimate
    chat_estimated_tokens = get_estimated_tokens(
        selected_reports=selected_reports,                                    # Selected reports for the ad-hoc prompt
        user_question=chat_prompt_preview,                                    # Current input text
        prompt_key=None,                                                      # No template when typing freely
    )
    chat_display_tokens = int(chat_estimated_tokens * (selected_coverage / 100))
    with cost_col:
        st.markdown(
            f"<div style='text-align: right;'>{format_token_estimate(chat_display_tokens)}</div>",
            unsafe_allow_html=True,                                           # Allow inline HTML for alignment
        )
    with clear_col:
        if st.button("\U0001F5D1", help="Clear chat"):
            st.session_state.chat_messages = []                               # Clear chat history
            st.rerun()

    prompt_key = None                                                         # Track prompt template key
    required_reports = []                                                     # Reports required by template
    if clicked_template:
        user_input = clicked_template["label"]                               # Use template label as the question
        prompt_key = clicked_template["prompt_key"]                           # Set template key
        required_report_ids = AI_BUTTON_REPORTS.get(prompt_key, [])
        required_reports = get_reports_for_ids(combined_reports, required_report_ids)

    if user_input:
        if not prompt_key and not selected_reports:
            st.warning("Please select at least one report to continue.")      # Require report selection for free-form prompts
        else:
            report_payload = required_reports if prompt_key else selected_reports
            st.session_state.chat_messages.append({
                "role": "user",
                "content": user_input,
            })

            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    response_text = analyze_selected_reports(
                        selected_reports=report_payload,                      # Reports included in the AI prompt
                        user_question=user_input,                             # User's question or template label
                        prompt_key=prompt_key,                                # Template key (if any)
                        coverage_pct=selected_coverage,                       # Coverage percentage from sidebar
                    )

                    st.write(response_text)
                    st.session_state.chat_messages.append({
                        "role": "assistant",
                        "content": response_text,
                    })
