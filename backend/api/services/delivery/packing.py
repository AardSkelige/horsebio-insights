"""Движок оценочной раскладки заказа по коробкам.

Модель — ДВУХУРОВНЕВАЯ, намеренно не «3D-тетрис»:

1. Габаритный фильтр (жёсткое ограничение): товар кладётся в коробку, только
   если три его стороны помещаются в стороны коробки хотя бы в одной ориентации
   (fits_by_dims). Это отсекает физически невозможное — например, товар 10 см
   не влезет в сечение коробки «200» (6×6 см), даже если проходит по объёму.

2. Плотность набивки — по объёму с коэффициентом заполнения (fill_rate): внутри
   подходящих по габаритам коробок считаем, сколько влезет, по объёму. Точную
   геометрию укладки не моделируем: товар (вёдра, банки в пупырке/стрейтче)
   мнётся и перекладывается, поэтому объёмная модель + калибруемый коэффициент
   честнее и проще жёсткой 3D-укладки. Остаточную погрешность гасит fill_rate.

Правила отдела упаковки: коробка ≤ 14 кг; вёдра 5,8 л едут отдельно в коробке M.

На вход движок принимает только позиции с известными весом и габаритами —
отсутствие данных обрабатывается ВЫШЕ (расчёт блокируется, см. оркестратор).
"""

from dataclasses import dataclass, field

from .box_catalog import (
    BOXES_BY_VOLUME,
    BOX_BY_CODE,
    BUCKET_BOX_CODE,
    DEFAULT_FILL_RATE,
    MAX_BOX_WEIGHT_G,
    Box,
)


@dataclass(frozen=True)
class Item:
    """Позиция заказа. dims_cm — (длина, ширина, высота) упаковки единицы товара."""
    sku: str
    name: str
    qty: int
    weight_g: float
    dims_cm: tuple[float, float, float]
    is_bucket_58: bool = False

    @property
    def unit_volume_cm3(self) -> float:
        l, w, h = self.dims_cm
        return l * w * h

    @property
    def sorted_dims(self) -> tuple[float, float, float]:
        return tuple(sorted(self.dims_cm))  # type: ignore[return-value]


@dataclass
class _Unit:
    """Одна физическая единица товара (позиция развёрнута по количеству)."""
    sku: str
    name: str
    weight_g: float
    volume_cm3: float
    sorted_dims: tuple[float, float, float]


@dataclass
class PackedBox:
    """Заполненная коробка: тип + вложенные единицы."""
    box: Box
    units: list[_Unit] = field(default_factory=list)

    @property
    def weight_g(self) -> float:
        return sum(u.weight_g for u in self.units)

    @property
    def used_volume_cm3(self) -> float:
        return sum(u.volume_cm3 for u in self.units)

    def usable_volume_cm3(self, fill_rate: float) -> float:
        return self.box.volume_cm3 * fill_rate

    def can_add(self, u: _Unit, fill_rate: float) -> bool:
        if not fits_by_dims(u.sorted_dims, self.box.sorted_dims):
            return False
        if self.weight_g + u.weight_g > MAX_BOX_WEIGHT_G:
            return False
        if self.used_volume_cm3 + u.volume_cm3 > self.usable_volume_cm3(fill_rate):
            return False
        return True


@dataclass
class PackResult:
    boxes: list[PackedBox]
    # Единицы, не влезающие ни в одну коробку (габаритнее всех / тяжелее 14 кг /
    # объёмнее максимальной коробки). При корректных данных должно быть пусто.
    unpackable: list[_Unit] = field(default_factory=list)

    @property
    def total_weight_g(self) -> float:
        return sum(b.weight_g for b in self.boxes)

    @property
    def total_volume_cm3(self) -> float:
        return sum(b.used_volume_cm3 for b in self.boxes)

    @property
    def total_places(self) -> int:
        return len(self.boxes)

    def summary_by_box(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for b in self.boxes:
            counts[b.box.code] = counts.get(b.box.code, 0) + 1
        return counts


def fits_by_dims(
    item_sorted: tuple[float, float, float],
    box_sorted: tuple[float, float, float],
) -> bool:
    """Помещается ли предмет в коробку хотя бы в одной ориентации.

    Сравниваем отсортированные стороны поштучно: если каждая сторона предмета
    не больше соответствующей стороны коробки — предмет влезает при подходящем
    повороте.
    """
    return all(i <= b for i, b in zip(item_sorted, box_sorted))


def _smallest_fitting_box(u: _Unit, allowed: tuple[Box, ...], fill_rate: float) -> Box | None:
    """Наименьшая по объёму коробка из allowed, куда единица влезает по габаритам
    и одна помещается по объёму с учётом fill_rate. None — если не влезает никуда."""
    for box in allowed:
        if not fits_by_dims(u.sorted_dims, box.sorted_dims):
            continue
        if u.volume_cm3 > box.volume_cm3 * fill_rate:
            continue
        return box
    return None


def _pack_units_ffd(
    units: list[_Unit], allowed: tuple[Box, ...], fill_rate: float
) -> tuple[list[PackedBox], list[_Unit]]:
    """First-Fit-Decreasing: крупные единицы раскладываем первыми, каждую —
    в первую открытую коробку, куда она входит; иначе открываем минимальную
    подходящую коробку из allowed."""
    units = sorted(units, key=lambda u: u.volume_cm3, reverse=True)
    open_boxes: list[PackedBox] = []
    unpackable: list[_Unit] = []
    for u in units:
        if u.weight_g > MAX_BOX_WEIGHT_G:
            unpackable.append(u)
            continue
        placed = next((b for b in open_boxes if b.can_add(u, fill_rate)), None)
        if placed is not None:
            placed.units.append(u)
            continue
        box = _smallest_fitting_box(u, allowed, fill_rate)
        if box is None:
            unpackable.append(u)
            continue
        nb = PackedBox(box)
        nb.units.append(u)
        open_boxes.append(nb)
    return open_boxes, unpackable


def _pack_units(
    units: list[_Unit], allowed: tuple[Box, ...], fill_rate: float
) -> tuple[list[PackedBox], list[_Unit]]:
    """Мультистартовый выбор раскладки.

    Жадный FFD склонен под каждый средний предмет открывать отдельную мелкую
    коробку и не консолидировать (6 коробок по 43% вместо одной большой). Чтобы
    это исправить, прогоняем FFD несколько раз, каждый раз запрещая всё более
    мелкие коробки (тем самым вынуждая укладку в крупную тару), и выбираем
    вариант с минимальным суммарным объёмом тары — именно за него платят ТК
    (сборные — за объём, СДЭК — за число мест, они коррелируют). Единицы, не
    влезающие даже в максимальную коробку, попадают в unpackable.

    allowed отсортирован по возрастанию объёма (BOXES_BY_VOLUME).
    """
    if not units:
        return [], []

    best_boxes: list[PackedBox] | None = None
    best_unpackable: list[_Unit] = []
    best_key: tuple[float, int] | None = None

    # k — сколько самых мелких коробок запрещаем; при k=0 доступны все.
    for k in range(len(allowed)):
        subset = allowed[k:]
        boxes, unpackable = _pack_units_ffd(units, subset, fill_rate)
        # ключ: сначала минимум unpackable, затем объём тары, затем число мест.
        key = (sum(b.box.volume_cm3 for b in boxes), len(boxes))
        if best_key is None or len(unpackable) < len(best_unpackable) or (
            len(unpackable) == len(best_unpackable) and key < best_key
        ):
            best_boxes, best_unpackable, best_key = boxes, unpackable, key
        # как только начали появляться невлезающие из-за запрета мелких — дальше
        # запрещать смысла нет (крупные их тоже не спасут по габаритам).
        if unpackable and not best_unpackable:
            break

    return best_boxes or [], best_unpackable


def pack(items: list[Item], fill_rate: float = DEFAULT_FILL_RATE) -> PackResult:
    """Разложить заказ по коробкам. Вёдра 5,8 л пакуются отдельным пулом строго
    в коробки типа M; остальное — по всему справочнику тары."""
    regular: list[_Unit] = []
    buckets: list[_Unit] = []
    for it in items:
        for _ in range(it.qty):
            u = _Unit(it.sku, it.name, it.weight_g, it.unit_volume_cm3, it.sorted_dims)
            (buckets if it.is_bucket_58 else regular).append(u)

    boxes, unpackable = _pack_units(regular, BOXES_BY_VOLUME, fill_rate)

    if buckets:
        bucket_box = BOX_BY_CODE[BUCKET_BOX_CODE]
        b_boxes, b_unpack = _pack_units(buckets, (bucket_box,), fill_rate)
        boxes += b_boxes
        unpackable += b_unpack

    return PackResult(boxes=boxes, unpackable=unpackable)
