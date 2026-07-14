// src/api/statsApi.js
export const statsApi = {
    get: (signal) =>
        fetch('/api/stats/', { credentials: 'include', signal }).then(r => r.json()),
};
