export const greeting = (date) => {
    const hour = date.getHours();
    if (hour < 6) return 'Доброй ночи';
    if (hour < 12) return 'Доброе утро';
    if (hour < 18) return 'Добрый день';
    return 'Добрый вечер';
};

export const today = (date) => date.toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' });

export const updatedLabel = (value) => {
    const date = value ? new Date(value) : null;
    if (!date || Number.isNaN(date.getTime())) return 'Время обновления МойСклад неизвестно';
    const time = date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
    if (date.toDateString() === new Date().toDateString()) return `МойСклад обновлён в ${time}`;
    return `МойСклад обновлён ${date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })} в ${time}`;
};

const sentence = (text) => (/[.!?…]$/.test(text) ? text : `${text}.`);

export const headlineDetails = (headline) => [headline.body, headline.action].filter(Boolean).map(sentence).join(' ');

export const quietLead = ({ complete, read }) => {
    if (!complete) {
        return { title: 'Не все разделы ответили', sub: 'Дела из них сейчас не видны. Загляните сюда чуть позже.', showRead: false };
    }
    if (read.total) {
        const critical = read.critical ? `, из них критичных ${read.critical}` : '';
        return { title: 'Новых дел нет', sub: `Прочитанные ещё не решены: ${read.total}${critical}.`, showRead: true };
    }
    return { title: 'Сегодня ничего не горит', sub: 'Срочных дел в ваших разделах нет.', showRead: false };
};
