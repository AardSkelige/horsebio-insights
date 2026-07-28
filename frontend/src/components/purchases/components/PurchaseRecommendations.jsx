import { useState, useMemo, useCallback } from 'react';
import PropTypes from 'prop-types';
import { ChevronDown, ChevronUp, ChevronRight } from 'lucide-react';

const CollapsibleSection = ({ title, hint, defaultOpen = false, children, badge }) => {
    const [open, setOpen] = useState(defaultOpen);
    return (
        <div style={{ backgroundColor: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: '10px' }}>
            <button
                onClick={() => setOpen(o => !o)}
                className="no-tap-scale"
                style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 20px', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left' }}
            >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span style={{ fontFamily: 'var(--serif)', fontSize: '18px', fontWeight: 400, color: 'var(--ink)' }}>{title}</span>
                    {badge && <span style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--muted)' }}>{badge}</span>}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
                    {!open && hint && <span style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--muted)' }}>{hint}</span>}
                    {open ? <ChevronUp style={{ width: 16, height: 16, color: 'var(--muted)', flexShrink: 0 }} /> : <ChevronDown style={{ width: 16, height: 16, color: 'var(--muted)', flexShrink: 0 }} />}
                </div>
            </button>
            {open && <div style={{ padding: '0 20px 20px' }}>{children}</div>}
        </div>
    );
};

CollapsibleSection.propTypes = {
    title: PropTypes.string.isRequired,
    hint: PropTypes.string,
    defaultOpen: PropTypes.bool,
    children: PropTypes.node,
    badge: PropTypes.string,
};

const sectionStyle = { marginBottom: '16px' };
const blockTitleStyle = { fontFamily: 'var(--sans)', fontSize: '12px', fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: '6px' };
const blockBodyStyle = { fontFamily: 'var(--mono)', fontSize: '12px', color: 'var(--body)', backgroundColor: 'var(--surface-soft)', padding: '12px', borderRadius: '8px', whiteSpace: 'pre-line', lineHeight: 1.6 };

const DetailBlock = ({ title, content }) => content ? (
    <div style={sectionStyle}>
        <div style={blockTitleStyle}>{title}</div>
        <div style={blockBodyStyle}>{content}</div>
    </div>
) : null;

DetailBlock.propTypes = { title: PropTypes.string.isRequired, content: PropTypes.string };

const fmt = (n) => Number(n || 0).toLocaleString('ru', { maximumFractionDigits: 0 });

const SummaryPill = ({ label, value, uom, accent, note }) => (
    <div style={{ backgroundColor: 'var(--surface-soft)', borderRadius: '8px', padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
        <div style={{ fontFamily: 'var(--sans)', fontSize: '11px', fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: accent || 'var(--muted)' }}>{label}</div>
        <div style={{ fontFamily: 'var(--serif)', fontSize: '20px', color: 'var(--ink)', lineHeight: 1, fontVariantNumeric: 'lining-nums', fontFeatureSettings: '"lnum" 1' }}>
            {value}
            {uom && value !== '—' && <span style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--muted)', marginLeft: '4px' }}>{uom}</span>}
        </div>
        {note && <div style={{ fontFamily: 'var(--sans)', fontSize: '11px', color: 'var(--muted)' }}>{note}</div>}
    </div>
);

SummaryPill.propTypes = { label: PropTypes.string.isRequired, value: PropTypes.oneOfType([PropTypes.string, PropTypes.number]), uom: PropTypes.string, accent: PropTypes.string, note: PropTypes.string };

const DetailedCalculations = ({ details, uom }) => {
    const [showMath, setShowMath] = useState(false);
    if (!details || !details.reorder_point) {
        return <div style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--muted)' }}>Нет детальных расчётов</div>;
    }

    const reorder = details.reorder_point?.value || 0;
    const optimal = details.optimal_order_quantity?.value || 0;
    const optimalMissing = optimal <= 0;
    const safety = details.safety_stock?.value || 0;
    const leadAvg = details.lead_time?.avg || 0;
    const monthly = details.periodic_orders?.frequent_orders?.total_size || 0;
    const quarterly = details.periodic_orders?.quarterly_orders?.total_size || 0;

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '4px' }}>
            {/* Суть простым языком */}
            <p style={{ fontFamily: 'var(--sans)', fontSize: '14px', color: 'var(--body)', margin: 0, lineHeight: 1.5 }}>
                Заказывайте, когда остаток упадёт до <b style={{ color: 'var(--ink)' }}>{fmt(reorder)} {uom}</b>.
                {!optimalMissing && <> Оптимальная партия — <b style={{ color: 'var(--ink)' }}>{fmt(optimal)} {uom}</b>.</>}
            </p>

            {/* Ключевые числа */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '10px' }}>
                <SummaryPill label="Точка заказа" value={fmt(reorder)} uom={uom} accent="var(--primary)" note="когда делать заказ" />
                <SummaryPill label="Оптимальная партия" value={optimalMissing ? '—' : fmt(optimal)} uom={uom} note={optimalMissing ? 'нет данных о цене' : 'EOQ'} />
                <SummaryPill label="Страховой запас" value={fmt(safety)} uom={uom} note="буфер на задержки" />
                <SummaryPill label="Срок поставки" value={leadAvg.toFixed(1)} uom="дн." note="в среднем" />
            </div>

            {/* Периодичность */}
            {(monthly > 0 || quarterly > 0) && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '10px' }}>
                    {monthly > 0 && <SummaryPill label="Ежемесячно" value={fmt(monthly)} uom={uom} note="партия на 30 дней" />}
                    {quarterly > 0 && <SummaryPill label="Ежеквартально" value={fmt(quarterly)} uom={uom} note="партия на 90 дней" />}
                </div>
            )}

            {/* Расчёт по клику */}
            <div>
                <button
                    onClick={() => setShowMath(s => !s)}
                    style={{ display: 'flex', alignItems: 'center', gap: '4px', background: 'none', border: 'none', cursor: 'pointer', padding: 0, fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--muted)' }}
                >
                    {showMath ? <ChevronDown style={{ width: 14, height: 14 }} /> : <ChevronRight style={{ width: 14, height: 14 }} />}
                    {showMath ? 'Скрыть расчёт' : 'Показать расчёт'}
                </button>
                {showMath && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '10px' }}>
                        <DetailBlock title="Точка заказа" content={details.reorder_point?.details} />
                        <DetailBlock title="Оптимальный размер заказа" content={details.optimal_order_quantity?.details} />
                        {details.periodic_orders && (
                            <div style={sectionStyle}>
                                <div style={{ ...blockTitleStyle, marginBottom: '10px' }}>Варианты периодичности заказов</div>
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '12px' }}>
                                    {details.periodic_orders.frequent_orders && (
                                        <div>
                                            <div style={{ fontFamily: 'var(--sans)', fontSize: '12px', fontWeight: 600, color: 'var(--body)', marginBottom: '6px' }}>Ежемесячные поставки</div>
                                            <div style={blockBodyStyle}>{details.periodic_orders.frequent_orders.details}</div>
                                        </div>
                                    )}
                                    {details.periodic_orders.quarterly_orders && (
                                        <div>
                                            <div style={{ fontFamily: 'var(--sans)', fontSize: '12px', fontWeight: 600, color: 'var(--body)', marginBottom: '6px' }}>Квартальные поставки</div>
                                            <div style={blockBodyStyle}>{details.periodic_orders.quarterly_orders.details}</div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                        {details.safety_stock && (
                            <div style={{ ...sectionStyle, padding: '12px', backgroundColor: 'rgba(92,138,204,0.06)', borderRadius: '8px', border: '1px solid rgba(92,138,204,0.2)' }}>
                                <div style={{ ...blockTitleStyle, color: '#5c8acc' }}>Страховой запас</div>
                                <div style={{ ...blockBodyStyle, backgroundColor: 'transparent', padding: 0 }}>{details.safety_stock.details}</div>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};

DetailedCalculations.propTypes = { details: PropTypes.object, uom: PropTypes.string };

const thStyle = {
    fontFamily: 'var(--sans)', fontSize: '11px', fontWeight: 600,
    letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--muted)',
    padding: '10px 12px', textAlign: 'left', borderBottom: '1px solid var(--hairline)',
};
const tdStyle = {
    fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--body)',
    padding: '12px', borderBottom: '1px solid var(--hairline-soft)',
    verticalAlign: 'top',
};

const plural = (n, ...forms) => forms[n === 1 ? 0 : n >= 2 && n <= 4 ? 1 : 2];

const PurchaseRecommendations = ({ recommendations = [], material, generalCalculations, suppliers, activityThreshold, showInactive }) => {
    const [expandedRows, setExpandedRows] = useState(new Set());

    const toggleRow = (name) => {
        setExpandedRows(prev => {
            const next = new Set(prev);
            next.has(name) ? next.delete(name) : next.add(name);
            return next;
        });
    };

    const isSupplierActive = useCallback((supplierName) => {
        if (showInactive || !suppliers) return true;
        const s = Object.values(suppliers).find(s => s.supplier_name === supplierName);
        if (!s) return true;
        const lastOrderDate = s.orders?.[0]?.date ? new Date(s.orders[0].date) : new Date(0);
        const threshold = new Date();
        threshold.setMonth(threshold.getMonth() - activityThreshold);
        return lastOrderDate > threshold;
    }, [suppliers, activityThreshold, showInactive]);

    const filteredRecs = useMemo(() =>
        recommendations.filter(r => isSupplierActive(r.supplier_name)),
        [recommendations, isSupplierActive]
    );

    const hiddenCount = recommendations.length - filteredRecs.length;

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <CollapsibleSection title="Общие рекомендации по закупкам" hint="сколько и когда закупать">
                <DetailedCalculations details={generalCalculations} uom={material?.uom} />
            </CollapsibleSection>

            <CollapsibleSection
                title="Рекомендации по поставщикам"
                hint="нажмите чтобы развернуть"
                badge={hiddenCount > 0 ? `Скрыто неактивных: ${hiddenCount}` : undefined}
            >
                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr>
                                <th style={{ ...thStyle, width: '40px' }} />
                                <th style={{ ...thStyle, width: '20%' }}>Поставщик</th>
                                <th style={thStyle}>Надёжность</th>
                                <th style={thStyle}>Точка заказа</th>
                                <th style={thStyle}>Оптимальный размер</th>
                                <th style={thStyle}>Lead time</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredRecs.map(rec => {
                                const expanded = expandedRows.has(rec.supplier_name);
                                return [
                                    <tr key={rec.supplier_name}>
                                        <td style={{ ...tdStyle, padding: '8px' }}>
                                            <button
                                                onClick={() => toggleRow(rec.supplier_name)}
                                                style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '4px', color: 'var(--muted)', display: 'flex', alignItems: 'center' }}
                                            >
                                                {expanded ? <ChevronDown style={{ width: 14, height: 14 }} /> : <ChevronRight style={{ width: 14, height: 14 }} />}
                                            </button>
                                        </td>
                                        <td style={{ ...tdStyle, fontWeight: 500, color: 'var(--ink)' }}>{rec.supplier_name}</td>
                                        <td style={tdStyle}>
                                            <div>{rec.reliability ? `${(rec.reliability * 100).toFixed(0)}%` : '0%'}</div>
                                            {rec.orders_in_transit > 0 && (
                                                <div style={{ fontSize: '12px', color: 'var(--muted)' }}>
                                                    {rec.orders_in_transit} {plural(rec.orders_in_transit, 'заказ', 'заказа', 'заказов')} в пути
                                                </div>
                                            )}
                                        </td>
                                        <td style={tdStyle}>{(rec.reorder_point || 0).toLocaleString('ru')} {material?.uom || ''}</td>
                                        <td style={tdStyle}>{(rec.optimal_batch || 0).toLocaleString('ru')} {material?.uom || ''}</td>
                                        <td style={tdStyle}>{(rec.lead_time || 0).toFixed(1)} дней</td>
                                    </tr>,
                                    expanded && (
                                        <tr key={`${rec.supplier_name}-detail`}>
                                            <td colSpan={6} style={{ padding: '16px 20px', backgroundColor: 'var(--surface-soft)', borderBottom: '1px solid var(--hairline-soft)' }}>
                                                <DetailedCalculations details={rec.detailed_calculations} uom={material?.uom} />
                                            </td>
                                        </tr>
                                    )
                                ];
                            })}
                            {filteredRecs.length === 0 && (
                                <tr>
                                    <td colSpan={6} style={{ ...tdStyle, textAlign: 'center', color: 'var(--muted)', padding: '32px' }}>
                                        Нет активных поставщиков с рекомендациями
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </CollapsibleSection>
        </div>
    );
};

PurchaseRecommendations.propTypes = {
    recommendations: PropTypes.array,
    material: PropTypes.shape({ uom: PropTypes.string }),
    generalCalculations: PropTypes.object,
    suppliers: PropTypes.object,
    activityThreshold: PropTypes.number,
    showInactive: PropTypes.bool,
};

export default PurchaseRecommendations;
