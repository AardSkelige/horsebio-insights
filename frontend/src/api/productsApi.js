// src/api/productsApi.js
import api from '../utils/api';

export const productsApi = {
    getList: (params, signal) =>
        api.get('/products/', { params, signal }),

    getAll: (signal) =>
        api.get('/products/', { signal }),

    getDetails: (id, qs, signal) =>
        api.get(`/products/${id}/`, { params: qs || undefined, signal }),
};
