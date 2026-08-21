import { useState, useEffect } from 'react';
import { Package, Download } from 'lucide-react';
import FBOTable from './FBOTable';
import FBOStatistics from './FBOStatistics';
import FBOOrderDetails from './FBOOrderDetails';
import { Button, ErrorState, Page, PageHeader, SectionLabel } from '../ui';
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
            const blob = await analysisApi.fbo.export();
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

    const header = (showActions) => (
        <PageHeader
            title="FBO Заказы"
            subtitle="Неотгруженные FBO заказы с плановой датой отгрузки"
            onRefresh={showActions ? fetchFBOData : undefined}
            actions={showActions && (
                <Button variant="soft" icon={Download} loading={isExporting} onClick={handleExport}>
                    {isExporting ? 'Экспорт...' : 'Экспорт'}
                </Button>
            )}
        />
    );

    if (isLoading) return (
        <Page>
            {header(false)}
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
        </Page>
    );

    if (error) return (
        <Page>
            {header(false)}
            <ErrorState
                title={error}
                hint="Попробуйте повторить позже или обратитесь к администратору."
                onRetry={fetchFBOData}
            />
        </Page>
    );

    return (
        <Page>
            {header(true)}

            {data.statistics && (
                <section>
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
        </Page>
    );
};



export default FBOAnalysis;
