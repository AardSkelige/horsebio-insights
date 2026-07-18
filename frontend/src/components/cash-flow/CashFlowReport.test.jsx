import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CashFlowReport from './CashFlowReport';
import { analysisApi } from '../../api/analysisApi';

vi.mock('../../api/analysisApi', () => ({
    analysisApi: {
        cashFlow: { get: vi.fn(), export: vi.fn() },
    },
}));

// toLocaleString('ru-RU') разделяет тысячи неразрывными пробелами
const byMoney = (expected) => (content) => content.replace(/\u00A0/g, ' ') === expected;

const DATA = {
    initial_balance: 8877300,
    income: { total: 500000, channels: { 'Ozon': 200000, 'Оптовые продажи': 300000, 'Пустой канал': 0 } },
    expense: { total: 120000, categories: { 'Сырьё': { amount: 120000, moysklad_link: 'https://online.moysklad.ru/app/#operation' } } },
    net_cash_flow: 380000,
    profit: 380000,
    final_balance: 9257300,
};

const fillDatesAndFetch = async (user) => {
    const [from, to] = document.querySelectorAll('input[type="date"]');
    fireEvent.change(from, { target: { value: '2026-01-01' } });
    fireEvent.change(to, { target: { value: '2026-06-30' } });
    await user.click(screen.getByRole('button', { name: /Сформировать отчёт/ }));
};

beforeEach(() => vi.clearAllMocks());

describe('CashFlowReport', () => {
    it('без выбранного периода кнопка заблокирована', () => {
        render(<CashFlowReport />);
        expect(screen.getByRole('button', { name: /Сформировать отчёт/ })).toBeDisabled();
        expect(screen.getByText('Выберите период для формирования отчёта')).toBeInTheDocument();
    });

    it('показывает итоговые карточки с правильными суммами', async () => {
        const user = userEvent.setup();
        analysisApi.cashFlow.get.mockResolvedValue({ success: true, data: DATA });
        render(<CashFlowReport />);
        await fillDatesAndFetch(user);

        expect(analysisApi.cashFlow.get).toHaveBeenCalledWith('2026-01-01', '2026-06-30');
        expect(await screen.findByText('Начальный остаток')).toBeInTheDocument();
        expect(screen.getByText(byMoney('8 877 300'))).toBeInTheDocument();
        expect(screen.getByText(byMoney('9 257 300'))).toBeInTheDocument();
        // 380 000 встречается дважды: чистый поток и прибыль
        expect(screen.getAllByText(byMoney('380 000'))).toHaveLength(2);
    });

    it('каналы отсортированы по убыванию суммы, нулевые скрыты', async () => {
        const user = userEvent.setup();
        analysisApi.cashFlow.get.mockResolvedValue({ success: true, data: DATA });
        render(<CashFlowReport />);
        await fillDatesAndFetch(user);

        const opt = await screen.findByText('Оптовые продажи');
        const ozon = screen.getByText('Ozon');
        // Оптовые (300 000) должны идти раньше Ozon (200 000)
        expect(opt.compareDocumentPosition(ozon) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
        expect(screen.queryByText('Пустой канал')).not.toBeInTheDocument();
    });

    it('статья расходов со ссылкой ведёт в МойСклад', async () => {
        const user = userEvent.setup();
        analysisApi.cashFlow.get.mockResolvedValue({ success: true, data: DATA });
        render(<CashFlowReport />);
        await fillDatesAndFetch(user);

        const link = await screen.findByRole('link', { name: /Сырьё/ });
        expect(link).toHaveAttribute('href', 'https://online.moysklad.ru/app/#operation');
        expect(link).toHaveAttribute('target', '_blank');
    });

    it('ошибка от сервера показывается пользователю', async () => {
        const user = userEvent.setup();
        analysisApi.cashFlow.get.mockResolvedValue({ success: false, error: 'Период слишком большой' });
        render(<CashFlowReport />);
        await fillDatesAndFetch(user);
        expect(await screen.findByText('Период слишком большой')).toBeInTheDocument();
    });

    it('сетевая ошибка не роняет страницу', async () => {
        const user = userEvent.setup();
        analysisApi.cashFlow.get.mockRejectedValue(new Error('Failed to fetch'));
        render(<CashFlowReport />);
        await fillDatesAndFetch(user);
        expect(await screen.findByText(/Ошибка сети/)).toBeInTheDocument();
    });
});
