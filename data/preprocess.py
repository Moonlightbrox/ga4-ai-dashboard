# This module converts raw GA4 API responses into pandas DataFrames.
# It performs light normalization so downstream code can work with clean tables.

import pandas as pd
from google.analytics.data_v1beta import RunReportResponse


# ============================================================================
# GA4 Response to DataFrame
# ============================================================================
# This function turns GA4 API rows into a tabular DataFrame.

# This function converts a GA4 RunReportResponse into a DataFrame.
def ga4_to_dataframe(
    response: RunReportResponse,                                            # Raw GA4 API response
) -> pd.DataFrame:

    # If GA4 returned no rows, return an empty DataFrame
    if not response.rows:
        return pd.DataFrame()                                                # Return empty table when no data is present

    dim_names = [d.name for d in response.dimension_headers]                 # Dimension column names
    metric_names = [m.name for m in response.metric_headers]                 # Metric column names

    rows = []                                                                # List of row dictionaries to build the DataFrame

    for row in response.rows:
        entry = {}                                                           # One row of data

        for i, dim in enumerate(row.dimension_values):
            entry[dim_names[i]] = dim.value                                  # Map dimension values to column names

        for i, met in enumerate(row.metric_values):
            try:
                entry[metric_names[i]] = float(met.value)                    # Parse numeric metrics as floats
            except ValueError:                                               # Handle metrics that are not numeric
                entry[metric_names[i]] = met.value                           # Store raw value when float conversion fails

        rows.append(entry)                                                   # Add row to the list

    df = pd.DataFrame(rows)                                                  # Build DataFrame from row list

    if "date" in df.columns:
        df["date"] = pd.to_datetime(
            df["date"],                                                     # Raw GA4 date string
            format="%Y%m%d",                                                # GA4 date format
            errors="coerce",                                               # Convert invalid dates to NaT
        )

    return df                                                                # Return the normalized DataFrame
