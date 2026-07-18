// Единый темп анимаций Recharts: дефолтные 1500ms слишком вальяжны
// для аналитики. При системном reduced motion анимация отключается.
const prefersReducedMotion =
    typeof window !== 'undefined' &&
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

export const CHART_ANIMATION = {
    animationDuration: 500,
    animationEasing: 'ease-out',
    isAnimationActive: !prefersReducedMotion,
};
