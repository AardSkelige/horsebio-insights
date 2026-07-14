export const formatCurrency = (value) => {
    if (value === null || value === undefined) return '-';
    return new Intl.NumberFormat('ru-RU', {
        style: 'currency',
        currency: 'RUB',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(value);
};

export const formatNumber = (num) => {
    if (num === null || num === undefined) return '-';
    return Math.round(num).toLocaleString('ru-RU');
};

export const formatDate = (dateString) => {
    if (!dateString) return '-';
    const s = String(dateString).replace(' ', 'T');
    const [y, m, d] = s.substring(0, 10).split('-');
    if (!y || !m || !d) return dateString;
    return `${d}.${m}.${y}`;
};

export const formatDateTime = (dateString) => {
    if (!dateString) return '-';
    const s = String(dateString).replace(' ', 'T');
    const date = new Date(s);
    if (isNaN(date.getTime())) return formatDate(dateString);
    return date.toLocaleDateString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
};