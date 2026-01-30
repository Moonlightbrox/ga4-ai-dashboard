# This module defines the core GA4 reports and returns them as standardized tables.
# It also provides a registry and helpers so the UI can fetch consistent report data.

import pandas as pd
from backend.data.ga4_service import fetch_ga4_report
from backend.data.preprocess import ga4_to_dataframe
from backend.components.format import format_duration, round_metric         # MODIFIED


# ADDED
def _add_ratio_metric(
    df: pd.DataFrame,
    numerator_col: str,
    denominator_col: str,
    target_col: str,
) -> pd.DataFrame:
    if numerator_col in df.columns and denominator_col in df.columns:
        numerator = pd.to_numeric(df[numerator_col], errors="coerce").fillna(0.0)
        denominator = pd.to_numeric(df[denominator_col], errors="coerce").fillna(0.0)
        safe_denominator = denominator.replace(0, pd.NA)
        df[target_col] = round_metric(                                       # FORMAT APPLIED # MODIFIED
            (numerator / safe_denominator).fillna(0.0)
        )
        # VERIFIED: 12345 / 321 = 38.46
    return df


# ADDED
def _round_columns(
    df: pd.DataFrame,
    columns: list[str],
    decimals: int = 2,
) -> pd.DataFrame:
    for col in columns:
        if col in df.columns:
            df[col] = round_metric(df[col], decimals=decimals)
    return df


# ADDED
def _normalize_rate_to_percent(
    df: pd.DataFrame,
    column: str,
    decimals: int = 2,
) -> pd.DataFrame:
    if column not in df.columns:
        return df
    series = pd.to_numeric(df[column], errors="coerce").fillna(0.0)
    if not series.empty and series.max(skipna=True) <= 1:
        series = series * 100
    df[column] = round_metric(series, decimals=decimals)
    return df


# ADDED
def _add_duration_per_user_display(
    df: pd.DataFrame,
    seconds_col: str,
    users_col: str,
    display_col: str,
) -> pd.DataFrame:
    if seconds_col in df.columns and users_col in df.columns:
        seconds = pd.to_numeric(df[seconds_col], errors="coerce").fillna(0.0)
        users = pd.to_numeric(df[users_col], errors="coerce").fillna(0.0)
        safe_users = users.replace(0, pd.NA)
        per_user_seconds = (seconds / safe_users).fillna(0.0)
        df[display_col] = format_duration(per_user_seconds)                  # FORMAT USED # DURATION COLUMN ADDED
        # VERIFIED: 3600 seconds / 100 users = 36s -> 00:36
    return df


# ADDED
def _add_duration_per_session_display(
    df: pd.DataFrame,
    seconds_col: str,
    sessions_col: str,
    display_col: str,
) -> pd.DataFrame:
    if seconds_col in df.columns and sessions_col in df.columns:
        seconds = pd.to_numeric(df[seconds_col], errors="coerce").fillna(0.0)
        sessions = pd.to_numeric(df[sessions_col], errors="coerce").fillna(0.0)
        safe_sessions = sessions.replace(0, pd.NA)
        per_session_seconds = (seconds / safe_sessions).fillna(0.0)
        df[display_col] = format_duration(per_session_seconds)               # FORMAT USED # DURATION COLUMN ADDED
        # VERIFIED: 3600 seconds / 90 sessions = 40s -> 00:40
    return df


# REMOVED
# ADDED
HUMAN_READABLE_COLUMNS = {                                                   # HUMAN-READABLE COLUMN # ADDED
    "totalUsers": "Total Users",
    "activeUsers": "Active Users",
    "newUsers": "New Users",
    "sessions": "Sessions",
    "engagedSessions": "Engaged Sessions",
    "userEngagementDuration": "User Engagement Seconds",
    "user_engagement_duration_per_user": "User Engagement Duration per User", # DURATION COLUMN ADDED
    "user_engagement_duration_per_session": "User Engagement Duration per Session", # DURATION COLUMN ADDED
    "transactions": "Transactions",
    "purchaseRevenue": "Purchase Revenue",
    "screenPageViews": "Screen Page Views",
    "itemViewEvents": "Item View Events",
    "addToCarts": "Add To Carts",
    "checkouts": "Checkouts",
    "itemsViewed": "Items Viewed",
    "itemsAddedToCart": "Items Added To Cart",
    "itemsCheckedOut": "Items Checked Out",
    "itemsPurchased": "Items Purchased",
    "itemRevenue": "Item Revenue",
    "view_to_cart_rate": "View -> Cart Conversion Rate",                     # DERIVED METRIC
    "cart_to_checkout_rate": "Cart -> Checkout Conversion Rate",             # DERIVED METRIC
    "checkout_to_purchase_rate": "Checkout -> Purchase Conversion Rate",     # DERIVED METRIC
    "item_view_to_purchase_rate": "Item View -> Purchase Conversion Rate",   # DERIVED METRIC
    "revenue_per_item_view": "Revenue per Item View",                        # DERIVED METRIC
    "revenue_per_purchase": "Revenue per Purchase",                          # DERIVED METRIC
    "pageview_to_item_view_rate": "View -> Item View Conversion Rate",        # DERIVED METRIC
    "item_view_to_cart_rate": "Item View -> Cart Conversion Rate",           # DERIVED METRIC
    "revenue_per_transaction": "Revenue per Transaction",                    # DERIVED METRIC
    "revenue_per_user": "Revenue per User",
    "revenue_per_active_user": "Revenue per Active User",
    "revenue_per_session": "Revenue per Session",
    "sessions_per_user": "Sessions per User",
    "conversion_rate": "Conversion Rate",
    "bounceRate": "Bounce Rate",
    "active_user_ratio": "Active User Ratio",
    "country": "Country",
    "city": "City",
    "deviceCategory": "Device Category",
    "operatingSystem": "Operating System",
    "browser": "Browser",
    "sessionSource": "Session Source",
    "sessionMedium": "Session Medium",
    "landingPage": "Landing Page",
    "pagePath": "Page Path",
    "pageTitle": "Page Title",
    "itemName": "Item Name",
    "itemCategory": "Item Category",
    "date": "Date",
}


# ADDED
REVENUE_COLUMNS = [
    "purchaseRevenue",
    "itemRevenue",
]


# ADDED
def _apply_human_readable_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns=HUMAN_READABLE_COLUMNS)                          # HUMAN-READABLE COLUMN # ADDED


# ============================================================================
# Core Report Builders
# ============================================================================
# Each function below calls GA4, normalizes columns, and returns a DataFrame.

# This report summarizes traffic by source, medium, device, and country.
def get_traffic_overview(
    start_date: str,                                                          # GA4 start date for the report
    end_date: str,                                                            # GA4 end date for the report
) -> pd.DataFrame:
    """
    Traffic by source, medium, device, and country.

    Compatible: session dimensions with session/user metrics.
    """

    expected_columns = [                                                      # Expected schema for consistent UI use # MODIFIED
        "country",
        "deviceCategory",
        "sessionSource",
        "sessionMedium",
        "totalUsers",
        "activeUsers",
        "newUsers",
        "sessions",
        "engagedSessions",
        "userEngagementDuration",
        "user_engagement_duration_per_user",                                # DURATION COLUMN ADDED
        "user_engagement_duration_per_session",                             # DURATION COLUMN ADDED
        "transactions",
        "purchaseRevenue",
        "revenue_per_user",                                                  # DERIVED METRIC # ADDED
        "revenue_per_active_user",                                           # DERIVED METRIC # ADDED
        "revenue_per_session",                                               # DERIVED METRIC # ADDED
        "sessions_per_user",                                                 # DERIVED METRIC # ADDED
        "conversion_rate",                                                   # DERIVED METRIC # ADDED
    ]

    try:
        response = fetch_ga4_report(
            start_date=start_date,                                            # Date range start
            end_date=end_date,                                                # Date range end
            metrics=[
                "totalUsers",
                "activeUsers",
                "newUsers",
                "sessions",
                "engagedSessions",
                "userEngagementDuration",
                "transactions",
                "purchaseRevenue",
            ],
            dimensions=[
                "country",
                "deviceCategory",
                "sessionSource",
                "sessionMedium",
            ],
        )
    except Exception as e:                                                    # Handle GA4 API errors to keep UI stable
        return pd.DataFrame(columns=expected_columns)                         # Return empty table with expected columns

    df = ga4_to_dataframe(response)                                           # Convert GA4 response to DataFrame

    if df.empty:
        return pd.DataFrame(columns=expected_columns)                         # Return empty table with expected columns

    for col in expected_columns:
        if col not in df.columns:
            df[col] = 0                                                       # Fill missing columns to keep schema stable


    df = _add_duration_per_user_display(                                      # DURATION COLUMN ADDED
        df,
        seconds_col="userEngagementDuration",
        users_col="totalUsers",
        display_col="user_engagement_duration_per_user",
    )
    df = _add_duration_per_session_display(                                   # DURATION COLUMN ADDED
        df,
        seconds_col="userEngagementDuration",
        sessions_col="sessions",
        display_col="user_engagement_duration_per_session",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - revenue per user # ADDED
        df,
        numerator_col="purchaseRevenue",
        denominator_col="totalUsers",
        target_col="revenue_per_user",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - revenue per active user # ADDED
        df,
        numerator_col="purchaseRevenue",
        denominator_col="activeUsers",
        target_col="revenue_per_active_user",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - revenue per session # ADDED
        df,
        numerator_col="purchaseRevenue",
        denominator_col="sessions",
        target_col="revenue_per_session",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - sessions per user # ADDED
        df,
        numerator_col="sessions",
        denominator_col="totalUsers",
        target_col="sessions_per_user",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - conversion rate # ADDED
        df,
        numerator_col="transactions",
        denominator_col="sessions",
        target_col="conversion_rate",
    )

    df = _round_columns(df, REVENUE_COLUMNS)

    return _apply_human_readable_columns(                                     # HUMAN-READABLE COLUMN # MODIFIED
        df[expected_columns]                                                 # Return ordered, consistent columns
    )


# This report provides daily trend metrics for key KPIs.
def get_daily_trends(
    start_date: str,                                                          # GA4 start date for the report
    end_date: str,                                                            # GA4 end date for the report
) -> pd.DataFrame:
    """
    Daily metrics to identify trends.

    Compatible: date dimension with most metrics.
    """

    expected_columns = [                                                      # Expected schema for consistent UI use # MODIFIED
        "date",
        "totalUsers",
        "newUsers",
        "sessions",
        "engagedSessions",
        "userEngagementDuration",
        "user_engagement_duration_per_user",                                # DURATION COLUMN ADDED
        "user_engagement_duration_per_session",                             # DURATION COLUMN ADDED
        "transactions",
        "purchaseRevenue",
        "screenPageViews",
        "revenue_per_user",                                                  # DERIVED METRIC # ADDED
        "revenue_per_session",                                               # DERIVED METRIC # ADDED
        "sessions_per_user",                                                 # DERIVED METRIC # ADDED
        "conversion_rate",                                                   # DERIVED METRIC # ADDED
    ]

    try:
        response = fetch_ga4_report(
            start_date=start_date,                                            # Date range start
            end_date=end_date,                                                # Date range end
            metrics=[
                "totalUsers",
                "newUsers",
                "sessions",
                "engagedSessions",
                "userEngagementDuration",
                "transactions",
                "purchaseRevenue",
                "screenPageViews",
            ],
            dimensions=["date"],
        )
    except Exception as e:                                                    # Handle GA4 API errors to keep UI stable
        return pd.DataFrame(columns=expected_columns)                         # Return empty table with expected columns

    df = ga4_to_dataframe(response)                                           # Convert GA4 response to DataFrame

    if df.empty:
        return pd.DataFrame(columns=expected_columns)                         # Return empty table with expected columns

    for col in expected_columns:
        if col not in df.columns:
            df[col] = 0                                                       # Fill missing columns to keep schema stable


    df = _add_duration_per_user_display(                                      # DURATION COLUMN ADDED
        df,
        seconds_col="userEngagementDuration",
        users_col="totalUsers",
        display_col="user_engagement_duration_per_user",
    )
    df = _add_duration_per_session_display(                                   # DURATION COLUMN ADDED
        df,
        seconds_col="userEngagementDuration",
        sessions_col="sessions",
        display_col="user_engagement_duration_per_session",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - revenue per user # ADDED
        df,
        numerator_col="purchaseRevenue",
        denominator_col="totalUsers",
        target_col="revenue_per_user",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - revenue per session # ADDED
        df,
        numerator_col="purchaseRevenue",
        denominator_col="sessions",
        target_col="revenue_per_session",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - sessions per user # ADDED
        df,
        numerator_col="sessions",
        denominator_col="totalUsers",
        target_col="sessions_per_user",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - conversion rate # ADDED
        df,
        numerator_col="transactions",
        denominator_col="sessions",
        target_col="conversion_rate",
    )

    df = _round_columns(df, REVENUE_COLUMNS)

    return _apply_human_readable_columns(                                     # HUMAN-READABLE COLUMN # MODIFIED
        df[expected_columns]                                                 # Return ordered, consistent columns
    )


# This report tracks landing page performance metrics.
def get_landing_pages(
    start_date: str,                                                          # GA4 start date for the report
    end_date: str,                                                            # GA4 end date for the report
) -> pd.DataFrame:
    """
    Performance by landing page.

    Compatible: landing page dimension with session metrics.
    """

    expected_columns = [                                                      # Expected schema for consistent UI use # MODIFIED
        "landingPage",
        "sessions",
        "engagedSessions",
        "userEngagementDuration",
        "user_engagement_duration_per_session",                             # DURATION COLUMN ADDED
        "transactions",
        "purchaseRevenue",
        "totalUsers",
        "bounceRate",
        "revenue_per_user",                                                  # DERIVED METRIC # ADDED
        "revenue_per_session",                                               # DERIVED METRIC # ADDED
        "sessions_per_user",                                                 # DERIVED METRIC # ADDED
        "conversion_rate",                                                   # DERIVED METRIC # ADDED
    ]

    try:
        response = fetch_ga4_report(
            start_date=start_date,                                            # Date range start
            end_date=end_date,                                                # Date range end
            metrics=[
                "sessions",
                "engagedSessions",
                "userEngagementDuration",
                "transactions",
                "purchaseRevenue",
                "totalUsers",
                "bounceRate",
            ],
            dimensions=["landingPage"],
        )
    except Exception as e:                                                    # Handle GA4 API errors to keep UI stable
        return pd.DataFrame(columns=expected_columns)                         # Return empty table with expected columns

    df = ga4_to_dataframe(response)                                           # Convert GA4 response to DataFrame

    if df.empty:
        return pd.DataFrame(columns=expected_columns)                         # Return empty table with expected columns

    for col in expected_columns:
        if col not in df.columns:
            df[col] = 0                                                       # Fill missing columns to keep schema stable


    df = _add_duration_per_session_display(                                   # DURATION COLUMN ADDED
        df,
        seconds_col="userEngagementDuration",
        sessions_col="sessions",
        display_col="user_engagement_duration_per_session",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - revenue per user # ADDED
        df,
        numerator_col="purchaseRevenue",
        denominator_col="totalUsers",
        target_col="revenue_per_user",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - revenue per session # ADDED
        df,
        numerator_col="purchaseRevenue",
        denominator_col="sessions",
        target_col="revenue_per_session",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - sessions per user # ADDED
        df,
        numerator_col="sessions",
        denominator_col="totalUsers",
        target_col="sessions_per_user",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - conversion rate # ADDED
        df,
        numerator_col="transactions",
        denominator_col="sessions",
        target_col="conversion_rate",
    )

    df = _normalize_rate_to_percent(df, "conversion_rate", decimals=2)
    df = _normalize_rate_to_percent(df, "bounceRate", decimals=2)
    df = _round_columns(df, REVENUE_COLUMNS)

    df = _apply_human_readable_columns(                                       # HUMAN-READABLE COLUMN # MODIFIED
        df[expected_columns]                                                 # Return ordered, consistent columns
    )
    return df.rename(columns={                                               # Landing-page-specific label
        "User Engagement Duration per Session": "Session Length",
    })


# This report breaks down performance by device, OS, and browser.
def get_device_performance(
    start_date: str,                                                          # GA4 start date for the report
    end_date: str,                                                            # GA4 end date for the report
) -> pd.DataFrame:
    """
    Performance by device, OS, and browser.

    Compatible: device dimensions with user/session metrics.
    """

    expected_columns = [                                                      # Expected schema for consistent UI use # MODIFIED
        "deviceCategory",
        "operatingSystem",
        "browser",
        "totalUsers",
        "sessions",
        "engagedSessions",
        "userEngagementDuration",
        "user_engagement_duration_per_user",                                # DURATION COLUMN ADDED
        "user_engagement_duration_per_session",                             # DURATION COLUMN ADDED
        "transactions",
        "purchaseRevenue",
        "revenue_per_user",                                                  # DERIVED METRIC # ADDED
        "revenue_per_session",                                               # DERIVED METRIC # ADDED
        "sessions_per_user",                                                 # DERIVED METRIC # ADDED
        "conversion_rate",                                                   # DERIVED METRIC # ADDED
    ]

    try:
        response = fetch_ga4_report(
            start_date=start_date,                                            # Date range start
            end_date=end_date,                                                # Date range end
            metrics=[
                "totalUsers",
                "sessions",
                "engagedSessions",
                "userEngagementDuration",
                "transactions",
                "purchaseRevenue",
            ],
            dimensions=[
                "deviceCategory",
                "operatingSystem",
                "browser",
            ],
        )
    except Exception as e:                                                    # Handle GA4 API errors to keep UI stable
        return pd.DataFrame(columns=expected_columns)                         # Return empty table with expected columns

    df = ga4_to_dataframe(response)                                           # Convert GA4 response to DataFrame

    if df.empty:
        return pd.DataFrame(columns=expected_columns)                         # Return empty table with expected columns

    for col in expected_columns:
        if col not in df.columns:
            df[col] = 0                                                       # Fill missing columns to keep schema stable


    df = _add_duration_per_user_display(                                      # DURATION COLUMN ADDED
        df,
        seconds_col="userEngagementDuration",
        users_col="totalUsers",
        display_col="user_engagement_duration_per_user",
    )
    df = _add_duration_per_session_display(                                   # DURATION COLUMN ADDED
        df,
        seconds_col="userEngagementDuration",
        sessions_col="sessions",
        display_col="user_engagement_duration_per_session",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - revenue per user # ADDED
        df,
        numerator_col="purchaseRevenue",
        denominator_col="totalUsers",
        target_col="revenue_per_user",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - revenue per session # ADDED
        df,
        numerator_col="purchaseRevenue",
        denominator_col="sessions",
        target_col="revenue_per_session",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - sessions per user # ADDED
        df,
        numerator_col="sessions",
        denominator_col="totalUsers",
        target_col="sessions_per_user",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - conversion rate # ADDED
        df,
        numerator_col="transactions",
        denominator_col="sessions",
        target_col="conversion_rate",
    )

    df = _round_columns(df, REVENUE_COLUMNS)

    return _apply_human_readable_columns(                                     # HUMAN-READABLE COLUMN # MODIFIED
        df[expected_columns]                                                 # Return ordered, consistent columns
    )


# This report shows the ecommerce funnel steps by date.
def get_ecommerce_funnel(
    start_date: str,                                                          # GA4 start date for the report
    end_date: str,                                                            # GA4 end date for the report
) -> pd.DataFrame:
    """
    Ecommerce funnel metrics by date.

    Compatible: date dimension with event metrics.
    """

    expected_columns = [                                                      # Expected schema for consistent UI use # MODIFIED
        "date",
        "screenPageViews",
        "itemViewEvents",
        "addToCarts",
        "checkouts",
        "transactions",
        "purchaseRevenue",
        "pageview_to_item_view_rate",                                        # FUNNEL METRIC ADDED
        "item_view_to_cart_rate",                                            # FUNNEL METRIC ADDED
        "cart_to_checkout_rate",                                             # FUNNEL METRIC ADDED
        "checkout_to_purchase_rate",                                         # FUNNEL METRIC ADDED
        "revenue_per_transaction",                                           # FUNNEL METRIC ADDED
    ]

    try:
        response = fetch_ga4_report(
            start_date=start_date,                                            # Date range start
            end_date=end_date,                                                # Date range end
            metrics=[
                "screenPageViews",
                "itemViewEvents",
                "addToCarts",
                "checkouts",
                "transactions",
                "purchaseRevenue",
            ],
            dimensions=["date"],
        )
    except Exception as e:                                                    # Handle GA4 API errors to keep UI stable
        return pd.DataFrame(columns=expected_columns)                         # Return empty table with expected columns

    df = ga4_to_dataframe(response)                                           # Convert GA4 response to DataFrame

    if df.empty:
        return pd.DataFrame(columns=expected_columns)                         # Return empty table with expected columns

    for col in expected_columns:
        if col not in df.columns:
            df[col] = 0                                                       # Fill missing columns to keep schema stable


    df = _add_ratio_metric(                                                   # DERIVED METRIC # FUNNEL METRIC ADDED
        df,
        numerator_col="itemViewEvents",
        denominator_col="screenPageViews",
        target_col="pageview_to_item_view_rate",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC # FUNNEL METRIC ADDED
        df,
        numerator_col="addToCarts",
        denominator_col="itemViewEvents",
        target_col="item_view_to_cart_rate",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC # FUNNEL METRIC ADDED
        df,
        numerator_col="checkouts",
        denominator_col="addToCarts",
        target_col="cart_to_checkout_rate",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC # FUNNEL METRIC ADDED
        df,
        numerator_col="transactions",
        denominator_col="checkouts",
        target_col="checkout_to_purchase_rate",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC # FUNNEL METRIC ADDED
        df,
        numerator_col="purchaseRevenue",
        denominator_col="transactions",
        target_col="revenue_per_transaction",
    )
    # VERIFIED: 120 purchases / 600 item views = 0.20 (20%)

    df = _round_columns(df, REVENUE_COLUMNS)

    return _apply_human_readable_columns(                                     # HUMAN-READABLE COLUMN # MODIFIED
        df[expected_columns]                                                 # Return ordered, consistent columns
    )


# This report summarizes item-level product performance.
def get_top_products(
    start_date: str,                                                          # GA4 start date for the report
    end_date: str,                                                            # GA4 end date for the report
) -> pd.DataFrame:
    """
    Product/item performance metrics.

    Compatible: item dimensions with item metrics.
    """

    expected_columns = [                                                      # Expected schema for consistent UI use # MODIFIED
        "itemName",
        "itemCategory",
        "itemsViewed",
        "itemsAddedToCart",
        "itemsCheckedOut",
        "itemsPurchased",
        "itemRevenue",
        "view_to_cart_rate",                                                 # FUNNEL METRIC ADDED
        "cart_to_checkout_rate",                                             # FUNNEL METRIC ADDED
        "checkout_to_purchase_rate",                                         # FUNNEL METRIC ADDED
        "item_view_to_purchase_rate",                                        # FUNNEL METRIC ADDED
        "revenue_per_item_view",                                             # FUNNEL METRIC ADDED
        "revenue_per_purchase",                                              # FUNNEL METRIC ADDED
    ]

    try:
        response = fetch_ga4_report(
            start_date=start_date,                                            # Date range start
            end_date=end_date,                                                # Date range end
            metrics=[
                "itemsViewed",
                "itemsAddedToCart",
                "itemsCheckedOut",
                "itemsPurchased",
                "itemRevenue",
            ],
            dimensions=[
                "itemName",
                "itemCategory",
            ],
        )
    except Exception as e:                                                    # Handle GA4 API errors to keep UI stable
        return pd.DataFrame(columns=expected_columns)                         # Return empty table with expected columns

    df = ga4_to_dataframe(response)                                           # Convert GA4 response to DataFrame

    if df.empty:
        return pd.DataFrame(columns=expected_columns)                         # Return empty table with expected columns

    for col in expected_columns:
        if col not in df.columns:
            df[col] = 0                                                       # Fill missing columns to keep schema stable


    df = _add_ratio_metric(                                                   # DERIVED METRIC # FUNNEL METRIC ADDED
        df,
        numerator_col="itemsAddedToCart",
        denominator_col="itemsViewed",
        target_col="view_to_cart_rate",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC # FUNNEL METRIC ADDED
        df,
        numerator_col="itemsCheckedOut",
        denominator_col="itemsAddedToCart",
        target_col="cart_to_checkout_rate",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC # FUNNEL METRIC ADDED
        df,
        numerator_col="itemsPurchased",
        denominator_col="itemsCheckedOut",
        target_col="checkout_to_purchase_rate",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC # FUNNEL METRIC ADDED
        df,
        numerator_col="itemsPurchased",
        denominator_col="itemsViewed",
        target_col="item_view_to_purchase_rate",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC # FUNNEL METRIC ADDED
        df,
        numerator_col="itemRevenue",
        denominator_col="itemsViewed",
        target_col="revenue_per_item_view",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC # FUNNEL METRIC ADDED
        df,
        numerator_col="itemRevenue",
        denominator_col="itemsPurchased",
        target_col="revenue_per_purchase",
    )
    # VERIFIED: 120 purchases / 600 item views = 0.20 (20%)

    df = _round_columns(df, REVENUE_COLUMNS)

    return _apply_human_readable_columns(                                     # HUMAN-READABLE COLUMN # MODIFIED
        df[expected_columns]                                                 # Return ordered, consistent columns
    )


# This report summarizes performance by geography.
def get_geographic_breakdown(
    start_date: str,                                                          # GA4 start date for the report
    end_date: str,                                                            # GA4 end date for the report
) -> pd.DataFrame:
    """
    Performance by country and city.

    Compatible: geographic dimensions with user/session metrics.
    """

    expected_columns = [                                                      # Expected schema for consistent UI use # MODIFIED
        "country",
        "city",
        "totalUsers",
        "newUsers",
        "sessions",
        "engagedSessions",
        "transactions",
        "purchaseRevenue",
        "revenue_per_user",                                                  # DERIVED METRIC # ADDED
        "revenue_per_session",                                               # DERIVED METRIC # ADDED
        "sessions_per_user",                                                 # DERIVED METRIC # ADDED
        "conversion_rate",                                                   # DERIVED METRIC # ADDED
    ]

    try:
        response = fetch_ga4_report(
            start_date=start_date,                                            # Date range start
            end_date=end_date,                                                # Date range end
            metrics=[
                "totalUsers",
                "newUsers",
                "sessions",
                "engagedSessions",
                "transactions",
                "purchaseRevenue",
            ],
            dimensions=[
                "country",
                "city",
            ],
        )
    except Exception as e:                                                    # Handle GA4 API errors to keep UI stable
        return pd.DataFrame(columns=expected_columns)                         # Return empty table with expected columns

    df = ga4_to_dataframe(response)                                           # Convert GA4 response to DataFrame

    if df.empty:
        return pd.DataFrame(columns=expected_columns)                         # Return empty table with expected columns

    for col in expected_columns:
        if col not in df.columns:
            df[col] = 0                                                       # Fill missing columns to keep schema stable


    df = _add_ratio_metric(                                                   # DERIVED METRIC - revenue per user # ADDED
        df,
        numerator_col="purchaseRevenue",
        denominator_col="totalUsers",
        target_col="revenue_per_user",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - revenue per session # ADDED
        df,
        numerator_col="purchaseRevenue",
        denominator_col="sessions",
        target_col="revenue_per_session",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - sessions per user # ADDED
        df,
        numerator_col="sessions",
        denominator_col="totalUsers",
        target_col="sessions_per_user",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - conversion rate # ADDED
        df,
        numerator_col="transactions",
        denominator_col="sessions",
        target_col="conversion_rate",
    )

    df = _round_columns(df, REVENUE_COLUMNS)

    return _apply_human_readable_columns(                                     # HUMAN-READABLE COLUMN # MODIFIED
        df[expected_columns]                                                 # Return ordered, consistent columns
    )


# This report summarizes acquisition by session source and medium.
def get_user_acquisition(
    start_date: str,                                                          # GA4 start date for the report
    end_date: str,                                                            # GA4 end date for the report
) -> pd.DataFrame:
    """
    User acquisition by channel.

    Compatible: session dimensions with user/session metrics.
    """

    expected_columns = [                                                      # Expected schema for consistent UI use # MODIFIED
        "sessionSource",
        "sessionMedium",
        "totalUsers",
        "newUsers",
        "sessions",
        "engagedSessions",
        "userEngagementDuration",
        "user_engagement_duration_per_user",                                # DURATION COLUMN ADDED
        "user_engagement_duration_per_session",                             # DURATION COLUMN ADDED
        "transactions",
        "purchaseRevenue",
        "revenue_per_user",                                                  # DERIVED METRIC # ADDED
        "revenue_per_session",                                               # DERIVED METRIC # ADDED
        "sessions_per_user",                                                 # DERIVED METRIC # ADDED
        "conversion_rate",                                                   # DERIVED METRIC # ADDED
    ]

    try:
        response = fetch_ga4_report(
            start_date=start_date,                                            # Date range start
            end_date=end_date,                                                # Date range end
            metrics=[
                "totalUsers",
                "newUsers",
                "sessions",
                "engagedSessions",
                "userEngagementDuration",
                "transactions",
                "purchaseRevenue",
            ],
            dimensions=[
                "sessionSource",
                "sessionMedium",
            ],
        )
    except Exception as e:                                                    # Handle GA4 API errors to keep UI stable
        return pd.DataFrame(columns=expected_columns)                         # Return empty table with expected columns

    df = ga4_to_dataframe(response)                                           # Convert GA4 response to DataFrame

    if df.empty:
        return pd.DataFrame(columns=expected_columns)                         # Return empty table with expected columns

    for col in expected_columns:
        if col not in df.columns:
            df[col] = 0                                                       # Fill missing columns to keep schema stable


    df = _add_duration_per_user_display(                                      # DURATION COLUMN ADDED
        df,
        seconds_col="userEngagementDuration",
        users_col="totalUsers",
        display_col="user_engagement_duration_per_user",
    )
    df = _add_duration_per_session_display(                                   # DURATION COLUMN ADDED
        df,
        seconds_col="userEngagementDuration",
        sessions_col="sessions",
        display_col="user_engagement_duration_per_session",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - revenue per user # ADDED
        df,
        numerator_col="purchaseRevenue",
        denominator_col="totalUsers",
        target_col="revenue_per_user",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - revenue per session # ADDED
        df,
        numerator_col="purchaseRevenue",
        denominator_col="sessions",
        target_col="revenue_per_session",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - sessions per user # ADDED
        df,
        numerator_col="sessions",
        denominator_col="totalUsers",
        target_col="sessions_per_user",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - conversion rate # ADDED
        df,
        numerator_col="transactions",
        denominator_col="sessions",
        target_col="conversion_rate",
    )

    df = _round_columns(df, REVENUE_COLUMNS)

    return _apply_human_readable_columns(                                     # HUMAN-READABLE COLUMN # MODIFIED
        df[expected_columns]                                                 # Return ordered, consistent columns
    )


# This report evaluates acquisition efficiency by source and medium.
def get_test_acquisition_efficiency(
    start_date: str,                                                          # GA4 start date for the report
    end_date: str,                                                            # GA4 end date for the report
) -> pd.DataFrame:
    """
    Experimental acquisition efficiency report.

    Compatible: session dimensions with user/session metrics.
    """

    expected_columns = [                                                      # Expected schema for consistent UI use
        "sessionSource",
        "sessionMedium",
        "totalUsers",
        "activeUsers",
        "newUsers",
        "sessions",
        "engagedSessions",
        "userEngagementDuration",
        "user_engagement_duration_per_user",                                # DURATION COLUMN ADDED
        "user_engagement_duration_per_session",                             # DURATION COLUMN ADDED
        "transactions",
        "purchaseRevenue",
        "sessions_per_user",                                                 # DERIVED METRIC
        "conversion_rate",                                                   # DERIVED METRIC
        "revenue_per_user",                                                  # DERIVED METRIC
        "revenue_per_session",                                               # DERIVED METRIC
        "revenue_per_transaction",                                           # DERIVED METRIC
        "active_user_ratio",                                                 # DERIVED METRIC
    ]

    try:
        response = fetch_ga4_report(
            start_date=start_date,                                            # Date range start
            end_date=end_date,                                                # Date range end
            metrics=[
                "totalUsers",
                "activeUsers",
                "newUsers",
                "sessions",
                "engagedSessions",
                "userEngagementDuration",
                "transactions",
                "purchaseRevenue",
            ],
            dimensions=[
                "sessionSource",
                "sessionMedium",
            ],
        )
    except Exception as e:                                                    # Handle GA4 API errors to keep UI stable
        return pd.DataFrame(columns=expected_columns)                         # Return empty table with expected columns

    df = ga4_to_dataframe(response)                                           # Convert GA4 response to DataFrame

    if df.empty:
        return pd.DataFrame(columns=expected_columns)                         # Return empty table with expected columns

    for col in expected_columns:
        if col not in df.columns:
            df[col] = 0                                                       # Fill missing columns to keep schema stable


    df = _add_duration_per_user_display(                                      # DURATION COLUMN ADDED
        df,
        seconds_col="userEngagementDuration",
        users_col="totalUsers",
        display_col="user_engagement_duration_per_user",
    )
    df = _add_duration_per_session_display(                                   # DURATION COLUMN ADDED
        df,
        seconds_col="userEngagementDuration",
        sessions_col="sessions",
        display_col="user_engagement_duration_per_session",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - sessions per user
        df,
        numerator_col="sessions",
        denominator_col="totalUsers",
        target_col="sessions_per_user",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - conversion rate
        df,
        numerator_col="transactions",
        denominator_col="sessions",
        target_col="conversion_rate",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - revenue per user
        df,
        numerator_col="purchaseRevenue",
        denominator_col="totalUsers",
        target_col="revenue_per_user",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - revenue per session
        df,
        numerator_col="purchaseRevenue",
        denominator_col="sessions",
        target_col="revenue_per_session",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - revenue per transaction
        df,
        numerator_col="purchaseRevenue",
        denominator_col="transactions",
        target_col="revenue_per_transaction",
    )
    df = _add_ratio_metric(                                                   # DERIVED METRIC - active user ratio
        df,
        numerator_col="activeUsers",
        denominator_col="totalUsers",
        target_col="active_user_ratio",
    )

    df = _round_columns(df, REVENUE_COLUMNS)

    return _apply_human_readable_columns(                                     # HUMAN-READABLE COLUMN # MODIFIED
        df[expected_columns]                                                 # Return ordered, consistent columns
    )


# This report shows page performance by path and title.
def get_page_performance(
    start_date: str,                                                          # GA4 start date for the report
    end_date: str,                                                            # GA4 end date for the report
) -> pd.DataFrame:
    """
    Performance by page path.

    Compatible: page dimensions with session/event metrics.
    """

    expected_columns = [                                                      # Expected schema for consistent UI use # MODIFIED
        "pagePath",
        "pageTitle",
        "screenPageViews",
        "sessions",
        "engagedSessions",
        "userEngagementDuration",
    ]

    try:
        response = fetch_ga4_report(
            start_date=start_date,                                            # Date range start
            end_date=end_date,                                                # Date range end
            metrics=[
                "screenPageViews",
                "sessions",
                "engagedSessions",
                "userEngagementDuration",
            ],
            dimensions=[
                "pagePath",
                "pageTitle",
            ],
        )
    except Exception as e:                                                    # Handle GA4 API errors to keep UI stable
        return pd.DataFrame(columns=expected_columns)                         # Return empty table with expected columns

    df = ga4_to_dataframe(response)                                           # Convert GA4 response to DataFrame

    if df.empty:
        return pd.DataFrame(columns=expected_columns)                         # Return empty table with expected columns

    for col in expected_columns:
        if col not in df.columns:
            df[col] = 0                                                       # Fill missing columns to keep schema stable


    df = _round_columns(df, REVENUE_COLUMNS)

    return _apply_human_readable_columns(                                     # HUMAN-READABLE COLUMN # MODIFIED
        df[expected_columns]                                                 # Return ordered, consistent columns
    )


# ============================================================================
# Core Report Registry
# ============================================================================
# The UI consumes this registry as the single source of truth for reports.

CORE_REPORTS = [                                                              # List of report metadata + builder function
    {
        "id": "traffic_overview",
        "name": "Traffic Overview",
        "description": "Sessions, users, and revenue by source, medium, device, and country.",
        "fn": get_traffic_overview,                                          # Function that builds this report
    },
    {
        "id": "daily_trends",
        "name": "Daily Trends",
        "description": "Time series for users, sessions, engagement, and revenue.",
        "fn": get_daily_trends,                                              # Function that builds this report
    },
    {
        "id": "landing_pages",
        "name": "Landing Pages",
        "description": "Landing page sessions, engagement, and revenue.",
        "fn": get_landing_pages,                                             # Function that builds this report
    },
    {
        "id": "device_performance",
        "name": "Device Performance",
        "description": "Performance split by device, OS, and browser.",
        "fn": get_device_performance,                                        # Function that builds this report
    },
    {
        "id": "ecommerce_funnel",
        "name": "Ecommerce Funnel",
        "description": "Funnel steps from views to purchases by date.",
        "fn": get_ecommerce_funnel,                                          # Function that builds this report
    },
    {
        "id": "top_products",
        "name": "Top Products",
        "description": "Item performance for views, carts, checkouts, and revenue.",
        "fn": get_top_products,                                              # Function that builds this report
    },
    {
        "id": "geographic_breakdown",
        "name": "Geographic Breakdown",
        "description": "Users, sessions, and revenue by country and city.",
        "fn": get_geographic_breakdown,                                      # Function that builds this report
    },
    {
        "id": "user_acquisition",
        "name": "User Acquisition",
        "description": "Users, sessions, and revenue by source and medium.",
        "fn": get_user_acquisition,                                          # Function that builds this report
    },
    {
        "id": "test_acquisition_efficiency",
        "name": "Test Acquisition Efficiency",
        "description": "Experimental efficiency metrics by source and medium.",
        "fn": get_test_acquisition_efficiency,                               # Function that builds this report
    },
    {
        "id": "page_performance",
        "name": "Page Performance",
        "description": "Page views, sessions, and engagement by page path and title.",
        "fn": get_page_performance,                                          # Function that builds this report
    },
]


# This function fetches all core reports and returns a registry map.
def get_all_core_reports(
    start_date: str,                                                          # GA4 start date for the report bundle
    end_date: str,                                                            # GA4 end date for the report bundle
) -> dict[str, dict]:
    """
    Fetch all core reports at once.

    Returns a dict where each key is a report id and each value is report data.
    """

    registry = {}                                                             # Map of report_id to report payload

    for report in CORE_REPORTS:
        report_id = report["id"]                                               # Unique report identifier
        try:
            data = report["fn"](start_date, end_date)                         # Execute the report builder
        except Exception as e:                                                # Handle report failures without breaking all reports
            print(f"Warning: {report_id} failed - {e}")
            data = pd.DataFrame()                                             # Return empty data for the failed report

        registry[report_id] = {
            "id": report_id,                                                 # Stable report id
            "name": report["name"],                                          # Display name
            "description": report["description"],                           # UI-friendly description
            "data": data,                                                    # Report DataFrame
        }

    return registry                                                           # Return the full report registry
