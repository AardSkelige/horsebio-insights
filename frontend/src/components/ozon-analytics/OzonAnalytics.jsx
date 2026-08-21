import { ChartBar, PackageSearch } from 'lucide-react';
import { Page, PageHeader } from '../ui';
import ReportSection from './components/ReportSection';
import CompetitorsSection from './components/CompetitorsSection';
import StockAvailabilitySection from './components/StockAvailabilitySection';
import './OzonAnalytics.css';

const OzonAnalytics = () => (
    <Page className="ozon-page">
        <PageHeader title="Ozon" subtitle="4 инструмента для отчётов и обработки файлов" />

        <ReportSection />

        <div className="ozon-grid">
            <section className="ozon-section">
                <div className="ozon-section__heading">
                    <div className="ozon-section__icon"><ChartBar size={18} /></div>
                    <div>
                        <h2>Конкуренты</h2>
                        <p>Дополнительные метрики эффективности из analytics_report.</p>
                    </div>
                </div>
                <CompetitorsSection />
            </section>

            <section className="ozon-section">
                <div className="ozon-section__heading">
                    <div className="ozon-section__icon"><PackageSearch size={18} /></div>
                    <div>
                        <h2>Доступность товаров</h2>
                        <p>Форматирование региональных остатков и товаров в пути.</p>
                    </div>
                </div>
                <StockAvailabilitySection />
            </section>
        </div>
    </Page>
);

export default OzonAnalytics;
