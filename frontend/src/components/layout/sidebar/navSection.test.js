import { describe, expect, it } from 'vitest';
import { navSection } from './navGroups';

describe('пункт меню для адреса', () => {
    it('вложенные страницы раздела подсвечивают сам раздел', () => {
        expect(navSection('/raw-materials')).toBe('/raw-materials');
        expect(navSection('/raw-materials/receipts')).toBe('/raw-materials');
        expect(navSection('/raw-materials/receipts/7')).toBe('/raw-materials');
        expect(navSection('/protocols/123')).toBe('/protocols');
    });

    it('соседние разделы с общим началом адреса не путаются, главная не захватывает всё', () => {
        expect(navSection('/analysis/abc')).toBe('/analysis/abc');
        expect(navSection('/analysis/fbo')).toBe('/analysis/fbo');
        expect(navSection('/raw-materials-x')).toBe('/raw-materials-x');
        expect(navSection('/')).toBe('/');
    });
});
