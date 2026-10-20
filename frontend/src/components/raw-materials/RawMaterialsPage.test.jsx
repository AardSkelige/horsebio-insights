import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RawMaterialsPage from './RawMaterialsPage';

vi.mock('../../api/rawMaterialsApi', () => ({
    rawMaterialsApi: { list: vi.fn(), refresh: vi.fn() },
}));

import { rawMaterialsApi } from '../../api/rawMaterialsApi';

const PAYLOAD = {
    synced_at: '2026-10-20T15:55:00+03:00',
    items: [
        {
            id: 1, name: 'Хондроитин сульфат', slot: 'A6', uom: 'г', quantity: 150000,
            batches: [
                { id: 11, series: 'GN2508029', expiry_date: '2020-01-01', quantity: 100000 },
                { id: 12, series: '', expiry_date: null, quantity: 50000 },
            ],
        },
        {
            id: 2, name: 'Ведро 2 литра', slot: 'C2', group: 'Тара', uom: 'шт', quantity: 966,
            batches: [{ id: 21, series: '', expiry_date: null, quantity: 966 }],
        },
    ],
};

const cardOf = (name) => screen.getByText(name).closest('.raw-materials__item');

describe('Склад сырья', () => {
    beforeEach(() => {
        rawMaterialsApi.list.mockResolvedValue(PAYLOAD);
        rawMaterialsApi.refresh.mockResolvedValue(PAYLOAD);
    });

    it('группирует по ячейкам и показывает остаток и серии', async () => {
        render(<RawMaterialsPage />);
        await screen.findByText('Хондроитин сульфат');
        const card = within(cardOf('Хондроитин сульфат'));
        expect(screen.getByRole('heading', { name: 'A6' })).toBeInTheDocument();
        expect(card.getByText('150 кг')).toBeInTheDocument();
        expect(card.getByText('GN2508029')).toBeInTheDocument();
        expect(card.getByText('Без серии')).toBeInTheDocument();
        expect(card.getByText(/Просрочена/)).toBeInTheDocument();
    });

    it('у тары не показывает пустую строку «без серии»', async () => {
        render(<RawMaterialsPage />);
        await screen.findByText('Ведро 2 литра');
        expect(within(cardOf('Ведро 2 литра')).queryByText('Без серии')).not.toBeInTheDocument();
    });

    it('переключается на тару', async () => {
        render(<RawMaterialsPage />);
        await screen.findByText('Ведро 2 литра');
        await userEvent.click(screen.getByRole('tab', { name: 'Тара' }));
        expect(screen.queryByText('Хондроитин сульфат')).not.toBeInTheDocument();
    });

    it('фильтрует по ячейке', async () => {
        render(<RawMaterialsPage />);
        await screen.findByText('Ведро 2 литра');
        await userEvent.selectOptions(screen.getByRole('combobox'), 'C2');
        expect(screen.queryByText('Хондроитин сульфат')).not.toBeInTheDocument();
        expect(screen.getByText('Ведро 2 литра')).toBeInTheDocument();
    });

    it('по кнопке обновления сверяется с МойСклад', async () => {
        render(<RawMaterialsPage />);
        await screen.findByText('Ведро 2 литра');
        await userEvent.click(screen.getByRole('button', { name: /Обновить/ }));
        expect(rawMaterialsApi.refresh).toHaveBeenCalled();
    });
});
