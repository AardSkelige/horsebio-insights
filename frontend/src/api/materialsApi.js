// src/api/materialsApi.js
import api from '../utils/api';

export const materialsApi = {
    getList: (params, signal) =>
        api.get('/materials/', { params, signal }),

    getAll: (signal) =>
        api.get('/materials/', { signal }),

    getDetails: (id, qs, signal) =>
        api.get(`/materials/${id}/`, { params: qs || undefined, signal }),

    getPeriod: (id, params, signal) =>
        api.get(`/materials/${id}/period/`, { params: params || undefined, signal }),

    patchPeriod: async (id, periodMonths) => {
        return api.patch(`/materials/${id}/period/`, { period_months: periodMonths });
    },
};
