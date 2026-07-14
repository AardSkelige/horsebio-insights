import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Layout from './Layout';

vi.mock('../../contexts/DataPanelContext', () => ({
    useDataPanel: () => ({ open: false, close: vi.fn() }),
}));
vi.mock('../../hooks/usePageTracking', () => ({ usePageTracking: () => {} }));
vi.mock('../common/FloatingLoadingCard', () => ({ default: () => null }));
vi.mock('../home/components/DataManagementCard', () => ({ default: () => null }));
vi.mock('./Sidebar', () => ({
    default: ({ mobileOpen }) => <div data-testid="sidebar" data-mobile-open={String(mobileOpen)} />,
}));

const setViewportWidth = (width) => {
    Object.defineProperty(window, 'innerWidth', { value: width, writable: true, configurable: true });
};

const renderLayout = () => render(
    <MemoryRouter>
        <Layout><div>контент</div></Layout>
    </MemoryRouter>
);

const sidebarOpen = () => screen.getByTestId('sidebar').dataset.mobileOpen === 'true';

const swipe = (fromX, toX, y = 300) => {
    fireEvent.touchStart(document, { touches: [{ clientX: fromX, clientY: y }] });
    fireEvent.touchMove(document, { touches: [{ clientX: toX, clientY: y }] });
    fireEvent.touchEnd(document, { touches: [] });
};

describe('Layout — мобильный сайдбар', () => {
    beforeEach(() => setViewportWidth(500));

    it('по умолчанию закрыт, кнопка-бургер открывает', async () => {
        const user = userEvent.setup();
        renderLayout();
        expect(sidebarOpen()).toBe(false);
        await user.click(screen.getByRole('button', { name: 'Открыть меню' }));
        expect(sidebarOpen()).toBe(true);
    });

    it('свайп от левого края НЕ открывает сайдбар (край отдан iOS-жесту «назад»)', () => {
        renderLayout();
        swipe(5, 150);
        expect(sidebarOpen()).toBe(false);
    });

    it('свайп влево закрывает открытый сайдбар', async () => {
        const user = userEvent.setup();
        renderLayout();
        await user.click(screen.getByRole('button', { name: 'Открыть меню' }));
        expect(sidebarOpen()).toBe(true);
        swipe(250, 100);
        expect(sidebarOpen()).toBe(false);
    });

    it('вертикальный скролл не закрывает сайдбар', async () => {
        const user = userEvent.setup();
        renderLayout();
        await user.click(screen.getByRole('button', { name: 'Открыть меню' }));
        fireEvent.touchStart(document, { touches: [{ clientX: 250, clientY: 100 }] });
        fireEvent.touchMove(document, { touches: [{ clientX: 180, clientY: 400 }] });
        fireEvent.touchEnd(document, { touches: [] });
        expect(sidebarOpen()).toBe(true);
    });

    it('на десктопе мобильной шапки нет', () => {
        setViewportWidth(1200);
        renderLayout();
        expect(screen.queryByRole('button', { name: 'Открыть меню' })).not.toBeInTheDocument();
    });
});
