""" ga4_service.py
=====================================================================
PURPOSE
=====================================================================

This module is the SINGLE ENTRY POINT for executing GA4 Data API queries.

It is responsible ONLY for:
- Executing GA4 API requests
- Validating required inputs
- Converting metric & dimension names into GA4 API objects

---------------------------------------------------------------------
WHAT THIS FILE IS RESPONSIBLE FOR
---------------------------------------------------------------------
✔ Executing GA4 API calls
✔ Enforcing explicit metrics & dimensions
✔ Returning RAW GA4 responses

---------------------------------------------------------------------
WHAT THIS FILE IS *NOT* RESPONSIBLE FOR
---------------------------------------------------------------------
✘ Defining metrics or dimensions
✘ Calculating KPIs or ratios
✘ Aggregating or transforming data
✘ Business logic or interpretation
✘ AI prompting or reasoning

---------------------------------------------------------------------
MENTAL MODEL
---------------------------------------------------------------------
Think of this file as:

    "The GA4 query executor"

It answers ONE question:

    “Given explicit GA4 fields, fetch the raw data safely.”
"""

import os
from typing import List

from dotenv import load_dotenv

from google.analytics.data_v1beta import BetaAnalyticsDataClient  
from google.analytics.data_v1beta.types import (DateRange, Dimension, Metric, RunReportRequest, FilterExpression,)


# =====================================================================
# ENVIRONMENT & CLIENT INITIALIZATION
# =====================================================================

# Load environment variables (.env)
load_dotenv()

# GA4 Property ID (numbers only)
PROPERTY_ID = os.getenv("GA_PROPERTY_ID")

# Single reusable GA4 API client
_client = BetaAnalyticsDataClient()


# =====================================================================
# CORE GA4 DATA FETCH FUNCTION
# =====================================================================

""" fetch_ga4_report
Execute a RAW GA4 Data API request.

PARAMETERS
----------
start_date : str
    GA4-compatible start date.
    Examples:
        "30daysAgo"
        "today"
        "2024-01-01"

end_date : str
    GA4-compatible end date.

metrics : List[str]
    EXPLICIT GA4 metric names.
    These define WHAT is measured.
    Example:
        ["activeUsers", "sessions", "purchaseRevenue"]

dimensions : List[str] | None
    EXPLICIT GA4 dimension names.
    These define HOW data is broken down.
    Example:
        ["date", "country", "deviceCategory"]

metric_groups : List[str] | None
    SEMANTIC metadata ONLY.
    Used for:
        - logging
        - AI context
        - debugging
    NOT sent to GA4.

dimension_groups : List[str] | None
    SEMANTIC metadata ONLY.
    Used for:
        - documentation
        - AI reasoning
    NOT sent to GA4.

RETURNS
-------
RunReportResponse
    Raw GA4 API response.

DESIGN RULES
------------
✔ GA4 execution uses ONLY explicit metrics & dimensions
✔ Semantic groups are metadata only

✘ No calculations
✘ No aggregation
✘ No interpretation
✘ No AI logic
"""

def fetch_ga4_report(
    start_date: str,
    end_date: str,

    # Technical GA4 fields (USED by GA4)
    metrics: List[str] | None = None,
    dimensions: List[str] | None = None,
    dimension_filter: FilterExpression | None = None,
):

    # --------------------------------------------------
    # Safety checks
    # --------------------------------------------------
    if not PROPERTY_ID:
        raise ValueError("GA_PROPERTY_ID is not set in environment variables")

    if not metrics:
        raise ValueError("Explicit GA4 metrics must be provided")

    # --------------------------------------------------
    # Build GA4 Metric objects
    # --------------------------------------------------
    ga4_metrics = [
        Metric(name=m)                 # WHAT is being measured
        for m in metrics
    ]

    # --------------------------------------------------
    # Build GA4 Dimension objects
    # --------------------------------------------------
    ga4_dimensions = [
        Dimension(name=d)              # HOW data is broken down
        for d in dimensions
    ] if dimensions else []

    # --------------------------------------------------
    # Build GA4 API request
    # --------------------------------------------------
    request = RunReportRequest(
        property=f"properties/{PROPERTY_ID}",                 # GA4 property
        date_ranges=[
            DateRange(
                start_date=start_date,
                end_date=end_date,
            )
        ],
        metrics=ga4_metrics,                                   # Explicit metrics
        dimensions=ga4_dimensions,                             # Explicit dimensions
        dimension_filter=dimension_filter,                     # Optional filters
        limit=100_000,                                         # Safety limit
    )

    # --------------------------------------------------
    # Execute request and return RAW response
    # --------------------------------------------------
    return _client.run_report(request)
