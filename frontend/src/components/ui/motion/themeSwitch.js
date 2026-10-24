import { canTransition, runTransition } from './smoothNavigate';

const REVEAL_MS = 550;

export const switchTheme = (next, apply, event) => {
    const root = document.documentElement;
    const commit = () => {
        root.setAttribute('data-theme', next);
        apply(next);
    };
    if (!canTransition()) {
        commit();
        return;
    }
    const rect = event?.currentTarget?.getBoundingClientRect();
    const x = rect ? rect.left + rect.width / 2 : window.innerWidth / 2;
    const y = rect ? rect.top + rect.height / 2 : window.innerHeight / 2;
    const radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));
    runTransition('theme', commit).ready.then(() => {
        root.animate(
            { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
            { duration: REVEAL_MS, easing: 'cubic-bezier(0.65, 0, 0.35, 1)', pseudoElement: '::view-transition-new(root)' },
        );
    }).catch(() => {});
};
