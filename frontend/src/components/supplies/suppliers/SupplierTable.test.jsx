import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MotionProvider } from '../../ui/motion';
import SupplierTable from './SupplierTable';
import SupplierFilterPanel from './SupplierFilterPanel';

/** Таблица переехала на общий DataTable — проверяем, что колонки описаны верно. */
const ROWS = [
    {
        id: '1', name: 'ООО Ромашка', supplies_count: 12, positions_count: 40,
        unique_materials: 7, total_sum: 150000, avg_supply_sum: 12500,
        last_supply: '2026-03-14T10:00:00Z',
    },
];

const props = {
    suppliers: ROWS,
    loading: false,
    pagination: { current: 1, pageSize: 10, total: 1 },
    sortField: 'total_sum',
    sortOrder: 'desc',
    onSort: vi.fn(),
    onPageChange: vi.fn(),
    onSupplierClick: vi.fn(),
};

const withProvider = (ui) => render(<MotionProvider>{ui}</MotionProvider>);

describe('SupplierTable', () => {
    it('показывает все колонки строки', () => {
        withProvider(<SupplierTable {...props} />);

        expect(screen.getByText('ООО Ромашка')).toBeInTheDocument();
        expect(screen.getByText('150 000 ₽')).toBeInTheDocument();
        expect(screen.getByText('12 500 ₽')).toBeInTheDocument();
        expect(screen.getByText('14.03.2026')).toBeInTheDocument();
    });

    it('передаёт клик по строке наверх через кнопку «Детали»', async () => {
        const onSupplierClick = vi.fn();
        withProvider(<SupplierTable {...props} onSupplierClick={onSupplierClick} />);

        await userEvent.click(screen.getByRole('button', { name: /Детали/ }));
        expect(onSupplierClick).toHaveBeenCalledWith(ROWS[0]);
    });

    it('сортирует по клику на заголовок', async () => {
        const onSort = vi.fn();
        withProvider(<SupplierTable {...props} onSort={onSort} />);

        await userEvent.click(screen.getByText('Приёмок'));
        expect(onSort).toHaveBeenCalledWith('supplies_count');
    });
});

describe('SupplierFilterPanel', () => {
    it('сбрасывает фильтры целиком и показывает кнопку только при активных', async () => {
        const onChange = vi.fn();
        const { rerender } = render(
            <SupplierFilterPanel filters={{ search: '', startDate: null, endDate: null }} onChange={onChange} />,
        );
        expect(screen.queryByRole('button', { name: /Сбросить/ })).toBeNull();

        rerender(
            <SupplierFilterPanel
                filters={{ search: 'ромашка', startDate: '2026-01-01', endDate: null }}
                onChange={onChange}
            />,
        );
        await userEvent.click(screen.getByRole('button', { name: /Сбросить/ }));
        expect(onChange).toHaveBeenCalledWith({ search: '', startDate: null, endDate: null });
    });

    it('поиск отдаёт наверх введённое значение', async () => {
        const onChange = vi.fn();
        render(
            <SupplierFilterPanel filters={{ search: '', startDate: null, endDate: null }} onChange={onChange} />,
        );

        await userEvent.type(screen.getByPlaceholderText('Поиск поставщика'), 'р');
        expect(onChange).toHaveBeenCalledWith({ search: 'р', startDate: null, endDate: null });
    });
});
