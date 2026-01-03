
import streamlit as st

from ai.cloud import analyze_selected_reports, get_estimated_tokens
from analytics.raw_reports import get_all_core_reports
from components.date_selector import get_date_range
from components.format import format_dataframe_numbers, format_token_estimate
from data.ga4_schema import CORE_REPORT_DIMENSIONS, CORE_REPORT_METRICS
from data.ga4_service import fetch_ga4_report
from data.preprocess import ga4_to_dataframe


st.set_page_config(
    page_title="Test Page",
    layout="wide",
    initial_sidebar_state="expanded",
)



if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

if "user_reports" not in st.session_state:
    st.session_state.user_reports = {}

if "custom_report_error" not in st.session_state:
    st.session_state.custom_report_error = None

if "custom_report_success" not in st.session_state:
    st.session_state.custom_report_success = None

if "core_reports_cache" not in st.session_state:
    st.session_state.core_reports_cache = {}

if "core_reports_date_key" not in st.session_state:
    st.session_state.core_reports_date_key = None

if "reload_core_reports" not in st.session_state:
    st.session_state.reload_core_reports = False

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

def get_reports_for_ids(report_map: dict, report_ids: list[str]) -> list[dict]:
    selected = []
    for report_id in report_ids:
        report = report_map.get(report_id)
        if not report:
            continue
        selected.append(report)
    return selected


@st.cache_data(show_spinner=False)
def load_core_reports_cached(start_date: str, end_date: str) -> dict[str, dict]:
    return get_all_core_reports(start_date, end_date)


@st.cache_data(show_spinner=False)
def load_custom_report_cached(
    start_date: str,
    end_date: str,
    metrics: tuple[str, ...],
    dimensions: tuple[str, ...],
):
    response = fetch_ga4_report(
        start_date=start_date,
        end_date=end_date,
        metrics=list(metrics),
        dimensions=list(dimensions),
    )
    return ga4_to_dataframe(response)


col_chat, col_reports = st.columns([3, 2])

with st.sidebar:
    st.header("Date range")
    start_date, end_date = get_date_range()
    if st.button("Refresh data"):
        st.session_state.reload_core_reports = True
    st.divider()
    st.subheader("AI Data Coverage")
    coverage_options = list(range(10, 101, 10))
    selected_coverage = st.selectbox(
        "AI Data Coverage",
        options=coverage_options,
        index=8,
        key="ai_data_coverage",
        format_func=lambda value: f"{value}%",
        label_visibility="collapsed",
    )

date_key = f"{start_date}_{end_date}"
if st.session_state.core_reports_date_key != date_key:
    st.session_state.reload_core_reports = True

core_reports = st.session_state.core_reports_cache
if st.session_state.reload_core_reports or not core_reports:
    try:
        # Cache reports by date to avoid redundant GA4 fetches on UI-only reruns.
        core_reports = load_core_reports_cached(start_date, end_date)
        st.session_state.core_reports_cache = core_reports
        st.session_state.core_reports_date_key = date_key
        st.session_state.reload_core_reports = False
    except Exception as exc:
        core_reports = {}
        st.session_state.core_reports_cache = {}
        st.sidebar.error(f"Failed to load reports: {exc}")

combined_reports = {**core_reports, **st.session_state.user_reports}

with col_reports:
    st.subheader("\U0001F4CA Reports")
    st.caption("Select reports to include in AI analysis")

    bulk_cols = st.columns(3)
    select_all = bulk_cols[0].button("Select all reports")
    select_basic = bulk_cols[1].button("Select basic reports")
    select_user = bulk_cols[2].button("Select user reports")

    user_group_options = ["All user reports"]
    if st.session_state.user_reports:
        user_group_options.extend(sorted({
            report.get("group")
            for report in st.session_state.user_reports.values()
            if report.get("group")
        }))
    selected_user_group = st.selectbox(
        "User report group",
        options=user_group_options,
        key="user_report_group",
    )

    if select_all:
        for report in combined_reports.values():
            st.session_state[f"report_{report['id']}"] = True

    if select_basic:
        for report in combined_reports.values():
            st.session_state[f"report_{report['id']}"] = False
        for report in core_reports.values():
            st.session_state[f"report_{report['id']}"] = True

    if select_user:
        for report in combined_reports.values():
            st.session_state[f"report_{report['id']}"] = False
        if not st.session_state.user_reports:
            st.info("No user reports available yet.")
        else:
            matched_group = False
            for report in st.session_state.user_reports.values():
                if selected_user_group == "All user reports" or report.get("group") == selected_user_group:
                    st.session_state[f"report_{report['id']}"] = True
                    matched_group = True
            if selected_user_group != "All user reports" and not matched_group:
                st.info("No reports found in that group.")

    selected_reports = []
    ordered_reports = list(core_reports.values()) + list(st.session_state.user_reports.values())
    for report in ordered_reports:
        is_user_report = report["id"] in st.session_state.user_reports
        if is_user_report:
            checkbox_col, delete_col = st.columns([6, 1])
            with checkbox_col:
                checked = st.checkbox(
                    report["name"],
                    help=report["description"],
                    key=f"report_{report['id']}",
                )
            with delete_col:
                if st.button("\U0001F5D1", key=f"delete_{report['id']}", help="Delete report"):
                    st.session_state.user_reports.pop(report["id"], None)
                    st.session_state.pop(f"report_{report['id']}", None)
                    st.rerun()
        else:
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

    with st.expander("Advanced: Custom Report Builder"):
        st.caption("Build custom reports using metrics and dimensions")

        metric_options = list(CORE_REPORT_METRICS.keys())
        dimension_options = list(CORE_REPORT_DIMENSIONS.keys())

        def metric_label(metric_id):
            meta = CORE_REPORT_METRICS[metric_id]
            return f"{meta['label']} - {meta['description']} ({metric_id})"

        def dimension_label(dimension_id):
            meta = CORE_REPORT_DIMENSIONS[dimension_id]
            return f"{meta['label']} - {meta['description']} ({dimension_id})"

        selected_dimensions = st.multiselect(
            "Dimensions",
            dimension_options,
            format_func=dimension_label,
        )
        selected_metrics = st.multiselect(
            "Metrics",
            metric_options,
            format_func=metric_label,
        )
        report_name = st.text_input("Report name (optional)")
        report_group = st.text_input("Report group (optional)")

        if st.button("Create report"):
            st.session_state.custom_report_error = None
            st.session_state.custom_report_success = None

            if not selected_dimensions or not selected_metrics:
                st.session_state.custom_report_error = (
                    "Select at least one dimension and one metric."
                )
            else:
                try:
                    # Cache custom report fetches by date, metrics, and dimensions.
                    report_df = load_custom_report_cached(
                        start_date=start_date,
                        end_date=end_date,
                        metrics=tuple(selected_metrics),
                        dimensions=tuple(selected_dimensions),
                    )

                    report_id = f"user_{len(st.session_state.user_reports) + 1}"
                    display_name = report_name.strip() if report_name else f"Custom Report {len(st.session_state.user_reports) + 1}"
                    group_name = report_group.strip() if report_group else None
                    description = (
                        f"Dimensions: {', '.join(selected_dimensions)} | "
                        f"Metrics: {', '.join(selected_metrics)}"
                    )

                    # User-defined report (Phase 2).
                    st.session_state.user_reports[report_id] = {
                        "id": report_id,
                        "name": display_name,
                        "description": description,
                        "group": group_name,
                        "data": report_df,
                    }
                    st.session_state.custom_report_success = "Custom report created."
                    st.rerun()
                except Exception:
                    st.session_state.custom_report_error = (
                        "The selected metrics and dimensions are not compatible. "
                        "Please try a different combination."
                    )

        if st.session_state.custom_report_error:
            st.error(st.session_state.custom_report_error)
        if st.session_state.custom_report_success:
            st.success(st.session_state.custom_report_success)


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
    clicked_template = None
    for idx, question in enumerate(template_questions):
        with template_cols[idx]:
            required_report_ids = AI_BUTTON_REPORTS.get(question["prompt_key"], [])
            required_reports = get_reports_for_ids(combined_reports, required_report_ids)
            estimated_tokens = get_estimated_tokens(
                selected_reports=required_reports,
                user_question=question["label"],
                prompt_key=question["prompt_key"],
            )
            display_tokens = int(estimated_tokens * (selected_coverage / 100))
            button_label = f"{question['label']}  {format_token_estimate(display_tokens)}"
            if st.button(button_label, key=f"template_{idx}"):
                clicked_template = question

    for message in st.session_state.chat_messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    input_col, cost_col, clear_col = st.columns([6, 1, 1])
    with input_col:
        user_input = st.chat_input("Ask a question about your data", key="scoping_chat_prompt")
    chat_prompt_preview = st.session_state.get("scoping_chat_prompt", "")
    chat_estimated_tokens = get_estimated_tokens(
        selected_reports=selected_reports,
        user_question=chat_prompt_preview,
        prompt_key=None,
    )
    chat_display_tokens = int(chat_estimated_tokens * (selected_coverage / 100))
    with cost_col:
        st.markdown(
            f"<div style='text-align: right;'>{format_token_estimate(chat_display_tokens)}</div>",
            unsafe_allow_html=True,
        )
    with clear_col:
        if st.button("\U0001F5D1", help="Clear chat"):
            st.session_state.chat_messages = []
            st.rerun()

    prompt_key = None
    required_reports = []
    if clicked_template:
        user_input = clicked_template["label"]
        prompt_key = clicked_template["prompt_key"]
        required_report_ids = AI_BUTTON_REPORTS.get(prompt_key, [])
        required_reports = get_reports_for_ids(combined_reports, required_report_ids)

    if user_input:
        if not prompt_key and not selected_reports:
            st.warning("Please select at least one report to continue.")
        else:
            report_payload = required_reports if prompt_key else selected_reports
            st.session_state.chat_messages.append({
                "role": "user",
                "content": user_input,
            })

            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    response_text = analyze_selected_reports(
                        selected_reports=report_payload,
                        user_question=user_input,
                        prompt_key=prompt_key,
                    )

                    st.write(response_text)
                    st.session_state.chat_messages.append({
                        "role": "assistant",
                        "content": response_text,
                    })












