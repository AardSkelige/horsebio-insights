import { describe, it, expect, vi, afterEach } from 'vitest';
import { sevOf, SEV, msLink, fmtDuration, relTime, KIND_MS_TYPE } from './checksShared';

describe('sevOf', () => {
    it('возвращает известный уровень', () => {
        expect(sevOf('critical')).toBe(SEV.critical);
        expect(sevOf('ok')).toBe(SEV.ok);
    });

    it('неизвестный уровень падает в info', () => {
        expect(sevOf('whatever')).toBe(SEV.info);
        expect(sevOf(undefined)).toBe(SEV.info);
    });
});

describe('msLink', () => {
    it('строит ссылку на документ МойСклад', () => {
        expect(msLink('enter', 'abc-123')).toBe('https://online.moysklad.ru/app/#enter/edit?id=abc-123');
    });

    it('без типа или id ссылки нет', () => {
        expect(msLink(null, 'abc')).toBeNull();
        expect(msLink('enter', null)).toBeNull();
    });

    it('kinds без документа помечены null в KIND_MS_TYPE', () => {
        expect(KIND_MS_TYPE.deviations).toBeNull();
        expect(KIND_MS_TYPE.supply_jumps).toBeNull();
    });
});

describe('fmtDuration', () => {
    it('секунды и минуты', () => {
        expect(fmtDuration(42)).toBe('42с');
        expect(fmtDuration(125)).toBe('2м 5с');
    });

    it('null/undefined — пустая строка', () => {
        expect(fmtDuration(null)).toBe('');
        expect(fmtDuration(undefined)).toBe('');
    });
});

describe('relTime', () => {
    afterEach(() => vi.useRealTimers());

    it('сегодня / вчера / дата', () => {
        vi.useFakeTimers();
        vi.setSystemTime(new Date('2026-07-02T12:00:00'));
        expect(relTime('2026-07-02 09:15')).toBe('сегодня 09:15');
        expect(relTime('2026-07-01 23:40')).toBe('вчера 23:40');
        expect(relTime('2026-06-20 08:00')).toBe('20.06 08:00');
    });

    it('пустое или кривое значение не роняет рендер', () => {
        expect(relTime(null)).toBe('—');
        expect(relTime('не дата')).toBe('не дата');
    });
});
