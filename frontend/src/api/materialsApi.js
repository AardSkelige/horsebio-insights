// src/api/materialsApi.js
import { getCsrfToken } from '../utils/api';

const json = (r) => r.json();

export const materialsApi = {
    getList: (params, signal) =>
        fetch(`/api/materials/?${params}`, { signal }).then(json),

    getAll: (signal) =>
        fetch('/api/materials/', { signal }).then(json),

    getDetails: (id, qs, signal) =>
        fetch(`/api/materials/${id}/${qs ? `?${qs}` : ''}`, { signal }).then(json),

    getPeriod: (id, params, signal) =>
        fetch(`/api/materials/${id}/period/${params ? `?${params}` : ''}`, { signal }).then(json),

    patchPeriod: async (id, periodMonths) => {
        const csrfToken = await getCsrfToken();
        return fetch(`/api/materials/${id}/period/`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            credentials: 'include',
            body: JSON.stringify({ period_months: periodMonths }),
        }).then(json);
    },
};
