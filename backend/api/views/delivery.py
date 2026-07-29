"""API калькулятора стоимости доставки.

Эндпоинты:
- POST /api/delivery/estimate  — оценка доставки по заказу или ручному списку;
- GET  /api/delivery/products  — поиск товаров для ручного ввода позиций.

Вся доменная логика — в api.services.delivery (раскладка + тарифы ПЭК/СДЭК).
Здесь только разбор запроса и формат ответа.
"""

import logging

from rest_framework.decorators import api_view
from rest_framework.response import Response

from api.services.delivery import estimate as estimate_service
from api.services.delivery import ms_source
from api.services.delivery import pec_calculator

logger = logging.getLogger(__name__)


@api_view(["POST"])
def estimate(request):
    """Оценка доставки. Тело:
    {mode: 'order'|'manual', order: '06442', positions: [{href, qty, name?}],
     to_city: 'Санкт-Петербург'}.

    Ответ: {blocked, missing, packing, carriers, ...} либо {error} со статусом 400."""
    data = request.data or {}
    mode = (data.get("mode") or "order").strip()
    to_city = data.get("to_city") or ""

    try:
        if mode == "manual":
            result = estimate_service.estimate_by_positions(data.get("positions") or [], to_city)
        else:
            result = estimate_service.estimate_by_order(data.get("order") or "", to_city)
    except Exception:
        logger.exception("Ошибка расчёта доставки")
        return Response({"error": "внутренняя ошибка расчёта доставки"}, status=500)

    if result.get("error"):
        return Response(result, status=400)
    return Response(result)


@api_view(["GET"])
def products(request):
    """Поиск товаров для ручного ввода: ?q=строка → [{href, name, code}]."""
    query = (request.query_params.get("q") or "").strip()
    if len(query) < 2:
        return Response([])
    try:
        return Response(ms_source.search_products(query))
    except Exception:
        logger.exception("Ошибка поиска товаров для доставки")
        return Response({"error": "ошибка поиска товаров"}, status=500)


@api_view(["GET"])
def recent_orders(request):
    """Последние заказы (не маркетплейсные) для выбора в один клик:
    [{id, name, counterparty, city, sum, moment}]."""
    try:
        return Response(ms_source.recent_orders())
    except Exception:
        logger.exception("Ошибка загрузки последних заказов")
        return Response({"error": "не удалось загрузить последние заказы"}, status=500)


@api_view(["GET"])
def cities(request):
    """Подсказки городов из справочника перевозчика: ?q=масква → Москва."""
    query = (request.query_params.get("q") or "").strip()
    if len(query) < 2:
        return Response([])
    try:
        return Response(pec_calculator.suggest_towns(query))
    except Exception:
        logger.exception("Ошибка поиска города для доставки")
        return Response({"error": "не удалось загрузить справочник городов"}, status=502)
