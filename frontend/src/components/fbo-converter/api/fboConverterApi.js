import { getCookie, parserAPI } from '../../../utils/api';

const getCsrfToken = async () => {
    const cookieToken = getCookie('csrftoken');
    if (cookieToken) return cookieToken;
    const csrfResponse = await parserAPI.getCsrfToken();
    return csrfResponse?.csrfToken || '';
};

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

export const convertFboSupply = async (file) => {
    const csrfToken = await getCsrfToken();
    if (!csrfToken) throw new Error('Не удалось получить CSRF токен');

    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch('/api/ozon/fbo-converter/convert/', {
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken },
        credentials: 'include',
        body: formData,
    });

    if (!response.ok) {
        const text = await response.text();
        let msg = `Ошибка сервера (${response.status})`;
        try { msg = JSON.parse(text)?.message || msg; } catch { /* ignore parse error */ }
        throw new Error(msg);
    }

    const blob = await response.blob();
    const date = new Date().toISOString().slice(0, 10);
    downloadBlob(blob, `fbo_supply_${date}.xlsx`);
};
