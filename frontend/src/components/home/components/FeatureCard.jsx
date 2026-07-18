import PropTypes from 'prop-types';
import { Link } from 'react-router-dom';
import { useState } from 'react';

const FeatureCard = ({ icon: Icon, title, description, link, compact = false }) => {
    const [hovered, setHovered] = useState(false);

    return (
        <Link
            to={link}
            onMouseEnter={() => setHovered(true)}
            onMouseLeave={() => setHovered(false)}
            title={compact ? `${title}: ${description}` : undefined}
            style={{
                backgroundColor: hovered ? 'var(--surface-cream-strong)' : 'var(--surface-card)',
                borderRadius: '12px',
                transform: hovered ? 'translateY(-2px)' : 'translateY(0)',
                boxShadow: hovered ? '0 6px 20px rgba(20,20,19,0.08)' : '0 0 0 rgba(20,20,19,0)',
                transition: 'background-color 150ms ease, transform 180ms ease-out, box-shadow 180ms ease-out',
                display: compact ? 'grid' : 'block',
                gridTemplateColumns: compact ? '28px minmax(0, 1fr)' : undefined,
                alignItems: compact ? 'center' : undefined,
                columnGap: compact ? '10px' : undefined,
                minHeight: compact ? '56px' : undefined,
                padding: compact ? '7px 12px' : '16px',
                textDecoration: 'none',
            }}
        >
            <div style={{
                width: compact ? '28px' : undefined,
                height: compact ? '28px' : undefined,
                borderRadius: compact ? '8px' : undefined,
                backgroundColor: compact ? 'var(--canvas)' : undefined,
                display: compact ? 'flex' : undefined,
                alignItems: compact ? 'center' : undefined,
                justifyContent: compact ? 'center' : undefined,
                marginBottom: compact ? 0 : '10px',
            }}>
                <Icon style={{
                    width: '16px',
                    height: '16px',
                    color: hovered ? 'var(--primary)' : 'var(--muted)',
                    transform: hovered ? 'translateY(-3px) scale(1.1)' : 'translateY(0) scale(1)',
                    transition: 'color 150ms ease, transform 180ms ease-out',
                }} />
            </div>
            <div style={{ minWidth: 0 }}>
                <h3 style={{
                    fontSize: '13px',
                    fontWeight: 500,
                    color: 'var(--ink)',
                    marginBottom: '3px',
                    lineHeight: 1.3,
                    fontFamily: 'var(--sans)',
                    whiteSpace: compact ? 'nowrap' : undefined,
                    overflow: compact ? 'hidden' : undefined,
                    textOverflow: compact ? 'ellipsis' : undefined,
                }}>
                    {title}
                </h3>
                <p style={{
                    fontSize: compact ? '11px' : '12px',
                    color: 'var(--muted)',
                    lineHeight: compact ? 1.25 : 1.5,
                    margin: 0,
                    fontFamily: 'var(--sans)',
                    whiteSpace: compact ? 'nowrap' : undefined,
                    overflow: compact ? 'hidden' : undefined,
                    textOverflow: compact ? 'ellipsis' : undefined,
                }}>
                    {description}
                </p>
            </div>
        </Link>
    );
};

FeatureCard.propTypes = {
    icon: PropTypes.elementType.isRequired,
    title: PropTypes.string.isRequired,
    description: PropTypes.string.isRequired,
    link: PropTypes.string.isRequired,
    compact: PropTypes.bool,
};

export default FeatureCard;
