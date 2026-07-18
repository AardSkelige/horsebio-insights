import PropTypes from 'prop-types';

// Плашка-скелетон; использует глобальный класс .skeleton (shimmer из index.css)
export const Skeleton = ({ width = '100%', height = 14, style }) => (
    <div className="skeleton" style={{ width, height, borderRadius: 6, ...style }} />
);

Skeleton.propTypes = {
    width: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
    height: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
    style: PropTypes.object,
};

// Псевдослучайные ширины, стабильные между рендерами — чтобы скелетон
// выглядел как текст разной длины, а не как решётка
const widthFor = (row, col) => 45 + ((row * 7 + col * 13) % 45);

// Строки-скелетоны для таблиц на время загрузки данных
export const SkeletonRows = ({ cols, rows = 8 }) => (
    [...Array(rows)].map((_, r) => (
        <tr key={r}>
            {[...Array(cols)].map((_, c) => (
                <td key={c} style={{ padding: '12px 12px', borderBottom: '1px solid var(--hairline-soft)' }}>
                    <Skeleton width={`${widthFor(r, c)}%`} height={12} />
                </td>
            ))}
        </tr>
    ))
);

SkeletonRows.propTypes = {
    cols: PropTypes.number.isRequired,
    rows: PropTypes.number,
};
