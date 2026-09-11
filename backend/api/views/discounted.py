"""
Ручки раздела «Уценка»: страница, снятие с продажи, публикация, файл для сайта.

Сам расчёт — в api/services/discounted_report.py. Здесь остаётся то, что
отвечает на запрос: чтение снимка, действия человека и сборка файла импорта
для админки сайта.
"""

import logging

from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from api.exceptions import ExternalServiceError
from api.services import section_snapshots, site_csv, site_exchange, site_feed
from api.services.discounted_report import (
    ANNOUNCE, BASE_URL, NOTICE, RETAIL_PRICE_NAME, SECTION_KEY, SITE_FOLDER,
    STATE_DELIST, STATE_EXPIRED, UC_SUFFIX,
    build_snapshot, invalidate_cache, keywords, ms_get, ms_get_all_pages,
    positions_snapshot, price_of, site_slug,
)

logger = logging.getLogger(__name__)


@api_view(["GET"])
def discounted_list(request):
    """Уценённые позиции с расчётом, что пора снимать с продажи.

    Читает снимок из базы: открытие страницы в МойСклад не ходит. Пересборку
    заказывают явно — кнопкой «Обновить» (`?refresh=1`) или расписанием через
    `manage.py build_discounted_snapshot`. Первый заход после выката собирает
    снимок сам: пустая страница до ближайшего прогона хуже трёх секунд ожидания.
    """
    if request.GET.get("refresh") == "1":
        return Response(section_snapshots.rebuild(SECTION_KEY, build_snapshot))
    return Response(section_snapshots.read(SECTION_KEY, build_snapshot))


@api_view(["POST"])
def discounted_delist(request, product_id):
    """Снять позицию с продажи на сайте — обменом, без захода в админку.

    Артикул и название берём из МойСклад, а не из тела запроса: страница могла
    открыться час назад, и данные в ней успели устареть.
    """
    try:
        product = ms_get(f"/entity/product/{product_id}")
    except Exception as exc:
        logger.warning("Товар %s не найден в МойСклад", product_id, exc_info=True)
        raise ExternalServiceError(f"Товар не найден в МойСклад: {exc}")

    site_exchange.set_visibility(
        product_id=product_id,
        article=product.get("article") or "",
        name=product.get("name") or "",
        visibility=site_exchange.HIDDEN_404,
    )

    # Список считается из остатков и дат, а не из доступности на сайте, поэтому
    # кеш сбрасываем только чтобы страница перерисовалась свежей.
    invalidate_cache()
    return Response({"ok": True, "product_id": product_id}, status=status.HTTP_200_OK)


@api_view(["POST"])
def discounted_publish(request, product_id):
    """Завести карточку уценки на сайте: фото, цена, остаток, тексты и SEO.

    Фотографии берём у основной карточки — артикул уценки без суффикса `-UC`.
    Карточка создаётся скрытой: открывает её человек, убедившись, что всё легло
    правильно. Так же безопаснее при повторном вызове — обновление не выкинет
    товар в продажу раньше времени.
    """
    try:
        product = ms_get(f"/entity/product/{product_id}")
    except Exception as exc:
        logger.warning("Товар %s не найден в МойСклад", product_id, exc_info=True)
        raise ExternalServiceError(f"Товар не найден в МойСклад: {exc}")

    article = product.get("article") or ""
    name = product.get("name") or ""
    price = price_of(product, RETAIL_PRICE_NAME)
    if not price:
        raise ExternalServiceError(
            f"У карточки не заполнена цена «{RETAIL_PRICE_NAME}» — публиковать нечего"
        )

    stock_rows = ms_get_all_pages(
        "/report/stock/all",
        {"filter": f"product={BASE_URL}/entity/product/{product_id}", "groupBy": "product"},
    )
    quantity = int(sum(row.get("stock") or 0 for row in stock_rows))

    source_article = article[: -len(UC_SUFFIX)] if article.endswith(UC_SUFFIX) else article
    pictures = site_feed.pictures_for(source_article)

    # Если карточка уже на витрине, доступность не трогаем: иначе повторная
    # отправка (например, чтобы обновить фотографии) снимет товар с продажи.
    on_site = {}
    try:
        on_site = site_feed.offers()
    except Exception:
        logger.warning("Фид сайта недоступен, публикуем карточку скрытой", exc_info=True)
    visibility = None if article in on_site else site_exchange.HIDDEN_404

    uploaded = site_exchange.publish(
        product_id=product_id,
        article=article,
        name=name,
        price=int(round(price)),
        quantity=quantity,
        pictures=pictures,
        visibility=visibility,
        attributes=[
            ("Анонс товара", ANNOUNCE),
            ("Подробное описание товара", NOTICE),
            ("ЧПУ", site_slug(name)),
            ("Заголовок (H1)", name),
            ("Заголовок страницы (Title)", f"{name} — уценка со скидкой 30 % | Horse-Bio"),
            ("Описание страницы (Description)", ANNOUNCE),
            ("Ключевые слова (Keywords)", keywords(name)),
            # Уценка не должна конкурировать с основной карточкой в поиске
            ("Запретить индексацию страницы", 1),
            # Промокоды на уценённый товар не действуют
            ("Товар уже со скидкой", 1),
        ],
    )

    invalidate_cache()
    return Response({
        "ok": True,
        "product_id": product_id,
        "pictures": uploaded,
        "quantity": quantity,
        "price": int(round(price)),
    }, status=status.HTTP_200_OK)


def _must_hide(position):
    """Карточку нельзя оставлять на витрине.

    Два случая из регламента: до конца срока осталось меньше двух месяцев
    (продавать нечего — покупателю не хватит срока на курс и доставку) и товар
    раскуплен. Обмен, который снимал бы такие карточки сам, упёрся в демо-лимит,
    поэтому снятие делает тот же файл импорта.
    """
    return position["state"] in (STATE_EXPIRED, STATE_DELIST) or position["quantity"] <= 0


def _csv_row(position, pictures, description="", fields=None):
    """Строка файла импорта по позиции склада «Уценка».

    description — текст основной карточки. Пустой оставляем поле пустым: импорт
    затрёт описание, которое уже стоит в карточке, а восстанавливать его неоткуда.

    fields — дополнительные поля основной карточки (состав, применение,
    противопоказания и прочее). На сайте они обязательные, без них карточку
    не сохранить, а руками это несколько тысяч знаков на позицию.
    """
    name = position["name"]
    return {
        "article": position["article"],
        "name": name,
        "folder": SITE_FOLDER,
        # Скрытой карточка уходит в двух случаях: её ещё нет на витрине (открывает
        # её человек, проверив глазами) или её пора снять — по сроку или потому,
        # что товар кончился. Всё остальное, что уже продаётся, файл не трогает.
        "hidden": 0 if position.get("published") and not _must_hide(position) else 1,
        "price": f"{position['price']:.2f}",
        # Зачёркнутая цена — РРЦ, от которой считали скидку
        "price_old": f"{position['price_full']:.2f}",
        "amount": int(position["quantity"]),
        # Промокоды на уценённый товар не действуют
        "discounted": 1,
        "note": ANNOUNCE,
        "body": (NOTICE + description) if description else "",
        "image": ", ".join(pictures),
        "sef_url": site_slug(name),
        # Уценка не должна конкурировать с основной карточкой в поиске
        "seo_noindex": 1,
        "seo_h1": name,
        "seo_title": f"{name} — уценка со скидкой 30 % | Horse-Bio",
        "seo_description": ANNOUNCE,
        "seo_keywords": keywords(name),
        **{f"cf_{key}": value for key, value in (fields or {}).items()},
    }


@api_view(["GET"])
def discounted_csv(request):
    """Файл импорта для админки сайта — на случай, когда обмен недоступен.

    Обмен работает в демо-режиме с лимитом на число загруженных предложений;
    когда лимит выбран, он отвечает `success`, но часть полей не применяет.
    Импорт CSV лимитов не имеет, поэтому файл — надёжный запасной путь.

    Файл приводит витрину в соответствие со складом целиком, а не только заводит
    карточки: позиции с остатком получают фактическое количество, а те, что пора
    снять по сроку или раскуплены, — признак «скрыто». Поэтому в него идут ещё и
    опубликованные позиции с нулевым остатком: без них раскупленная карточка
    осталась бы в продаже.

    Если фид сайта не ответил, файл не собирается вовсе. Колонка «Скрыто» считается
    от того, что сейчас на витрине, а при недоступном фиде это неизвестно: карточки
    вышли бы скрытыми все до одной, и импорт снял бы с продажи весь раздел.
    """
    positions = positions_snapshot()
    if any(p.get("published") is None for p in positions):
        raise ExternalServiceError(
            "Фид сайта не ответил — неизвестно, что сейчас на витрине, и файл"
            " снял бы с продажи все карточки. Нажмите «Обновить» и попробуйте снова."
        )

    positions = [p for p in positions if p["quantity"] > 0 or p.get("published")]

    rows = []
    for position in positions:
        article = position["article"]
        source = article[: -len(UC_SUFFIX)] if article.endswith(UC_SUFFIX) else article
        rows.append(_csv_row(
            position,
            site_feed.pictures_for(source),
            site_feed.description_for(source),
            site_feed.rich_fields_for(source),
        ))

    response = HttpResponse(site_csv.build(rows), content_type="text/csv; charset=windows-1251")
    response["Content-Disposition"] = 'attachment; filename="ucenka-import.csv"'
    return response
