# This module provides a Streamlit date range selector for GA4 queries.
# It converts user-friendly choices into GA4-compatible date strings.

import streamlit as st # type: ignore
from datetime import date, timedelta


# This function returns a GA4-friendly start and end date based on UI input.
def get_date_range():
    option = st.selectbox(
        "Date range",                                                       # Label shown to the user
        ["Last 7 days", "Last 30 days", "Custom range"],                # Preset and custom options
        index=1                                                              # Default to "Last 30 days"
    )

    today = date.today()                                                     # Current date used for defaults

    if option == "Last 7 days":
        return "7daysAgo", "today"                                        # Return GA4-relative dates

    if option == "Last 30 days":
        return "30daysAgo", "today"                                       # Return GA4-relative dates

    start, end = st.date_input(
        "Select date range",                                                # Label for the custom picker
        value=(today - timedelta(days=30), today),                           # Default to last 30 days
        max_value=today                                                      # Prevent future dates
    )

    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")            # Return explicit ISO dates
