import api from '../utils/api';

/**
 * Уведомления разделов.
 *
 * Список считается на сервере заново по живым данным при каждом запросе — своей
 * истории у уведомлений нет (см. backend/api/notifications/core.py). Отметка
 * о прочтении персональная, и эндпоинт отметки возвращает уже пересчитанный
 * список, поэтому второй запрос за ним не нужен.
 */
export const notificationsApi = {
    list: (params, signal) => api.get('/notifications/', { params, signal }),
    // Пустой список ключей означает «все» — так работает «Прочитать всё».
    // read=false возвращает уведомление в непрочитанные.
    setRead: (keys = [], read = true) => api.post('/notifications/read/', { keys, read }),
};
