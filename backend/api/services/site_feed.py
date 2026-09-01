"""Чтение витрины horse-bio.ru через служебный фид.

Обмен CommerceML умеет только писать: узнать, что реально выставлено на сайте,
через него нельзя. Поэтому один из фидов маркетплейсов (`avito`, на площадке
не используется) переведён на локальный шаблон и отдаёт по каждой позиции
артикул, ссылку, цену, остаток и все фотографии.

Отсюда мы берём три вещи:

* фотографии основной карточки — их нужно приложить к карточке уценки, а обмен
  фото не отдаёт, только принимает;
* факт публикации: если артикул есть в фиде, карточка на сайте видна покупателю.
  Скрытые карточки в фид не попадают;
* дополнительные поля карточки — состав, применение, противопоказания, назначение.
  На сайте они обязательные, а руками их переносить — это несколько тысяч знаков
  на позицию.

Шаблон фида и его грабли описаны в docs/site-channels.md. Главное: без строки
`data.offers.filter_enabled = false` фид отдаёт только товары с флагом выгрузки
и без модификаций — а половина наших позиций как раз модификации.
"""

import logging
import re
from xml.etree import ElementTree

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

CACHE_KEY = "site_feed_offers"
PAGE_CACHE_KEY = "site_feed_page"
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
            # В фиде это анонс, а не полный текст карточки: полное описание
            # шаблонизатор не отдаёт, за ним ходим на саму страницу
            "announce": (node.findtext("description") or "").strip(),
            # Дополнительные поля: ключ у них тот же, что колонка `cf_<ключ>`
            # в файле импорта, поэтому храним как есть
            "fields": {
                (f.get("key") or "").strip(): (f.text or "").strip()
                for f in node.findall("field") if (f.get("key") or "").strip()
            },
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


# Блок с полным описанием на странице товара. Фид его не отдаёт — среди полей
# оффера полного текста нет вовсе, только анонс. Поэтому читаем страницу.
DESCRIPTION_BLOCK = "desc-area html_block"


def _block(html, marker):
    """Содержимое div, в классе которого встречается marker, с учётом вложенных div."""
    opening = re.search(r'<div[^>]*class="[^"]*' + re.escape(marker) + r'[^"]*"[^>]*>', html)
    if not opening:
        return None
    start = opening.end()
    depth = 1
    for tag in re.finditer(r"<(/?)div\b", html[start:]):
        depth += -1 if tag.group(1) else 1
        if depth == 0:
            return html[start:start + tag.start()].strip()
    return None


def _page(article):
    """HTML страницы товара. Кешируется: за ним ходят и описание, и характеристики."""
    offer = offers().get(article)
    if not offer or not offer.get("url"):
        return ""

    key = f"{PAGE_CACHE_KEY}:{article}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        response = requests.get(offer["url"], timeout=TIMEOUT)
        response.raise_for_status()
    except requests.RequestException:
        logger.warning("Не открыл страницу товара %s", article, exc_info=True)
        return ""
    cache.set(key, response.text, CACHE_TTL)
    return response.text


def _blocks(html):
    """Все блоки вкладок карточки: описание, состав, применение, противопоказания.

    У них один класс и разные id, поэтому берём подряд все и разбираем ниже
    по содержимому — так разбор не зависит ни от порядка вкладок, ни от их
    названий.
    """
    blocks = []
    for opening in re.finditer(r'<div[^>]*class="[^"]*' + re.escape(DESCRIPTION_BLOCK) + r'[^"]*"[^>]*>', html):
        start = opening.end()
        depth = 1
        for tag in re.finditer(r"<(/?)div\b", html[start:]):
            depth += -1 if tag.group(1) else 1
            if depth == 0:
                blocks.append(html[start:start + tag.start()].strip())
                break
    return blocks


def _plain(html):
    """Текст без разметки и лишних пробелов — для сравнения блока со значением из фида."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = text.replace("&mdash;", "—").replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", text).strip()


def rich_fields_for(article):
    """Дополнительные поля карточки с сохранённой вёрсткой.

    Фид отдаёт значения без разметки: заголовки, списки и абзацы платформа
    вырезает, и состав приезжает сплошной простынёй. Тот же текст есть на самой
    странице товара — уже свёрстанным. Поэтому берём значения из фида как
    образец, а содержимое — из соответствующего блока страницы.

    Сопоставляем по тексту, а не по названию вкладки: названия в админке
    меняются, а текст — это и есть само значение.
    """
    fields = fields_for(article)
    if not fields:
        return fields

    blocks = [(_plain(block), block) for block in _blocks(_page(article))]
    if not blocks:
        return fields

    result = {}
    for key, value in fields.items():
        sample = _plain(value)[:60]
        match = next((block for plain, block in blocks if sample and plain.startswith(sample)), None)
        result[key] = match or value
    return result


def description_for(article):
    """Полное описание карточки с её страницы на сайте.

    Пустая строка, если страницы нет или вёрстка изменилась: описание — вещь
    приятная, но не настолько, чтобы из-за неё падала выгрузка. Вызывающий сам
    решает, что делать с пустым результатом (обычно — не трогать поле).
    """
    return _block(_page(article), DESCRIPTION_BLOCK) or ""


# «Другие варианты товара» намеренно не переносим: у основной карточки это связка
# фасовок со ссылками на фото, и уценке в ней делать нечего — она не вариант
# основного товара, а отдельная позиция.
SKIPPED_FIELDS = {"fasovka"}


def fields_for(article):
    """Дополнительные поля карточки: {ключ: значение}. Пустой словарь, если фид молчит."""
    try:
        fields = offers().get(article, {}).get("fields", {})
    except Exception:
        logger.warning("Фид сайта недоступен, доп. поля для %s не получены", article, exc_info=True)
        return {}
    return {
        key: value for key, value in fields.items()
        # Ключи со слэшем и двоеточием — это настройки выгрузки на маркетплейсы
        # (`share/yandex_market:folder_yandex`), а не характеристики товара:
        # в файле импорта они живут отдельными колонками, без префикса cf_
        if key not in SKIPPED_FIELDS and "/" not in key and ":" not in key
    }
