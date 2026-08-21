import { useState } from 'react';
import PropTypes from 'prop-types';
import { ChevronRight } from 'lucide-react';

/**
 * Раскрывающаяся строка: заголовок с шевроном, содержимое под ним.
 *
 * Встречалась в девяти местах — в модалках отгрузок, в разборе поставщиков,
 * в рекомендациях по закупкам — и каждый раз собиралась заново из кнопки,
 * состояния и повёрнутой иконки.
 *
 * `summary` — то, что видно всегда; `aside` встаёт справа от него (сумма,
 * количество). Открытое состояние можно вести снаружи через `open` +
 * `onToggle`, иначе компонент держит его сам.
 */
export default function Disclosure({
    summary,
    aside,
    children,
    defaultOpen = false,
    open: controlledOpen,
    onToggle,
    divided = true,
}) {
    const [innerOpen, setInnerOpen] = useState(defaultOpen);
    const isControlled = controlledOpen !== undefined;
    const open = isControlled ? controlledOpen : innerOpen;

    const toggle = () => {
        if (!isControlled) setInnerOpen((v) => !v);
        onToggle?.(!open);
    };

    return (
        <div className={`ui-disclosure${divided ? ' is-divided' : ''}`}>
            <button
                type="button"
                className="ui-disclosure__head"
                onClick={toggle}
                aria-expanded={open}
            >
                <span className="ui-disclosure__summary">
                    <ChevronRight
                        size={13}
                        className={`ui-disclosure__chevron${open ? ' is-open' : ''}`}
                        aria-hidden="true"
                    />
                    {summary}
                </span>
                {aside && <span className="ui-disclosure__aside">{aside}</span>}
            </button>

            {open && <div className="ui-disclosure__body">{children}</div>}
        </div>
    );
}

Disclosure.propTypes = {
    summary: PropTypes.node.isRequired,
    aside: PropTypes.node,
    children: PropTypes.node,
    defaultOpen: PropTypes.bool,
    open: PropTypes.bool,
    onToggle: PropTypes.func,
    divided: PropTypes.bool,
};
