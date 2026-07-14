"""
Date parsing and filtering utilities for API views.
Consolidates duplicated date handling code from multiple views.
"""
from datetime import datetime
from typing import Optional

from django.db.models import QuerySet
from django.utils import timezone


def parse_date_param(
    date_str: Optional[str],
    end_of_day: bool = False,
    date_format: str = '%Y-%m-%d'
) -> Optional[datetime]:
    """
    Parse a date string from query parameters into a timezone-aware datetime.

    Args:
        date_str: Date string to parse (e.g., '2024-01-15')
        end_of_day: If True, set time to 23:59:59, otherwise 00:00:00
        date_format: Expected date format (default: '%Y-%m-%d')

    Returns:
        Timezone-aware datetime or None if parsing fails or date_str is empty

    Example:
        >>> start = parse_date_param('2024-01-01')
        >>> end = parse_date_param('2024-01-31', end_of_day=True)
    """
    if not date_str:
        return None

    try:
        parsed = datetime.strptime(date_str, date_format)
        if end_of_day:
            parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    except (ValueError, TypeError):
        return None


def apply_date_filter(
    queryset: QuerySet,
    start_date: Optional[str],
    end_date: Optional[str],
    date_field: str = 'date',
    date_format: str = '%Y-%m-%d'
) -> QuerySet:
    """
    Apply date range filter to a queryset.

    Args:
        queryset: Django QuerySet to filter
        start_date: Start date string (inclusive)
        end_date: End date string (inclusive)
        date_field: Name of the date field to filter on (supports lookups like 'supply__date')
        date_format: Expected date format for parsing

    Returns:
        Filtered QuerySet

    Example:
        >>> qs = Supply.objects.all()
        >>> qs = apply_date_filter(qs, '2024-01-01', '2024-01-31', 'date')
        >>> # For related fields:
        >>> items = SupplyItem.objects.all()
        >>> items = apply_date_filter(items, '2024-01-01', '2024-01-31', 'supply__date')
    """
    start = parse_date_param(start_date, end_of_day=False, date_format=date_format)
    end = parse_date_param(end_date, end_of_day=True, date_format=date_format)

    if start:
        queryset = queryset.filter(**{f'{date_field}__gte': start})
    if end:
        queryset = queryset.filter(**{f'{date_field}__lte': end})

    return queryset


def get_period_dates(
    end_date_str: Optional[str],
    period_months: int = 12,
    date_format: str = '%Y-%m-%d'
) -> tuple[datetime, datetime]:
    """
    Calculate start and end dates for a period ending at given date.

    Args:
        end_date_str: End date string (if None, uses current date)
        period_months: Number of months to look back
        date_format: Expected date format

    Returns:
        Tuple of (start_date, end_date) as timezone-aware datetimes

    Example:
        >>> start, end = get_period_dates('2024-06-30', period_months=6)
        >>> # Returns dates from ~2024-01-01 to 2024-06-30
    """
    from datetime import timedelta

    if end_date_str:
        end_date = parse_date_param(end_date_str, end_of_day=True, date_format=date_format)
        if not end_date:
            end_date = timezone.now()
    else:
        end_date = timezone.now()

    # Calculate start date using approximate month length (30 days)
    start_date = end_date - timedelta(days=period_months * 30)

    return start_date, end_date
