"""
This module provides formatting utilities for numeric, ratio, duration,
and token-related values used throughout the Streamlit UI.
It ensures consistent, readable, and user-friendly presentation.
"""

# ============================================================================
# Ratio Column Registry
# ============================================================================
# These columns should retain decimal precision when formatting.

RATIO_COLUMNS = {
    "Revenue per User",
    "Revenue per Active User",
    "Revenue per Session",
    "Sessions per User",
    "Conversion Rate",
    "View -> Cart Conversion Rate",
    "Cart -> Checkout Conversion Rate",
    "Checkout -> Purchase Conversion Rate",
    "Item View -> Purchase Conversion Rate",
    "Revenue per Item View",
    "Revenue per Purchase",
    "View -> Item View Conversion Rate",
    "Item View -> Cart Conversion Rate",
    "Revenue per Transaction",
    "Active User Ratio",
    "revenue_per_user",
    "revenue_per_active_user",
    "revenue_per_session",
    "sessions_per_user",
    "conversion_rate",
    "view_to_cart_rate",
    "cart_to_checkout_rate",
    "checkout_to_purchase_rate",
    "item_view_to_purchase_rate",
    "revenue_per_item_view",
    "revenue_per_purchase",
    "pageview_to_item_view_rate",
    "item_view_to_cart_rate",
    "revenue_per_transaction",
    "active_user_ratio",
}


# Formats a single numeric value for UI display.
def format_number(
    value,                          # Raw input value
    currency=False,                 # Whether to prefix currency symbol
):
    if value is None:
        return "-"                  # Placeholder for missing values

    try:
        num = float(value)
    except (ValueError, TypeError):  # Handle non-numeric inputs safely
        return str(value)

    if num == 0:
        return "ƒ,_0" if currency else "0"

    if abs(num) >= 1_000_000:
        formatted = f"{num / 1_000_000:.1f}M"
    elif abs(num) >= 1_000:
        formatted = f"{num / 1_000:.1f}K"
    else:
        formatted = f"{num:.2f}"

    formatted = formatted.rstrip("0").rstrip(".")
    return f"ƒ,_{formatted}" if currency else formatted


# Formats numeric columns inside a DataFrame.
def format_dataframe_numbers(
    df,                             # DataFrame to format
    decimals=0,                     # Default decimal precision
):
    if df is None:
        return df                   # Preserve None input

    try:
        numeric_cols = df.select_dtypes(include="number").columns
    except AttributeError:           # Handle non-DataFrame input
        return df

    if not numeric_cols.any():
        return df

    formatted = df.copy()
    ratio_cols = [c for c in numeric_cols if c in RATIO_COLUMNS]
    rounded = formatted[numeric_cols].round(decimals)

    if ratio_cols:
        rounded[ratio_cols] = formatted[ratio_cols].round(2)  # Preserve ratio precision

    if decimals == 0:
        for col in numeric_cols:
            if col in ratio_cols:
                continue
            try:
                rounded[col] = rounded[col].astype("Int64")
            except (TypeError, ValueError):                    # Skip incompatible columns
                pass

    formatted[numeric_cols] = rounded
    return formatted                   # Return formatted DataFrame


# Formats seconds into HH:MM:SS duration strings.
def format_duration(value):
    def _format_seconds(seconds):
        if seconds is None:
            return "00:00:00"
        try:
            total_seconds = int(float(seconds))
        except (TypeError, ValueError):
            return "00:00:00"
        if total_seconds < 0:
            total_seconds = 0
        hours, remainder = divmod(total_seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    if hasattr(value, "apply"):
        return value.apply(_format_seconds)
    return _format_seconds(value)


# Rounds a metric safely for both scalars and pandas Series.
def round_metric(value, decimals=2):
    try:
        return value.astype("Float64").round(decimals)
    except AttributeError:
        try:
            return round(float(value), decimals)
        except (TypeError, ValueError):
            return value


# Converts token counts into compact strings.
def format_token_number(tokens: int) -> str:
    if tokens >= 1000:
        return f"~{int(round(tokens / 1000))}k"
    return f"~{tokens}"


# Assigns a status color based on token count.
def token_status(tokens: int) -> str:
    if tokens < 20000:
        return "green"
    if tokens <= 60000:
        return "yellow"
    return "red"


# Returns an emoji representing token size status.
def token_emoji(tokens: int) -> str:
    status = token_status(tokens)
    if status == "green":
        return "🟢"
    if status == "yellow":
        return "🟡"
    return "🔴"


# Combines emoji and formatted token count for UI display.
def format_token_estimate(tokens: int) -> str:
    return f"{token_emoji(tokens)} {format_token_number(tokens)}"
