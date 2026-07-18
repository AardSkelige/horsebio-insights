import { useState, useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import { seasonalAnalysisApi } from '../../api/seasonalAnalysis';
import { SeasonalFilters } from './SeasonalFilters';
import { SeasonalPatterns } from './SeasonalPatterns';
import { SeasonalStatistics } from './SeasonalStatistics';
import { SeasonalCharts } from './SeasonalCharts';
import SeasonalProductDetails from './SeasonalProductDetails';
import { FadeRise } from '../ui/motion';
import { Skeleton } from '../ui/Skeleton';

const sectionCard = { backgroundColor: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: '10px', padding: '24px' };
const sectionHeading = { fontFamily: 'var(--serif)', fontSize: '22px', fontWeight: 400, letterSpacing: '-0.02em', color: 'var(--ink)', margin: '0 0 16px' };
const labelStyle = { fontFamily: 'var(--sans)', fontSize: '11px', fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: '12px' };

export const SeasonalAnalysis = () => {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [data, setData] = useState(null);
    const [selectedProduct, setSelectedProduct] = useState(null);
    const [detailsLoading, setDetailsLoading] = useState(false);
    const [filters, setFilters] = useState({ category: 'A', periodMonths: 12, endDate: null });
    const statsRef = useRef(null);

    useEffect(() => {
        const load = async () => {
            setLoading(true);
            setError(null);
            try {
                const res = await seasonalAnalysisApi.getAnalysis(filters);
                if (!res) throw new Error('Нет ответа от сервера');
                if (res.status === 'success' && res.data) setData(res.data);
                else throw new Error(res.message || 'Ошибка получения данных');
            } catch (err) {
                setError(err.message || 'Ошибка загрузки данных');
                setData(null);
            } finally {
                setLoading(false);
            }
        };
        load();
    }, [filters]);

    // Детали грузим отдельным флагом: общий loading размонтирует всю страницу,
    // и выбор продукта выглядел как «ничего не произошло»
    const handleProductSelect = async (product) => {
        if (!product?.id) return;
        setDetailsLoading(true);
        setError(null);
        statsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        try {
            const res = await seasonalAnalysisApi.getProductDetails(product.id, filters);
            if (!res) throw new Error('Нет ответа от сервера');
            if (res.status === 'success' && res.data) {
                const d = res.data;
                if (!d.monthly_sales || !d.seasonal_factors) throw new Error('Неполные данные продукта');
                setSelectedProduct({
                    ...d,
                    monthly_sales: Object.fromEntries(Object.entries(d.monthly_sales).map(([k, v]) => [k, Number(v)])),
                    seasonal_factors: Object.fromEntries(Object.entries(d.seasonal_factors).map(([k, v]) => [k, Number(v)])),
                });
            } else {
                throw new Error(res.message || 'Ошибка загрузки данных продукта');
            }
        } catch {
            setError('Ошибка загрузки данных продукта');
            setSelectedProduct(null);
        } finally {
            setDetailsLoading(false);
        }
    };

    const handleFiltersChange = (f) => { setError(null); setSelectedProduct(null); setFilters(f); };

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', color: 'var(--ink)' }}>
            {/* Header */}
            <div style={{ borderBottom: '1px solid var(--hairline)', paddingBottom: '16px' }}>
                <h1 style={{ fontFamily: 'var(--serif)', fontSize: '32px', fontWeight: 400, letterSpacing: '-0.025em', lineHeight: 1.1, color: 'var(--ink)', margin: '0 0 4px' }}>
                    Анализ сезонности
                </h1>
                <p style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--muted)', margin: 0 }}>
                    Сезонные паттерны продаж для оптимизации запасов и планирования производства
                </p>
            </div>

            {/* Filters */}
            <FadeRise style={{ ...sectionCard, backgroundColor: 'var(--surface-soft)' }}>
                <div style={labelStyle}>Параметры анализа</div>
                <SeasonalFilters value={filters} onChange={handleFiltersChange} />
            </FadeRise>

            {/* Первая загрузка — скелетон страницы */}
            {loading && !data && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }} aria-busy="true">
                    <Skeleton height={420} style={{ borderRadius: 10 }} />
                    <Skeleton height={180} style={{ borderRadius: 10 }} />
                </div>
            )}

            {/* Error */}
            {error && !loading && (
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', padding: '12px 16px', backgroundColor: 'rgba(198,69,69,0.08)', border: '1px solid rgba(198,69,69,0.3)', borderRadius: '8px', fontFamily: 'var(--sans)', fontSize: '13px', color: '#c64545' }}>
                    <span style={{ flex: 1 }}><b>Ошибка загрузки данных:</b> {error}</span>
                    <button onClick={() => setError(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#c64545', padding: 0, flexShrink: 0 }}>
                        <X style={{ width: 14, height: 14 }} />
                    </button>
                </div>
            )}

            {/* Content: при перезагрузке фильтров не размонтируем, а приглушаем */}
            {data && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', opacity: loading ? 0.45 : 1, pointerEvents: loading ? 'none' : 'auto', transition: 'opacity 200ms ease' }}>
                    <FadeRise style={sectionCard}>
                        <h2 style={sectionHeading}>Сезонные паттерны</h2>
                        <SeasonalPatterns data={data} onProductSelect={handleProductSelect} loading={loading} />
                    </FadeRise>

                    <div ref={statsRef} style={{ scrollMarginTop: 16 }}>
                        <FadeRise delay={0.05} style={sectionCard}>
                            <h2 style={sectionHeading}>Статистика сезонности</h2>
                            <SeasonalStatistics data={selectedProduct} loading={detailsLoading} />
                        </FadeRise>
                    </div>

                    {selectedProduct && (
                        <>
                            <FadeRise style={sectionCard}>
                                <h2 style={sectionHeading}>Детальный анализ</h2>
                                <SeasonalCharts data={selectedProduct} loading={loading} />
                            </FadeRise>

                            <FadeRise delay={0.05} style={sectionCard}>
                                <h2 style={sectionHeading}>Подробная информация о продукте</h2>
                                <SeasonalProductDetails data={selectedProduct} loading={loading} error={error} />
                            </FadeRise>
                        </>
                    )}
                </div>
            )}
        </div>
    );
};

export default SeasonalAnalysis;
