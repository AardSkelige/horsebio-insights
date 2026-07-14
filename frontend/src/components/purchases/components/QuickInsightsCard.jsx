import { useState } from 'react';
import PropTypes from 'prop-types';
import { materialsApi } from '../../../api/materialsApi';

const StatCard = ({ label, value, suffix, hint, accent }) => (
    <div style={{ backgroundColor: 'var(--surface-dark)', borderRadius: '10px', padding: '20px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
        <div style={{ fontFamily: 'var(--sans)', fontSize: '11px', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: accent || 'var(--on-dark-soft)' }}>{label}</div>
        <div style={{ fontFamily: 'var(--serif)', fontSize: '26px', fontWeight: 400, color: 'var(--on-dark)', lineHeight: 1, fontVariantNumeric: 'lining-nums', fontFeatureSettings: '"lnum" 1' }}>
            {typeof value === 'number' ? value.toLocaleString('ru', { maximumFractionDigits: 2 }) : value}
            {suffix && <span style={{ fontFamily: 'var(--sans)', fontSize: '13px', fontWeight: 400, marginLeft: '5px', color: 'var(--on-dark-soft)' }}>{suffix}</span>}
        </div>
        {hint && <div style={{ fontFamily: 'var(--sans)', fontSize: '11px', color: 'var(--on-dark-soft)' }}>{hint}</div>}
    </div>
);

StatCard.propTypes = {
    label: PropTypes.string.isRequired,
    value: PropTypes.oneOfType([PropTypes.number, PropTypes.string]),
    suffix: PropTypes.string,
    hint: PropTypes.string,
    accent: PropTypes.string,
};

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

    const noticeColors = { success: '#059669', error: '#c64545' };
    const noticeBgs = { success: 'rgba(5,150,105,0.08)', error: 'rgba(198,69,69,0.08)' };

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
                <div style={{ padding: '10px 14px', backgroundColor: 'rgba(204,120,92,0.08)', border: '1px solid rgba(204,120,92,0.3)', borderRadius: '8px', fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--primary)' }}>
                    Рост спроса{growthRatio ? ` (${growthRatio.toFixed(1)}×)` : ''} — расчёт по последним 3 месяцам
                    {yearlyAvg > 0 && recentAvg > 0 && (
                        <span style={{ color: 'var(--muted)', marginLeft: 8 }}>
                            Год: {(yearlyAvg * 30).toFixed(0)} {material.uom}/мес → Сейчас: {(recentAvg * 30).toFixed(0)} {material.uom}/мес
                        </span>
                    )}
                </div>
            )}

            {ordersCount === 0 && (
                <div style={{ padding: '10px 14px', backgroundColor: 'rgba(212,160,23,0.08)', border: '1px solid rgba(212,160,23,0.3)', borderRadius: '8px', fontFamily: 'var(--sans)', fontSize: '13px', color: '#a07010' }}>
                    За выбранный период ({periodMonths} мес) нет заказов — расчёт времени доставки невозможен.
                    {periodIsCustom && (
                        <button onClick={() => patchPeriod(null)} style={{ marginLeft: 8, background: 'none', border: 'none', cursor: 'pointer', color: '#a07010', textDecoration: 'underline', fontSize: '13px', fontFamily: 'var(--sans)' }}>
                            Сбросить к 12 мес
                        </button>
                    )}
                </div>
            )}

            {notice && (
                <div style={{ padding: '8px 12px', borderRadius: '8px', fontFamily: 'var(--sans)', fontSize: '12px', color: noticeColors[notice.type], backgroundColor: noticeBgs[notice.type], border: `1px solid ${noticeColors[notice.type]}40` }}>
                    {notice.text}
                </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '12px' }}>
                <StatCard label="Потребление в день" value={dailyConsumption} suffix={material.uom} />
                <StatCard label="Среднее время поставки" value={leadTime.avg || 0} suffix="дней" hint={`мин ${leadTime.min || 0} · макс ${leadTime.max || 0}`} accent="var(--primary)" />
                <StatCard label="Точка заказа" value={reorderPoint} suffix={material.uom} hint="Сделайте заказ при этом остатке" />
                <StatCard label="Оптимальный размер (EOQ)" value={optimalOrder} suffix={material.uom} hint="Справочно" />
                <StatCard label="Ежемесячный заказ" value={monthlyOrder} suffix={material.uom} hint="Минимум на 30 дней" />
                <StatCard label="Квартальный заказ" value={quarterlyOrder} suffix={material.uom} hint="Минимум на 90 дней" />
            </div>
        </div>
    );
};

QuickInsightsCard.propTypes = {
    analysisData: PropTypes.object,
    material: PropTypes.shape({ id: PropTypes.number.isRequired, uom: PropTypes.string }),
    onPeriodChange: PropTypes.func,
};

export default QuickInsightsCard;
