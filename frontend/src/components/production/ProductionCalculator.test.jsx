import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ProductionCalculator from './ProductionCalculator';
import { productionApi } from '../../api/productionApi';

vi.mock('../../api/productionApi', () => ({
    productionApi: {
        searchProducts: vi.fn(),
        calculateFromItems: vi.fn(),
        calculateFromFile: vi.fn(),
        export: vi.fn(),
    },
}));

// Компонент работает с сырым fetch Response — эмулируем минимально необходимое
const jsonResponse = (data, ok = true) => ({
    ok,
    headers: { get: () => 'application/json' },
    json: async () => data,
});

const PRODUCT = { article: 'HB-001', name: 'Шампунь для лошадей', has_processing_plan: true };

const CALC_RESULT = {
    success: true,
    products_found: 1,
    products_not_found: 0,
    products_without_processing_plan: 0,
    components_summary: [
        { material_id: 'm1', material_name: 'Основа моющая', uom: 'кг', total_quantity: 7.5 },
        { material_id: 'm2', material_name: 'Флакон 500мл', uom: 'шт', total_quantity: 3 },
    ],
    products: [
        {
            article: 'HB-001', name: 'Шампунь для лошадей', quantity: 3,
            found: true, has_processing_plan: true, processing_plan_name: 'ТК Шампунь',
            components: [
                { material_id: 'm1', material_name: 'Основа моющая', uom: 'кг', quantity_per_recipe: 2.5, total_quantity: 7.5 },
            ],
        },
    ],
};

async function addProduct(user) {
    productionApi.searchProducts.mockResolvedValue({ success: true, products: [PRODUCT] });
    await user.type(screen.getByPlaceholderText('Поиск по артикулу или названию...'), 'шамп');
    await user.click(await screen.findByText('Шампунь для лошадей'));
}

beforeEach(() => vi.clearAllMocks());

describe('ProductionCalculator — подбор товаров', () => {
    it('поиск находит товар и добавляет его в таблицу', async () => {
        const user = userEvent.setup();
        render(<ProductionCalculator />);
        await addProduct(user);
        expect(screen.getByText('HB-001')).toBeInTheDocument();
        expect(screen.getByText('Рассчитать компоненты')).toBeInTheDocument();
    });

    it('повторное добавление того же товара не создаёт дубль', async () => {
        const user = userEvent.setup();
        render(<ProductionCalculator />);
        await addProduct(user);
        // имя товара теперь есть и в таблице, и в выпадашке — кликаем именно по выпадашке
        await user.type(screen.getByPlaceholderText('Поиск по артикулу или названию...'), 'шамп');
        await waitFor(() => expect(screen.getAllByText('Шампунь для лошадей')).toHaveLength(2));
        await user.click(screen.getAllByText('Шампунь для лошадей')[0]);
        expect(await screen.findByText('Этот товар уже добавлен')).toBeInTheDocument();
        expect(screen.getAllByRole('spinbutton')).toHaveLength(1); // строка в таблице одна
    });
});

describe('ProductionCalculator — расчёт', () => {
    it('отправляет позиции с количеством и показывает сводку компонентов', async () => {
        const user = userEvent.setup();
        render(<ProductionCalculator />);
        await addProduct(user);

        const qty = screen.getByRole('spinbutton');
        await user.clear(qty);
        await user.type(qty, '3');

        productionApi.calculateFromItems.mockResolvedValue(jsonResponse(CALC_RESULT));
        await user.click(screen.getByText('Рассчитать компоненты'));

        expect(productionApi.calculateFromItems).toHaveBeenCalledWith([{ article: 'HB-001', quantity: 3 }]);
        expect(await screen.findByText('Основа моющая')).toBeInTheDocument();
        expect(screen.getByText('Флакон 500мл')).toBeInTheDocument();
        expect(screen.getByText('7,5')).toBeInTheDocument(); // числа в русском формате
        expect(screen.getByText(/Сводка компонентов \(2\)/)).toBeInTheDocument();
    });

    it('строка товара раскрывается и показывает состав по техкарте', async () => {
        const user = userEvent.setup();
        render(<ProductionCalculator />);
        await addProduct(user);
        productionApi.calculateFromItems.mockResolvedValue(jsonResponse(CALC_RESULT));
        await user.click(screen.getByText('Рассчитать компоненты'));

        await user.click(await screen.findByText('ТК Шампунь'));
        expect(screen.getByText('на ед.: 2,5')).toBeInTheDocument();
        expect(screen.getByText('итого: 7,5')).toBeInTheDocument();
    });

    it('нулевое количество не отправляется на сервер', async () => {
        const user = userEvent.setup();
        render(<ProductionCalculator />);
        await addProduct(user);
        await user.clear(screen.getByRole('spinbutton'));
        await user.click(screen.getByText('Рассчитать компоненты'));
        expect(await screen.findByText('Укажите количество для товаров')).toBeInTheDocument();
        expect(productionApi.calculateFromItems).not.toHaveBeenCalled();
    });

    it('ошибка сервера показывает понятное уведомление', async () => {
        const user = userEvent.setup();
        render(<ProductionCalculator />);
        await addProduct(user);
        productionApi.calculateFromItems.mockResolvedValue(jsonResponse({ success: false, error: 'Техкарты не найдены' }, false));
        await user.click(screen.getByText('Рассчитать компоненты'));
        expect(await screen.findByText('Техкарты не найдены')).toBeInTheDocument();
    });
});
