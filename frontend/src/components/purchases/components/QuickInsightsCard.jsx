import { useState } from 'react';
import PropTypes from 'prop-types';
import { Hint, Notice, StatCard, StatGrid } from '../../ui';
import { analysisApi } from '../../../api/analysisApi';
import { num } from '../../../utils/formatters';
import './QuickInsightsCard.css';


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
    const monthlyOrder = periodicOrders?.frequent_orders?.order_size || 0;
    const quarterlyOrder = periodicOrders?.quarterly_orders?.order_size || 0;

    const basicCalcs = calculations?.basic_calculations || {};
    const trendDetected = basicCalcs?.trend_detected || false;
    const yearlyAvg = basicCalcs?.yearly_avg || 0;
    const recentAvg = basicCalcs?.recent_avg || 0;
    const growthRatio = basicCalcs?.growth_ratio || 0;
    const workingDaysPerMonth = basicCalcs?.working_days_per_month || 0;

    const showNotice = (type, text) => {
        setNotice({ type, text });
        setTimeout(() => setNotice(null), 3000);
    };

    const patchPeriod = async (value) => {
        setSaving(true);
        try {
            const data = await analysisApi.purchase.patchPeriod(material.id, value);
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
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--muted)' }}>Период расчёта <Hint text="За какой срок брать расход и сроки поставок. Выбор личный: у коллег остаётся их период." /></span>
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
                    {yearlyAvg > 0 && recentAvg > 0 && workingDaysPerMonth > 0 && (
                        <span style={{ color: 'var(--muted)', marginLeft: 8 }}>
                            За {periodMonths} мес: {(yearlyAvg * workingDaysPerMonth).toFixed(0)} {material.uom}/мес → Сейчас: {(recentAvg * workingDaysPerMonth).toFixed(0)} {material.uom}/мес
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

            <div className="purchase-kpis">
                <StatGrid>
                    <StatCard title="Расход в день" value={dailyConsumption} format={num} suffix={material.uom} note={trendDetected ? 'Пн–пт, за 3 мес' : `Пн–пт, среднее за ${periodMonths} мес`} hint="Сколько уходит в производство за рабочий день: отгрузки товаров × нормы из техкарт, без суббот, воскресений и праздников." />
                    <StatCard title="Срок поставки" value={leadTime.received ? leadTime.avg : '—'} format={num} suffix={leadTime.received ? 'дн.' : undefined} note={leadTime.received ? `мин ${leadTime.min} · макс ${leadTime.max}` : 'Нет принятых поставок'} hint="Календарных дней от заказа поставщику до приёмки. Учитываются только принятые заказы за период." />
                    <StatCard title="Точка заказа" value={reorderPoint} format={num} suffix={material.uom} note="Доставка + запас" hint="Остаток, при котором пора заказывать: расход за среднее время поставки плюс страховой запас на случай задержки (не меньше недели расхода)." />
                    <StatCard title="Партия EOQ" value={optimalOrder} format={num} suffix={material.uom} note="Оптимальная, справочно" hint="Партия, при которой суммарные затраты на заказы и хранение минимальны. Ориентир, а не правило." />
                    <StatCard title="Заказ на месяц" value={monthlyOrder} format={num} suffix={material.uom} note="Расход за месяц" hint="Потребление в рабочий день × среднее число рабочих дней в месяце. Страховой запас сюда не входит, он заложен в точку заказа." />
                    <StatCard title="Заказ на квартал" value={quarterlyOrder} format={num} suffix={material.uom} note="Расход за квартал" hint="Месячный расход × 3. Страховой запас сюда не входит, он заложен в точку заказа." />
                </StatGrid>
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
