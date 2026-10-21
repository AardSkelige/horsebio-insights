import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ProductionPlanPage from './ProductionPlanPage';

vi.mock('../../api/productionPlanApi', () => ({
    productionPlanApi: {
        get: vi.fn(),
        refresh: vi.fn(),
        export: vi.fn(),
        exclusions: vi.fn(),
        addExclusion: vi.fn(),
        removeExclusion: vi.fn(),
        setGreen: vi.fn(),
    },
}));

import { productionPlanApi } from '../../api/productionPlanApi';

const MONTHS = ['2026-07-01', '2026-08-01', '2026-09-01'];
const ROWS = [
    {
        article: '08-10EP5000', name: 'Льняное масло ExterPro для лошадей, 5000 мл', months: [9, 0, 4], spikes: [],
        channels: [{ key: 'ozon', label: 'Ozon', months: [9, 0, 4] }],
        usual: 4, need: 8, available: 0, in_production: 0, produce: 8, status: 'urgent', green: false,
    },
    {
        article: '11-36AP0100', name: 'Капсулы Хондроитин+МСМ+Глюкозамин', months: [1454, 846, 724], spikes: [0],
        channels: [{ key: 'ozon', label: 'Ozon', months: [606, 844, 691] }, { key: 'direct', label: 'Дилеры, сайт, чаты', months: [848, 2, 33] }],
        usual: 846, need: 1692, available: 800, in_production: 300, produce: 592, status: 'produce', green: true,
    },
    {
        article: '01-16AP2000', name: 'МультиКальций ArtroPro', months: [120, 127, 110], spikes: [],
        channels: [{ key: 'ozon', label: 'Ozon', months: [120, 127, 110] }],
        usual: 120, need: 240, available: 400, in_production: 0, produce: 0, status: 'enough', green: false,
    },
];

const plan = (overrides = {}) => ({ months: MONTHS, ozon_months: MONTHS, wb_months: [], stock_at: '2026-10-21T06:19:00+00:00', rows: ROWS, ...overrides });

describe('Производственный план', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        Object.defineProperty(window, 'innerWidth', { value: 1280, writable: true, configurable: true });
        productionPlanApi.get.mockResolvedValue(plan());
        productionPlanApi.setGreen.mockResolvedValue({});
    });

    it('по умолчанию показывает только то, что надо произвести', async () => {
        render(<ProductionPlanPage />);
        expect(await screen.findByText('11-36AP0100')).toBeInTheDocument();
        expect(screen.queryByText('01-16AP2000')).not.toBeInTheDocument();
        await userEvent.click(screen.getByRole('tab', { name: 'Все' }));
        expect(screen.getByText('01-16AP2000')).toBeInTheDocument();
    });

    it('считает итог к производству', async () => {
        render(<ProductionPlanPage />);
        expect(await screen.findByText('600 шт')).toBeInTheDocument();
        expect(screen.getByText('2 позиций')).toBeInTheDocument();
    });

    it('по клику раскрывает каналы и расчёт словами', async () => {
        render(<ProductionPlanPage />);
        await userEvent.click(await screen.findByText('11-36AP0100'));
        expect(screen.getByText('Дилеры, сайт, чаты')).toBeInTheDocument();
        expect(screen.getByText(/Всплеск \(в июле 1\s454\) в расчёт не взят/)).toBeInTheDocument();
        expect(screen.getByText(/произвести 592/)).toBeInTheDocument();
    });

    it('убирает товар из зелёного списка', async () => {
        render(<ProductionPlanPage />);
        await userEvent.click(await screen.findByText('11-36AP0100'));
        await userEvent.click(screen.getByRole('button', { name: 'Убрать из зелёного списка' }));
        expect(productionPlanApi.setGreen).toHaveBeenCalledWith('11-36AP0100', 'Капсулы Хондроитин+МСМ+Глюкозамин', false);
        expect(await screen.findByRole('button', { name: 'Добавить в зелёный список' })).toBeInTheDocument();
    });

    it('предупреждает, если продажи Ozon за месяц не загружены', async () => {
        productionPlanApi.get.mockResolvedValue(plan({ ozon_months: MONTHS.slice(0, 2) }));
        render(<ProductionPlanPage />);
        expect(await screen.findByText(/Нет продаж Ozon в сентябре/)).toBeInTheDocument();
    });

    it('ищет по части названия', async () => {
        render(<ProductionPlanPage />);
        await screen.findByText('11-36AP0100');
        await userEvent.type(screen.getByPlaceholderText(/Поиск/), 'льнян');
        const table = within(screen.getByRole('table'));
        expect(table.getByText('08-10EP5000')).toBeInTheDocument();
        expect(table.queryByText('11-36AP0100')).not.toBeInTheDocument();
    });

    it('после неудачного обновления перечитывает план и показывает причину', async () => {
        productionPlanApi.refresh.mockRejectedValue(new Error('Остатки обновлены, а продажи Ozon нет'));
        render(<ProductionPlanPage />);
        await screen.findByText('11-36AP0100');
        await userEvent.click(screen.getByRole('button', { name: /Обновить/ }));
        expect(await screen.findByText(/продажи Ozon нет/)).toBeInTheDocument();
        expect(productionPlanApi.get).toHaveBeenCalledTimes(2);
    });

    it('не стирает исключение, если сохранить не удалось', async () => {
        productionPlanApi.exclusions.mockResolvedValue({ items: [] });
        productionPlanApi.addExclusion.mockRejectedValue(new Error('Слишком длинно'));
        render(<ProductionPlanPage />);
        await userEvent.click(await screen.findByRole('button', { name: 'Исключения' }));
        const input = await screen.findByPlaceholderText(/Артикул или слово/);
        await userEvent.type(input, 'мармелад');
        await userEvent.click(screen.getByRole('button', { name: 'Добавить' }));
        expect(await screen.findByText('Слишком длинно')).toBeInTheDocument();
        expect(input).toHaveValue('мармелад');
    });

    it('пишет, с какого месяца WB считается по данным WB', async () => {
        productionPlanApi.get.mockResolvedValue(plan({ wb_months: MONTHS.slice(1) }));
        render(<ProductionPlanPage />);
        expect(await screen.findByText(/WB по данным WB с августа, раньше — то, что мы им отгрузили/)).toBeInTheDocument();
    });
});
