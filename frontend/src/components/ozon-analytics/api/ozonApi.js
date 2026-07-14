// src/components/ozon-analytics/api/ozonApi.js
import axios from 'axios';

const BASE_URL = '/api/ozon';

// File download via redirect - no API call needed
export const exportAdvertisingData = async (startDate, endDate) => {
    window.location.href = `${BASE_URL}/advertising/export/?startDate=${startDate}&endDate=${endDate}`;
};

export const exportSalesData = async (startDate, endDate) => {
    window.location.href = `${BASE_URL}/sales/export/?startDate=${startDate}&endDate=${endDate}`;
};

// Helper to download blob response as file
const downloadBlob = (blob, filename) => {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
};

export const generateReport = async (adsFile, productsFile) => {
    const formData = new FormData();
    formData.append('ads_file', adsFile);
    formData.append('products_file', productsFile);

    const response = await axios.post(`${BASE_URL}/report/`, formData, {
        responseType: 'blob',
        headers: { 'Content-Type': 'multipart/form-data' }
    });

    downloadBlob(response.data, `DRR_отчет_эффективность_рекламы_${new Date().toISOString().slice(0, 10)}.xlsx`);
};

export const processCompetitorsInfo = async (file) => {
    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await axios.post(`${BASE_URL}/competitors/process/`, formData, {
            responseType: 'blob',
            headers: { 'Content-Type': 'multipart/form-data' }
        });

        downloadBlob(response.data, `competitors_info_${new Date().toISOString().slice(0, 10)}.xlsx`);
        return true;
    } catch (error) {
        console.error('Ошибка при обработке информации о конкурентах:', error);
        throw error;
    }
};

export const processStockAvailability = async (file) => {
    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await axios.post(`${BASE_URL}/stock/process/`, formData, {
            responseType: 'blob',
            headers: { 'Content-Type': 'multipart/form-data' }
        });

        downloadBlob(response.data, `stock_availability_${new Date().toISOString().slice(0, 10)}.xlsx`);
        return true;
    } catch (error) {
        console.error('Ошибка при обработке информации о доступности товаров:', error);
        throw error;
    }
};
