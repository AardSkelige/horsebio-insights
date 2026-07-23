import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import HomePage from './HomePage';
import { authApi } from '../../api/authApi';
import { inventoryApi } from '../../api/inventoryApi';
import { checksApi } from '../checks/checksShared';

vi.mock('../../api/authApi', () => ({
    authApi: { check: vi.fn(), home: vi.fn(), updateHome: vi.fn() },
}));

vi.mock('../../api/inventoryApi', () => ({
    inventoryApi: { getCurrent: vi.fn() },
}));

vi.mock('../../api/deadlinesApi', () => ({
    deadlinesApi: { get: vi.fn() },
}));

vi.mock('../checks/checksShared', () => ({
    checksApi: { overview: vi.fn() },
}));

vi.mock('../../contexts/LoadingContext', () => ({
    useLoading: () => ({ isLoading: false, syncVersion: 0 }),
}));

const renderPage = () => render(
    <MemoryRouter>
        <HomePage />
    </MemoryRouter>
);

describe('HomePage', () => {
    beforeEach(() => {
        authApi.check.mockResolvedValue({
            isSuperuser: false,
            username: 'lilia',
            firstName: 'Лиля',
        });
        authApi.home.mockResolvedValue({
            data: {
                pinnedPaths: [],
                recentPaths: ['/inventory', '/analysis/abc'],
                dataUpdatedAt: '2026-07-18T09:00:00+03:00',
            },
        });
        authApi.updateHome.mockImplementation((pinnedPaths) => Promise.resolve({
            data: { pinnedPaths, recentPaths: [], dataUpdatedAt: null },
        }));
        inventoryApi.getCurrent.mockResolvedValue({
            status: 'success',
            data: { inventoried: 18, total: 24 },
        });
        checksApi.overview.mockResolvedValue({ scripts: [] });
    });

    it('сохраняет визуальное деление ссылок по рабочим разделам', async () => {
        renderPage();

        expect(screen.getByRole('heading', { level: 2, name: 'Отгрузки' })).toBeInTheDocument();
        expect(screen.getByRole('heading', { level: 2, name: 'Заказы сайта' })).toBeInTheDocument();
        expect(screen.getByRole('heading', { level: 2, name: 'Приёмки' })).toBeInTheDocument();
        expect(screen.getByRole('heading', { level: 2, name: 'Производство' })).toBeInTheDocument();
        expect(screen.getByRole('heading', { level: 2, name: 'Инвентаризация' })).toBeInTheDocument();
        expect(screen.getByRole('heading', { level: 2, name: 'Аналитика' })).toBeInTheDocument();
        expect(await screen.findByRole('heading', { level: 1, name: /Лиля/ })).toBeInTheDocument();
        expect(screen.getAllByRole('link')).toHaveLength(21);
        expect(screen.getAllByRole('link', { name: /Товары/ })[0]).toHaveAttribute('href', '/shipments/products');
        expect(screen.getAllByRole('link', { name: /ABC Анализ/ })[0]).toHaveAttribute('href', '/analysis/abc');
        expect(await screen.findByText('Поставщики')).toBeInTheDocument();
        expect(await screen.findByText('18 из 24 позиций · 75%')).toBeInTheDocument();
    });

    it('добавляет проверки только суперпользователю', async () => {
        authApi.check.mockResolvedValue({ isSuperuser: true, allowedPages: [] });
        renderPage();

        expect((await screen.findAllByRole('link', { name: /Проверки/ }))[0]).toHaveAttribute('href', '/checks');
        expect(screen.getByRole('link', { name: /Аналитика системы/ })).toHaveAttribute('href', '/system/analytics');
        expect(screen.getAllByRole('link')).toHaveLength(24);
    });

    it('закрепляет раздел в персональной главной', async () => {
        renderPage();

        fireEvent.click(await screen.findByRole('button', { name: 'Закрепить Мониторинг' }));

        await waitFor(() => {
            expect(authApi.updateHome).toHaveBeenCalledWith(['/inventory']);
        });
        expect(screen.getByRole('button', { name: 'Открепить Мониторинг' })).toBeInTheDocument();
    });
});
