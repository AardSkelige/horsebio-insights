import PropTypes from 'prop-types';
import { Target } from 'lucide-react';

const fmt = (n) => Number(n || 0).toLocaleString('ru', { maximumFractionDigits: 0 });

/**
 * Выбирает поставщика для итоговой рекомендации.
 * Приоритет — тем, у кого есть валидный оптимальный размер партии (ненулевая цена);
 * среди них максимальная надёжность, при равенстве — меньший срок поставки.
 * Экспортируется отдельно для юнит-тестов.
 */
export const pickRecommendedSupplier = (recommendations = []) => {
    if (!recommendations.length) return null;
    const withBatch = recommendations.filter(r => (r.optimal_batch || 0) > 0);
    const pool = withBatch.length ? withBatch : recommendations;
    return [...pool].sort((a, b) =>
        (b.reliability || 0) - (a.reliability || 0) ||
        (a.lead_time || 0) - (b.lead_time || 0)
    )[0];
};

const PurchaseVerdict = ({ analysisData, material }) => {
    const calc = analysisData?.general_calculations || {};
    const reorder = calc.reorder_point?.value || 0;
    if (!reorder) return null; // нет данных — вердикт не показываем

    const uom = material?.uom || '';
    const supplier = pickRecommendedSupplier(analysisData?.recommendations);
    const optimal = supplier?.optimal_batch || calc.optimal_order_quantity?.value || 0;

    return (
        <div style={{ backgroundColor: 'rgba(204,120,92,0.06)', border: '1px solid rgba(204,120,92,0.3)', borderRadius: '10px', padding: '20px 24px', display: 'flex', gap: '16px', alignItems: 'flex-start' }}>
            <div style={{ flexShrink: 0, width: 36, height: 36, borderRadius: '50%', backgroundColor: 'rgba(204,120,92,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Target style={{ width: 18, height: 18, color: 'var(--primary)' }} />
            </div>
            <div>
                <div style={{ fontFamily: 'var(--sans)', fontSize: '11px', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--primary)', marginBottom: '6px' }}>Рекомендация</div>
                <p style={{ fontFamily: 'var(--serif)', fontSize: '18px', color: 'var(--ink)', margin: 0, lineHeight: 1.45, fontVariantNumeric: 'lining-nums', fontFeatureSettings: '"lnum" 1' }}>
                    Заказывайте, когда остаток упадёт до <b>{fmt(reorder)} {uom}</b>.
                    {supplier ? (
                        <>
                            {' '}Выгоднее — <b>{supplier.supplier_name}</b>
                            {supplier.reliability ? `: надёжность ${(supplier.reliability * 100).toFixed(0)}%` : ''}
                            {optimal > 0 ? <>, партия <b>{fmt(optimal)} {uom}</b></> : null}.
                        </>
                    ) : optimal > 0 ? (
                        <>{' '}Оптимальная партия — <b>{fmt(optimal)} {uom}</b>.</>
                    ) : null}
                </p>
            </div>
        </div>
    );
};

PurchaseVerdict.propTypes = {
    analysisData: PropTypes.object,
    material: PropTypes.shape({ uom: PropTypes.string }),
};

export default PurchaseVerdict;
