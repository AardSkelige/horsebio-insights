"""Адаптер публичного калькулятора ПЭК (без ЛК, договора и авторизации).

Два эндпоинта:
- справочник городов:  GET https://pecom.ru/ru/calc/towns.php  (регион→{id:город})
- расчёт:  GET http://calc.pecom.ru/bitrix/components/pecom/calc/ajax.php

Ответ расчёта покомпонентный: auto (перевозка терминал-терминал), deliver
(доставка до двери получателя), take (забор от нас — НЕ используем, груз сами
возим на терминал ПЭК). Отсюда две цены: склад→склад и до двери.
"""

import time
from difflib import SequenceMatcher

import requests

from .box_catalog import Box
from .packing import PackResult

TOWNS_URL = "https://pecom.ru/ru/calc/towns.php"
CALC_URL = "http://calc.pecom.ru/bitrix/components/pecom/calc/ajax.php"

# Публичные эндпоинты ПЭК отклоняют запросы без браузерного User-Agent (403).
_UA = {"User-Agent": "Mozilla/5.0 (compatible; HorseBioInsights/1.0)"}

# Пункт отправления HorseBio — терминал ПЭК, куда сами привозим груз.
DEFAULT_FROM_TOWN_ID = 67131  # Подрезково (Химки)

_TOWNS_CACHE: dict[str, int] | None = None


def _load_towns() -> dict[str, int]:
    """Плоский справочник {название города: id}. Кэшируется в процессе."""
    global _TOWNS_CACHE
    if _TOWNS_CACHE is not None:
        return _TOWNS_CACHE
    resp = requests.get(TOWNS_URL, headers=_UA, timeout=30)
    resp.raise_for_status()
    flat: dict[str, int] = {}
    for cities in resp.json().values():
        if isinstance(cities, dict):
            for cid, name in cities.items():
                flat[str(name)] = int(cid)
    _TOWNS_CACHE = flat
    return flat


def find_town_id(name: str) -> int | None:
    """id города по названию: точное совпадение, иначе первое вхождение подстроки."""
    towns = _load_towns()
    if name in towns:
        return towns[name]
    lowered = name.strip().lower()
    for town_name, tid in towns.items():
        if lowered and lowered in town_name.lower():
            return tid
    return None


def suggest_towns(query: str, limit: int = 8) -> list[dict]:
    """Города ПЭК для автодополнения, включая близкие опечатки.

    Точные совпадения и совпадения по началу строки всегда выше нечёткого
    поиска. Возвращаем каноническое название из справочника, чтобы калькулятор
    не получал произвольный пользовательский текст.
    """
    raw_query = (query or "").strip()
    normalized_query = raw_query.casefold().replace("ё", "е")
    if len(normalized_query) < 2:
        return []

    direct_matches: list[tuple[tuple, str]] = []
    fuzzy_matches: list[tuple[float, str]] = []
    fuzzy_threshold = 0.72 if len(normalized_query) < 4 else 0.58
    for town_name in _load_towns():
        normalized_name = town_name.casefold().replace("ё", "е")
        if normalized_name == normalized_query:
            rank = (0, 0, town_name)
        elif normalized_name.startswith(normalized_query):
            rank = (1, len(normalized_name) - len(normalized_query), town_name)
        elif normalized_query in normalized_name:
            rank = (2, normalized_name.index(normalized_query), town_name)
        else:
            similarity = SequenceMatcher(None, normalized_query, normalized_name).ratio()
            if similarity < fuzzy_threshold:
                continue
            fuzzy_matches.append((similarity, town_name))
            continue
        direct_matches.append((rank, town_name))

    safe_limit = max(1, min(limit, 20))
    if direct_matches:
        direct_matches.sort(key=lambda item: item[0])
        return [{"name": town_name} for _, town_name in direct_matches[:safe_limit]]

    fuzzy_matches.sort(key=lambda item: (-item[0], item[1]))
    if not fuzzy_matches:
        return []
    best_similarity = fuzzy_matches[0][0]
    close_matches = [
        town_name
        for similarity, town_name in fuzzy_matches
        if similarity >= max(fuzzy_threshold, best_similarity - 0.1)
    ]
    return [{"name": town_name} for town_name in close_matches[:safe_limit]]


def _places_params(result: PackResult) -> dict:
    """Каждая коробка раскладки → одно грузовое место ПЭК: ШГВ (м), объём (м³),
    вес (кг). Габариты берём внешние — по ним ТК считает объём груза."""
    params: dict[str, str] = {}
    for i, pb in enumerate(result.boxes):
        box: Box = pb.box
        l, w, h = (d / 100 for d in box.dims_cm)  # см → м
        params[f"places[{i}][0]"] = f"{w:.3f}"
        params[f"places[{i}][1]"] = f"{l:.3f}"
        params[f"places[{i}][2]"] = f"{h:.3f}"
        params[f"places[{i}][3]"] = f"{box.volume_cm3 / 1_000_000:.4f}"
        params[f"places[{i}][4]"] = f"{pb.weight_g / 1000:.2f}"
        params[f"places[{i}][5]"] = "0"  # негабарит
        params[f"places[{i}][6]"] = "0"  # своя упаковка — услуга ПЭК не нужна
    return params


def _num(value) -> float | None:
    """Компонент ответа ПЭК приходит как [заголовок, город, сумма] либо отсутствует."""
    if isinstance(value, list) and value and isinstance(value[-1], (int, float)):
        return float(value[-1])
    return None


def calculate(result: PackResult, to_town: str, from_town_id: int = DEFAULT_FROM_TOWN_ID) -> dict:
    """Стоимость доставки ПЭК для готовой раскладки.

    Возвращает {'warehouse': ₽ склад-склад, 'door': ₽ до двери, 'days': срок,
    'to_town_id': id} либо {'error': ...}, если город не найден / нет мест.
    """
    if not result.boxes:
        return {"error": "нет грузовых мест для расчёта"}
    to_id = find_town_id(to_town)
    if to_id is None:
        return {"error": f"город назначения не найден в справочнике ПЭК: {to_town!r}"}

    params = {"take[town]": str(from_town_id), "deliver[town]": str(to_id)}
    params.update(_places_params(result))

    last_exc: Exception | None = None
    for attempt in range(4):
        try:
            resp = requests.get(CALC_URL, params=params, headers=_UA, timeout=40)
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception as e:  # сеть/парсинг — повтор с паузой
            last_exc = e
            time.sleep(1.5 * (attempt + 1))
    else:
        return {"error": f"ПЭК не ответил: {last_exc}"}

    auto = _num(data.get("auto"))
    deliver = _num(data.get("deliver")) or 0.0
    if auto is None:
        return {"error": "ПЭК не вернул стоимость перевозки", "raw": data}

    return {
        "warehouse": round(auto, 2),
        "door": round(auto + deliver, 2),
        "days": data.get("periods_days"),
        "to_town_id": to_id,
    }
