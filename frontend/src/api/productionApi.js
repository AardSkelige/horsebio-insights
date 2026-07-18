// src/api/productionApi.js
import api from '../utils/api';

export const productionApi = {
    searchProducts: (query, limit = 10) =>
        api.get('/production/products/search/', { params: { search: query, limit } }),

    calculateFromFile: async (file) => {
        const formData = new FormData();
        formData.append('file', file);
        return api.post('/production/calculate/', formData);
    },

    calculateFromItems: async (items) => {
        return api.post('/production/calculate-json/', { items });
    },

    export: async (result) => {
        return api.post('/production/export/', result, { responseType: 'blob' });
    },
};
