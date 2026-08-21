import PropTypes from 'prop-types';
import { m } from 'motion/react';

/**
 * Переключатель одного значения из нескольких: период, вкладка, режим ввода.
 *
 * Встречался в шести местах — «Проверки», ДДС, калькулятор производства,
 * расчёт доставки, инвентаризация, управление данными — и везде собирался
 * заново, из-за чего активный сегмент выглядел по-разному.
 *
 * `pill` включает перетекающую подсветку активного сегмента; `layoutId` нужен
 * ей, чтобы анимация не путала переключатели, когда их на экране несколько.
 */
export default function Segmented({
    options,
    value,
    onChange,
    pill = true,
    layoutId = 'ui-segmented-pill',
    disabled = false,
    tone = 'panel',
    className = '',
    style,
}) {
    return (
        <div
            className={['ui-segmented', `ui-segmented--${tone}`, className].filter(Boolean).join(' ')}
            style={style}
            role="tablist"
        >
            {options.map((o) => {
                const val = typeof o === 'string' ? o : o.value;
                const label = typeof o === 'string' ? o : o.label;
                const active = val === value;

                return (
                    <button
                        key={val}
                        type="button"
                        role="tab"
                        aria-selected={active}
                        disabled={disabled}
                        className={`ui-segmented__item${active ? ' is-active' : ''}`}
                        onClick={() => onChange(val)}
                    >
                        {active && pill && (
                            <m.span
                                layoutId={layoutId}
                                transition={{ type: 'spring', stiffness: 500, damping: 40 }}
                                className="ui-segmented__pill"
                                aria-hidden="true"
                            />
                        )}
                        <span className="ui-segmented__label">{label}</span>
                    </button>
                );
            })}
        </div>
    );
}

Segmented.propTypes = {
    options: PropTypes.arrayOf(PropTypes.oneOfType([
        PropTypes.string,
        PropTypes.shape({ value: PropTypes.any, label: PropTypes.node }),
    ])).isRequired,
    value: PropTypes.any,
    onChange: PropTypes.func.isRequired,
    pill: PropTypes.bool,
    layoutId: PropTypes.string,
    disabled: PropTypes.bool,
    tone: PropTypes.oneOf(['panel', 'plain', 'dark']),
    className: PropTypes.string,
    style: PropTypes.object,
};
