// src/api/counterpartiesApi.js
import api from '../utils/api';

export const counterpartiesApi = {
    getList: (params, signal) =>
        api.get('/counterparties/', { params, signal }),

    getGroups: (params, signal) =>
        api.get('/counterparty-groups/', { params, signal }),

    getDetails: (id, params, signal) =>
        api.get(`/counterparties/${id}/`, { params, signal }),
};
