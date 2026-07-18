// src/api/suppliesApi.js
import api from '../utils/api';

export const suppliesApi = {
    getAll: (signal) =>
        api.get('/supplies/', { signal }),

    materials: {
        getList: (params, signal) =>
            api.get('/supplies/materials/list/', { params, signal }),

        getAll: (signal) =>
            api.get('/supplies/materials/list/', { signal }),

        getDetails: (id, qs, signal) =>
            api.get(`/supplies/materials/${id}/details/`, { params: qs || undefined, signal }),
    },

    suppliers: {
        getList: (params, signal) =>
            api.get('/supplies/suppliers/', { params, signal }),

        getDetails: (id, qs, signal) =>
            api.get(`/supplies/suppliers/${id}/details/`, { params: qs || undefined, signal }),
    },
};
