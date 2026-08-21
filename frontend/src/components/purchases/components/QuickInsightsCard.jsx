import { useState } from 'react';
import PropTypes from 'prop-types';
import { Notice, StatCard, StatGrid } from '../../ui';
import { materialsApi } from '../../../api/materialsApi';


const selectStyle = {
    height: '32px', padding: '0 8px',
    fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--ink)',
    backgroundColor: 'var(--canvas)', border: '1px solid var(--hairline)',
    borderRadius: '6px', outline: 'none', cursor: 'pointer',
};

const QuickInsightsCard = ({ analysisData, material, onPeriodChange }) => {
    const [saving, setSaving] = useState(false);
    const [notice, setNotice] = useState(null);

    if (!analysisData || !material) return null;

    const periodMonths = analysisData.period_months || 12;
    const periodIsCustom = analysisData.period_is_custom || false;
    const ordersCount = analysisData.orders_count ?? 0;
    const calculations = analysisData.general_calculations || {};

    const consumptionMatch = (calculations?.reorder_point?.details || '').match(/Общее среднее потребление в день \(([0-9.]+)\)/);
    const dailyConsumption = consumptionMatch ? parseFloat(consumptionMatch[1]) : 0;

    const leadTime = calculations?.lead_time || {};
    const reorderPoint = calculations?.reorder_point?.value || 0;
    const optimalOrder = calculations?.optimal_order_quantity?.value || 0;
    const periodicOrders = calculations?.periodic_orders || {};
    const monthlyOrder = periodicOrders?.frequent_orders?.total_size || 0;
    const quarterlyOrder = periodicOrders?.quarterly_orders?.total_size || 0;

    const basicCalcs = calculations?.basic_calculations || {};
    const trendDetected = basicCalcs?.trend_detected || false;
    const yearlyAvg = basicCalcs?.yearly_avg || 0;
    const recentAvg = basicCalcs?.recent_avg || 0;
    const growthRatio = basicCalcs?.growth_ratio || 0;

    const showNotice = (type, text) => {
        setNotice({ type, text });
        setTimeout(() => setNotice(null), 3000);
    };

    const patchPeriod = async (value) => {
        setSaving(true);
        try {
            const data = await materialsApi.patchPeriod(material.id, value);
            if (data.status === 'success') { showNotice('success', value ? 'Период сохранён' : 'Сброшено к 12 мес'); onPeriodChange?.(); }
            else showNotice('error', data.message || 'Ошибка');
        } catch { showNotice('error', 'Ошибка сохранения'); }
        finally { setSaving(false); }
    };

    return (
        <div style={{ backgroundColor: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: '10px', padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
                <h2 style={{ fontFamily: 'var(--serif)', fontSize: '22px', fontWeight: 400, letterSpacing: '-0.02em', color: 'var(--ink)', margin: 0 }}>Ключевые показатели</h2>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--muted)' }}>Период расчёта:</span>
                    <select
                        value={periodMonths}
                        onChange={e => patchPeriod(Number(e.target.value))}
                        disabled={saving}
                        style={selectStyle}
                    >
                        <option value={3}>3 мес</option>
                        <option value={6}>6 мес</option>
                        <option value={12}>12 мес</option>
                    </select>
                    {periodIsCustom && (
                        <button
                            onClick={() => patchPeriod(null)}
                            disabled={saving}
                            style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--primary)', background: 'none', border: 'none', cursor: 'pointer', padding: '0 4px', textDecoration: 'underline' }}
                        >
                            Сбросить
                        </button>
                    )}
                </div>
            </div>

            {trendDetected && (
                <div style={{ padding: '10px 14px', backgroundColor: 'var(--accent-bg)', border: '1px solid var(--accent-border)', borderRadius: '8px', fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--primary)' }}>
                    Рост спроса{growthRatio ? ` (${growthRatio.toFixed(1)}×)` : ''} — расчёт по последним 3 месяцам
                    {yearlyAvg > 0 && recentAvg > 0 && (
                        <span style={{ color: 'var(--muted)', marginLeft: 8 }}>
                            Год: {(yearlyAvg * 30).toFixed(0)} {material.uom}/мес → Сейчас: {(recentAvg * 30).toFixed(0)} {material.uom}/мес
                        </span>
                    )}
                </div>
            )}

            {ordersCount === 0 && (
                <div style={{ padding: '10px 14px', backgroundColor: 'var(--warning-bg)', border: '1px solid var(--warning-border)', borderRadius: '8px', fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--warning-ink)' }}>
                    За выбранный период ({periodMonths} мес) нет заказов — расчёт времени доставки невозможен.
                    {periodIsCustom && (
                        <button onClick={() => patchPeriod(null)} style={{ marginLeft: 8, background: 'none', border: 'none', cursor: 'pointer', color: 'var(--warning-ink)', textDecoration: 'underline', fontSize: '13px', fontFamily: 'var(--sans)' }}>
                            Сбросить к 12 мес
                        </button>
                    )}
                </div>
            )}

            {notice && (
                <Notice tone={notice.type}>{notice.text}</Notice>
            )}

            <StatGrid>
                <StatCard tone="dark" title="Потребление в день" value={dailyConsumption} suffix={material.uom} />
                <StatCard tone="dark" title="Среднее время поставки" value={leadTime.avg || 0} suffix="дней" note={`мин ${leadTime.min || 0} · макс ${leadTime.max || 0}`} />
                <StatCard tone="dark" title="Точка заказа" value={reorderPoint} suffix={material.uom} note="Сделайте заказ при этом остатке" />
                <StatCard tone="dark" title="Оптимальный размер (EOQ)" value={optimalOrder} suffix={material.uom} note="Справочно" />
                <StatCard tone="dark" title="Ежемесячный заказ" value={monthlyOrder} suffix={material.uom} note="Минимум на 30 дней" />
                <StatCard tone="dark" title="Квартальный заказ" value={quarterlyOrder} suffix={material.uom} note="Минимум на 90 дней" />
            </StatGrid>
        </div>
    );
};

QuickInsightsCard.propTypes = {
    analysisData: PropTypes.object,
    material: PropTypes.shape({ id: PropTypes.number.isRequired, uom: PropTypes.string }),
    onPeriodChange: PropTypes.func,
};

export default QuickInsightsCard;
