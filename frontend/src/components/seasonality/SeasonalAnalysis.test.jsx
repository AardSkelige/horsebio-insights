import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MotionProvider } from '../ui/motion';
import { SeasonalAnalysis } from './SeasonalAnalysis';

const product = {
    id: 57,
    name: 'Хондропротектор Хондрофит',
    article: '11-03AP0500',
    seasonality_type: 'STABLE',
    seasonality_name: 'Стабильные продажи',
    seasonal_factors: { 1: 1.0, 2: 1.1 },
    stability_metrics: { coefficient_std: 0.2, max_deviation: 0.1 },
};

const details = {
    ...product,
    group: 'Товары',
    monthly_sales: { '2025-07': 200, '2025-08': 633 },
    peaks: [{ month: 'Август', deviation_percent: 25.0 }],
    troughs: [],
    sales_stats: { avg_monthly_quantity: 400, total_revenue: 1000000 },
};

vi.mock('../../api/seasonalAnalysis', () => ({
    seasonalAnalysisApi: {
        getAnalysis: vi.fn(() => Promise.resolve({ status: 'success', data: { products: [product] } })),
        getProductDetails: vi.fn(() => Promise.resolve({ status: 'success', data: details })),
    },
}));

describe('SeasonalAnalysis — клик по строке продукта', () => {
    it('открывает детальный анализ выбранного продукта', async () => {
        const user = userEvent.setup();
        render(<MotionProvider><SeasonalAnalysis /></MotionProvider>);

        // Таблица паттернов загрузилась
        const row = await screen.findByText('Хондропротектор Хондрофит');

        // До клика — приглашение выбрать продукт, деталей нет
        expect(screen.getByText('Выберите продукт для просмотра статистики')).toBeInTheDocument();
        expect(screen.queryByText('Детальный анализ')).not.toBeInTheDocument();

        await user.click(row);

        // После клика — статистика заполнена и появились детальные секции
        await waitFor(() => {
            expect(screen.getByText('Детальный анализ')).toBeInTheDocument();
        }, { timeout: 3000 });
        expect(screen.getByText('Подробная информация о продукте')).toBeInTheDocument();
        expect(screen.queryByText('Выберите продукт для просмотра статистики')).not.toBeInTheDocument();
    });
});
