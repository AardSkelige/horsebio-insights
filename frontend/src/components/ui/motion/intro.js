import { useSyncExternalStore } from 'react';

const CHART_AT = 600;
const LEAD_AFTER_CHART = 1700;
const LEAD_WITHOUT_CHART = 1000;
const OUTRO_MS = 750;
const LEAD_PLAY_MS = 1150;
const SCENE_MIN_MS = 3300;

let playing = false;
let full = false;
let startedAt = 0;
let lastPath = null;
let leaving = false;
const listeners = new Set();

export const reducedMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;

export const introFor = (pathname, fresh) => {
    if (fresh) {
        lastPath = null;
        leaving = false;
    }
    if (pathname === lastPath) return playing;
    playing = pathname === '/' && !reducedMotion();
    full = playing && lastPath === null;
    if (playing) startedAt = performance.now();
    lastPath = pathname;
    return playing;
};

export const introFull = () => full;

export const endIntro = () => {
    if (!playing) return;
    playing = false;
    listeners.forEach((listener) => listener());
};

export const leaveApp = () => {
    if (reducedMotion()) return Promise.resolve();
    leaving = true;
    playing = false;
    listeners.forEach((listener) => listener());
    return new Promise((resolve) => { setTimeout(resolve, OUTRO_MS); });
};

export const introChartStart = (dataAt) => Math.max(dataAt, startedAt + CHART_AT);

export const introLeadAt = (chartAt) => (chartAt === null ? startedAt + LEAD_WITHOUT_CHART : chartAt + LEAD_AFTER_CHART);

export const introEndAt = (leadAt) => Math.max(leadAt + LEAD_PLAY_MS, startedAt + SCENE_MIN_MS);

const subscribe = (listener) => {
    listeners.add(listener);
    return () => listeners.delete(listener);
};

export const useIntro = () => useSyncExternalStore(subscribe, () => playing);

export const useLeaving = () => useSyncExternalStore(subscribe, () => leaving);
