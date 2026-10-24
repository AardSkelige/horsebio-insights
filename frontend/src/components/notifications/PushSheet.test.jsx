import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const subscribeApi = vi.fn(() => Promise.resolve({ subscribed: true }));

vi.mock('../../api/pushApi', () => ({
    pushApi: {
        key: () => Promise.resolve({ publicKey: 'BA4t99aIjJ5P' }),
        subscribe: (...args) => subscribeApi(...args),
        unsubscribe: vi.fn(),
        test: () => sendTest(),
    },
}));

const sendTest = vi.fn(() => Promise.resolve({ sent: 1, devices: 1 }));

const subscription = { endpoint: 'https://push.example/1', toJSON: () => ({ endpoint: 'https://push.example/1', keys: { p256dh: 'k', auth: 'a' } }) };

const stubPush = (permission) => {
    window.PushManager = function PushManager() {};
    window.Notification = { permission, requestPermission: vi.fn(() => Promise.resolve('granted')) };
    const states = { default: 'prompt', granted: 'granted', denied: 'denied' };
    const pushManager = {
        getSubscription: vi.fn(() => Promise.resolve(null)),
        subscribe: vi.fn(() => Promise.resolve(subscription)),
        permissionState: vi.fn(() => Promise.resolve(states[permission])),
    };
    Object.defineProperty(navigator, 'serviceWorker', {
        configurable: true,
        value: { ready: Promise.resolve({ pushManager }), addEventListener: vi.fn(), removeEventListener: vi.fn() },
    });
    return pushManager;
};

const stubIphoneSafari = () => {
    delete window.PushManager;
    delete window.Notification;
    Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: { addEventListener: vi.fn(), removeEventListener: vi.fn() } });
    vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Safari');
};

const renderSheet = async (props = {}) => {
    vi.resetModules();
    const { default: PushSheet } = await import('./PushSheet');
    const view = render(<MemoryRouter><PushSheet {...props} /></MemoryRouter>);
    await act(async () => { vi.advanceTimersByTime(1500); });
    return view;
};

describe('PushSheet', () => {
    beforeEach(() => {
        vi.useFakeTimers({ shouldAdvanceTime: true });
        vi.restoreAllMocks();
        subscribeApi.mockClear();
    });

    it('при запуске предлагает включить и после согласия отдаёт подписку серверу', async () => {
        const pushManager = stubPush('default');
        await renderSheet();

        await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Включить' })); });

        expect(window.Notification.requestPermission).toHaveBeenCalled();
        expect(pushManager.subscribe).toHaveBeenCalledWith(expect.objectContaining({ userVisibleOnly: true }));
        expect(subscribeApi).toHaveBeenCalledWith(subscription.toJSON());
        expect(sendTest).toHaveBeenCalled();
        expect(screen.getByText('Уведомления включены')).toBeInTheDocument();
    });

    it('если телефон запретил, говорит об этом и где включить', async () => {
        stubPush('default');
        window.Notification.requestPermission = vi.fn(() => Promise.resolve('denied'));
        const pushManager = navigator.serviceWorker.ready.then((r) => r.pushManager);
        (await pushManager).subscribe.mockRejectedValue(Object.assign(new Error('denied'), { name: 'NotAllowedError' }));
        (await pushManager).permissionState.mockResolvedValueOnce('prompt').mockResolvedValue('denied');
        await renderSheet();

        await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Включить' })); });

        expect(screen.getByText('Уведомления запрещены')).toBeInTheDocument();
        expect(screen.getByText(/push=denied/)).toBeInTheDocument();
    });

    it('если iPhone сказал «запрещено», но подписка прошла, считает включённым', async () => {
        const pushManager = stubPush('default');
        window.Notification.requestPermission = vi.fn(() => Promise.resolve('denied'));
        await renderSheet();

        await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Включить' })); });

        expect(pushManager.subscribe).toHaveBeenCalled();
        expect(screen.getByText('Уведомления включены')).toBeInTheDocument();
    });

    it('ошибку подписки показывает текстом, а не глотает', async () => {
        const pushManager = stubPush('default');
        pushManager.subscribe.mockRejectedValue(new Error('push service not available'));
        await renderSheet();

        await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Включить' })); });

        expect(screen.getByText(/push service not available/)).toBeInTheDocument();
    });

    it('«Не сейчас» прячет окошко до следующего запуска', async () => {
        stubPush('default');
        await renderSheet();

        fireEvent.click(screen.getByRole('button', { name: 'Не сейчас' }));
        await act(async () => { vi.advanceTimersByTime(500); });

        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
        await renderSheet();
        expect(screen.getAllByRole('dialog')).toHaveLength(1);
    });

    it('во время сцены главной молчит', async () => {
        stubPush('default');
        await renderSheet({ quiet: true });

        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('если уже разрешено, не предлагает и молча обновляет подписку', async () => {
        stubPush('granted');
        await renderSheet();

        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
        expect(subscribeApi).toHaveBeenCalled();
    });

    it('на iPhone в Safari подсказывает добавить на экран «Домой»', async () => {
        stubIphoneSafari();
        await renderSheet();

        expect(screen.getByText('Уведомления на iPhone')).toBeInTheDocument();
        expect(screen.getByText('Нажмите три полоски в строке адреса внизу')).toBeInTheDocument();
    });
});
