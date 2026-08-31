import { useState } from 'react';
import PropTypes from 'prop-types';
import { ExternalLink, EyeOff, Package } from 'lucide-react';
import { Button } from '../ui';
import { discountedApi } from '../../api/discountedApi';

const money = (value) => `${Math.round(value).toLocaleString('ru-RU')} ₽`;

function term(position) {
    if (position.state === 'no_date') return { text: 'срок не указан', hot: false };
    if (position.days_left < 0) return { text: `просрочен на ${-position.days_left} дн`, hot: true };
    if (position.days_left === 0) return { text: 'истекает сегодня', hot: true };
    return { text: `осталось ${position.days_left} дн`, hot: false };
}

/**
 * Позиция на складе «Уценка».
 *
 * Кнопки «отправить на сайт» здесь нет намеренно: обмен упёрся в демо-лимит и
 * применяет изменения через раз, поэтому карточки заводятся файлом («Файл для
 * сайта» в шапке). Код публикации остался в site_exchange.publish — вернуть
 * кнопку можно будет сразу после оплаты полной версии обмена.
 *
 * «Нет на витрине» означает, что покупатель карточку не видит: её либо ещё не
 * отправляли, либо она скрыта. Это читается из фида сайта, а не из наших записей,
 * поэтому показывает настоящее положение дел, а не то, что мы когда-то отправили.
 *
 * «Снять с продажи» уходит обменом на сайт, а не в МойСклад: остаток и срок
 * остаются как были, меняется только доступность карточки покупателю. Поэтому
 * после успешного снятия карточка не исчезает — она просто перестаёт предлагать
 * это действие, а сама позиция остаётся на складе до списания.
 */
export default function DiscountedCard({ position, onDelisted }) {
    const [busy, setBusy] = useState(false);
    const [done, setDone] = useState(false);
    const [error, setError] = useState(null);

    const { text, hot } = term(position);
    const canDelist = position.state === 'expired' || position.state === 'delist';

    const handleDelist = async () => {
        setBusy(true);
        setError(null);
        try {
            await discountedApi.delist(position.id);
            setDone(true);
            onDelisted?.(position.id);
        } catch (e) {
            // Молчаливый провал опаснее ошибки: человек решит, что товар снят,
            // а он останется в продаже. Поэтому текст показываем прямо на карточке.
            setError(e?.message || 'Сайт не принял обмен');
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className={`uc-card ${position.state}`}>
            <div className="nm">{position.name}</div>
            <div className="art">{position.article}</div>

            <div className="row">
                <span className={`term${hot ? ' hot' : ''}`}>{text}</span>
                <span className="qty">{position.quantity} шт</span>
            </div>

            <div className="row">
                <span className="price">
                    {money(position.price)}
                    {position.price_full > position.price && (
                        <span className="was">{money(position.price_full)}</span>
                    )}
                </span>
                <span className="qty">{money(position.sum)}</span>
            </div>

            {position.published !== null && (
                <div className={`uc-site${position.published ? ' live' : ''}`}>
                    <span className="dot" />
                    {position.published
                        ? `На сайте: ${money(position.site_price)}, ${position.site_quantity} шт`
                        : 'Нет на витрине'}
                </div>
            )}

            <div className="uc-actions">
                {canDelist && (
                    <Button
                        variant="primary"
                        size="sm"
                        icon={EyeOff}
                        loading={busy}
                        disabled={done}
                        onClick={handleDelist}
                    >
                        {done ? 'Снят с продажи' : busy ? 'Снимаю…' : 'Снять с продажи'}
                    </Button>
                )}
                {position.ms_url && (
                    <Button as="a" variant="ghost" size="sm" icon={Package}
                        href={position.ms_url} target="_blank" rel="noreferrer">
                        МойСклад
                    </Button>
                )}
                {position.site_url && (
                    <Button as="a" variant="ghost" size="sm" icon={ExternalLink}
                        href={position.site_url} target="_blank" rel="noreferrer">
                        Сайт
                    </Button>
                )}
            </div>

            {error && <div className="uc-error" role="alert">{error}</div>}
        </div>
    );
}

DiscountedCard.propTypes = {
    position: PropTypes.shape({
        id: PropTypes.string.isRequired,
        article: PropTypes.string,
        name: PropTypes.string,
        state: PropTypes.string.isRequired,
        days_left: PropTypes.number,
        quantity: PropTypes.number,
        price: PropTypes.number,
        price_full: PropTypes.number,
        sum: PropTypes.number,
        ms_url: PropTypes.string,
        site_url: PropTypes.string,
        published: PropTypes.bool,
        site_price: PropTypes.number,
        site_quantity: PropTypes.number,
    }).isRequired,
    onDelisted: PropTypes.func,
};
