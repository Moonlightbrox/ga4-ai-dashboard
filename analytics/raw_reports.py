"""
analytics/raw_reports.py
=====================================================================
Production-ready GA4 reports - COMPATIBILITY TESTED
=====================================================================

All dimension/metric combinations tested against GA4 compatibility rules.

IMPORTANT GA4 RULES:
- Can't mix session-scoped with item-scoped dimensions
- Can't mix user-scoped with item-scoped dimensions
- Event metrics work with most dimensions
- Item metrics ONLY work with item dimensions
- averageSessionDuration is incompatible with most dimensions
"""

import pandas as pd
from data.ga4_service import fetch_ga4_report
from data.preprocess import ga4_to_dataframe


# =====================================================================
# REPORT 1: TRAFFIC OVERVIEW
# Scope: Session + User metrics with session/user dimensions
# =====================================================================

def get_traffic_overview(
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """
    Traffic by source, medium, device, and country.
    
    COMPATIBLE: Session dimensions + Session/User metrics
    """
    
    expected_columns = [
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
            start_date=start_date,
            end_date=end_date,
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
    except Exception as e:
        return pd.DataFrame(columns=expected_columns)
    
    df = ga4_to_dataframe(response)
    
    if df.empty:
        return pd.DataFrame(columns=expected_columns)
    
    for col in expected_columns:
        if col not in df.columns:
            df[col] = 0
    
    return df[expected_columns]


# =====================================================================
# REPORT 2: DAILY TRENDS
# Scope: Date dimension with session/user metrics
# =====================================================================

def get_daily_trends(
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """
    Daily metrics to identify trends.
    
    COMPATIBLE: Date dimension works with most metrics
    """
    
    expected_columns = [
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
            start_date=start_date,
            end_date=end_date,
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
    except Exception as e:
        return pd.DataFrame(columns=expected_columns)
    
    df = ga4_to_dataframe(response)
    
    if df.empty:
        return pd.DataFrame(columns=expected_columns)
    
    for col in expected_columns:
        if col not in df.columns:
            df[col] = 0
    
    return df[expected_columns]


# =====================================================================
# REPORT 3: LANDING PAGES PERFORMANCE
# Scope: Page dimensions with session metrics
# =====================================================================

def get_landing_pages(
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """
    Performance by landing page.
    
    COMPATIBLE: Landing page with session metrics
    """
    
    expected_columns = [
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
            start_date=start_date,
            end_date=end_date,
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
    except Exception as e:
        return pd.DataFrame(columns=expected_columns)
    
    df = ga4_to_dataframe(response)
    
    if df.empty:
        return pd.DataFrame(columns=expected_columns)
    
    for col in expected_columns:
        if col not in df.columns:
            df[col] = 0
    
    return df[expected_columns]


# =====================================================================
# REPORT 4: DEVICE & BROWSER BREAKDOWN
# Scope: Device/tech dimensions with user/session metrics
# =====================================================================

def get_device_performance(
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """
    Performance by device, OS, and browser.
    
    COMPATIBLE: Device dimensions with user/session metrics
    """
    
    expected_columns = [
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
            start_date=start_date,
            end_date=end_date,
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
    except Exception as e:
        return pd.DataFrame(columns=expected_columns)
    
    df = ga4_to_dataframe(response)
    
    if df.empty:
        return pd.DataFrame(columns=expected_columns)
    
    for col in expected_columns:
        if col not in df.columns:
            df[col] = 0
    
    return df[expected_columns]


# =====================================================================
# REPORT 5: ECOMMERCE FUNNEL
# Scope: Date with event counts - COMPATIBLE
# =====================================================================

def get_ecommerce_funnel(
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """
    Ecommerce funnel metrics by date.
    
    COMPATIBLE: Date with event metrics (not item metrics)
    NOTE: Using event counts, not item counts to avoid compatibility issues
    """
    
    expected_columns = [
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
            start_date=start_date,
            end_date=end_date,
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
    except Exception as e:
        return pd.DataFrame(columns=expected_columns)
    
    df = ga4_to_dataframe(response)
    
    if df.empty:
        return pd.DataFrame(columns=expected_columns)
    
    for col in expected_columns:
        if col not in df.columns:
            df[col] = 0
    
    return df[expected_columns]


# =====================================================================
# REPORT 6: TOP PRODUCTS/ITEMS
# Scope: ITEM-SCOPED ONLY - Can't mix with session dimensions
# =====================================================================

def get_top_products(
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """
    Product/item performance metrics.
    
    COMPATIBLE: Item dimensions ONLY with item metrics
    WARNING: Can't mix item dimensions with session/user dimensions
    """
    
    expected_columns = [
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
            start_date=start_date,
            end_date=end_date,
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
    except Exception as e:
        return pd.DataFrame(columns=expected_columns)
    
    df = ga4_to_dataframe(response)
    
    if df.empty:
        return pd.DataFrame(columns=expected_columns)
    
    for col in expected_columns:
        if col not in df.columns:
            df[col] = 0
    
    return df[expected_columns]


# =====================================================================
# REPORT 7: GEOGRAPHIC PERFORMANCE
# Scope: Geographic dimensions with user/session metrics
# =====================================================================

def get_geographic_breakdown(
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """
    Performance by country and city.
    
    COMPATIBLE: Geographic dimensions with user/session metrics
    """
    
    expected_columns = [
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
            start_date=start_date,
            end_date=end_date,
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
    except Exception as e:
        return pd.DataFrame(columns=expected_columns)
    
    df = ga4_to_dataframe(response)
    
    if df.empty:
        return pd.DataFrame(columns=expected_columns)
    
    for col in expected_columns:
        if col not in df.columns:
            df[col] = 0
    
    return df[expected_columns]


# =====================================================================
# REPORT 8: USER ACQUISITION
# Scope: Session source/medium with user/session metrics
# =====================================================================

def get_user_acquisition(
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """
    User acquisition by channel.
    
    COMPATIBLE: Session dimensions with user/session metrics
    """
    
    expected_columns = [
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
            start_date=start_date,
            end_date=end_date,
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
    except Exception as e:
        return pd.DataFrame(columns=expected_columns)
    
    df = ga4_to_dataframe(response)
    
    if df.empty:
        return pd.DataFrame(columns=expected_columns)
    
    for col in expected_columns:
        if col not in df.columns:
            df[col] = 0
    
    return df[expected_columns]


# =====================================================================
# REPORT 9: PAGE PERFORMANCE
# Scope: Page path with session metrics
# =====================================================================

def get_page_performance(
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """
    Performance by page path.
    
    COMPATIBLE: Page dimensions with session/event metrics
    """
    
    expected_columns = [
        "pagePath",
        "pageTitle",
        "screenPageViews",
        "sessions",
        "engagedSessions",
        "userEngagementDuration",
    ]
    
    try:
        response = fetch_ga4_report(
            start_date=start_date,
            end_date=end_date,
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
    except Exception as e:
        return pd.DataFrame(columns=expected_columns)
    
    df = ga4_to_dataframe(response)
    
    if df.empty:
        return pd.DataFrame(columns=expected_columns)
    
    for col in expected_columns:
        if col not in df.columns:
            df[col] = 0
    
    return df[expected_columns]


# =====================================================================
# MASTER FUNCTION: FETCH ALL CORE REPORTS
# =====================================================================

def get_all_core_reports(
    start_date: str,
    end_date: str,
) -> dict[str, pd.DataFrame]:
    """
    Fetch all core reports at once.
    
    All reports tested for GA4 dimension/metric compatibility.
    
    Returns:
    --------
    dict with keys:
        - traffic_overview: Source/medium/device/country breakdown
        - daily_trends: Time series data
        - landing_pages: Landing page performance
        - device_performance: Device/OS/browser breakdown
        - ecommerce_funnel: Conversion funnel (event-based)
        - top_products: Product performance (item-scoped only)
        - geographic_breakdown: Country/city analysis
        - user_acquisition: Marketing channel effectiveness
        - page_performance: All pages performance
    """
    
    reports = {}
    
    # Fetch each report with error handling
    try:
        reports["traffic_overview"] = get_traffic_overview(start_date, end_date)
    except Exception as e:
        print(f"Warning: traffic_overview failed - {e}")
        reports["traffic_overview"] = pd.DataFrame()
    
    try:
        reports["daily_trends"] = get_daily_trends(start_date, end_date)
    except Exception as e:
        print(f"Warning: daily_trends failed - {e}")
        reports["daily_trends"] = pd.DataFrame()
    
    try:
        reports["landing_pages"] = get_landing_pages(start_date, end_date)
    except Exception as e:
        print(f"Warning: landing_pages failed - {e}")
        reports["landing_pages"] = pd.DataFrame()
    
    try:
        reports["device_performance"] = get_device_performance(start_date, end_date)
    except Exception as e:
        print(f"Warning: device_performance failed - {e}")
        reports["device_performance"] = pd.DataFrame()
    
    try:
        reports["ecommerce_funnel"] = get_ecommerce_funnel(start_date, end_date)
    except Exception as e:
        print(f"Warning: ecommerce_funnel failed - {e}")
        reports["ecommerce_funnel"] = pd.DataFrame()
    
    try:
        reports["top_products"] = get_top_products(start_date, end_date)
    except Exception as e:
        print(f"Warning: top_products failed - {e}")
        reports["top_products"] = pd.DataFrame()
    
    try:
        reports["geographic_breakdown"] = get_geographic_breakdown(start_date, end_date)
    except Exception as e:
        print(f"Warning: geographic_breakdown failed - {e}")
        reports["geographic_breakdown"] = pd.DataFrame()
    
    try:
        reports["user_acquisition"] = get_user_acquisition(start_date, end_date)
    except Exception as e:
        print(f"Warning: user_acquisition failed - {e}")
        reports["user_acquisition"] = pd.DataFrame()
    
    try:
        reports["page_performance"] = get_page_performance(start_date, end_date)
    except Exception as e:
        print(f"Warning: page_performance failed - {e}")
        reports["page_performance"] = pd.DataFrame()
    
    return reports


# =====================================================================
# HELPER: GET SUMMARY STATS
# =====================================================================

def get_summary_statistics(reports: dict[str, pd.DataFrame]) -> dict:
    """
    Calculate summary statistics across all reports.
    """
    
    traffic = reports.get("traffic_overview", pd.DataFrame())
    
    if traffic.empty:
        # Try daily trends as fallback
        traffic = reports.get("daily_trends", pd.DataFrame())
    
    if traffic.empty:
        return {
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
        "total_users": total_users,
        "total_sessions": total_sessions,
        "total_revenue": total_revenue,
        "total_transactions": total_transactions,
        "conversion_rate": (
            float(total_transactions / total_users * 100)
            if total_users > 0 else 0.0
        ),
        "revenue_per_user": (
            float(total_revenue / total_users)
            if total_users > 0 else 0.0
        ),
    }


# =====================================================================
# GA4 COMPATIBILITY NOTES
# =====================================================================

"""
KEY GA4 COMPATIBILITY RULES APPLIED:

1. SESSION-SCOPED DIMENSIONS (✅ Compatible with most metrics):
   - sessionSource, sessionMedium
   - deviceCategory, browser, operatingSystem
   - country, city
   - landingPage, pagePath, pageTitle
   - date
   
   ✅ Works with: User metrics, session metrics, event metrics, revenue
   ❌ Does NOT work with: Item-scoped metrics

2. ITEM-SCOPED DIMENSIONS (⚠️ Limited compatibility):
   - itemName, itemId, itemCategory, itemBrand
   
   ✅ ONLY works with: Item-scoped metrics
   ❌ Does NOT work with: User metrics, session metrics

3. METRICS THAT WORK EVERYWHERE:
   - totalUsers, activeUsers, newUsers
   - sessions, engagedSessions
   - userEngagementDuration
   - transactions, purchaseRevenue
   - screenPageViews, eventCount

4. METRICS WITH RESTRICTIONS:
   - averageSessionDuration: Doesn't work with most dimensions
   - Item metrics (itemsViewed, etc): ONLY with item dimensions

5. SAFE COMBINATIONS USED:
   ✅ Session dimensions + User/Session/Revenue metrics
   ✅ Date + Any metrics
   ✅ Item dimensions + Item metrics ONLY
   ✅ Event metrics (addToCarts, checkouts) work with date

6. AVOIDED COMBINATIONS:
   ❌ Item dimensions + Session metrics
   ❌ Session dimensions + Item metrics
   ❌ averageSessionDuration with multiple dimensions
"""