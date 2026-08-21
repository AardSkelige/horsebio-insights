import PropTypes from 'prop-types';

/**
 * Плитка «подпись + значение» — мелкая единица показателя внутри карточки
 * или раскрытой строки таблицы. Не путать со `StatCard`: тот крупный,
 * с засечным начертанием, и живёт в сводке наверху страницы.
 */
export function Metric({ label, value }) {
    return (
        <div className="ui-metric">
            <div className="ui-metric__label">{label}</div>
            <div className="ui-metric__value">{value}</div>
        </div>
    );
}

Metric.propTypes = {
    label: PropTypes.node.isRequired,
    value: PropTypes.node,
};

/** Сетка плиток: сама подбирает число колонок под ширину. */
export function MetricGrid({ children, className = '', ...rest }) {
    return (
        <div className={['ui-metric-grid', className].filter(Boolean).join(' ')} {...rest}>
            {children}
        </div>
    );
}

MetricGrid.propTypes = {
    children: PropTypes.node,
    className: PropTypes.string,
};
