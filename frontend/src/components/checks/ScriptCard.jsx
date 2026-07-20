import PropTypes from 'prop-types';
import {
    Loader2, CheckCircle, AlertCircle, Circle, ChevronRight, Clock,
    Activity, Banknote, PackagePlus, CalendarClock, Mail, ShoppingCart,
} from 'lucide-react';
import { SEV, relTime, plural } from './checksShared';
import InfoTip from './InfoTip';
import './ScriptCard.css';

// Что проверяем / как проверяем / подробности в «?» — по каждому скрипту.
// Экспортируется: шапка деталки (CheckDetail) показывает те же тексты, что и список.
export const SCRIPT_META = {
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
    horsebio_order_email_sync: {
        Icon: Mail,
        what: 'Заказы с сайта не теряются, попадают в очередь на заведение в МойСклад',
        how: 'Каждые 5 минут проверяет почту info@horse-bio.ru и распознаёт заказы в письмах-уведомлениях',
        hint: 'Сайт присылает на info@horse-bio.ru письмо на каждый заказ (и на смену его статуса — '
            + 'например, при оплате). Робот читает эти письма и запоминает данные заказа — сами письма '
            + 'не трогает и не помечает прочитанными, можно спокойно перечитать историю заново. '
            + '«Другие письма» — это письма от того же адреса, но не про заказ (например, уведомление '
            + 'о модерации комментария на сайте) — это нормально, не ошибка.',
    },
    horsebio_order_email_create: {
        Icon: ShoppingCart,
        what: 'Заказ с сайта заведён в МойСклад, а оплата отражена без задержки',
        how: 'Черновик — сразу после письма о заказе; платёж и проведение — после письма об оплате',
        hint: 'Если заказ не оплачен 24 часа, черновик автоматически удаляется из МойСклад — считаем, '
            + 'что клиент передумал (если он всё же оплатит позже, заказ заведётся заново). Если сотрудник '
            + 'уже сам принял оплату или поправил комментарий в МойСклад вручную — робот это не перезаписывает.',
    },
};

/** Единый статус-бейдж: точка/иконка + короткий фиксированный текст.
 *  Один и тот же формат для всех строк страницы Проверки — разбор по пунктам
 *  и цифры смотрим в деталке по клику, а не в списке. */
export function StatusBadge({ color, icon: Icon, spin, children }) {
    return (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color, fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap' }}>
            {Icon
                ? <Icon size={14} className={spin ? 'animate-spin' : undefined} />
                : <span style={{ width: 7, height: 7, borderRadius: 999, background: color }} />}
            {children}
        </span>
    );
}
StatusBadge.propTypes = {
    color: PropTypes.string.isRequired,
    icon: PropTypes.elementType,
    spin: PropTypes.bool,
    children: PropTypes.node,
};

/** Правая часть строки: только ок/не ок — без разнородных цифр и текстов разной длины. */
function StatusLine({ script }) {
    if (script.is_running) {
        return <StatusBadge color="var(--primary)" icon={Loader2} spin>Выполняется…</StatusBadge>;
    }
    const s = script.summary;
    if (script.structured && s) {
        const total = (s.critical || 0) + (s.important || 0) + (s.warnings || 0);
        if (total > 0) {
            const sev = s.critical ? 'critical' : s.important ? 'important' : 'warning';
            return (
                <StatusBadge color={SEV[sev].color} icon={AlertCircle}>
                    {total} {plural(total, 'проблема', 'проблемы', 'проблем')}
                </StatusBadge>
            );
        }
        return <StatusBadge color="var(--success)" icon={CheckCircle}>ОК</StatusBadge>;
    }
    const code = script.last_run?.exit_code;
    if (code == null) {
        return <StatusBadge color="var(--muted-soft)" icon={Circle}>Не запускался</StatusBadge>;
    }
    if (code === 0) {
        return <StatusBadge color="var(--success)" icon={CheckCircle}>ОК</StatusBadge>;
    }
    return <StatusBadge color="var(--error)" icon={AlertCircle}>Ошибка</StatusBadge>;
}
StatusLine.propTypes = { script: PropTypes.object.isRequired };

export function AccountBadge({ account }) {
    return (
        <span style={{
            fontFamily: 'var(--sans)', fontSize: 10.5, fontWeight: 700, letterSpacing: '0.04em', color: 'var(--muted)',
            padding: '1px 7px', borderRadius: 6, background: 'var(--surface-soft)',
            textTransform: 'uppercase', whiteSpace: 'nowrap', flexShrink: 0,
        }}>{account}</span>
    );
}
AccountBadge.propTypes = { account: PropTypes.string.isRequired };

/** Строка скрипта: иконка, название, бейдж аккаунта, «?», ниже — что и как проверяем,
 *  справа — содержательные цифры и время. Единый формат для всех строк страницы. */
export default function ScriptCard({ script, onOpen }) {
    const meta = SCRIPT_META[script.id] || {};
    const Icon = meta.Icon || Activity;
    return (
        <div
            role="button"
            tabIndex={0}
            onClick={() => onOpen(script.id)}
            onKeyDown={(e) => { if (e.key === 'Enter') onOpen(script.id); }}
            className="group checks-script-card"
            style={{
                width: '100%', textAlign: 'left',
                background: 'var(--surface-card)', border: '1px solid var(--hairline)',
                borderRadius: 12, padding: '13px 16px', cursor: 'pointer',
                transition: 'background 0.15s, border-color 0.15s',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--surface-cream-strong)'; e.currentTarget.style.borderColor = 'var(--primary)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--surface-card)'; e.currentTarget.style.borderColor = 'var(--hairline)'; }}
        >
            <div className="checks-script-card__row">
                <div className="checks-script-card__content">
                    <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 14.5, fontWeight: 600, color: 'var(--ink)', lineHeight: 1.3 }}>
                        <Icon size={16} style={{ color: 'var(--muted)', flexShrink: 0 }} />
                        {script.name}
                        <AccountBadge account={script.account} />
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
                <div className="checks-script-card__meta">
                    <div className="checks-script-card__status">
                        <StatusLine script={script} />
                    </div>
                    <span
                        className="checks-script-card__timing"
                        aria-label={script.last_run ? 'Последний запуск' : 'Расписание'}
                    >
                        <Clock size={13} />
                        {script.last_run ? relTime(script.last_run.finished_at) : script.schedule}
                    </span>
                </div>
                <ChevronRight className="checks-script-card__arrow" size={17} />
            </div>
        </div>
    );
}

ScriptCard.propTypes = {
    script: PropTypes.object.isRequired,
    onOpen: PropTypes.func.isRequired,
};
