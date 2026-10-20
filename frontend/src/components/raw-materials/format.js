const BIG_UNITS = { г: 'кг', мл: 'л' };
const SOON_DAYS = 60;

const trim = (value) => value.toLocaleString('ru-RU', { maximumFractionDigits: 1 });

export function formatQuantity(value, uom) {
    const unit = String(uom || '').toLowerCase();
    if (BIG_UNITS[unit] && Math.abs(value) >= 1000) return `${trim(value / 1000)} ${BIG_UNITS[unit]}`;
    return `${trim(value)} ${unit}`.trim();
}

export function expiryState(isoDate, today = new Date()) {
    if (!isoDate) return null;
    const start = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    const days = Math.round((new Date(`${isoDate}T00:00:00`) - start) / 86_400_000);
    if (days < 0) return 'expired';
    if (days <= SOON_DAYS) return 'soon';
    return 'ok';
}

export function matches(item, query) {
    const words = query.toLowerCase().replace(/ё/g, 'е').split(/\s+/).filter(Boolean);
    const haystack = [item.name, item.slot, ...item.batches.map((b) => b.series)]
        .join(' ').toLowerCase().replace(/ё/g, 'е');
    return words.every((word) => haystack.includes(word));
}

export const TARA_GROUP = 'Тара';

const bySlot = (a, b) => a.localeCompare(b, 'ru', { numeric: true });

export function groupBySlot(items) {
    const groups = new Map();
    items.forEach((item) => {
        const key = item.slot || '';
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(item);
    });
    return [...groups.entries()]
        .sort(([a], [b]) => (!a) - (!b) || bySlot(a, b))
        .map(([slot, slotItems]) => ({ slot, items: slotItems }));
}
