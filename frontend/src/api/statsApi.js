import api from '../utils/api';

export const statsApi = {
    get: (signal) =>
        api.get('/stats/', { signal }),
};
