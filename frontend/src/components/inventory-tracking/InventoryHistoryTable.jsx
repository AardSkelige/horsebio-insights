import PropTypes from 'prop-types';
import { Badge, DataTable, SectionLabel } from '../ui';
import { formatDateTimeShort } from '../../utils/formatters';

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

function PctBar({ pct }) {
    const color = pct >= 80 ? 'var(--success)' : pct >= 50 ? 'var(--warning)' : 'var(--error)';
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
        <div>
            <SectionLabel>По месяцам</SectionLabel>

            <div style={{ background: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: 12, overflow: 'hidden' }}>
                {isMobile ? (
                    /* ── Mobile cards ── */
                    <div>
                        {history.map((row, i) => {
                            const monthKey = row.month_start.slice(0, 7);
                            const active = selectedMonth === monthKey;
                            const color = row.pct >= 80 ? 'var(--success)' : row.pct >= 50 ? 'var(--warning)' : 'var(--error)';
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
                                                    background: 'var(--success-bg)',
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
                    <DataTable
                        columns={[
                            { key: 'month', label: 'Месяц', render: (r) => formatMonthLabel(r.month_start.slice(0, 7)) },
                            { key: 'total', label: 'Всего', numeric: true },
                            {
                                key: 'inventoried',
                                label: 'Были',
                                numeric: true,
                                render: (r) => <span style={{ color: 'var(--success-ink)' }}>{r.inventoried}</span>,
                            },
                            {
                                key: 'not_inventoried',
                                label: 'Не были',
                                numeric: true,
                                render: (r) => (
                                    <span style={{ color: r.not_inventoried > 0 ? 'var(--error-ink)' : 'var(--muted)' }}>
                                        {r.not_inventoried}
                                    </span>
                                ),
                            },
                            { key: 'pct', label: 'Охват', render: (r) => <PctBar pct={r.pct} /> },
                            { key: 'run_at', label: 'Обновлено', render: (r) => formatDateTimeShort(r.run_at) },
                            {
                                key: 'snapshot',
                                label: '',
                                sortable: false,
                                render: (r) => r.is_snapshot && <Badge tone="success">снимок</Badge>,
                            },
                        ]}
                        rows={history}
                        rowKey="month_start"
                        onRowClick={(r) => {
                            const monthKey = r.month_start.slice(0, 7);
                            onSelectMonth(selectedMonth === monthKey ? null : monthKey);
                        }}
                        isRowActive={(r) => selectedMonth === r.month_start.slice(0, 7)}
                        emptyText="Инвентаризаций пока не было"
                    />
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
