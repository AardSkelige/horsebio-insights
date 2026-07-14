// src/api/inventoryApi.js
import { getCookie } from '../utils/api';

export const inventoryApi = {
    getHistory: () =>
        fetch('/api/inventory/history/').then(r => r.json()),

    getCurrent: (params, signal) =>
        fetch(`/api/inventory/current/${params ? `?${params}` : ''}`, { signal }).then(r => r.json()),

    refresh: async (month) => {
        const body = month ? JSON.stringify({ month }) : undefined;
        return fetch('/api/inventory/refresh/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCookie('csrftoken'),
                ...(body ? { 'Content-Type': 'application/json' } : {}),
            },
            body,
        }).then(r => r.json());
    },

    uploadCells: async (file, month) => {
        const form = new FormData();
        form.append('file', file);
        if (month) form.append('month', month);
        return fetch('/api/inventory/upload-cells/', {
            method: 'POST',
            headers: { 'X-CSRFToken': getCookie('csrftoken') },
            body: form,
        }).then(r => r.json());
    },

    getCellsLog: (month) => {
        const q = month ? `?month=${month}` : '';
        return fetch(`/api/inventory/cells-log/${q}`).then(r => r.json());
    },
};
