import PropTypes from 'prop-types';
import { AlertTriangle, Inbox, RefreshCw } from 'lucide-react';
import Button from './Button';

/**
 * Пустое состояние: данных нет, и это нормально.
 *
 * `hint` объясняет, что сделать, чтобы они появились — без него пустой экран
 * читается как поломка.
 */
export function EmptyState({ title = 'Нет данных', hint, icon: Icon = Inbox, inline = false, action }) {
    return (
        <div className={`ui-state${inline ? ' ui-state--inline' : ''}`}>
            <span className="ui-state__icon"><Icon size={20} aria-hidden="true" /></span>
            <span className="ui-state__title">{title}</span>
            {hint && <span className="ui-state__hint">{hint}</span>}
            {action}
        </div>
    );
}

EmptyState.propTypes = {
    title: PropTypes.node,
    hint: PropTypes.node,
    icon: PropTypes.elementType,
    inline: PropTypes.bool,
    action: PropTypes.node,
};

/**
 * Ошибка загрузки. С `onRetry` показывает кнопку повтора: тупик без выхода
 * заставляет человека перезагружать страницу целиком.
 */
export function ErrorState({ title = 'Не удалось загрузить данные', hint, onRetry, inline = false }) {
    return (
        <div className={`ui-state ui-state--error${inline ? ' ui-state--inline' : ''}`} role="alert">
            <span className="ui-state__icon"><AlertTriangle size={20} aria-hidden="true" /></span>
            <span className="ui-state__title">{title}</span>
            {hint && <span className="ui-state__hint">{hint}</span>}
            {onRetry && (
                <Button variant="ghost" size="sm" icon={RefreshCw} onClick={onRetry}>
                    Попробовать ещё раз
                </Button>
            )}
        </div>
    );
}

ErrorState.propTypes = {
    title: PropTypes.node,
    hint: PropTypes.node,
    onRetry: PropTypes.func,
    inline: PropTypes.bool,
};
