import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import SiteOrdersTable from './SiteOrdersTable';

vi.mock('../../api/siteOrdersApi', () => ({
    siteOrdersApi: { remove: vi.fn(), cancelOzon: vi.fn() },
}));

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


describe('SiteOrdersTable — доставка Ozon', () => {
    const OZON = {
        quote_id: 'f91bf49c-078d-4fec-8096-09bc49638a6a',
        status: 'ordered', status_label: 'Заказ создан в Ozon',
        order_number: '34742020-0375', posting_number: '34742020-0375-1',
        posting_status: 'awaiting_packaging', delivery_cost: 97,
        needs_attention: false, cancellable: true,
    };

    // У обычных заказов доставки Ozon нет — колонка должна молчать, а не
    // сообщать «нет доставки».
    it('у заказа без доставки Ozon чипа нет', () => {
        renderTable({});

        expect(screen.queryByText(/Ozon:/)).not.toBeInTheDocument();
    });

    // Чип живёт в своей колонке: в общей ячейке со статусом он съезжал,
    // а у заказов без доставки Ozon колонка просто пустая.
    it('в таблице есть колонка «Доставка»', () => {
        renderTable({ ozon: OZON });

        expect(screen.getByText('Доставка')).toBeInTheDocument();
    });

    it('показывает статус отправления, а не расчёта', () => {
        renderTable({ ozon: OZON });

        expect(screen.getByText('Ozon: Ожидает сборки')).toBeInTheDocument();
    });

    it('в подсказке — номер отправления и стоимость логистики', () => {
        renderTable({ ozon: OZON });

        expect(screen.getByText('34742020-0375-1')).toBeInTheDocument();
        expect(screen.getByText('97 ₽')).toBeInTheDocument();
    });

    it('пока заказ живой — кнопка отмены есть', () => {
        renderTable({ ozon: OZON });

        expect(screen.getByText('Отменить доставку Ozon')).toBeInTheDocument();
    });

    it('у доставленного заказа отменять нечего', () => {
        renderTable({ ozon: { ...OZON, posting_status: 'delivered', cancellable: false } });

        expect(screen.getByText('Ozon: Доставлено')).toBeInTheDocument();
        expect(screen.queryByText('Отменить доставку Ozon')).not.toBeInTheDocument();
    });

    // Статусов у Ozon больше, чем в словаре подписей: незнакомый должен
    // остаться собой, а не превратиться в подпись расчёта.
    it('незнакомый статус отправления показывается как есть', () => {
        renderTable({ ozon: { ...OZON, posting_status: 'arbitration' } });

        expect(screen.getByText('Ozon: arbitration')).toBeInTheDocument();
        expect(screen.queryByText(/Заказ создан в Ozon/)).not.toBeInTheDocument();
    });

    it('без отправления показывается состояние расчёта', () => {
        renderTable({
            ozon: { ...OZON, posting_number: null, posting_status: null },
        });

        expect(screen.getByText('Ozon: Заказ создан в Ozon')).toBeInTheDocument();
    });

    it('невыкуп подсвечивается как проблема', () => {
        renderTable({
            ozon: { ...OZON, posting_status: 'not_accepted', needs_attention: true, cancellable: false },
        });

        expect(screen.getByText('Ozon: Не принято').closest('.chip')).toHaveClass('err');
    });
});
