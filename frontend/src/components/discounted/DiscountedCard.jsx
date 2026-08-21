import { useState } from 'react';
import PropTypes from 'prop-types';
import { ExternalLink, EyeOff, Package } from 'lucide-react';
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
 * «Снять с продажи» уходит обменом на сайт, а не в МойСклад: остаток и срок
 * остаются как были, меняется только доступность карточки покупателю. Поэтому
 * после успешного снятия карточка не исчезает — она просто перестаёт предлагать
 * это действие, а сама позиция остаётся на складе до списания.
 */
export default function DiscountedCard({ position, siteAdminUrl, onDelisted }) {
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

            <div className="uc-actions">
                {canDelist && (
                    <button
                        type="button"
                        className="uc-btn solid"
                        onClick={handleDelist}
                        disabled={busy || done}
                    >
                        <EyeOff size={13} aria-hidden="true" />
                        {done ? 'Снят с продажи' : busy ? 'Снимаю…' : 'Снять с продажи'}
                    </button>
                )}
                <a
                    className="uc-btn ghost"
                    href={position.ms_url}
                    target="_blank"
                    rel="noreferrer"
                >
                    <Package size={13} aria-hidden="true" />
                    МойСклад
                </a>
                <a
                    className="uc-btn ghost"
                    href={siteAdminUrl}
                    target="_blank"
                    rel="noreferrer"
                >
                    <ExternalLink size={13} aria-hidden="true" />
                    Админка
                </a>
            </div>

            {error && <div className="uc-error">{error}</div>}
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
    }).isRequired,
    siteAdminUrl: PropTypes.string,
    onDelisted: PropTypes.func,
};
