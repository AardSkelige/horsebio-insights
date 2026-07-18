import PropTypes from 'prop-types';

function formatMonthLabel(yyyyMm) {
    const [year, month] = yyyyMm.split('-');
    const d = new Date(Number(year), Number(month) - 1, 1);
    return d.toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' });
}

function formatMonthShort(yyyyMm) {
    const [year, month] = yyyyMm.split('-');
    const d = new Date(Number(year), Number(month) - 1, 1);
    return d.toLocaleDateString('ru-RU', { month: 'short', year: '2-digit' });
}

const th = {
    fontFamily: 'var(--sans)',
    fontSize: 11,
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    color: 'var(--muted)',
    padding: '10px 16px',
    textAlign: 'left',
    whiteSpace: 'nowrap',
};

const td = {
    fontFamily: 'var(--sans)',
    fontSize: 13,
    color: 'var(--ink)',
    padding: '11px 16px',
    borderTop: '1px solid var(--hairline-soft)',
};

function PctBar({ pct }) {
    const color = pct >= 80 ? 'var(--success)' : pct >= 50 ? '#f59e0b' : 'var(--error)';
    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{
                width: 72, height: 4, borderRadius: 2,
                background: 'var(--surface-cream-strong)',
                overflow: 'hidden', flexShrink: 0,
            }}>
                <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 2 }} />
            </div>
            <span style={{ fontFamily: 'var(--sans)', fontSize: 12, color, fontWeight: 500, minWidth: 34 }}>
                {pct}%
            </span>
        </div>
    );
}

PctBar.propTypes = { pct: PropTypes.number.isRequired };

export default function InventoryHistoryTable({ history, selectedMonth, onSelectMonth, isMobile }) {
    return (
        <div style={{ marginTop: 48 }}>
            <h2 style={{
                fontFamily: 'var(--serif)',
                fontSize: isMobile ? 18 : 22,
                fontWeight: 400,
                letterSpacing: '-0.02em',
                color: 'var(--ink)',
                margin: '0 0 16px',
            }}>
                По месяцам
            </h2>

            <div style={{ background: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: 12, overflow: 'hidden' }}>
                {isMobile ? (
                    /* ── Mobile cards ── */
                    <div>
                        {history.map((row, i) => {
                            const monthKey = row.month_start.slice(0, 7);
                            const active = selectedMonth === monthKey;
                            const color = row.pct >= 80 ? 'var(--success)' : row.pct >= 50 ? '#f59e0b' : 'var(--error)';
                            return (
                                <div
                                    key={row.month_start}
                                    onClick={() => onSelectMonth(active ? null : monthKey)}
                                    style={{
                                        padding: '12px 16px',
                                        borderTop: i > 0 ? '1px solid var(--hairline-soft)' : 'none',
                                        background: active ? 'var(--surface-soft)' : 'transparent',
                                        cursor: 'pointer',
                                    }}
                                >
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                                        <span style={{
                                            fontFamily: 'var(--sans)', fontSize: 13,
                                            color: active ? 'var(--primary)' : 'var(--ink)',
                                            fontWeight: active ? 600 : 500,
                                        }}>
                                            {formatMonthShort(monthKey)}
                                        </span>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                            <span style={{ fontFamily: 'var(--sans)', fontSize: 12, color, fontWeight: 600 }}>
                                                {row.pct}%
                                            </span>
                                            {row.is_snapshot && (
                                                <span style={{
                                                    background: 'rgba(93,184,114,0.12)',
                                                    color: 'var(--success)',
                                                    fontFamily: 'var(--sans)', fontSize: 10,
                                                    fontWeight: 500, padding: '2px 7px', borderRadius: 10,
                                                }}>
                                                    снимок
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                    <div style={{ marginBottom: 6 }}>
                                        <PctBar pct={row.pct} />
                                    </div>
                                    <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                                        <span style={{ fontSize: 11, color: 'var(--muted)' }}>
                                            Всего: {row.total}
                                        </span>
                                        <span style={{ fontSize: 11, color: 'var(--success)' }}>
                                            Были: {row.inventoried}
                                        </span>
                                        <span style={{ fontSize: 11, color: row.not_inventoried > 0 ? 'var(--error)' : 'var(--muted)' }}>
                                            Не были: {row.not_inventoried}
                                        </span>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                ) : (
                    /* ── Desktop table ── */
                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ background: 'var(--surface-soft)' }}>
                                    <th style={th}>Месяц</th>
                                    <th style={{ ...th, textAlign: 'right' }}>Всего</th>
                                    <th style={{ ...th, textAlign: 'right' }}>Были</th>
                                    <th style={{ ...th, textAlign: 'right' }}>Не были</th>
                                    <th style={th}>Охват</th>
                                    <th style={th}>Обновлено</th>
                                    <th style={th}></th>
                                </tr>
                            </thead>
                            <tbody>
                                {history.map(row => {
                                    const monthKey = row.month_start.slice(0, 7);
                                    const active = selectedMonth === monthKey;
                                    return (
                                        <tr
                                            key={row.month_start}
                                            onClick={() => onSelectMonth(active ? null : monthKey)}
                                            style={{
                                                background: active ? 'var(--surface-soft)' : 'transparent',
                                                cursor: 'pointer',
                                                transition: 'background 0.1s',
                                            }}
                                        >
                                            <td style={td}>
                                                <span style={{
                                                    color: active ? 'var(--primary)' : 'var(--ink)',
                                                    fontWeight: active ? 600 : 400,
                                                }}>
                                                    {formatMonthLabel(monthKey)}
                                                </span>
                                            </td>
                                            <td style={{ ...td, textAlign: 'right', color: 'var(--muted)' }}>
                                                {row.total}
                                            </td>
                                            <td style={{ ...td, textAlign: 'right', color: 'var(--success)' }}>
                                                {row.inventoried}
                                            </td>
                                            <td style={{ ...td, textAlign: 'right', color: row.not_inventoried > 0 ? 'var(--error)' : 'var(--muted)' }}>
                                                {row.not_inventoried}
                                            </td>
                                            <td style={td}><PctBar pct={row.pct} /></td>
                                            <td style={{ ...td, color: 'var(--muted)', fontSize: 12 }}>
                                                {new Date(row.run_at).toLocaleString('ru-RU', {
                                                    day: '2-digit', month: '2-digit',
                                                    hour: '2-digit', minute: '2-digit',
                                                })}
                                            </td>
                                            <td style={td}>
                                                {row.is_snapshot && (
                                                    <span style={{
                                                        background: 'rgba(93,184,114,0.12)',
                                                        color: 'var(--success)',
                                                        fontFamily: 'var(--sans)', fontSize: 11,
                                                        fontWeight: 500, padding: '2px 9px', borderRadius: 10,
                                                    }}>
                                                        снимок
                                                    </span>
                                                )}
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    );
}

InventoryHistoryTable.propTypes = {
    history: PropTypes.arrayOf(PropTypes.shape({
        month_start: PropTypes.string.isRequired,
        run_at: PropTypes.string.isRequired,
        total: PropTypes.number.isRequired,
        inventoried: PropTypes.number.isRequired,
        not_inventoried: PropTypes.number.isRequired,
        pct: PropTypes.number.isRequired,
        is_snapshot: PropTypes.bool.isRequired,
    })).isRequired,
    selectedMonth: PropTypes.string,
    onSelectMonth: PropTypes.func.isRequired,
    isMobile: PropTypes.bool,
};
