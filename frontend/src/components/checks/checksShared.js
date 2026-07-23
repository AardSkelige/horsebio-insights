// Общие утилиты и токены страницы /checks
import api from '../../utils/api';

// Палитра severity — три различимых уровня + ok/info
export const SEV = {
    critical:  { color: '#c64545', bg: 'rgba(198,69,69,0.10)',  label: 'Критичные' },
    important: { color: '#c47d2f', bg: 'rgba(196,125,47,0.10)', label: 'Важные' },
    warning:   { color: '#b08a1f', bg: 'rgba(176,138,31,0.10)', label: 'Предупреждения' },
    info:      { color: 'var(--muted)', bg: 'rgba(0,0,0,0.04)', label: 'Инфо' },
    ok:        { color: 'var(--success)', bg: 'rgba(93,184,114,0.10)', label: 'Норма' },
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
    enters:       '#5c8acc',
    enter_zero:   '#c64545',
    losses:       '#b08a1f',
    inventories:  '#7a6bd0',
    moves:        '#3fa3a3',
    supplies:     '#c47d2f',
    salesreturns: '#cc6f9c',
    deviations:   '#5db872',
    supply_jumps: '#9a8c7a',
};

// Русское склонение: plural(3, 'возврат', 'возврата', 'возвратов') → 'возврата'
export function plural(n, one, few, many) {
    const m10 = Math.abs(n) % 10, m100 = Math.abs(n) % 100;
    if (m10 === 1 && m100 !== 11) return one;
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
    return many;
}

export function fmtRub(v) {
    return `${Math.round(v || 0).toLocaleString('ru-RU')} ₽`;
}

export const PENDING_RETURNS_HINT =
    'Когда маркетплейс ставит заказу статус «возврат», робот сам создаёт черновик документа — '
    + 'так видно, что товар должен вернуться и сколько денег в нём зависло. Когда товар физически приходит '
    + 'на склад, документ проводят — и возврат отсюда исчезает. Если возврат висит дольше месяца, товар, '
    + 'похоже, застрял — надо смотреть в кабинете маркетплейса, где он.';

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
