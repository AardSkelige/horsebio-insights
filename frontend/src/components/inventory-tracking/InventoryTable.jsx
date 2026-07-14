import PropTypes from 'prop-types';

const COL_WIDTHS = {
    code: 80,
    article: 120,
    name: undefined,
    folder: 130,
    count: 90,
    lastDate: 150,
    daysSince: 100,
};

const headerCell = {
    fontFamily: 'var(--sans)',
    fontSize: 11,
    fontWeight: 500,
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
    color: 'var(--on-dark-soft)',
    padding: '10px 12px',
    textAlign: 'left',
    whiteSpace: 'nowrap',
};

const bodyCell = {
    fontFamily: 'var(--sans)',
    fontSize: 13,
    color: 'var(--on-dark)',
    padding: '10px 12px',
    borderTop: '1px solid rgba(255,255,255,0.06)',
};

function formatDate(isoStr) {
    if (!isoStr) return '—';
    const d = new Date(isoStr);
    return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function DaysBadge({ days }) {
    if (days === null || days === undefined) return <span style={{ color: 'var(--on-dark-soft)' }}>—</span>;
    const color = days <= 7 ? 'var(--success)' : days <= 30 ? 'var(--warning)' : 'var(--error)';
    return (
        <span style={{
            background: color + '22',
            color,
            padding: '2px 8px',
            borderRadius: 4,
            fontSize: 12,
            fontWeight: 500,
        }}>
            {days === 0 ? 'сегодня' : `${days} д.`}
        </span>
    );
}

DaysBadge.propTypes = { days: PropTypes.number };

export default function InventoryTable({ title, products, type, loading, isMobile }) {
    const isNotInventoried = type === 'not-inventoried';

    return (
        <div style={{ marginBottom: 32 }}>
            {/* Section header */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                <span style={{
                    fontFamily: 'var(--sans)',
                    fontSize: 11,
                    fontWeight: 600,
                    textTransform: 'uppercase',
                    letterSpacing: '0.08em',
                    color: isNotInventoried ? 'var(--error)' : 'var(--success)',
                }}>
                    {title}
                </span>
                <span style={{
                    background: isNotInventoried ? 'rgba(198,69,69,0.12)' : 'rgba(93,184,114,0.12)',
                    color: isNotInventoried ? 'var(--error)' : 'var(--success)',
                    borderRadius: 12,
                    padding: '1px 8px',
                    fontSize: 12,
                    fontWeight: 600,
                }}>
                    {products.length}
                </span>
            </div>

            <div style={{ background: 'var(--surface-dark)', borderRadius: 12, overflow: 'hidden' }}>
                {loading ? (
                    <div style={{
                        padding: 32, textAlign: 'center',
                        fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--on-dark-soft)',
                    }}>
                        Загрузка...
                    </div>
                ) : products.length === 0 ? (
                    <div style={{
                        padding: 32, textAlign: 'center',
                        fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--on-dark-soft)',
                    }}>
                        {isNotInventoried ? 'Все позиции были учтены — отлично!' : 'Нет данных'}
                    </div>
                ) : isMobile ? (
                    /* ── Mobile card list ── */
                    <div>
                        {products.map((p, i) => (
                            <div key={p.external_id || i} style={{
                                padding: '12px 16px',
                                borderTop: i > 0 ? '1px solid rgba(255,255,255,0.06)' : 'none',
                                background: isNotInventoried ? 'rgba(198,69,69,0.04)' : 'transparent',
                            }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8, marginBottom: 5 }}>
                                    <span style={{ fontSize: 13, color: 'var(--on-dark)', fontWeight: 500, flex: 1, minWidth: 0 }}>
                                        {p.name}
                                    </span>
                                    <DaysBadge days={p.days_since_last} />
                                </div>
                                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
                                    {p.code && (
                                        <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--on-dark-soft)' }}>
                                            #{p.code}
                                        </span>
                                    )}
                                    {p.article && (
                                        <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--on-dark-soft)' }}>
                                            {p.article}
                                        </span>
                                    )}
                                    {p.folder && (
                                        <span style={{ fontSize: 11, color: 'var(--on-dark-soft)' }}>
                                            {p.folder}
                                        </span>
                                    )}
                                    {!isNotInventoried && p.inventory_count !== undefined && (
                                        <span style={{ fontSize: 11, color: 'var(--on-dark-soft)' }}>
                                            {p.inventory_count} раз
                                        </span>
                                    )}
                                    {p.last_inventoried_at && (
                                        <span style={{ fontSize: 11, color: 'var(--on-dark-soft)' }}>
                                            {formatDate(p.last_inventoried_at)}
                                        </span>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                ) : (
                    /* ── Desktop table ── */
                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ background: 'rgba(255,255,255,0.04)' }}>
                                    <th style={{ ...headerCell, width: COL_WIDTHS.code }}>Код</th>
                                    <th style={{ ...headerCell, width: COL_WIDTHS.article }}>Артикул</th>
                                    <th style={headerCell}>Наименование</th>
                                    <th style={{ ...headerCell, width: COL_WIDTHS.folder }}>Категория</th>
                                    {!isNotInventoried && (
                                        <th style={{ ...headerCell, width: COL_WIDTHS.count, textAlign: 'right' }}>Раз</th>
                                    )}
                                    <th style={{ ...headerCell, width: COL_WIDTHS.lastDate }}>Последняя дата</th>
                                    <th style={{ ...headerCell, width: COL_WIDTHS.daysSince, textAlign: 'right' }}>Дней с последней</th>
                                </tr>
                            </thead>
                            <tbody>
                                {products.map((p, i) => (
                                    <tr key={p.external_id || i}
                                        style={isNotInventoried ? { background: 'rgba(198,69,69,0.04)' } : {}}>
                                        <td style={{ ...bodyCell, color: 'var(--on-dark-soft)', fontFamily: 'var(--mono)', fontSize: 12 }}>
                                            {p.code || '—'}
                                        </td>
                                        <td style={{ ...bodyCell, color: 'var(--on-dark-soft)', fontFamily: 'var(--mono)', fontSize: 12 }}>
                                            {p.article || '—'}
                                        </td>
                                        <td style={bodyCell}>{p.name}</td>
                                        <td style={{ ...bodyCell, color: 'var(--on-dark-soft)' }}>{p.folder || '—'}</td>
                                        {!isNotInventoried && (
                                            <td style={{ ...bodyCell, textAlign: 'right', fontWeight: 500 }}>
                                                {p.inventory_count}
                                            </td>
                                        )}
                                        <td style={{ ...bodyCell, color: 'var(--on-dark-soft)' }}>
                                            {formatDate(p.last_inventoried_at)}
                                        </td>
                                        <td style={{ ...bodyCell, textAlign: 'right' }}>
                                            <DaysBadge days={p.days_since_last} />
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    );
}

InventoryTable.propTypes = {
    title: PropTypes.string.isRequired,
    products: PropTypes.array.isRequired,
    type: PropTypes.oneOf(['inventoried', 'not-inventoried']).isRequired,
    loading: PropTypes.bool.isRequired,
    isMobile: PropTypes.bool,
};
