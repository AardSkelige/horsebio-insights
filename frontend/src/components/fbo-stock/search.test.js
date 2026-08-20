import { describe, it, expect } from 'vitest';
import { matchesQuery, parseQuery, searchIndex } from './search';

// Реальные позиции со склада готовой продукции
const ITEMS = [
    { name: 'Псиллиум GastroPro для собак и кошек, 150 г', article: '12-11GP0150', code: '2-311' },
    { name: 'Хондропротектор Хондрофит ArtroPro для собак крупных пород, 500 мл', article: '11-03AP0500', code: '2-014' },
    { name: 'Хондропротектор Хондрофит ArtroPro для кошек и собак мелких пород, 200 мл', article: '11-10AP0200', code: '2-021' },
    { name: 'Хондропротектор Хондро Лайт ArtroPro для лошадей, 300 г', article: '01-27AP0300', code: '2-127' },
    { name: 'Говяжий Коллаген ArtroPro для собак, 150 г', article: '11-41AP0150', code: '2-002' },
];

const find = (query) => ITEMS
    .filter((item) => matchesQuery(searchIndex(item), parseQuery(query)))
    .map((item) => item.article);

describe('поиск по остаткам', () => {
    it('находит по нескольким частям в любом порядке', () => {
        expect(find('хондрофит 500')).toEqual(['11-03AP0500']);
        expect(find('500 хондрофит')).toEqual(['11-03AP0500']);
        expect(find('хондрофит 200')).toEqual(['11-10AP0200']);
    });

    it('находит по обрывку слова', () => {
        expect(find('псил 150')).toEqual(['12-11GP0150']);
        expect(find('хондро 300')).toEqual(['01-27AP0300']);
    });

    it('без частей возвращает всё', () => {
        expect(find('')).toHaveLength(ITEMS.length);
        expect(find('   ')).toHaveLength(ITEMS.length);
    });

    it('различает похожие позиции по объёму', () => {
        expect(find('хондрофит')).toEqual(['11-03AP0500', '11-10AP0200']);
        expect(find('150')).toEqual(['12-11GP0150', '11-41AP0150']);
    });

    it('ищет по артикулу — с дефисом и без', () => {
        expect(find('11-41')).toEqual(['11-41AP0150']);
        expect(find('1141AP0150')).toEqual(['11-41AP0150']);
    });

    it('не различает регистр и ё/е', () => {
        expect(find('ХОНДРОФИТ 500')).toEqual(['11-03AP0500']);
        expect(find('говяжий коллаген')).toEqual(['11-41AP0150']);
        expect(find('Говяжiй'.replace('i', 'и'))).toEqual(['11-41AP0150']);
    });
});
