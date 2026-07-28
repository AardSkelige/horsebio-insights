import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PurchaseRecommendations from './PurchaseRecommendations';

const GENERAL = {
    reorder_point: { value: 1318982, details: 'РАСЧЕТ СРЕДНЕГО ПОТРЕБЛЕНИЯ:\nПериод анализа: ...' },
    optimal_order_quantity: { value: 1069120, details: 'Расчёт EOQ ...' },
    safety_stock: { value: 500000, details: 'Расчёт страхового запаса ...' },
    lead_time: { avg: 9.3, details: 'Расчёт времени поставки ...' },
    periodic_orders: {
        frequent_orders: { total_size: 1000000, details: 'Ежемесячно ...' },
        quarterly_orders: { total_size: 3000000, details: 'Ежеквартально ...' },
    },
};

const baseProps = {
    recommendations: [],
    material: { uom: 'г' },
    suppliers: {},
    activityThreshold: 6,
    showInactive: true,
};

const openGeneral = async (user) => {
    await user.click(screen.getByText('Общие рекомендации по закупкам'));
};

describe('PurchaseRecommendations — суть вместо простыни', () => {
    it('по умолчанию показывает ключевые числа, а не сырой расчёт', async () => {
        const user = userEvent.setup();
        const { container } = render(<PurchaseRecommendations {...baseProps} generalCalculations={GENERAL} />);
        await openGeneral(user);

        // Суть: фраза-рекомендация и плитки
        expect(container.textContent).toMatch(/Заказывайте, когда остаток упадёт до/);
        expect(screen.getByText('Точка заказа')).toBeInTheDocument();
        expect(screen.getByText('Оптимальная партия')).toBeInTheDocument();
        expect(screen.getByText('Страховой запас')).toBeInTheDocument();

        // Сырой моноширинный расчёт скрыт до клика
        expect(screen.queryByText(/РАСЧЕТ СРЕДНЕГО ПОТРЕБЛЕНИЯ/)).toBeNull();
    });

    it('«Показать расчёт» раскрывает детальную математику', async () => {
        const user = userEvent.setup();
        render(<PurchaseRecommendations {...baseProps} generalCalculations={GENERAL} />);
        await openGeneral(user);

        await user.click(screen.getByText('Показать расчёт'));
        expect(screen.getByText(/РАСЧЕТ СРЕДНЕГО ПОТРЕБЛЕНИЯ/)).toBeInTheDocument();
    });

    it('при нулевой цене оптимальная партия помечена как недоступная', async () => {
        const user = userEvent.setup();
        const zeroPrice = { ...GENERAL, optimal_order_quantity: { value: 0, details: 'нет цены' } };
        const { container } = render(<PurchaseRecommendations {...baseProps} generalCalculations={zeroPrice} />);
        await openGeneral(user);

        expect(container.textContent).toMatch(/нет данных о цене/);
        // Фраза-рекомендация не обещает партию, которую не смогли посчитать
        expect(container.textContent).not.toMatch(/Оптимальная партия — /);
    });
});
