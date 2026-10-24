from django.core.cache import cache


def latest_document_update():
    from core.models import Shipment, Supply

    stamps = [
        Shipment.objects.order_by('-moysklad_updated').values_list('moysklad_updated', flat=True).first(),
        Supply.objects.order_by('-moysklad_updated').values_list('moysklad_updated', flat=True).first(),
    ]
    stamps = [value for value in stamps if value]
    return max(stamps) if stamps else None


def latest_data_update():
    cached = [
        cache.get('last_manual_update'),
        cache.get('last_auto_sync_update'),
        cache.get('last_successful_update'),
    ]
    candidates = [value for value in cached if hasattr(value, 'isoformat')]
    return max(candidates) if candidates else latest_document_update()
