import { describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';

const test = vi.fn(() => Promise.resolve({ sent: 1, devices: 1 }));

vi.mock('../../api/pushApi', () => ({
    pushApi: {
        key: () => Promise.resolve({ publicKey: 'BA4t99aIjJ5P' }),
        subscribe: () => Promise.resolve({ subscribed: true }),
        unsubscribe: vi.fn(),
        test: () => test(),
    },
}));

describe('PushPanelAction', () => {
    it('когда пуши включены, присылает тестовое и говорит, куда дошло', async () => {
        window.PushManager = function PushManager() {};
        window.Notification = { permission: 'granted', requestPermission: vi.fn() };
        const subscription = { toJSON: () => ({ endpoint: 'https://push.example/1' }) };
        Object.defineProperty(navigator, 'serviceWorker', {
            configurable: true,
            value: { ready: Promise.resolve({ pushManager: { getSubscription: () => Promise.resolve(subscription), permissionState: () => Promise.resolve('granted') } }) },
        });
        vi.resetModules();
        const { default: PushPanelAction } = await import('./PushPanelAction');
        render(<PushPanelAction />);

        await act(async () => { fireEvent.click(screen.getByRole('button', { name: /Прислать тестовое уведомление/ })); });

        expect(test).toHaveBeenCalled();
        expect(screen.getByText('Отправлено на 1 устройство')).toBeInTheDocument();
    });
});
