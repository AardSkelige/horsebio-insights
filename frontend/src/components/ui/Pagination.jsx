import PropTypes from 'prop-types';

/**
 * Номера страниц со свёрткой: первая, последняя и по две вокруг текущей,
 * между разрывами — многоточие.
 *
 * Ничего не рендерит, если всё помещается на одну страницу.
 */
export default function Pagination({ pagination, onPageChange }) {
    const { current, pageSize, total } = pagination;
    const totalPages = Math.ceil((total || 0) / pageSize) || 1;

    // `total` приходит из ответа и на первом рендере может быть не задан:
    // сравнение с undefined даёт false, и панель показала бы «undefined записей»
    if (!total || total <= pageSize) return null;

    const pages = Array.from({ length: totalPages }, (_, i) => i + 1)
        .filter((p) => p === 1 || p === totalPages || Math.abs(p - current) <= 2)
        .reduce((acc, p, i, arr) => {
            if (i > 0 && p - arr[i - 1] > 1) acc.push('…');
            acc.push(p);
            return acc;
        }, []);

    return (
        <nav className="ui-pagination" aria-label="Страницы">
            <span className="ui-pagination__summary">
                {total} записей · стр. {current} из {totalPages}
            </span>
            <div className="ui-pagination__pages">
                {pages.map((p, i) => p === '…' ? (
                    <span key={`gap-${i}`} className="ui-pagination__gap">…</span>
                ) : (
                    <button
                        key={p}
                        type="button"
                        className={`ui-pagination__page${p === current ? ' is-current' : ''}`}
                        onClick={() => onPageChange(p)}
                        aria-current={p === current ? 'page' : undefined}
                    >
                        {p}
                    </button>
                ))}
            </div>
        </nav>
    );
}

Pagination.propTypes = {
    pagination: PropTypes.shape({
        current: PropTypes.number.isRequired,
        pageSize: PropTypes.number.isRequired,
        total: PropTypes.number,
    }).isRequired,
    onPageChange: PropTypes.func.isRequired,
};
