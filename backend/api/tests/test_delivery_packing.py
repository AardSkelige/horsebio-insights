"""Тесты движка раскладки заказа по коробкам (api.services.delivery.packing)."""

from django.test import SimpleTestCase

from api.services.delivery.box_catalog import MAX_BOX_WEIGHT_G
from api.services.delivery.packing import Item, fits_by_dims, pack


class FitsByDimsTests(SimpleTestCase):
    def test_fits_in_some_orientation(self):
        # предмет 10×10×2 не влезает в сечение коробки «200» (24×6×6)
        self.assertFalse(fits_by_dims((2, 10, 10), (6, 6, 24)))
        # но влезает в S (13×20×20)
        self.assertTrue(fits_by_dims((2, 10, 10), (13, 20, 20)))

    def test_exact_fit(self):
        self.assertTrue(fits_by_dims((13, 20, 20), (13, 20, 20)))


class PackingTests(SimpleTestCase):
    def test_single_small_item_uses_smallest_box(self):
        item = Item(sku="A", name="крошка", qty=1, weight_g=50, dims_cm=(5, 5, 5))
        res = pack([item])
        self.assertEqual(res.total_places, 1)
        self.assertEqual(res.boxes[0].box.code, "XS")
        self.assertFalse(res.unpackable)

    def test_weight_limit_forces_split(self):
        # две единицы по 8 кг не могут ехать в одной коробке (лимит 14 кг)
        item = Item(sku="H", name="тяжёлое", qty=2, weight_g=8000, dims_cm=(10, 10, 10))
        res = pack([item])
        self.assertEqual(res.total_places, 2)
        for b in res.boxes:
            self.assertLessEqual(b.weight_g, MAX_BOX_WEIGHT_G)

    def test_overweight_unit_is_unpackable(self):
        item = Item(sku="X", name="слишком тяжёлое", qty=1, weight_g=20000, dims_cm=(10, 10, 10))
        res = pack([item])
        self.assertEqual(res.total_places, 0)
        self.assertEqual(len(res.unpackable), 1)

    def test_oversized_unit_is_unpackable(self):
        # сторона больше самой крупной коробки (XL 40×30×40) — не влезает никуда
        item = Item(sku="B", name="негабарит", qty=1, weight_g=100, dims_cm=(50, 5, 5))
        res = pack([item])
        self.assertEqual(len(res.unpackable), 1)

    def test_consolidation_prefers_fewer_boxes(self):
        # 8 средних единиц, влезающих в крупную тару, должны консолидироваться,
        # а не разъехаться по 8 отдельным полупустым коробкам
        item = Item(sku="C", name="банка", qty=8, weight_g=400, dims_cm=(15, 15, 15))
        res = pack([item])
        self.assertLess(res.total_places, 8)

    def test_buckets_go_to_M_box_separately(self):
        bucket = Item(sku="V", name="ведро 5,8", qty=1, weight_g=6000,
                      dims_cm=(24, 20, 12), is_bucket_58=True)
        other = Item(sku="O", name="прочее", qty=1, weight_g=100, dims_cm=(5, 5, 5))
        res = pack([bucket, other])
        bucket_boxes = [b for b in res.boxes if any(u.sku == "V" for u in b.units)]
        self.assertTrue(bucket_boxes)
        for b in bucket_boxes:
            self.assertEqual(b.box.code, "M")
            # ведро едет отдельно — без чужих товаров
            self.assertTrue(all(u.sku == "V" for u in b.units))

    def test_totals_are_consistent(self):
        items = [
            Item(sku="A", name="a", qty=3, weight_g=500, dims_cm=(10, 10, 10)),
            Item(sku="B", name="b", qty=2, weight_g=300, dims_cm=(8, 8, 8)),
        ]
        res = pack(items)
        self.assertAlmostEqual(res.total_weight_g, 3 * 500 + 2 * 300)
        self.assertEqual(sum(res.summary_by_box().values()), res.total_places)
