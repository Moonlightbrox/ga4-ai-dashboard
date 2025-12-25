def format_number(value, currency=False):
    if value is None:
        return "-"

    try:
        num = float(value)
    except (ValueError, TypeError):
        return str(value)

    if num == 0:
        return "₾0" if currency else "0"

    if abs(num) >= 1_000_000:
        formatted = f"{num / 1_000_000:.1f}M"
    elif abs(num) >= 1_000:
        formatted = f"{num / 1_000:.1f}K"
    else:
        formatted = f"{num:.2f}"

    formatted = formatted.rstrip("0").rstrip(".")

    return f"₾{formatted}" if currency else formatted
