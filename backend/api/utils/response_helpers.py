"""
Response formatting utilities for API views.
Consolidates duplicated data conversion code from multiple views.
"""
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union


def to_float_safe(value: Any, default: float = 0.0) -> float:
    """
    Safely convert a value to float, handling None, NaN, and invalid values.

    Args:
        value: Value to convert (can be Decimal, int, float, str, or None)
        default: Default value to return if conversion fails

    Returns:
        Float value or default

    Example:
        >>> to_float_safe(Decimal('10.5'))
        10.5
        >>> to_float_safe(None)
        0.0
        >>> to_float_safe('invalid')
        0.0
        >>> to_float_safe(float('nan'))
        0.0
    """
    if value is None:
        return default

    try:
        float_value = float(value)
        # Check for NaN (NaN != NaN is True)
        if float_value != float_value:
            return default
        return float_value
    except (ValueError, TypeError):
        return default


def format_decimal_fields(data: Dict[str, Any], fields: List[str]) -> Dict[str, Any]:
    """
    Convert specified Decimal fields to float in a dictionary.

    Args:
        data: Dictionary containing data
        fields: List of field names to convert

    Returns:
        Dictionary with converted fields

    Example:
        >>> data = {'quantity': Decimal('10.5'), 'name': 'Test'}
        >>> format_decimal_fields(data, ['quantity'])
        {'quantity': 10.5, 'name': 'Test'}
    """
    result = data.copy()
    for field in fields:
        if field in result:
            result[field] = to_float_safe(result[field])
    return result


def format_nested_decimal_fields(
    data: Dict[str, Any],
    nested_path: str,
    fields: List[str]
) -> Dict[str, Any]:
    """
    Convert Decimal fields in nested dictionaries.

    Args:
        data: Dictionary containing nested data
        nested_path: Dot-separated path to nested dict (e.g., 'stats.price')
        fields: List of field names to convert in the nested dict

    Returns:
        Dictionary with converted fields

    Example:
        >>> data = {'stats': {'revenue': Decimal('1000')}}
        >>> format_nested_decimal_fields(data, 'stats', ['revenue'])
        {'stats': {'revenue': 1000.0}}
    """
    result = data.copy()
    parts = nested_path.split('.')
    current = result

    # Navigate to parent of target
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            return result
        current = current[part]

    # Convert fields in target dict
    target_key = parts[-1]
    if target_key in current and isinstance(current[target_key], dict):
        current[target_key] = format_decimal_fields(current[target_key], fields)

    return result


def format_list_decimal_fields(
    items: List[Dict[str, Any]],
    fields: List[str]
) -> List[Dict[str, Any]]:
    """
    Convert Decimal fields in a list of dictionaries.

    Args:
        items: List of dictionaries
        fields: List of field names to convert

    Returns:
        List with converted fields

    Example:
        >>> items = [{'quantity': Decimal('10')}, {'quantity': Decimal('20')}]
        >>> format_list_decimal_fields(items, ['quantity'])
        [{'quantity': 10.0}, {'quantity': 20.0}]
    """
    return [format_decimal_fields(item, fields) for item in items]


def build_paginated_response(
    items: List[Any],
    total: int,
    page: int,
    page_size: int,
    extra_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Build a standardized paginated response.

    Args:
        items: List of items for current page
        total: Total count of all items
        page: Current page number
        page_size: Items per page
        extra_data: Additional data to include in response

    Returns:
        Standardized response dictionary

    Example:
        >>> build_paginated_response([{'id': 1}], total=10, page=1, page_size=10)
        {'status': 'success', 'data': {'items': [{'id': 1}], 'total': 10, 'page': 1, 'page_size': 10}}
    """
    response = {
        'status': 'success',
        'data': {
            'items': items,
            'total': total,
            'page': page,
            'page_size': page_size,
        }
    }

    if extra_data:
        response['data'].update(extra_data)

    return response
