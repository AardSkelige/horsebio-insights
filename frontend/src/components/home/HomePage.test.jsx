import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import HomePage from './HomePage';
import { authApi } from '../../api/authApi';

const openPanel = vi.fn();
let auth;
let notifications;

vi.mock('../../api/authApi', () => ({
    authApi: { home: vi.fn() },
}));

vi.mock('../../hooks/useAuthStatus', () => ({
    useAuthStatus: () => auth,
}));

vi.mock('../../contexts/NotificationsContext', () => ({
    useNotifications: () => ({ ...notifications, openPanel }),
}));

vi.mock('../../contexts/LoadingContext', () => ({
    useLoading: () => ({ isLoading: false, syncVersion: 0 }),
}));

vi.mock('./components/PulseChart', () => ({
    default: ({ label }) => <div data-testid="pulse">{label}</div>,
}));

const item = (overrides = {}) => ({
    key: 'raw:1',
    source: 'raw-materials',
    source_label: 'Склад сырья',
    route: '/raw-materials',
    level: 'critical',
    title: 'Серия Л-0912 просрочена',
    body: 'На ячейке Б-14 лежит 6,4 кг',
    action: 'Спишите серию.',
    seen: false,
    ...overrides,
});

const homeData = (overrides = {}) => ({
    data: {
        sectionVisits: {},
        pulse: { label: 'Отгрузки за 30 дней', unit: '₽', points: [] },
        frequentPaths: ['/inventory'],
        dataUpdatedAt: '2026-10-24T14:20:00+03:00',
        ...overrides,
    },
});

const renderPage = () => render(
    <MemoryRouter>
        <HomePage />
    </MemoryRouter>
);

describe('HomePage', () => {
    beforeEach(() => {
        auth = { isSuperuser: false, firstName: 'Иван', allowedPages: ['raw-materials', 'inventory', 'protocols'] };
        notifications = {
            items: [
                item(),
                item({ key: 'd:1', source: 'deadlines', source_label: 'Сроки оплаты', route: '/deadlines', level: 'warning', title: 'Оплата скоро' }),
                item({ key: 'd:2', source: 'deadlines', level: 'info', title: 'К сведению' }),
            ],
            bySource: {},
            complete: true,
            loaded: true,
        };
        openPanel.mockClear();
        authApi.home.mockResolvedValue(homeData());
    });

    it('показывает самое серьёзное непрочитанное и ведёт в его раздел', async () => {
        renderPage();

        expect(await screen.findByRole('heading', { level: 1, name: 'Серия Л-0912 просрочена' })).toBeInTheDocument();
        expect(screen.getByText('На ячейке Б-14 лежит 6,4 кг. Спишите серию.')).toBeInTheDocument();
        expect(screen.getByRole('link', { name: /Открыть: Склад сырья/ })).toHaveAttribute('href', '/raw-materials');

        fireEvent.click(screen.getByRole('button', { name: 'Ещё 2 дела' }));
        expect(openPanel).toHaveBeenCalled();
    });

    it('при равной серьёзности берёт раздел, который человек открывает чаще', async () => {
        notifications.items = [
            item({ level: 'warning', title: 'Приёмка без серий' }),
            item({ key: 'd:1', source: 'deadlines', level: 'warning', title: 'Оплата скоро' }),
        ];
        authApi.home.mockResolvedValue(homeData({ sectionVisits: { deadlines: 5, 'raw-materials': 1 } }));
        renderPage();

        expect(await screen.findByRole('heading', { level: 1, name: 'Оплата скоро' })).toBeInTheDocument();
    });

    it('прочитанное сразу уходит из главной фразы', async () => {
        notifications.items[0] = item({ seen: true });
        renderPage();

        expect(await screen.findByRole('heading', { level: 1, name: 'Оплата скоро' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Ещё 1 дело' })).toBeInTheDocument();
    });

    it('в спокойный день говорит, что ничего не горит', async () => {
        notifications.items = [];
        renderPage();

        expect(await screen.findByRole('heading', { level: 1, name: 'Сегодня ничего не горит' })).toBeInTheDocument();
        expect(screen.queryByRole('link', { name: /Открыть:/ })).not.toBeInTheDocument();
    });

    it('прочитанное не прячет нерешённое', async () => {
        notifications.items = notifications.items.map((one) => ({ ...one, seen: true }));
        renderPage();

        expect(await screen.findByRole('heading', { level: 1, name: 'Новых дел нет' })).toBeInTheDocument();
        expect(screen.getByText('Прочитанные ещё не решены: 3, из них критичных 1.')).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: 'Показать прочитанные' }));
        expect(openPanel).toHaveBeenCalledWith({ showRead: true });
    });

    it('если раздел не ответил, не говорит, что всё спокойно', async () => {
        notifications.items = [];
        notifications.complete = false;
        renderPage();

        expect(await screen.findByRole('heading', { level: 1, name: 'Не все разделы ответили' })).toBeInTheDocument();
    });

    it('пока уведомления не пришли, ничего не утверждает', async () => {
        notifications.items = [];
        notifications.loaded = false;
        const { container } = renderPage();

        await act(async () => {});
        expect(authApi.home).toHaveBeenCalled();
        expect(screen.queryByRole('heading', { level: 1 })).not.toBeInTheDocument();
        expect(container.querySelector('[aria-busy="true"]')).toBeInTheDocument();
    });

    it('пока главная грузится, на месте пульса стоит заготовка', async () => {
        auth.allowedPages.push('shipments-products');
        authApi.home.mockReturnValue(new Promise(() => {}));
        const { container } = renderPage();

        await act(async () => {});
        expect(container.querySelector('.home-pulse--wait')).toBeInTheDocument();
        expect(screen.queryByTestId('pulse')).not.toBeInTheDocument();
    });

    it('без доступа к отгрузкам заготовку пульса не показывает', async () => {
        authApi.home.mockReturnValue(new Promise(() => {}));
        const { container } = renderPage();

        await act(async () => {});
        expect(container.querySelector('.home-pulse--wait')).not.toBeInTheDocument();
    });

    it('пульс рисуется, не дожидаясь уведомлений', async () => {
        notifications.loaded = false;
        renderPage();

        expect(await screen.findByTestId('pulse')).toBeInTheDocument();
        expect(screen.queryByRole('heading', { level: 1 })).not.toBeInTheDocument();
    });

    it('рисует пульс, только когда сервер его отдал', async () => {
        authApi.home.mockResolvedValue(homeData({ pulse: null }));
        renderPage();

        await screen.findByRole('heading', { level: 1 });
        expect(screen.queryByTestId('pulse')).not.toBeInTheDocument();
    });

    it('внизу частые разделы, добранные доступными до трёх', async () => {
        notifications.bySource = { inventory: { total: 4 } };
        renderPage();

        const nav = await screen.findByRole('navigation', { name: 'Мои разделы' });
        const links = nav.querySelectorAll('a');
        expect([...links].map((link) => link.getAttribute('href'))).toEqual(['/inventory', '/raw-materials', '/protocols']);
        expect(screen.getByText('4 дела')).toBeInTheDocument();
    });

    it('при ошибке не делает вид, что всё спокойно', async () => {
        authApi.home.mockRejectedValueOnce(new Error('500'));
        renderPage();

        expect(await screen.findByText('Не удалось загрузить главную')).toBeInTheDocument();
        expect(screen.queryByText('Сегодня ничего не горит')).not.toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', { name: /Попробовать ещё раз/ }));
        expect(await screen.findByRole('heading', { level: 1, name: 'Серия Л-0912 просрочена' })).toBeInTheDocument();
    });
});
