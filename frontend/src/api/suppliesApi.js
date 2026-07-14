// src/api/suppliesApi.js
const json = (r) => r.json();

export const suppliesApi = {
    getAll: (signal) =>
        fetch('/api/supplies/', { signal }).then(json),

    materials: {
        getList: (params, signal) =>
            fetch(`/api/supplies/materials/list/?${params}`, { signal }).then(json),

        getAll: (signal) =>
            fetch('/api/supplies/materials/list/', { signal }).then(json),

        getDetails: (id, qs, signal) =>
            fetch(`/api/supplies/materials/${id}/details/${qs ? `?${qs}` : ''}`, { signal }).then(json),
    },

    suppliers: {
        getList: (params, signal) =>
            fetch(`/api/supplies/suppliers/?${params}`, { signal }).then(json),

        getDetails: (id, qs, signal) =>
            fetch(`/api/supplies/suppliers/${id}/details/${qs ? `?${qs}` : ''}`, { signal }).then(json),
    },
};
