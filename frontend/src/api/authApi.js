// src/api/authApi.js
import { getCookie, getCsrfToken, parserAPI } from '../utils/api';

const json = (r) => r.json();

export const authApi = {
    check: async (signal) => {
        const r = await fetch('/api/auth/check/', { credentials: 'include', cache: 'no-store', signal });
        if (!r.ok) throw new Error(`Auth check failed with status ${r.status}`);
        return r.json();
    },

    activity: (signal) =>
        fetch('/api/auth/activity/', { credentials: 'include', signal }).then(json),

    login: async (username, password) => {
        const csrfData = await parserAPI.getCsrfToken();
        const formData = new FormData();
        formData.append('username', username);
        formData.append('password', password);
        return fetch('/api/auth/login/', {
            method: 'POST',
            credentials: 'include',
            headers: { 'X-CSRFToken': csrfData.csrfToken },
            body: formData,
        });
    },

    logout: () =>
        fetch('/api/auth/logout/', {
            method: 'POST',
            credentials: 'include',
            headers: { 'X-CSRFToken': getCookie('csrftoken') || '' },
        }),

    track: (path, name, duration) =>
        fetch('/api/auth/track/', {
            method: 'POST',
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken') || '',
            },
            body: JSON.stringify({ path, name, duration }),
        }).catch(() => {}),

    usage: (signal) =>
        fetch('/api/auth/usage/', { credentials: 'include', signal }).then(r => r.json()),

    adminAnalytics: (signal, month) => {
        const url = month
            ? `/api/auth/admin-analytics/?month=${month}`
            : '/api/auth/admin-analytics/';
        return fetch(url, { credentials: 'include', signal }).then(r => r.json());
    },

    sessions: (signal) =>
        fetch('/api/auth/sessions/', { credentials: 'include', signal }).then(r => r.json()),

    revokeSession: (sessionId) =>
        fetch(`/api/auth/sessions/${sessionId}/revoke/`, {
            method: 'DELETE',
            credentials: 'include',
            headers: { 'X-CSRFToken': getCookie('csrftoken') || '' },
        }).then(r => r.json()),
};
