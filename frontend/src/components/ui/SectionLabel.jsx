import PropTypes from 'prop-types';

const SectionLabel = ({ children }) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
        <span style={{ fontFamily: 'var(--sans)', fontSize: 11, fontWeight: 500, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--muted)', whiteSpace: 'nowrap' }}>{children}</span>
        <div style={{ flex: 1, height: 1, background: 'var(--hairline)' }} />
    </div>
);
SectionLabel.propTypes = { children: PropTypes.node.isRequired };

export default SectionLabel;
