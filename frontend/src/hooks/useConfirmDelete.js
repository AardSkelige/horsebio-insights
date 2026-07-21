import { useState } from 'react';

// Кнопка удаления с подтверждением и спиннером: confirm → run() → onDone().
// setDeleting(false) намеренно только в ветке ошибки — при успехе строка/запись
// исчезает через onDone (список перечитывается), гасить флаг уже не на чем.
// Заменяет одинаковый handleDelete в SiteOrdersTable (RowActions) и HealthResults (FindingRow).
export const useConfirmDelete = ({ confirm, run, onDone }) => {
    const [deleting, setDeleting] = useState(false);

    const trigger = async () => {
        if (!window.confirm(confirm)) return;
        setDeleting(true);
        try {
            await run();
            onDone?.();
        } catch (e) {
            alert(e.message || 'Не удалось удалить');
            setDeleting(false);
        }
    };

    return { deleting, trigger };
};
