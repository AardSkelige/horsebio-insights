import api from '../utils/api';

export const deadlinesApi = {
    get: (signal) => api.get('/deadlines/', { signal }),
};
