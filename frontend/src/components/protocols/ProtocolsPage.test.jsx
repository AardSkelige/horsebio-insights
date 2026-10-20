import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import ProtocolsPage from './ProtocolsPage';

vi.mock('../../api/protocolsApi', () => ({
    protocolsApi: { tasks: vi.fn(), task: vi.fn(), docx: vi.fn(), linkTemplate: vi.fn(), linkMaterial: vi.fn() },
}));

import { protocolsApi } from '../../api/protocolsApi';

const row = (overrides) => ({
    row_name: 'Хондроитин сульфат', material_id: 'm-ch', material_name: 'Хондроитин сульфат', uom: 'г', qty: 2310,
    series: 'OLD', expiry_date: '2027-01-01', manufacturer: 'QINGDAO', source: 'issued', expired: false,
    options: [
        { series: 'OLD', expiry_date: '2027-01-01', manufacturer: 'QINGDAO', source: 'stock' },
        { series: 'NEW', expiry_date: '2028-01-01', manufacturer: 'QINGDAO', source: 'stock' },
    ],
    ...overrides,
});

const TASK = {
    task: { id: 't-1', name: '00689', moment: '2026-10-20' },
    templates: [{ id: 1, title: 'Хондро' }, { id: 2, title: 'Коллаген' }],
    variants: [{
        template: { id: 1, title: 'Хондро' },
        plan_ids: ['p-1'], plans: ['Хондро 600 г'],
        products: [{ source_name: 'Хондро 600 г', qty: 20 }],
        rows: [
            row(),
            row({ row_name: 'Ароматизатор', material_id: 'm-fl', qty: 90, series: '25095796', expiry_date: '2026-09-23', options: [] }),
        ],
        unplaced: [{ material_id: 'm-bucket', name: 'Ведро 2 литра', qty: 20, is_tara: true }],
    }],
};

const renderAt = (path) => render(
    <MemoryRouter initialEntries={[path]}>
        <Routes>
            <Route path="/protocols" element={<ProtocolsPage />} />
            <Route path="/protocols/:taskId" element={<ProtocolsPage />} />
        </Routes>
    </MemoryRouter>,
);

describe('Протоколы', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        protocolsApi.tasks.mockResolvedValue({ tasks: [{ id: 't-1', name: '00689', moment: '2026-10-20', state: 'подготовка', description: 'Рыбный коллаген 500' }] });
        protocolsApi.task.mockResolvedValue(TASK);
        protocolsApi.docx.mockResolvedValue(new Blob(['PK']));
        window.URL.createObjectURL = vi.fn(() => 'blob:x');
        window.URL.revokeObjectURL = vi.fn();
    });

    it('показывает задания из МойСклад со ссылкой на протокол', async () => {
        renderAt('/protocols');
        const link = await screen.findByRole('link', { name: /00689/ });
        expect(link).toHaveAttribute('href', '/protocols/t-1');
    });

    it('подсвечивает просроченную серию', async () => {
        renderAt('/protocols/t-1');
        expect(await screen.findByText('Просрочена 23.09.2026')).toBeInTheDocument();
    });

    it('скачивает протокол с выбранной серией', async () => {
        renderAt('/protocols/t-1');
        await userEvent.selectOptions(await screen.findByRole('combobox', { name: 'Серия: Хондроитин сульфат' }), 'NEW|2028-01-01');
        await userEvent.click(screen.getByRole('button', { name: /Скачать Word/ }));
        const [, variant, rows] = protocolsApi.docx.mock.calls[0];
        expect(variant).toBe(0);
        expect(rows[0].series).toBe('NEW');
    });

    it('запоминает выбранный шаблон для техкарты', async () => {
        protocolsApi.linkTemplate.mockResolvedValue({ ok: true });
        renderAt('/protocols/t-1');
        await userEvent.selectOptions(await screen.findByRole('combobox', { name: 'Шаблон протокола' }), '2');
        expect(protocolsApi.linkTemplate).toHaveBeenCalledWith(2, [{ id: 'p-1', name: 'Хондро 600 г' }]);
    });

    it('тару без строки в шаблоне не выдаёт за ошибку', async () => {
        renderAt('/protocols/t-1');
        await screen.findByText('Хондро 600 г', { exact: false });
        expect(within(document.body).queryByText(/Нет строки в шаблоне/)).not.toBeInTheDocument();
    });

    it('пустой пункт шаблона ничего не меняет', async () => {
        renderAt('/protocols/t-1');
        await userEvent.selectOptions(await screen.findByRole('combobox', { name: 'Шаблон протокола' }), '');
        expect(protocolsApi.linkTemplate).not.toHaveBeenCalled();
    });

    it('показывает причину, если протокол не собрался', async () => {
        protocolsApi.docx.mockRejectedValue(new Error('Количество «1.2.3» не число'));
        renderAt('/protocols/t-1');
        await userEvent.click(await screen.findByRole('button', { name: /Скачать Word/ }));
        expect(await screen.findByText('Количество «1.2.3» не число')).toBeInTheDocument();
    });
});
