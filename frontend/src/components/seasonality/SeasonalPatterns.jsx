import { useState } from 'react';
import PropTypes from 'prop-types';
import { TrendingUp, TrendingDown, AlertTriangle } from 'lucide-react';

const MONTHS = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'];

const TYPE_STYLE = {
    STABLE:     { bg: 'var(--info-bg)',  color: 'var(--info-ink)', border: 'var(--info-border)'  },
    MULTI_PEAK: { bg: 'var(--cat-violet-bg)',  color: 'var(--cat-violet-ink)', border: 'var(--cat-violet-border)'  },
    SUMMER:     { bg: 'var(--success-bg)',  color: 'var(--success-ink)', border: 'var(--success-border)'  },
    WINTER:     { bg: 'var(--cat-teal-bg)',  color: 'var(--cat-teal-ink)', border: 'var(--cat-teal-border)'  },
};
const DEFAULT_TYPE = { bg: 'var(--surface-card)', color: 'var(--muted)', border: 'var(--hairline)' };

const FactorCell = ({ value }) => {
    if (!value || typeof value !== 'number') return <span style={{ color: 'var(--muted)' }}>—</span>;
    const isHigh = value >= 1.2;
    const isLow  = value <= 0.8;
    const color  = isHigh ? 'var(--success-ink)' : isLow ? 'var(--error-ink)' : 'var(--body)';
    const bg     = isHigh ? 'var(--success-bg)' : isLow ? 'var(--error-bg)' : 'transparent';
    return (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '3px', padding: '2px 6px', borderRadius: '6px', backgroundColor: bg, color, fontFamily: 'var(--mono)', fontSize: '11px', fontWeight: 600 }}>
            {isHigh && <TrendingUp style={{ width: 10, height: 10 }} />}
            {isLow  && <TrendingDown style={{ width: 10, height: 10 }} />}
            {value.toFixed(2)}
        </span>
    );
};

const PAGE_SIZE = 10;

const thBase = { fontFamily: 'var(--sans)', fontSize: '11px', fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--muted)', padding: '8px 10px', textAlign: 'center', borderBottom: '1px solid var(--hairline)', whiteSpace: 'nowrap', backgroundColor: 'var(--canvas)' };
const tdBase = { fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--body)', padding: '10px 10px', borderBottom: '1px solid var(--hairline-soft)', textAlign: 'center', verticalAlign: 'middle' };

export const SeasonalPatterns = ({ data, onProductSelect }) => {
    const [page, setPage] = useState(1);
    const products = data?.products || [];
    const totalPages = Math.max(1, Math.ceil(products.length / PAGE_SIZE));
    const paginated = products.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '1100px' }}>
                    <thead>
                        <tr>
                            <th style={{ ...thBase, textAlign: 'left', position: 'sticky', left: 0, backgroundColor: 'var(--canvas)', zIndex: 1, minWidth: '200px' }}>Продукт</th>
                            <th style={{ ...thBase, minWidth: '140px' }}>Тип сезонности</th>
                            {MONTHS.map(m => <th key={m} style={{ ...thBase, minWidth: '56px' }}>{m}</th>)}
                        </tr>
                    </thead>
                    <tbody>
                        {paginated.map(p => {
                            const ts = TYPE_STYLE[p.seasonality_type] || DEFAULT_TYPE;
                            const highVol = p.stability_metrics?.coefficient_std > 0.5;
                            return (
                                <tr
                                    key={p.id}
                                    onClick={() => onProductSelect?.(p)}
                                    style={{ cursor: 'pointer' }}
                                    onMouseEnter={e => e.currentTarget.style.backgroundColor = 'var(--surface-soft)'}
                                    onMouseLeave={e => e.currentTarget.style.backgroundColor = 'transparent'}
                                >
                                    <td style={{ ...tdBase, textAlign: 'left', position: 'sticky', left: 0, backgroundColor: 'inherit' }}>
                                        <div style={{ fontWeight: 500, color: 'var(--ink)' }}>{p.name}</div>
                                        {p.article && <div style={{ fontSize: '11px', color: 'var(--muted)' }}>{p.article}</div>}
                                    </td>
                                    <td style={tdBase}>
                                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '5px' }}>
                                            <span style={{ display: 'inline-block', padding: '2px 8px', borderRadius: '20px', fontSize: '11px', fontWeight: 600, backgroundColor: ts.bg, color: ts.color, border: `1px solid ${ts.border}`, whiteSpace: 'nowrap' }}>
                                                {p.seasonality_name}
                                            </span>
                                            {highVol && <AlertTriangle style={{ width: 12, height: 12, color: 'var(--warning)', flexShrink: 0 }} title="Высокая волатильность" />}
                                        </div>
                                    </td>
                                    {MONTHS.map((_, i) => (
                                        <td key={i} style={tdBase}>
                                            <FactorCell value={p.seasonal_factors?.[i + 1]} />
                                        </td>
                                    ))}
                                </tr>
                            );
                        })}
                        {paginated.length === 0 && (
                            <tr><td colSpan={14} style={{ ...tdBase, padding: '32px', color: 'var(--muted)' }}>Нет данных</td></tr>
                        )}
                    </tbody>
                </table>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
                <span style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--muted)' }}>
                    Всего {products.length} продуктов · нажмите строку для детального анализа
                </span>
                {totalPages > 1 && (
                    <div style={{ display: 'flex', gap: '4px' }}>
                        {[...Array(totalPages)].map((_, i) => (
                            <button
                                key={i}
                                onClick={() => setPage(i + 1)}
                                style={{ fontFamily: 'var(--sans)', fontSize: '12px', padding: '4px 10px', borderRadius: '6px', border: `1px solid ${page === i + 1 ? 'var(--primary)' : 'var(--hairline)'}`, backgroundColor: page === i + 1 ? 'var(--primary)' : 'var(--canvas)', color: page === i + 1 ? 'var(--on-primary)' : 'var(--body)', cursor: 'pointer' }}
                            >
                                {i + 1}
                            </button>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};

FactorCell.propTypes = { value: PropTypes.number };

SeasonalPatterns.propTypes = {
    data: PropTypes.shape({
        products: PropTypes.arrayOf(PropTypes.shape({
            id: PropTypes.number.isRequired,
            name: PropTypes.string.isRequired,
            article: PropTypes.string,
            seasonality_type: PropTypes.string.isRequired,
            seasonality_name: PropTypes.string.isRequired,
            seasonal_factors: PropTypes.object.isRequired,
            stability_metrics: PropTypes.shape({ coefficient_std: PropTypes.number.isRequired }).isRequired,
        })),
    }),
    onProductSelect: PropTypes.func,
};

export default SeasonalPatterns;
