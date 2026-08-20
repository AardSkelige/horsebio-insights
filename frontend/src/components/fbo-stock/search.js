/**
 * Поиск по остаткам — как в МойСклад: запрос дробится на части, и позиция
 * подходит, если найдены все части в любом порядке. Так «хондрофит 500»
 * находит «Хондропротектор Хондрофит ArtroPro …, 500 мл», а «псил 150» —
 * «Псиллиум GastroPro для собак и кошек, 150 г».
 */

const normalize = (value) => String(value || '').toLowerCase().replace(/ё/g, 'е');

/** Строка, по которой ищем: название, артикул, код и артикул без дефисов —
 *  чтобы «0802EP0800» находило товар с артикулом «08-02EP0800». */
export const searchIndex = (item) => normalize([
    item.name,
    item.article,
    item.code,
    String(item.article || '').replace(/-/g, ''),
].join(' '));

export const parseQuery = (query) => normalize(query).split(/\s+/).filter(Boolean);

export const matchesQuery = (haystack, parts) => parts.every((part) => haystack.includes(part));
