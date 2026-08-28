"""Отладка обмена с сайтом: печатает запросы, XML и ответы целиком.

Нужна, чтобы разбираться, почему сайт принимает файл (`success`), но не применяет
изменения. Логирует каждый шаг обмена: checkauth, init, загрузку файла и импорт.
Только отправляет — результат смотрим в админке.

    # доступность: 0 — доступен, 1 — недоступен (404), 2 — скрыт с доступом по ссылке
    python manage.py site_exchange_probe --article 06-04GP1600-UC --visibility 0

    # цена и остаток
    python manage.py site_exchange_probe --article 06-04GP1600-UC --price 1456 --quantity 32

    # произвольный реквизит из «Переопределения свойств»
    python manage.py site_exchange_probe --article 06-04GP1600-UC --attribute "Анонс товара=проба"
"""

import time
from datetime import date
from xml.sax.saxutils import escape

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from api.services import site_exchange as se
from api.views.discounted import _get_all_pages, FOLDER_PARENT, FOLDER_NAME

PRICE_TYPE_ID = "22222222-0000-4000-8000-000000000001"
PRICE_TYPE_NAME = "Розница"
UNIT = ('<БазоваяЕдиница Код="796" НаименованиеПолное="Штука" '
        'МеждународноеСокращение="PCE">шт</БазоваяЕдиница>')


class Command(BaseCommand):
    help = "Отправить обмен с подробным логом и посмотреть, применился ли он"

    def add_arguments(self, parser):
        parser.add_argument("--article", required=True)
        parser.add_argument("--visibility", type=int, choices=[0, 1, 2],
                            help="доступность: 0 доступен, 1 недоступен (404), 2 скрыт по ссылке")
        parser.add_argument("--price", type=int)
        parser.add_argument("--quantity", type=int)
        parser.add_argument("--attribute", action="append", default=[],
                            metavar="ИМЯ=ЗНАЧЕНИЕ", help="произвольный реквизит, можно несколько раз")
        parser.add_argument("--image", action="append", default=[],
                            help="URL картинки, можно несколько раз")
        parser.add_argument("--upload-images", action="store_true",
                            help="сначала залить картинки как файлы обмена (import_files/…), "
                                 "как это делает 1С, и сослаться на них путём внутри архива")
        parser.add_argument("--as-modification", action="store_true",
                            help="слать составной идентификатор GUID#GUID — карточка ведёт себя как модификация")
        parser.add_argument("--attribute-name", default=se.VISIBILITY_ATTRIBUTE,
                            help="имя реквизита доступности (по умолчанию из site_exchange)")
        parser.add_argument("--offer-visibility", type=int, choices=[0, 1, 2],
                            help="доступность реквизитом внутри <Предложение> (уровень модификации)")
        parser.add_argument("--name", help="отправить другое название — проверка, доходит ли import.xml до карточки")
        parser.add_argument("--no-folder", action="store_true",
                            help="не передавать <Группы> в товаре")

    # ---------- обмен с логом ----------

    def _log_response(self, title, response):
        self.stdout.write(self.style.HTTP_INFO(f"\n--- {title} ---"))
        self.stdout.write(f"{response.request.method} {response.request.url}")
        self.stdout.write(f"HTTP {response.status_code}")
        for key, value in response.headers.items():
            if key.lower() in ("content-type", "content-length", "set-cookie"):
                self.stdout.write(f"  {key}: {value}")
        self.stdout.write("Ответ:")
        self.stdout.write(response.text.strip() or "(пусто)")

    def _session(self):
        login, password = settings.SITE_CML_LOGIN, settings.SITE_CML_PASSWORD
        if not (login and password):
            raise CommandError("Не заданы SITE_CML_LOGIN и SITE_CML_PASSWORD")
        session = requests.Session()
        session.auth = (login, password)
        session.headers.update({"User-Agent": se.USER_AGENT})

        response = session.get(settings.SITE_CML_URL,
                               params={"type": "catalog", "mode": "checkauth"}, timeout=60)
        self._log_response("checkauth", response)
        lines = response.text.splitlines()
        if len(lines) >= 3:
            session.cookies.set(lines[1].strip(), lines[2].strip())
            self.stdout.write(f"cookie: {lines[1].strip()}={lines[2].strip()}")

        response = session.get(settings.SITE_CML_URL,
                               params={"type": "catalog", "mode": "init"}, timeout=60)
        self._log_response("init", response)
        return session

    def _upload_images(self, session, urls):
        """Залить картинки как файлы обмена и вернуть пути, на которые можно ссылаться.

        В CommerceML <Картинка> — это путь к файлу внутри архива обмена, а не ссылка.
        Раз архив мы не собираем (init отвечает zip=no), отправляем каждый файл
        отдельным mode=file с именем вида import_files/<имя>.
        """
        paths = []
        for url in urls:
            name = url.rstrip("/").rsplit("/", 1)[-1]
            path = f"import_files/{name}"
            body = requests.get(url if url.startswith("http") else f"https://horse-bio.ru/{url}",
                                timeout=60).content
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n=== {path} ({len(body)} байт) ==="))
            response = session.post(
                settings.SITE_CML_URL,
                params={"type": "catalog", "mode": "file", "filename": path},
                data=body,
                headers={"Content-Type": "application/octet-stream"},
                timeout=120,
            )
            self._log_response(f"file {path}", response)
            paths.append(path)
        return paths

    def _send(self, session, filename, xml):
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n=== {filename} ({len(xml)} байт) ==="))
        self.stdout.write(xml)

        response = session.post(
            settings.SITE_CML_URL,
            params={"type": "catalog", "mode": "file", "filename": filename},
            data=xml.encode("utf-8"),
            headers={"Content-Type": "application/octet-stream"},
            timeout=60,
        )
        self._log_response(f"file {filename}", response)

        # По протоколу «progress» значит «файлы ещё готовятся, повтори запрос»:
        # клиент обязан звать mode=import, пока не получит success. Без этого импорт
        # остаётся недоделанным и в списке заданий сайта даже не появляется.
        for attempt in range(1, 31):
            response = session.get(
                settings.SITE_CML_URL,
                params={"type": "catalog", "mode": "import", "filename": filename},
                timeout=120,
            )
            self._log_response(f"import {filename} (попытка {attempt})", response)
            if not response.text.strip().startswith("progress"):
                break
            time.sleep(3)

    # ---------- тела файлов ----------

    def _catalog(self, product, attributes, with_folder=True, images=()):
        values = "".join(
            f"<ЗначениеРеквизита><Наименование>{escape(name)}</Наименование>"
            f"<Значение>{escape(str(value))}</Значение></ЗначениеРеквизита>"
            for name, value in attributes
        )
        folder = f"<Группы><Ид>{se.FOLDER_ID}</Ид></Группы>" if with_folder else ""
        pictures = "".join(f"<Картинка>{escape(url)}</Картинка>" for url in images)
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<КоммерческаяИнформация ВерсияСхемы="2.05" ДатаФормирования="{date.today().isoformat()}">
 <Классификатор>
  <Ид>{se.CLASSIFIER_ID}</Ид>
  <Наименование>Каталог Horse-Bio</Наименование>
  <Группы><Группа><Ид>{se.FOLDER_ID}</Ид><Наименование>{se.SITE_FOLDER_NAME}</Наименование></Группа></Группы>
 </Классификатор>
 <Каталог СодержитТолькоИзменения="false">
  <Ид>{se.CATALOG_ID}</Ид>
  <ИдКлассификатора>{se.CLASSIFIER_ID}</ИдКлассификатора>
  <Наименование>Каталог Horse-Bio</Наименование>
  <Товары>
   <Товар>
    <Ид>{product['id']}</Ид>
    <Артикул>{escape(product['article'])}</Артикул>
    <Наименование>{escape(product['name'])}</Наименование>
    {folder}
    {UNIT}
    {pictures}
    <ЗначенияРеквизитов>{values}</ЗначенияРеквизитов>
   </Товар>
  </Товары>
 </Каталог>
</КоммерческаяИнформация>"""

    def _offers(self, product, price, quantity, visibility=None):
        offer_attributes = ""
        if visibility is not None:
            offer_attributes = (
                "<ЗначенияРеквизитов><ЗначениеРеквизита>"
                f"<Наименование>{se.VISIBILITY_ATTRIBUTE}</Наименование>"
                f"<Значение>{visibility}</Значение>"
                "</ЗначениеРеквизита></ЗначенияРеквизитов>"
            )
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<КоммерческаяИнформация ВерсияСхемы="2.05" ДатаФормирования="{date.today().isoformat()}">
 <ПакетПредложений>
  <Ид>{se.CATALOG_ID}</Ид>
  <Наименование>Предложения Horse-Bio</Наименование>
  <ИдКаталога>{se.CATALOG_ID}</ИдКаталога>
  <ИдКлассификатора>{se.CLASSIFIER_ID}</ИдКлассификатора>
  <ТипыЦен>
   <ТипЦены><Ид>{PRICE_TYPE_ID}</Ид><Наименование>{PRICE_TYPE_NAME}</Наименование>
    <Валюта>руб</Валюта></ТипЦены>
  </ТипыЦен>
  <Предложения>
   <Предложение>
    <Ид>{product['id']}</Ид>
    <Артикул>{escape(product['article'])}</Артикул>
    <Наименование>{escape(product['name'])}</Наименование>
    {UNIT}
    <Цены><Цена>
     <ИдТипаЦены>{PRICE_TYPE_ID}</ИдТипаЦены>
     <ЦенаЗаЕдиницу>{price}</ЦенаЗаЕдиницу>
     <Валюта>руб</Валюта><Единица>шт</Единица><Коэффициент>1</Коэффициент>
    </Цена></Цены>
    <Количество>{quantity}</Количество>
    {offer_attributes}
   </Предложение>
  </Предложения>
 </ПакетПредложений>
</КоммерческаяИнформация>"""

    # ---------- сценарий ----------

    def handle(self, *args, **options):
        article = options["article"]
        products = _get_all_pages("/entity/product", {"filter": f"pathName={FOLDER_PARENT}/{FOLDER_NAME}"})
        product = next((p for p in products if p.get("article") == article), None)
        if not product:
            raise CommandError(f"В группе «{FOLDER_PARENT}/{FOLDER_NAME}» нет товара {article}")

        if options["name"]:
            product = dict(product, name=options["name"])
        if options["as_modification"]:
            # CommerceML адресует модификацию как <Ид товара>#<Ид модификации>;
            # у наших карточек оба идентификатора совпадают
            product = dict(product, id=f"{product['id']}#{product['id']}")
        self.stdout.write(f"Товар: {product['name']}")
        self.stdout.write(f"  id (он же GUID обмена): {product['id']}")
        self.stdout.write(f"  артикул: {product['article']}")

        attributes = []
        if options["visibility"] is not None:
            attributes.append((options["attribute_name"], options["visibility"]))
        for raw in options["attribute"]:
            if "=" not in raw:
                raise CommandError(f"Реквизит нужно задавать как ИМЯ=ЗНАЧЕНИЕ, а не «{raw}»")
            name, value = raw.split("=", 1)
            attributes.append((name, value))

        session = self._session()

        images = options["image"]
        if images and options["upload_images"]:
            images = self._upload_images(session, images)

        if attributes or options["name"] or images:
            if attributes:
                self.stdout.write("\nРеквизиты: " + ", ".join(f"{n} = {v}" for n, v in attributes))
            self._send(session, "import.xml",
                       self._catalog(product, attributes,
                                     with_folder=not options["no_folder"],
                                     images=images))

        if (options["price"] is not None or options["quantity"] is not None
                or options["offer_visibility"] is not None):
            price = options["price"] if options["price"] is not None else 0
            quantity = options["quantity"] if options["quantity"] is not None else 0
            self._send(session, "offers.xml",
                       self._offers(product, price, quantity, options["offer_visibility"]))
