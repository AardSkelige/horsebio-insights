import PropTypes from 'prop-types';
import { StatCard, StatGrid } from '../ui';
import { percent } from '../../utils/formatters';

/**
 * Сводка инвентаризации: сколько позиций всего, сколько прошло и сколько нет.
 *
 * Раньше карточки были собраны вручную — значение сверху, подпись снизу,
 * шрифт 40px — и заметно отличались от сводок на остальных страницах.
 *
 * Две карточки кликабельны: ведут к соответствующему списку ниже.
 */
export default function InventoryStatsCards({ data, isMobile, onScrollTo }) {
    const { total, inventoried, not_inventoried: notInventoried } = data;
    const share = (n) => (total > 0 ? percent((n / total) * 100, 0) : null);

    const jumpProps = (target) => (onScrollTo ? {
        onClick: () => onScrollTo(target),
        style: { cursor: 'pointer' },
        title: 'Перейти к списку',
    } : {});

    return (
        <StatGrid min={isMobile ? 140 : 190}>
            <StatCard title="Позиций всего" value={total} />

            <StatCard
                title="Были в инвентаризации"
                value={inventoried}
                note={share(inventoried)}
                accent="var(--success-ink)"
                {...jumpProps('inventoried')}
            />

            <StatCard
                title="Не были"
                value={notInventoried}
                note={share(notInventoried)}
                accent={notInventoried > 0 ? 'var(--error-ink)' : undefined}
                {...jumpProps('not-inventoried')}
            />
        </StatGrid>
    );
}

InventoryStatsCards.propTypes = {
    data: PropTypes.shape({
        total: PropTypes.number,
        inventoried: PropTypes.number,
        not_inventoried: PropTypes.number,
    }).isRequired,
    isMobile: PropTypes.bool,
    onScrollTo: PropTypes.func,
};
