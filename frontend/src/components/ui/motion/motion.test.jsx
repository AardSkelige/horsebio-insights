import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MotionProvider, AnimatedNumber, Stagger, StaggerItem, FadeRise, ModalShell } from './index';

const withProvider = (ui) => render(<MotionProvider>{ui}</MotionProvider>);

describe('motion-примитивы', () => {
    it('Stagger/StaggerItem рендерят детей и пробрасывают className', () => {
        withProvider(
            <Stagger className="grid">
                <StaggerItem>первая карточка</StaggerItem>
                <StaggerItem>вторая карточка</StaggerItem>
            </Stagger>
        );
        expect(screen.getByText('первая карточка')).toBeInTheDocument();
        expect(screen.getByText('вторая карточка')).toBeInTheDocument();
        expect(document.querySelector('.grid')).not.toBeNull();
    });

    it('FadeRise рендерит содержимое', () => {
        withProvider(<FadeRise>секция</FadeRise>);
        expect(screen.getByText('секция')).toBeInTheDocument();
    });

    it('AnimatedNumber докручивается до значения', async () => {
        withProvider(<AnimatedNumber value={1250} format={(v) => String(v)} />);
        await waitFor(
            () => expect(screen.getByText('1250')).toBeInTheDocument(),
            { timeout: 3000 }
        );
    });

    it('AnimatedNumber применяет format к значению', async () => {
        withProvider(<AnimatedNumber value={1250} format={(v) => v.toLocaleString('ru-RU')} />);
        await waitFor(
            () => expect(screen.getByText((t) => t.replace(/\s/g, ' ') === '1 250')).toBeInTheDocument(),
            { timeout: 3000 }
        );
    });
});

describe('ModalShell', () => {
    it('открытая модалка рендерит содержимое через портал', () => {
        withProvider(
            <ModalShell open onClose={() => {}}>
                <div>содержимое модалки</div>
            </ModalShell>
        );
        expect(screen.getByText('содержимое модалки')).toBeInTheDocument();
    });

    it('закрытая модалка ничего не рендерит', () => {
        withProvider(
            <ModalShell open={false} onClose={() => {}}>
                <div>содержимое модалки</div>
            </ModalShell>
        );
        expect(screen.queryByText('содержимое модалки')).not.toBeInTheDocument();
    });

    it('содержимое исчезает после смены open на false', async () => {
        const { rerender } = withProvider(
            <ModalShell open onClose={() => {}}>
                <div>содержимое модалки</div>
            </ModalShell>
        );
        rerender(
            <MotionProvider>
                <ModalShell open={false} onClose={() => {}}>
                    <div>содержимое модалки</div>
                </ModalShell>
            </MotionProvider>
        );
        await waitFor(
            () => expect(screen.queryByText('содержимое модалки')).not.toBeInTheDocument(),
            { timeout: 3000 }
        );
    });

    it('клик по подложке вызывает onClose', async () => {
        const onClose = vi.fn();
        const user = userEvent.setup();
        withProvider(
            <ModalShell open onClose={onClose}>
                <div>содержимое модалки</div>
            </ModalShell>
        );
        const backdrop = screen.getByText('содержимое модалки').closest('[style*="fixed"]').firstChild;
        await user.click(backdrop);
        expect(onClose).toHaveBeenCalled();
    });
});
