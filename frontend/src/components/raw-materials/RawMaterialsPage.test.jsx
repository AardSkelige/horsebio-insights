import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import RawMaterialsPage from './RawMaterialsPage';

vi.mock('../../api/rawMaterialsApi', () => ({
    rawMaterialsApi: { list: vi.fn(), refresh: vi.fn(), issue: vi.fn() },
}));

import { rawMaterialsApi } from '../../api/rawMaterialsApi';

const PAYLOAD = {
    synced_at: '2026-10-20T15:55:00+03:00',
    slots: ['A6', 'C2'],
    items: [
        {
            id: 1, name: 'Хондроитин сульфат', slot: 'A6', slots: ['A6'], uom: 'г', quantity: 150000,
            batches: [
                { id: 11, series: 'GN2508029', expiry_date: '2020-01-01', quantity: 100000 },
                { id: 12, series: 'GN2509001', expiry_date: '2030-01-01', quantity: 30000 },
                { id: 13, series: '', expiry_date: null, quantity: 20000 },
            ],
        },
        {
            id: 2, name: 'Ведро 2 литра', slot: 'C2', slots: ['C2'], group: 'Тара', uom: 'шт', quantity: 966,
            batches: [{ id: 21, series: '', expiry_date: null, quantity: 966 }],
        },
    ],
};

const renderPage = () => render(<MemoryRouter><RawMaterialsPage /></MemoryRouter>);
const itemOf = (name) => screen.getByText(name).closest('.shelf__item');

describe('Склад сырья', () => {
    beforeEach(() => {
        localStorage.clear();
        rawMaterialsApi.list.mockResolvedValue(PAYLOAD);
        rawMaterialsApi.refresh.mockResolvedValue(PAYLOAD);
    });

    it('у каждого сырья своя карточка с ячейкой и всеми сериями', async () => {
        renderPage();
        await screen.findByText('Хондроитин сульфат');
        const item = within(itemOf('Хондроитин сульфат'));
        expect(item.getByText('A6')).toBeInTheDocument();
        expect(item.getByText('150 кг')).toBeInTheDocument();
        expect(item.getByText('GN2508029')).toBeInTheDocument();
        expect(item.getByText('просрочена 01.01.2020')).toBeInTheDocument();
        expect(item.getAllByRole('row')).toHaveLength(4);
    });

    it('у тары без серий та же табличка, только с прочерками', async () => {
        renderPage();
        await screen.findByText('Ведро 2 литра');
        const item = within(itemOf('Ведро 2 литра'));
        expect(item.getAllByRole('row')).toHaveLength(2);
        expect(item.getAllByText('—')).toHaveLength(2);
    });

    it('переключается на тару', async () => {
        renderPage();
        await screen.findByText('Ведро 2 литра');
        await userEvent.click(screen.getByRole('tab', { name: 'Тара' }));
        expect(screen.queryByText('Хондроитин сульфат')).not.toBeInTheDocument();
    });

    it('ищет по ячейке', async () => {
        renderPage();
        await screen.findByText('Ведро 2 литра');
        await userEvent.type(screen.getByPlaceholderText('Сырьё, серия или ячейка'), 'c2');
        expect(screen.queryByText('Хондроитин сульфат')).not.toBeInTheDocument();
    });

    it('клик по сырью открывает карточку со всеми сериями и выдачей', async () => {
        const user = userEvent.setup();
        renderPage();
        await user.click(await screen.findByText('Хондроитин сульфат'));
        const sheet = within(screen.getByRole('dialog', { name: 'Карточка сырья' }));
        expect(sheet.getAllByRole('radio')).toHaveLength(3);
        expect(sheet.getByRole('radio', { name: /GN2509001/ })).toHaveAttribute('aria-checked', 'true');
        expect(sheet.getByRole('button', { name: 'В корзину' })).toBeInTheDocument();
    });

    it('по кнопке обновления сверяется с МойСклад', async () => {
        renderPage();
        await screen.findByText('Ведро 2 литра');
        await userEvent.click(screen.getByRole('button', { name: /Обновить/ }));
        expect(rawMaterialsApi.refresh).toHaveBeenCalled();
    });
});
