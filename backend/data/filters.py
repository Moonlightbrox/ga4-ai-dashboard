# This module provides helper builders for GA4 filter expressions.
# It keeps filter creation consistent and easy to reuse across reports.

from google.analytics.data_v1beta.types import Filter, FilterExpression


# This function builds a GA4 filter that matches a specific event name.
def event_name_filter(
    event_name: str,                                                       # Event name to match in GA4
) -> FilterExpression:
    return FilterExpression(                                                  # Return a GA4 filter expression object
        filter=Filter(
            field_name="eventName",                                          # Field to filter on in GA4
            string_filter=Filter.StringFilter(
                value=event_name,                                             # Event name to match exactly
                match_type=Filter.StringFilter.MatchType.EXACT,               # Use exact match for precision
            ),
        )
    )
