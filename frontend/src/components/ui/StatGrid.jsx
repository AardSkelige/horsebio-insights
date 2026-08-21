import PropTypes from 'prop-types';
import { Skeleton } from './Skeleton';

/**
 * Сетка карточек показателей: сама подбирает число колонок под ширину экрана.
 *
 * `min` — минимальная ширина карточки, по умолчанию 190px.
 *
 * Раскладка на `auto-fill`, а не `auto-fit`: пустые треки сохраняются, и три
 * карточки выглядят так же, как шесть, — не растягиваются на всю ширину.
 * Ровно этим отличались «Покупатели» от экрана ДДС.
 *
 * Увеличивайте `min` для карточек с длинным содержимым (списки, топы), а не
 * для показателей — у тех значение короткое.
 */
export default function StatGrid({
    min = 190,
    gap = 12,
    loading = false,
    count = 4,
    className = '',
    style,
    children,
    ...rest
}) {
    return (
        <div
            className={className || undefined}
            // Свой `style` подмешивается, а не заменяет сетку целиком:
            // иначе достаточно передать marginBottom, чтобы раскладка развалилась
            style={{
                display: 'grid',
                gridTemplateColumns: `repeat(auto-fill, minmax(min(${min}px, 100%), 1fr))`,
                gap,
                ...style,
            }}
            {...rest}
        >
            {/* Пока показатели не пришли, место под них занимают заглушки:
                иначе появление карточек сдвигает фильтры и таблицу вниз */}
            {loading
                ? Array.from({ length: count }, (_, i) => <Skeleton key={i} height={STAT_CARD_HEIGHT} />)
                : children}
        </div>
    );
}

/** Высота карточки показателя — заглушка должна занимать ровно её место. */
const STAT_CARD_HEIGHT = 76;

StatGrid.propTypes = {
    min: PropTypes.number,
    gap: PropTypes.number,
    loading: PropTypes.bool,
    count: PropTypes.number,
    className: PropTypes.string,
    style: PropTypes.object,
    children: PropTypes.node,
};
