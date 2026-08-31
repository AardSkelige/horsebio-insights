import PropTypes from 'prop-types';
import { Check, Undo2 } from 'lucide-react';

export const NotificationShape = PropTypes.shape({
    key: PropTypes.string.isRequired,
    source: PropTypes.string,
    source_label: PropTypes.string,
    route: PropTypes.string,
    level: PropTypes.oneOf(['critical', 'warning', 'info']).isRequired,
    title: PropTypes.string.isRequired,
    body: PropTypes.string,
    action: PropTypes.string,
    seen: PropTypes.bool,
});

/**
 * Одно уведомление.
 *
 * Два вида, и они отвечают на разные вопросы:
 *
 *   full — в панели. Только уведомляет: что случилось и из каких цифр это
 *          видно. Что делать — не пишем: решение принимается на странице
 *          раздела, где есть и кнопки, и остальная картина.
 *   line — на странице раздела. Заголовок и действие; цифры уже есть
 *          на карточке позиции рядом.
 *
 * Прочитанность видна двумя признаками сразу: непрочитанное лежит на светлой
 * подложке и с залитой точкой, прочитанное — на пустом фоне и с контурной.
 * Отметку ставит человек кнопкой справа, сама она не ставится: счётчик,
 * гаснущий от факта открытия панели, невозможно понять.
 */
export default function NotificationItem({ item, variant = 'full', showSource = false, onToggleRead }) {
    const line = variant === 'line';
    const read = Boolean(item.seen);

    return (
        <article className={`nt-item${read ? ' nt-item--read' : ''}${line ? ' nt-item--line' : ''}`}>
            <span
                className={`nt-item__dot nt-item__dot--${item.level}`}
                aria-hidden="true"
            />
            <div className="nt-item__main">
                <p className="nt-item__title">
                    {showSource && item.source_label && (
                        <span className="nt-item__source">{item.source_label}</span>
                    )}
                    {item.title}
                </p>
                {line
                    ? item.action && <p className="nt-item__action">{item.action}</p>
                    : item.body && <p className="nt-item__body">{item.body}</p>}
            </div>

            {onToggleRead && (
                <button
                    type="button"
                    className="nt-item__toggle"
                    onClick={() => onToggleRead([item.key], !read)}
                    aria-label={read ? 'Вернуть в непрочитанные' : 'Отметить прочитанным'}
                    title={read ? 'Вернуть в непрочитанные' : 'Отметить прочитанным'}
                >
                    {read ? <Undo2 size={13} /> : <Check size={14} />}
                </button>
            )}
        </article>
    );
}

NotificationItem.propTypes = {
    item: NotificationShape.isRequired,
    variant: PropTypes.oneOf(['full', 'line']),
    showSource: PropTypes.bool,
    onToggleRead: PropTypes.func,
};
