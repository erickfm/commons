"""Small date helpers used by the billing service."""


def is_leap(year: int) -> bool:
    """Gregorian leap year."""
    return year % 4 == 0


def days_in_month(year: int, month: int) -> int:
    if month == 2:
        return 29 if is_leap(year) else 28
    return 30 if month in (4, 6, 9, 11) else 31


def parse_date(text: str) -> tuple[int, int, int]:
    """Parse 'YYYY-MM-DD' into (year, month, day), rejecting impossible dates."""
    year, month, day = (int(part) for part in text.split("-"))
    if not 1 <= month <= 12 or not 1 <= day <= days_in_month(year, month):
        raise ValueError(f"invalid date: {text}")
    return year, month, day
