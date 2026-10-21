import PropTypes from 'prop-types';
import { Badge, Skeleton } from '../ui';
import { FadeRise } from '../ui/motion';
import Breakdown from './Breakdown';
import { STATUS, days, qty } from './format';

export default function PlanCards({ rows, months, loading, open, onOpen, onToggleGreen }) {
    if (loading) {
        return [...Array(5)].map((_, i) => (
            <div key={i} className="plan-card"><Skeleton width="40%" height={10} /><Skeleton width="85%" height={14} /></div>
        ));
    }
    return rows.map((row) => (
        <div key={row.article} className="plan-card">
            <button type="button" className="plan-card__head" onClick={() => onOpen(row.article)}>
                <span className="plan-card__top">
                    <span className="plan-code">{row.article}</span>
                    <Badge tone={STATUS[row.status].tone}>{STATUS[row.status].label}</Badge>
                </span>
                <span className="plan-card__name">{row.green && <span className="plan-green" />}{row.name}</span>
                <span className="plan-card__line"><span>Обычно в месяц</span><b>{qty(row.usual)}</b></span>
                <span className="plan-card__line"><span>Можно взять со склада</span><b className={row.available ? '' : 'is-zero'}>{row.available ? qty(row.available) : '0'}</b></span>
                <span className="plan-card__line"><span>Склада хватит на</span><b className={row.status === 'urgent' ? 'is-zero' : ''}>{days(row.days)}</b></span>
                <span className="plan-card__line"><span>В производстве</span><b>{qty(row.in_production)}</b></span>
                <span className="plan-card__line plan-card__total"><span>Произвести</span><b>{qty(row.produce)} шт</b></span>
            </button>
            {open === row.article && (
                <FadeRise><Breakdown row={row} months={months} onToggleGreen={onToggleGreen} /></FadeRise>
            )}
        </div>
    ));
}

PlanCards.propTypes = {
    rows: PropTypes.array.isRequired,
    months: PropTypes.arrayOf(PropTypes.string).isRequired,
    loading: PropTypes.bool,
    open: PropTypes.string,
    onOpen: PropTypes.func.isRequired,
    onToggleGreen: PropTypes.func.isRequired,
};
