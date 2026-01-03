# This module defines the core GA4 reports and returns them as standardized tables.
# It also provides a registry and helpers so the UI can fetch consistent report data.

import pandas as pd
from data.ga4_service import fetch_ga4_report
from data.preprocess import ga4_to_dataframe


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

    expected_columns = [                                                      # Expected schema for consistent UI use
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
        "transactions",
        "purchaseRevenue",
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

    return df[expected_columns]                                               # Return ordered, consistent columns


# This report provides daily trend metrics for key KPIs.
def get_daily_trends(
    start_date: str,                                                          # GA4 start date for the report
    end_date: str,                                                            # GA4 end date for the report
) -> pd.DataFrame:
    """
    Daily metrics to identify trends.

    Compatible: date dimension with most metrics.
    """

    expected_columns = [                                                      # Expected schema for consistent UI use
        "date",
        "totalUsers",
        "newUsers",
        "sessions",
        "engagedSessions",
        "userEngagementDuration",
        "transactions",
        "purchaseRevenue",
        "screenPageViews",
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

    return df[expected_columns]                                               # Return ordered, consistent columns


# This report tracks landing page performance metrics.
def get_landing_pages(
    start_date: str,                                                          # GA4 start date for the report
    end_date: str,                                                            # GA4 end date for the report
) -> pd.DataFrame:
    """
    Performance by landing page.

    Compatible: landing page dimension with session metrics.
    """

    expected_columns = [                                                      # Expected schema for consistent UI use
        "landingPage",
        "sessions",
        "engagedSessions",
        "userEngagementDuration",
        "transactions",
        "purchaseRevenue",
        "totalUsers",
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

    return df[expected_columns]                                               # Return ordered, consistent columns


# This report breaks down performance by device, OS, and browser.
def get_device_performance(
    start_date: str,                                                          # GA4 start date for the report
    end_date: str,                                                            # GA4 end date for the report
) -> pd.DataFrame:
    """
    Performance by device, OS, and browser.

    Compatible: device dimensions with user/session metrics.
    """

    expected_columns = [                                                      # Expected schema for consistent UI use
        "deviceCategory",
        "operatingSystem",
        "browser",
        "totalUsers",
        "sessions",
        "engagedSessions",
        "userEngagementDuration",
        "transactions",
        "purchaseRevenue",
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

    return df[expected_columns]                                               # Return ordered, consistent columns


# This report shows the ecommerce funnel steps by date.
def get_ecommerce_funnel(
    start_date: str,                                                          # GA4 start date for the report
    end_date: str,                                                            # GA4 end date for the report
) -> pd.DataFrame:
    """
    Ecommerce funnel metrics by date.

    Compatible: date dimension with event metrics.
    """

    expected_columns = [                                                      # Expected schema for consistent UI use
        "date",
        "screenPageViews",
        "itemViewEvents",
        "addToCarts",
        "checkouts",
        "transactions",
        "purchaseRevenue",
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

    return df[expected_columns]                                               # Return ordered, consistent columns


# This report summarizes item-level product performance.
def get_top_products(
    start_date: str,                                                          # GA4 start date for the report
    end_date: str,                                                            # GA4 end date for the report
) -> pd.DataFrame:
    """
    Product/item performance metrics.

    Compatible: item dimensions with item metrics.
    """

    expected_columns = [                                                      # Expected schema for consistent UI use
        "itemName",
        "itemCategory",
        "itemsViewed",
        "itemsAddedToCart",
        "itemsCheckedOut",
        "itemsPurchased",
        "itemRevenue",
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

    return df[expected_columns]                                               # Return ordered, consistent columns


# This report summarizes performance by geography.
def get_geographic_breakdown(
    start_date: str,                                                          # GA4 start date for the report
    end_date: str,                                                            # GA4 end date for the report
) -> pd.DataFrame:
    """
    Performance by country and city.

    Compatible: geographic dimensions with user/session metrics.
    """

    expected_columns = [                                                      # Expected schema for consistent UI use
        "country",
        "city",
        "totalUsers",
        "newUsers",
        "sessions",
        "engagedSessions",
        "transactions",
        "purchaseRevenue",
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

    return df[expected_columns]                                               # Return ordered, consistent columns


# This report summarizes acquisition by session source and medium.
def get_user_acquisition(
    start_date: str,                                                          # GA4 start date for the report
    end_date: str,                                                            # GA4 end date for the report
) -> pd.DataFrame:
    """
    User acquisition by channel.

    Compatible: session dimensions with user/session metrics.
    """

    expected_columns = [                                                      # Expected schema for consistent UI use
        "sessionSource",
        "sessionMedium",
        "totalUsers",
        "newUsers",
        "sessions",
        "engagedSessions",
        "userEngagementDuration",
        "transactions",
        "purchaseRevenue",
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

    return df[expected_columns]                                               # Return ordered, consistent columns


# This report shows page performance by path and title.
def get_page_performance(
    start_date: str,                                                          # GA4 start date for the report
    end_date: str,                                                            # GA4 end date for the report
) -> pd.DataFrame:
    """
    Performance by page path.

    Compatible: page dimensions with session/event metrics.
    """

    expected_columns = [                                                      # Expected schema for consistent UI use
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

    return df[expected_columns]                                               # Return ordered, consistent columns


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


# ============================================================================
# Summary Statistics Helpers
# ============================================================================
# These helpers compute quick KPIs across the report bundle.

# This function normalizes report structures into a dict of DataFrames.
def _extract_report_frames(reports: dict) -> dict[str, pd.DataFrame]:
    if not reports:
        return {}                                                             # Return empty mapping when no reports exist

    sample = next(iter(reports.values()))                                     # Peek at one report to detect structure
    if isinstance(sample, dict) and "data" in sample:
        return {key: value.get("data", pd.DataFrame()) for key, value in reports.items()}  # Return only DataFrames

    return reports                                                            # Return input if it is already a DataFrame map


# This function computes high-level summary metrics across reports.
def get_summary_statistics(reports: dict) -> dict:
    """
    Calculate summary statistics across all reports.
    """

    report_frames = _extract_report_frames(reports)                           # Normalize input into DataFrames
    traffic = report_frames.get("traffic_overview", pd.DataFrame())           # Preferred report for top-line metrics

    if traffic.empty:
        traffic = report_frames.get("daily_trends", pd.DataFrame())           # Fallback to daily trends if needed

    if traffic.empty:
        return {                                                              # Return zeros when no data is available
            "total_users": 0,
            "total_sessions": 0,
            "total_revenue": 0.0,
            "total_transactions": 0,
            "conversion_rate": 0.0,
            "revenue_per_user": 0.0,
        }

    total_users = int(traffic["totalUsers"].sum()) if "totalUsers" in traffic.columns else 0
    total_sessions = int(traffic["sessions"].sum()) if "sessions" in traffic.columns else 0
    total_revenue = float(traffic["purchaseRevenue"].sum()) if "purchaseRevenue" in traffic.columns else 0.0
    total_transactions = int(traffic["transactions"].sum()) if "transactions" in traffic.columns else 0

    return {
        "total_users": total_users,                                          # Total users across the period
        "total_sessions": total_sessions,                                    # Total sessions across the period
        "total_revenue": total_revenue,                                      # Total purchase revenue
        "total_transactions": total_transactions,                            # Total transactions/purchases
        "conversion_rate": (
            float(total_transactions / total_users * 100)
            if total_users > 0 else 0.0
        ),
        "revenue_per_user": (
            float(total_revenue / total_users)
            if total_users > 0 else 0.0
        ),
    }


# ============================================================================
# GA4 Compatibility Notes
# ============================================================================
# This section summarizes the dimension/metric compatibility rules used above.

"""
KEY GA4 COMPATIBILITY RULES APPLIED:

1. SESSION-SCOPED DIMENSIONS (compatible with most metrics):
   - sessionSource, sessionMedium
   - deviceCategory, browser, operatingSystem
   - country, city
   - landingPage, pagePath, pageTitle
   - date

   Works with: User metrics, session metrics, event metrics, revenue
   Does NOT work with: Item-scoped metrics

2. ITEM-SCOPED DIMENSIONS (limited compatibility):
   - itemName, itemId, itemCategory, itemBrand

   ONLY works with: Item-scoped metrics
   Does NOT work with: User metrics, session metrics

3. METRICS THAT WORK EVERYWHERE:
   - totalUsers, activeUsers, newUsers
   - sessions, engagedSessions
   - userEngagementDuration
   - transactions, purchaseRevenue
   - screenPageViews, eventCount

4. METRICS WITH RESTRICTIONS:
   - averageSessionDuration: doesn't work with most dimensions
   - Item metrics (itemsViewed, etc): ONLY with item dimensions

5. SAFE COMBINATIONS USED:
   - Session dimensions + User/Session/Revenue metrics
   - Date + Any metrics
   - Item dimensions + Item metrics ONLY
   - Event metrics (addToCarts, checkouts) work with date

6. AVOIDED COMBINATIONS:
   - Item dimensions + Session metrics
   - Session dimensions + Item metrics
   - averageSessionDuration with multiple dimensions
"""
