import PropTypes from 'prop-types';
import { SkeletonRows } from '../ui';
import { useState } from 'react';
import { Globe, Package, Trash2, Loader2, Truck, XCircle } from 'lucide-react';
import { siteOrdersApi } from '../../api/siteOrdersApi';
import { useConfirmDelete } from '../../hooks/useConfirmDelete';
import './SiteOrdersTable.css';

const STATUS_CLASS = {
    error: 'err',
    cancelled: 'cancelled',
    paid: 'ok',
    waiting_payment: 'warn',
    processing: 'processing',
};

const ROW_CLASS = {
    error: 'err-row',
    cancelled: 'cancelled-row',
};

function formatRub(value) {
    return (value || 0).toLocaleString('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 });
}

// Скидка приходит отдельным полем: сайт в письме шлёт цены по прайсу, а итог
// уже со скидкой, поэтому в «Сумме» её не видно — показываем второй строкой.
// В подсказке — название купона, если сайт его прислал.
function DiscountNote({ row }) {
    if (!row.discount) return null;
    return (
        <span className="discount-note" title={row.discount_label || undefined}>
            −{formatRub(row.discount)}
        </span>
    );
}
DiscountNote.propTypes = { row: PropTypes.object.isRequired };

const POSTING_LABELS = {
    awaiting_packaging: 'Ожидает сборки',
    awaiting_deliver: 'Ожидает отгрузки',
    delivering: 'В пути',
    delivered: 'Доставлено',
    cancelled: 'Отменено',
    not_accepted: 'Не принято',
};

function OzonChip({ ozon }) {
    if (!ozon) return null;

    // Статусов у Ozon больше, чем в словаре. Незнакомый показываем как есть:
    // подставить сюда подпись расчёта значит выдать состояние заказа за
    // состояние посылки — «Заказ создан» вместо «в арбитраже».
    const label = POSTING_LABELS[ozon.posting_status] || ozon.posting_status || ozon.status_label;
    const tone = ozon.needs_attention || ozon.status === 'unknown' || ozon.status === 'failed'
        ? 'err'
        : ozon.posting_status === 'delivered' ? 'ok' : 'processing';

    return (
        <div className="status-wrap" tabIndex={0}>
            <span className={`chip ${tone}`}>
                <Truck size={11} style={{ marginRight: 4 }} />
                Ozon: {label}
            </span>
            <div className="tip">
                {ozon.order_number && (
                    <div className="step-line"><span className="m">Заказ</span><span>{ozon.order_number}</span></div>
                )}
                {ozon.posting_number && (
                    <div className="step-line"><span className="m">Отправление</span><span>{ozon.posting_number}</span></div>
                )}
                {ozon.delivery_cost > 0 && (
                    <div className="step-line"><span className="m">Логистика</span><span>{formatRub(ozon.delivery_cost)}</span></div>
                )}
                {ozon.error && (
                    <div className="step-line"><span className="m">Ошибка</span><span>{ozon.error}</span></div>
                )}
            </div>
        </div>
    );
}
OzonChip.propTypes = { ozon: PropTypes.object };

function CancelOzonButton({ row, onDone }) {
    const [busy, setBusy] = useState(false);

    if (!row.ozon?.cancellable) return null;

    const handleCancel = async () => {
        const confirmed = window.confirm(
            `Отменить доставку Ozon по заказу №${row.number}?\n\n` +
            'Посылка не поедет. Деньги покупателю верните кнопкой «Полный возврат» ' +
            'в админке сайта — после того, как Ozon подтвердит отмену.'
        );
        if (!confirmed) return;

        setBusy(true);
        try {
            const { data } = await siteOrdersApi.cancelOzon(row.order_id);
            window.alert(data?.message || 'Отмена принята Ozon');
            onDone?.();
        } catch (e) {
            window.alert(e?.response?.data?.message || 'Не удалось отменить доставку');
        } finally {
            setBusy(false);
        }
    };

    return (
        <span className="act-wrap" tabIndex={0}>
            <button type="button" className="icon-btn danger" onClick={handleCancel} disabled={busy}>
                {busy ? <Loader2 size={15} className="animate-spin" /> : <XCircle size={15} />}
            </button>
            <span className="tip act-tip">Отменить доставку Ozon</span>
        </span>
    );
}
CancelOzonButton.propTypes = { row: PropTypes.object.isRequired, onDone: PropTypes.func };

function StatusChip({ row }) {
    const cls = STATUS_CLASS[row.status] || 'processing';
    return (
        <div className="status-wrap" tabIndex={0}>
            <span className={`chip ${cls}`}><span className="cdot" />{row.status_label}</span>
            {row.timeline?.length > 0 && (
                <div className="tip">
                    {row.timeline.map((ev, i) => (
                        <div className="step-line" key={i}>
                            <span className="m">{ev.time}</span>
                            <span>{ev.text}</span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
StatusChip.propTypes = { row: PropTypes.object.isRequired };

function RowActions({ row, onDeleted, canDelete }) {
    const label = `${row.name || 'заказ'}${row.number ? ` — №${row.number}` : ''}`;
    const { deleting, trigger: handleDelete } = useConfirmDelete({
        confirm: `Удалить «${label}» из журнала автоматизации? Само письмо и документы в МойСклад ` +
            `(если уже созданы) не тронутся — сотрётся только запись в нашем внутреннем учёте, ` +
            `и при следующей проверке почты письмо может быть разобрано заново.`,
        run: () => siteOrdersApi.remove(row.order_id),
        onDone: onDeleted,
    });

    return (
        <span className="actions-cell">
            <span className="act-wrap" tabIndex={0}>
                <a
                    className={`icon-btn${row.site_link ? '' : ' disabled'}`}
                    href={row.site_link || undefined}
                    target="_blank" rel="noopener noreferrer"
                >
                    <Globe size={15} />
                </a>
                <span className="tip act-tip">Открыть заказ на сайте</span>
            </span>
            <span className="act-wrap" tabIndex={0}>
                <a
                    className={`icon-btn${row.ms_link ? '' : ' disabled'}`}
                    href={row.ms_link || undefined}
                    target="_blank" rel="noopener noreferrer"
                >
                    <Package size={15} />
                </a>
                <span className="tip act-tip">{row.ms_link ? 'Открыть в МойСклад' : 'Черновик ещё не создан'}</span>
            </span>
            <CancelOzonButton row={row} onDone={onDeleted} />
            {canDelete && (
                <span className="act-wrap" tabIndex={0}>
                    <button
                        type="button"
                        className="icon-btn danger"
                        onClick={handleDelete}
                        disabled={deleting}
                    >
                        {deleting ? <Loader2 size={15} className="animate-spin" /> : <Trash2 size={15} />}
                    </button>
                    <span className="tip act-tip">Убрать запись из журнала</span>
                </span>
            )}
        </span>
    );
}
RowActions.propTypes = { row: PropTypes.object.isRequired, onDeleted: PropTypes.func, canDelete: PropTypes.bool };

function SortHeader({ label, sortKey, sort, onSortChange, align }) {
    const active = sort.key === sortKey;
    return (
        <th
            className={`sortable${active ? ` sort-${sort.dir}` : ''}`}
            style={align ? { textAlign: align } : undefined}
            tabIndex={0}
            onClick={() => onSortChange(sortKey)}
            onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSortChange(sortKey); } }}
        >
            {label}<span className="sort-arrow" />
        </th>
    );
}
SortHeader.propTypes = {
    label: PropTypes.string.isRequired,
    sortKey: PropTypes.string.isRequired,
    sort: PropTypes.shape({ key: PropTypes.string, dir: PropTypes.string }).isRequired,
    onSortChange: PropTypes.func.isRequired,
    align: PropTypes.string,
};

function OrderCard({ row, onDeleted, canDelete }) {
    return (
        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--hairline)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                <div>
                    <div style={{ fontFamily: 'var(--sans)', fontSize: 13.5, fontWeight: 600, color: 'var(--ink)' }}>{row.name}</div>
                    <div style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--muted)' }}>{row.phone}</div>
                </div>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--ink)', whiteSpace: 'nowrap', textAlign: 'right' }}>
                    {formatRub(row.sum)}
                    <DiscountNote row={row} />
                </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 8, gap: 8, flexWrap: 'wrap' }}>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 11.5, color: 'var(--muted)' }}>№{row.number} · {row.date_label}</span>
                <StatusChip row={row} />
            </div>
            {row.ozon && <div style={{ marginTop: 6 }}><OzonChip ozon={row.ozon} /></div>}
            <div style={{ marginTop: 8 }}><RowActions row={row} onDeleted={onDeleted} canDelete={canDelete} /></div>
        </div>
    );
}
OrderCard.propTypes = { row: PropTypes.object.isRequired, onDeleted: PropTypes.func, canDelete: PropTypes.bool };

export default function SiteOrdersTable({ rows, loading, sort, onSortChange, onDeleted, canDelete, isMobile }) {
    if (isMobile) {
        if (loading) return <div style={{ padding: 16, color: 'var(--muted)', fontSize: 13 }}>Загрузка…</div>;
        return (
            <div style={{ border: '1px solid var(--hairline)', borderRadius: 10, overflow: 'hidden' }}>
                {rows.map(row => <OrderCard key={row.order_id} row={row} onDeleted={onDeleted} canDelete={canDelete} />)}
            </div>
        );
    }

    return (
        <div style={{ border: '1px solid var(--hairline)', borderRadius: 10 }}>
            <table className="site-orders-table">
                <colgroup>
                    <col style={{ width: '22%' }} />
                    <col style={{ width: '8%' }} />
                    <col style={{ width: '12%' }} />
                    <col style={{ width: '10%' }} />
                    <col style={{ width: '20%' }} />
                    <col style={{ width: '18%' }} />
                    <col style={{ width: '10%' }} />
                </colgroup>
                <thead>
                    <tr>
                        <SortHeader label="Покупатель" sortKey="name" sort={sort} onSortChange={onSortChange} />
                        <th>Заказ</th>
                        <SortHeader label="Дата" sortKey="date" sort={sort} onSortChange={onSortChange} />
                        <SortHeader label="Сумма" sortKey="sum" sort={sort} onSortChange={onSortChange} align="right" />
                        <SortHeader label="Статус" sortKey="status" sort={sort} onSortChange={onSortChange} />
                        <th>Доставка</th>
                        <th />
                    </tr>
                </thead>
                <tbody>
                    {loading ? (
                        <SkeletonRows cols={7} rows={5} />
                    ) : rows.map(row => (
                        <tr key={row.order_id} className={ROW_CLASS[row.status] || ''}>
                            <td>
                                {row.name}
                                <span className="contact">{row.phone}</span>
                            </td>
                            <td className="mono">№{row.number}</td>
                            <td className="mono" style={{ fontSize: 12, color: 'var(--muted-soft)' }}>{row.date_label}</td>
                            <td className="num-cell">
                                {formatRub(row.sum)}
                                <DiscountNote row={row} />
                            </td>
                            <td><StatusChip row={row} /></td>
                            <td><OzonChip ozon={row.ozon} /></td>
                            <td><RowActions row={row} onDeleted={onDeleted} canDelete={canDelete} /></td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

SiteOrdersTable.propTypes = {
    rows: PropTypes.array.isRequired,
    loading: PropTypes.bool.isRequired,
    sort: PropTypes.shape({ key: PropTypes.string, dir: PropTypes.string }).isRequired,
    onSortChange: PropTypes.func.isRequired,
    onDeleted: PropTypes.func,
    canDelete: PropTypes.bool,
    isMobile: PropTypes.bool,
};
