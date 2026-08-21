import { describe, expect, it, vi, beforeEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useIsMobile } from './useIsMobile';

/** Управляемый matchMedia: jsdom своего не отдаёт. */
function mockMatchMedia(initialMatches) {
    let matches = initialMatches;
    const listeners = new Set();

    window.matchMedia = vi.fn().mockImplementation((query) => ({
        media: query,
        get matches() { return matches; },
        addEventListener: (_, fn) => listeners.add(fn),
        removeEventListener: (_, fn) => listeners.delete(fn),
    }));

    return {
        setMatches(next) {
            matches = next;
            listeners.forEach((fn) => fn({ matches: next }));
        },
        get listenerCount() { return listeners.size; },
    };
}

describe('useIsMobile', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it('возвращает состояние на момент первого рендера', () => {
        mockMatchMedia(true);
        const { result } = renderHook(() => useIsMobile());
        expect(result.current).toBe(true);
    });

    it('реагирует на пересечение границы', () => {
        const media = mockMatchMedia(false);
        const { result } = renderHook(() => useIsMobile());
        expect(result.current).toBe(false);

        act(() => media.setMatches(true));
        expect(result.current).toBe(true);
    });

    it('снимает слушателя при размонтировании', () => {
        const media = mockMatchMedia(false);
        const { unmount } = renderHook(() => useIsMobile());
        expect(media.listenerCount).toBe(1);

        unmount();
        expect(media.listenerCount).toBe(0);
    });
});
