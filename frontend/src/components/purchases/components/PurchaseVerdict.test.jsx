import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import PurchaseVerdict, { pickRecommendedSupplier } from './PurchaseVerdict';

describe('pickRecommendedSupplier', () => {
    it('без рекомендаций возвращает null', () => {
        expect(pickRecommendedSupplier([])).toBeNull();
        expect(pickRecommendedSupplier()).toBeNull();
    });

    it('приоритет поставщику с валидной партией (ненулевая цена)', () => {
        const recs = [
            { supplier_name: 'A', reliability: 1, optimal_batch: 0 },     // нулевая цена — партия не рассчитана
            { supplier_name: 'B', reliability: 0.8, optimal_batch: 500 },
        ];
        expect(pickRecommendedSupplier(recs).supplier_name).toBe('B');
    });

    it('среди валидных — по надёжности, при равенстве по сроку поставки', () => {
        const recs = [
            { supplier_name: 'A', reliability: 0.9, lead_time: 10, optimal_batch: 100 },
            { supplier_name: 'B', reliability: 0.9, lead_time: 3, optimal_batch: 100 },
            { supplier_name: 'C', reliability: 1.0, lead_time: 20, optimal_batch: 100 },
        ];
        expect(pickRecommendedSupplier(recs).supplier_name).toBe('C'); // выше надёжность
        expect(pickRecommendedSupplier(recs.slice(0, 2)).supplier_name).toBe('B'); // равная надёжность → меньший срок
    });

    it('если валидных партий нет — выбирает по надёжности', () => {
        const recs = [
            { supplier_name: 'A', reliability: 0.5, optimal_batch: 0 },
            { supplier_name: 'B', reliability: 0.9, optimal_batch: 0 },
        ];
        expect(pickRecommendedSupplier(recs).supplier_name).toBe('B');
    });

    it('не мутирует исходный массив', () => {
        const recs = [
            { supplier_name: 'A', reliability: 0.5, optimal_batch: 100 },
            { supplier_name: 'B', reliability: 0.9, optimal_batch: 100 },
        ];
        pickRecommendedSupplier(recs);
        expect(recs[0].supplier_name).toBe('A');
    });
});

describe('PurchaseVerdict', () => {
    const material = { uom: 'г' };

    it('не рендерится без точки заказа', () => {
        const { container } = render(
            <PurchaseVerdict analysisData={{ general_calculations: {} }} material={material} />
        );
        expect(container).toBeEmptyDOMElement();
    });

    it('показывает точку заказа и рекомендованного поставщика', () => {
        const analysisData = {
            general_calculations: {
                reorder_point: { value: 1318982 },
                optimal_order_quantity: { value: 1069120 },
            },
            recommendations: [
                { supplier_name: 'ООО "МСД кемикалс"', reliability: 1, lead_time: 9, optimal_batch: 1069120 },
                { supplier_name: 'ООО "ФПК "МИКАХИМ"', reliability: 1, lead_time: 0, optimal_batch: 0 },
            ],
        };
        const { container } = render(<PurchaseVerdict analysisData={analysisData} material={material} />);
        expect(container.textContent).toMatch(/Рекомендация/);
        expect(container.textContent).toMatch(/Заказывайте, когда остаток упадёт до/);
        expect(container.textContent).toMatch(/МСД кемикалс/);          // поставщик с валидной ценой
        expect(container.textContent).toMatch(/надёжность 100%/);
        expect(container.textContent).not.toMatch(/МИКАХИМ/);           // нулевая цена — не рекомендуем
    });

    it('без поставщиков даёт общий вывод по партии', () => {
        const analysisData = {
            general_calculations: {
                reorder_point: { value: 5000 },
                optimal_order_quantity: { value: 2000 },
            },
            recommendations: [],
        };
        const { container } = render(<PurchaseVerdict analysisData={analysisData} material={material} />);
        expect(container.textContent).toMatch(/Оптимальная партия/);
    });
});
