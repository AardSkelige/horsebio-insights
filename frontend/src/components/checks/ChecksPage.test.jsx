import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import ChecksPage from './ChecksPage';
import api from '../../utils/api';

vi.mock('../../utils/api', () => ({
    default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
    getCsrfToken: vi.fn(),
}));

// Деталка тестируется отдельно — здесь важна только навигация список ↔ деталка
vi.mock('./CheckDetail', () => ({
    default: ({ scriptId, onBack }) => (
        <div>
            <div>деталка: {scriptId}</div>
            <button onClick={onBack}>← Назад к списку</button>
        </div>
    ),
}));

const SCRIPTS = [
    {
        id: 'horsebio_health_check',
        name: 'Проверка данных',
        description: 'Целостность данных МойСклад',
        account: 'HorseBio',
        structured: true,
        summary: { critical: 2, important: 0, warnings: 1 },
        last_run: { exit_code: 0, finished_at: '2026-07-01 10:00' },
        schedule: 'ежедневно',
    },
    {
        id: 'horsebio_returns',
        name: 'Мониторинг возвратов',
        description: 'Возвраты покупателей',
        account: 'HorseBio',
        last_run: null,
        schedule: 'каждый час',
    },
    {
        // StarPony на странице проверок НЕ показывается (виден только в ЛК суперпользователя),
        // но остаётся в данных, чтобы деталь по прямой ссылке /checks/:id работала
        id: 'starpony_returns',
        name: 'StarPony возвраты',
        description: 'Возвраты StarPony',
        account: 'StarPony',
        last_run: null,
        schedule: 'каждый час',
    },
];

const renderAt = (path) => render(
    <MemoryRouter initialEntries={[path]}>
        <Routes>
            <Route path="/checks" element={<ChecksPage />} />
            <Route path="/checks/:scriptId" element={<ChecksPage />} />
        </Routes>
    </MemoryRouter>
);

beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({ scripts: SCRIPTS });
});

describe('ChecksPage — список', () => {
    it('показывает строки HorseBio, но скрывает StarPony', async () => {
        renderAt('/checks');
        expect(await screen.findByText('Проверка данных')).toBeInTheDocument();
        expect(screen.getByText('Мониторинг возвратов')).toBeInTheDocument();
        expect(screen.getAllByText('HorseBio').length).toBeGreaterThan(0);
        // StarPony на странице проверок не отображается
        expect(screen.queryByText('StarPony возвраты')).not.toBeInTheDocument();
        expect(screen.queryByText('StarPony')).not.toBeInTheDocument();
    });

    it('показывает статус и время запуска одной компактной строкой', async () => {
        renderAt('/checks');
        expect(await screen.findByText('Проверка данных')).toBeInTheDocument();
        expect(screen.getByText('Не запускался')).toBeInTheDocument();
        expect(screen.getByLabelText('Последний запуск')).toBeInTheDocument();
        expect(screen.getByLabelText('Расписание')).toHaveTextContent('каждый час');
    });

    it('показывает ошибку, если API недоступен', async () => {
        api.get.mockRejectedValue(new Error('Сервер недоступен'));
        renderAt('/checks');
        expect(await screen.findByText('Сервер недоступен')).toBeInTheDocument();
    });
});

describe('ChecksPage — навигация', () => {
    it('клик по карточке открывает деталку', async () => {
        const user = userEvent.setup();
        renderAt('/checks');
        await user.click(await screen.findByText('Проверка данных'));
        expect(screen.getByText('деталка: horsebio_health_check')).toBeInTheDocument();
        expect(screen.queryByText('Мониторинг возвратов')).not.toBeInTheDocument();
    });

    it('«назад» из деталки возвращает к списку', async () => {
        const user = userEvent.setup();
        renderAt('/checks');
        await user.click(await screen.findByText('Проверка данных'));
        await user.click(screen.getByText('← Назад к списку'));
        expect(await screen.findByText('Мониторинг возвратов')).toBeInTheDocument();
    });

    it('прямая ссылка /checks/:id сразу открывает деталку', async () => {
        renderAt('/checks/starpony_returns');
        expect(await screen.findByText('деталка: starpony_returns')).toBeInTheDocument();
    });
});
