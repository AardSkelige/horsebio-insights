import { useLayoutEffect, useState, useSyncExternalStore } from 'react';

const UNDER_BARS = 140;
const SCRIM_FADE_MS = 220;
const PHONE = '(max-width: 767px)';

const measure = () => {
    const extra = window.matchMedia?.(PHONE).matches ? UNDER_BARS : 0;
    const top = window.scrollY;
    const height = window.innerHeight;
    return {
        extra,
        panel: { position: 'absolute', top, bottom: 'auto', height: height + extra, boxSizing: 'border-box', '--under-bars': `${extra}px` },
        scrim: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 'auto', height: Math.max(document.documentElement.scrollHeight, top + height + extra) },
    };
};

let locks = 0;
let tints = 0;
let untint = 0;
const tintListeners = new Set();
const notifyTint = () => tintListeners.forEach((listener) => listener());

const lockPage = (tinted) => {
    const root = document.documentElement;
    locks += 1;
    root.style.overflow = 'hidden';
    if (tinted) {
        tints += 1;
        clearTimeout(untint);
        root.classList.remove('page-layer-untinting');
        root.classList.add('page-layer-tinted');
        notifyTint();
    }
    return () => {
        locks -= 1;
        if (locks === 0) root.style.overflow = '';
        if (tinted) {
            tints -= 1;
            if (tints === 0) {
                root.classList.add('page-layer-untinting');
                untint = setTimeout(() => root.classList.remove('page-layer-tinted', 'page-layer-untinting'), SCRIM_FADE_MS);
            }
            notifyTint();
        }
    };
};

export const usePageLayer = (open, { tinted = true } = {}) => {
    const [layer, setLayer] = useState(null);

    useLayoutEffect(() => {
        if (!open) return undefined;
        const update = () => setLayer(measure());
        update();
        window.addEventListener('resize', update);
        const unlock = lockPage(tinted);
        return () => {
            window.removeEventListener('resize', update);
            unlock();
            setLayer(null);
        };
    }, [open, tinted]);

    return layer;
};

export const useHeldLayer = (layer) => {
    const [held, setHeld] = useState(null);
    if (layer && layer !== held) setHeld(layer);
    return [layer ?? held, () => setHeld(null)];
};

const subscribeTint = (listener) => {
    tintListeners.add(listener);
    return () => tintListeners.delete(listener);
};

export const usePageTint = () => useSyncExternalStore(subscribeTint, () => tints > 0);
