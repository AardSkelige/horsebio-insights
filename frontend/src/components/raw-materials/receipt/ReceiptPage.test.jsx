import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import ReceiptPage from './ReceiptPage';
import ReceiptsPage from './ReceiptsPage';

vi.mock('../../../api/rawMaterialsApi', () => ({
    rawMaterialsApi: { receipts: vi.fn(), fillReceiptLine: vi.fn() },
}));

import { rawMaterialsApi } from '../../../api/rawMaterialsApi';

const line = (id, name, extra = {}) => ({
    id, name, uom: 'г', quantity: 400000, slot: 'A6', tara: false, filled: false,
    series: '', expiry_date: null, manufacturer: '', ...extra,
});

const payload = (lines) => ({
    stale: false,
    items: [{
        id: 7, name: '00150', moment: '2026-10-21T15:20:00+03:00', agent: 'ООО «Ревада-Нева»',
        lines, raw: lines.filter((l) => !l.tara).length, waiting: lines.filter((l) => !l.tara && !l.filled).length,
    }],
});

const LINES = [
    line(1, 'Глюкозамин гидрохлорид', { manufacturer: 'Shandong' }),
    line(2, 'Гиалуроновая кислота', { quantity: 2000, slot: 'B5' }),
    line(3, 'Крышка 110 мм', { uom: 'шт', quantity: 500, tara: true }),
];

const renderAt = (path) => render(
    <MemoryRouter initialEntries={[path]}>
        <Routes>
            <Route path="/raw-materials/receipts" element={<ReceiptsPage />} />
            <Route path="/raw-materials/receipts/:id" element={<ReceiptPage />} />
        </Routes>
    </MemoryRouter>,
);

describe('Приёмка', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        rawMaterialsApi.receipts.mockResolvedValue(payload(LINES));
    });

    it('в списке видно, сколько позиций ждут серий', async () => {
        renderAt('/raw-materials/receipts');
        expect(await screen.findByText('Ждёт серий · 2')).toBeInTheDocument();
        expect(screen.getByText(/Глюкозамин гидрохлорид 400 кг, Гиалуроновая кислота 2 кг, Крышка 110 мм 500 шт/)).toBeInTheDocument();
    });

    it('сохраняет только заполненные строки, производитель подставлен из прошлой серии, тара без полей', async () => {
        rawMaterialsApi.fillReceiptLine.mockResolvedValue(payload([
            { ...LINES[0], filled: true, series: '2025122709', expiry_date: '2028-12-26' }, LINES[1], LINES[2],
        ]));
        const user = userEvent.setup();
        renderAt('/raw-materials/receipts/7');

        const glucosamine = within((await screen.findByText('Глюкозамин гидрохлорид')).closest('.receipt__line'));
        expect(glucosamine.getByLabelText(/Производитель/)).toHaveValue('Shandong');
        expect(screen.getByText('Тара · серия не нужна')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Впишите серию и срок' })).toBeDisabled();

        await user.type(glucosamine.getByLabelText('Серия'), '2025122709');
        await user.type(glucosamine.getByLabelText('Годен до'), '2028-12-26');
        await user.click(screen.getByRole('button', { name: 'Сохранить 1 серию' }));

        expect(rawMaterialsApi.fillReceiptLine).toHaveBeenCalledTimes(1);
        expect(rawMaterialsApi.fillReceiptLine).toHaveBeenCalledWith(1, { series: '2025122709', expiry_date: '2028-12-26', manufacturer: 'Shandong' });
        expect(await glucosamine.findByText('Внесено')).toBeInTheDocument();
    });
});
