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

const plain = (text) => text.replace(/\u00A0/g, ' ');

const ARTICLE_LINK = 'https://online.moysklad.ru/app/#operation?article';
const PERIOD_LINK = 'https://online.moysklad.ru/app/#operation?period';

const DATA = {
    initial_balance: 8877300,
    moysklad_period_link: PERIOD_LINK,
    group_links: { 'Дилеры': 'https://online.moysklad.ru/app/#operation?group' },
    income: {
        total: 500000,
        channels: { 'Ozon': 200000, 'Оптовые продажи': 300000, 'Пустой канал': 0 },
        groups: { 'Маркетплейсы': 200000, 'Дилеры': 300000, 'Пустая группа': 0 },
    },
    expense: {
        total: 120000,
        categories: { 'Сырьё': { amount: 120000, moysklad_link: ARTICLE_LINK } },
        groups: { 'Поставщики': 120000 },
    },
    net_cash_flow: 380000,
    profit: 380000,
    final_balance: 9257300,
};

const fillDatesAndFetch = async (user) => {
    fireEvent.change(screen.getByLabelText('Дата начала'), { target: { value: '2026-01-01' } });
    fireEvent.change(screen.getByLabelText('Дата окончания'), { target: { value: '2026-06-30' } });
    await user.click(screen.getByRole('button', { name: /Сформировать/ }));
};

const renderLoaded = async () => {
    const user = userEvent.setup();
    analysisApi.cashFlow.get.mockResolvedValue({ success: true, data: DATA });
    const view = render(<CashFlowReport />);
    await fillDatesAndFetch(user);
    await screen.findByText('Кон. остаток');
    return { user, ...view };
};

beforeEach(() => vi.clearAllMocks());

describe('CashFlowReport', () => {
    it('без выбранного периода кнопка заблокирована', () => {
        render(<CashFlowReport />);
        expect(screen.getByRole('button', { name: /Сформировать/ })).toBeDisabled();
        expect(screen.getByText('Выберите период для формирования отчёта')).toBeInTheDocument();
    });

    it('запрашивает отчёт за выбранный период и показывает итоги', async () => {
        const { container } = await renderLoaded();

        expect(analysisApi.cashFlow.get).toHaveBeenCalledWith('2026-01-01', '2026-06-30');
        const foot = plain(container.querySelector('.cf-foot').textContent);
        expect(foot).toContain('+380 000 ₽');
        expect(foot).toContain('9 257 300 ₽');
    });

    it('группы прихода отсортированы по убыванию суммы, нулевые скрыты', async () => {
        await renderLoaded();

        const dealers = screen.getByText('Дилеры', { selector: '.cf-txt' });
        const markets = screen.getByText('Маркетплейсы', { selector: '.cf-txt' });
        expect(dealers.compareDocumentPosition(markets) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
        expect(screen.queryByText('Пустая группа')).not.toBeInTheDocument();
    });

    it('переключение на каналы показывает каналы без нулевых', async () => {
        const { user } = await renderLoaded();

        await user.click(screen.getByRole('button', { name: 'Каналы' }));
        const opt = await screen.findByText('Оптовые продажи');
        const ozon = screen.getByText('Ozon');
        expect(opt.compareDocumentPosition(ozon) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
        expect(screen.queryByText('Пустой канал')).not.toBeInTheDocument();
    });

    it('клик по строке открывает МойСклад: статья по своей ссылке, группа без ссылки по периоду', async () => {
        const open = vi.spyOn(window, 'open').mockImplementation(() => null);
        const { user } = await renderLoaded();

        await user.click(screen.getByText('Поставщики', { selector: '.cf-txt' }));
        expect(open).toHaveBeenLastCalledWith(PERIOD_LINK, '_blank', 'noopener,noreferrer');

        await user.click(screen.getByRole('button', { name: 'Статьи' }));
        await user.click(await screen.findByText('Сырьё'));
        expect(open).toHaveBeenLastCalledWith(ARTICLE_LINK, '_blank', 'noopener,noreferrer');
        open.mockRestore();
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
