import PropTypes from 'prop-types';

const StatCard = ({ title, count, description }) => (
    <div style={{ background: 'var(--surface-card)', borderRadius: 12, padding: '16px 20px', border: '1px solid var(--hairline)' }}>
        <div style={{ fontFamily: 'var(--sans)', fontSize: 11, fontWeight: 500, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 8 }}>
            {title}
        </div>
        <div style={{ fontFamily: 'var(--serif)', fontSize: 28, fontWeight: 400, letterSpacing: '-0.02em', lineHeight: 1, color: 'var(--ink)', fontVariantNumeric: 'lining-nums', fontFeatureSettings: '"lnum" 1' }}>
            {count}
        </div>
        <div style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)', marginTop: 4 }}>
            {description}
        </div>
    </div>
);

StatCard.propTypes = {
    title: PropTypes.string.isRequired,
    count: PropTypes.number.isRequired,
    description: PropTypes.string.isRequired,
};

const MaterialStatistics = ({ stats }) => (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 12 }}>
        <StatCard title="Материалы для производства" count={stats['Материалы для производства']} description="позиций материалов" />
        <StatCard title="Тара"      count={stats['Тара']}      description="видов тары" />
        <StatCard title="Этикетки"  count={stats['Этикетки']}  description="наименований этикеток" />
    </div>
);

MaterialStatistics.propTypes = {
    stats: PropTypes.shape({
        'Материалы для производства': PropTypes.number.isRequired,
        'Тара': PropTypes.number.isRequired,
        'Этикетки': PropTypes.number.isRequired,
    }).isRequired,
};

export default MaterialStatistics;
