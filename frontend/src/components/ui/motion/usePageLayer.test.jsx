import { describe, expect, it } from 'vitest';
import { renderHook } from '@testing-library/react';
import { usePageLayer } from './usePageLayer';

describe('usePageLayer', () => {
    it('держит страницу, пока открыт хоть один слой, и отпускает после последнего', () => {
        const menu = renderHook(({ open }) => usePageLayer(open), { initialProps: { open: true } });
        const scrim = renderHook(({ open }) => usePageLayer(open), { initialProps: { open: true } });

        expect(document.documentElement.style.overflow).toBe('hidden');
        menu.rerender({ open: false });
        expect(document.documentElement.style.overflow).toBe('hidden');
        scrim.rerender({ open: false });
        expect(document.documentElement.style.overflow).toBe('');
    });

    it('отдаёт слою текущую прокрутку и высоту экрана', () => {
        window.scrollY = 300;
        const { result } = renderHook(() => usePageLayer(true));

        expect(result.current.panel.top).toBe(300);
        expect(result.current.panel.height).toBe(window.innerHeight + result.current.extra);
    });
});
