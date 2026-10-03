import { useState } from 'react';
import PropTypes from 'prop-types';
import { ExternalLink, EyeOff, Package } from 'lucide-react';
import { Button } from '../ui';
import Tooltip from '../ui/Tooltip';
import { formatDate } from '../../utils/formatters';
import { discountedApi } from '../../api/discountedApi';

const money = (value) => `${Math.round(value).toLocaleString('ru-RU')} ₽`;

function term(position) {
    if (position.state === 'no_date') return { text: 'срок не указан', hot: false };
    if (position.days_left < 0) return { text: `просрочен на ${-position.days_left} дн`, hot: true };
    if (position.days_left === 0) return { text: 'истекает сегодня', hot: true };
    return { text: `осталось ${position.days_left} дн`, hot: false };
}

// Откуда взялась цифра и что из неё следует — по наведению: на карточке места
// хватает только на сами значения.
function termHint(position, months) {
    if (position.state === 'no_date') return '«Годен до» в карточке МойСклад не заполнено — без даты не посчитать, когда снимать';
    const until = `Годен до ${formatDate(position.expires)}`;
    if (position.state === 'ok') return `${until}. Продаём, пока до конца срока больше ${months} мес`;
    if (position.state === 'expired') return `${until}. Срок вышел — снимаем с продажи и списываем`;
    return `${until}. До конца срока меньше ${months} мес — по регламенту снимаем с продажи и списываем`;
}

const Hint = ({ content, children }) => (
    <Tooltip content={content} className="uc-hint">{children}</Tooltip>
);
Hint.propTypes = { content: PropTypes.node.isRequired, children: PropTypes.node.isRequired };

/**
 * Уценённая позиция на складе.
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
 * Строка про Ozon появляется только у позиций, заведённых на площадке: там продаётся
 * часть уценки, и её отсутствие — не проблема, о которой надо сообщать. Остаток туда
 * едет из МойСклад сам (каждые 15 минут), поэтому расхождению взяться неоткуда —
 * строка показывает цену площадки, которая с ценой сайта не совпадает намеренно.
 *
 * «Снять с продажи» уходит обменом на сайт, а не в МойСклад: остаток и срок
 * остаются как были, меняется только доступность карточки покупателю. Поэтому
 * после успешного снятия карточка не исчезает — она просто перестаёт предлагать
 * это действие, а сама позиция остаётся на складе до списания.
 */
export default function DiscountedCard({ position, delistMonths, discountRate, onDelisted }) {
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
                <Hint content={termHint(position, delistMonths)}>
                    <span className={`term${hot ? ' hot' : ''}`}>{text}</span>
                </Hint>
                <Hint content="Остаток уценённой карточки в МойСклад">
                    <span className="qty">{position.quantity} шт</span>
                </Hint>
            </div>

            <div className="row">
                <Hint content={`Цена уценки — ${Math.round((1 - discountRate) * 100)} % от РРЦ сайта. Зачёркнута РРЦ`}>
                    <span className="price">
                        {money(position.price)}
                        {position.price_full > position.price && (
                            <span className="was">{money(position.price_full)}</span>
                        )}
                    </span>
                </Hint>
                <Hint content="Весь остаток по цене уценки — столько выручим, если продадим всё">
                    <span className="qty">{money(position.sum)}</span>
                </Hint>
            </div>

            {position.published !== null && (
                <Hint content={position.published
                    ? 'Цена и остаток, которые сейчас видит покупатель на horse-bio.ru'
                    : 'Покупатели карточку не видят: её не загружали файлом или она скрыта в админке'}>
                    <span className={`uc-site${position.published ? ' live' : ''}`}>
                        <span className="dot" />
                        {position.published
                            ? `На сайте: ${money(position.site_price)}, ${position.site_quantity} шт`
                            : 'Нет на витрине'}
                    </span>
                </Hint>
            )}

            {position.ozon_url && (
                <Hint content="Цена на Ozon отличается от сайта намеренно. Остаток подтягивается из МойСклад каждые 15 минут">
                    <span className="uc-site live">
                        <span className="dot" />
                        {position.ozon_price
                            ? `На Ozon: ${money(position.ozon_price)}, ${position.ozon_quantity} шт`
                            : 'На Ozon'}
                    </span>
                </Hint>
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
                {position.ozon_url && (
                    <Button as="a" variant="ghost" size="sm" icon={ExternalLink}
                        href={position.ozon_url} target="_blank" rel="noreferrer">
                        Ozon
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
        expires: PropTypes.string,
        quantity: PropTypes.number,
        price: PropTypes.number,
        price_full: PropTypes.number,
        sum: PropTypes.number,
        ms_url: PropTypes.string,
        site_url: PropTypes.string,
        published: PropTypes.bool,
        site_price: PropTypes.number,
        site_quantity: PropTypes.number,
        ozon_url: PropTypes.string,
        ozon_price: PropTypes.number,
        ozon_quantity: PropTypes.number,
    }).isRequired,
    delistMonths: PropTypes.number.isRequired,
    discountRate: PropTypes.number.isRequired,
    onDelisted: PropTypes.func,
};
