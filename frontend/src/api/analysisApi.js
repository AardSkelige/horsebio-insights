// src/api/analysisApi.js
import { getCsrfToken } from '../utils/api';

export const analysisApi = {
    cashFlow: {
        get: async (dateFrom, dateTo) => {
            const csrfToken = await getCsrfToken();
            const response = await fetch('/api/analysis/cash-flow/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                credentials: 'include',
                body: JSON.stringify({
                    date_from: dateFrom + 'T00:00:00.000',
                    date_to: dateTo + 'T23:59:59.999',
                }),
            });
            return response;
        },

        export: async (dateFrom, dateTo) => {
            const csrfToken = await getCsrfToken();
            return fetch('/api/analysis/cash-flow/export/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                credentials: 'include',
                body: JSON.stringify({
                    date_from: dateFrom + 'T00:00:00.000',
                    date_to: dateTo + 'T23:59:59.999',
                }),
            });
        },
    },

    fbo: {
        get: (signal) =>
            fetch('/api/analysis/fbo/', { signal }).then(r => r.json()),

        export: () =>
            fetch('/api/analysis/fbo/export/'),
    },

    purchase: {
        getMaterial: (materialId, signal) =>
            fetch(`/api/analysis/purchase/material/${materialId}/`, { signal }).then(r => r.json()),
    },
};
