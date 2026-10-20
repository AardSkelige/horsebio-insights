"""
DRF Serializers for the HorseBio API.
Provides consistent data serialization, validation, and documentation.
"""
from typing import Any, Dict
from rest_framework import serializers


# =============================================================================
# Input/Validation Serializers
# =============================================================================

class DateRangeSerializer(serializers.Serializer):
    """Serializer for date range input validation."""
    start_date = serializers.DateField(required=False, allow_null=True)
    end_date = serializers.DateField(required=False, allow_null=True)

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        start = data.get('start_date')
        end = data.get('end_date')
        if start and end and start > end:
            raise serializers.ValidationError(
                "start_date must be before end_date"
            )
        return data


class PaginationSerializer(serializers.Serializer):
    """Serializer for pagination input validation."""
    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=500, default=10)


class SortingSerializer(serializers.Serializer):
    """Serializer for sorting input validation."""
    sort_field = serializers.CharField(required=False, default='name')
    sort_order = serializers.ChoiceField(choices=['asc', 'desc'], default='desc')

    def validate_sort_field(self, value: str) -> str:
        allowed_fields = self.context.get('allowed_sort_fields')
        if allowed_fields is not None and value not in allowed_fields:
            raise serializers.ValidationError("Unsupported sort field")
        return value


class SearchFilterSerializer(serializers.Serializer):
    """Serializer for search and filter input validation."""
    search = serializers.CharField(required=False, allow_blank=True, default='')
    group = serializers.CharField(required=False, allow_blank=True, default='')


class ListQuerySerializer(
    DateRangeSerializer,
    PaginationSerializer,
    SortingSerializer,
    SearchFilterSerializer,
):
    """Единая валидация query-параметров аналитических списков.

    API исторически использует camelCase, а базовые serializers — snake_case.
    ``from_query_params`` централизованно выполняет это преобразование, чтобы
    views больше не разбирали числа и даты вручную.
    """
    subgroup = serializers.CharField(required=False, allow_blank=True, default='')
    sales_channel = serializers.CharField(required=False, allow_blank=True, default='')

    @classmethod
    def from_query_params(
        cls,
        query_params,
        *,
        default_sort_field: str,
        allowed_sort_fields,
    ) -> Dict[str, Any]:
        aliases = {
            'page': ('page',),
            'page_size': ('pageSize', 'page_size'),
            'search': ('search',),
            'group': ('group',),
            'subgroup': ('subgroup',),
            'sales_channel': ('salesChannel', 'sales_channel'),
            'start_date': ('startDate', 'start_date'),
            'end_date': ('endDate', 'end_date'),
            'sort_field': ('sortField', 'sort_field'),
            'sort_order': ('sortOrder', 'sort_order'),
        }
        data = {}
        for target, source_names in aliases.items():
            for source_name in source_names:
                if source_name in query_params:
                    data[target] = query_params.get(source_name)
                    break
        data.setdefault('sort_field', default_sort_field)

        serializer = cls(
            data=data,
            context={'allowed_sort_fields': set(allowed_sort_fields)},
        )
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data
