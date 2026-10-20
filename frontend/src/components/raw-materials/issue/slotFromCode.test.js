import { describe, expect, it } from 'vitest';
import slotFromCode from './slotFromCode';

describe('QR ячейки', () => {
    it('достаёт ячейку из адреса наклейки, в том числе русскую А', () => {
        expect(slotFromCode('https://insight.horse-bio.ru/raw-materials/slot/A6')).toBe('A6');
        expect(slotFromCode(`https://insight.horse-bio.ru/raw-materials/slot/${encodeURIComponent('А1')}`)).toBe('А1');
    });

    it('чужие коды не принимает', () => {
        expect(slotFromCode('https://sklad.horse-bio.ru/cell/A1')).toBeNull();
        expect(slotFromCode('4607012345678')).toBeNull();
        expect(slotFromCode('https://insight.horse-bio.ru/raw-materials/')).toBeNull();
    });
});
