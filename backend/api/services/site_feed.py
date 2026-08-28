"""Чтение витрины horse-bio.ru через служебный фид.

Обмен CommerceML умеет только писать: узнать, что реально выставлено на сайте,
через него нельзя. Поэтому один из фидов маркетплейсов (`avito`, на площадке
не используется) переведён на локальный шаблон и отдаёт по каждой позиции
артикул, ссылку, цену, остаток и все фотографии.

Отсюда мы берём две вещи:

* фотографии основной карточки — их нужно приложить к карточке уценки, а обмен
  фото не отдаёт, только принимает;
* факт публикации: если артикул есть в фиде, карточка на сайте видна покупателю.
  Скрытые карточки в фид не попадают.

Шаблон фида и его грабли описаны в docs/site-channels.md. Главное: без строки
`data.offers.filter_enabled = false` фид отдаёт только товары с флагом выгрузки
и без модификаций — а половина наших позиций как раз модификации.
"""

import logging
from xml.etree import ElementTree

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

CACHE_KEY = "site_feed_offers"
CACHE_TTL = 10 * 60
TIMEOUT = 90


def _parse(xml):
    offers = {}
    for node in ElementTree.fromstring(xml):
        article = (node.findtext("article") or "").strip()
        if not article:
            continue
        offers[article] = {
            "name": (node.findtext("name") or "").strip(),
            "url": (node.findtext("url") or "").strip(),
            "price": float(node.findtext("price") or 0),
            "amount": float(node.findtext("amount") or 0),
            "pictures": [p.text.strip() for p in node.findall("picture") if (p.text or "").strip()],
        }
    return offers


def offers(refresh=False):
    """Что сейчас выставлено на сайте: {артикул: {name, url, price, amount, pictures}}.

    Фид отдаёт весь каталог одним куском и меняется редко, поэтому держим его
    в кеше: страница уценки дёргает его на каждую отрисовку.
    """
    if not refresh:
        cached = cache.get(CACHE_KEY)
        if cached is not None:
            return cached

    response = requests.get(settings.SITE_FEED_URL, timeout=TIMEOUT)
    response.raise_for_status()
    parsed = _parse(response.content)
    cache.set(CACHE_KEY, parsed, CACHE_TTL)
    return parsed


def pictures_for(article):
    """Фотографии карточки по артикулу. Пустой список, если фид её не знает."""
    try:
        return offers().get(article, {}).get("pictures", [])
    except Exception:
        logger.warning("Фид сайта недоступен, фотографии для %s не получены", article, exc_info=True)
        return []
