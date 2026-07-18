import { useState, useEffect, useCallback } from 'react';
import PropTypes from 'prop-types';
import { counterpartiesApi } from '../../../api/counterpartiesApi';
import { X, ChevronDown, Loader2, AlertCircle } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { CounterpartyPropTypes } from './types';
import { CHART_ANIMATION } from '../../../utils/chartAnimation';
import { formatDateTime, formatDate } from '../../../utils/formatters';
import SectionLabel from '../../ui/SectionLabel';
import { ModalShell } from '../../ui/motion';

/* ── helpers ──────────────────────────────────────────────── */

const fmt  = (n) => (n == null ? '—' : n.toLocaleString('ru-RU'));
const fmtC = (v) => (v == null ? '—' : v.toLocaleString('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }));
const plural = (n) => n === 1 ? 'отгрузка' : n < 5 ? 'отгрузки' : 'отгрузок';

/* ── sub-components ───────────────────────────────────────── */

const StatCard = ({ title, value }) => (
    <div style={{ background: 'var(--surface-card)', borderRadius: 10, padding: '14px 16px', border: '1px solid var(--hairline)' }}>
        <div style={{ fontFamily: 'var(--sans)', fontSize: 11, fontWeight: 500, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 6 }}>{title}</div>
        <div style={{ fontFamily: 'var(--serif)', fontSize: 26, fontWeight: 400, letterSpacing: '-0.02em', color: 'var(--ink)', fontVariantNumeric: 'lining-nums', fontFeatureSettings: '"lnum" 1' }}>{value}</div>
    </div>
);
StatCard.propTypes = { title: PropTypes.string.isRequired, value: PropTypes.string.isRequired };

const TopProductCard = ({ product }) => {
    if (!product?.name) return null;
    return (
        <div style={{ padding: '10px 12px', borderRadius: 8, border: '1px solid var(--hairline)', background: 'var(--canvas)' }}>
            <div style={{ fontFamily: 'var(--sans)', fontSize: 13, fontWeight: 500, color: 'var(--ink)', marginBottom: 4 }}>{product.name}</div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 4 }}>
                {product.quantity != null && <span style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)' }}>{fmt(product.quantity)} шт.</span>}
                {product.revenue   != null && <span style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--body)' }}>{fmtC(product.revenue)}</span>}
            </div>
            {product.shipments_count > 0 && (
                <span style={{ fontFamily: 'var(--sans)', fontSize: 11, background: 'var(--surface-card)', color: 'var(--muted)', borderRadius: 9999, padding: '2px 8px', marginTop: 4, display: 'inline-block' }}>
                    {product.shipments_count} {plural(product.shipments_count)}
                </span>
            )}
        </div>
    );
};
TopProductCard.propTypes = {
    product: PropTypes.shape({ name: PropTypes.string, quantity: PropTypes.number, revenue: PropTypes.number, shipments_count: PropTypes.number }).isRequired,
};

const ShipmentPanel = ({ shipment }) => (
    <div style={{ borderLeft: '2px solid var(--hairline)', paddingLeft: 14, paddingBottom: 12 }}>
        <div style={{ fontFamily: 'var(--sans)', fontSize: 13, fontWeight: 500, color: 'var(--ink)' }}>Отгрузка №{shipment.number}</div>
        <div style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)', marginBottom: 8 }}>{formatDateTime(shipment.date)}</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {shipment.items?.map((item, i) => (
                <div key={i} style={{ background: 'var(--surface-soft)', borderRadius: 6, padding: '8px 10px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <span style={{ fontFamily: 'var(--sans)', fontSize: 12, fontWeight: 500, color: 'var(--ink)' }}>{item.product_name}</span>
                        <span style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)', flexShrink: 0, marginLeft: 8 }}>{fmt(item.quantity)} шт.</span>
                    </div>
                    {item.materials?.length > 0 && (
                        <div style={{ marginTop: 4, paddingLeft: 8, borderLeft: '1px solid var(--hairline)' }}>
                            {item.materials.map((m, mi) => (
                                <div key={mi} style={{ fontFamily: 'var(--sans)', fontSize: 11, color: 'var(--muted)' }}>{m.name}: {fmt(m.quantity)} {m.uom}</div>
                            ))}
                        </div>
                    )}
                </div>
            ))}
        </div>
    </div>
);
ShipmentPanel.propTypes = {
    shipment: PropTypes.shape({
        number: PropTypes.string.isRequired,
        date: PropTypes.string.isRequired,
        items: PropTypes.arrayOf(PropTypes.shape({
            product_name: PropTypes.string.isRequired,
            quantity: PropTypes.number.isRequired,
            materials: PropTypes.arrayOf(PropTypes.shape({ name: PropTypes.string.isRequired, quantity: PropTypes.number.isRequired, uom: PropTypes.string.isRequired })),
        })).isRequired,
    }).isRequired,
};

const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    return (
        <div style={{ background: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: 8, padding: '10px 14px', fontFamily: 'var(--sans)', fontSize: 12 }}>
            <div style={{ color: 'var(--muted)', marginBottom: 6 }}>{label}</div>
            {payload.map((entry, i) => (
                <div key={i} style={{ color: entry.color }}>
                    {entry.name}: {entry.name === 'Количество' ? `${fmt(entry.value)} шт.` : fmtC(entry.value)}
                </div>
            ))}
        </div>
    );
};
CustomTooltip.propTypes = { active: PropTypes.bool, payload: PropTypes.array, label: PropTypes.string };


/* ── main modal ───────────────────────────────────────────── */

const CounterpartyDetailsModal = ({ counterparty, visible, onClose, dateRange }) => {
    const [details, setDetails] = useState(null);
    const [loading, setLoading]  = useState(false);
    const [error, setError]      = useState(null);
    const [openDates, setOpenDates] = useState({});

    const fetchDetails = useCallback(async () => {
        if (!counterparty?.id || !visible) return;
        setLoading(true);
        setError(null);
        try {
            const params = new URLSearchParams();
            if (dateRange?.startDate) params.append('startDate', dateRange.startDate);
            if (dateRange?.endDate)   params.append('endDate',   dateRange.endDate);
            const data = await counterpartiesApi.getDetails(counterparty.id, params);
            if (data.status === 'success' && data.data) setDetails(data.data);
            else throw new Error(data.message || 'Ошибка получения данных');
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }, [counterparty, visible, dateRange]);

    useEffect(() => { fetchDetails(); }, [fetchDetails]);

    useEffect(() => {
        const onKey = (e) => { if (e.key === 'Escape') onClose(); };
        if (visible) document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, [visible, onClose]);

    const chartData
 = details?.monthly_dynamics?.map(item => ({
        month: new Date(item.month).toLocaleDateString('ru', { month: 'short', year: '2-digit' }),
        quantity: item.quantity,
        revenue: item.revenue,
    })) || [];

    const groupedShipments = details?.shipment_history?.reduce((acc, s) => {
        const d = s.date.split('T')[0];
        (acc[d] ??= []).push(s);
        return acc;
    }, {}) || {};

    return (
        <ModalShell open={visible} onClose={onClose} maxWidth={900}>

                {/* Header */}
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', padding: '20px 24px 16px', borderBottom: '1px solid var(--hairline)', flexShrink: 0 }}>
                    <div>
                        <h2 style={{ fontFamily: 'var(--serif)', fontSize: 24, fontWeight: 400, letterSpacing: '-0.02em', color: 'var(--ink)', margin: 0 }}>
                            {counterparty?.name}
                        </h2>
                        <p style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)', margin: '4px 0 0' }}>Детальная статистика контрагента</p>
                    </div>
                    <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)', padding: 4, marginTop: 2 }}>
                        <X size={18} />
                    </button>
                </div>

                {/* Body */}
                <div style={{ overflowY: 'auto', padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 24 }}>

                    {loading && (
                        <div style={{ display: 'flex', justifyContent: 'center', padding: '48px 0', color: 'var(--muted)' }}>
                            <Loader2 size={22} className="animate-spin" />
                        </div>
                    )}

                    {error && !loading && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '16px', borderRadius: 8, background: 'var(--surface-soft)', color: '#c64545' }}>
                            <AlertCircle size={15} />
                            <span style={{ fontFamily: 'var(--sans)', fontSize: 13 }}>{error}</span>
                        </div>
                    )}

                    {details && !loading && !error && (
                        <>
                            {/* Статистика */}
                            <section>
                                <SectionLabel>Статистика</SectionLabel>
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 10 }}>
                                    <StatCard title="Всего отгрузок" value={fmt(details.statistics?.total_shipments)} />
                                    <StatCard title="Всего товаров"  value={fmt(details.statistics?.total_products)}  />
                                    <StatCard title="Видов товаров"  value={fmt(details.statistics?.unique_products)} />
                                </div>
                            </section>

                            {/* Топы */}
                            <section>
                                <SectionLabel>Топ товаров</SectionLabel>
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16 }}>
                                    <div>
                                        <div style={{ fontFamily: 'var(--sans)', fontSize: 12, fontWeight: 500, color: 'var(--muted)', marginBottom: 8 }}>По количеству</div>
                                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                                            {details.top_by_quantity?.map((p, i) => <TopProductCard key={i} product={p} />)}
                                        </div>
                                    </div>
                                    <div>
                                        <div style={{ fontFamily: 'var(--sans)', fontSize: 12, fontWeight: 500, color: 'var(--muted)', marginBottom: 8 }}>По выручке</div>
                                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                                            {details.top_by_revenue?.map((p, i) => <TopProductCard key={i} product={p} />)}
                                        </div>
                                    </div>
                                </div>
                            </section>

                            {/* График */}
                            {chartData.length > 0 && (
                                <section>
                                    <SectionLabel>Динамика по месяцам</SectionLabel>
                                    <div style={{ height: 260 }}>
                                        <ResponsiveContainer width="100%" height="100%">
                                            <LineChart data={chartData}>
                                                <CartesianGrid strokeDasharray="3 3" stroke="var(--hairline)" />
                                                <XAxis dataKey="month" tick={{ fontSize: 11, fontFamily: 'var(--sans)', fill: 'var(--muted)' }} />
                                                <YAxis yAxisId="quantity" tick={{ fontSize: 11, fontFamily: 'var(--sans)', fill: 'var(--muted)' }} tickFormatter={v => `${fmt(v)} шт.`} width={70} />
                                                <YAxis yAxisId="revenue" orientation="right" tick={{ fontSize: 11, fontFamily: 'var(--sans)', fill: 'var(--muted)' }} tickFormatter={v => `${(v / 1000).toFixed(0)}k ₽`} width={60} />
                                                <Tooltip content={<CustomTooltip />} />
                                                <Legend wrapperStyle={{ fontFamily: 'var(--sans)', fontSize: 12 }} />
                                                <Line {...CHART_ANIMATION} yAxisId="quantity" type="monotone" dataKey="quantity" name="Количество" stroke="var(--primary)" strokeWidth={2} dot={{ r: 3 }} />
                                                <Line {...CHART_ANIMATION} yAxisId="revenue"  type="monotone" dataKey="revenue"  name="Выручка"    stroke="var(--muted)"   strokeWidth={2} dot={{ r: 3 }} />
                                            </LineChart>
                                        </ResponsiveContainer>
                                    </div>
                                </section>
                            )}

                            {/* История отгрузок */}
                            {Object.keys(groupedShipments).length > 0 && (
                                <section>
                                    <SectionLabel>История отгрузок</SectionLabel>
                                    <p style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)', margin: '0 0 10px' }}>Показаны последние 1000 отгрузок</p>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                        {Object.entries(groupedShipments).map(([date, shipments]) => (
                                            <div key={date} style={{ border: '1px solid var(--hairline)', borderRadius: 8, overflow: 'hidden' }}>
                                                <button
                                                    onClick={() => setOpenDates(prev => ({ ...prev, [date]: !prev[date] }))}
                                                    style={{ width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px', background: openDates[date] ? 'var(--surface-soft)' : 'var(--canvas)', border: 'none', cursor: 'pointer', fontFamily: 'var(--sans)', fontSize: 13 }}
                                                >
                                                    <span style={{ fontWeight: 500, color: 'var(--ink)' }}>{formatDate(date)}</span>
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                                        <span style={{ fontSize: 12, color: 'var(--muted)' }}>{shipments.length} {plural(shipments.length)}</span>
                                                        <ChevronDown size={14} style={{ color: 'var(--muted)', transform: openDates[date] ? 'rotate(180deg)' : 'none', transition: 'transform 150ms' }} />
                                                    </div>
                                                </button>
                                                {openDates[date] && (
                                                    <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 12, borderTop: '1px solid var(--hairline)' }}>
                                                        {shipments.map((s, i) => <ShipmentPanel key={`${s.number}-${i}`} shipment={s} />)}
                                                    </div>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                </section>
                            )}
                        </>
                    )}
                </div>
        </ModalShell>
    );
};

CounterpartyDetailsModal.propTypes = {
    counterparty: PropTypes.shape(CounterpartyPropTypes),
    visible: PropTypes.bool.isRequired,
    onClose: PropTypes.func.isRequired,
    dateRange: PropTypes.shape({ startDate: PropTypes.string, endDate: PropTypes.string }),
};

export default CounterpartyDetailsModal;
