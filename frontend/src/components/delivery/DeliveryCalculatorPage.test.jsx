import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { deliveryApi } from '../../api/deliveryApi';
import DeliveryCalculatorPage from './DeliveryCalculatorPage';

vi.mock('../../api/deliveryApi', () => ({
    deliveryApi: {
        recentOrders: vi.fn(),
        searchProducts: vi.fn(),
        searchCities: vi.fn(),
        estimate: vi.fn(),
    },
}));

const ORDER = {
    id: 'order-1',
    name: '06425',
    counterparty: 'Фрейман Юрий Анатольевич',
    city: 'Гатчина',
    address: 'Пункт СДЭК, Гатчина',
    sum: 2008,
    moment: '2026-07-29T10:00:00+03:00',
};

const RESULT = {
    blocked: false,
    to_city: 'Гатчина',
    packing: {
        places: 1,
        weight_kg: 1.11,
        volume_l: 5.2,
        boxes: { SM: 1 },
        detail: [{ box: 'SM', weight_kg: 1.11, fill_pct: 43, items: ['ЭквиГард'] }],
        unpackable: [],
    },
    carriers: {
        pec: { warehouse: 770, door: 1776, days: '2 - 4' },
        cdek: { warehouse: 400, door: 660, days: '3 - 4' },
    },
};

describe('DeliveryCalculatorPage', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        deliveryApi.recentOrders.mockResolvedValue([ORDER]);
        deliveryApi.searchProducts.mockResolvedValue([]);
        deliveryApi.searchCities.mockResolvedValue([{ name: 'Гатчина (Гатчинский р-н)' }]);
        deliveryApi.estimate.mockResolvedValue(RESULT);
    });

    afterEach(() => vi.restoreAllMocks());

    it('сохраняет результат заказа между табами и прокручивает к нему после расчёта', async () => {
        const user = userEvent.setup();
        const scrollSpy = vi.spyOn(window.HTMLElement.prototype, 'scrollIntoView');
        render(<DeliveryCalculatorPage />);

        expect(screen.getByRole('status')).toHaveTextContent('Выберите заказ');
        await user.click(await screen.findByRole('button', { name: /06425/ }));
        await waitFor(() => expect(screen.getByRole('button', { name: 'Рассчитать' })).toBeEnabled());
        await user.click(screen.getByRole('button', { name: 'Рассчитать' }));

        expect(await screen.findByRole('heading', { name: 'Доставка в Гатчина' })).toBeInTheDocument();
        expect(screen.getByRole('status')).toHaveTextContent('Расчёт готов');
        await waitFor(() => expect(scrollSpy).toHaveBeenCalled());

        await user.click(screen.getByRole('tab', { name: 'Ручной состав' }));
        expect(screen.queryByRole('heading', { name: 'Доставка в Гатчина' })).not.toBeInTheDocument();

        await user.click(screen.getByRole('tab', { name: 'Заказ МойСклад' }));
        expect(screen.getByRole('heading', { name: 'Доставка в Гатчина' })).toBeInTheDocument();
        expect(screen.getByDisplayValue('Гатчина')).toBeInTheDocument();
    });

    it('не подставляет страну вместо города из старого ответа API', async () => {
        const user = userEvent.setup();
        deliveryApi.recentOrders.mockResolvedValue([{ ...ORDER, city: 'Россия' }]);
        render(<DeliveryCalculatorPage />);

        await user.click(await screen.findByRole('button', { name: /06425/ }));

        expect(screen.getByLabelText('Город получателя')).toHaveValue('');
        expect(screen.getByRole('button', { name: 'Рассчитать' })).toBeDisabled();
        expect(screen.getByText('Город не указан')).toBeInTheDocument();
    });

    it('показывает понятный статус во время расчёта', async () => {
        const user = userEvent.setup();
        let resolveEstimate;
        deliveryApi.estimate.mockReturnValue(new Promise((resolve) => {
            resolveEstimate = resolve;
        }));
        render(<DeliveryCalculatorPage />);

        await user.click(await screen.findByRole('button', { name: /06425/ }));
        await waitFor(() => expect(screen.getByRole('button', { name: 'Рассчитать' })).toBeEnabled());
        await user.click(screen.getByRole('button', { name: 'Рассчитать' }));

        expect(screen.getByRole('status')).toHaveTextContent('Рассчитываем доставку');
        expect(screen.getByRole('status')).toHaveTextContent('Подбираем упаковку и сравниваем тарифы');

        resolveEstimate(RESULT);
        expect(await screen.findByRole('heading', { name: 'Доставка в Гатчина' })).toBeInTheDocument();
    });

    it('исправляет опечатку через подсказку и разрешает только выбранный город', async () => {
        const user = userEvent.setup();
        deliveryApi.recentOrders.mockResolvedValue([{ ...ORDER, city: '' }]);
        deliveryApi.searchCities.mockResolvedValue([{ name: 'Москва' }]);
        render(<DeliveryCalculatorPage />);

        await user.click(await screen.findByRole('button', { name: /06425/ }));
        const cityInput = screen.getByLabelText('Город получателя');
        await user.type(cityInput, 'масква');

        expect(screen.getByRole('button', { name: 'Рассчитать' })).toBeDisabled();
        await user.click(await screen.findByRole('option', { name: 'Москва' }));

        expect(cityInput).toHaveValue('Москва');
        expect(screen.getByRole('button', { name: 'Рассчитать' })).toBeEnabled();
        expect(screen.getByRole('status')).toHaveTextContent('Всё готово к расчёту');
    });

    it('корректирует количество ручной позиции кнопками плюс и минус', async () => {
        const user = userEvent.setup();
        const product = {
            href: 'https://example.test/product/1',
            name: 'Коллаген',
            code: '2-003',
        };
        deliveryApi.searchProducts.mockResolvedValue([product]);
        render(<DeliveryCalculatorPage />);

        await user.click(screen.getByRole('tab', { name: 'Ручной состав' }));
        await user.type(screen.getByLabelText('Поиск товара'), 'Коллаген');
        await user.click(await screen.findByRole('button', { name: /Коллаген/ }));

        const quantity = screen.getByLabelText('Количество: Коллаген');
        const decrement = screen.getByRole('button', { name: 'Уменьшить количество: Коллаген' });
        expect(quantity).toHaveValue('1');
        expect(decrement).toBeDisabled();

        await user.click(screen.getByRole('button', { name: 'Увеличить количество: Коллаген' }));
        expect(quantity).toHaveValue('2');
        expect(decrement).toBeEnabled();

        await user.click(decrement);
        expect(quantity).toHaveValue('1');
    });

    it('показывает фасовку отдельно в результатах поиска товара', async () => {
        const user = userEvent.setup();
        const longName = 'Хондропротектор ArtroPro для кошек, 200 мл (с помпой-дозатором)';
        deliveryApi.searchProducts.mockResolvedValue([{
            href: 'https://example.test/product/2',
            name: longName,
            code: '2-027',
        }]);
        render(<DeliveryCalculatorPage />);

        await user.click(screen.getByRole('tab', { name: 'Ручной состав' }));
        await user.type(screen.getByLabelText('Поиск товара'), 'Хондропротектор');

        expect(await screen.findByText('200 мл')).toBeInTheDocument();
        await user.hover(screen.getByText(longName));
        expect(screen.getByRole('tooltip', { name: longName })).toBeInTheDocument();
    });
});
