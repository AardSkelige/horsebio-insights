"""
DRF Serializers for the HorseBio API.
Provides consistent data serialization, validation, and documentation.
"""
from typing import Any, Dict, Optional
from decimal import Decimal
from rest_framework import serializers
from core.models import (
    Counterparty,
    Product,
    RawMaterial,
    Shipment,
    ShipmentItem,
    RawMaterialUsage,
    Supply,
    SupplyItem,
    PurchaseOrder,
    PurchaseOrderItem,
)


# =============================================================================
# Base Serializers
# =============================================================================

class DecimalFloatField(serializers.DecimalField):
    """Custom decimal field that serializes to float for JSON compatibility."""

    def to_representation(self, value) -> Optional[float]:
        if value is None:
            return None
        return float(value)


class BaseModelSerializer(serializers.ModelSerializer):
    """Base serializer with common configuration."""

    class Meta:
        abstract = True

    def get_float_value(self, value, default: float = 0.0) -> float:
        """Safely convert a value to float."""
        if value is None:
            return default
        try:
            float_val = float(value)
            return float_val if float_val == float_val else default  # NaN check
        except (ValueError, TypeError):
            return default


# =============================================================================
# Counterparty Serializers
# =============================================================================

class CounterpartySerializer(BaseModelSerializer):
    """Serializer for Counterparty model."""

    class Meta:
        model = Counterparty
        fields = ['id', 'name', 'external_id', 'is_legacy']
        read_only_fields = ['id', 'external_id']


class CounterpartyListSerializer(BaseModelSerializer):
    """Serializer for counterparty list views with aggregated data."""
    total_sales = DecimalFloatField(max_digits=15, decimal_places=2, read_only=True, required=False)
    shipments_count = serializers.IntegerField(read_only=True, required=False)
    total_products = serializers.IntegerField(read_only=True, required=False)
    last_shipment = serializers.DateTimeField(read_only=True, required=False)

    class Meta:
        model = Counterparty
        fields = [
            'id', 'name', 'total_sales', 'shipments_count',
            'total_products', 'last_shipment'
        ]


class CounterpartyDetailSerializer(CounterpartySerializer):
    """Serializer for counterparty detail views."""
    legacy_records = CounterpartySerializer(many=True, read_only=True)
    all_related_ids = serializers.ListField(child=serializers.IntegerField(), read_only=True)

    class Meta(CounterpartySerializer.Meta):
        fields = CounterpartySerializer.Meta.fields + ['legacy_records', 'all_related_ids']


# =============================================================================
# Product Serializers
# =============================================================================

class ProductSerializer(BaseModelSerializer):
    """Serializer for Product model."""

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'external_id', 'group', 'subgroup',
            'article', 'code', 'uom_name', 'description'
        ]
        read_only_fields = ['id', 'external_id']


class ProductListSerializer(BaseModelSerializer):
    """Serializer for product list views with aggregated data."""
    total_quantity = DecimalFloatField(max_digits=15, decimal_places=2, read_only=True, required=False)
    average_price = DecimalFloatField(max_digits=15, decimal_places=2, read_only=True, required=False)
    total_sum = DecimalFloatField(max_digits=15, decimal_places=2, read_only=True, required=False)
    shipments_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'group', 'subgroup', 'total_quantity',
            'average_price', 'total_sum', 'shipments_count'
        ]


# =============================================================================
# Raw Material Serializers
# =============================================================================

class RawMaterialSerializer(BaseModelSerializer):
    """Serializer for RawMaterial model."""

    class Meta:
        model = RawMaterial
        fields = [
            'id', 'name', 'external_id', 'group', 'article',
            'code', 'uom_name', 'description'
        ]
        read_only_fields = ['id', 'external_id']


class RawMaterialListSerializer(BaseModelSerializer):
    """Serializer for material list views with aggregated data."""
    total_usage = DecimalFloatField(max_digits=15, decimal_places=2, read_only=True, required=False)
    shipments_count = serializers.IntegerField(read_only=True, required=False)
    suppliers_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = RawMaterial
        fields = [
            'id', 'name', 'code', 'group', 'uom_name',
            'total_usage', 'shipments_count', 'suppliers_count'
        ]


class RawMaterialUsageSerializer(BaseModelSerializer):
    """Serializer for RawMaterialUsage model."""
    raw_material = RawMaterialSerializer(read_only=True)
    quantity = DecimalFloatField(max_digits=10, decimal_places=2)

    class Meta:
        model = RawMaterialUsage
        fields = ['id', 'raw_material', 'quantity']


# =============================================================================
# Shipment Serializers
# =============================================================================

class ShipmentItemSerializer(BaseModelSerializer):
    """Serializer for ShipmentItem model."""
    product = ProductSerializer(read_only=True)
    quantity = DecimalFloatField(max_digits=10, decimal_places=2)
    price = DecimalFloatField(max_digits=10, decimal_places=2)
    total_sum = serializers.SerializerMethodField()
    raw_material_usages = RawMaterialUsageSerializer(many=True, read_only=True)

    class Meta:
        model = ShipmentItem
        fields = ['id', 'product', 'quantity', 'price', 'total_sum', 'raw_material_usages']

    def get_total_sum(self, obj) -> float:
        return float(obj.quantity * obj.price)


class ShipmentSerializer(BaseModelSerializer):
    """Serializer for Shipment model."""
    counterparty = CounterpartySerializer(read_only=True)

    class Meta:
        model = Shipment
        fields = ['id', 'external_id', 'number', 'date', 'counterparty', 'moysklad_updated']
        read_only_fields = ['id', 'external_id', 'moysklad_updated']


class ShipmentDetailSerializer(ShipmentSerializer):
    """Serializer for shipment detail views with items."""
    items = ShipmentItemSerializer(many=True, read_only=True)
    items_count = serializers.SerializerMethodField()
    total_sum = serializers.SerializerMethodField()

    class Meta(ShipmentSerializer.Meta):
        fields = ShipmentSerializer.Meta.fields + ['items', 'items_count', 'total_sum']

    def get_items_count(self, obj) -> int:
        return obj.items.count()

    def get_total_sum(self, obj) -> float:
        return sum(item.quantity * item.price for item in obj.items.all())


class ShipmentListSerializer(BaseModelSerializer):
    """Lightweight serializer for shipment list views."""
    counterparty_name = serializers.CharField(source='counterparty.name', read_only=True)
    items_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Shipment
        fields = ['id', 'number', 'date', 'counterparty_name', 'items_count']


# =============================================================================
# Supply Serializers
# =============================================================================

class SupplyItemSerializer(BaseModelSerializer):
    """Serializer for SupplyItem model."""
    raw_material = RawMaterialSerializer(read_only=True)
    quantity = DecimalFloatField(max_digits=10, decimal_places=3)
    price = DecimalFloatField(max_digits=15, decimal_places=2)
    total = DecimalFloatField(max_digits=15, decimal_places=2)

    class Meta:
        model = SupplyItem
        fields = ['id', 'raw_material', 'quantity', 'price', 'total']


class SupplySerializer(BaseModelSerializer):
    """Serializer for Supply model."""
    counterparty = CounterpartySerializer(read_only=True)
    sum = DecimalFloatField(max_digits=15, decimal_places=2)

    class Meta:
        model = Supply
        fields = ['id', 'external_id', 'number', 'date', 'counterparty', 'sum', 'moysklad_updated']
        read_only_fields = ['id', 'external_id', 'moysklad_updated']


class SupplyDetailSerializer(SupplySerializer):
    """Serializer for supply detail views with items."""
    items = SupplyItemSerializer(many=True, read_only=True)
    items_count = serializers.SerializerMethodField()

    class Meta(SupplySerializer.Meta):
        fields = SupplySerializer.Meta.fields + ['items', 'items_count']

    def get_items_count(self, obj) -> int:
        return obj.items.count()


class SupplyListSerializer(BaseModelSerializer):
    """Lightweight serializer for supply list views."""
    supplier_name = serializers.CharField(source='counterparty.name', read_only=True)
    supplier_id = serializers.IntegerField(source='counterparty.id', read_only=True)
    sum = DecimalFloatField(max_digits=15, decimal_places=2)
    items_count = serializers.IntegerField(read_only=True, required=False)
    total_quantity = DecimalFloatField(max_digits=15, decimal_places=2, read_only=True, required=False)

    class Meta:
        model = Supply
        fields = [
            'id', 'number', 'date', 'supplier_name', 'supplier_id',
            'sum', 'items_count', 'total_quantity'
        ]


# =============================================================================
# Purchase Order Serializers
# =============================================================================

class PurchaseOrderItemSerializer(BaseModelSerializer):
    """Serializer for PurchaseOrderItem model."""
    raw_material = RawMaterialSerializer(read_only=True)
    quantity = DecimalFloatField(max_digits=10, decimal_places=3)
    price = DecimalFloatField(max_digits=15, decimal_places=2)
    total = DecimalFloatField(max_digits=15, decimal_places=2)
    shipped_quantity = DecimalFloatField(max_digits=10, decimal_places=3)
    waiting_quantity = DecimalFloatField(max_digits=10, decimal_places=3)

    class Meta:
        model = PurchaseOrderItem
        fields = [
            'id', 'raw_material', 'quantity', 'price', 'total',
            'shipped_quantity', 'waiting_quantity'
        ]


class PurchaseOrderSerializer(BaseModelSerializer):
    """Serializer for PurchaseOrder model."""
    counterparty = CounterpartySerializer(read_only=True)
    sum = DecimalFloatField(max_digits=15, decimal_places=2)
    lead_time = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = PurchaseOrder
        fields = [
            'id', 'external_id', 'number', 'date', 'created',
            'counterparty', 'status', 'sum', 'lead_time', 'moysklad_updated'
        ]
        read_only_fields = ['id', 'external_id', 'moysklad_updated']


class PurchaseOrderDetailSerializer(PurchaseOrderSerializer):
    """Serializer for purchase order detail views."""
    items = PurchaseOrderItemSerializer(many=True, read_only=True)
    supplies = SupplyListSerializer(many=True, read_only=True)

    class Meta(PurchaseOrderSerializer.Meta):
        fields = PurchaseOrderSerializer.Meta.fields + ['items', 'supplies']


# =============================================================================
# Statistics & Analytics Serializers
# =============================================================================

class StatisticsSerializer(serializers.Serializer):
    """Serializer for general statistics."""
    shipments_count = serializers.IntegerField()
    shipments_current_month = serializers.IntegerField()
    supplies_count = serializers.IntegerField()
    supplies_current_month = serializers.IntegerField()
    last_manual_update = serializers.CharField(allow_null=True)
    last_auto_update = serializers.CharField(allow_null=True)
    latest_update_type = serializers.CharField(allow_null=True)
    latest_update_time = serializers.CharField(allow_null=True)


class MonthlyDataSerializer(serializers.Serializer):
    """Serializer for monthly statistics."""
    month = serializers.CharField()
    year = serializers.IntegerField()
    shipments = serializers.IntegerField()
    supplies = serializers.IntegerField()


class PeriodSerializer(serializers.Serializer):
    """Serializer for period information."""
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    months = serializers.IntegerField()


class ABCCategoryMetricsSerializer(serializers.Serializer):
    """Serializer for ABC analysis category metrics."""
    product_count = serializers.IntegerField()
    revenue = DecimalFloatField(max_digits=15, decimal_places=2)
    revenue_share = DecimalFloatField(max_digits=5, decimal_places=4)
    quantity = DecimalFloatField(max_digits=15, decimal_places=2)
    avg_monthly_revenue = DecimalFloatField(max_digits=15, decimal_places=2)
    avg_monthly_quantity = DecimalFloatField(max_digits=15, decimal_places=2)


class ABCProductSerializer(serializers.Serializer):
    """Serializer for ABC analysis product data."""
    id = serializers.IntegerField()
    name = serializers.CharField()
    article = serializers.CharField(allow_null=True)
    group = serializers.CharField(allow_null=True)
    subgroup = serializers.CharField(allow_null=True)
    metrics = serializers.DictField()


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


# =============================================================================
# Response Wrapper Serializers
# =============================================================================

class APIResponseSerializer(serializers.Serializer):
    """Standard API response wrapper."""
    status = serializers.ChoiceField(choices=['success', 'error'])
    data = serializers.DictField(required=False)
    message = serializers.CharField(required=False)
    code = serializers.CharField(required=False)
    error_id = serializers.CharField(required=False)


class PaginatedResponseSerializer(serializers.Serializer):
    """Paginated API response."""
    status = serializers.CharField(default='success')
    data = serializers.DictField()
    total = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
