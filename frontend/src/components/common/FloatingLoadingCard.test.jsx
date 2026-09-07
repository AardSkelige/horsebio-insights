import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import FloatingLoadingCard from './FloatingLoadingCard';

const loadingState = {
    isLoading: false,
    loadingProgress: {
        status: 'partial',
        message: 'Обновлено частично, не удались: отгрузки',
        processed: 100,
        total: 100,
        entities: [
            { entity: 'supplies', name: 'Приёмки', status: 'ok', error: null },
            { entity: 'shipments', name: 'Отгрузки', status: 'failed', error: 'МойСклад недоступен' },
        ],
    },
    logs: [],
    progress: { processed: 100, total: 100 },
    cancelLoading: vi.fn(),
    resetStates: vi.fn(),
    getProgressPercentage: () => 100,
    getCurrentStage: () => 'Отгрузки',
};

vi.mock('../../contexts/LoadingContext', () => ({
    useLoading: () => loadingState,
}));

describe('FloatingLoadingCard', () => {
    beforeEach(() => {
        vi.useFakeTimers({ shouldAdvanceTime: true });
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    it('называет сущности, которые остались вчерашними', () => {
        // Ради этого прогон и помечается «частично»: отчёты уже считаются
        // на смеси свежего и старого, и знать, чего именно, важнее всего.
        render(<FloatingLoadingCard />);

        expect(screen.getByText('Не обновились')).toBeInTheDocument();
        expect(screen.getByText('Отгрузки')).toBeInTheDocument();
        expect(screen.getByText('МойСклад недоступен')).toBeInTheDocument();
        expect(screen.queryByText('Приёмки')).not.toBeInTheDocument();
    });

    it('не прячет список сам через три секунды', async () => {
        // Обычная карточка исчезает через три секунды после конца загрузки.
        // Здесь исчезать нечему: это единственное место, где написано,
        // что осталось вчерашним, и три секунды на прочитать — не время.
        render(<FloatingLoadingCard />);

        await act(async () => { await vi.advanceTimersByTimeAsync(5000); });

        expect(screen.getByText('Отгрузки')).toBeInTheDocument();
        expect(loadingState.resetStates).not.toHaveBeenCalled();
    });
});
