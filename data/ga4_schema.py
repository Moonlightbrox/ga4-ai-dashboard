# This module defines the canonical GA4 metrics and dimensions used by the app.
# It also provides UI-friendly labels so users can build custom reports safely.

# ============================================================================
# GA4 Atomic Metrics (Safe to Fetch)
# ============================================================================
# These are raw GA4 metrics that can be requested directly from the API.

GA4_METRICS: set[str] = {

    # ------------------------------------------------------------------
    # Users and Activity
    # ------------------------------------------------------------------
    "activeUsers",                 # Users with at least one engaged session
    "newUsers",                    # First-time users
    "totalUsers",                  # All users

    "active1DayUsers",             # Daily active users (DAU)
    "active7DayUsers",             # Weekly active users (WAU)
    "active28DayUsers",            # Monthly active users (MAU)

    # ------------------------------------------------------------------
    # Sessions and Engagement Signals
    # ------------------------------------------------------------------
    "sessions",                    # Total sessions
    "engagedSessions",             # Sessions considered engaged
    "eventCount",                  # Total events fired
    "userEngagementDuration",      # Total engagement time (seconds)

    "screenPageViews",             # Total page and screen views

    # ------------------------------------------------------------------
    # Ecommerce Transactions and Value
    # ------------------------------------------------------------------
    "transactions",                # Purchase events count
    "ecommercePurchases",          # Completed ecommerce purchases
    "totalRevenue",                # Total revenue (all sources)
    "purchaseRevenue",             # Revenue from purchases only
    "grossPurchaseRevenue",        # Revenue before refunds/discounts
    "refundAmount",                # Total refunded amount

    # ------------------------------------------------------------------
    # Ecommerce Items
    # ------------------------------------------------------------------
    "itemViewEvents",              # Item detail view events
    "addToCarts",                  # Add-to-cart events
    "checkouts",                   # Begin checkout events

    "itemsPurchased",              # Number of items sold
    "itemsViewed",                 # Items viewed
    "itemsAddedToCart",            # Items added to cart
    "itemsCheckedOut",             # Items checked out
    "itemsViewedInList",           # Items viewed in product lists
    "itemsClickedInList",          # Items clicked from product lists

    "itemRevenue",                 # Revenue attributed to items
    "grossItemRevenue",            # Item revenue before discounts
    "itemDiscountAmount",          # Discount amount applied to items
    "itemRefundAmount",            # Refunded item value

    # ------------------------------------------------------------------
    # Ecommerce Funnel Events
    # ------------------------------------------------------------------
    "addToCarts",                  # Add-to-cart events
    "checkouts",                   # Checkout-start events
    "itemViewEvents",              # Item view events
    "itemListViewEvents",          # Product list view events
    "itemListClickEvents",         # Product list click events

    # ------------------------------------------------------------------
    # Promotions
    # ------------------------------------------------------------------
    "promotionViews",              # Promotion impressions
    "promotionClicks",             # Promotion clicks

    # ------------------------------------------------------------------
    # Purchasers
    # ------------------------------------------------------------------
    "firstTimePurchasers",         # Users who purchased for the first time
    "totalPurchasers",             # Users who made at least one purchase
}


# ============================================================================
# GA4 Dimensions (How Metrics Are Segmented)
# ============================================================================
# Dimensions define the row context for GA4 queries.

GA4_DIMENSIONS: set[str] = {

    # ------------------------------------------------------------------
    # Time
    # ------------------------------------------------------------------
    "date",                        # Calendar date (YYYYMMDD)
    "week",                        # Calendar week
    "month",                       # Calendar month

    # ------------------------------------------------------------------
    # Geography
    # ------------------------------------------------------------------
    "country",                     # Country
    "city",                        # City

    # ------------------------------------------------------------------
    # Acquisition
    # ------------------------------------------------------------------
    "sessionSource",               # Source that initiated a session
    "sessionMedium",               # Medium that initiated a session

    # ------------------------------------------------------------------
    # Device and Tech
    # ------------------------------------------------------------------
    "deviceCategory",              # Device type (desktop, mobile, tablet)
    "operatingSystem",             # Operating system name
    "browser",                     # Browser name

    # ------------------------------------------------------------------
    # Pages and Content
    # ------------------------------------------------------------------
    "pagePath",                    # Page URL path
    "pageTitle",                   # Page title
    "landingPage",                 # First page of the session
    "exitPage",                    # Last page of the session

    # ------------------------------------------------------------------
    # Ecommerce Items
    # ------------------------------------------------------------------
    "itemId",                      # Item SKU or ID
    "itemName",                    # Product name
    "itemBrand",                   # Product brand
    "itemVariant",                 # Variant (size, color)
    "itemAffiliation",             # Store or partner affiliation

    "itemCategory",                # Category level 1
    "itemCategory2",               # Category level 2
    "itemCategory3",               # Category level 3
    "itemCategory4",               # Category level 4
    "itemCategory5",               # Category level 5

    # ------------------------------------------------------------------
    # Ecommerce Lists and Promotions
    # ------------------------------------------------------------------
    "itemListId",                  # Product list ID
    "itemListName",                # Product list name
    "itemListPosition",            # Position in list

    "itemPromotionId",             # Promotion ID
    "itemPromotionName",           # Promotion name

    # ------------------------------------------------------------------
    # Transactions
    # ------------------------------------------------------------------
    "transactionId",               # Unique transaction ID
    "orderCoupon",                 # Coupon code applied
    "shippingTier",                # Shipping option or tier
    "currencyCode",                # Transaction currency
}


# ============================================================================
# UI-Friendly Metadata for Report Builder
# ============================================================================
# These maps add labels and descriptions used in custom report UI controls.

CORE_REPORT_METRICS: dict[str, dict[str, str]] = {
    "totalUsers": {
        "label": "Total Users",
        "description": "All users in the date range",
    },
    "activeUsers": {
        "label": "Active Users",
        "description": "Users with at least one engaged session",
    },
    "newUsers": {
        "label": "New Users",
        "description": "First-time users",
    },
    "sessions": {
        "label": "Sessions",
        "description": "Total sessions",
    },
    "engagedSessions": {
        "label": "Engaged Sessions",
        "description": "Sessions considered engaged",
    },
    "userEngagementDuration": {
        "label": "Engagement Duration",
        "description": "Total engagement time (seconds)",
    },
    "transactions": {
        "label": "Transactions",
        "description": "Completed purchase events",
    },
    "purchaseRevenue": {
        "label": "Purchase Revenue",
        "description": "Revenue from purchases",
    },
    "screenPageViews": {
        "label": "Screen/Page Views",
        "description": "Total page and screen views",
    },
    "itemViewEvents": {
        "label": "Item View Events",
        "description": "View item event count",
    },
    "addToCarts": {
        "label": "Add To Carts",
        "description": "Add to cart event count",
    },
    "checkouts": {
        "label": "Checkouts",
        "description": "Begin checkout event count",
    },
    "itemsViewed": {
        "label": "Items Viewed",
        "description": "Items viewed count",
    },
    "itemsAddedToCart": {
        "label": "Items Added To Cart",
        "description": "Items added to cart count",
    },
    "itemsCheckedOut": {
        "label": "Items Checked Out",
        "description": "Items checked out count",
    },
    "itemsPurchased": {
        "label": "Items Purchased",
        "description": "Items purchased count",
    },
    "itemRevenue": {
        "label": "Item Revenue",
        "description": "Revenue attributed to items",
    },
}

CORE_REPORT_DIMENSIONS: dict[str, dict[str, str]] = {
    "country": {
        "label": "Country",
        "description": "User country",
    },
    "deviceCategory": {
        "label": "Device Category",
        "description": "Device type (desktop, mobile, tablet)",
    },
    "sessionSource": {
        "label": "Session Source",
        "description": "Traffic source for the session",
    },
    "sessionMedium": {
        "label": "Session Medium",
        "description": "Traffic medium for the session",
    },
    "date": {
        "label": "Date",
        "description": "Calendar date (YYYYMMDD)",
    },
    "landingPage": {
        "label": "Landing Page",
        "description": "First page of the session",
    },
    "operatingSystem": {
        "label": "Operating System",
        "description": "User operating system",
    },
    "browser": {
        "label": "Browser",
        "description": "User browser",
    },
    "itemName": {
        "label": "Item Name",
        "description": "Product name",
    },
    "itemCategory": {
        "label": "Item Category",
        "description": "Product category",
    },
    "city": {
        "label": "City",
        "description": "User city",
    },
    "pagePath": {
        "label": "Page Path",
        "description": "Page URL path",
    },
    "pageTitle": {
        "label": "Page Title",
        "description": "Page title",
    },
}
