import PropTypes from 'prop-types';
import { useState } from 'react';
import { m } from 'motion/react';
import { formatNumber } from '../../../utils/formatters';
import { AnimatedNumber, Stagger, StaggerItem } from '../../ui/motion';

const serif = { fontFamily: 'var(--serif)' };
const mono = { fontFamily: 'var(--mono)' };

const card = {
    backgroundColor: 'var(--surface-dark)',
    borderRadius: '12px',
    padding: '20px',
    position: 'relative',
};

const createMoyskladLink = (type, externalId) => {
    if (!externalId) return null;
    const docType = type === 'shipment' ? 'demand' : 'supply';
    return `https://online.moysklad.ru/app/#${docType}/edit?id=${externalId}`;
};

const Tooltip = ({ text }) => {
    const [visible, setVisible] = useState(false);
    return (
        <span style={{ position: 'absolute', top: '14px', right: '14px' }}>
            <span
                onMouseEnter={() => setVisible(true)}
                onMouseLeave={() => setVisible(false)}
                style={{
                    width: '16px', height: '16px',
                    borderRadius: '50%',
                    border: '1px solid var(--muted-soft)',
                    color: 'var(--muted-soft)',
                    fontSize: '9px',
                    fontFamily: 'var(--sans)',
                    fontWeight: 600,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    cursor: 'default',
                    userSelect: 'none',
                }}
            >
                ?
            </span>
            {visible && (
                <m.span
                    initial={{ opacity: 0, y: 4, scale: 0.97 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    transition={{ type: 'spring', stiffness: 400, damping: 28 }}
                    style={{
                    position: 'absolute',
                    top: 'calc(100% + 6px)',
                    right: 0,
                    backgroundColor: 'var(--canvas)',
                    color: 'var(--ink)',
                    fontSize: '12px',
                    fontFamily: 'var(--sans)',
                    lineHeight: '1.5',
                    padding: '8px 10px',
                    borderRadius: '8px',
                    boxShadow: '0 4px 16px rgba(20,20,19,0.12)',
                    border: '1px solid var(--hairline)',
                    whiteSpace: 'normal',
                    width: '200px',
                    zIndex: 10,
                    pointerEvents: 'none',
                }}>
                    {text}
                </m.span>
            )}
        </span>
    );
};
Tooltip.propTypes = { text: PropTypes.string.isRequired };

const StatisticsCards = ({ stats }) => {
    const months = stats.last_3_months || [];

    const statCards = [
        {
            title: 'Отгрузки',
            tooltip: 'Общее количество отгрузок товаров покупателям.',
            count: stats.shipments_count,
            monthCount: stats.shipments_current_month || 0,
            monthKey: 'shipments',
        },
        {
            title: 'Приёмки',
            tooltip: 'Общее количество приёмок материалов от поставщиков.',
            count: stats.supplies_count || 0,
            monthCount: stats.supplies_current_month || 0,
            monthKey: 'supplies',
        },
    ];

    const recentCards = [
        {
            title: 'Последние отгрузки',
            tooltip: 'Последние 10 отгрузок в базе данных.',
            items: stats.last_10_shipments || stats.last_6_shipments || stats.last_3_shipments || [],
            linkType: 'shipment',
        },
        {
            title: 'Последние приёмки',
            tooltip: 'Последние 10 приёмок в базе данных.',
            items: stats.last_10_supplies || stats.last_6_supplies || stats.last_3_supplies || [],
            linkType: 'supply',
        },
    ];

    return (
        <Stagger className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">

            {/* Stat cards */}
            {statCards.map((c) => (
                <StaggerItem key={c.title} style={card}>
                    <div style={{
                        ...serif,
                        fontSize: '40px',
                        fontWeight: 400,
                        letterSpacing: '-0.025em',
                        lineHeight: 1,
                        color: 'var(--on-dark)',
                        marginBottom: '6px',
                        fontVariantNumeric: 'lining-nums',
                        fontFeatureSettings: '"lnum" 1',
                    }}>
                        <AnimatedNumber value={c.count} format={formatNumber} />
                    </div>
                    <Tooltip text={c.tooltip} />
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '16px' }}>
                        <span style={{ fontSize: '11px', letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--on-dark-soft)' }}>
                            {c.title}
                        </span>
                        <span style={{ fontSize: '11px', color: 'var(--muted-soft)' }}>
                            · {formatNumber(c.monthCount)} за месяц
                        </span>
                    </div>

                    {months.length > 0 && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                            {months.map((m) => (
                                <div key={`${m.month}-${m.year}`} style={{ display: 'flex', justifyContent: 'space-between' }}>
                                    <span style={{ ...mono, fontSize: '12px', color: 'var(--muted-soft)' }}>
                                        {m.month} {m.year}
                                    </span>
                                    <span style={{ ...mono, fontSize: '12px', color: 'var(--on-dark-soft)' }}>
                                        {formatNumber(m[c.monthKey])}
                                    </span>
                                </div>
                            ))}
                        </div>
                    )}
                </StaggerItem>
            ))}

            {/* Recent docs cards */}
            {recentCards.map((c) => (
                <StaggerItem key={c.title} style={card}>
                    <Tooltip text={c.tooltip} />
                    <div style={{ marginBottom: '12px' }}>
                        <span style={{ fontSize: '11px', letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--on-dark-soft)' }}>
                            {c.title}
                        </span>
                    </div>

                    {c.items.length > 0 ? (
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 12px' }}>
                            {c.items.slice(0, 10).map((item, i) => {
                                const url = createMoyskladLink(c.linkType, item.external_id);
                                const text = `№${item.number} · ${new Date(item.date).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })}`;
                                const style = { ...mono, fontSize: '12px', color: 'var(--muted-soft)', textDecoration: 'none', transition: 'color 150ms ease' };
                                return url ? (
                                    <a key={i} href={url} target="_blank" rel="noopener noreferrer" style={style}
                                        onMouseEnter={e => (e.target.style.color = 'var(--on-dark)')}
                                        onMouseLeave={e => (e.target.style.color = 'var(--muted-soft)')}>
                                        {text}
                                    </a>
                                ) : (
                                    <span key={i} style={style}>{text}</span>
                                );
                            })}
                        </div>
                    ) : (
                        <p style={{ fontSize: '12px', color: 'var(--muted-soft)' }}>Нет данных</p>
                    )}
                </StaggerItem>
            ))}
        </Stagger>
    );
};

StatisticsCards.propTypes = {
    stats: PropTypes.shape({
        shipments_count: PropTypes.number.isRequired,
        shipments_current_month: PropTypes.number,
        supplies_count: PropTypes.number,
        supplies_current_month: PropTypes.number,
        last_3_months: PropTypes.arrayOf(PropTypes.shape({
            month: PropTypes.string,
            year: PropTypes.number,
            shipments: PropTypes.number,
            supplies: PropTypes.number,
        })),
        last_3_shipments: PropTypes.array,
        last_6_shipments: PropTypes.array,
        last_10_shipments: PropTypes.array,
        last_3_supplies: PropTypes.array,
        last_6_supplies: PropTypes.array,
        last_10_supplies: PropTypes.array,
    })
};

export default StatisticsCards;
