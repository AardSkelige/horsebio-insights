import PropTypes from 'prop-types';
import {
    Loader2, CheckCircle, AlertCircle, Circle, ChevronRight, Clock,
    Activity, Banknote, PackagePlus, CalendarClock,
} from 'lucide-react';
import { SEV, sevOf, relTime, plural } from './checksShared';
import InfoTip from './InfoTip';

// Что проверяем / как проверяем / подробности в «?» — по каждому скрипту
const SCRIPT_META = {
    horsebio_health_check: {
        Icon: Activity,
        what: 'Себестоимость посчитана верно, в документах МойСклад порядок',
        how: '13 проверок за один запуск — от сравнения FIFO с приёмками до кодов товаров',
        hint: 'Список проверок: отклонения FIFO vs приёмка · отрицательные остатки · оприходования '
            + '(внутренние склады, цена не по приёмке, нулевые цены) · списания · инвентаризации · '
            + 'перемещения · приёмки · возвраты с нулевой себестоимостью · скачки цен в приёмках · '
            + 'коды товаров · незавершённые черновики. Внутри — сетка со статусом каждой проверки.',
    },
    horsebio_buy_prices: {
        Icon: Banknote,
        what: 'Закупочная цена (buyPrice) каждого товара соответствует реальной FIFO-себестоимости',
        how: 'Робот сверяет цены и обновляет разошедшиеся',
        hint: 'buyPrice используется отчётами о прибыли. Если приёмки изменили FIFO-себестоимость, '
            + 'робот подтянет закупочную цену — прибыль в отчётах останется честной.',
    },
    horsebio_returns: {
        Icon: PackagePlus,
        what: 'Каждый возврат ВБ/Озон оформлен документом в МойСклад',
        how: 'Робот следит за статусами заказов и сам создаёт черновики возвратов',
        hint: 'Когда интеграция маркетплейса ставит заказу статус «возврат», робот находит отгрузку '
            + 'и создаёт черновик возврата. Так видно, какой товар должен вернуться и сколько денег в нём. '
            + 'Черновик проводят, когда товар физически приходит на склад.',
    },
    horsebio_deadlines: {
        Icon: CalendarClock,
        what: 'Счета поставщикам оплачены вовремя',
        how: 'Сверяем сроки оплат: предупреждаем о просроченных и скоро истекающих',
        hint: 'Критичные — уже просроченные оплаты, важные — истекают в ближайшие дни.',
    },
    starpony_cost_prices: {
        Icon: Banknote,
        what: 'Тип цены «Себестоимость» соответствует FIFO',
        how: 'Робот копирует FIFO-себестоимость в тип цены у товаров с остатками',
        hint: 'StarPony использует тип цены «Себестоимость» в отчётах — робот держит его актуальным.',
    },
};

// Подписи severity с русским склонением
const SEV_WORDS = {
    critical:  ['критичная', 'критичные', 'критичных'],
    important: ['важная', 'важные', 'важных'],
    warning:   ['предупреждение', 'предупреждения', 'предупреждений'],
};

function SeverityChip({ sev, count }) {
    const c = SEV[sev];
    const w = SEV_WORDS[sev];
    return (
        <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 5,
            padding: '2px 9px', borderRadius: 999, fontSize: 12, fontWeight: 600,
            color: c.color, background: c.bg, whiteSpace: 'nowrap',
        }}>
            <span style={{ width: 7, height: 7, borderRadius: 999, background: c.color }} />
            {count} {w ? plural(count, ...w) : ''}
        </span>
    );
}
SeverityChip.propTypes = { sev: PropTypes.string, count: PropTypes.number };

/** Правая часть строки: полезные цифры вместо голого «ОК».
 *  Проверки — severity-чипы; роботы — ненулевые счётчики последнего запуска. */
function StatusLine({ script }) {
    if (script.is_running) {
        return (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--primary)', fontSize: 13, fontWeight: 600 }}>
                <Loader2 size={14} className="animate-spin" /> Выполняется…
            </span>
        );
    }
    const s = script.summary;
    if (script.structured && s) {
        const total = (s.critical || 0) + (s.important || 0) + (s.warnings || 0);
        if (total > 0) {
            return (
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                    {s.critical ? <SeverityChip sev="critical" count={s.critical} /> : null}
                    {s.important ? <SeverityChip sev="important" count={s.important} /> : null}
                    {s.warnings ? <SeverityChip sev="warning" count={s.warnings} /> : null}
                </div>
            );
        }
        // Роботы: показать содержательные счётчики («Уже актуальны: 488»)
        const stats = (Array.isArray(s.stats) ? s.stats : [])
            .filter((st) => st.value > 0 && st.label !== 'Ошибки').slice(0, 2);
        if (stats.length > 0) {
            return (
                <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--success)', whiteSpace: 'nowrap' }}>
                    ✓ {stats.map((st) => `${st.label.toLowerCase()}: ${st.value}`).join(' · ')}
                </span>
            );
        }
        return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--success)', fontSize: 13, fontWeight: 600 }}><CheckCircle size={14} /> Всё чисто</span>;
    }
    const code = script.last_run?.exit_code;
    if (code == null) {
        return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--muted-soft)', fontSize: 13 }}><Circle size={13} /> Не запускался</span>;
    }
    if (code === 0) {
        return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--success)', fontSize: 13, fontWeight: 600 }}><CheckCircle size={14} /> ОК</span>;
    }
    return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--error)', fontSize: 13, fontWeight: 600 }}><AlertCircle size={14} /> Ошибка</span>;
}
StatusLine.propTypes = { script: PropTypes.object.isRequired };

/** Мини-сводка внутренних проверок хелс-чека: проблемные поимённо, чистые одним счётчиком. */
function HealthChecksStrip({ checks }) {
    const problems = checks.filter((c) => c.status === 'problems');
    const clean = checks.filter((c) => c.status === 'ok').length;
    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginTop: 9 }}>
            {problems.map((c) => {
                const s = sevOf(c.severity);
                return (
                    <span key={c.id} style={{
                        display: 'inline-flex', alignItems: 'center', gap: 5, padding: '2px 9px',
                        borderRadius: 999, fontSize: 12, fontWeight: 600, color: s.color, background: s.bg,
                    }}>
                        <span style={{ width: 6, height: 6, borderRadius: 999, background: s.color }} />
                        {c.title} · {c.count}
                    </span>
                );
            })}
            {clean > 0 && (
                <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--success)' }}>
                    ✓ {problems.length ? 'остальные ' : ''}{clean} {plural(clean, 'проверка чистая', 'проверки чистые', 'проверок чистые')}
                </span>
            )}
        </div>
    );
}
HealthChecksStrip.propTypes = { checks: PropTypes.array.isRequired };

export function accountBadge(account) {
    return (
        <span style={{
            fontSize: 10.5, fontWeight: 700, letterSpacing: '0.04em', color: 'var(--muted)',
            padding: '1px 7px', borderRadius: 6, background: 'var(--surface-soft)',
            textTransform: 'uppercase', whiteSpace: 'nowrap', flexShrink: 0,
        }}>{account}</span>
    );
}

/** Строка скрипта: иконка, название, бейдж аккаунта, «?», ниже — что и как проверяем,
 *  справа — содержательные цифры и время. Единый формат для всех строк страницы. */
export default function ScriptCard({ script, onOpen }) {
    const meta = SCRIPT_META[script.id] || {};
    const Icon = meta.Icon || Activity;
    const healthChecks = script.is_health && Array.isArray(script.summary?.checks)
        ? script.summary.checks : null;
    return (
        <div
            role="button"
            tabIndex={0}
            onClick={() => onOpen(script.id)}
            onKeyDown={(e) => { if (e.key === 'Enter') onOpen(script.id); }}
            className="group"
            style={{
                width: '100%', textAlign: 'left',
                background: 'var(--surface-card)', border: '1px solid var(--hairline)',
                borderRadius: 12, padding: '13px 16px', cursor: 'pointer',
                transition: 'background 0.15s, border-color 0.15s',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--surface-cream-strong)'; e.currentTarget.style.borderColor = 'var(--primary)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--surface-card)'; e.currentTarget.style.borderColor = 'var(--hairline)'; }}
        >
            <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 14.5, fontWeight: 600, color: 'var(--ink)', lineHeight: 1.3 }}>
                        <Icon size={16} style={{ color: 'var(--muted)', flexShrink: 0 }} />
                        {script.name}
                        {accountBadge(script.account)}
                        {meta.hint && <InfoTip text={meta.hint} width={310} />}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 3, lineHeight: 1.45 }}>
                        {meta.what ? (
                            <>
                                <div><b style={{ color: 'var(--body)', fontWeight: 600 }}>Что проверяем:</b> {meta.what}</div>
                                <div><b style={{ color: 'var(--body)', fontWeight: 600 }}>Как:</b> {meta.how}</div>
                            </>
                        ) : script.description}
                    </div>
                </div>
                <StatusLine script={script} />
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--muted-soft)', whiteSpace: 'nowrap', flexShrink: 0 }}>
                    <Clock size={12} />
                    {script.last_run ? relTime(script.last_run.finished_at) : script.schedule}
                </span>
                <ChevronRight size={17} style={{ color: 'var(--muted-soft)', flexShrink: 0 }} />
            </div>
            {healthChecks && <HealthChecksStrip checks={healthChecks} />}
        </div>
    );
}

ScriptCard.propTypes = {
    script: PropTypes.object.isRequired,
    onOpen: PropTypes.func.isRequired,
};
