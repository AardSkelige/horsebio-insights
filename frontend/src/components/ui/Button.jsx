import PropTypes from 'prop-types';
import { Loader2 } from 'lucide-react';

/**
 * Кнопка приложения.
 *
 * Варианты соответствуют реальным ролям в интерфейсе:
 * - `primary`   — главное действие формы или диалога;
 * - `secondary` — равнозначная альтернатива рядом с primary;
 * - `soft`      — залитое второстепенное действие без рамки («Экспорт», выбор периода);
 * - `ghost`     — обведённое второстепенное действие (ссылки на МойСклад, «Сбросить»);
 * - `link`      — текстовое действие акцентом («Обновить», «Детали»), самый частый случай;
 * - `quiet`     — текстовое действие без акцента («Выгрузить»);
 * - `subtle`    — мелкое действие внутри плотного списка (заливка + тон);
 * - `danger`    — удаление и снятие с продажи.
 *
 * `tone` уточняет цвет у `subtle`: акцентный для добавления, опасный для удаления.
 *
 * `as="a"` рендерит ссылку с тем же оформлением — внешние ссылки в интерфейсе
 * выглядят как кнопки и должны совпадать с ними пиксель в пиксель.
 *
 * `loadingLabel` подменяет подпись на время загрузки («Обновляем…»): обе подписи
 * лежат в одной ячейке грида, поэтому кнопка держит ширину по самой длинной и
 * не дёргает соседей в момент переключения.
 */
export default function Button({
    variant = 'secondary',
    tone,
    size = 'md',
    loading = false,
    loadingLabel = null,
    block = false,
    icon: Icon = null,
    as = 'button',
    className = '',
    children,
    disabled,
    ...rest
}) {
    const classes = [
        'ui-btn',
        `ui-btn--${variant}`,
        `ui-btn--${size}`,
        tone ? `is-${tone}` : '',
        block ? 'ui-btn--block' : '',
        className,
    ].filter(Boolean).join(' ');

    const iconSize = size === 'sm' ? 13 : 14;

    // Иконка загрузки подменяет собой обычную: так ширина кнопки не прыгает
    const leading = loading
        ? <Loader2 size={iconSize} className="ui-btn__spinner" aria-hidden="true" />
        : Icon ? <Icon size={iconSize} aria-hidden="true" /> : null;

    // Скрытая подпись помечена aria-hidden, поэтому скринридер читает ровно
    // одну — актуальную, а не обе сразу
    const label = loadingLabel == null ? children : (
        <span className="ui-btn__label">
            <span data-off={loading || undefined} aria-hidden={loading || undefined}>{children}</span>
            <span data-off={!loading || undefined} aria-hidden={!loading || undefined}>{loadingLabel}</span>
        </span>
    );

    if (as === 'a') {
        // У ссылки нет атрибута disabled: гасим её через aria и снятие href,
        // иначе «выключенная» ссылка выглядит выключенной, но остаётся кликабельной
        const off = disabled || loading;
        return (
            <a
                className={classes}
                aria-disabled={off || undefined}
                tabIndex={off ? -1 : undefined}
                {...rest}
                href={off ? undefined : rest.href}
            >
                {leading}
                {label}
            </a>
        );
    }

    return (
        <button
            type="button"
            className={classes}
            disabled={disabled || loading}
            {...rest}
        >
            {leading}
            {label}
        </button>
    );
}

Button.propTypes = {
    variant: PropTypes.oneOf(['primary', 'secondary', 'soft', 'subtle', 'ghost', 'link', 'quiet', 'danger']),
    tone: PropTypes.oneOf(['accent', 'danger']),
    size: PropTypes.oneOf(['sm', 'md']),
    loading: PropTypes.bool,
    loadingLabel: PropTypes.node,
    block: PropTypes.bool,
    icon: PropTypes.elementType,
    as: PropTypes.oneOf(['button', 'a']),
    className: PropTypes.string,
    children: PropTypes.node,
    disabled: PropTypes.bool,
};
