import { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { Package, AlertCircle, RefreshCw, Download, Loader2 } from 'lucide-react';
import FBOTable from './FBOTable';
import FBOStatistics from './FBOStatistics';
import SectionLabel from '../ui/SectionLabel';
import FBOOrderDetails from './FBOOrderDetails';
import { analysisApi } from '../../api/analysisApi';

const STAGES = [
    [0,  20, 'Получение заказов...'],
    [20, 40, 'Анализ FBO заказов...'],
    [40, 60, 'Получение данных о товарах...'],
    [60, 80, 'Расчёт остатков...'],
    [80, 95, 'Завершение анализа...'],
];

const FBOAnalysis = () => {
    const [isLoading, setIsLoading] = useState(true);
    const [isExporting, setIsExporting] = useState(false);
    const [error, setError] = useState(null);
    const [progress, setProgress] = useState(0);
    const [data, setData] = useState({ statistics: null, products: [], orders: [] });

    useEffect(() => { fetchFBOData(); }, []);

    const fetchFBOData = async () => {
        setIsLoading(true);
        setError(null);
        setProgress(0);

        const timer = setInterval(() => {
            setProgress(prev => {
                if (prev >= 95) { clearInterval(timer); return prev; }
                return prev + Math.random() * 2 + 1;
            });
        }, 1000);

        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 300000);
            const result = await analysisApi.fbo.get(controller.signal);
            clearTimeout(timeoutId);
            setData({ statistics: result.statistics, products: result.products, orders: result.orders });
        } catch (err) {
            setError(err.message || 'Произошла ошибка при загрузке данных');
        } finally {
            clearInterval(timer);
            setProgress(100);
            setTimeout(() => setIsLoading(false), 400);
        }
    };

    const handleExport = async () => {
        setIsExporting(true);
        try {
            const response = await analysisApi.fbo.export();
            if (!response.ok) throw new Error('Ошибка при экспорте данных');
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const link = document.createElement('a');
            const date = new Date().toLocaleDateString('ru-RU').replace(/\./g, '');
            link.href = url;
            link.download = `fbo_analysis_${date}.xlsx`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            window.URL.revokeObjectURL(url);
        } catch (err) {
            console.error('Export error:', err);
        } finally {
            setIsExporting(false);
        }
    };

    const stage = STAGES.find(([min, max]) => progress >= min && progress < max)?.[2] ?? 'Завершение...';

    const PageHeader = ({ showActions = false }) => (
        <div style={{ borderBottom: '1px solid var(--hairline)', paddingBottom: '16px', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
            <div>
                <h1 style={{ fontFamily: 'var(--serif)', fontSize: '32px', fontWeight: 400, letterSpacing: '-0.025em', lineHeight: 1.1, color: 'var(--ink)', margin: 0, marginBottom: '4px' }}>
                    Анализ FBO заказов
                </h1>
                <p style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--muted)', margin: 0 }}>
                    Неотгруженные FBO заказы с плановой датой отгрузки
                </p>
            </div>
            {showActions && (
                <div style={{ display: 'flex', gap: '8px' }}>
                    <button onClick={fetchFBOData} style={btnStyle(false)} title="Обновить данные">
                        <RefreshCw style={{ width: 13, height: 13 }} />
                        Обновить
                    </button>
                    <button onClick={handleExport} disabled={isExporting} style={btnStyle(true)} title="Экспорт в Excel">
                        {isExporting
                            ? <><Loader2 style={{ width: 13, height: 13 }} className="animate-spin" />Экспорт...</>
                            : <><Download style={{ width: 13, height: 13 }} />Экспорт</>
                        }
                    </button>
                </div>
            )}
        </div>
    );

    PageHeader.propTypes = { showActions: PropTypes.bool };

    if (isLoading) return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', color: 'var(--ink)' }}>
            <PageHeader />
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '64px 0', gap: '20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <Package style={{ width: 18, height: 18, color: 'var(--primary)' }} className="animate-pulse" />
                    <span style={{ fontFamily: 'var(--sans)', fontSize: '14px', color: 'var(--muted)' }}>{stage}</span>
                </div>
                <div style={{ width: '320px', height: '3px', backgroundColor: 'var(--hairline)', borderRadius: '2px', overflow: 'hidden' }}>
                    <div style={{ height: '100%', backgroundColor: 'var(--primary)', borderRadius: '2px', width: `${Math.min(progress, 100)}%`, transition: 'width 600ms ease' }} />
                </div>
                <p style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--muted-soft)', textAlign: 'center', maxWidth: '400px', margin: 0 }}>
                    Загрузка может занять до 3–5 минут в зависимости от объёма данных
                </p>
            </div>
        </div>
    );

    if (error) return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', color: 'var(--ink)' }}>
            <PageHeader />
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '64px 0', gap: '12px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#dc2626' }}>
                    <AlertCircle style={{ width: 18, height: 18 }} />
                    <span style={{ fontFamily: 'var(--sans)', fontSize: '14px', fontWeight: 500 }}>{error}</span>
                </div>
                <p style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--muted)', textAlign: 'center', maxWidth: '400px' }}>
                    Попробуйте повторить позже или обратитесь к администратору.
                </p>
                <button onClick={fetchFBOData} style={{ ...btnStyle(false), marginTop: '8px' }}>
                    <RefreshCw style={{ width: 13, height: 13 }} /> Повторить загрузку
                </button>
            </div>
        </div>
    );

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px', color: 'var(--ink)' }}>
            <PageHeader showActions />

            {data.statistics && (
                <section>
                    <SectionLabel>Статистика</SectionLabel>
                    <FBOStatistics statistics={data.statistics} />
                </section>
            )}

            {data.products.length > 0 && (
                <section>
                    <SectionLabel>Сводная информация по товарам</SectionLabel>
                    <FBOTable products={data.products} />
                </section>
            )}

            {data.orders.length > 0 && (
                <section>
                    <SectionLabel>Детали заказов</SectionLabel>
                    <FBOOrderDetails orders={data.orders} />
                </section>
            )}
        </div>
    );
};


const btnStyle = (primary) => ({
    display: 'inline-flex', alignItems: 'center', gap: '6px',
    padding: '6px 14px', borderRadius: '8px', border: 'none',
    fontFamily: 'var(--sans)', fontSize: '13px', fontWeight: 500,
    cursor: 'pointer', transition: 'background-color 150ms ease',
    backgroundColor: primary ? 'var(--primary)' : 'var(--surface-card)',
    color: primary ? '#fff' : 'var(--ink)',
});

export default FBOAnalysis;
