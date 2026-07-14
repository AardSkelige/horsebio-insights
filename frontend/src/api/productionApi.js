// src/api/productionApi.js
import { getCsrfToken } from '../utils/api';

export const productionApi = {
    searchProducts: (query, limit = 10) =>
        fetch(`/api/production/products/search/?search=${encodeURIComponent(query)}&limit=${limit}`)
            .then(r => r.json()),

    calculateFromFile: async (file) => {
        const csrfToken = await getCsrfToken();
        const formData = new FormData();
        formData.append('file', file);
        return fetch('/api/production/calculate/', {
            method: 'POST',
            headers: { 'X-CSRFToken': csrfToken },
            credentials: 'include',
            body: formData,
        });
    },

    calculateFromItems: async (items) => {
        const csrfToken = await getCsrfToken();
        return fetch('/api/production/calculate-json/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            credentials: 'include',
            body: JSON.stringify({ items }),
        });
    },

    export: async (result) => {
        const csrfToken = await getCsrfToken();
        return fetch('/api/production/export/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            credentials: 'include',
            body: JSON.stringify(result),
        });
    },
};
