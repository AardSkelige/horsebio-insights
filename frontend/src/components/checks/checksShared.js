// Общие утилиты и токены страницы /checks
import api from '../../utils/api';
import { money, plural } from '../../utils/formatters';

// Переэкспорт: проверки исторически берут форматирование отсюда
export { plural };
export const fmtRub = money;

// Палитра severity — три различимых уровня + ok/info
export const SEV = {
    critical:  { color: 'var(--error-ink)',      bg: 'var(--error-bg)',      label: 'Критичные' },
    important: { color: 'var(--cat-orange-ink)', bg: 'var(--cat-orange-bg)', label: 'Важные' },
    warning:   { color: 'var(--warning-ink)',    bg: 'var(--warning-bg)',    label: 'Предупреждения' },
    info:      { color: 'var(--muted)',          bg: 'var(--surface-soft)',  label: 'Инфо' },
    ok:        { color: 'var(--success-ink)',    bg: 'var(--success-bg)',    label: 'Норма' },
};

export const SEV_RANK = { critical: 3, important: 2, warning: 1, info: 0, ok: 0 };

export function sevOf(s) {
    return SEV[s] || SEV.info;
}

// Ссылка в UI МойСклад на документ/товар
export function msLink(msType, msId) {
    if (!msType || !msId) return null;
    return `https://online.moysklad.ru/app/#${msType}/edit?id=${msId}`;
}

// Тип исключения → тип документа МойСклад (для ссылок). null = не документ.
export const KIND_MS_TYPE = {
    enters: 'enter',
    losses: 'loss',
    inventories: 'inventory',
    moves: 'move',
    supplies: 'supply',
    salesreturns: 'salesreturn',
    enter_zero: 'enter',
    deviations: null,    // товар по коду — без doc-ссылки
    supply_jumps: null,  // позиция по имени
};

// Цвет бейджа категории исключения (приглушённая палитра)
export const KIND_BADGE = {
    enters:       'var(--cat-blue)',
    enter_zero:   'var(--error)',
    losses:       'var(--cat-amber)',
    inventories:  'var(--cat-violet)',
    moves:        'var(--cat-teal)',
    supplies:     'var(--cat-orange)',
    salesreturns: 'var(--cat-pink)',
    deviations:   'var(--cat-green)',
    supply_jumps: 'var(--cat-clay)',
};


export const PENDING_RETURNS_ID = 'horsebio_pending_returns';

export const PENDING_RETURNS_HINT =
    'Когда маркетплейс объявляет возврат, робот сам создаёт черновик документа — так видно, что товар '
    + 'должен вернуться и сколько денег в нём зависло. Когда товар физически приходит на склад, документ '
    + 'проводят — и возврат отсюда исчезает. У возвратов Озона робот знает, где коробка, и ставит статус: '
    + '«Уже у нас» значит доставили, надо разобрать и провести; «завис в пути» — товар больше месяца в '
    + 'дороге, пора смотреть в кабинете маркетплейса. У ВБ маршрут из API не достать — судим по возрасту.';

// «сегодня 14:05» / «вчера 09:00» / «23.06 09:00»
export function relTime(ts) {
    if (!ts) return '—';
    const d = new Date(ts.replace(' ', 'T'));
    if (Number.isNaN(d.getTime())) return ts;
    const today = new Date();
    const yest = new Date(today); yest.setDate(today.getDate() - 1);
    const hm = d.toTimeString().slice(0, 5);
    if (d.toDateString() === today.toDateString()) return `сегодня ${hm}`;
    if (d.toDateString() === yest.toDateString()) return `вчера ${hm}`;
    const dd = String(d.getDate()).padStart(2, '0');
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    return `${dd}.${mm} ${hm}`;
}

export function fmtDuration(sec) {
    if (sec == null) return '';
    const s = Math.round(sec);
    if (s < 60) return `${s}с`;
    const m = Math.floor(s / 60);
    return `${m}м ${s % 60}с`;
}

// ─── API ──────────────────────────────────────────────────────────────────────
export const checksApi = {
    overview: () => api.get('/checks/scripts/'),
    runs: (id) => api.get(`/checks/scripts/${id}/runs/`),
    results: (id, runId) => api.get(`/checks/scripts/${id}/results/`, { params: runId ? { run_id: runId } : {} }),
    log: (id, runId) => api.get(`/checks/scripts/${id}/log/`, { params: runId ? { run_id: runId } : {} }),
    run: (id) => api.post(`/checks/scripts/${id}/run/`),
    stop: (id) => api.post(`/checks/scripts/${id}/stop/`),
    removeRun: (id, runId) => api.delete(`/checks/scripts/${id}/runs/${runId}/`),
    listExceptions: (kind) => api.get('/checks/exceptions/', { params: kind ? { kind } : {} }),
    addException: (payload) => api.post('/checks/exceptions/', payload),
    updateException: (id, payload) => api.patch(`/checks/exceptions/${id}/`, payload),
    removeException: (id) => api.delete(`/checks/exceptions/${id}/`),
    // Универсальное удаление находки — url приходит с бэкенда в item.delete_action.url
    // (например /site-orders/{id}/), разные роботы подставляют свой эндпоинт
    deleteRecord: (url) => api.delete(url),
};
