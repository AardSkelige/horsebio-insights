import PropTypes from 'prop-types';
import { AlertCircle, AlertTriangle, CheckCircle, Info, Loader2, X } from 'lucide-react';

const ICON = {
    success: CheckCircle,
    error: AlertCircle,
    warning: AlertTriangle,
    info: Info,
    loading: Loader2,
};

/**
 * Плашка результата действия: «файл обработан», «сайт не принял обмен».
 *
 * Отличается от `ErrorState` тем, что не заменяет собой содержимое, а появляется
 * рядом с кнопкой, которая её вызвала.
 *
 * Тон целиком берётся из токенов статуса, поэтому текст читается в обеих темах.
 * Раньше такие плашки собирали границу конкатенацией — `${color}40` — и после
 * перевода палитры на переменные строка `var(--error)40` перестала быть валидным
 * цветом, из-за чего граница пропадала совсем.
 */
export default function Notice({ tone = 'info', children, onClose }) {
    const Icon = ICON[tone] || Info;

    return (
        <div className={`ui-notice ui-notice--${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
            <Icon
                size={14}
                className={tone === 'loading' ? 'ui-notice__icon animate-spin' : 'ui-notice__icon'}
                aria-hidden="true"
            />
            <span className="ui-notice__text">{children}</span>
            {onClose && (
                <button type="button" className="ui-notice__close" onClick={onClose} aria-label="Закрыть">
                    <X size={14} aria-hidden="true" />
                </button>
            )}
        </div>
    );
}

Notice.propTypes = {
    tone: PropTypes.oneOf(['success', 'error', 'warning', 'info', 'loading']),
    children: PropTypes.node,
    onClose: PropTypes.func,
};
