import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

import NotificationItem from './NotificationItem';
import NotificationsPanel from './NotificationsPanel';
import NotificationsBell from './NotificationsBell';
import SectionNotifications from './SectionNotifications';

// Один общий поддельный контекст: компоненты уведомлений отличаются только
// обвязкой, а данные у всех берутся из него
const state = {
    items: [],
    counts: { total: 0, unseen: 0, critical: 0, warning: 0, info: 0 },
    bySource: {},
    loading: false,
    error: null,
    panelOpen: false,
    openPanel: vi.fn(),
    closePanel: vi.fn(),
    reload: vi.fn(),
    setRead: vi.fn(),
};

vi.mock('../../contexts/NotificationsContext', () => ({
    useNotifications: () => state,
    useSectionNotifications: (source) => ({
        items: state.items.filter((item) => item.source === source),
        loading: state.loading,
    }),
}));

const item = (overrides = {}) => ({
    key: 'discounted:delist:p1',
    source: 'discounted',
    source_label: 'Уценка',
    route: '/discounted',
    level: 'critical',
    title: 'Пробиотик 1600г — пора снимать с продажи',
    body: 'До конца срока 60 дн · на складе 32 шт',
    action: 'Выгрузите «Файл для сайта» и загрузите его в админке — карточка уйдёт с витрины',
    seen: false,
    ...overrides,
});

// Счётчики считаем так же, как сервер: level — по самому серьёзному
// непрочитанному, счётчики по уровням — по всему списку
const LEVELS = ['critical', 'warning', 'info'];

const withCounts = (items) => {
    const unread = items.filter((i) => !i.seen);
    return {
        items,
        counts: {
            total: items.length,
            unseen: unread.length,
            level: LEVELS.find((level) => unread.some((i) => i.level === level)) || null,
            critical: items.filter((i) => i.level === 'critical').length,
            warning: items.filter((i) => i.level === 'warning').length,
            info: items.filter((i) => i.level === 'info').length,
        },
    };
};

const setState = (patch) => Object.assign(state, patch);

beforeEach(() => {
    setState({ ...withCounts([]), bySource: {}, loading: false, error: null, panelOpen: false });
    state.openPanel = vi.fn();
    state.closePanel = vi.fn();
    state.reload = vi.fn();
    state.setRead = vi.fn();
});

const renderIn = (ui) => render(<MemoryRouter>{ui}</MemoryRouter>);

describe('NotificationItem', () => {
    it('в панели только уведомляет: что случилось и из каких цифр это видно', () => {
        renderIn(<NotificationItem item={item()} />);
        expect(screen.getByText(/пора снимать с продажи/)).toBeInTheDocument();
        expect(screen.getByText(/на складе 32 шт/)).toBeInTheDocument();
        // что делать — решают на странице раздела, а не в шторке
        expect(screen.queryByText(/Файл для сайта/)).not.toBeInTheDocument();
        expect(screen.queryByRole('link')).not.toBeInTheDocument();
    });

    it('строкой на странице раздела — заголовок и действие', () => {
        renderIn(<NotificationItem item={item()} variant="line" />);
        expect(screen.getByText(/пора снимать с продажи/)).toBeInTheDocument();
        expect(screen.getByText(/Файл для сайта/)).toBeInTheDocument();
        // цифры уже есть на карточке позиции рядом
        expect(screen.queryByText(/на складе 32 шт/)).not.toBeInTheDocument();
    });

    it('прочитанное видно и никуда не исчезает', () => {
        const { container } = renderIn(<NotificationItem item={item({ seen: true })} />);
        expect(screen.getByText(/пора снимать с продажи/)).toBeInTheDocument();
        expect(container.querySelector('.nt-item')).toHaveClass('nt-item--read');
    });

    it('уровень показан точкой семантического цвета', () => {
        const { container } = renderIn(<NotificationItem item={item({ level: 'info' })} />);
        expect(container.querySelector('.nt-item__dot')).toHaveClass('nt-item__dot--info');
    });

    it('кнопка отметки ставит прочтение и снимает его', async () => {
        const onToggleRead = vi.fn();
        const { unmount } = renderIn(<NotificationItem item={item()} onToggleRead={onToggleRead} />);
        await userEvent.click(screen.getByRole('button', { name: 'Отметить прочитанным' }));
        expect(onToggleRead).toHaveBeenCalledWith(['discounted:delist:p1'], true);
        unmount();

        renderIn(<NotificationItem item={item({ seen: true })} onToggleRead={onToggleRead} />);
        await userEvent.click(screen.getByRole('button', { name: 'Вернуть в непрочитанные' }));
        expect(onToggleRead).toHaveBeenLastCalledWith(['discounted:delist:p1'], false);
    });
});

describe('Колокольчик', () => {
    it('молчит, когда всё в порядке', () => {
        const { container } = renderIn(<NotificationsBell expanded />);
        expect(container.querySelector('.nt-count')).toBeNull();
    });

    it('показывает непрочитанные и красится по самому серьёзному', () => {
        setState(withCounts([item(), item({ key: 'k2', level: 'warning' })]));
        const { container } = renderIn(<NotificationsBell expanded />);
        expect(screen.getByText('2')).toBeInTheDocument();
        expect(container.querySelector('.nt-count .nt-dot')).toHaveClass('nt-dot--critical');
    });

    it('когда всё прочитано, значка нет — список остался в панели', () => {
        setState(withCounts([item({ seen: true })]));
        const { container } = renderIn(<NotificationsBell expanded />);
        expect(container.querySelector('.nt-count')).toBeNull();
    });

    it('цвет — по непрочитанному, а не по всему списку', () => {
        // прочитанное критическое не должно красить точку в красный
        setState(withCounts([
            item({ seen: true }),
            item({ key: 'k2', level: 'info', seen: false }),
        ]));
        const { container } = renderIn(<NotificationsBell expanded />);
        expect(screen.getByText('1')).toBeInTheDocument();
        expect(container.querySelector('.nt-count .nt-dot')).toHaveClass('nt-dot--info');
    });

    it('открывает панель', async () => {
        setState(withCounts([item()]));
        renderIn(<NotificationsBell expanded />);
        await userEvent.click(screen.getByRole('button', { name: /Уведомления/ }));
        expect(state.openPanel).toHaveBeenCalled();
    });
});

describe('Панель', () => {
    it('закрытая ничего не рисует', () => {
        setState({ ...withCounts([item()]), panelOpen: false });
        renderIn(<NotificationsPanel />);
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('группирует по разделам и ведёт в раздел', () => {
        setState({ ...withCounts([item()]), panelOpen: true });
        renderIn(<NotificationsPanel />);
        expect(screen.getByRole('dialog', { name: 'Уведомления' })).toBeInTheDocument();
        expect(screen.getByText('Уценка')).toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'Открыть' })).toHaveAttribute('href', '/discounted');
    });

    it('открытие панели ничего не помечает — отметку ставит человек', async () => {
        setState({ ...withCounts([item()]), panelOpen: true });
        renderIn(<NotificationsPanel />);
        await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
        expect(state.setRead).not.toHaveBeenCalled();
    });

    it('«Прочитать всё» есть, только пока есть непрочитанные', () => {
        setState({ ...withCounts([item()]), panelOpen: true });
        const { unmount } = renderIn(<NotificationsPanel />);
        expect(screen.getByRole('button', { name: 'Прочитать всё' })).toBeInTheDocument();
        expect(screen.getByText('1 новое')).toBeInTheDocument();
        unmount();

        setState({ ...withCounts([item({ seen: true })]), panelOpen: true });
        renderIn(<NotificationsPanel />);
        expect(screen.queryByRole('button', { name: 'Прочитать всё' })).not.toBeInTheDocument();
    });

    it('«Прочитать всё» помечает весь список', async () => {
        setState({ ...withCounts([item()]), panelOpen: true });
        renderIn(<NotificationsPanel />);
        await userEvent.click(screen.getByRole('button', { name: 'Прочитать всё' }));
        expect(state.setRead).toHaveBeenCalledWith([], true);
    });

    it('прочитанное остаётся в списке', () => {
        setState({ ...withCounts([item({ seen: true })]), panelOpen: true });
        renderIn(<NotificationsPanel />);
        expect(screen.getByText(/пора снимать с продажи/)).toBeInTheDocument();
    });

    it('пустая говорит об этом прямо', () => {
        setState({ ...withCounts([]), panelOpen: true });
        renderIn(<NotificationsPanel />);
        expect(screen.getByText('Ничего не требует внимания')).toBeInTheDocument();
    });
});

describe('Строка на странице раздела', () => {
    it('берёт только свой раздел', () => {
        setState(withCounts([
            item(),
            item({ key: 'other', source: 'deadlines', title: 'Чужой раздел' }),
        ]));
        renderIn(<SectionNotifications source="discounted" />);
        expect(screen.getByText(/пора снимать с продажи/)).toBeInTheDocument();
        expect(screen.queryByText('Чужой раздел')).not.toBeInTheDocument();
    });

    it('цветная линия — по самому серьёзному уведомлению раздела', () => {
        setState(withCounts([item({ level: 'warning' }), item({ key: 'k2', level: 'critical' })]));
        const { container } = renderIn(<SectionNotifications source="discounted" />);
        expect(container.querySelector('.nt-section')).toHaveClass('nt-section--critical');
    });

    it('ничего не рисует, когда по разделу тихо', () => {
        const { container } = renderIn(<SectionNotifications source="discounted" />);
        expect(container).toBeEmptyDOMElement();
    });
});
