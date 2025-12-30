def format_number(value, currency=False):
    if value is None:
        return "-"

    try:
        num = float(value)
    except (ValueError, TypeError):
        return str(value)

    if num == 0:
        return "\u0192,_0" if currency else "0"

    if abs(num) >= 1_000_000:
        formatted = f"{num / 1_000_000:.1f}M"
    elif abs(num) >= 1_000:
        formatted = f"{num / 1_000:.1f}K"
    else:
        formatted = f"{num:.2f}"

    formatted = formatted.rstrip("0").rstrip(".")

    return f"\u0192,_{formatted}" if currency else formatted


def format_dataframe_numbers(df, decimals=0):
    if df is None:
        return df

    try:
        numeric_cols = df.select_dtypes(include="number").columns
    except AttributeError:
        return df

    if len(numeric_cols) == 0:
        return df

    formatted = df.copy()
    rounded = formatted[numeric_cols].round(decimals)

    if decimals == 0:
        for col in numeric_cols:
            try:
                rounded[col] = rounded[col].astype("Int64")
            except (TypeError, ValueError):
                pass

    formatted[numeric_cols] = rounded
    return formatted
