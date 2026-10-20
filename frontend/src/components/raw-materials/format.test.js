import { describe, expect, it } from 'vitest';
import { expiryState, formatQuantity, groupBySlot, matches } from './format';

const plain = (value, uom) => formatQuantity(value, uom).replace(/\s/g, ' ');

describe('склад сырья: форматирование', () => {
    it('крупные граммы и миллилитры показывает в кг и л', () => {
        expect(plain(2520000, 'г')).toBe('2 520 кг');
        expect(plain(435000, 'Мл')).toBe('435 л');
        expect(plain(462.8, 'г')).toBe('462,8 г');
        expect(plain(4200, 'шт')).toBe('4 200 шт');
    });

    it('делит сроки на просроченные, скорые и обычные', () => {
        const today = new Date(2026, 9, 20);
        expect(expiryState('2026-10-19', today)).toBe('expired');
        expect(expiryState('2026-10-20', today)).toBe('soon');
        expect(expiryState('2026-12-19', today)).toBe('soon');
        expect(expiryState('2027-03-01', today)).toBe('ok');
        expect(expiryState(null, today)).toBeNull();
    });

    it('ищет по названию, серии и ячейке', () => {
        const item = { name: 'Хондроитин сульфат', slot: 'A6', batches: [{ series: 'GN2508029' }] };
        expect(matches(item, 'хондр a6')).toBe(true);
        expect(matches(item, 'gn2508')).toBe(true);
        expect(matches(item, 'мсм')).toBe(false);
    });

    it('сортирует ячейки как на полке, без ячейки — в конце', () => {
        const items = ['A10', '', 'B1', 'A2'].map((slot, id) => ({ id, slot, name: 'x', batches: [] }));
        expect(groupBySlot(items).map((g) => g.slot)).toEqual(['A2', 'A10', 'B1', '']);
    });
    it('находит сырьё по любой ячейке, где оно лежит', () => {
        const item = { name: 'Хондроитин', slot: 'A6', slots: ['A6', 'C2'], batches: [] };
        expect(matches(item, 'c2')).toBe(true);
    });
});
