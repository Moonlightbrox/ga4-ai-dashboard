# This module formats numeric values for display in the Streamlit UI.
# It provides helpers for human-friendly numbers and token estimates.

# This function formats a single numeric value, optionally as currency.
def format_number(
    value,                                                                 # Raw value to format
    currency=False,                                                        # When True, prefix with a currency symbol
):
    if value is None:
        return "-"                                                           # Return placeholder for missing values

    try:
        num = float(value)                                                   # Convert input to a number when possible
    except (ValueError, TypeError):                                          # Handle non-numeric input safely
        return str(value)                                                    # Return original value as a string

    if num == 0:
        return "\u0192,_0" if currency else "0"                              # Return zero with optional currency symbol

    if abs(num) >= 1_000_000:
        formatted = f"{num / 1_000_000:.1f}M"                                # Use millions shorthand for large values
    elif abs(num) >= 1_000:
        formatted = f"{num / 1_000:.1f}K"                                    # Use thousands shorthand for mid values
    else:
        formatted = f"{num:.2f}"                                             # Use two decimals for small values

    formatted = formatted.rstrip("0").rstrip(".")                           # Trim trailing zeros and dots for cleaner output

    return f"\u0192,_{formatted}" if currency else formatted                  # Return formatted string with optional currency


# This function formats all numeric columns in a DataFrame for UI display.
def format_dataframe_numbers(
    df,                                                                    # DataFrame to format
    decimals=0,                                                            # Number of decimals to round to
):
    if df is None:
        return df                                                            # Return original input when no DataFrame exists

    try:
        numeric_cols = df.select_dtypes(include="number").columns            # Identify numeric columns for rounding
    except AttributeError:                                                   # Handle non-DataFrame input safely
        return df                                                            # Return original input when not a DataFrame

    if len(numeric_cols) == 0:
        return df                                                            # Return original input when no numeric columns

    formatted = df.copy()                                                    # Copy to avoid mutating the original data
    rounded = formatted[numeric_cols].round(decimals)                        # Round numeric columns to desired precision

    if decimals == 0:
        for col in numeric_cols:
            try:
                rounded[col] = rounded[col].astype("Int64")                  # Use integer display when no decimals are needed
            except (TypeError, ValueError):                                  # Handle columns that cannot be cast safely
                pass                                                         # Leave column as-is when conversion fails

    formatted[numeric_cols] = rounded                                        # Replace numeric columns with formatted values
    return formatted                                                         # Return the formatted DataFrame


# This function converts a token count into a human-friendly string.
def format_token_number(
    tokens: int,                                                           # Token count to format
) -> str:
    if tokens >= 1000:
        return f"~{int(round(tokens / 1000))}k"                               # Return compact thousands representation
    return f"~{tokens}"                                                      # Return raw token count with prefix


# This function maps a token count to a status color label.
def token_status(
    tokens: int,                                                           # Token count to classify
) -> str:
    if tokens < 20000:
        return "green"                                                      # Safe token size range
    if tokens <= 60000:
        return "yellow"                                                     # Warning range for larger prompts
    return "red"                                                            # High token range to avoid


# This function selects a colored emoji based on token size.
def token_emoji(
    tokens: int,                                                           # Token count used for emoji selection
) -> str:
    status = token_status(tokens)                                            # Determine token size category
    if status == "green":
        return "\U0001F7E2"                                                  # Green circle emoji
    if status == "yellow":
        return "\U0001F7E1"                                                  # Yellow circle emoji
    return "\U0001F534"                                                      # Red circle emoji


# This function formats a full token estimate string for the UI.
def format_token_estimate(
    tokens: int,                                                           # Token count to format
) -> str:
    return f"{token_emoji(tokens)} {format_token_number(tokens)}"            # Return emoji + compact token count
