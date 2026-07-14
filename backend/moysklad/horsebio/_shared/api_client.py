#!/usr/bin/env python3
"""
Общая библиотека для работы с API МойСклад.

Класс ProductionHelper — универсальный HTTP-клиент с методами для:
- Базовых запросов: _get, _post, _put, _delete, _get_all_pages
- Складов и ячеек: get_stores, get_store_slots, get_store_zones
- Техкарт и производства: get_processing_plans, get_processing_plan_materials
- Остатков: get_stock_all, get_stock_by_store, get_stock_by_slots
- Перемещений: create_move, create_internal_move_from_slot/to_slot
- Организации: get_default_organization

Используется из: 01_daemons, 02_checks, 03_updates.
"""

import json
import os
import requests
import concurrent.futures
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / '.env')

# Конфигурация
MOYSKLAD_TOKEN = os.getenv('MOYSKLAD_TOKEN')
if not MOYSKLAD_TOKEN:
    raise ValueError("MOYSKLAD_TOKEN environment variable is required")
BASE_URL = "https://api.moysklad.ru/api/remap/1.2"


@dataclass
class MaterialRequirement:
    """Требуемый материал для производства"""
    product_id: str
    product_name: str
    product_meta: Dict
    quantity_needed: float
    slot_id: Optional[str] = None
    slot_name: Optional[str] = None
    slot_meta: Optional[Dict] = None
    available_in_slot: float = 0.0


@dataclass
class StockInSlot:
    """Остаток товара в ячейке"""
    product_id: str
    product_name: str
    product_meta: Dict
    slot_id: str
    slot_name: str
    slot_meta: Dict
    quantity: float
    store_id: str
    store_name: str


class ProductionHelper:
    """Помощник для работы с адресным хранением при производстве"""

    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept-Encoding": "gzip",
            "Content-Type": "application/json"
        }
        self._stores_cache = {}
        self._slots_cache = {}

    # === Базовые методы API ===

    def _get(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """GET запрос к API. При таймауте автоматически повторяет запрос."""
        import time
        url = f"{BASE_URL}{endpoint}"
        while True:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    requests.get, url, headers=self.headers, params=params, timeout=10
                )
                try:
                    response = future.result(timeout=10)
                    break
                except (concurrent.futures.TimeoutError,
                        requests.exceptions.ConnectionError,
                        requests.exceptions.Timeout):
                    time.sleep(0.5)
        response.raise_for_status()
        return response.json()

    def _post(self, endpoint: str, data: Dict) -> Dict:
        """POST запрос к API"""
        url = f"{BASE_URL}{endpoint}"
        response = requests.post(url, headers=self.headers, json=data, timeout=10)
        if not response.ok:
            print(f"Ошибка API: {response.status_code}")
            print(f"Ответ: {response.text}")
        response.raise_for_status()
        return response.json()

    def _delete(self, endpoint: str) -> None:
        """DELETE запрос к API"""
        url = f"{BASE_URL}{endpoint}"
        response = requests.delete(url, headers=self.headers, timeout=10)
        if not response.ok:
            print(f"Ошибка API: {response.status_code}")
            print(f"Ответ: {response.text}")
        response.raise_for_status()

    def _put(self, endpoint: str, data: Dict) -> Dict:
        """PUT запрос к API (обновление)"""
        url = f"{BASE_URL}{endpoint}"
        response = requests.put(url, headers=self.headers, json=data, timeout=10)
        if not response.ok:
            print(f"Ошибка API: {response.status_code}")
            print(f"Ответ: {response.text}")
        response.raise_for_status()
        return response.json()

    def _get_all_pages(self, endpoint: str, params: Optional[Dict] = None) -> List[Dict]:
        """Получить все страницы результатов"""
        all_items = []
        offset = 0
        # МойСклад молча игнорирует expand при limit > 100 — вложенные объекты
        # приходят без полей (только meta)
        limit = 100 if params and params.get('expand') else 1000

        while True:
            page_params = params.copy() if params else {}
            page_params['offset'] = offset
            page_params['limit'] = limit

            result = self._get(endpoint, page_params)
            rows = result.get('rows', [])

            if not rows:
                break

            all_items.extend(rows)

            if len(rows) < limit:
                break

            offset += limit

        return all_items

    # === Склады и ячейки ===

    def get_stores(self) -> List[Dict]:
        """Получить все склады"""
        return self._get_all_pages("/entity/store")

    def get_store_by_name(self, name: str) -> Optional[Dict]:
        """Найти склад по имени (частичное совпадение)"""
        stores = self.get_stores()
        for store in stores:
            if name.lower() in store.get('name', '').lower():
                return store
        return None

    def get_store_slots(self, store_id: str) -> List[Dict]:
        """Получить ячейки склада"""
        if store_id in self._slots_cache:
            return self._slots_cache[store_id]

        slots = self._get_all_pages(f"/entity/store/{store_id}/slots")
        self._slots_cache[store_id] = slots
        return slots

    def get_store_zones(self, store_id: str) -> List[Dict]:
        """Получить зоны склада"""
        return self._get_all_pages(f"/entity/store/{store_id}/zones")

    # === Техкарты ===

    def get_processing_plans(self) -> List[Dict]:
        """Получить все техкарты"""
        return self._get_all_pages("/entity/processingplan")

    def get_processing_plan(self, plan_id: str) -> Dict:
        """Получить техкарту по ID"""
        return self._get(f"/entity/processingplan/{plan_id}")

    def get_processing_plan_materials(self, plan_id: str) -> List[Dict]:
        """Получить материалы техкарты с expand для получения данных о товарах"""
        result = self._get(f"/entity/processingplan/{plan_id}/materials", {"expand": "product,assortment"})
        return result.get('rows', [])

    def get_processing_plan_products(self, plan_id: str) -> List[Dict]:
        """Получить готовую продукцию техкарты с expand для получения данных о товарах"""
        result = self._get(f"/entity/processingplan/{plan_id}/products", {"expand": "product,assortment"})
        return result.get('rows', [])

    # === Выполнение этапов (документы производства) ===

    def get_processings(self, limit: int = 100) -> List[Dict]:
        """Получить список выполнений этапов (документы производства)"""
        result = self._get("/entity/processing", {"limit": limit, "order": "moment,desc"})
        return result.get("rows", [])

    def get_processing(self, processing_id: str) -> Dict:
        """Получить выполнение этапа по ID"""
        return self._get(f"/entity/processing/{processing_id}")

    def get_processing_materials(self, processing_id: str) -> List[Dict]:
        """Получить материалы выполнения этапа"""
        result = self._get(f"/entity/processing/{processing_id}/materials", {"expand": "assortment"})
        return result.get("rows", [])

    def get_processing_products(self, processing_id: str) -> List[Dict]:
        """Получить готовую продукцию выполнения этапа"""
        result = self._get(f"/entity/processing/{processing_id}/products", {"expand": "assortment"})
        return result.get("rows", [])

    def get_processings_by_store(self, materials_store_id: str, limit: int = 50) -> List[Dict]:
        """Получить выполнения этапов для указанного склада материалов"""
        result = self._get("/entity/processing", {
            "filter": f"materialsStore=https://api.moysklad.ru/api/remap/1.2/entity/store/{materials_store_id}",
            "order": "moment,desc",
            "limit": limit
        })
        return result.get("rows", [])

    # === Остатки ===

    def get_stock_by_store(self, store_id: str) -> List[Dict]:
        """Получить остатки по складу"""
        params = {
            "filter": f"store=https://api.moysklad.ru/api/remap/1.2/entity/store/{store_id}"
        }
        return self._get_all_pages("/report/stock/bystore", params)

    def get_stock_all(self) -> List[Dict]:
        """Получить все остатки"""
        return self._get_all_pages("/report/stock/all")

    def get_stock_by_slots(self, store_id: str) -> Dict[str, Dict[str, float]]:
        """
        Получить текущие остатки товаров по ячейкам склада.

        Использует endpoint /report/stock/byslot/current который показывает
        актуальные остатки с разбивкой по товарам и ячейкам.

        Args:
            store_id: ID склада

        Returns:
            Словарь {product_id: {slot_id: quantity, ...}, ...}

        Example:
            {
                "product-id-1": {
                    "slot-id-A1": 150.0,
                    "slot-id-A2": 50.0
                },
                "product-id-2": {
                    "slot-id-B1": 25.0
                }
            }
        """
        from collections import defaultdict

        print(f"  🔍 Запрос остатков по ячейкам...")

        # Словарь: product_id -> slot_id -> quantity
        stock = defaultdict(lambda: defaultdict(float))

        try:
            # Запрашиваем остатки по ячейкам для данного склада
            result = self._get("/report/stock/byslot/current", {
                "filter": f"storeId={store_id}"
            })

            # API возвращает список напрямую (не в rows)
            items = result if isinstance(result, list) else result.get("rows", [])

            for item in items:
                product_id = item.get("assortmentId")
                slot_id = item.get("slotId")
                quantity = item.get("stock", 0)

                if product_id and slot_id and quantity > 0:
                    stock[product_id][slot_id] = quantity

            print(f"    ✅ Найдено {len(stock)} товаров с остатками в ячейках")

        except Exception as e:
            print(f"    ⚠️ Ошибка при получении остатков: {e}")

        # Конвертируем в обычный dict
        return {k: dict(v) for k, v in stock.items()}

    # === Перемещения ===

    def get_default_organization(self) -> Dict:
        """Получить организацию по умолчанию"""
        result = self._get("/entity/organization", {"limit": 1})
        rows = result.get('rows', [])
        if rows:
            return rows[0]
        raise Exception("Организация не найдена")

    def create_move(
        self,
        source_store_id: str,
        target_store_id: str,
        positions: List[Dict],
        description: str = "",
        source_slot_id: Optional[str] = None,
        target_slot_id: Optional[str] = None
    ) -> Dict:
        """
        Создать перемещение.

        Args:
            source_store_id: ID склада-источника
            target_store_id: ID склада-назначения
            positions: Позиции [{product_id, quantity, source_slot_id?, target_slot_id?}]
            description: Описание перемещения
            source_slot_id: Ячейка-источник по умолчанию (для всех позиций)
            target_slot_id: Ячейка-назначение по умолчанию (для всех позиций)
        """
        # Формируем мета склада-источника
        source_store_meta = {
            "meta": {
                "href": f"{BASE_URL}/entity/store/{source_store_id}",
                "type": "store",
                "mediaType": "application/json"
            }
        }

        # Формируем мета склада-назначения
        target_store_meta = {
            "meta": {
                "href": f"{BASE_URL}/entity/store/{target_store_id}",
                "type": "store",
                "mediaType": "application/json"
            }
        }

        # Формируем позиции
        move_positions = []
        for pos in positions:
            position = {
                "quantity": pos['quantity'],
                "assortment": {
                    "meta": {
                        "href": f"{BASE_URL}/entity/product/{pos['product_id']}",
                        "type": "product",
                        "mediaType": "application/json"
                    }
                }
            }

            # Ячейка-источник
            slot_source = pos.get('source_slot_id') or source_slot_id
            if slot_source:
                position["sourceSlot"] = {
                    "meta": {
                        "href": f"{BASE_URL}/entity/store/{source_store_id}/slots/{slot_source}",
                        "type": "slot",
                        "mediaType": "application/json"
                    }
                }

            # Ячейка-назначение
            slot_target = pos.get('target_slot_id') or target_slot_id
            if slot_target:
                position["targetSlot"] = {
                    "meta": {
                        "href": f"{BASE_URL}/entity/store/{target_store_id}/slots/{slot_target}",
                        "type": "slot",
                        "mediaType": "application/json"
                    }
                }

            move_positions.append(position)

        # Получаем организацию
        org = self.get_default_organization()
        org_meta = {
            "meta": {
                "href": f"{BASE_URL}/entity/organization/{org.get('id')}",
                "type": "organization",
                "mediaType": "application/json"
            }
        }

        # Формируем тело запроса
        move_data = {
            "organization": org_meta,
            "sourceStore": source_store_meta,
            "targetStore": target_store_meta,
            "positions": move_positions
        }

        if description:
            move_data["description"] = description

        return self._post("/entity/move", move_data)

    def create_internal_move_from_slot(
        self,
        store_id: str,
        positions: List[Dict],
        description: str = "Снятие с ячейки перед производством"
    ) -> Dict:
        """
        Создать внутреннее перемещение: с ячейки на склад (без ячейки).

        Используется для "снятия с полки" материалов перед производством.

        Args:
            store_id: ID склада
            positions: [{product_id, quantity, source_slot_id}]
            description: Описание
        """
        # В МойСклад для перемещения внутри склада используется тот же склад
        return self.create_move(
            source_store_id=store_id,
            target_store_id=store_id,
            positions=positions,
            description=description
            # target_slot_id не указываем - товар попадает "на пол"
        )

    def create_internal_move_to_slot(
        self,
        store_id: str,
        target_slot_id: str,
        positions: List[Dict],
        description: str = "Размещение в ячейку после производства"
    ) -> Dict:
        """
        Создать внутреннее перемещение: со склада (без ячейки) в ячейку.

        Используется для размещения готовой продукции в ячейку.

        Args:
            store_id: ID склада
            target_slot_id: ID целевой ячейки
            positions: [{product_id, quantity}]
            description: Описание
        """
        return self.create_move(
            source_store_id=store_id,
            target_store_id=store_id,
            positions=positions,
            description=description,
            target_slot_id=target_slot_id
            # source_slot_id не указываем - берем товар "с пола"
        )

    # === Основная логика ===

    def prepare_materials_for_production(
        self,
        processing_plan_id: str,
        materials_store_id: str,
        quantity_multiplier: float = 1.0
    ) -> Tuple[bool, str, Optional[Dict]]:
        """
        Подготовить материалы для производства - снять с ячеек.

        Args:
            processing_plan_id: ID техкарты
            materials_store_id: ID склада материалов
            quantity_multiplier: Множитель количества (для партии)

        Returns:
            (успех, сообщение, данные перемещения)
        """
        try:
            # 1. Получаем материалы из техкарты
            materials = self.get_processing_plan_materials(processing_plan_id)
            if not materials:
                return False, "Техкарта не содержит материалов", None

            print(f"\nМатериалы техкарты ({len(materials)}):")
            for mat in materials:
                product = mat.get('product', mat.get('assortment', {}))
                name = product.get('name', 'Неизвестный товар')
                qty = mat.get('quantity', 0) * quantity_multiplier
                print(f"  - {name}: {qty}")

            # 2. Получаем ячейки склада
            slots = self.get_store_slots(materials_store_id)
            if not slots:
                return False, "На складе нет ячеек", None

            print(f"\nЯчейки на складе ({len(slots)}):")
            for slot in slots:
                print(f"  - {slot.get('name')} (ID: {slot.get('id')})")

            # 3. Формируем позиции для перемещения
            positions = []
            for mat in materials:
                product = mat.get('product', mat.get('assortment', {}))
                product_meta = product.get('meta', {})
                product_href = product_meta.get('href', '')

                # Извлекаем product_id из href
                product_id = product_href.split('/')[-1] if product_href else None

                if not product_id:
                    print(f"  Предупреждение: не удалось получить ID для {product.get('name')}")
                    continue

                qty = mat.get('quantity', 0) * quantity_multiplier

                # Берем первую ячейку для упрощения
                if slots:
                    positions.append({
                        'product_id': product_id,
                        'quantity': qty,
                        'source_slot_id': slots[0].get('id')
                    })

            if not positions:
                return False, "Не удалось сформировать позиции для перемещения", None

            print(f"\nПозиции для перемещения ({len(positions)}):")
            for pos in positions:
                print(f"  - Product: {pos['product_id']}, Qty: {pos['quantity']}")

            # 5. Создаем перемещение
            move = self.create_internal_move_from_slot(
                store_id=materials_store_id,
                positions=positions,
                description=f"Подготовка к производству (техкарта: {processing_plan_id})"
            )

            return True, "Перемещение создано успешно", move

        except Exception as e:
            return False, f"Ошибка: {str(e)}", None

    def place_finished_product_to_slot(
        self,
        processing_plan_id: str,
        finished_store_id: str,
        target_slot_id: str,
        quantity_multiplier: float = 1.0
    ) -> Tuple[bool, str, Optional[Dict]]:
        """
        Разместить готовую продукцию в ячейку после производства.

        Args:
            processing_plan_id: ID техкарты
            finished_store_id: ID склада готовой продукции
            target_slot_id: ID целевой ячейки
            quantity_multiplier: Множитель количества

        Returns:
            (успех, сообщение, данные перемещения)
        """
        try:
            # 1. Получаем готовую продукцию из техкарты
            products = self.get_processing_plan_products(processing_plan_id)
            if not products:
                return False, "Техкарта не содержит готовой продукции", None

            print(f"\nГотовая продукция техкарты ({len(products)}):")
            for prod in products:
                product = prod.get('product', prod.get('assortment', {}))
                name = product.get('name', 'Неизвестный товар')
                qty = prod.get('quantity', 0) * quantity_multiplier
                print(f"  - {name}: {qty}")

            # 2. Формируем позиции для перемещения
            positions = []
            for prod in products:
                product = prod.get('product', prod.get('assortment', {}))
                product_meta = product.get('meta', {})
                product_href = product_meta.get('href', '')

                product_id = product_href.split('/')[-1] if product_href else None

                if not product_id:
                    print(f"  Предупреждение: не удалось получить ID для {product.get('name')}")
                    continue

                qty = prod.get('quantity', 0) * quantity_multiplier
                positions.append({
                    'product_id': product_id,
                    'quantity': qty
                })

            if not positions:
                return False, "Не удалось сформировать позиции для перемещения", None

            # 3. Создаем перемещение в ячейку
            move = self.create_internal_move_to_slot(
                store_id=finished_store_id,
                target_slot_id=target_slot_id,
                positions=positions,
                description=f"Размещение готовой продукции (техкарта: {processing_plan_id})"
            )

            return True, "Перемещение создано успешно", move

        except Exception as e:
            return False, f"Ошибка: {str(e)}", None


def print_stores_info(helper: ProductionHelper):
    """Вывести информацию о складах и ячейках"""
    print("=" * 60)
    print("СКЛАДЫ И ЯЧЕЙКИ")
    print("=" * 60)

    stores = helper.get_stores()
    for store in stores:
        print(f"\n📦 {store.get('name')}")
        print(f"   ID: {store.get('id')}")

        slots = helper.get_store_slots(store.get('id'))
        if slots:
            print(f"   Ячейки ({len(slots)}):")
            for slot in slots[:5]:
                print(f"     - {slot.get('name')} (ID: {slot.get('id')})")
            if len(slots) > 5:
                print(f"     ... и еще {len(slots) - 5}")


def print_processing_plans(helper: ProductionHelper):
    """Вывести список техкарт"""
    print("\n" + "=" * 60)
    print("ТЕХКАРТЫ")
    print("=" * 60)

    plans = helper.get_processing_plans()
    for i, plan in enumerate(plans[:10], 1):
        print(f"\n{i}. {plan.get('name')}")
        print(f"   ID: {plan.get('id')}")


def demo_workflow(helper: ProductionHelper):
    """Демонстрация рабочего процесса"""
    print("\n" + "=" * 60)
    print("ДЕМО: Подготовка к производству")
    print("=" * 60)

    # Ищем тестовые склады
    materials_store = helper.get_store_by_name("Тестовый склад | Материалы")
    finished_store = helper.get_store_by_name("Тестовый склад | Готовая продукция")

    if not materials_store:
        print("❌ Склад материалов не найден")
        return

    if not finished_store:
        print("❌ Склад готовой продукции не найден")
        return

    print(f"\n✅ Склад материалов: {materials_store.get('name')}")
    print(f"✅ Склад готовой продукции: {finished_store.get('name')}")

    # Ищем техкарту для теста
    plans = helper.get_processing_plans()
    if not plans:
        print("❌ Техкарты не найдены")
        return

    test_plan = plans[0]
    print(f"\n📋 Тестовая техкарта: {test_plan.get('name')}")
    print(f"   ID: {test_plan.get('id')}")

    # Получаем материалы
    print("\n📦 Материалы техкарты:")
    materials = helper.get_processing_plan_materials(test_plan.get('id'))
    for mat in materials:
        product = mat.get('product', mat.get('assortment', {}))
        print(f"   - {product.get('name')}: {mat.get('quantity')}")

    # Получаем готовую продукцию
    print("\n🎁 Готовая продукция:")
    products = helper.get_processing_plan_products(test_plan.get('id'))
    for prod in products:
        product = prod.get('product', prod.get('assortment', {}))
        print(f"   - {product.get('name')}: {prod.get('quantity')}")


def main():
    """Главная функция"""
    helper = ProductionHelper(MOYSKLAD_TOKEN)

    print("🏭 СИСТЕМА АДРЕСНОГО ХРАНЕНИЯ ДЛЯ ПРОИЗВОДСТВА")
    print("=" * 60)

    while True:
        print("\n📋 МЕНЮ:")
        print("1. Показать склады и ячейки")
        print("2. Показать техкарты")
        print("3. Демо workflow")
        print("4. Подготовить материалы (снять с ячеек)")
        print("5. Разместить готовую продукцию в ячейку")
        print("0. Выход")

        choice = input("\nВыбор: ").strip()

        if choice == '0':
            break
        elif choice == '1':
            print_stores_info(helper)
        elif choice == '2':
            print_processing_plans(helper)
        elif choice == '3':
            demo_workflow(helper)
        elif choice == '4':
            plan_id = input("ID техкарты: ").strip()
            store_id = input("ID склада материалов: ").strip()
            qty = float(input("Множитель количества (1.0): ").strip() or "1.0")

            success, msg, move = helper.prepare_materials_for_production(
                plan_id, store_id, qty
            )
            print(f"\n{'✅' if success else '❌'} {msg}")
            if move:
                print(f"   ID перемещения: {move.get('id')}")
        elif choice == '5':
            plan_id = input("ID техкарты: ").strip()
            store_id = input("ID склада готовой продукции: ").strip()
            slot_id = input("ID целевой ячейки: ").strip()
            qty = float(input("Множитель количества (1.0): ").strip() or "1.0")

            success, msg, move = helper.place_finished_product_to_slot(
                plan_id, store_id, slot_id, qty
            )
            print(f"\n{'✅' if success else '❌'} {msg}")
            if move:
                print(f"   ID перемещения: {move.get('id')}")
        else:
            print("Неверный выбор")


if __name__ == "__main__":
    main()
