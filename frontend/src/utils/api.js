// src/utils/api.js
import axios from 'axios';

export function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

const createClient = (baseURL) => {
    const client = axios.create({
        baseURL,
        withCredentials: true,
    });

    client.interceptors.request.use(config => {
        if (typeof config.params === 'string') {
            config.params = new URLSearchParams(config.params);
        }

        const method = config.method?.toUpperCase();
        if (method && !['GET', 'HEAD', 'OPTIONS'].includes(method)) {
            const csrfToken = getCookie('csrftoken');
            if (csrfToken) config.headers['X-CSRFToken'] = csrfToken;
        }
        return config;
    });

    client.interceptors.response.use(
        response => response.data,
        error => {
            if (axios.isCancel(error) || error.code === 'ERR_CANCELED') {
                const cancellationError = new Error('Request canceled');
                cancellationError.name = 'AbortError';
                cancellationError.cause = error;
                throw cancellationError;
            }

            const apiError = new Error(
                error.response?.data?.message ||
                error.response?.data?.error ||
                error.message ||
                'Произошла ошибка при загрузке данных. Пожалуйста, попробуйте позже.'
            );
            apiError.status = error.response?.status;
            apiError.data = error.response?.data;
            apiError.cause = error;
            throw apiError;
        }
    );

    return client;
};

const api = createClient('/api');
const parserClient = createClient('/parser');

export const downloadBlob = (blob, filename) => {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
};

export const getCsrfToken = async () => {
    const csrfToken = getCookie('csrftoken');
    if (csrfToken) return csrfToken;
    const data = await parserClient.get('/csrf/');
    return data.csrfToken || null;
};

export const parserAPI = {
    getCsrfToken: () => parserClient.get('/csrf/'),

    async loadData(csrfToken, { startDate, endDate, months }) {
        return parserClient.post('/load-data/', {
            startDate,
            endDate,
            months,
        }, {
            headers: {
                'X-CSRFToken': csrfToken
            },
        });
    },

    stopLoading: () => parserClient.post('/stop-loading/'),
    getTaskStatus: () => parserClient.get('/task-status/'),
};

export const dataAPI = {
    getLatestData: async () => {
        try {
            const response = await api.get('/latest/');
            return response;
        } catch (error) {
            console.error('Error fetching latest data:', error);
            throw error;
        }
    },

    getShipments: async (params) => {
        try {
            const response = await api.get('/shipments/', { params });
            return response;
        } catch (error) {
            console.error('Error in getShipments:', error);
            throw error;
        }
    },

    getStats: async () => {
        try {
            const response = await api.get('/stats/');
            return response;
        } catch (error) {
            console.error('Error in getStats:', error);
            throw error;
        }
    },

    getShipmentStatistics: async (params) => {
        try {
            const response = await api.get('/shipments/statistics/', { params });
            return response;
        } catch (error) {
            console.error('Error fetching shipment statistics:', error);
            throw error;
        }
    },

    getShipmentDetails: async (shipmentId) => {
        try {
            const response = await api.get(`/shipments/details/${shipmentId}/`);
            return response;
        } catch (error) {
            console.error('Error fetching shipment details:', error);
            throw error;
        }
    }
};

export default api;
