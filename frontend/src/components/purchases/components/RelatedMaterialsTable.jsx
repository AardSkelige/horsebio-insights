import { useState, useMemo, useCallback } from 'react';
import PropTypes from 'prop-types';
import { ChevronDown, ChevronUp } from 'lucide-react';

const FreqBadge = ({ value = 0 }) => {
    const color = value >= 50 ? '#059669' : value >= 25 ? '#5c8acc' : value >= 10 ? '#a07010' : 'var(--muted)';
    const bg = value >= 50 ? 'rgba(5,150,105,0.1)' : value >= 25 ? 'rgba(92,138,204,0.1)' : value >= 10 ? 'rgba(160,112,16,0.1)' : 'var(--surface-card)';
    return (
        <span style={{ display: 'inline-block', padding: '2px 8px', borderRadius: '20px', fontSize: '11px', fontWeight: 600, fontFamily: 'var(--sans)', backgroundColor: bg, color }}>
            {value.toFixed(1)}%
        </span>
    );
};

const thStyle = {
    fontFamily: 'var(--sans)', fontSize: '11px', fontWeight: 600,
    letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--muted)',
    padding: '8px 12px', textAlign: 'left', borderBottom: '1px solid var(--hairline)',
};
const tdStyle = {
    fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--body)',
    padding: '10px 12px', borderBottom: '1px solid var(--hairline-soft)',
    verticalAlign: 'top',
};

FreqBadge.propTypes = { value: PropTypes.number };

const SupplierBlock = ({ supplier, data }) => (
    <div style={{ marginBottom: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span style={{ fontFamily: 'var(--sans)', fontSize: '14px', fontWeight: 600, color: 'var(--ink)' }}>{supplier}</span>
            <span style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--muted)' }}>Всего заказов: {data.total_orders || 0}</span>
        </div>

        {!data.related?.length ? (
            <div style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--muted)' }}>Нет данных о совместных заказах</div>
        ) : (
            <>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr>
                            <th style={{ ...thStyle, width: '35%' }}>Материал</th>
                            <th style={thStyle}>Частота</th>
                            <th style={thStyle}>Совм. заказов</th>
                            <th style={thStyle}>Среднее кол-во</th>
                        </tr>
                    </thead>
                    <tbody>
                        {data.related.map((r, i) => (
                            <tr key={`${r.code}-${i}`}>
                                <td style={tdStyle}>
                                    <div style={{ fontWeight: 500, color: 'var(--ink)' }}>{r.name}</div>
                                    <div style={{ fontSize: '12px', color: 'var(--muted)' }}>Код: {r.code}</div>
                                </td>
                                <td style={tdStyle}><FreqBadge value={r.frequency || 0} /></td>
                                <td style={tdStyle}>{r.total_joint_orders}</td>
                                <td style={tdStyle}>{(r.avg_quantity || 0).toLocaleString('ru')} {r.uom}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
                {data.skipped?.length > 0 && (
                    <div style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--muted)', marginTop: '8px' }}>
                        Также есть {data.skipped.length} материалов с более редкими совместными заказами
                    </div>
                )}
            </>
        )}
    </div>
);

SupplierBlock.propTypes = {
    supplier: PropTypes.string.isRequired,
    data: PropTypes.shape({ total_orders: PropTypes.number, related: PropTypes.array, skipped: PropTypes.array }).isRequired,
};

const RelatedMaterialsTable = ({ relatedData, suppliers, activityThreshold, showInactive }) => {
    const [open, setOpen] = useState(false);

    const isSupplierActive = useCallback((supplierName) => {
        if (showInactive || !suppliers) return true;
        const s = Object.values(suppliers).find(s => s.supplier_name === supplierName);
        if (!s) return true;
        const lastOrderDate = s.orders?.[0]?.date ? new Date(s.orders[0].date) : new Date(0);
        const threshold = new Date();
        threshold.setMonth(threshold.getMonth() - activityThreshold);
        return lastOrderDate > threshold;
    }, [suppliers, activityThreshold, showInactive]);

    const filteredEntries = useMemo(() => {
        if (!relatedData?.supplier_materials) return [];
        return Object.entries(relatedData.supplier_materials).filter(([name]) => isSupplierActive(name));
    }, [relatedData?.supplier_materials, isSupplierActive]);

    const hiddenCount = useMemo(() => {
        if (!relatedData?.supplier_materials) return 0;
        return Object.keys(relatedData.supplier_materials).length - filteredEntries.length;
    }, [relatedData?.supplier_materials, filteredEntries.length]);

    if (!relatedData?.supplier_materials) return null;

    return (
        <div style={{ backgroundColor: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: '10px' }}>
            <button
                onClick={() => setOpen(o => !o)}
                style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 20px', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left' }}
            >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span style={{ fontFamily: 'var(--serif)', fontSize: '18px', fontWeight: 400, color: 'var(--ink)' }}>Связанные материалы</span>
                    {hiddenCount > 0 && (
                        <span style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--muted)' }}>Скрыто неактивных: {hiddenCount}</span>
                    )}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', flexShrink: 0 }}>
                    {open ? <ChevronUp style={{ width: 16, height: 16, color: 'var(--muted)', flexShrink: 0 }} /> : <ChevronDown style={{ width: 16, height: 16, color: 'var(--muted)', flexShrink: 0 }} />}
                </div>
            </button>

            {open && (
                <div style={{ padding: '0 20px 20px' }}>
                    <div style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--muted)', backgroundColor: 'var(--surface-soft)', padding: '10px 14px', borderRadius: '8px', marginBottom: '20px' }}>
                        Анализ основан на {relatedData.total_orders || 0} заказах. Материалы с частотой совместных заказов менее 5% не показываются в основной таблице.
                    </div>
                    {filteredEntries.map(([supplier, data]) => (
                        <SupplierBlock key={supplier} supplier={supplier} data={data} />
                    ))}
                    {filteredEntries.length === 0 && (
                        <div style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--muted)', textAlign: 'center', padding: '24px' }}>
                            Нет данных по активным поставщикам
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

RelatedMaterialsTable.propTypes = {
    relatedData: PropTypes.shape({ supplier_materials: PropTypes.object, total_orders: PropTypes.number }),
    suppliers: PropTypes.object,
    activityThreshold: PropTypes.number,
    showInactive: PropTypes.bool,
};

export default RelatedMaterialsTable;
