import PropTypes from 'prop-types';

const numStyle = {
    fontFamily: 'var(--serif)',
    fontWeight: 400,
    letterSpacing: '-0.025em',
    lineHeight: 1,
    color: 'var(--on-dark)',
    marginBottom: 6,
    fontVariantNumeric: 'lining-nums',
    fontFeatureSettings: '"lnum" 1',
};

const labelStyle = {
    fontFamily: 'var(--sans)',
    fontSize: 11,
    letterSpacing: '0.1em',
    textTransform: 'uppercase',
    color: 'var(--on-dark-soft)',
};

const pctStyle = {
    fontFamily: 'var(--sans)',
    fontSize: 11,
    marginLeft: 6,
    color: 'var(--muted-soft)',
};

export default function InventoryStatsCards({ data, isMobile, onScrollTo }) {
    const { total, inventoried, not_inventoried } = data;
    const invPct = total > 0 ? Math.round((inventoried / total) * 100) : 0;
    const notPct = total > 0 ? Math.round((not_inventoried / total) * 100) : 0;

    const cardBase = {
        backgroundColor: 'var(--surface-dark)',
        borderRadius: 12,
        padding: isMobile ? '14px 16px' : '20px',
        flex: 1,
        minWidth: 0,
    };

    const clickable = onScrollTo ? {
        cursor: 'pointer',
        transition: 'opacity 0.15s',
    } : {};

    const fontSize = isMobile ? 32 : 40;

    return (
        <div style={{ display: 'flex', flexDirection: isMobile ? 'column' : 'row', gap: 12, marginBottom: 28 }}>
            <div style={{ ...cardBase }}>
                <div style={{ ...numStyle, fontSize }}>{total}</div>
                <div style={{ display: 'flex', alignItems: 'center' }}>
                    <span style={labelStyle}>Позиций всего</span>
                </div>
            </div>

            <div
                style={{ ...cardBase, ...clickable }}
                onClick={() => onScrollTo?.('inventoried')}
                title={onScrollTo ? 'Перейти к списку' : undefined}
            >
                <div style={{ ...numStyle, fontSize, color: 'var(--success)' }}>{inventoried}</div>
                <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 4 }}>
                    <span style={onScrollTo ? { ...labelStyle, textDecoration: 'underline', textDecorationColor: 'rgba(250,249,245,0.3)', textUnderlineOffset: 3 } : labelStyle}>
                        Были в инвентаризации
                    </span>
                    <span style={pctStyle}>· {invPct}%</span>
                </div>
            </div>

            <div
                style={{ ...cardBase, ...clickable }}
                onClick={() => onScrollTo?.('not-inventoried')}
                title={onScrollTo ? 'Перейти к списку' : undefined}
            >
                <div style={{ ...numStyle, fontSize, color: not_inventoried > 0 ? 'var(--error)' : 'var(--on-dark)' }}>
                    {not_inventoried}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 4 }}>
                    <span style={onScrollTo ? { ...labelStyle, textDecoration: 'underline', textDecorationColor: 'rgba(250,249,245,0.3)', textUnderlineOffset: 3 } : labelStyle}>
                        Не были
                    </span>
                    <span style={pctStyle}>· {notPct}%</span>
                </div>
            </div>
        </div>
    );
}

InventoryStatsCards.propTypes = {
    data: PropTypes.shape({
        total: PropTypes.number,
        inventoried: PropTypes.number,
        not_inventoried: PropTypes.number,
    }).isRequired,
    isMobile: PropTypes.bool,
};
