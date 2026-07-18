import PropTypes from 'prop-types';
import AnimatedNumber from './motion/AnimatedNumber';

const StatCard = ({ title, value, size = 28, format }) => (
    <div style={{ background: 'var(--surface-card)', borderRadius: 12, padding: '16px 20px', border: '1px solid var(--hairline)', minWidth: 0 }}>
        <div style={{ fontFamily: 'var(--sans)', fontSize: 11, fontWeight: 500, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 8 }}>
            {title}
        </div>
        <div style={{ fontFamily: 'var(--serif)', fontSize: size, fontWeight: 400, letterSpacing: '-0.02em', lineHeight: 1.15, color: 'var(--ink)', fontVariantNumeric: 'lining-nums', fontFeatureSettings: '"lnum" 1', overflowWrap: 'break-word' }}>
            {typeof value === 'number'
                ? <AnimatedNumber value={value} format={format || String} />
                : value}
        </div>
    </div>
);
StatCard.propTypes = {
    title: PropTypes.string.isRequired,
    value: PropTypes.oneOfType([PropTypes.string, PropTypes.number]).isRequired,
    size: PropTypes.number,
    format: PropTypes.func,
};

export default StatCard;
