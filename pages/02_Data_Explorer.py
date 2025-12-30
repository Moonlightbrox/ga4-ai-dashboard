import streamlit as st
import pandas as pd

from analytics.raw_reports import get_all_core_reports
from components.date_selector import get_date_range
from data.ga4_schema import GA4_DIMENSIONS, GA4_METRICS
from data.ga4_service import fetch_ga4_report
from data.preprocess import ga4_to_dataframe


st.set_page_config(
    page_title="GA4 Data Explorer",
    layout="wide",
    initial_sidebar_state="expanded",
)


if "basic_reports" not in st.session_state:
    st.session_state.basic_reports = {}

if "basic_reports_loaded" not in st.session_state:
    st.session_state.basic_reports_loaded = False

if "custom_report" not in st.session_state:
    st.session_state.custom_report = pd.DataFrame()

if "custom_report_error" not in st.session_state:
    st.session_state.custom_report_error = None


with st.sidebar:
    st.header("Data Setup")
    start_date, end_date = get_date_range()

    current_dates = f"{start_date}_{end_date}"
    if "last_dates" not in st.session_state:
        st.session_state.last_dates = current_dates
    elif st.session_state.last_dates != current_dates:
        st.session_state.last_dates = current_dates
        st.session_state.basic_reports_loaded = False
        st.session_state.basic_reports = {}
        st.session_state.custom_report = pd.DataFrame()
        st.session_state.custom_report_error = None

    st.markdown("---")
    if st.session_state.basic_reports_loaded:
        if st.button("Refresh basic reports"):
            st.session_state.basic_reports_loaded = False
            st.session_state.basic_reports = {}
            st.rerun()
    else:
        st.caption("Basic reports not loaded")


st.title("GA4 Data Explorer")
st.caption("Fetch standard GA4 reports and build custom reports without AI")


st.subheader("Basic Reports")
st.caption("Prebuilt reports from GA4 with CSV download")

if st.button("Load basic reports", type="primary"):
    with st.spinner("Fetching GA4 reports..."):
        try:
            st.session_state.basic_reports = get_all_core_reports(start_date, end_date)
            st.session_state.basic_reports_loaded = True
        except Exception as exc:
            st.error(f"Failed to load reports: {exc}")

basic_reports = st.session_state.basic_reports

if st.session_state.basic_reports_loaded:
    report_items = list(basic_reports.values())
    report_names = [item["name"] for item in report_items]
    report_label = st.selectbox("Select a report", report_names)
    report_info = next((item for item in report_items if item["name"] == report_label), None)

    if not report_info:
        st.info("Select a report to preview its data.")
    else:
        report_df = report_info.get("data", pd.DataFrame())
        if report_df.empty:
            st.info("No rows returned for this report.")
        else:
            st.dataframe(report_df, use_container_width=True)
            csv_data = report_df.to_csv(index=False)
            st.download_button(
                "Download CSV",
                csv_data,
                file_name=f"{report_info['id']}_{start_date}_to_{end_date}.csv",
                mime="text/csv",
            )

st.markdown("---")


st.subheader("Custom Report Builder")
st.caption("Choose metrics and dimensions from the curated GA4 list")

metric_options = sorted(GA4_METRICS)
dimension_options = sorted(GA4_DIMENSIONS)

default_metrics = [m for m in ["totalUsers", "sessions"] if m in metric_options]
default_dimensions = [d for d in ["date"] if d in dimension_options]

selected_metrics = st.multiselect(
    "Metrics",
    metric_options,
    default=default_metrics,
)

selected_dimensions = st.multiselect(
    "Dimensions",
    dimension_options,
    default=default_dimensions,
)

max_rows = st.number_input("Max rows to display", min_value=50, max_value=5000, value=500, step=50)

if st.button("Run custom report"):
    st.session_state.custom_report_error = None
    if not selected_metrics:
        st.session_state.custom_report_error = "Select at least one metric."
    else:
        with st.spinner("Fetching custom report..."):
            try:
                response = fetch_ga4_report(
                    start_date=start_date,
                    end_date=end_date,
                    metrics=selected_metrics,
                    dimensions=selected_dimensions,
                )
                st.session_state.custom_report = ga4_to_dataframe(response)
            except Exception as exc:
                st.session_state.custom_report = pd.DataFrame()
                st.session_state.custom_report_error = str(exc)

if st.session_state.custom_report_error:
    st.error(st.session_state.custom_report_error)

custom_df = st.session_state.custom_report
if not custom_df.empty:
    st.dataframe(custom_df.head(int(max_rows)), use_container_width=True)
    csv_data = custom_df.to_csv(index=False)
    st.download_button(
        "Download custom CSV",
        csv_data,
        file_name=f"custom_report_{start_date}_to_{end_date}.csv",
        mime="text/csv",
    )

st.markdown("---")

st.caption(
    "Note: some metric and dimension combinations are incompatible in GA4. "
    "If a request fails, adjust your selection and try again."
)
