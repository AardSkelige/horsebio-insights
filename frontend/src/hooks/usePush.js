import { useSyncExternalStore } from 'react';
import { pushApi } from '../api/pushApi';

export const pushSupported = () => typeof window !== 'undefined'
    && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;

const isIOS = () => /iPhone|iPad|iPod/.test(navigator.userAgent)
    || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);

const isStandalone = () => window.navigator.standalone === true
    || window.matchMedia?.('(display-mode: standalone)').matches === true;

const detect = () => {
    if (pushSupported()) return { permission: Notification.permission, needsInstall: false };
    return { permission: 'unsupported', needsInstall: typeof window !== 'undefined' && isIOS() && !isStandalone() };
};

let state = { ...detect(), dismissed: false };
const listeners = new Set();

const setState = (patch) => {
    state = { ...state, ...patch };
    listeners.forEach((listener) => listener());
};

const subscribe = (listener) => {
    listeners.add(listener);
    return () => listeners.delete(listener);
};

const toBytes = (base64) => {
    const padded = (base64 + '='.repeat((4 - (base64.length % 4)) % 4)).replace(/-/g, '+').replace(/_/g, '/');
    return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
};

export const subscribeDevice = async () => {
    const registration = await navigator.serviceWorker.ready;
    let subscription = await registration.pushManager.getSubscription();
    if (!subscription) {
        const { publicKey } = await pushApi.key();
        if (!publicKey) return;
        subscription = await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: toBytes(publicKey),
        });
    }
    await pushApi.subscribe(subscription.toJSON());
};

export const unsubscribeDevice = async () => {
    if (!pushSupported() || Notification.permission !== 'granted') return;
    const registration = await navigator.serviceWorker.getRegistration();
    const subscription = await registration?.pushManager.getSubscription();
    if (subscription) await pushApi.unsubscribe(subscription.endpoint);
};

export const enablePush = async () => {
    const permission = await Notification.requestPermission();
    setState({ permission });
    if (permission === 'granted') await subscribeDevice();
    return permission;
};

export const onIOS = () => isIOS();

export const dismissPush = () => setState({ dismissed: true });

export const offerPush = () => setState({ dismissed: false });

export const usePush = () => useSyncExternalStore(subscribe, () => state);

export const canOffer = ({ permission, needsInstall }) => permission === 'default' || needsInstall;
