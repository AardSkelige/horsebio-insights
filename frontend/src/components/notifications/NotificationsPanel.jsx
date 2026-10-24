import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { CheckCheck, ChevronRight, RefreshCw } from 'lucide-react';
import { pluralWith } from '../../utils/formatters';
import { CloseButton, IconButton, Notice, Segmented, Skeleton } from '../ui';
import { DrawerShell } from '../ui/motion';
import { useNotifications } from '../../contexts/NotificationsContext';
import NotificationItem from './NotificationItem';
import PushPanelAction from './PushPanelAction';
import './notifications.css';

/** Уведомления по разделам, в порядке от самого серьёзного. */
const groupBySource = (items) => {
    const groups = [];
    const index = new Map();
    items.forEach((item) => {
        if (!index.has(item.source)) {
            index.set(item.source, groups.length);
            groups.push({ source: item.source, label: item.source_label, route: item.source_route || item.route, items: [] });
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
        <DrawerShell open={panelOpen} onClose={closePanel} label="Уведомления" className="nt-panel">
            <div className="ui-drawer__head">
                <h2 className="ui-drawer__title">Уведомления</h2>
                {counts.unseen > 0 && (
                    <span className="nt-panel__count">
                        {pluralWith(counts.unseen, 'новое', 'новых', 'новых')}
                    </span>
                )}
                {counts.unseen > 0 && (
                    <IconButton icon={CheckCheck} label="Прочитать всё" onClick={() => setRead([], true)} />
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

            {readCount > 0 && (
                <div className="nt-panel__bar">
                    <Segmented
                        layoutId="nt-panel-filter"
                        value={showRead ? 'all' : 'new'}
                        onChange={(value) => setShowRead(value === 'all')}
                        options={[
                            { value: 'new', label: `Новые (${counts.unseen})` },
                            { value: 'all', label: `Все (${items.length})` },
                        ]}
                    />
                </div>
            )}

            <div className="ui-drawer__body">
                <PushPanelAction />
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
                        {group.route ? (
                            <Link className="nt-group__head nt-group__head--link" to={group.route} onClick={closePanel}>
                                <span className="nt-group__label">{group.label}</span>
                                <ChevronRight size={16} aria-hidden="true" />
                            </Link>
                        ) : (
                            <div className="nt-group__head">
                                <span className="nt-group__label">{group.label}</span>
                            </div>
                        )}
                        {group.items.map((item) => (
                            <NotificationItem key={item.key} item={item} onToggleRead={setRead} />
                        ))}
                    </section>
                ))}
            </div>
        </DrawerShell>
    );
}
