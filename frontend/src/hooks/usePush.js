import { useSyncExternalStore } from 'react';
import { pushApi } from '../api/pushApi';

export const pushSupported = () => typeof window !== 'undefined'
    && 'serviceWorker' in navigator && 'PushManager' in window;

const isIOS = () => /iPhone|iPad|iPod/.test(navigator.userAgent)
    || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);

const isStandalone = () => window.navigator.standalone === true
    || window.matchMedia?.('(display-mode: standalone)').matches === true;

const fromNotification = () => (typeof Notification === 'undefined' ? 'default' : Notification.permission);

const detect = () => {
    if (pushSupported()) return { permission: fromNotification(), needsInstall: false };
    return { permission: 'unsupported', needsInstall: typeof window !== 'undefined' && isIOS() && !isStandalone() };
};

let state = { ...detect(), dismissed: false, asked: false };
let prepared = null;
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

const PERMISSION = { granted: 'granted', denied: 'denied', prompt: 'default' };

const readPermission = async (registration) => {
    try {
        const value = await registration.pushManager.permissionState({ userVisibleOnly: true });
        return PERMISSION[value] || fromNotification();
    } catch {
        return fromNotification();
    }
};

export const preparePush = async () => {
    if (!pushSupported()) return null;
    if (prepared) return prepared;
    const registration = await navigator.serviceWorker.ready;
    const { publicKey } = await pushApi.key();
    prepared = { registration, publicKey };
    setState({ permission: await readPermission(registration) });
    return prepared;
};

export const subscribeDevice = async () => {
    const { registration, publicKey } = await preparePush();
    let subscription = await registration.pushManager.getSubscription();
    if (!subscription) {
        subscription = await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: toBytes(publicKey) });
    }
    await pushApi.subscribe(subscription.toJSON());
};

export const unsubscribeDevice = async () => {
    if (!pushSupported()) return;
    const registration = await navigator.serviceWorker.getRegistration();
    const subscription = await registration?.pushManager.getSubscription();
    if (subscription) await pushApi.unsubscribe(subscription.endpoint);
};

export const enablePush = async () => {
    const asked = typeof Notification === 'undefined' ? null : Notification.requestPermission();
    if (asked) await asked.catch(() => null);
    const ready = prepared || await preparePush();
    let subscription;
    try {
        subscription = await ready.registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: toBytes(ready.publicKey),
        });
    } catch (error) {
        const permission = await readPermission(ready.registration);
        setState({ permission });
        if (permission === 'denied') return 'denied';
        throw error;
    }
    await pushApi.subscribe(subscription.toJSON());
    setState({ permission: 'granted' });
    return 'granted';
};

export const pushDiagnostics = async () => {
    const registration = prepared?.registration;
    const push = registration ? await registration.pushManager.permissionState({ userVisibleOnly: true }).catch((e) => e.name) : 'нет';
    return `Notification=${fromNotification()}, push=${push}, приложение=${isStandalone() ? 'да' : 'нет'}`;
};

export const dismissPush = () => setState({ dismissed: true, asked: false });

export const offerPush = () => setState({ dismissed: false, asked: true });

export const onIOS = () => isIOS();

export const usePush = () => useSyncExternalStore(subscribe, () => state);

export const canOffer = ({ permission, needsInstall }) => permission === 'default' || needsInstall;
