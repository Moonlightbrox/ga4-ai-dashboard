from google.analytics.data_v1beta.types import Filter, FilterExpression

def event_name_filter(event_name: str) -> FilterExpression:
    return FilterExpression(
        filter=Filter(
            field_name="eventName",
            string_filter=Filter.StringFilter(
                value=event_name,
                match_type=Filter.StringFilter.MatchType.EXACT,
            ),
        )
    )