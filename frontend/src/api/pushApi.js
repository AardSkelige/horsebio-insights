import api from '../utils/api';

export const pushApi = {
    key: () => api.get('/push/'),
    subscribe: (subscription) => api.post('/push/subscribe/', subscription),
    unsubscribe: (endpoint) => api.post('/push/unsubscribe/', { endpoint }),
    test: () => api.post('/push/test/'),
};
