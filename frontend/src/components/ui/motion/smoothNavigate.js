import { flushSync } from 'react-dom';
import { reducedMotion } from './intro';

let current = null;

export const canTransition = () => Boolean(document.startViewTransition) && !reducedMotion();

export const runTransition = (kind, update) => {
    const root = document.documentElement;
    root.dataset.transition = kind;
    const transition = document.startViewTransition(() => flushSync(update));
    current = transition;
    transition.finished.catch(() => {}).finally(() => {
        if (current === transition) delete root.dataset.transition;
    });
    return transition;
};

export const smoothNavigate = (navigate, to, { slow = false, ...options } = {}) => {
    if (!canTransition()) {
        navigate(to, options);
        return;
    }
    runTransition(slow ? 'slow' : 'nav', () => navigate(to, options));
};

export const isPlainClick = (event) => event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
