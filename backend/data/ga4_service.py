# This module is the single entry point for running GA4 Data API queries.
# It validates inputs, builds GA4 request objects, and returns raw responses.

import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import List

from dotenv import load_dotenv

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.auth.credentials import Credentials
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
# This section loads configuration and prepares request context helpers.

ENV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(dotenv_path=ENV_PATH)                                          



_CURRENT_PROPERTY_ID = ContextVar("ga4_property_id", default=None)
_CURRENT_CREDENTIALS = ContextVar("ga4_credentials", default=None)


@contextmanager
def ga4_request_context(
    property_id: str | None = None,
    credentials: Credentials | None = None,
):
    token_property = _CURRENT_PROPERTY_ID.set(property_id)
    token_credentials = _CURRENT_CREDENTIALS.set(credentials)
    try:
        yield
    finally:
        _CURRENT_PROPERTY_ID.reset(token_property)
        _CURRENT_CREDENTIALS.reset(token_credentials)


def _build_client(credentials: Credentials | None = None) -> BetaAnalyticsDataClient:
    if credentials is None:
        return BetaAnalyticsDataClient()
    return BetaAnalyticsDataClient(credentials=credentials)


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
    property_id: str | None = None,                                           # Optional GA4 property override
    credentials: Credentials | None = None,                                  # Optional user credentials
):

    # ------------------------------------------------------------------
    # Safety checks
    # ------------------------------------------------------------------
    resolved_property_id = property_id or _CURRENT_PROPERTY_ID.get() 
    resolved_credentials = credentials or _CURRENT_CREDENTIALS.get()

    if not resolved_property_id:
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
        property=f"properties/{resolved_property_id}",                         # GA4 property to query
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
    client = _build_client(resolved_credentials)
    return client.run_report(request)                                        # Return GA4 RunReportResponse
