self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

self.addEventListener('push', (event) => {
    const data = event.data ? event.data.json() : {};
    event.waitUntil(self.registration.showNotification(data.title || 'HorseBio Insights', {
        body: data.body || '',
        icon: '/icon-192.png',
        badge: '/icon-192.png',
        tag: data.tag,
        data: { url: data.url || '/' },
    }));
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const path = event.notification.data?.url || '/';
    event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
        const own = clients.filter((one) => one.url.startsWith(self.location.origin));
        const client = own.find((one) => one.focused) || own[0];
        if (!client) return self.clients.openWindow(path);
        if (new URL(client.url).pathname.startsWith('/login')) return client.navigate(path).then((one) => one && one.focus());
        client.postMessage({ type: 'open', path });
        return client.focus();
    }));
});
