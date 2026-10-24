import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { pluralWith } from '../../utils/formatters';
import { CloseButton, IconButton, Notice, Skeleton } from '../ui';
import { DrawerShell } from '../ui/motion';
import { useNotifications } from '../../contexts/NotificationsContext';
import NotificationItem from './NotificationItem';
import './notifications.css';

/** Уведомления по разделам, в порядке от самого серьёзного. */
const groupBySource = (items) => {
    const groups = [];
    const index = new Map();
    items.forEach((item) => {
        if (!index.has(item.source)) {
            index.set(item.source, groups.length);
            groups.push({ source: item.source, label: item.source_label, route: item.route, items: [] });
        }
        groups[index.get(item.source)].items.push(item);
    });
    return groups;
};

/**
 * Панель уведомлений.
 *
 * Панель только уведомляет: что случилось и из каких цифр это видно. Что
 * делать — написано на странице раздела, туда ведёт «Открыть» у каждого
 * раздела: решение принимают, глядя на всю картину, а не на строчку в шторке.
 *
 * Открытие панели ничего не помечает. Прочитанность ставит человек — кнопкой
 * у уведомления или «Прочитать всё» в шапке, — и её же можно снять. Иначе
 * счётчик и точки в меню гаснут сами собой, и понять это невозможно.
 */
export default function NotificationsPanel() {
    const {
        items, counts, complete, loading, error, panelOpen, showRead, setShowRead, closePanel, reload, setRead,
    } = useNotifications();

    const readCount = items.length - counts.unseen;
    const visible = useMemo(() => (showRead ? items : items.filter((item) => !item.seen)), [items, showRead]);
    const groups = useMemo(() => groupBySource(visible), [visible]);

    return (
        <DrawerShell open={panelOpen} onClose={closePanel} label="Уведомления">
            <div className="ui-drawer__head">
                <h2 className="ui-drawer__title">Уведомления</h2>
                {counts.unseen > 0 && (
                    <span className="nt-panel__count">
                        {pluralWith(counts.unseen, 'новое', 'новых', 'новых')}
                    </span>
                )}
                <IconButton
                    icon={RefreshCw}
                    label="Обновить"
                    className={loading ? 'animate-spin' : ''}
                    disabled={loading}
                    onClick={() => reload(true)}
                />
                <CloseButton onClick={closePanel} />
            </div>

            {(counts.unseen > 0 || readCount > 0) && (
                <div className="nt-panel__bar">
                    {counts.unseen > 0 && (
                        <button type="button" className="nt-panel__all" onClick={() => setRead([], true)}>
                            Прочитать всё
                        </button>
                    )}
                    {readCount > 0 && (
                        <button type="button" className="nt-panel__all" onClick={() => setShowRead(!showRead)}>
                            {showRead ? 'Скрыть прочитанные' : `Показать прочитанные (${readCount})`}
                        </button>
                    )}
                </div>
            )}

            <div className="ui-drawer__body">
                {error && <Notice tone="error">{error}</Notice>}
                {!complete && !error && <Notice tone="warning">Не все разделы ответили, список может быть неполным</Notice>}

                {loading && items.length === 0 && !error && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, paddingTop: 14 }}>
                        <Skeleton height={44} />
                        <Skeleton height={44} />
                    </div>
                )}

                {!loading && items.length === 0 && complete && (
                    <p className="nt-panel__empty">Ничего не требует внимания</p>
                )}

                {!loading && items.length > 0 && visible.length === 0 && !error && (
                    <p className="nt-panel__empty">Новых нет</p>
                )}

                {groups.map((group) => (
                    <section className="nt-group" key={group.source}>
                        <div className="nt-group__head">
                            <span className="nt-group__label">{group.label}</span>
                            {group.route && (
                                <Link className="nt-group__link" to={group.route} onClick={closePanel}>
                                    Открыть
                                </Link>
                            )}
                        </div>
                        {group.items.map((item) => (
                            <NotificationItem key={item.key} item={item} onToggleRead={setRead} />
                        ))}
                    </section>
                ))}
            </div>
        </DrawerShell>
    );
}
