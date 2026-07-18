import { useState } from 'react';
import PropTypes from 'prop-types';
import { AnimatePresence, m } from 'motion/react';
import { ChevronDown, ChevronUp, ChevronsUpDown, ChevronRight } from 'lucide-react';
import { SkeletonRows } from '../ui/Skeleton';

const COL_WIDTHS = {
    code: 80,
    article: 120,
    name: undefined,
    folder: 130,
    count: 90,
    lastDate: 150,
    daysSince: 110,
};

const headerCell = {
    fontFamily: 'var(--sans)',
    fontSize: 11,
    fontWeight: 500,
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
    color: 'var(--muted)',
    padding: '10px 12px',
    textAlign: 'left',
    whiteSpace: 'nowrap',
    cursor: 'pointer',
    userSelect: 'none',
};

const bodyCell = {
    fontFamily: 'var(--sans)',
    fontSize: 13,
    color: 'var(--ink)',
    padding: '10px 12px',
    borderTop: '1px solid var(--hairline-soft)',
};

function formatDate(isoStr) {
    if (!isoStr) return '—';
    const d = new Date(isoStr);
    return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function DaysBadge({ days }) {
    if (days === null || days === undefined) return <span style={{ color: 'var(--muted)' }}>—</span>;
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

function SortIcon({ active, order }) {
    if (!active) return <ChevronsUpDown size={11} style={{ color: 'var(--muted-soft)', marginLeft: 3, flexShrink: 0 }} />;
    return order === 'asc'
        ? <ChevronUp size={11} style={{ color: 'var(--primary)', marginLeft: 3, flexShrink: 0 }} />
        : <ChevronDown size={11} style={{ color: 'var(--primary)', marginLeft: 3, flexShrink: 0 }} />;
}

SortIcon.propTypes = { active: PropTypes.bool, order: PropTypes.oneOf(['asc', 'desc']) };

const compare = (a, b, field) => {
    const av = a[field];
    const bv = b[field];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;   // пустые — всегда в конец
    if (bv == null) return -1;
    if (typeof av === 'number') return av - bv;
    return String(av).localeCompare(String(bv), 'ru');
};

export default function InventoryTable({ title, products, type, loading, isMobile, open, onToggle }) {
    const isNotInventoried = type === 'not-inventoried';
    const [sortField, setSortField] = useState(null);
    const [sortOrder, setSortOrder] = useState('asc');

    const handleSort = (field) => {
        if (field === sortField) {
            setSortOrder(o => (o === 'asc' ? 'desc' : 'asc'));
        } else {
            setSortField(field);
            setSortOrder('asc');
        }
    };

    const sorted = sortField
        ? [...products].sort((a, b) => {
            const r = compare(a, b, sortField);
            return sortOrder === 'asc' ? r : -r;
        })
        : products;

    const th = (field, label, extra = {}) => (
        <th style={{ ...headerCell, ...extra }} onClick={() => handleSort(field)}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: extra.textAlign === 'right' ? 'flex-end' : 'flex-start' }}>
                {label}
                <SortIcon active={sortField === field} order={sortOrder} />
            </div>
        </th>
    );

    return (
        <div style={{ marginBottom: 16 }}>
            <div style={{ background: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: 12, overflow: 'hidden' }}>
                {/* Заголовок секции — переключает сворачивание */}
                <button
                    onClick={onToggle}
                    className="no-tap-scale"
                    style={{
                        width: '100%',
                        display: 'flex', alignItems: 'center', gap: 10,
                        padding: '14px 16px',
                        background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left',
                    }}
                >
                    <ChevronRight size={14} style={{ color: 'var(--muted)', transform: open ? 'rotate(90deg)' : 'none', transition: 'transform 180ms ease', flexShrink: 0 }} />
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
                        {loading ? '…' : products.length}
                    </span>
                    <span style={{ marginLeft: 'auto', fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted-soft)' }}>
                        {open ? 'свернуть' : 'показать'}
                    </span>
                </button>

                <AnimatePresence initial={false}>
                    {open && (
                        <m.div
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: 'auto', opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            transition={{ duration: 0.25, ease: 'easeOut' }}
                            style={{ overflow: 'hidden', borderTop: '1px solid var(--hairline-soft)' }}
                        >
                            {loading ? (
                                <table style={{ width: '100%', borderCollapse: 'collapse' }} aria-busy="true">
                                    <tbody>
                                        <SkeletonRows cols={isMobile ? 2 : 6} rows={5} />
                                    </tbody>
                                </table>
                            ) : products.length === 0 ? (
                                <div style={{
                                    padding: 32, textAlign: 'center',
                                    fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--muted)',
                                }}>
                                    {isNotInventoried ? 'Все позиции были учтены — отлично!' : 'Нет данных'}
                                </div>
                            ) : isMobile ? (
                                /* ── Mobile card list ── */
                                <div>
                                    {sorted.map((p, i) => (
                                        <div key={p.external_id || i} style={{
                                            padding: '12px 16px',
                                            borderTop: i > 0 ? '1px solid var(--hairline-soft)' : 'none',
                                            background: isNotInventoried ? 'rgba(198,69,69,0.04)' : 'transparent',
                                        }}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8, marginBottom: 5 }}>
                                                <span style={{ fontSize: 13, color: 'var(--ink)', fontWeight: 500, flex: 1, minWidth: 0 }}>
                                                    {p.name}
                                                </span>
                                                <DaysBadge days={p.days_since_last} />
                                            </div>
                                            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
                                                {p.code && (
                                                    <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--muted)' }}>
                                                        #{p.code}
                                                    </span>
                                                )}
                                                {p.article && (
                                                    <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--muted)' }}>
                                                        {p.article}
                                                    </span>
                                                )}
                                                {p.folder && (
                                                    <span style={{ fontSize: 11, color: 'var(--muted)' }}>
                                                        {p.folder}
                                                    </span>
                                                )}
                                                {!isNotInventoried && p.inventory_count !== undefined && (
                                                    <span style={{ fontSize: 11, color: 'var(--muted)' }}>
                                                        {p.inventory_count} раз
                                                    </span>
                                                )}
                                                {p.last_inventoried_at && (
                                                    <span style={{ fontSize: 11, color: 'var(--muted)' }}>
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
                                            <tr style={{ background: 'var(--surface-soft)' }}>
                                                {th('code', 'Код', { width: COL_WIDTHS.code })}
                                                {th('article', 'Артикул', { width: COL_WIDTHS.article })}
                                                {th('name', 'Наименование')}
                                                {th('folder', 'Категория', { width: COL_WIDTHS.folder })}
                                                {!isNotInventoried && th('inventory_count', 'Раз', { width: COL_WIDTHS.count, textAlign: 'right' })}
                                                {th('last_inventoried_at', 'Последняя дата', { width: COL_WIDTHS.lastDate })}
                                                {th('days_since_last', 'Дней с последней', { width: COL_WIDTHS.daysSince, textAlign: 'right' })}
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {sorted.map((p, i) => (
                                                <tr key={p.external_id || i}
                                                    style={isNotInventoried ? { background: 'rgba(198,69,69,0.04)' } : {}}>
                                                    <td style={{ ...bodyCell, color: 'var(--muted)', fontFamily: 'var(--mono)', fontSize: 12 }}>
                                                        {p.code || '—'}
                                                    </td>
                                                    <td style={{ ...bodyCell, color: 'var(--muted)', fontFamily: 'var(--mono)', fontSize: 12 }}>
                                                        {p.article || '—'}
                                                    </td>
                                                    <td style={bodyCell}>{p.name}</td>
                                                    <td style={{ ...bodyCell, color: 'var(--muted)' }}>{p.folder || '—'}</td>
                                                    {!isNotInventoried && (
                                                        <td style={{ ...bodyCell, textAlign: 'right', fontWeight: 500 }}>
                                                            {p.inventory_count}
                                                        </td>
                                                    )}
                                                    <td style={{ ...bodyCell, color: 'var(--muted)' }}>
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
                        </m.div>
                    )}
                </AnimatePresence>
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
    open: PropTypes.bool.isRequired,
    onToggle: PropTypes.func.isRequired,
};
