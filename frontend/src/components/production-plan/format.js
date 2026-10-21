const MONTHS = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'];
const MONTHS_IN = ['январе', 'феврале', 'марте', 'апреле', 'мае', 'июне', 'июле', 'августе', 'сентябре', 'октябре', 'ноябре', 'декабре'];

const MONTHS_FROM = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];

const index = (iso) => Number(String(iso).slice(5, 7)) - 1;

export const monthName = (iso) => MONTHS[index(iso)];
export const monthIn = (iso) => MONTHS_IN[index(iso)];
export const monthShort = (iso) => monthName(iso).slice(0, 3);

export const wbSource = (months = [], wbMonths = []) => {
    if (months.length && wbMonths.length === months.length) return 'WB — тоже все продажи, по данным WB.';
    if (wbMonths.length) return `WB по данным WB с ${MONTHS_FROM[index(wbMonths[0])]}, раньше — то, что мы им отгрузили.`;
    return 'WB — то, что мы им отгрузили.';
};

export const qty = (value) => (value ? new Intl.NumberFormat('ru-RU').format(Math.round(value)) : '—');

export const STATUS = {
    urgent: { label: 'Срочно', tone: 'error' },
    produce: { label: 'К производству', tone: 'warning' },
    in_production: { label: 'В производстве', tone: 'info' },
    enough: { label: 'Хватает', tone: 'success' },
};

export const FILTERS = [
    { value: 'todo', label: 'Произвести', test: (row) => row.produce > 0 },
    { value: 'urgent', label: 'Срочно', test: (row) => row.status === 'urgent' },
    { value: 'green', label: 'Зелёный список', test: (row) => row.green },
    { value: 'all', label: 'Все', test: () => true },
];
