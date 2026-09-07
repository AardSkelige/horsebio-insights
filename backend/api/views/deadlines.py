from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .scripts_monitor import scripts_auth_basic


def _read_deadlines() -> dict | None:
    """Снимок последней проверки — из базы.

    Раньше страница читала файл на томе робота: без тома она была бы пустой
    от каждого деплоя до ближайшего ночного прогона.
    """
    from api.models import PaymentDeadlineSnapshot

    row = PaymentDeadlineSnapshot.objects.first()
    return (row.payload or None) if row else None


def _snapshot_age_hours() -> float | None:
    """Сколько часов снимку. Заменило время изменения файла."""
    from django.utils import timezone
    from api.models import PaymentDeadlineSnapshot

    row = PaymentDeadlineSnapshot.objects.first()
    if row is None:
        return None
    return (timezone.now() - row.updated_at).total_seconds() / 3600


@scripts_auth_basic
@require_http_methods(['GET'])
def get_deadlines(request):
    data = _read_deadlines()
    age = _snapshot_age_hours()

    if data is None:
        return JsonResponse({'status': 'ok', 'available': False})

    return JsonResponse({
        'status': 'ok',
        'available': True,
        'stale': age is not None and age > 26,
        'age_hours': round(age, 1) if age is not None else None,
        **data,
    })
