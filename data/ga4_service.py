# This module is the single entry point for running GA4 Data API queries.
# It validates inputs, builds GA4 request objects, and returns raw responses.

import os
from typing import List

from dotenv import load_dotenv

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Metric,
    RunReportRequest,
    FilterExpression,
)


# ============================================================================
# Environment and Client Setup
# ============================================================================
# This section loads configuration and creates the GA4 API client once.

load_dotenv()                                                                # Load environment variables from .env

PROPERTY_ID = os.getenv("GA_PROPERTY_ID")                                   # GA4 property ID (numbers only)

_client = BetaAnalyticsDataClient()                                          # Reusable GA4 API client


# ============================================================================
# Core GA4 Data Fetch Function
# ============================================================================
# This function builds and executes a GA4 RunReportRequest.

# This function fetches a raw GA4 report response for given metrics/dimensions.
def fetch_ga4_report(
    start_date: str,                                                          # GA4-compatible start date
    end_date: str,                                                            # GA4-compatible end date
    metrics: List[str] | None = None,                                         # GA4 metric names to request
    dimensions: List[str] | None = None,                                      # GA4 dimension names to request
    dimension_filter: FilterExpression | None = None,                         # Optional GA4 dimension filter
):

    # ------------------------------------------------------------------
    # Safety checks
    # ------------------------------------------------------------------
    if not PROPERTY_ID:
        raise ValueError("GA_PROPERTY_ID is not set in environment variables")

    if not metrics:
        raise ValueError("Explicit GA4 metrics must be provided")

    # ------------------------------------------------------------------
    # Build GA4 Metric objects
    # ------------------------------------------------------------------
    ga4_metrics = [
        Metric(name=m)                                                       # Create metric objects for GA4 API
        for m in metrics
    ]

    # ------------------------------------------------------------------
    # Build GA4 Dimension objects
    # ------------------------------------------------------------------
    ga4_dimensions = [
        Dimension(name=d)                                                    # Create dimension objects for GA4 API
        for d in dimensions
    ] if dimensions else []

    # ------------------------------------------------------------------
    # Build GA4 API request
    # ------------------------------------------------------------------
    request = RunReportRequest(
        property=f"properties/{PROPERTY_ID}",                                 # GA4 property to query
        date_ranges=[
            DateRange(
                start_date=start_date,                                       # Start of query window
                end_date=end_date,                                           # End of query window
            )
        ],
        metrics=ga4_metrics,                                                 # Explicit metrics
        dimensions=ga4_dimensions,                                           # Explicit dimensions
        dimension_filter=dimension_filter,                                   # Optional dimension filter
        limit=100_000,                                                       # Safety limit to cap row counts
    )

    # ------------------------------------------------------------------
    # Execute request and return raw response
    # ------------------------------------------------------------------
    return _client.run_report(request)                                       # Return GA4 RunReportResponse
