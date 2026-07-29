import PropTypes from 'prop-types';
import {
    Truck,
    Boxes,
    Weight,
    AlertTriangle,
    Package,
    Clock,
    BadgeCheck,
    Zap,
    Ruler,
    ChevronDown,
} from 'lucide-react';
import { FadeRise, Stagger, StaggerItem, AnimatedNumber } from '../ui/motion';

const CARRIER_LABELS = { pec: 'ПЭК', cdek: 'СДЭК' };

const money = (value) => (typeof value === 'number' ? value : null);

const minDays = (days) => {
    if (!days) return Infinity;
    const match = String(days).match(/\d+/);
    return match ? Number(match[0]) : Infinity;
};

const basePrice = (carrier) => (
    carrier && !carrier.error ? money(carrier.warehouse) ?? money(carrier.door) : null
);

const Price = ({ value }) => (
    value === null || value === undefined
        ? <span className="delivery-price-empty">Нет тарифа</span>
        : (
            <>
                <AnimatedNumber
                    value={value}
                    format={(number) => Math.round(number).toLocaleString('ru-RU')}
                /> ₽
            </>
        )
);

Price.propTypes = { value: PropTypes.number };

const CarrierCard = ({ id, data, cheapest, fastest }) => {
    const label = CARRIER_LABELS[id] || id;

    if (!data || data.error) {
        return (
            <article className="delivery-carrier delivery-carrier--error">
                <header>
                    <span><Truck aria-hidden="true" />{label}</span>
                </header>
                <p>{data?.error || 'Тарифы недоступны'}</p>
            </article>
        );
    }

    return (
        <article className={cheapest ? 'delivery-carrier is-cheapest' : 'delivery-carrier'}>
            <header>
                <span><Truck aria-hidden="true" />{label}</span>
                <div className="delivery-carrier__badges">
                    {cheapest && <span><BadgeCheck aria-hidden="true" />Выгоднее</span>}
                    {fastest && <span><Zap aria-hidden="true" />Быстрее</span>}
                </div>
            </header>

            <div className="delivery-carrier__primary">
                <small>До пункта / терминала</small>
                <strong><Price value={money(data.warehouse)} /></strong>
            </div>

            <div className="delivery-carrier__row">
                <span>До двери</span>
                <strong><Price value={money(data.door)} /></strong>
            </div>
            <div className="delivery-carrier__row">
                <span><Clock aria-hidden="true" />Срок</span>
                <strong>{data.days ? `${data.days} дн.` : 'Не указан'}</strong>
            </div>
        </article>
    );
};

CarrierCard.propTypes = {
    id: PropTypes.string.isRequired,
    data: PropTypes.object,
    cheapest: PropTypes.bool,
    fastest: PropTypes.bool,
};

const CargoStat = ({ icon: Icon, value, label }) => (
    <div className="delivery-cargo-stat">
        <Icon aria-hidden="true" />
        <span>
            <strong>{value}</strong>
            <small>{label}</small>
        </span>
    </div>
);

CargoStat.propTypes = {
    icon: PropTypes.elementType.isRequired,
    value: PropTypes.node.isRequired,
    label: PropTypes.string.isRequired,
};

const BlockingNotice = ({ title, text, items }) => (
    <FadeRise className="delivery-blocking-notice" role="alert">
        <div className="delivery-blocking-notice__title">
            <AlertTriangle aria-hidden="true" />
            <div>
                <h3>{title}</h3>
                <p>{text}</p>
            </div>
        </div>
        <ul>
            {items.map((item, index) => (
                <li key={`${item.name}-${index}`}>
                    <strong>{item.name}</strong>
                    {item.lacks?.length > 0 && <span>Не заполнено: {item.lacks.join(', ')}</span>}
                </li>
            ))}
        </ul>
    </FadeRise>
);

BlockingNotice.propTypes = {
    title: PropTypes.string.isRequired,
    text: PropTypes.string.isRequired,
    items: PropTypes.array.isRequired,
};

const DeliveryResult = ({ result }) => {
    if (!result) return null;

    if (result.blocked) {
        return (
            <BlockingNotice
                title="Не хватает данных для расчёта"
                text="Заполните вес и габариты этих товаров в МойСклад и запустите расчёт повторно."
                items={result.missing || []}
            />
        );
    }

    const { packing, carriers = {}, to_city: toCity } = result;
    const unpackable = packing?.unpackable || [];

    if (unpackable.length > 0) {
        return (
            <BlockingNotice
                title="Не удалось подобрать упаковку"
                text="Габариты этих товаров не подходят ни под одну коробку. Тарифы не показаны, чтобы не занижать стоимость доставки."
                items={unpackable.map((name) => ({ name }))}
            />
        );
    }

    const boxesText = Object.entries(packing.boxes || {})
        .map(([code, amount]) => `${code} × ${amount}`)
        .join(', ');
    const prices = Object.entries(carriers)
        .map(([id, carrier]) => [id, basePrice(carrier)])
        .filter(([, price]) => price !== null);
    const cheapestId = prices.length
        ? prices.reduce((left, right) => (right[1] < left[1] ? right : left))[0]
        : null;
    const speeds = Object.entries(carriers)
        .filter(([, carrier]) => carrier && !carrier.error)
        .map(([id, carrier]) => [id, minDays(carrier.days)]);
    const fastestId = speeds.length
        ? speeds.reduce((left, right) => (right[1] < left[1] ? right : left))[0]
        : null;
    const compareCarriers = prices.length > 1;

    return (
        <FadeRise className="delivery-result">
            <div className="delivery-result__shell">
                <div className="delivery-result__heading">
                    <div>
                        <span className="delivery-result__eyebrow">Результат расчёта</span>
                        <h2>Доставка в {toCity || 'указанный город'}</h2>
                        <p>Тарифы рассчитаны по данным упаковки из МойСклад.</p>
                    </div>
                    <span className="delivery-result__status">Предварительно</span>
                </div>

                <div className="delivery-cargo-summary">
                    <CargoStat icon={Package} value={packing.places} label="грузовых мест" />
                    <CargoStat icon={Weight} value={`${packing.weight_kg} кг`} label="общий вес" />
                    <CargoStat icon={Ruler} value={`${packing.volume_l} л`} label="объём груза" />
                    <CargoStat icon={Boxes} value={boxesText || '—'} label="коробки" />
                </div>

                <div className="delivery-tariffs">
                    <div className="delivery-tariffs__head">
                        <h3>Тарифы перевозчиков</h3>
                        {compareCarriers && <p>Сравниваем стоимость до пункта / терминала.</p>}
                    </div>
                    <Stagger className="delivery-carrier-grid">
                        {Object.entries(carriers).map(([id, data]) => (
                            <StaggerItem key={id}>
                                <CarrierCard
                                    id={id}
                                    data={data}
                                    cheapest={compareCarriers && id === cheapestId}
                                    fastest={compareCarriers && id === fastestId}
                                />
                            </StaggerItem>
                        ))}
                    </Stagger>
                </div>

                {packing.detail?.length > 0 && (
                    <details className="delivery-box-details">
                        <summary>
                            <span>Раскладка по коробкам</span>
                            <span>{packing.places} мест</span>
                            <ChevronDown aria-hidden="true" />
                        </summary>
                        <div className="delivery-box-details__body">
                            {packing.detail.map((box, index) => (
                                <div key={`${box.box}-${index}`} className="delivery-box-row">
                                    <span className="delivery-box-row__code">{box.box}</span>
                                    <span className="delivery-box-row__items">{box.items.join(', ')}</span>
                                    <span className="delivery-box-row__meta">
                                        {box.weight_kg} кг · заполнение {box.fill_pct}%
                                    </span>
                                </div>
                            ))}
                        </div>
                    </details>
                )}

                <p className="delivery-result__disclaimer">
                    Итоговый тариф может измениться после контрольного обмера и взвешивания.
                </p>
            </div>
        </FadeRise>
    );
};

DeliveryResult.propTypes = { result: PropTypes.object };

export default DeliveryResult;
