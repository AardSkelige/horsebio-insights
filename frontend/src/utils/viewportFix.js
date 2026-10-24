const MAX_GAP = 80;

const isIOS = () => /iPhone|iPad|iPod/.test(navigator.userAgent)
    || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);

const isStandalone = () => window.navigator.standalone === true
    || window.matchMedia?.('(display-mode: standalone)').matches === true;

const measure = () => {
    const landscape = window.matchMedia?.('(orientation: landscape)').matches;
    const full = landscape ? Math.min(screen.width, screen.height) : Math.max(screen.width, screen.height);
    const gap = Math.round(full - window.innerHeight);
    const fix = isIOS() && isStandalone() && gap > 0 && gap <= MAX_GAP ? gap : 0;
    document.documentElement.style.setProperty('--vp-fix', `${fix}px`);
};

export const installViewportFix = () => {
    measure();
    window.addEventListener('resize', measure);
    window.addEventListener('orientationchange', measure);
};
