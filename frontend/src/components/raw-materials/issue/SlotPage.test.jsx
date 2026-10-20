import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import SlotPage from './SlotPage';

vi.mock('../../../api/rawMaterialsApi', () => ({
    rawMaterialsApi: { list: vi.fn(), refresh: vi.fn(), issue: vi.fn() },
}));

import { rawMaterialsApi } from '../../../api/rawMaterialsApi';

const PAYLOAD = {
    synced_at: '2026-10-20T15:55:00+03:00',
    slots: ['А1', 'A6', 'C2'],
    items: [
        {
            id: 1, name: 'Хондроитин сульфат', slot: 'А1', slots: ['А1', 'A6'], uom: 'г', quantity: 1500,
            batches: [
                { id: 11, series: 'OLD', expiry_date: '2020-01-01', quantity: 500 },
                { id: 12, series: 'GN2508029', expiry_date: '2030-01-01', quantity: 1000 },
            ],
        },
        {
            id: 2, name: 'Ведро 2 литра', slot: 'C2', group: 'Тара', uom: 'шт', quantity: 966,
            batches: [{ id: 21, series: '', expiry_date: null, quantity: 966 }],
        },
    ],
};

const renderSlot = (slot) => render(
    <MemoryRouter initialEntries={[`/raw-materials/slot/${encodeURIComponent(slot)}`]}>
        <Routes>
            <Route path="/raw-materials/slot/:slot" element={<SlotPage />} />
        </Routes>
    </MemoryRouter>,
);

describe('Выдача из ячейки', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        localStorage.clear();
        rawMaterialsApi.list.mockResolvedValue(PAYLOAD);
        rawMaterialsApi.issue.mockResolvedValue({
            id: 1, moysklad_name: '00285', description: 'Ваня, выдача сырья',
            moysklad_url: 'https://online.moysklad.ru/app/#move/edit?id=m', lines: [],
        });
    });

    it('показывает только то, что лежит в ячейке, и понимает русскую А', async () => {
        renderSlot('А1');
        expect(await screen.findByText('Хондроитин сульфат')).toBeInTheDocument();
        expect(screen.queryByText('Ведро 2 литра')).not.toBeInTheDocument();
    });

    it('предлагает непросроченную серию, не даёт взять больше остатка и выдаёт одним перемещением', async () => {
        const user = userEvent.setup();
        renderSlot('А1');
        await user.click(await screen.findByRole('button', { name: 'Взять Хондроитин сульфат' }));

        const sheet = within(screen.getByRole('dialog', { name: 'Взять со склада' }));
        expect(sheet.getByRole('radio', { name: /GN2508029/ })).toHaveAttribute('aria-checked', 'true');

        const amount = sheet.getByRole('textbox');
        await user.type(amount, '1200');
        expect(sheet.getByText(/На полке только/)).toBeInTheDocument();
        expect(sheet.getByRole('button', { name: 'В корзину' })).toBeDisabled();

        await user.clear(amount);
        await user.type(amount, '250,5');
        await user.click(sheet.getByRole('button', { name: 'В корзину' }));

        await user.click(await screen.findByRole('button', { name: 'Выдать' }));
        const cart = within(screen.getByRole('dialog', { name: 'Выдача на производство' }));
        await user.click(cart.getByRole('button', { name: /Выдать 1 позицию/ }));

        const body = rawMaterialsApi.issue.mock.calls[0][0];
        expect(body.lines).toEqual([{ batch: 12, quantity: 250.5, slot: 'А1' }]);
        expect(body.key).toMatch(/^[0-9a-f-]{36}$/);
        expect(await cart.findByText('Перемещение 00285 проведено')).toBeInTheDocument();
    });

    it('ошибку МойСклад показывает и оставляет корзину с тем же ключом', async () => {
        rawMaterialsApi.issue.mockRejectedValueOnce(new Error('МойСклад не принял перемещение: нет в ячейке'));
        const user = userEvent.setup();
        renderSlot('C2');
        await user.click(await screen.findByRole('button', { name: 'Взять Ведро 2 литра' }));
        const sheet = within(screen.getByRole('dialog', { name: 'Взять со склада' }));
        await user.type(sheet.getByRole('textbox'), '10');
        await user.click(sheet.getByRole('button', { name: 'В корзину' }));
        await user.click(await screen.findByRole('button', { name: 'Выдать' }));

        const cart = within(screen.getByRole('dialog', { name: 'Выдача на производство' }));
        await user.click(cart.getByRole('button', { name: /Выдать 1 позицию/ }));
        expect(await cart.findByText(/нет в ячейке/)).toBeInTheDocument();

        await user.click(cart.getByRole('button', { name: /Выдать 1 позицию/ }));
        const [first, second] = rawMaterialsApi.issue.mock.calls.map(([body]) => body.key);
        expect(second).toBe(first);
    });

    it('сырьё видно и во второй ячейке, и выдаётся оттуда', async () => {
        const user = userEvent.setup();
        renderSlot('A6');
        await user.click(await screen.findByRole('button', { name: 'Взять Хондроитин сульфат' }));
        const sheet = within(screen.getByRole('dialog', { name: 'Взять со склада' }));
        await user.type(sheet.getByRole('textbox'), '0,1');
        await user.click(sheet.getByRole('button', { name: 'В корзину' }));
        await user.click(screen.getByRole('button', { name: 'Взять Хондроитин сульфат' }));
        await user.type(within(screen.getByRole('dialog', { name: 'Взять со склада' })).getByRole('textbox'), '0,2');
        await user.click(within(screen.getByRole('dialog', { name: 'Взять со склада' })).getByRole('button', { name: 'В корзину' }));

        await user.click(await screen.findByRole('button', { name: 'Выдать' }));
        const cart = within(screen.getByRole('dialog', { name: 'Выдача на производство' }));
        await user.click(cart.getByRole('button', { name: /Выдать 1 позицию/ }));
        expect(rawMaterialsApi.issue.mock.calls[0][0].lines).toEqual([{ batch: 12, quantity: 0.3, slot: 'A6' }]);
    });

    it('после выдачи в корзине остаётся только то, что не вошло в перемещение', async () => {
        localStorage.setItem('raw-materials-issue-cart', JSON.stringify({
            key: 'old-key',
            lines: [
                { batch: 12, name: 'Хондроитин сульфат', uom: 'г', slot: 'А1', quantity: 100 },
                { batch: 21, name: 'Ведро 2 литра', uom: 'шт', slot: 'C2', quantity: 5 },
            ],
        }));
        rawMaterialsApi.issue.mockResolvedValueOnce({
            id: 1, moysklad_name: '00285', description: 'Иван Петров, выдача сырья', moysklad_url: '#',
            lines: [{ id: 1, batch: 12, name: 'Хондроитин сульфат', uom: 'г', quantity: 100 }],
        });
        const user = userEvent.setup();
        renderSlot('А1');
        await user.click(await screen.findByRole('button', { name: 'Выдать' }));
        const cart = within(screen.getByRole('dialog', { name: 'Выдача на производство' }));
        await user.click(cart.getByRole('button', { name: /Выдать 2 позиции/ }));

        expect(await cart.findByText(/В корзине осталось 1 позиция/)).toBeInTheDocument();
        const saved = JSON.parse(localStorage.getItem('raw-materials-issue-cart'));
        expect(saved.lines.map((l) => l.batch)).toEqual([21]);
        expect(saved.key).not.toBe('old-key');
    });

    it('на неизвестную ячейку говорит, что её нет', async () => {
        renderSlot('Z9');
        expect(await screen.findByText('Такой ячейки нет')).toBeInTheDocument();
    });
});
