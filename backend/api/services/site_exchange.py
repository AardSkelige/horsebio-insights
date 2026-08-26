"""
Обмен с сайтом horse-bio.ru по протоколу CommerceML.

Сайт на Megagroup CMS-S3. У него нет обычного REST API, но есть обмен CommerceML —
тот же, которым с магазинами разговаривает 1С. Через него можно создавать карточки,
менять цены и остатки и снимать товар с продажи, причём применяется всё само,
без захода в админку.

Что важно знать, прежде чем править этот модуль (проверено на живом сайте 21.08.2026):

* Товары сопоставляются по GUID из поля <Ид>, а не по артикулу. Чтобы не заводить
  таблицу соответствий, в качестве GUID берём id товара в МойСклад — он и так UUID.
* Ответ `success` на mode=import означает «файл принят в очередь», а не «применён».
* Цены, остатки и доступность применяет ТОЛЬКО автоимпорт. Если в админке выключен
  тумблер «Автоматический импорт товаров», обмен молча ничего не сделает.
* Доступность карточки — реквизит «Параметры отображения» (во множественном числе;
  единственное число, указанное в поле маппинга админки, не работает). Значение
  числом: 0 — доступен, 1 — недоступен (404), 2 — скрыт с доступом по ссылке.
  Требует включённого «связывания параметров» в «Переопределении свойств».
* Демо-режим ограничен 50 предложениями. Позиционной отсечки внутри файла нет —
  проверено файлом на 51 предложение. Точный смысл ограничения уточняется.
"""

import logging
from datetime import date
from xml.sax.saxutils import escape

import requests
from django.conf import settings

from api.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)

# Идентификаторы нашего каталога в терминах обмена. Постоянные: сайт запоминает их
# у себя, и при смене мы потеряем связь с уже созданными карточками.
CLASSIFIER_ID = "11111111-0000-4000-8000-000000000001"
CATALOG_ID = "11111111-0000-4000-8000-000000000002"
FOLDER_ID = "11111111-0000-4000-8000-000000000003"
# Имя категории видит покупатель на сайте — оно НЕ совпадает с группой «Уценка»
# в МойСклад: там это слово нужно отделу упаковки, чтобы отличать позиции в накладной.
SITE_FOLDER_NAME = "Уцененный товар"

# Megagroup узнаёт себя по User-Agent 1С — с обычным заголовком обмен не отвечает
USER_AGENT = "1C+Enterprise/8.3"

VISIBILITY_ATTRIBUTE = "Параметры отображения"
VISIBLE = 0
HIDDEN_404 = 1
HIDDEN_BY_LINK = 2

TIMEOUT = 60


class SiteExchangeError(ExternalServiceError):
    """Обмен с сайтом не прошёл."""


def _credentials():
    login = settings.SITE_CML_LOGIN
    password = settings.SITE_CML_PASSWORD
    if not (login and password):
        raise SiteExchangeError(
            "Не заданы SITE_CML_LOGIN и SITE_CML_PASSWORD — обмен с сайтом не настроен"
        )
    return login, password


def _session():
    """Сессия обмена: логинимся и кладём выданную cookie.

    Ответ checkauth — три строки: success, имя cookie, её значение. Без этой cookie
    последующие запросы сайт не свяжет в один обмен.
    """
    login, password = _credentials()
    session = requests.Session()
    session.auth = (login, password)
    session.headers.update({"User-Agent": USER_AGENT})

    response = session.get(
        settings.SITE_CML_URL,
        params={"type": "catalog", "mode": "checkauth"},
        timeout=TIMEOUT,
    )
    if response.status_code != 200 or not response.text.startswith("success"):
        raise SiteExchangeError(f"Сайт не принял авторизацию обмена: {response.text[:200]}")

    lines = response.text.splitlines()
    if len(lines) >= 3:
        session.cookies.set(lines[1].strip(), lines[2].strip())

    session.get(settings.SITE_CML_URL, params={"type": "catalog", "mode": "init"}, timeout=TIMEOUT)
    return session


def _send(session, filename, xml):
    """Загрузить файл обмена и поставить его в очередь на применение."""
    response = session.post(
        settings.SITE_CML_URL,
        params={"type": "catalog", "mode": "file", "filename": filename},
        data=xml.encode("utf-8"),
        headers={"Content-Type": "application/octet-stream"},
        timeout=TIMEOUT,
    )
    if response.status_code != 200 or "success" not in response.text:
        raise SiteExchangeError(f"Сайт не принял файл {filename}: {response.text[:200]}")

    response = session.get(
        settings.SITE_CML_URL,
        params={"type": "catalog", "mode": "import", "filename": filename},
        timeout=TIMEOUT * 2,
    )
    text = response.text.strip()
    # «progress» — сайт ещё готовит файлы; для наших объёмов это не встречалось,
    # но ошибкой не является, поэтому пропускаем его наравне с success
    if response.status_code != 200 or not (text.startswith("success") or text.startswith("progress")):
        raise SiteExchangeError(f"Сайт отказался применять {filename}: {text[:200]}")
    return text


def _catalog_xml(items):
    """import.xml: карточки товаров и категория на сайте.

    items — список словарей: id (он же GUID обмена), article, name и,
    необязательно, visibility.
    """
    goods = []
    for item in items:
        attributes = ""
        if item.get("visibility") is not None:
            attributes = (
                "    <ЗначенияРеквизитов>"
                f"<ЗначениеРеквизита><Наименование>{VISIBILITY_ATTRIBUTE}</Наименование>"
                f"<Значение>{int(item['visibility'])}</Значение></ЗначениеРеквизита>"
                "</ЗначенияРеквизитов>\n"
            )
        goods.append(
            f"""   <Товар>
    <Ид>{escape(item['id'])}</Ид>
    <Артикул>{escape(item['article'])}</Артикул>
    <Наименование>{escape(item['name'])}</Наименование>
    <Группы><Ид>{FOLDER_ID}</Ид></Группы>
    <БазоваяЕдиница Код="796" НаименованиеПолное="Штука" МеждународноеСокращение="PCE">шт</БазоваяЕдиница>
{attributes}   </Товар>"""
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<КоммерческаяИнформация ВерсияСхемы="2.05" ДатаФормирования="{date.today().isoformat()}">
 <Классификатор>
  <Ид>{CLASSIFIER_ID}</Ид>
  <Наименование>Каталог Horse-Bio</Наименование>
  <Группы><Группа><Ид>{FOLDER_ID}</Ид><Наименование>{SITE_FOLDER_NAME}</Наименование></Группа></Группы>
 </Классификатор>
 <Каталог СодержитТолькоИзменения="false">
  <Ид>{CATALOG_ID}</Ид>
  <ИдКлассификатора>{CLASSIFIER_ID}</ИдКлассификатора>
  <Наименование>Каталог Horse-Bio</Наименование>
  <Товары>
{chr(10).join(goods)}
  </Товары>
 </Каталог>
</КоммерческаяИнформация>"""


def set_visibility(product_id, article, name, visibility):
    """Снять товар с продажи на сайте или вернуть его в продажу.

    Возвращает текст ответа сайта. Бросает SiteExchangeError, если обмен не прошёл —
    вызывающий код обязан показать это пользователю, иначе человек будет думать,
    что товар снят, а он останется в продаже.
    """
    session = _session()
    xml = _catalog_xml([{
        "id": product_id,
        "article": article,
        "name": name,
        "visibility": visibility,
    }])
    result = _send(session, "import.xml", xml)
    logger.info(
        "Обмен с сайтом: товар %s (%s) → доступность %s, ответ %r",
        article, product_id, visibility, result,
    )
    return result
