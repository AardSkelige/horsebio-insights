// src/api/analysisApi.js
import api from '../utils/api';

export const analysisApi = {
    cashFlow: {
        get: (dateFrom, dateTo) =>
            api.post('/analysis/cash-flow/', {
                    date_from: dateFrom + 'T00:00:00.000',
                    date_to: dateTo + 'T23:59:59.999',
            }),

        export: (dateFrom, dateTo) =>
            api.post('/analysis/cash-flow/export/', {
                    date_from: dateFrom + 'T00:00:00.000',
                    date_to: dateTo + 'T23:59:59.999',
            }, { responseType: 'blob' }),
    },

    fbo: {
        get: (signal) =>
            api.get('/analysis/fbo/', { signal }),

        export: () =>
            api.get('/analysis/fbo/export/', { responseType: 'blob' }),
    },

    purchase: {
        getMaterial: (materialId, signal) =>
            api.get(`/analysis/purchase/material/${materialId}/`, { signal }),
    },
};
