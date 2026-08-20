import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import FboStock from './FboStock';

vi.mock('../../api/analysisApi', () => ({
    analysisApi: {
        fboStock: {
            get: vi.fn(),
            export: vi.fn(),
        },
    },
}));

import { analysisApi } from '../../api/analysisApi';

// Цифры со скриншотов МойСклад: у пробиотика 70 шт ждут выпуска по
// производственному заданию, поэтому «Доступно» в МойСклад показывает 289
const ITEMS = [
    {
        article: '06-03GP0800', code: '2-207', name: 'Пробиотик GastroPro для лошадей, 800г', folder: 'GastroPro',
        stock: 237, reserve: 18, quantity: 219, in_transit: 70, minimum_balance: 267,
        below_minimum: true, is_empty: false,
    },
    {
        article: '08-02EP0800', code: '2-156', name: 'Биотин ExterPro для лошадей, 800 г', folder: 'ExterPro',
        stock: 213, reserve: 12, quantity: 201, in_transit: 0, minimum_balance: 133,
        below_minimum: false, is_empty: false,
    },
    {
        article: '99-00XX0000', code: '2-999', name: 'Товар без движения', folder: 'ArtroPro',
        stock: 0, reserve: 0, quantity: 0, in_transit: 0, minimum_balance: 0,
        below_minimum: false, is_empty: true,
    },
];

const renderPage = () => render(<FboStock />);

const rowFor = (article) => screen.getByText(article).closest('tr');

describe('Остатки для FBO', () => {
    beforeEach(() => {
        Object.defineProperty(window, 'innerWidth', { value: 1280, writable: true, configurable: true });
        analysisApi.fboStock.get.mockResolvedValue({
            status: 'success',
            data: { generated_at: '2026-08-20T15:33:00+03:00', store: 'Склад готовой продукции', items: ITEMS },
        });
    });

    it('показывает «можно взять» без ожидания', async () => {
        renderPage();
        await screen.findByText('06-03GP0800');
        const row = within(rowFor('06-03GP0800'));
        expect(row.getByText('219')).toBeInTheDocument();   // 237 − 18, а не 289
        expect(row.getByText('70')).toBeInTheDocument();
    });

    it('поясняет разницу с колонкой «Доступно» в МойСклад', async () => {
        renderPage();
        expect(await screen.findByText(/Можно взять = На складе − В резерве/)).toBeInTheDocument();
    });

    it('прячет позиции без движения, пока не попросят', async () => {
        const user = userEvent.setup();
        renderPage();
        await screen.findByText('06-03GP0800');
        expect(screen.queryByText('99-00XX0000')).not.toBeInTheDocument();

        await user.click(screen.getByLabelText(/Показывать позиции без остатка/));
        expect(screen.getByText('99-00XX0000')).toBeInTheDocument();
    });

    it('ищет по артикулу', async () => {
        const user = userEvent.setup();
        renderPage();
        await screen.findByText('06-03GP0800');

        await user.type(screen.getByPlaceholderText(/^Поиск/), '08-02');
        expect(screen.getByText('08-02EP0800')).toBeInTheDocument();
        expect(screen.queryByText('06-03GP0800')).not.toBeInTheDocument();
    });

    it('ищет по нескольким частям, как в МойСклад', async () => {
        const user = userEvent.setup();
        renderPage();
        await screen.findByText('06-03GP0800');

        // Оба товара по 800 г — отсекает вторая часть запроса
        await user.type(screen.getByPlaceholderText(/^Поиск/), 'проб 800');
        expect(screen.getByText('06-03GP0800')).toBeInTheDocument();
        expect(screen.queryByText('08-02EP0800')).not.toBeInTheDocument();
    });

    it('сортирует по клику на заголовок колонки', async () => {
        const user = userEvent.setup();
        renderPage();
        await screen.findByText('06-03GP0800');

        const articles = () => screen.getAllByText(/^\d\d-\d\d[A-Z]{2}\d{4}$/).map((el) => el.textContent);
        expect(articles()).toEqual(['08-02EP0800', '06-03GP0800']);   // по названию: Биотин, Пробиотик

        await user.click(screen.getByText('Можно взять'));            // числовые — сразу по убыванию
        expect(articles()).toEqual(['06-03GP0800', '08-02EP0800']);

        await user.click(screen.getByText('Можно взять'));            // повторный клик разворачивает
        expect(articles()).toEqual(['08-02EP0800', '06-03GP0800']);
    });

    it('перезапрашивает данные мимо кеша по кнопке «Обновить»', async () => {
        const user = userEvent.setup();
        renderPage();
        await screen.findByText('06-03GP0800');

        await user.click(screen.getByRole('button', { name: /Обновить/ }));
        expect(analysisApi.fboStock.get).toHaveBeenLastCalledWith(
            expect.objectContaining({ refresh: true }),
        );
    });
});
