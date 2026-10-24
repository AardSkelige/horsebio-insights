import { useLayoutEffect, useState } from 'react';

const UNDER_BARS = 140;
const PHONE = '(max-width: 767px)';

const measure = () => {
    const extra = window.matchMedia?.(PHONE).matches ? UNDER_BARS : 0;
    const top = window.scrollY;
    const height = window.innerHeight;
    return {
        extra,
        panel: { position: 'absolute', top, bottom: 'auto', height: height + extra, paddingBottom: extra, boxSizing: 'border-box' },
        scrim: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 'auto', height: Math.max(document.documentElement.scrollHeight, top + height + extra) },
    };
};

let locks = 0;

const lockPage = () => {
    locks += 1;
    document.documentElement.style.overflow = 'hidden';
    return () => {
        locks -= 1;
        if (locks === 0) document.documentElement.style.overflow = '';
    };
};

export const usePageLayer = (open) => {
    const [layer, setLayer] = useState(null);

    useLayoutEffect(() => {
        if (!open) return undefined;
        setLayer(measure());
        return lockPage();
    }, [open]);

    return layer;
};
