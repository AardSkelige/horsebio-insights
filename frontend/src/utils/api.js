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

const api = axios.create({
    baseURL: '/api',
    headers: {
        'Content-Type': 'application/json',
    },
    withCredentials: true
});

api.interceptors.request.use(config => {
    const csrfToken = getCookie('csrftoken');
    if (csrfToken) {
        config.headers['X-CSRFToken'] = csrfToken;
    }
    return config;
});

api.interceptors.response.use(
    response => response.data,
    error => {
        console.error('API Error:', error.response || error);
        throw new Error(
            error.response?.data?.message ||
            'Произошла ошибка при загрузке данных. Пожалуйста, попробуйте позже.'
        );
    }
);

export const getCsrfToken = async () => {
    const cookieToken = getCookie('csrftoken');
    if (cookieToken) return cookieToken;
    const res = await fetch('/parser/csrf/', { method: 'GET', credentials: 'include' });
    const data = await res.json();
    return data.csrfToken || null;
};

export const parserAPI = {
    async getCsrfToken() {
        const response = await fetch('/parser/csrf/', {
            method: 'GET',
            credentials: 'include'
        });
        return response.json();
    },

    async loadData(csrfToken, { startDate, endDate, months }) {
        const response = await fetch('/parser/load-data/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            credentials: 'include',
            body: JSON.stringify({
                startDate,
                endDate,
                months
            })
        });

        if (!response.ok) {
            const text = await response.text();
            console.error('Server response:', text);
            throw new Error('Ошибка сервера');
        }

        return response.json();
    }
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
