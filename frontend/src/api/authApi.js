// src/api/authApi.js
import api, { parserAPI } from '../utils/api';

export const authApi = {
    check: (signal) => api.get('/auth/check/', {
        signal,
        headers: { 'Cache-Control': 'no-cache' },
    }),

    activity: (signal) =>
        api.get('/auth/activity/', { signal }),

    home: (signal) =>
        api.get('/auth/home/', { signal }),

    updateHome: (pinnedPaths) =>
        api.patch('/auth/home/', { pinnedPaths }),

    login: async (username, password) => {
        const csrfData = await parserAPI.getCsrfToken();
        const formData = new FormData();
        formData.append('username', username);
        formData.append('password', password);
        return api.post('/auth/login/', formData, {
            headers: { 'X-CSRFToken': csrfData.csrfToken },
        });
    },

    logout: () =>
        api.post('/auth/logout/'),

    track: (path, name, duration, keepalive = false) =>
        api.post('/auth/track/', { path, name, duration }, {
            fetchOptions: keepalive ? { keepalive: true } : undefined,
        }).catch(() => {}),

    usage: (signal) =>
        api.get('/auth/usage/', { signal }),

    adminAnalytics: (signal, month) => {
        return api.get('/auth/admin-analytics/', {
            params: month ? { month } : undefined,
            signal,
        });
    },

    sessions: (signal) =>
        api.get('/auth/sessions/', { signal }),

    revokeSession: (sessionId) =>
        api.delete(`/auth/sessions/${sessionId}/revoke/`),

    // Постраничные доступы (только суперпользователь)
    pagesAccess: (signal) =>
        api.get('/auth/pages-access/', { signal }),

    savePagesAccess: (userId, pages) =>
        api.post('/auth/pages-access/', { user_id: userId, pages }),
};
