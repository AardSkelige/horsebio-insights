import { describe, expect, it } from 'vitest';
import {
    duration, formatDate, formatDateTimeShort, money, moneyPrecise,
    num, numOrDash, percent, plural, pluralWith,
} from './formatters';

/** toLocaleString разделяет разряды неразрывным пробелом — сравниваем по смыслу. */
const plainSpaces = (s) => s.replace(/\u00A0|\u202F/g, ' ');

describe('числа и деньги', () => {
    it('разделяет разряды и округляет', () => {
        expect(plainSpaces(num(1966))).toBe('1 966');
        expect(plainSpaces(num(144791811.6))).toBe('144 791 812');
    });

    it('пустое значение — ноль, а в табличном варианте прочерк', () => {
        expect(num(null)).toBe('0');
        expect(num(undefined)).toBe('0');
        expect(numOrDash(0)).toBe('—');
        expect(numOrDash(null)).toBe('—');
    });

    it('деньги по умолчанию без копеек, точный вариант — с копейками', () => {
        expect(plainSpaces(money(144791811))).toBe('144 791 811 ₽');
        expect(plainSpaces(moneyPrecise(1234.5))).toBe('1 234,50 ₽');
    });

    it('проценты с одним знаком', () => {
        expect(percent(12.345)).toBe('12,3%');
    });
});

describe('склонение', () => {
    const forms = ['отгрузка', 'отгрузки', 'отгрузок'];

    it('работает на числах до двадцати', () => {
        expect(plural(1, ...forms)).toBe('отгрузка');
        expect(plural(3, ...forms)).toBe('отгрузки');
        expect(plural(7, ...forms)).toBe('отгрузок');
    });

    it('не путается на 11–14 — там всегда «отгрузок»', () => {
        expect(plural(11, ...forms)).toBe('отгрузок');
        expect(plural(12, ...forms)).toBe('отгрузок');
        expect(plural(14, ...forms)).toBe('отгрузок');
    });

    // прежние реализации ломались именно здесь: 21 давало «отгрузок»
    it('смотрит на последнюю цифру у чисел больше двадцати', () => {
        expect(plural(21, ...forms)).toBe('отгрузка');
        expect(plural(22, ...forms)).toBe('отгрузки');
        expect(plural(25, ...forms)).toBe('отгрузок');
        expect(plural(101, ...forms)).toBe('отгрузка');
        expect(plural(112, ...forms)).toBe('отгрузок');
    });

    it('ноль — множественная форма', () => {
        expect(plural(0, ...forms)).toBe('отгрузок');
    });

    it('pluralWith добавляет само число', () => {
        expect(plainSpaces(pluralWith(21, ...forms))).toBe('21 отгрузка');
    });
});

describe('длительность', () => {
    it('показывает часы и минуты', () => {
        expect(duration(76)).toBe('1 ч 16 м');
        expect(duration(45)).toBe('45 мин');
        expect(duration(120)).toBe('2 ч');
        expect(duration(0)).toBe('0');
    });
});

describe('даты', () => {
    it('разбирает дату без часового пояса', () => {
        expect(formatDate('2026-08-21')).toBe('21.08.2026');
        expect(formatDate(null)).toBe('-');
    });

    it('короткий формат — без года', () => {
        expect(formatDateTimeShort('2026-07-28T08:00:00')).toBe('28.07, 08:00');
        expect(formatDateTimeShort(null)).toBe('—');
    });
});
