import streamlit as st # type: ignore
from datetime import date, timedelta


def get_date_range():
    option = st.selectbox(
        "Date range",
        ["Last 7 days", "Last 30 days", "Custom range"],
        index=1
    )

    today = date.today()

    if option == "Last 7 days":
        return "7daysAgo", "today"

    if option == "Last 30 days":
        return "30daysAgo", "today"

    start, end = st.date_input(
        "Select date range",
        value=(today - timedelta(days=30), today),
        max_value=today
    )

    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
