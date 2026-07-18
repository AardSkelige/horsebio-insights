import PropTypes from 'prop-types';
import { Link } from 'react-router-dom';
import { useState } from 'react';

const FeatureCard = ({ icon: Icon, title, description, link }) => {
    const [hovered, setHovered] = useState(false);

    return (
        <Link
            to={link}
            onMouseEnter={() => setHovered(true)}
            onMouseLeave={() => setHovered(false)}
            style={{
                backgroundColor: hovered ? 'var(--surface-cream-strong)' : 'var(--surface-card)',
                borderRadius: '12px',
                transform: hovered ? 'translateY(-2px)' : 'translateY(0)',
                boxShadow: hovered ? '0 6px 20px rgba(20,20,19,0.08)' : '0 0 0 rgba(20,20,19,0)',
                transition: 'background-color 150ms ease, transform 180ms ease-out, box-shadow 180ms ease-out',
                display: 'block',
                padding: '16px',
                textDecoration: 'none',
            }}
        >
            <div style={{ marginBottom: '10px' }}>
                <Icon style={{
                    width: '16px',
                    height: '16px',
                    color: hovered ? 'var(--primary)' : 'var(--muted)',
                    transform: hovered ? 'translateY(-3px) scale(1.1)' : 'translateY(0) scale(1)',
                    transition: 'color 150ms ease, transform 180ms ease-out',
                }} />
            </div>
            <h3 style={{
                fontSize: '13px',
                fontWeight: 500,
                color: 'var(--ink)',
                marginBottom: '3px',
                lineHeight: 1.3,
                fontFamily: 'var(--sans)',
            }}>
                {title}
            </h3>
            <p style={{
                fontSize: '12px',
                color: 'var(--muted)',
                lineHeight: 1.5,
                margin: 0,
                fontFamily: 'var(--sans)',
            }}>
                {description}
            </p>
        </Link>
    );
};

FeatureCard.propTypes = {
    icon: PropTypes.elementType.isRequired,
    title: PropTypes.string.isRequired,
    description: PropTypes.string.isRequired,
    link: PropTypes.string.isRequired,
};

export default FeatureCard;
