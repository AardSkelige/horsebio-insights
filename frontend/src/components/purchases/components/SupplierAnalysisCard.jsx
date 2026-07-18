import { useState, useMemo } from 'react';
import PropTypes from 'prop-types';
import { ChevronDown, ChevronUp, ChevronRight } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer } from 'recharts';
import { CHART_ANIMATION } from '../../../utils/chartAnimation';

const CHART_COLORS = ['#cc785c', '#5c8acc', '#5cac6a', '#8a5ccc', '#cc5c8a', '#accc5c'];

const getSupplierStatus = (supplier, threshold = 6, now = new Date()) => {
    const lastOrderDate = supplier.orders?.[0]?.date ? new Date(supplier.orders[0].date) : new Date(0);
    const thresholdDate = new Date(now);
    thresholdDate.setMonth(now.getMonth() - threshold);
    const isActive = lastOrderDate > thresholdDate;
    const monthsAgo = Math.floor((now - lastOrderDate) / (1000 * 60 * 60 * 24 * 30));
    return { isActive, monthsAgo };
};

const SwitchToggle = ({ checked, onChange, label }) => (
    <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
        <span style={{ position: 'relative', display: 'inline-block', width: '34px', height: '18px', flexShrink: 0 }}>
            <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} style={{ position: 'absolute', opacity: 0, width: 0, height: 0 }} />
            <span style={{ position: 'absolute', inset: 0, borderRadius: '9px', backgroundColor: checked ? 'var(--primary)' : 'var(--surface-cream-strong)', transition: 'background-color 200ms' }} />
            <span style={{ position: 'absolute', top: '2px', left: checked ? '18px' : '2px', width: '14px', height: '14px', borderRadius: '50%', backgroundColor: '#fff', transition: 'left 200ms', boxShadow: '0 1px 3px rgba(0,0,0,0.2)' }} />
        </span>
        <span style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--muted)' }}>{label}</span>
    </label>
);

SwitchToggle.propTypes = {
    checked: PropTypes.bool.isRequired,
    onChange: PropTypes.func.isRequired,
    label: PropTypes.string.isRequired,
};

const selectStyle = {
    height: '32px', padding: '0 8px',
    fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--ink)',
    backgroundColor: 'var(--canvas)', border: '1px solid var(--hairline)',
    borderRadius: '6px', outline: 'none', cursor: 'pointer',
};

const thStyle = {
    fontFamily: 'var(--sans)', fontSize: '11px', fontWeight: 600,
    letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--muted)',
    padding: '10px 12px', textAlign: 'left', borderBottom: '1px solid var(--hairline)',
    whiteSpace: 'nowrap',
};

const tdStyle = {
    fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--body)',
    padding: '12px', borderBottom: '1px solid var(--hairline-soft)',
    verticalAlign: 'top',
};

const Badge = ({ active }) => (
    <span style={{
        display: 'inline-block', padding: '2px 8px', borderRadius: '20px',
        fontSize: '11px', fontWeight: 600, fontFamily: 'var(--sans)',
        backgroundColor: active ? 'rgba(5,150,105,0.1)' : 'rgba(212,160,23,0.1)',
        color: active ? '#059669' : '#a07010',
        border: `1px solid ${active ? 'rgba(5,150,105,0.3)' : 'rgba(212,160,23,0.3)'}`,
    }}>
        {active ? 'Активный' : 'Неактивный'}
    </span>
);

Badge.propTypes = { active: PropTypes.bool.isRequired };

const CollapsibleSection = ({ title, defaultOpen = false, children, rightSlot }) => {
    const [open, setOpen] = useState(defaultOpen);
    return (
        <div style={{ backgroundColor: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: '10px' }}>
            <button
                onClick={() => setOpen(o => !o)}
                className="no-tap-scale"
                style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 20px', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left' }}
            >
                <span style={{ fontFamily: 'var(--serif)', fontSize: '18px', fontWeight: 400, color: 'var(--ink)' }}>{title}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
                    {!open && rightSlot}
                    {open ? <ChevronUp style={{ width: 16, height: 16, color: 'var(--muted)', flexShrink: 0 }} /> : <ChevronDown style={{ width: 16, height: 16, color: 'var(--muted)', flexShrink: 0 }} />}
                </div>
            </button>
            {open && <div style={{ padding: '0 20px 20px' }}>{children}</div>}
        </div>
    );
};

CollapsibleSection.propTypes = {
    title: PropTypes.string.isRequired,
    defaultOpen: PropTypes.bool,
    children: PropTypes.node,
    rightSlot: PropTypes.node,
};

const SupplierAnalysisCard = ({ suppliers, material, activityThreshold, setActivityThreshold, showInactive, setShowInactive }) => {
    const [inactiveOpen, setInactiveOpen] = useState(false);
    const suppliersArray = Object.values(suppliers || {});

    const filteredSuppliers = useMemo(() =>
        suppliersArray.filter(s => showInactive || getSupplierStatus(s, activityThreshold).isActive),
        [suppliersArray, showInactive, activityThreshold]
    );

    const inactiveSuppliers = useMemo(() =>
        suppliersArray
            .filter(s => !getSupplierStatus(s, activityThreshold).isActive)
            .map(s => ({ name: s.supplier_name, monthsAgo: getSupplierStatus(s, activityThreshold).monthsAgo })),
        [suppliersArray, activityThreshold]
    );

    const priceHistoryData = useMemo(() => {
        const allDates = new Set();
        const byDate = {};
        filteredSuppliers.forEach(s => {
            s.orders?.forEach(o => {
                const d = o.date.split('T')[0];
                allDates.add(d);
                if (!byDate[d]) byDate[d] = {};
                byDate[d][s.supplier_name] = o.price;
            });
        });
        return Array.from(allDates).sort().map(d => ({ date: d, ...byDate[d] }));
    }, [filteredSuppliers]);

    const fmtDate = (d) => new Date(d).toLocaleDateString('ru');
    const plural = (n, ...forms) => forms[n === 1 ? 0 : n >= 2 && n <= 4 ? 1 : 2];

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {/* Filter bar */}
            <div style={{ backgroundColor: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: '10px', padding: '16px 20px', display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--muted)' }}>Порог активности:</span>
                    <select value={activityThreshold} onChange={e => setActivityThreshold(Number(e.target.value))} style={selectStyle}>
                        <option value={3}>3 месяца</option>
                        <option value={6}>6 месяцев</option>
                        <option value={12}>12 месяцев</option>
                    </select>
                </div>
                <SwitchToggle checked={showInactive} onChange={setShowInactive} label="Показать неактивных" />
                {inactiveSuppliers.length > 0 && !showInactive && (
                    <div style={{ marginLeft: 'auto' }}>
                        <button
                            onClick={() => setInactiveOpen(o => !o)}
                            style={{ display: 'flex', alignItems: 'center', gap: '6px', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--muted)' }}
                        >
                            Скрыто неактивных: {inactiveSuppliers.length}
                            {inactiveOpen ? <ChevronUp style={{ width: 14, height: 14 }} /> : <ChevronRight style={{ width: 14, height: 14 }} />}
                        </button>
                        {inactiveOpen && (
                            <div style={{ marginTop: '8px', padding: '12px', backgroundColor: 'var(--surface-soft)', borderRadius: '8px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                                {inactiveSuppliers.map(s => (
                                    <div key={s.name} style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'var(--sans)', fontSize: '13px' }}>
                                        <span style={{ color: 'var(--body)' }}>{s.name}</span>
                                        <span style={{ color: 'var(--muted)' }}>{s.monthsAgo} мес. назад</span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* Supplier analysis */}
            <CollapsibleSection title="Анализ поставщиков" rightSlot={<span style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--muted)' }}>нажмите чтобы развернуть</span>}>
                {/* Price chart */}
                {priceHistoryData.length > 0 && (
                    <div style={{ marginBottom: '24px' }}>
                        <div style={{ fontFamily: 'var(--sans)', fontSize: '11px', fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: '12px' }}>Динамика цен</div>
                        <div style={{ height: 260 }}>
                            <ResponsiveContainer width="100%" height="100%">
                                <LineChart data={priceHistoryData}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="var(--hairline)" />
                                    <XAxis dataKey="date" tickFormatter={fmtDate} style={{ fontFamily: 'var(--sans)', fontSize: 11 }} />
                                    <YAxis style={{ fontFamily: 'var(--sans)', fontSize: 11 }} />
                                    <RechartsTooltip
                                        formatter={(v, name) => [`${Number(v).toLocaleString('ru')} ₽`, name]}
                                        labelFormatter={fmtDate}
                                        contentStyle={{ fontFamily: 'var(--sans)', fontSize: 12, borderRadius: 8, border: '1px solid var(--hairline)' }}
                                    />
                                    {filteredSuppliers.map((s, i) => (
                                        <Line {...CHART_ANIMATION} key={s.supplier_name} type="monotone" dataKey={s.supplier_name} stroke={CHART_COLORS[i % CHART_COLORS.length]} dot strokeWidth={2} />
                                    ))}
                                </LineChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                )}

                {/* Suppliers table */}
                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr>
                                <th style={{ ...thStyle, width: '25%' }}>Поставщик</th>
                                <th style={{ ...thStyle, width: '20%' }}>Статистика заказов</th>
                                <th style={{ ...thStyle, width: '30%' }}>Сроки поставки</th>
                                <th style={{ ...thStyle, width: '25%' }}>Размеры заказов</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredSuppliers.map(s => {
                                const status = getSupplierStatus(s, activityThreshold);
                                return (
                                    <tr key={s.supplier_name}>
                                        <td style={tdStyle}>
                                            <div style={{ fontWeight: 500, marginBottom: 4 }}>{s.supplier_name}</div>
                                            <Badge active={status.isActive} />
                                            <div style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--muted)', marginTop: 4 }}>
                                                {status.monthsAgo > 0 ? `${status.monthsAgo} мес. назад` : 'менее месяца назад'}
                                            </div>
                                        </td>
                                        <td style={tdStyle}>
                                            <div style={{ fontSize: '18px', fontFamily: 'var(--serif)', color: s.delivery_reliability >= 0.95 ? '#059669' : '#a07010', fontVariantNumeric: 'lining-nums' }}>
                                                {(s.delivery_reliability * 100).toFixed(0)}%
                                            </div>
                                            <div style={{ fontSize: '12px', color: 'var(--muted)', marginTop: 4 }}>Всего: {s.total_orders} · Выполнено: {s.completed_orders}</div>
                                            {s.orders_in_transit > 0 && (
                                                <div style={{ fontSize: '12px', color: '#5c8acc', marginTop: 2 }}>
                                                    {s.orders_in_transit} {plural(s.orders_in_transit, 'заказ', 'заказа', 'заказов')} в пути
                                                </div>
                                            )}
                                        </td>
                                        <td style={tdStyle}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: 6 }}>
                                                <div style={{ flex: 1, height: 4, borderRadius: 2, backgroundColor: 'var(--surface-card)', overflow: 'hidden' }}>
                                                    <div style={{ height: '100%', borderRadius: 2, backgroundColor: 'var(--primary)', width: `${(s.avg_lead_time / s.max_lead_time * 100) || 0}%` }} />
                                                </div>
                                                <span style={{ fontWeight: 500, fontSize: '13px', flexShrink: 0 }}>{s.avg_lead_time?.toFixed(1) || 0} дн.</span>
                                            </div>
                                            <div style={{ fontSize: '12px', color: 'var(--muted)', marginBottom: 8 }}>
                                                мин {s.min_lead_time || 0} · макс {s.max_lead_time || 0} дн.
                                            </div>
                                            {s.orders?.slice(0, 3).map((o, i) => (
                                                <div key={i} style={{ fontSize: '12px', padding: '6px 8px', backgroundColor: 'var(--surface-soft)', borderRadius: '6px', marginBottom: 4 }}>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                                        <span style={{ color: 'var(--muted)' }}>{fmtDate(o.date)}</span>
                                                        {o.is_in_transit
                                                            ? <span style={{ color: '#5c8acc', fontWeight: 500 }}>В пути</span>
                                                            : <span style={{ fontWeight: 500 }}>{o.lead_time} дн.</span>}
                                                    </div>
                                                    <div style={{ color: 'var(--muted)' }}>
                                                        {o.quantity.toLocaleString('ru')} {material.uom} · {o.price} ₽
                                                    </div>
                                                </div>
                                            ))}
                                        </td>
                                        <td style={tdStyle}>
                                            {Object.entries(s.common_quantities || {})
                                                .sort((a, b) => b[1] - a[1])
                                                .map(([qty, count], i) => (
                                                    <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                                                        <span style={{ fontSize: '13px' }}>{Number(qty).toLocaleString('ru')} {material.uom}</span>
                                                        <span style={{ fontSize: '11px', fontWeight: 600, padding: '2px 7px', borderRadius: '20px', backgroundColor: 'rgba(92,138,204,0.12)', color: '#5c8acc' }}>
                                                            {count} {plural(count, 'раз', 'раза', 'раз')}
                                                        </span>
                                                    </div>
                                                ))
                                            }
                                        </td>
                                    </tr>
                                );
                            })}
                            {filteredSuppliers.length === 0 && (
                                <tr><td colSpan={4} style={{ ...tdStyle, textAlign: 'center', color: 'var(--muted)', padding: '32px' }}>Нет активных поставщиков</td></tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </CollapsibleSection>
        </div>
    );
};

SupplierAnalysisCard.propTypes = {
    suppliers: PropTypes.object,
    material: PropTypes.shape({ uom: PropTypes.string }),
    activityThreshold: PropTypes.number.isRequired,
    setActivityThreshold: PropTypes.func.isRequired,
    showInactive: PropTypes.bool.isRequired,
    setShowInactive: PropTypes.func.isRequired,
};

export default SupplierAnalysisCard;
