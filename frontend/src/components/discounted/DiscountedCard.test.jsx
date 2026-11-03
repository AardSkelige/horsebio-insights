import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import DiscountedCard from './DiscountedCard';

vi.mock('../../api/discountedApi', () => ({ discountedApi: { delist: vi.fn() } }));

const base = {
    id: 'p1', name: 'Уценка // Пробиотик', article: '06-04GP1600-UC', state: 'delist',
    days_left: 59, quantity: 29, price: 1456, price_full: 2080, sum: 42224,
    site_price: 1456, site_quantity: 29, ms_url: 'https://ms', site_url: 'https://site',
};

const renderCard = (position) => render(
    <DiscountedCard position={{ ...base, ...position }} delistMonths={2} discountRate={0.3} />,
);

describe('DiscountedCard: кнопка «Снять с продажи»', () => {
    it('есть, пока карточка на витрине', () => {
        renderCard({ published: true });
        expect(screen.getByRole('button', { name: /Снять с продажи/ })).toBeInTheDocument();
    });

    it('пропадает, когда карточки на витрине уже нет', () => {
        renderCard({ published: false });
        expect(screen.queryByRole('button', { name: /Снять с продажи/ })).not.toBeInTheDocument();
    });

    it('остаётся, если витрину проверить не удалось', () => {
        renderCard({ published: null });
        expect(screen.getByRole('button', { name: /Снять с продажи/ })).toBeInTheDocument();
    });
});
