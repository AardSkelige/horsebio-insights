import PropTypes from 'prop-types';

/** Контейнер страницы: колонка максимум 1200px по центру с нижним отступом. */
export function Page({ className = '', children, ...rest }) {
    return (
        <div className={['ui-page', className].filter(Boolean).join(' ')} {...rest}>
            {children}
        </div>
    );
}

Page.propTypes = {
    className: PropTypes.string,
    children: PropTypes.node,
};

/** Ряд фильтров, поиска и переключателей над содержимым страницы. */
export function Toolbar({ className = '', children, ...rest }) {
    return (
        <div className={['ui-toolbar', className].filter(Boolean).join(' ')} {...rest}>
            {children}
        </div>
    );
}

Toolbar.propTypes = {
    className: PropTypes.string,
    children: PropTypes.node,
};
