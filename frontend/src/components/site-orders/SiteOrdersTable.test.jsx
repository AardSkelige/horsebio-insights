import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import SiteOrdersTable from './SiteOrdersTable';

vi.mock('../../api/siteOrdersApi', () => ({ siteOrdersApi: { remove: vi.fn() } }));

const BASE_ROW = {
    order_id: '4428118', number: '2074', name: 'Алла Носова', phone: '+79630948363',
    date_label: '24.08 22:46', sum: 1313, status: 'paid', status_label: 'Оплачен и заведён',
    discount: 1500, discount_label: 'Кубок Конного парка, 1500 ₽',
};

function renderTable(row, isMobile = false) {
    render(
        <SiteOrdersTable
            rows={[{ ...BASE_ROW, ...row }]} loading={false}
            sort={{ key: 'date', dir: 'desc' }} onSortChange={() => {}} isMobile={isMobile}
        />,
    );
}

describe('SiteOrdersTable — скидка', () => {
    // Сумма в журнале — уже оплаченная, скидка в неё не видна: письмо шлёт цены
    // по прайсу, а итог со скидкой. Поэтому показываем её отдельной строкой.
    it('показывает размер скидки рядом с суммой', () => {
        renderTable({});

        expect(screen.getByText('−1 500 ₽')).toBeInTheDocument();
    });

    it('в подсказке — название купона', () => {
        renderTable({});

        expect(screen.getByText('−1 500 ₽')).toHaveAttribute('title', 'Кубок Конного парка, 1500 ₽');
    });

    it('без названия купона подсказки нет, сумма остаётся', () => {
        renderTable({ discount_label: '' });

        expect(screen.getByText('−1 500 ₽')).not.toHaveAttribute('title');
    });

    it('заказ без скидки ничего лишнего не рисует', () => {
        renderTable({ discount: 0, discount_label: '' });

        expect(screen.queryByText(/−/)).not.toBeInTheDocument();
    });

    it('на мобильной карточке скидка тоже видна', () => {
        renderTable({}, true);

        expect(screen.getByText('−1 500 ₽')).toBeInTheDocument();
    });
});
