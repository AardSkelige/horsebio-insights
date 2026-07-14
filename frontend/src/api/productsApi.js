// src/api/productsApi.js
const json = (r) => r.json();

export const productsApi = {
    getList: (params, signal) =>
        fetch(`/api/products/?${params}`, { signal }).then(json),

    getAll: (signal) =>
        fetch('/api/products/', { signal }).then(json),

    getDetails: (id, qs, signal) =>
        fetch(`/api/products/${id}/${qs ? `?${qs}` : ''}`, { signal }).then(json),
};
