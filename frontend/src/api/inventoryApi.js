// src/api/inventoryApi.js
import api from '../utils/api';

export const inventoryApi = {
    getHistory: () =>
        api.get('/inventory/history/'),

    getCurrent: (params, signal) =>
        api.get('/inventory/current/', { params: params || undefined, signal }),

    refresh: async (month) => {
        return api.post('/inventory/refresh/', month ? { month } : undefined);
    },

    uploadCells: async (file, month) => {
        const form = new FormData();
        form.append('file', file);
        if (month) form.append('month', month);
        return api.post('/inventory/upload-cells/', form);
    },

    getCellsLog: (month) => {
        return api.get('/inventory/cells-log/', {
            params: month ? { month } : undefined,
        });
    },
};
