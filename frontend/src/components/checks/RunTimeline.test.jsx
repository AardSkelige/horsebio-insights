import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RunTimeline from './RunTimeline';

const RUNS_DATA = {
    kind: 'structured',
    runs: [
        {
            run_id: 'r2', finished_at: '2026-06-27 10:00:00', exit_code: 0, duration_sec: 30,
            summary: { critical: 0, important: 0, warnings: 2 },
            delta: { critical: -1, important: 0, warnings: 0 }, changed: true,
        },
        {
            run_id: 'r1', finished_at: '2026-06-26 07:38:00', exit_code: 0, duration_sec: 25,
            summary: { critical: 1, important: 0, warnings: 2 },
            delta: null, changed: true,
        },
    ],
};

const swipeLeft = (el) => {
    fireEvent.touchStart(el, { touches: [{ clientX: 200, clientY: 100 }] });
    fireEvent.touchMove(el, { touches: [{ clientX: 120, clientY: 102 }] });
    fireEvent.touchEnd(el, { touches: [] });
};

let onSelect, onDelete;
beforeEach(() => {
    onSelect = vi.fn();
    onDelete = vi.fn();
});

const renderTimeline = () => render(
    <RunTimeline runsData={RUNS_DATA} selectedRun={null} onSelect={onSelect} onDelete={onDelete} />
);

describe('RunTimeline', () => {
    it('клик по карточке выбирает запуск', async () => {
        const user = userEvent.setup();
        renderTimeline();
        await user.click(screen.getByText(/27\.06 10:00/));
        expect(onSelect).toHaveBeenCalledWith('r2');
    });

    it('самый старый запуск помечен «нет предыдущего для сравнения», а не пустотой', () => {
        renderTimeline();
        expect(screen.getByText('нет предыдущего запуска для сравнения')).toBeInTheDocument();
    });

    it('улучшение показывается зелёной стрелкой вниз', () => {
        renderTimeline();
        expect(screen.getByText(/↓1 критичные/)).toBeInTheDocument();
    });

    it('свайп влево открывает корзину, клик по карточке закрывает её, а не выбирает запуск', () => {
        renderTimeline();
        const card = screen.getByText(/27\.06 10:00/).closest('button');
        swipeLeft(card);
        fireEvent.click(card);
        expect(onSelect).not.toHaveBeenCalled();
    });

    it('корзина не показывается без свайпа (не просвечивает в углах)', () => {
        renderTimeline();
        expect(screen.queryAllByLabelText('Удалить запуск')).toHaveLength(0);
    });

    it('кнопка корзины удаляет именно этот запуск', async () => {
        const user = userEvent.setup();
        renderTimeline();
        swipeLeft(screen.getByText(/26\.06 07:38/).closest('button'));
        await user.click(screen.getByLabelText('Удалить запуск'));
        expect(onDelete).toHaveBeenCalledWith('r1');
    });

    it('свайп второй карточки закрывает первую — открыта только одна корзина', () => {
        renderTimeline();
        swipeLeft(screen.getByText(/26\.06 07:38/).closest('button'));
        expect(screen.getAllByLabelText('Удалить запуск')).toHaveLength(1);
        swipeLeft(screen.getByText(/27\.06 10:00/).closest('button'));
        expect(screen.getAllByLabelText('Удалить запуск')).toHaveLength(1);
    });

    it('вертикальный скролл по карточке не считается свайпом', async () => {
        const user = userEvent.setup();
        renderTimeline();
        const card = screen.getByText(/27\.06 10:00/).closest('button');
        fireEvent.touchStart(card, { touches: [{ clientX: 200, clientY: 100 }] });
        fireEvent.touchMove(card, { touches: [{ clientX: 195, clientY: 220 }] });
        fireEvent.touchEnd(card, { touches: [] });
        await user.click(card);
        expect(onSelect).toHaveBeenCalledWith('r2');
    });
});
