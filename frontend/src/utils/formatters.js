/**
 * Форматирование чисел, денег, дат и склонений — одно на всё приложение.
 *
 * До этого модуля в компонентах жило девятнадцать своих `fmt`, семь вариантов
 * денежного формата и шесть склонений, и они расходились: одна и та же сумма
 * показывалась то с копейками, то без, а ноль — то нулём, то прочерком.
 */

/** Целое число с разделителями разрядов: 1966 → «1 966». */
export const num = (value) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '0';
    return Math.round(Number(value)).toLocaleString('ru-RU');
};

/** То же, но пустое значение показывается прочерком — для таблиц. */
export const numOrDash = (value) => {
    if (value === null || value === undefined || value === 0) return '—';
    return num(value);
};

/**
 * Рубли без копеек: «144 791 811 ₽».
 *
 * Копейки в отчётах не нужны и мешают сравнивать столбцы, поэтому основной
 * денежный формат — округлённый. Для цены за единицу есть `moneyPrecise`.
 */
export const money = (value) => `${num(value)} ₽`;

/** Рубли с копейками: «1 234,56 ₽» — цена за единицу, тариф. */
export const moneyPrecise = (value) => {
    const n = Number(value ?? 0);
    return `${n.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ₽`;
};

/**
 * Склонение по числу: `plural(21, 'отгрузка', 'отгрузки', 'отгрузок')`.
 *
 * Прежние реализации проверяли `n === 1` и `n >= 2 && n <= 4`, из-за чего
 * ломались на числах больше двадцати: 21 давало «отгрузок» вместо «отгрузка».
 * Правило русского языка смотрит на последнюю цифру, кроме чисел 11–14.
 */
export const plural = (count, one, few, many) => {
    const n = Math.abs(Math.round(Number(count) || 0));
    const tens = n % 100;
    if (tens >= 11 && tens <= 14) return many;
    const ones = n % 10;
    if (ones === 1) return one;
    if (ones >= 2 && ones <= 4) return few;
    return many;
};

/** Число вместе со склонённым словом: «21 отгрузка». */
export const pluralWith = (count, one, few, many) => `${num(count)} ${plural(count, one, few, many)}`;

/** Длительность в минутах: 76 → «1 ч 16 м», 45 → «45 мин». */
export const duration = (minutes) => {
    const total = Math.max(0, Math.round(Number(minutes) || 0));
    if (!total) return '0';
    if (total < 60) return `${total} мин`;
    const h = Math.floor(total / 60);
    const m = total % 60;
    return m ? `${h} ч ${m} м` : `${h} ч`;
};

/** Проценты: 12.345 → «12,3%». */
export const percent = (value, digits = 1) => {
    const n = Number(value ?? 0);
    return `${n.toLocaleString('ru-RU', { minimumFractionDigits: digits, maximumFractionDigits: digits })}%`;
};

/**
 * Валюта средствами Intl — оставлена для мест, где нужен знак валюты
 * в позиции по правилам локали (графики, экспорт).
 */
export const formatCurrency = (value) => {
    if (value === null || value === undefined) return '-';
    return new Intl.NumberFormat('ru-RU', {
        style: 'currency',
        currency: 'RUB',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    }).format(value);
};

/** Число без валюты; пустое значение — прочерк. Историческое имя, см. `num`. */
export const formatNumber = (value) => {
    if (value === null || value === undefined) return '-';
    return num(value);
};

/** Дата: «21.08.2026». Строка режется без разбора часовых поясов. */
export const formatDate = (dateString) => {
    if (!dateString) return '-';
    const s = String(dateString).replace(' ', 'T');
    const [y, m, d] = s.substring(0, 10).split('-');
    if (!y || !m || !d) return dateString;
    return `${d}.${m}.${y}`;
};

/** Дата и время: «21.08.2026, 16:38». */
export const formatDateTime = (dateString) => {
    if (!dateString) return '—';
    const s = String(dateString).replace(' ', 'T');
    const date = new Date(s);
    if (isNaN(date.getTime())) return formatDate(dateString);
    return date.toLocaleDateString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    });
};

/** Только время: «08:00» — когда дата и так ясна из контекста страницы. */
export const timeOnly = (dateString) => {
    if (!dateString) return null;
    const date = new Date(String(dateString).replace(' ', 'T'));
    if (isNaN(date.getTime())) return null;
    return date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
};

/** Короткая дата и время без года: «28.07, 08:00» — для плотных таблиц. */
export const formatDateTimeShort = (dateString) => {
    if (!dateString) return '—';
    const date = new Date(String(dateString).replace(' ', 'T'));
    if (isNaN(date.getTime())) return '—';
    return date.toLocaleString('ru-RU', {
        day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
    });
};
