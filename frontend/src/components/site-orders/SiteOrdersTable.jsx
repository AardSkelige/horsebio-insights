import PropTypes from 'prop-types';
import { Globe, Package, Trash2, Loader2 } from 'lucide-react';
import { SkeletonRows } from '../ui/Skeleton';
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
            <a
                className={`icon-btn${row.site_link ? '' : ' disabled'}`}
                href={row.site_link || undefined}
                target="_blank" rel="noopener noreferrer"
                title="Открыть заказ на сайте"
            >
                <Globe size={13} />
            </a>
            <a
                className={`icon-btn${row.ms_link ? '' : ' disabled'}`}
                href={row.ms_link || undefined}
                target="_blank" rel="noopener noreferrer"
                title={row.ms_link ? 'Открыть в МойСклад' : 'Черновик ещё не создан'}
            >
                <Package size={13} />
            </a>
            {canDelete && (
                <button
                    type="button"
                    className="icon-btn danger"
                    onClick={handleDelete}
                    disabled={deleting}
                    title="Убрать запись из журнала"
                >
                    {deleting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
                </button>
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
                <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--ink)', whiteSpace: 'nowrap' }}>{formatRub(row.sum)}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 8, gap: 8, flexWrap: 'wrap' }}>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 11.5, color: 'var(--muted)' }}>№{row.number} · {row.date_label}</span>
                <StatusChip row={row} />
            </div>
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
                    <col style={{ width: '24%' }} />
                    <col style={{ width: '9%' }} />
                    <col style={{ width: '13%' }} />
                    <col style={{ width: '11%' }} />
                    <col style={{ width: '33%' }} />
                    <col style={{ width: '10%' }} />
                </colgroup>
                <thead>
                    <tr>
                        <SortHeader label="Покупатель" sortKey="name" sort={sort} onSortChange={onSortChange} />
                        <th>Заказ</th>
                        <SortHeader label="Дата" sortKey="date" sort={sort} onSortChange={onSortChange} />
                        <SortHeader label="Сумма" sortKey="sum" sort={sort} onSortChange={onSortChange} align="right" />
                        <SortHeader label="Статус" sortKey="status" sort={sort} onSortChange={onSortChange} />
                        <th />
                    </tr>
                </thead>
                <tbody>
                    {loading ? (
                        <SkeletonRows cols={6} rows={5} />
                    ) : rows.map(row => (
                        <tr key={row.order_id} className={ROW_CLASS[row.status] || ''}>
                            <td>
                                {row.name}
                                <span className="contact">{row.phone}</span>
                            </td>
                            <td className="mono">№{row.number}</td>
                            <td className="mono" style={{ fontSize: 12, color: 'var(--muted-soft)' }}>{row.date_label}</td>
                            <td className="num-cell">{formatRub(row.sum)}</td>
                            <td><StatusChip row={row} /></td>
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
