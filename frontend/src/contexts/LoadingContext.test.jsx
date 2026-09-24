import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import { LoadingProvider, useLoading } from './LoadingContext';
import { parserAPI } from '../utils/api';

vi.mock('../utils/api', () => ({
    parserAPI: {
        getCsrfToken: vi.fn(),
        loadData: vi.fn(),
        getTaskStatus: vi.fn(),
        stopLoading: vi.fn(),
    },
}));

vi.mock('../utils/authSession', () => ({
    getFreshAuthStatus: () => ({ isAuthenticated: false }),
    subscribeAuth: () => () => {},
}));

function Probe() {
    const { isLoading, startLoading } = useLoading();
    return (
        <div>
            <button onClick={() => startLoading({ months: 12 })}>Обновить</button>
            <span data-testid="state">{isLoading ? 'идёт' : 'не идёт'}</span>
        </div>
    );
}

function ErrorProbe() {
    const { loadingProgress } = useLoading();
    return <span data-testid="outcome">{loadingProgress ? `${loadingProgress.status}: ${loadingProgress.message}` : ''}</span>;
}

const renderProbe = () => render(
    <LoadingProvider>
        <Probe />
    </LoadingProvider>
);

const start = async () => {
    await act(async () => {
        screen.getByText('Обновить').click();
    });
};

describe('LoadingContext', () => {
    beforeEach(() => {
        vi.useFakeTimers({ shouldAdvanceTime: true });
        parserAPI.getCsrfToken.mockResolvedValue({ csrfToken: 'token' });
        parserAPI.loadData.mockResolvedValue({ status: 'started', run_id: 42 });
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.clearAllMocks();
    });

    it('не принимает прошлый прогон за только что запущенный', async () => {
        // Строка нового прогона появляется не мгновенно, и первый опрос
        // находит предыдущий — законченный. Раньше полоса гасла через
        // полсекунды после нажатия, а синхронизация шла незаметно.
        parserAPI.getTaskStatus.mockResolvedValue({
            is_running: false,
            state: { id: 41, status: 'completed', message: 'Готово', processed: 100, total: 100 },
        });

        renderProbe();
        await start();

        await act(async () => { await vi.advanceTimersByTimeAsync(4000); });

        expect(screen.getByTestId('state').textContent).toBe('идёт');
    });

    it('заканчивает загрузку по своему прогону', async () => {
        parserAPI.getTaskStatus.mockResolvedValue({
            is_running: false,
            state: { id: 42, status: 'completed', message: 'Готово', processed: 100, total: 100 },
        });

        renderProbe();
        await start();

        await act(async () => { await vi.advanceTimersByTimeAsync(4000); });

        await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('не идёт'));
    });

    it('заканчивает загрузку и на частичном прогоне', async () => {
        // «Частично» — тоже итог: часть сущностей обновилась, часть осталась
        // вчерашней. Не считать его концом значило бы крутить полосу вечно.
        parserAPI.getTaskStatus.mockResolvedValue({
            is_running: false,
            state: {
                id: 42, status: 'partial', processed: 100, total: 100,
                message: 'Обновлено частично, не удались: отгрузки',
                entities: [{ entity: 'shipments', name: 'Отгрузки', status: 'failed', error: 'МойСклад недоступен' }],
            },
        });

        renderProbe();
        await start();

        await act(async () => { await vi.advanceTimersByTimeAsync(4000); });

        await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('не идёт'));
    });

    it('не ждёт вечно прогон, о котором сервер больше не слышит', async () => {
        // Процесс умер, не закрыв запись: статус в ней навсегда «идёт».
        parserAPI.getTaskStatus.mockResolvedValue({
            is_running: false,
            state: { id: 42, status: 'running', message: 'Обработка отгрузок', processed: 40, total: 100 },
        });

        renderProbe();
        await start();

        await act(async () => { await vi.advanceTimersByTimeAsync(4000); });

        await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('не идёт'));
    });

    it('не гасит полосу, пока сервер не ответил на запуск', async () => {
        // Опрос стартует вместе с нажатием и спрашивает сервер раньше,
        // чем тот ответит «запустил»: ответ приходит про прошлый прогон,
        // законченный. Так на проде и было — полоса моргнула и погасла,
        // а синхронизация шла незаметно.
        let answer;
        parserAPI.loadData.mockReturnValue(new Promise(resolve => { answer = resolve; }));
        parserAPI.getTaskStatus.mockResolvedValue({
            is_running: false,
            state: { id: 41, status: 'partial', message: 'Частично', processed: 100, total: 100 },
        });

        renderProbe();
        await start();
        await act(async () => { await vi.advanceTimersByTimeAsync(1000); });

        await act(async () => { answer({ status: 'started', run_id: 42 }); });
        await act(async () => { await vi.advanceTimersByTimeAsync(4000); });

        expect(screen.getByTestId('state').textContent).toBe('идёт');
    });

    it('показывает уже идущую синхронизацию вместо ошибки', async () => {
        // Нажатие во время чужого или ночного прогона получает 409.
        // Раньше страница стирала всё и только моргала — теперь следит
        // за идущим прогоном до его конца.
        const busy = new Error('Синхронизация уже выполняется (запущена: расписание)');
        busy.status = 409;
        parserAPI.loadData.mockRejectedValue(busy);
        parserAPI.getTaskStatus.mockResolvedValue({
            is_running: true,
            state: { id: 7, status: 'running', message: 'Загружаем отгрузки', processed: 60, total: 100 },
        });

        renderProbe();
        await start();
        await act(async () => { await vi.advanceTimersByTimeAsync(4000); });

        expect(screen.getByTestId('state').textContent).toBe('идёт');

        parserAPI.getTaskStatus.mockResolvedValue({
            is_running: false,
            state: { id: 7, status: 'completed', message: 'Готово', processed: 100, total: 100 },
        });
        await act(async () => { await vi.advanceTimersByTimeAsync(4000); });

        await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('не идёт'));
    });

    it('оставляет причину, если запуск не удался', async () => {
        const failure = new Error('Дата окончания не может быть в будущем');
        failure.status = 400;
        parserAPI.loadData.mockRejectedValue(failure);
        parserAPI.getTaskStatus.mockResolvedValue({ is_running: false, state: null });

        render(
            <LoadingProvider>
                <Probe />
                <ErrorProbe />
            </LoadingProvider>
        );
        await start();

        expect(screen.getByTestId('state').textContent).toBe('не идёт');
        expect(screen.getByTestId('outcome').textContent).toBe('error: Дата окончания не может быть в будущем');
    });
});
