""" ga4_schema.py

=====================================================================
PURPOSE
=====================================================================

Canonical analytics schema for GA4.

Defines:
- Atomic GA4 metrics (safe to fetch)
- GA4 dimensions (row scope)
- Derived metrics (formulas only)

This file defines WHAT exists and WHAT it means,
not WHEN or HOW it is calculated.
"""


# =====================================================================
# GA4 ATOMIC METRICS (SAFE TO FETCH FROM API)
# =====================================================================

""" GA4_METRICS

Atomic, summable GA4 metrics only.

RULE:
If a metric is a ratio, rate, average, or per-user,
it MUST NOT appear here.
"""

GA4_METRICS: set[str] = {

    # --------------------------------------------------
    # USERS & ACTIVITY
    # --------------------------------------------------
    "activeUsers",                 # Users with at least one engaged session
    "newUsers",                    # First-time users
    "totalUsers",                  # All users

    "active1DayUsers",             # Daily active users (DAU)
    "active7DayUsers",             # Weekly active users (WAU)
    "active28DayUsers",            # Monthly active users (MAU)

    # --------------------------------------------------
    # SESSIONS & ENGAGEMENT SIGNALS
    # --------------------------------------------------
    "sessions",                    # Total sessions
    "engagedSessions",             # Sessions considered engaged
    "eventCount",                  # Total events fired
    "userEngagementDuration",      # Total engagement time (seconds)
    
    "screenPageViews",             # The number of app screens or web pages your users viewed. Repeated views of a single page or screen are counted. (screen_view + page_view events).

    # --------------------------------------------------
    # ECOMMERCE – TRANSACTIONS & VALUE
    # --------------------------------------------------
    "transactions",                # The count of Events with purchase revenue.Events are in_app_purchase, ecommerce_purchase, purchase, app_store_subscription_renew, app_store_subscription_convert, and refund.
    "ecommercePurchases",          # The number of times users completed a purchase. This metric counts purchase events; this metric does not count in_app_purchase and subscription events.
    "totalRevenue",                # Total revenue (all sources)
    "purchaseRevenue",             # Revenue from purchases only
    "grossPurchaseRevenue",        # Revenue before refunds/discounts
    "refundAmount",                # Total refunded amount

    # --------------------------------------------------
    # ECOMMERCE – ITEMS
    # --------------------------------------------------
    "itemViewEvents",              # The number of times the item details were viewed. The metric counts the occurrence of the view_item event. 
    "addToCarts",                  # The number of times users added items to their shopping carts.
    "checkouts",                   # The number of times users started the checkout process. This metric counts the occurrence of the begin_checkout event.

    # Item counts
    "itemsPurchased",              # Number of items sold
    "itemsViewed",                 # Items viewed
    "itemsAddedToCart",            # Items added to cart
    "itemsCheckedOut",             # Items checked out
    "itemsViewedInList",           # Items viewed in product lists
    "itemsClickedInList",          # Items clicked from product lists

    "itemRevenue",                 # Revenue per item
    "grossItemRevenue",            # Item revenue before discounts
    "itemDiscountAmount",          # Discount amount applied to items
    "itemRefundAmount",            # Refunded item value

    # --------------------------------------------------
    # ECOMMERCE – FUNNEL EVENTS
    # --------------------------------------------------
    "addToCarts",                  # Add-to-cart events
    "checkouts",                   # Checkout-start events
    "itemViewEvents",              # Item view events
    "itemListViewEvents",          # Product list view events
    "itemListClickEvents",         # Product list click events

    # --------------------------------------------------
    # PROMOTIONS
    # --------------------------------------------------
    "promotionViews",              # Promotion impressions
    "promotionClicks",             # Promotion clicks

    # --------------------------------------------------
    # PURCHASERS
    # --------------------------------------------------
    "firstTimePurchasers",         # Users who purchased for the first time
    "totalPurchasers",             # Users who made at least one purchase
}


# =====================================================================
# GA4 DIMENSIONS 
# =====================================================================

""" GA4_DIMENSIONS

Dimensions define HOW metrics are segmented.
They define row scope and analytical context.
"""

GA4_DIMENSIONS: set[str] = {

    # --------------------------------------------------
    # TIME
    # --------------------------------------------------
    "date",                        # Calendar date (YYYYMMDD)
    "week",                        # Calendar week
    "month",                       # Calendar month

    # --------------------------------------------------
    # GEO
    # --------------------------------------------------
    "country",                     # Country
    "city",                        # City

    # --------------------------------------------------
    # ACQUISITION
    # --------------------------------------------------
    "sessionSource",               # The source that initiated a session on your website or app.
    "sessionMedium",               # The medium that initiated a session on your website or app.

    # --------------------------------------------------
    # DEVICE / TECH
    # --------------------------------------------------
    "deviceCategory",              # desktop / mobile / tablet
    "operatingSystem",             # OS name
    "browser",                     # Browser name

    # --------------------------------------------------
    # Pages & Content
    # --------------------------------------------------
    "pagePath",             
    "pageTitle",             
    "landingPage",                 # The page path associated with the first pageview in a session.
    "exitPage",                   

    # --------------------------------------------------
    # ECOMMERCE – ITEMS
    # --------------------------------------------------
    "itemId",                      # Item SKU / ID
    "itemName",                    # Product name
    "itemBrand",                   # Product brand
    "itemVariant",                 # Variant (size, color)
    "itemAffiliation",             # Store or partner affiliation

    "itemCategory",                # Category level 1
    "itemCategory2",               # Category level 2
    "itemCategory3",               # Category level 3
    "itemCategory4",               # Category level 4
    "itemCategory5",               # Category level 5

    # --------------------------------------------------
    # ECOMMERCE – LISTS & PROMOTIONS
    # --------------------------------------------------
    "itemListId",                  # Product list ID
    "itemListName",                # Product list name
    "itemListPosition",            # Position in list

    "itemPromotionId",             # Promotion ID
    "itemPromotionName",           # Promotion name

    # --------------------------------------------------
    # TRANSACTIONS
    # --------------------------------------------------
    "transactionId",               # Unique transaction ID
    "orderCoupon",                 # Coupon code applied
    "shippingTier",                # Shipping option / tier
    "currencyCode",                # Transaction currency
}
