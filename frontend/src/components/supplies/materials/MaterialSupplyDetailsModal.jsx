import { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { X, ChevronRight, Loader2 } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { CHART_ANIMATION } from '../../../utils/chartAnimation';
import SectionLabel from '../../ui/SectionLabel';
import StatCard from '../../ui/StatCard';
import { ModalShell } from '../../ui/motion';
import { suppliesApi } from '../../../api/suppliesApi';

const fmt = (n) => (n ?? 0).toLocaleString('ru-RU');

const SupplyRow = ({ supply, uom }) => {
    const [open, setOpen] = useState(false);
    return (
        <div style={{ borderBottom: '1px solid var(--hairline-soft)' }}>
            <button onClick={() => setOpen(o => !o)}
                style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 0', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <ChevronRight size={13} style={{ color: 'var(--muted)', transform: open ? 'rotate(90deg)' : 'none', transition: 'transform 150ms', flexShrink: 0 }} />
                    <span style={{ fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--ink)' }}>
                        Приёмка №{supply.number} от {supply.date}
                    </span>
                </div>
                <span style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)', whiteSpace: 'nowrap' }}>
                    {fmt(supply.quantity)} {uom}
                </span>
            </button>
            {open && (
                <div style={{ paddingBottom: 10 }}>
                    <div style={{ background: 'var(--surface-soft)', borderRadius: 8, padding: '10px 14px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                        <div>
                            <div style={{ fontFamily: 'var(--sans)', fontSize: 10, color: 'var(--muted)', marginBottom: 2 }}>Поставщик</div>
                            <div style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--ink)' }}>{supply.supplier}</div>
                        </div>
                        <div>
                            <div style={{ fontFamily: 'var(--sans)', fontSize: 10, color: 'var(--muted)', marginBottom: 2 }}>Цена за единицу</div>
                            <div style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--ink)' }}>{(supply.price || 0).toFixed(2)} ₽</div>
                        </div>
                        <div>
                            <div style={{ fontFamily: 'var(--sans)', fontSize: 10, color: 'var(--muted)', marginBottom: 2 }}>Количество</div>
                            <div style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--ink)' }}>{fmt(supply.quantity)} {uom}</div>
                        </div>
                        <div>
                            <div style={{ fontFamily: 'var(--sans)', fontSize: 10, color: 'var(--muted)', marginBottom: 2 }}>Сумма</div>
                            <div style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--ink)' }}>{fmt(supply.total)} ₽</div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
SupplyRow.propTypes = {
    supply: PropTypes.shape({ number: PropTypes.string, date: PropTypes.string, supplier: PropTypes.string, price: PropTypes.number, quantity: PropTypes.number, total: PropTypes.number }).isRequired,
    uom: PropTypes.string.isRequired,
};

const ChartTooltip = ({ active, payload, label, uom }) => {
    if (!active || !payload?.length) return null;
    return (
        <div style={{ background: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: 8, padding: '8px 12px', fontFamily: 'var(--sans)', fontSize: 12 }}>
            <div style={{ color: 'var(--muted)', marginBottom: 4 }}>{label}</div>
            {payload.map((entry, i) => (
                <div key={i} style={{ color: entry.color }}>
                    {entry.name === 'quantity' ? `${fmt(entry.value)} ${uom}` : `${entry.value.toFixed(2)} ₽`}
                </div>
            ))}
        </div>
    );
};
ChartTooltip.propTypes = { active: PropTypes.bool, payload: PropTypes.array, label: PropTypes.string, uom: PropTypes.string };

const MaterialSupplyDetailsModal = ({ material, visible, onClose, dateRange }) => {
    const [details, setDetails] = useState(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!material?.id || !visible) return;
        const ctrl = new AbortController();
        setLoading(true);
        setDetails(null);

        const params = new URLSearchParams();
        if (dateRange?.startDate) params.append('startDate', dateRange.startDate);
        if (dateRange?.endDate)   params.append('endDate',   dateRange.endDate);
        const qs = params.toString();

        suppliesApi.materials.getDetails(material.id, qs, ctrl.signal)
            .then(data => { if (data.status === 'success') setDetails(data.data); })
            .catch(() => {})
            .finally(() => setLoading(false));

        return () => ctrl.abort();
    }, [material, visible, dateRange]);

    useEffect(() => {
        if (!visible) return;
        const handler = (e) => { if (e.key === 'Escape') onClose(); };
        document.addEventListener('keydown', handler);
        return () => document.removeEventListener('keydown', handler);
    }, [visible, onClose]);

    const chartData = details?.monthly_data?.map(item => ({
        month: new Date(item.month).toLocaleDateString('ru', { month: 'short', year: '2-digit' }),
        quantity: item.quantity,
        price: item.avg_price,
    })) || [];

    const uom = details?.material?.uom || '';

    return (
        <ModalShell open={visible} onClose={onClose} maxWidth={900}>
                {/* Header */}
                <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', padding: '20px 24px 16px', borderBottom: '1px solid var(--hairline)', flexShrink: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, minWidth: 0 }}>
                        <h2 style={{ fontFamily: 'var(--serif)', fontSize: 22, fontWeight: 400, letterSpacing: '-0.02em', color: 'var(--ink)', margin: 0 }}>
                            {loading || !details ? (material?.name || 'Детали') : details.material.name}
                        </h2>
                        {!loading && details?.material?.code && (
                            <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--muted)' }}>{details.material.code}</span>
                        )}
                    </div>
                    <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)', padding: 4, flexShrink: 0 }}>
                        <X size={18} />
                    </button>
                </div>

                {/* Body */}
                <div style={{ overflowY: 'auto', padding: '20px 24px 24px', flex: 1 }}>
                    {loading ? (
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 240, color: 'var(--muted)' }}>
                            <Loader2 size={20} className="animate-spin" />
                        </div>
                    ) : !details ? (
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 120, fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--muted)' }}>
                            Нет данных
                        </div>
                    ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
                            {/* Stats */}
                            <div>
                                <SectionLabel>Статистика</SectionLabel>
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
                                    <StatCard title="Получено" value={`${fmt(details.statistics.total_quantity)} ${uom}`} />
                                    <StatCard title="Приёмок" value={fmt(details.statistics.total_supplies)} />
                                    <StatCard title="Общая сумма" value={`${fmt(details.statistics.total_sum)} ₽`} />
                                </div>
                            </div>

                            {/* Chart */}
                            {chartData.length > 0 && (
                                <div>
                                    <SectionLabel>Динамика поставок по месяцам</SectionLabel>
                                    <div style={{ height: 240 }}>
                                        <ResponsiveContainer width="100%" height="100%">
                                            <LineChart data={chartData} margin={{ top: 4, right: 48, left: 0, bottom: 0 }}>
                                                <CartesianGrid strokeDasharray="3 3" stroke="var(--hairline)" />
                                                <XAxis dataKey="month" tick={{ fontFamily: 'var(--sans)', fontSize: 11, fill: 'var(--muted)' }} />
                                                <YAxis yAxisId="qty" tick={{ fontFamily: 'var(--sans)', fontSize: 11, fill: 'var(--muted)' }} tickFormatter={fmt} width={50} />
                                                <YAxis yAxisId="price" orientation="right" tick={{ fontFamily: 'var(--sans)', fontSize: 11, fill: 'var(--muted)' }} tickFormatter={v => `${v.toFixed(0)}₽`} width={44} />
                                                <Tooltip content={<ChartTooltip uom={uom} />} />
                                                <Line {...CHART_ANIMATION} yAxisId="qty" type="monotone" dataKey="quantity" name="quantity" stroke="var(--primary)" strokeWidth={2} dot={{ r: 3, fill: 'var(--primary)' }} activeDot={{ r: 5 }} />
                                                <Line {...CHART_ANIMATION} yAxisId="price" type="monotone" dataKey="price" name="price" stroke="#5a8a6a" strokeWidth={2} dot={{ r: 3, fill: '#5a8a6a' }} activeDot={{ r: 5 }} />
                                            </LineChart>
                                        </ResponsiveContainer>
                                    </div>
                                </div>
                            )}

                            {/* Supply history */}
                            <div>
                                <SectionLabel>История приёмок</SectionLabel>
                                <div style={{ maxHeight: 400, overflowY: 'auto' }}>
                                    {details.supply_history?.map((s, i) => (
                                        <SupplyRow key={`${s.number}-${i}`} supply={s} uom={uom} />
                                    ))}
                                    {!details.supply_history?.length && (
                                        <span style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)' }}>Нет истории</span>
                                    )}
                                </div>
                            </div>
                        </div>
                    )}
                </div>
        </ModalShell>
    );
};

MaterialSupplyDetailsModal.propTypes = {
    material: PropTypes.shape({ id: PropTypes.number, name: PropTypes.string, code: PropTypes.string }),
    visible: PropTypes.bool.isRequired,
    onClose: PropTypes.func.isRequired,
    dateRange: PropTypes.shape({ startDate: PropTypes.string, endDate: PropTypes.string }),
};

export default MaterialSupplyDetailsModal;
