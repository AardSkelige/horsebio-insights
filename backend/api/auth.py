# backend/api/auth.py
import json
from functools import wraps
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.db import transaction
from django.db.models import Avg, Count, Sum, Max
from django.db.models.functions import ExtractHour
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .models import UserActivityLog, UserHomePreference, UserPageEvent, UserSession, UserPageAccess
from .access import pages_catalog, sanitize_page_keys, user_allowed_page_keys, ASSIGNABLE_PAGE_KEYS


MAX_PINNED_HOME_PATHS = 3


def login_required_api(view_func):
    """
    Декоратор для защиты API endpoints.
    Возвращает JSON с ошибкой 401 для неаутентифицированных запросов.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({
                'status': 'error',
                'message': 'Требуется авторизация'
            }, status=401)
        return view_func(request, *args, **kwargs)
    return wrapper


def _get_client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _log_activity(request, user, action):
    try:
        UserActivityLog.objects.create(
            user=user,
            action=action,
            ip_address=_get_client_ip(request) or None,
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:1000],
        )
    except Exception:
        # Login/logout should not fail because activity logging failed.
        pass


def _serialize_activity(item):
    return {
        'id': item.id,
        'action': item.action,
        'actionLabel': item.get_action_display(),
        'createdAt': item.created_at.isoformat(),
        'ipAddress': item.ip_address or '',
        'userAgent': item.user_agent or '',
    }


@ensure_csrf_cookie
@require_http_methods(["POST"])
def login_view(request):
    # Support both JSON and form data
    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid JSON'
            }, status=400)
    else:
        data = request.POST

    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return JsonResponse({
            'status': 'error',
            'message': 'Необходимо указать имя пользователя и пароль'
        }, status=400)

    user = authenticate(username=username, password=password)

    if user is None:
        return JsonResponse({
            'status': 'error',
            'message': 'Неверное имя пользователя или пароль'
        }, status=401)

    login(request, user)
    _log_activity(request, user, UserActivityLog.ACTION_LOGIN)

    try:
        UserSession.objects.update_or_create(
            session_key=request.session.session_key,
            defaults={
                'user': user,
                'ip_address': _get_client_ip(request) or None,
                'user_agent': request.META.get('HTTP_USER_AGENT', '')[:1000],
                'last_seen_at': timezone.now(),
            },
        )
    except Exception:
        pass

    return JsonResponse({
        'status': 'success',
        'message': 'Успешная авторизация'
    })


@ensure_csrf_cookie
@require_http_methods(["GET"])
def check_auth(request):
    u = request.user
    return JsonResponse({
        'isAuthenticated': u.is_authenticated,
        'isSuperuser': u.is_authenticated and u.is_superuser,
        'username': u.username if u.is_authenticated else '',
        'email': u.email if u.is_authenticated else '',
        'firstName': u.first_name if u.is_authenticated else '',
        'lastName': u.last_name if u.is_authenticated else '',
        # Разрешённые страницы — фронт по ним фильтрует меню и роуты
        'allowedPages': sorted(user_allowed_page_keys(u)) if u.is_authenticated else [],
    })


@require_http_methods(["GET"])
@login_required_api
def activity_view(request):
    logs = UserActivityLog.objects.filter(user=request.user).order_by('-created_at')[:20]
    return JsonResponse({
        'status': 'success',
        'activity': [_serialize_activity(item) for item in logs],
    })


@require_http_methods(["POST"])
@login_required_api
def track_page_view(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

    page_path = str(data.get('path', ''))[:200]
    page_name = str(data.get('name', page_path))[:100]
    duration = int(data.get('duration', 0))

    if not page_path or duration < 2:
        return JsonResponse({'status': 'ok'})

    UserPageEvent.objects.create(
        user=request.user,
        page_path=page_path,
        page_name=page_name,
        duration_seconds=min(duration, 7200),
    )
    return JsonResponse({'status': 'ok'})


def _validate_pinned_paths(value):
    if not isinstance(value, list):
        return None

    result = []
    for path in value:
        if not isinstance(path, str):
            return None
        path = path.strip()
        if (
            not path.startswith('/')
            or path.startswith('//')
            or len(path) > 200
            or path in {'/', '/login', '/profile'}
        ):
            return None
        if path not in result:
            result.append(path)

    if len(result) > MAX_PINNED_HOME_PATHS:
        return None
    return result


def _recent_page_paths(user, limit=6):
    paths = []
    rows = (
        UserPageEvent.objects
        .filter(user=user)
        .order_by('-created_at')
        .values_list('page_path', flat=True)[:100]
    )
    for path in rows:
        if path in {'/', '/login', '/profile'} or path in paths:
            continue
        paths.append(path)
        if len(paths) == limit:
            break
    return paths


def _latest_data_update():
    """Возвращает последнее известное обновление данных без тяжёлой статистики."""
    from django.core.cache import cache
    from core.models import Shipment, Supply

    cached = [
        cache.get('last_manual_update'),
        cache.get('last_auto_sync_update'),
        cache.get('last_successful_update'),
    ]
    candidates = [value for value in cached if hasattr(value, 'isoformat')]
    if candidates:
        return max(candidates)

    shipment_update = (
        Shipment.objects.order_by('-moysklad_updated')
        .values_list('moysklad_updated', flat=True)
        .first()
    )
    supply_update = (
        Supply.objects.order_by('-moysklad_updated')
        .values_list('moysklad_updated', flat=True)
        .first()
    )
    fallback = [value for value in (shipment_update, supply_update) if value]
    return max(fallback) if fallback else None


@require_http_methods(["GET", "PATCH"])
@login_required_api
def home_preferences_view(request):
    preference, _ = UserHomePreference.objects.get_or_create(user=request.user)

    if request.method == 'PATCH':
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'status': 'error', 'message': 'Некорректный JSON'}, status=400)

        pinned_paths = _validate_pinned_paths(data.get('pinnedPaths'))
        if pinned_paths is None:
            return JsonResponse({
                'status': 'error',
                'message': f'Можно закрепить до {MAX_PINNED_HOME_PATHS} разделов',
            }, status=400)
        preference.pinned_paths = pinned_paths
        preference.save(update_fields=['pinned_paths', 'updated_at'])

    updated_at = _latest_data_update()
    return JsonResponse({
        'status': 'success',
        'data': {
            'pinnedPaths': preference.pinned_paths,
            'recentPaths': _recent_page_paths(request.user),
            'dataUpdatedAt': updated_at.isoformat() if updated_at else None,
        },
    })


def _compute_badge(user, page_qs, sessions_this_month):
    badge = {'title': 'Цифровой бродяга', 'description': 'Изучаешь систему со всех сторон'}

    top = page_qs.values('page_name').annotate(n=Count('id')).order_by('-n').first()
    if top:
        page_badges = {
            'ABC Анализ':        ('ABC-маньяк',            'Категоризируешь всё что движется'),
            'ДДС':               ('Денежный шпион',         'Ни один рубль не проскочит мимо'),
            'FBO Заказы':        ('Логистический гений',    'Держишь поставки под полным контролем'),
            'Производство':      ('Инженер-рационализатор', 'Сырьё посчитано до грамма'),
            'Мониторинг':        ('Складской детектив',     'Ни одна позиция не ускользнёт'),
            'Сезонность':        ('Охотник за трендами',    'Видишь паттерны там, где другие — хаос'),
            'Помощник закупок':  ('Оптимизатор',            'Закупаешь умнее всех'),
            'Группы клиентов':   ('Профайлер',              'Знаешь клиентов лучше, чем они сами'),
            'Покупатели':        ('Профайлер',              'Знаешь клиентов лучше, чем они сами'),
            'Товары':            ('Товаровед',              'В курсе каждого SKU'),
            'Материалы':         ('Материальный мир',       'Знаешь расход до последнего грамма'),
            'Поставщики':        ('Переговорщик',           'Держишь поставщиков в тонусе'),
            'Ozon':              ('Маркетплейс-ниндзя',     'Завоёвываешь полки незаметно'),
        }
        entry = page_badges.get(top['page_name'])
        if entry:
            badge = {'title': entry[0], 'description': entry[1]}

    avg_hour = (
        UserActivityLog.objects
        .filter(user=user, action=UserActivityLog.ACTION_LOGIN)
        .annotate(hour=ExtractHour('created_at'))
        .aggregate(avg=Avg('hour'))['avg']
    )
    if avg_hour is not None:
        if avg_hour >= 21 or avg_hour < 5:
            badge = {'title': 'Ночная сова', 'description': 'Лучшие инсайты приходят после полуночи'}
        elif avg_hour < 8:
            badge = {'title': 'Ранняя пташка', 'description': 'Данные не ждут — ты уже в деле'}

    if sessions_this_month >= 25:
        badge = {'title': 'Невозможно остановить', 'description': f'{sessions_this_month} сессий за месяц — это не норма'}

    return badge


@require_http_methods(["GET"])
@login_required_api
def usage_view(request):
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    sessions_this_month = UserActivityLog.objects.filter(
        user=request.user,
        action=UserActivityLog.ACTION_LOGIN,
        created_at__gte=month_start,
    ).count()

    page_qs = UserPageEvent.objects.filter(user=request.user, created_at__gte=month_start)
    total_seconds = page_qs.aggregate(total=Sum('duration_seconds'))['total'] or 0

    top_pages = list(
        page_qs
        .values('page_path', 'page_name')
        .annotate(visits=Count('id'), avg_duration=Avg('duration_seconds'))
        .order_by('-visits')[:10]
    )

    badge = _compute_badge(request.user, page_qs, sessions_this_month)

    return JsonResponse({
        'status': 'success',
        'data': {
            'sessions_this_month': sessions_this_month,
            'total_minutes_this_month': total_seconds // 60,
            'top_pages': top_pages,
            'badge': badge,
        },
    })


@require_http_methods(["GET"])
@login_required_api
def admin_analytics_view(request):
    if not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Доступ запрещён'}, status=403)

    now = timezone.now()

    # Parse ?month=YYYY-MM, default to current month
    month_param = request.GET.get('month', '')
    try:
        year, month = map(int, month_param.split('-'))
        period_start = now.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)
    except (ValueError, AttributeError):
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    if period_start.month == 12:
        period_end = period_start.replace(year=period_start.year + 1, month=1)
    else:
        period_end = period_start.replace(month=period_start.month + 1)

    day7_start = now - timezone.timedelta(days=7)
    day30_start = now - timezone.timedelta(days=30)

    User = get_user_model()

    active_7d = (
        UserActivityLog.objects
        .filter(action=UserActivityLog.ACTION_LOGIN, created_at__gte=day7_start)
        .values('user').distinct().count()
    )
    active_30d = (
        UserActivityLog.objects
        .filter(action=UserActivityLog.ACTION_LOGIN, created_at__gte=day30_start)
        .values('user').distinct().count()
    )

    sessions_period = UserActivityLog.objects.filter(
        action=UserActivityLog.ACTION_LOGIN,
        created_at__gte=period_start,
        created_at__lt=period_end,
    ).count()

    unique_users_period = (
        UserActivityLog.objects
        .filter(action=UserActivityLog.ACTION_LOGIN, created_at__gte=period_start, created_at__lt=period_end)
        .values('user').distinct().count()
    )

    # Топ страниц — только активность обычных пользователей: посещения суперпользователей
    # (и, как следствие, admin-only страницы вроде /checks) не искажают картину.
    top_pages = list(
        UserPageEvent.objects
        .filter(created_at__gte=period_start, created_at__lt=period_end)
        .exclude(user__is_superuser=True)
        .values('page_path', 'page_name')
        .annotate(visits=Count('id'), unique_users=Count('user', distinct=True), avg_duration=Avg('duration_seconds'))
        .order_by('-visits')[:10]
    )

    login_qs = (
        UserActivityLog.objects
        .filter(action=UserActivityLog.ACTION_LOGIN, created_at__gte=period_start, created_at__lt=period_end)
        .values('user')
        .annotate(sessions=Count('id'))
    )
    sessions_by_user = {row['user']: row['sessions'] for row in login_qs}

    time_qs = (
        UserPageEvent.objects
        .filter(created_at__gte=period_start, created_at__lt=period_end)
        .values('user')
        .annotate(total_seconds=Sum('duration_seconds'))
    )
    time_by_user = {row['user']: row['total_seconds'] for row in time_qs}

    last_login_qs = (
        UserActivityLog.objects
        .filter(action=UserActivityLog.ACTION_LOGIN)
        .values('user')
        .annotate(last_login=Max('created_at'))
    )
    last_login_by_user = {row['user']: row['last_login'] for row in last_login_qs}

    users = []
    for u in User.objects.filter(is_active=True).order_by('username'):
        last = last_login_by_user.get(u.id)
        users.append({
            'id': u.id,
            'username': u.username,
            'fullName': ' '.join(filter(None, [u.first_name, u.last_name])),
            'isSuperuser': u.is_superuser,
            'sessionsPeriod': sessions_by_user.get(u.id, 0),
            'minutesPeriod': (time_by_user.get(u.id) or 0) // 60,
            'lastLogin': last.isoformat() if last else None,
        })

    available_months = [
        f"{d.year}-{d.month:02d}"
        for d in UserActivityLog.objects
        .filter(action=UserActivityLog.ACTION_LOGIN)
        .dates('created_at', 'month', order='DESC')
    ]
    current_month_str = now.strftime('%Y-%m')
    if current_month_str not in available_months:
        available_months.insert(0, current_month_str)

    return JsonResponse({
        'status': 'success',
        'data': {
            'period': period_start.strftime('%Y-%m'),
            'totalUsers': User.objects.filter(is_active=True).count(),
            'active7d': active_7d,
            'active30d': active_30d,
            'sessionsPeriod': sessions_period,
            'uniqueUsersPeriod': unique_users_period,
            'topPages': top_pages,
            'users': users,
            'availableMonths': available_months,
        },
    })


@require_http_methods(["GET", "POST"])
@login_required_api
def pages_access_view(request):
    """
    Управление постраничным доступом (только суперпользователь).

    GET  — каталог назначаемых страниц + список активных не-суперпользователей
           с их разрешёнными страницами.
    POST — сохранить доступы: {"user_id": N, "pages": ["abc", "cash-flow", ...]}.
    """
    if not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Доступ запрещён'}, status=403)

    User = get_user_model()

    if request.method == "GET":
        access_rows = UserPageAccess.objects.values_list('user_id', 'page_key')
        by_user = {}
        for uid, key in access_rows:
            by_user.setdefault(uid, []).append(key)

        users = []
        for u in User.objects.filter(is_active=True, is_superuser=False).order_by('username'):
            users.append({
                'id': u.id,
                'username': u.username,
                'fullName': ' '.join(filter(None, [u.first_name, u.last_name])),
                'pages': sorted(by_user.get(u.id, [])),
            })

        return JsonResponse({
            'status': 'success',
            'data': {
                'pages': pages_catalog(),
                'users': users,
            },
        })

    # POST — сохранить доступы одного пользователя
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'status': 'error', 'message': 'Некорректный запрос'}, status=400)

    user_id = payload.get('user_id')
    pages = sanitize_page_keys(payload.get('pages', []))

    try:
        target = User.objects.get(id=user_id, is_active=True)
    except User.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Пользователь не найден'}, status=404)

    if target.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Права суперпользователя не редактируются'}, status=400)

    with transaction.atomic():
        UserPageAccess.objects.filter(user=target).delete()
        UserPageAccess.objects.bulk_create(
            [UserPageAccess(user=target, page_key=key) for key in pages]
        )

    return JsonResponse({'status': 'success', 'data': {'user_id': target.id, 'pages': pages}})


@require_http_methods(["POST"])
def logout_view(request):
    if request.user.is_authenticated:
        _log_activity(request, request.user, UserActivityLog.ACTION_LOGOUT)
        try:
            if request.session.session_key:
                UserSession.objects.filter(session_key=request.session.session_key).delete()
        except Exception:
            pass
    logout(request)
    return JsonResponse({
        'status': 'success',
        'message': 'Вы вышли из системы'
    })


@require_http_methods(["GET"])
@login_required_api
def sessions_view(request):
    from django.contrib.sessions.models import Session
    valid_keys = set(Session.objects.values_list('session_key', flat=True))
    UserSession.objects.filter(user=request.user).exclude(session_key__in=valid_keys).delete()

    sessions = UserSession.objects.filter(user=request.user)
    current_key = request.session.session_key

    return JsonResponse({
        'status': 'success',
        'sessions': [
            {
                'id': s.id,
                'ip_address': s.ip_address or '',
                'user_agent': s.user_agent or '',
                'created_at': s.created_at.isoformat(),
                'last_seen_at': s.last_seen_at.isoformat(),
                'is_current': s.session_key == current_key,
            }
            for s in sessions
        ],
    })


@require_http_methods(["DELETE"])
@login_required_api
def session_revoke_view(request, session_id):
    try:
        user_session = UserSession.objects.get(id=session_id, user=request.user)
    except UserSession.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Сессия не найдена'}, status=404)

    from django.contrib.sessions.models import Session
    Session.objects.filter(session_key=user_session.session_key).delete()
    user_session.delete()

    return JsonResponse({'status': 'success'})
