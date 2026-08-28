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
* Доступность карточки — реквизит «Параметр отображения», в единственном числе:
  имя берётся из поля маппинга в «Переопределении свойств», а не из подписи над ним
  («Параметры отображения» — это название поля в админке, и оно не работает).
  Значение: 1 — недоступен (404), 2 — скрыт с доступом по ссылке, «Доступен» —
  вернуть в продажу. Ноль числом не работает: сайт считает его пустым значением
  и оставляет карточку как есть, поэтому для возврата шлём подпись из выпадашки.
  Требует включённого «связывания параметров» в «Переопределении свойств».
* Идентификатор товара в <Ид> — простой GUID. Составной вид «GUID#GUID», которым
  CommerceML адресует модификации, платформа не разбирает: она заводит по нему
  новый товар, записав всю строку в UUID.
* Демо-режим ограничен 50 предложениями. Позиционной отсечки внутри файла нет —
  проверено файлом на 51 предложение. Точный смысл ограничения уточняется.
"""

import logging
import time
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
PRICE_TYPE_ID = "22222222-0000-4000-8000-000000000001"
PRICE_TYPE_NAME = "Розница"
# Каталог файлов обмена на стороне сайта — в него кладём фотографии
PICTURES_DIR = "import_files"
# Имя категории видит покупатель на сайте — оно НЕ совпадает с группой «Уценка»
# в МойСклад: там это слово нужно отделу упаковки, чтобы отличать позиции в накладной.
SITE_FOLDER_NAME = "Уцененный товар"

# Megagroup узнаёт себя по User-Agent 1С — с обычным заголовком обмен не отвечает
USER_AGENT = "1C+Enterprise/8.3"

VISIBILITY_ATTRIBUTE = "Параметр отображения"
# Скрытие едет числом, а возврат в продажу — только словом из выпадашки админки:
# ноль сайт считает пустым значением и молча отбрасывает (проверено 28.08.2026 —
# не проходят ни «0», ни «00», ни « 0»).
VISIBLE = "Доступен"
HIDDEN_404 = 1
HIDDEN_BY_LINK = 2

TIMEOUT = 60
IMPORT_RETRIES = 40
IMPORT_RETRY_DELAY = 3


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

    # «progress» означает «файлы ещё готовятся, повтори запрос»: клиент обязан
    # звать mode=import, пока не получит success. Без этого импорт остаётся
    # недоделанным и в списке заданий сайта даже не появляется. Картинки готовятся
    # дольше всего — шесть штук занимали около восьми повторов.
    for _ in range(IMPORT_RETRIES):
        response = session.get(
            settings.SITE_CML_URL,
            params={"type": "catalog", "mode": "import", "filename": filename},
            timeout=TIMEOUT * 2,
        )
        text = response.text.strip()
        if response.status_code != 200 or not (text.startswith("success") or text.startswith("progress")):
            raise SiteExchangeError(f"Сайт отказался применять {filename}: {text[:200]}")
        if text.startswith("success"):
            return text
        time.sleep(IMPORT_RETRY_DELAY)
    raise SiteExchangeError(
        f"Сайт так и не применил {filename}: за "
        f"{IMPORT_RETRIES * IMPORT_RETRY_DELAY} секунд файл остался в обработке"
    )


def _catalog_xml(items):
    """import.xml: карточки товаров и категория на сайте.

    items — список словарей: id (он же GUID обмена), article, name и, необязательно,
    visibility, attributes (список пар имя-значение) и pictures (пути файлов обмена).
    """
    goods = []
    for item in items:
        values = []
        if item.get("visibility") is not None:
            values.append((VISIBILITY_ATTRIBUTE, item["visibility"]))
        values.extend(item.get("attributes") or [])
        attributes = ""
        if values:
            attributes = "    <ЗначенияРеквизитов>" + "".join(
                f"<ЗначениеРеквизита><Наименование>{escape(str(name))}</Наименование>"
                f"<Значение>{escape(str(value))}</Значение></ЗначениеРеквизита>"
                for name, value in values
            ) + "</ЗначенияРеквизитов>\n"
        pictures = "".join(
            f"    <Картинка>{escape(path)}</Картинка>\n" for path in item.get("pictures") or []
        )
        goods.append(
            f"""   <Товар>
    <Ид>{escape(item['id'])}</Ид>
    <Артикул>{escape(item['article'])}</Артикул>
    <Наименование>{escape(item['name'])}</Наименование>
    <Группы><Ид>{FOLDER_ID}</Ид></Группы>
    <БазоваяЕдиница Код="796" НаименованиеПолное="Штука" МеждународноеСокращение="PCE">шт</БазоваяЕдиница>
{pictures}{attributes}   </Товар>"""
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


def _offers_xml(items):
    """offers.xml: цены и остатки.

    Цена применяется только если в админке, во вкладке Автоимпорт, выбран тип цены
    в поле «Что использовать в качестве основной цены». Тип цены появляется в той
    выпадашке лишь после того, как обмен его однажды принёс, — поэтому имя и
    идентификатор здесь постоянные.
    """
    offers = []
    for item in items:
        offers.append(
            f"""   <Предложение>
    <Ид>{escape(item['id'])}</Ид>
    <Артикул>{escape(item['article'])}</Артикул>
    <Наименование>{escape(item['name'])}</Наименование>
    <БазоваяЕдиница Код="796" НаименованиеПолное="Штука" МеждународноеСокращение="PCE">шт</БазоваяЕдиница>
    <Цены><Цена>
     <ИдТипаЦены>{PRICE_TYPE_ID}</ИдТипаЦены>
     <ЦенаЗаЕдиницу>{item['price']}</ЦенаЗаЕдиницу>
     <Валюта>руб</Валюта><Единица>шт</Единица><Коэффициент>1</Коэффициент>
    </Цена></Цены>
    <Количество>{item['quantity']}</Количество>
   </Предложение>"""
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<КоммерческаяИнформация ВерсияСхемы="2.05" ДатаФормирования="{date.today().isoformat()}">
 <ПакетПредложений>
  <Ид>{CATALOG_ID}</Ид>
  <Наименование>Предложения Horse-Bio</Наименование>
  <ИдКаталога>{CATALOG_ID}</ИдКаталога>
  <ИдКлассификатора>{CLASSIFIER_ID}</ИдКлассификатора>
  <ТипыЦен>
   <ТипЦены><Ид>{PRICE_TYPE_ID}</Ид><Наименование>{PRICE_TYPE_NAME}</Наименование>
    <Валюта>руб</Валюта></ТипЦены>
  </ТипыЦен>
  <Предложения>
{chr(10).join(offers)}
  </Предложения>
 </ПакетПредложений>
</КоммерческаяИнформация>"""


def _upload_pictures(session, urls):
    """Залить фотографии как файлы обмена и вернуть пути, на которые можно ссылаться.

    В CommerceML <Картинка> — это путь к файлу внутри архива обмена, а не ссылка:
    ни абсолютный URL, ни относительный путь на сайте платформа не принимает.
    Архив мы не собираем (init отвечает zip=no), поэтому шлём каждый файл отдельным
    mode=file с именем import_files/<имя>. Фотографии при этом задваиваются
    в хранилище сайта — по-другому протокол не умеет.
    """
    paths = []
    for url in urls:
        name = url.rstrip("/").rsplit("/", 1)[-1]
        path = f"{PICTURES_DIR}/{name}"
        try:
            body = requests.get(url, timeout=TIMEOUT).content
        except requests.RequestException as exc:
            logger.warning("Не скачал фотографию %s: %s", url, exc)
            continue

        response = session.post(
            settings.SITE_CML_URL,
            params={"type": "catalog", "mode": "file", "filename": path},
            data=body,
            headers={"Content-Type": "application/octet-stream"},
            timeout=TIMEOUT * 2,
        )
        if response.status_code != 200 or "success" not in response.text:
            raise SiteExchangeError(f"Сайт не принял фотографию {name}: {response.text[:200]}")
        paths.append(path)
    return paths


def publish(product_id, article, name, price, quantity, pictures=(), attributes=()):
    """Завести или обновить карточку уценки на сайте.

    Один вызов делает всё: заливает фотографии, отправляет карточку с текстами
    и SEO, следом — цену и остаток. Карточка создаётся скрытой: открывает её
    человек, проверив глазами (см. docs/ucenka.md).

    Возвращает число залитых фотографий — по нему видно, дошли ли они.
    """
    session = _session()
    paths = _upload_pictures(session, pictures) if pictures else []

    _send(session, "import.xml", _catalog_xml([{
        "id": product_id,
        "article": article,
        "name": name,
        "visibility": HIDDEN_404,
        "attributes": list(attributes),
        "pictures": paths,
    }]))
    _send(session, "offers.xml", _offers_xml([{
        "id": product_id,
        "article": article,
        "name": name,
        "price": price,
        "quantity": quantity,
    }]))
    logger.info("Обмен с сайтом: опубликован %s (%s), фотографий %s", article, product_id, len(paths))
    return len(paths)


def push_stock(items):
    """Отправить на сайт цены и остатки. items — id, article, name, price, quantity."""
    if not items:
        return 0
    _send(_session(), "offers.xml", _offers_xml(items))
    logger.info("Обмен с сайтом: обновлены цены и остатки, позиций %s", len(items))
    return len(items)
