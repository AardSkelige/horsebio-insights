// src/api/counterpartiesApi.js
const json = (r) => r.json();

export const counterpartiesApi = {
    getList: (params, signal) =>
        fetch(`/api/counterparties/?${params}`, { signal }).then(json),

    getGroups: (params, signal) =>
        fetch(`/api/counterparty-groups/?${params}`, { signal }).then(json),
};
