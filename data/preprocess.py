""" preprocess.py
=====================================================================
PURPOSE
=====================================================================

This module converts raw GA4 API responses into a neutral tabular format.

It acts as a thin normalization layer between:
- the GA4 Data API (structured response objects)
- analytics, KPI, statement, and AI layers (DataFrames)

---------------------------------------------------------------------
WHAT THIS FILE IS RESPONSIBLE FOR
---------------------------------------------------------------------
✔ Converting GA4 responses to pandas DataFrames
✔ Preserving all returned dimensions and metrics
✔ Performing light technical normalization (types, dates)

---------------------------------------------------------------------
WHAT THIS FILE IS *NOT* RESPONSIBLE FOR
---------------------------------------------------------------------
✘ Calculating KPIs
✘ Comparing time periods
✘ Aggregating or summarizing data
✘ Assigning business meaning
✘ Preparing AI prompts

---------------------------------------------------------------------
MENTAL MODEL
---------------------------------------------------------------------
Think of this file as:

    "GA4 response → clean table"

Nothing more, nothing less.
"""

import pandas as pd
from google.analytics.data_v1beta import RunReportResponse  


# =====================================================================
# GA4 RESPONSE → DATAFRAME
# =====================================================================

""" ga4_to_dataframe
Convert a GA4 RunReportResponse into a pandas DataFrame.

PARAMETERS
----------
response : RunReportResponse
    Raw response returned by the GA4 Data API.

RETURNS
-------
pd.DataFrame
    Tabular representation where:
    - each row is one GA4 result row
    - each column is a metric or dimension
"""

def ga4_to_dataframe(response: RunReportResponse) -> pd.DataFrame:

    # If GA4 returned no rows, return an empty DataFrame
    if not response.rows:
        return pd.DataFrame()

    # Extract dimension and metric names from response headers
    dim_names = [d.name for d in response.dimension_headers]      # Column names for dimensions
    metric_names = [m.name for m in response.metric_headers]      # Column names for metrics

    rows = []

    # Iterate through each row returned by GA4
    for row in response.rows:
        entry = {}

        # Map dimension values to their corresponding column names
        for i, dim in enumerate(row.dimension_values):
            entry[dim_names[i]] = dim.value

        # Map metric values to their corresponding column names
        for i, met in enumerate(row.metric_values):
            try:
                entry[metric_names[i]] = float(met.value)          # Metrics are usually numeric
            except ValueError:
                entry[metric_names[i]] = met.value                 # Fallback for unexpected values

        rows.append(entry)

    # Convert list of row dictionaries into a DataFrame
    df = pd.DataFrame(rows)

    # Normalize GA4 date dimension into datetime (if present)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(
            df["date"],
            format="%Y%m%d",                                       # GA4 date format
            errors="coerce",
        )

    return df
