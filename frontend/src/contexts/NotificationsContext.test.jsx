import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { NotificationsProvider, useNotifications } from './NotificationsContext';

const authStatus = { isAuthenticated: true };
vi.mock('../hooks/useAuthStatus', () => ({ useAuthStatus: () => authStatus }));

const api = vi.hoisted(() => ({
    list: vi.fn(),
    setRead: vi.fn(),
}));
vi.mock('../api/notificationsApi', () => ({ notificationsApi: api }));

const payload = (overrides = {}) => ({
    items: [{ key: 'k1', source: 'discounted', level: 'critical', title: 'Дело', seen: false, muted: false }],
    counts: { total: 1, unseen: 1 },
    by_source: { discounted: { total: 1, unseen: 1, level: 'critical' } },
    ...overrides,
});

const Probe = () => {
    const { counts, items, reload, setRead } = useNotifications();
    return (
        <div>
            <span data-testid="total">{counts.total}</span>
            <span data-testid="unseen">{counts.unseen}</span>
            <span data-testid="titles">{items.map((i) => i.title).join(',')}</span>
            <button type="button" onClick={() => reload(true)}>обновить</button>
            <button type="button" onClick={() => setRead([], true)}>прочитать</button>
        </div>
    );
};

const renderProbe = () => render(
    <NotificationsProvider><Probe /></NotificationsProvider>,
);

beforeEach(() => {
    authStatus.isAuthenticated = true;
    api.list.mockReset().mockResolvedValue(payload());
    api.setRead.mockReset().mockResolvedValue(payload({ counts: { total: 1, unseen: 0 } }));
});

describe('NotificationsContext', () => {
    it('не спрашивает уведомления у неаутентифицированного', () => {
        authStatus.isAuthenticated = null;
        renderProbe();
        expect(api.list).not.toHaveBeenCalled();
        expect(screen.getByTestId('total')).toHaveTextContent('0');
    });

    it('загружает список при монтировании', async () => {
        renderProbe();
        await waitFor(() => expect(screen.getByTestId('titles')).toHaveTextContent('Дело'));
        expect(screen.getByTestId('unseen')).toHaveTextContent('1');
    });

    it('«обновить» перечитывает данные в обход кеша сервера', async () => {
        renderProbe();
        await waitFor(() => expect(api.list).toHaveBeenCalled());
        await userEvent.click(screen.getByRole('button', { name: 'обновить' }));
        await waitFor(() => expect(api.list).toHaveBeenLastCalledWith({ refresh: 1 }, expect.anything()));
    });

    it('гасит счётчик сразу, не дожидаясь ответа сервера', async () => {
        let release;
        api.setRead.mockImplementation(() => new Promise((resolve) => { release = resolve; }));
        renderProbe();
        await waitFor(() => expect(screen.getByTestId('unseen')).toHaveTextContent('1'));

        await userEvent.click(screen.getByRole('button', { name: 'прочитать' }));
        expect(screen.getByTestId('unseen')).toHaveTextContent('0');

        release(payload({ counts: { total: 1, unseen: 0 } }));
        await waitFor(() => expect(screen.getByTestId('total')).toHaveTextContent('1'));
    });

    it('ошибка загрузки не роняет остальной интерфейс', async () => {
        api.list.mockRejectedValue(new Error('сервер не ответил'));
        renderProbe();
        await waitFor(() => expect(api.list).toHaveBeenCalled());
        expect(screen.getByTestId('total')).toHaveTextContent('0');
    });
});
