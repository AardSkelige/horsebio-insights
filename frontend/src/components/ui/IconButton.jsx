import PropTypes from 'prop-types';
import { X } from 'lucide-react';

/**
 * Кнопка-иконка без подписи: закрыть, очистить, свернуть.
 *
 * `label` обязателен — он уходит в `aria-label`. Иконка без текста для
 * скринридера немая, а такие кнопки в приложении часто единственный способ
 * закрыть диалог.
 */
export default function IconButton({
    icon: Icon,
    label,
    size = 16,
    tone = 'muted',
    as = 'button',
    className = '',
    ...rest
}) {
    const classes = ['ui-icon-btn', `ui-icon-btn--${tone}`, className].filter(Boolean).join(' ');
    const content = <Icon size={size} aria-hidden="true" />;

    // Внешняя ссылка выглядит так же, как кнопка: в таблицах рядом стоят
    // и переходы в МойСклад, и действия вроде удаления
    if (as === 'a') {
        return (
            <a className={classes} aria-label={label} title={label} {...rest}>
                {content}
            </a>
        );
    }

    return (
        <button type="button" className={classes} aria-label={label} title={label} {...rest}>
            {content}
        </button>
    );
}

IconButton.propTypes = {
    icon: PropTypes.elementType.isRequired,
    label: PropTypes.string.isRequired,
    size: PropTypes.number,
    tone: PropTypes.oneOf(['muted', 'ink', 'danger']),
    as: PropTypes.oneOf(['button', 'a']),
    className: PropTypes.string,
};

/** Закрытие диалога — тот же примитив с закреплённой иконкой и подписью. */
export function CloseButton(props) {
    return <IconButton icon={X} label="Закрыть" size={18} {...props} />;
}
