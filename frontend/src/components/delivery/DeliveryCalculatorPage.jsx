import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import {
    Search,
    Trash2,
    Minus,
    Plus,
    Loader2,
    MapPin,
    Calculator,
    Check,
    PackageSearch,
    ChevronRight,
    StickyNote,
    ClipboardList,
} from 'lucide-react';
import { m } from 'motion/react';
import SectionLabel from '../ui/SectionLabel';
import Tooltip from '../ui/Tooltip';
import { FadeRise, Stagger, StaggerItem } from '../ui/motion';
import { deliveryApi } from '../../api/deliveryApi';
import DeliveryResult from './DeliveryResult';
import './DeliveryCalculatorPage.css';

const useDebounce = (callback, delay) => {
    const timeoutRef = useRef(null);
    useEffect(() => () => { if (timeoutRef.current) clearTimeout(timeoutRef.current); }, []);
    return useCallback((...args) => {
        if (timeoutRef.current) clearTimeout(timeoutRef.current);
        timeoutRef.current = setTimeout(() => callback(...args), delay);
    }, [callback, delay]);
};

const money = (value) => Math.round(value || 0).toLocaleString('ru-RU');

const normalizeSuggestedCity = (value) => {
    const city = String(value || '').trim();
    if (['россия', 'российская федерация', 'рф'].includes(city.toLocaleLowerCase('ru-RU'))) {
        return '';
    }
    return city.replace(/^(?:г(?:ород)?\.?)\s+/iu, '').trim();
};

const cityValueFromSuggestion = (value) => (
    normalizeSuggestedCity(value).replace(/\s*\([^)]*\)\s*$/u, '').trim()
);

const normalizedCityKey = (value) => (
    cityValueFromSuggestion(value).toLocaleLowerCase('ru-RU').replace(/ё/g, 'е')
);

const productMeasure = (value) => {
    const matches = [
        ...String(value || '').matchAll(
            /(\d+(?:[.,]\d+)?)\s*(кг|г|мл|л|шт)(?=\s|[),.;]|$)/giu,
        ),
    ];
    const match = matches.at(-1);
    return match ? `${match[1]} ${match[2].toLocaleLowerCase('ru-RU')}` : '';
};

const orderDate = (value) => {
    if (!value) return '';
    const date = new Date(value);
    return Number.isNaN(date.getTime())
        ? ''
        : date.toLocaleDateString('ru-RU', { day: '2-digit', month: 'short' });
};

const DeliveryCalculatorPage = () => {
    const [mode, setMode] = useState('order');

    const [recent, setRecent] = useState([]);
    const [recentLoading, setRecentLoading] = useState(false);
    const [recentProgress, setRecentProgress] = useState(0);
    const [orderQuery, setOrderQuery] = useState('');
    const [orderNumber, setOrderNumber] = useState('');
    const [orderId, setOrderId] = useState(null);
    const [note, setNote] = useState('');

    const [manualItems, setManualItems] = useState([]);
    const [searchValue, setSearchValue] = useState('');
    const [searchResults, setSearchResults] = useState([]);
    const [searchLoading, setSearchLoading] = useState(false);
    const [showDropdown, setShowDropdown] = useState(false);
    const searchRef = useRef(null);
    const recentRequestedRef = useRef(false);
    const resultSectionRef = useRef(null);
    const revealResultRef = useRef(false);

    const [loading, setLoading] = useState(false);
    const [progress, setProgress] = useState(0);
    const [citiesByMode, setCitiesByMode] = useState({ order: '', manual: '' });
    const [selectedCitiesByMode, setSelectedCitiesByMode] = useState({ order: '', manual: '' });
    const [citySuggestionsByMode, setCitySuggestionsByMode] = useState({ order: [], manual: [] });
    const [citySearchLoadingByMode, setCitySearchLoadingByMode] = useState({ order: false, manual: false });
    const [citySearchErrorsByMode, setCitySearchErrorsByMode] = useState({ order: '', manual: '' });
    const [showCitySuggestions, setShowCitySuggestions] = useState(false);
    const [resultsByMode, setResultsByMode] = useState({ order: null, manual: null });
    const [errorsByMode, setErrorsByMode] = useState({ order: null, manual: null });
    const cityPickerRef = useRef(null);
    const citySearchRequestRef = useRef(0);
    const city = citiesByMode[mode];
    const selectedCity = selectedCitiesByMode[mode];
    const citySuggestions = citySuggestionsByMode[mode];
    const citySearchLoading = citySearchLoadingByMode[mode];
    const citySearchError = citySearchErrorsByMode[mode];
    const result = resultsByMode[mode];
    const error = errorsByMode[mode];

    useEffect(() => {
        if (mode !== 'order' || recent.length || recentLoading || recentRequestedRef.current) return;
        recentRequestedRef.current = true;
        setRecentLoading(true);
        setRecentProgress(0);
        const interval = setInterval(
            () => setRecentProgress((value) => (value < 90 ? value + 8 : value)),
            200,
        );
        deliveryApi.recentOrders()
            .then((rows) => setRecent(Array.isArray(rows) ? rows : []))
            .catch(() => setRecent([]))
            .finally(() => {
                clearInterval(interval);
                setRecentProgress(100);
                setRecentLoading(false);
                setTimeout(() => setRecentProgress(0), 600);
            });
    }, [mode, recent.length, recentLoading]);

    useEffect(() => {
        const onClick = (event) => {
            if (searchRef.current && !searchRef.current.contains(event.target)) {
                setShowDropdown(false);
            }
            if (cityPickerRef.current && !cityPickerRef.current.contains(event.target)) {
                setShowCitySuggestions(false);
            }
        };
        document.addEventListener('mousedown', onClick);
        return () => document.removeEventListener('mousedown', onClick);
    }, []);

    useEffect(() => {
        if ((!result && !error) || !revealResultRef.current) return;
        revealResultRef.current = false;
        const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
        requestAnimationFrame(() => {
            resultSectionRef.current?.scrollIntoView({
                behavior: reduceMotion ? 'auto' : 'smooth',
                block: 'nearest',
            });
        });
    }, [error, result]);

    const selectedOrder = useMemo(
        () => recent.find((order) => order.id === orderId) || null,
        [orderId, recent],
    );

    const filteredOrders = useMemo(() => {
        const query = orderQuery.trim().toLocaleLowerCase('ru-RU');
        if (!query) return recent;
        return recent.filter((order) => (
            [order.name, order.counterparty, order.city]
                .filter(Boolean)
                .some((value) => String(value).toLocaleLowerCase('ru-RU').includes(query))
        ));
    }, [orderQuery, recent]);
    const canUseOrderQuery = /^\d+$/.test(orderQuery.trim());

    const selectOrder = async (order) => {
        const suggestedCity = normalizeSuggestedCity(order.city);
        const requestId = ++citySearchRequestRef.current;
        setOrderId(order.id);
        setOrderNumber(order.name || '');
        setNote(order.address || '');
        setCitiesByMode((values) => ({ ...values, order: suggestedCity }));
        setSelectedCitiesByMode((values) => ({ ...values, order: '' }));
        setCitySuggestionsByMode((values) => ({ ...values, order: [] }));
        setCitySearchErrorsByMode((values) => ({ ...values, order: '' }));
        setShowCitySuggestions(false);
        setResultsByMode((values) => ({ ...values, order: null }));
        setErrorsByMode((values) => ({ ...values, order: null }));

        if (suggestedCity.length < 2) {
            setCitySearchLoadingByMode((values) => ({ ...values, order: false }));
            return;
        }

        setCitySearchLoadingByMode((values) => ({ ...values, order: true }));
        try {
            const rows = await deliveryApi.searchCities(suggestedCity);
            if (citySearchRequestRef.current !== requestId) return;
            const suggestions = Array.isArray(rows) ? rows : [];
            const exact = suggestions.find((suggestion) => (
                normalizedCityKey(suggestion.name) === normalizedCityKey(suggestedCity)
            ));
            setCitySuggestionsByMode((values) => ({ ...values, order: suggestions }));
            if (exact) {
                const confirmedCity = cityValueFromSuggestion(exact.name);
                setCitiesByMode((values) => ({ ...values, order: confirmedCity }));
                setSelectedCitiesByMode((values) => ({ ...values, order: confirmedCity }));
            }
        } catch {
            if (citySearchRequestRef.current !== requestId) return;
            setCitySearchErrorsByMode((values) => ({
                ...values,
                order: 'Не удалось проверить город из заказа',
            }));
        } finally {
            if (citySearchRequestRef.current === requestId) {
                setCitySearchLoadingByMode((values) => ({ ...values, order: false }));
            }
        }
    };

    const selectOrderNumber = () => {
        const value = orderQuery.trim();
        if (!value) return;
        setOrderId(null);
        setOrderNumber(value);
        setNote('');
        setCitiesByMode((values) => ({ ...values, order: '' }));
        setSelectedCitiesByMode((values) => ({ ...values, order: '' }));
        setCitySuggestionsByMode((values) => ({ ...values, order: [] }));
        setShowCitySuggestions(false);
        setResultsByMode((values) => ({ ...values, order: null }));
        setErrorsByMode((values) => ({ ...values, order: null }));
    };

    const changeMode = (nextMode) => setMode(nextMode);

    const doSearch = useDebounce(async (query) => {
        if (query.trim().length < 2) {
            setSearchResults([]);
            return;
        }
        setSearchLoading(true);
        try {
            const rows = await deliveryApi.searchProducts(query.trim());
            setSearchResults(Array.isArray(rows) ? rows : []);
            setShowDropdown(true);
        } catch {
            setSearchResults([]);
        } finally {
            setSearchLoading(false);
        }
    }, 300);

    const doCitySearch = useDebounce(async (query, searchMode, requestId) => {
        setCitySearchLoadingByMode((values) => ({ ...values, [searchMode]: true }));
        setCitySearchErrorsByMode((values) => ({ ...values, [searchMode]: '' }));
        try {
            const rows = await deliveryApi.searchCities(query);
            if (citySearchRequestRef.current !== requestId) return;
            setCitySuggestionsByMode((values) => ({
                ...values,
                [searchMode]: Array.isArray(rows) ? rows : [],
            }));
        } catch {
            if (citySearchRequestRef.current !== requestId) return;
            setCitySuggestionsByMode((values) => ({ ...values, [searchMode]: [] }));
            setCitySearchErrorsByMode((values) => ({
                ...values,
                [searchMode]: 'Не удалось загрузить варианты городов',
            }));
        } finally {
            if (citySearchRequestRef.current === requestId) {
                setCitySearchLoadingByMode((values) => ({ ...values, [searchMode]: false }));
            }
        }
    }, 250);

    const requestCitySuggestions = (value, searchMode = mode) => {
        const query = value.trim();
        const requestId = ++citySearchRequestRef.current;
        setShowCitySuggestions(true);
        setCitySearchErrorsByMode((values) => ({ ...values, [searchMode]: '' }));
        if (query.length < 2) {
            setCitySuggestionsByMode((values) => ({ ...values, [searchMode]: [] }));
            setCitySearchLoadingByMode((values) => ({ ...values, [searchMode]: false }));
            return;
        }
        doCitySearch(query, searchMode, requestId);
    };

    const changeCity = (value) => {
        const cityMode = mode;
        setCitiesByMode((values) => ({ ...values, [cityMode]: value }));
        setSelectedCitiesByMode((values) => ({ ...values, [cityMode]: '' }));
        setResultsByMode((values) => ({ ...values, [cityMode]: null }));
        setErrorsByMode((values) => ({ ...values, [cityMode]: null }));
        requestCitySuggestions(value, cityMode);
    };

    const selectCitySuggestion = (name) => {
        const cityMode = mode;
        const confirmedCity = cityValueFromSuggestion(name);
        setCitiesByMode((values) => ({ ...values, [cityMode]: confirmedCity }));
        setSelectedCitiesByMode((values) => ({ ...values, [cityMode]: confirmedCity }));
        setCitySuggestionsByMode((values) => ({ ...values, [cityMode]: [] }));
        setCitySearchErrorsByMode((values) => ({ ...values, [cityMode]: '' }));
        setShowCitySuggestions(false);
        setResultsByMode((values) => ({ ...values, [cityMode]: null }));
        setErrorsByMode((values) => ({ ...values, [cityMode]: null }));
    };

    const addProduct = (product) => {
        setManualItems((items) => items.some((item) => item.href === product.href)
            ? items.map((item) => item.href === product.href
                ? { ...item, qty: String(Number(item.qty || 1) + 1) }
                : item)
            : [...items, { ...product, qty: '1' }]);
        setSearchValue('');
        setSearchResults([]);
        setShowDropdown(false);
        setResultsByMode((values) => ({ ...values, manual: null }));
        setErrorsByMode((values) => ({ ...values, manual: null }));
    };

    const changeQty = (href, raw) => {
        setManualItems((items) => items.map((item) => (
            item.href === href ? { ...item, qty: raw.replace(/\D/g, '') } : item
        )));
        setResultsByMode((values) => ({ ...values, manual: null }));
        setErrorsByMode((values) => ({ ...values, manual: null }));
    };

    const normalizeQty = (href) => setManualItems((items) => items.map((item) => (
        item.href === href
            ? { ...item, qty: String(Math.max(1, parseInt(item.qty, 10) || 1)) }
            : item
    )));

    const adjustQty = (href, delta) => {
        setManualItems((items) => items.map((item) => (
            item.href === href
                ? { ...item, qty: String(Math.max(1, (parseInt(item.qty, 10) || 1) + delta)) }
                : item
        )));
        setResultsByMode((values) => ({ ...values, manual: null }));
        setErrorsByMode((values) => ({ ...values, manual: null }));
    };

    const removeItem = (href) => {
        setManualItems((items) => items.filter((item) => item.href !== href));
        setResultsByMode((values) => ({ ...values, manual: null }));
        setErrorsByMode((values) => ({ ...values, manual: null }));
    };

    const hasSource = mode === 'order'
        ? Boolean(orderId || orderNumber.trim())
        : manualItems.length > 0;
    const cityConfirmed = Boolean(city.trim() && selectedCity === city.trim());
    const canCalc = Boolean(cityConfirmed && hasSource && !loading);

    const calculate = async () => {
        const calculationMode = mode;
        const calculationCity = citiesByMode[calculationMode];
        setErrorsByMode((values) => ({ ...values, [calculationMode]: null }));
        setResultsByMode((values) => ({ ...values, [calculationMode]: null }));
        setLoading(true);
        setProgress(0);
        const progressInterval = setInterval(
            () => setProgress((value) => (value < 90 ? value + 10 : value)),
            200,
        );
        try {
            const payload = calculationMode === 'order'
                ? { mode: 'order', order: orderId || orderNumber.trim(), to_city: calculationCity.trim() }
                : {
                    mode: 'manual',
                    positions: manualItems.map((item) => ({
                        href: item.href,
                        qty: parseInt(item.qty, 10) || 1,
                        name: item.name,
                        code: item.code,
                    })),
                    to_city: calculationCity.trim(),
                };
            const data = await deliveryApi.estimate(payload);
            clearInterval(progressInterval);
            setProgress(100);
            revealResultRef.current = true;
            setResultsByMode((values) => ({ ...values, [calculationMode]: data }));
        } catch (err) {
            clearInterval(progressInterval);
            revealResultRef.current = true;
            setErrorsByMode((values) => ({
                ...values,
                [calculationMode]: err?.data?.error || err?.message || 'Не удалось рассчитать доставку',
            }));
        } finally {
            setLoading(false);
            setTimeout(() => setProgress(0), 800);
        }
    };

    const selectionTitle = mode === 'order'
        ? (orderNumber ? `Заказ ${orderNumber}` : 'Заказ не выбран')
        : (manualItems.length ? `${manualItems.length} поз. в расчёте` : 'Состав не заполнен');

    const calculationStatus = loading
        ? {
            kind: 'loading',
            title: 'Рассчитываем доставку',
            detail: 'Подбираем упаковку и сравниваем тарифы',
            meta: `${Math.min(progress, 100)}%`,
            progress: Math.min(progress, 100),
        }
        : result
            ? {
                kind: 'result',
                title: 'Расчёт готов',
                detail: `Тарифы для города ${result.to_city || city} обновлены`,
                meta: 'Готово',
                progress: 100,
            }
            : error
                ? {
                    kind: 'error',
                    title: 'Расчёт не выполнен',
                    detail: 'Исправьте данные и повторите попытку',
                    meta: 'Ошибка',
                    progress: 0,
                }
                : !hasSource
                    ? {
                        kind: 'idle',
                        title: mode === 'order' ? 'Выберите заказ' : 'Добавьте товары',
                        detail: 'Затем выберите город получателя',
                        meta: 'Ожидание',
                        progress: 0,
                    }
                    : citySearchLoading
                        ? {
                            kind: 'validating',
                            title: 'Проверяем город',
                            detail: 'Сверяем направление со справочником перевозчика',
                            meta: 'Проверка',
                            progress: 45,
                        }
                    : !cityConfirmed
                        ? {
                            kind: 'idle',
                            title: 'Выберите город из списка',
                            detail: 'Так перевозчики получат корректное направление',
                            meta: 'Ожидание',
                            progress: 0,
                        }
                        : {
                            kind: 'ready',
                            title: 'Всё готово к расчёту',
                            detail: `Направление подтверждено: ${selectedCity}`,
                            meta: 'Готово',
                            progress: 100,
                        };

    const feedbackPanel = (
        <div className="delivery-feedback">
            <div
                className={`delivery-calculation-status is-${calculationStatus.kind}`}
                role="status"
                aria-live="polite"
            >
                <div className="delivery-calculation-status__head">
                    {calculationStatus.kind === 'loading' || calculationStatus.kind === 'validating'
                        ? <Loader2 className="animate-spin" aria-hidden="true" />
                        : calculationStatus.kind === 'result' || calculationStatus.kind === 'ready'
                            ? <Check aria-hidden="true" />
                            : <Calculator aria-hidden="true" />}
                    <span>
                        <strong>{calculationStatus.title}</strong>
                        <small>{calculationStatus.detail}</small>
                    </span>
                    <b>{calculationStatus.meta}</b>
                </div>
                <div className="delivery-progress delivery-progress--calculation" aria-hidden="true">
                    <span style={{ width: `${calculationStatus.progress}%` }} />
                </div>
            </div>
            {error && (
                <div ref={resultSectionRef} className="delivery-result-section">
                    <FadeRise className="delivery-alert delivery-alert--error" role="alert">
                        {error}
                    </FadeRise>
                </div>
            )}
            {result && (
                <section ref={resultSectionRef} className="delivery-result-section">
                    <DeliveryResult result={result} />
                </section>
            )}
        </div>
    );

    const renderCityPicker = (id, placeholder) => {
        const listId = `${id}-options`;
        const hintId = `${id}-hint`;
        const hasQuery = city.trim().length >= 2;
        const showOptions = showCitySuggestions && hasQuery;
        return (
            <div
                ref={cityPickerRef}
                className={cityConfirmed ? 'delivery-city-picker is-confirmed' : 'delivery-city-picker'}
            >
                <div className="delivery-input">
                    <MapPin aria-hidden="true" />
                    <input
                        id={id}
                        value={city}
                        onChange={(event) => changeCity(event.target.value)}
                        onFocus={() => requestCitySuggestions(city)}
                        placeholder={placeholder}
                        role="combobox"
                        aria-autocomplete="list"
                        aria-expanded={showOptions}
                        aria-controls={listId}
                        aria-describedby={hintId}
                        autoComplete="off"
                        spellCheck="false"
                    />
                    {citySearchLoading
                        ? <Loader2 className="delivery-city-picker__state animate-spin" aria-hidden="true" />
                        : cityConfirmed && <Check className="delivery-city-picker__state" aria-hidden="true" />}
                </div>
                {showOptions && (
                    <div id={listId} className="delivery-city-options" role="listbox">
                        {citySearchLoading && (
                            <div className="delivery-city-options__message">Ищем город…</div>
                        )}
                        {!citySearchLoading && citySuggestions.map((suggestion) => (
                            <button
                                type="button"
                                role="option"
                                aria-selected={cityValueFromSuggestion(suggestion.name) === selectedCity}
                                key={suggestion.name}
                                onClick={() => selectCitySuggestion(suggestion.name)}
                            >
                                <MapPin aria-hidden="true" />
                                <span>{suggestion.name}</span>
                            </button>
                        ))}
                        {!citySearchLoading && citySearchError && (
                            <div className="delivery-city-options__message is-error">{citySearchError}</div>
                        )}
                        {!citySearchLoading && !citySearchError && citySuggestions.length === 0 && (
                            <div className="delivery-city-options__message">
                                Город не найден. Проверьте написание.
                            </div>
                        )}
                    </div>
                )}
                <small id={hintId} className="delivery-city-picker__hint">
                    {cityConfirmed
                        ? `Выбран город: ${selectedCity}`
                        : city
                            ? 'Выберите подходящий город из подсказок'
                            : 'Начните вводить и выберите город из списка'}
                </small>
            </div>
        );
    };

    const calculationControls = mode === 'order' ? (
        <div className={orderNumber ? 'delivery-calc-strip' : 'delivery-calc-strip is-empty'}>
            {orderNumber ? (
                <>
                    <div className="delivery-calc-strip__context">
                        <span>Заказ {orderNumber}</span>
                        <strong>{selectedOrder?.counterparty || 'Заказ по номеру'}</strong>
                        {note && <small title={note}><StickyNote aria-hidden="true" />{note}</small>}
                    </div>
                    <div className="delivery-calc-strip__actions">
                        <label htmlFor="delivery-order-city">Город получателя</label>
                        {renderCityPicker('delivery-order-city', 'Например, Владимир')}
                        <button
                            type="button"
                            className="delivery-calculate"
                            onClick={calculate}
                            disabled={!canCalc}
                        >
                            {loading
                                ? <><Loader2 className="animate-spin" aria-hidden="true" />Считаем…</>
                                : <><Calculator aria-hidden="true" />{result ? 'Пересчитать' : 'Рассчитать'}</>}
                        </button>
                    </div>
                </>
            ) : (
                <>
                    <ClipboardList aria-hidden="true" />
                    <span>Выберите заказ — здесь появятся город и расчёт.</span>
                </>
            )}
        </div>
    ) : (
        <div className="delivery-calc-strip">
            <div className="delivery-calc-strip__context">
                <span>Ручной состав</span>
                <strong>{selectionTitle}</strong>
                <small>Добавьте товары и укажите город назначения.</small>
            </div>
            <div className="delivery-calc-strip__actions">
                <label htmlFor="delivery-manual-city">Город получателя</label>
                {renderCityPicker('delivery-manual-city', 'Например, Санкт-Петербург')}
                <button
                    type="button"
                    className="delivery-calculate"
                    onClick={calculate}
                    disabled={!canCalc}
                >
                    {loading
                        ? <><Loader2 className="animate-spin" aria-hidden="true" />Считаем…</>
                        : <><Calculator aria-hidden="true" />{result ? 'Пересчитать' : 'Рассчитать'}</>}
                </button>
            </div>
        </div>
    );

    const resultColumn = (
        <div className="delivery-result-column">
            {calculationControls}
            {feedbackPanel}
        </div>
    );

    return (
        <div className="delivery-page">
            <header className="delivery-page__header">
                <h1>Калькулятор доставки</h1>
                <p>Подбор упаковки и сравнение тарифов ПЭК и СДЭК для клиентских заказов.</p>
            </header>

            <section>
                <SectionLabel>Источник расчёта</SectionLabel>
                <div className="delivery-tabs" role="tablist" aria-label="Источник расчёта">
                    {[
                        { key: 'order', label: 'Заказ МойСклад' },
                        { key: 'manual', label: 'Ручной состав' },
                    ].map((tab) => (
                        <button
                            key={tab.key}
                            type="button"
                            role="tab"
                            aria-selected={mode === tab.key}
                            className={mode === tab.key ? 'delivery-tabs__button is-active' : 'delivery-tabs__button'}
                            onClick={() => changeMode(tab.key)}
                        >
                            {tab.label}
                            {mode === tab.key && (
                                <m.span
                                    layoutId="delivery-tab-pill"
                                    className="delivery-tabs__active"
                                    transition={{ type: 'spring', stiffness: 500, damping: 40 }}
                                />
                            )}
                        </button>
                    ))}
                </div>

                {mode === 'order' ? (
                    <FadeRise className="delivery-workspace">
                        <div className="delivery-browser">
                            <div className="delivery-browser__head">
                                <div>
                                    <h2>Последние заказы</h2>
                                    <p>Выберите заказ или введите его номер.</p>
                                </div>
                                <span className="delivery-count">{recent.length}</span>
                            </div>

                            <div className="delivery-search">
                                <Search aria-hidden="true" />
                                <input
                                    value={orderQuery}
                                    onChange={(event) => setOrderQuery(event.target.value)}
                                    onKeyDown={(event) => {
                                        if (event.key === 'Enter' && canUseOrderQuery) selectOrderNumber();
                                    }}
                                    placeholder="Номер, клиент или город"
                                    aria-label="Поиск заказа"
                                />
                            </div>

                            {(recentLoading || recentProgress > 0) && (
                                <div className="delivery-progress" aria-label="Загрузка заказов">
                                    <span style={{ width: `${Math.min(recentProgress, 100)}%` }} />
                                </div>
                            )}

                            <div className="delivery-order-list">
                                {recentLoading && recent.length === 0 && (
                                    <div className="delivery-order-skeletons">
                                        {[0, 1, 2, 3, 4].map((index) => (
                                            <div key={index} className="delivery-order-skeleton">
                                                <div className="skeleton" />
                                            </div>
                                        ))}
                                    </div>
                                )}

                                {!recentLoading && filteredOrders.length === 0 && (
                                    <div className="delivery-order-empty">
                                        {orderQuery.trim()
                                            ? (canUseOrderQuery
                                                ? <>В списке совпадений нет. Можно продолжить с номером <strong>{orderQuery.trim()}</strong>.</>
                                                : 'В последних заказах совпадений нет.')
                                            : 'Заказов не найдено.'}
                                    </div>
                                )}

                                {filteredOrders.map((order) => {
                                    const active = orderId === order.id;
                                    const suggestedCity = normalizeSuggestedCity(order.city);
                                    return (
                                        <button
                                            type="button"
                                            key={order.id}
                                            className={active ? 'delivery-order is-active' : 'delivery-order'}
                                            onClick={() => selectOrder(order)}
                                        >
                                            <span className="delivery-order__number">
                                                <strong>{order.name}</strong>
                                                <small>{orderDate(order.moment)}</small>
                                            </span>
                                            <span className="delivery-order__customer">
                                                <strong>{order.counterparty || 'Без контрагента'}</strong>
                                                <small>{suggestedCity || 'Город не указан'}</small>
                                            </span>
                                            <span className="delivery-order__sum">{money(order.sum)} ₽</span>
                                            <ChevronRight aria-hidden="true" />
                                        </button>
                                    );
                                })}
                            </div>

                            {canUseOrderQuery && (
                                <button type="button" className="delivery-number-action" onClick={selectOrderNumber}>
                                    Использовать номер «{orderQuery.trim()}»
                                    <ChevronRight aria-hidden="true" />
                                </button>
                            )}
                        </div>

                        {resultColumn}
                    </FadeRise>
                ) : (
                    <FadeRise className="delivery-workspace">
                        <div className="delivery-browser delivery-browser--manual">
                            <div className="delivery-browser__head">
                                <div>
                                    <h2>Состав отправления</h2>
                                    <p>Добавьте готовую продукцию и укажите количество.</p>
                                </div>
                                <span className="delivery-count">{manualItems.length}</span>
                            </div>

                            <div ref={searchRef} className="delivery-product-search">
                                <div className="delivery-search">
                                    <Search aria-hidden="true" />
                                    <input
                                        value={searchValue}
                                        onChange={(event) => {
                                            setSearchValue(event.target.value);
                                            doSearch(event.target.value);
                                        }}
                                        onFocus={() => {
                                            if (searchResults.length) setShowDropdown(true);
                                        }}
                                        placeholder="Название или артикул товара"
                                        aria-label="Поиск товара"
                                    />
                                    {searchLoading && <Loader2 className="animate-spin delivery-search__loader" aria-hidden="true" />}
                                </div>

                                {showDropdown && searchResults.length > 0 && (
                                    <div className="delivery-product-results">
                                        {searchResults.map((product) => {
                                            const measure = productMeasure(product.name);
                                            return (
                                                <button type="button" key={product.href} onMouseDown={() => addProduct(product)}>
                                                    <span>{product.code || 'Без артикула'}</span>
                                                    <Tooltip content={product.name} focusable={false}>
                                                        <strong>{product.name}</strong>
                                                    </Tooltip>
                                                    {measure && <em>{measure}</em>}
                                                </button>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>

                            {manualItems.length > 0 ? (
                                <Stagger className="delivery-manual-list">
                                    {manualItems.map((item) => (
                                        <StaggerItem key={item.href}>
                                            <div className="delivery-manual-item">
                                                <span>
                                                    <Tooltip content={item.name}>
                                                        <strong>{item.name}</strong>
                                                    </Tooltip>
                                                    <small>{item.code || 'Без артикула'}</small>
                                                </span>
                                                <div className="delivery-manual-item__quantity">
                                                    <span>Количество</span>
                                                    <div className="delivery-qty-stepper">
                                                        <button
                                                            type="button"
                                                            onClick={() => adjustQty(item.href, -1)}
                                                            disabled={(parseInt(item.qty, 10) || 1) <= 1}
                                                            aria-label={`Уменьшить количество: ${item.name}`}
                                                        >
                                                            <Minus aria-hidden="true" />
                                                        </button>
                                                        <input
                                                            inputMode="numeric"
                                                            value={item.qty}
                                                            onChange={(event) => changeQty(item.href, event.target.value)}
                                                            onBlur={() => normalizeQty(item.href)}
                                                            aria-label={`Количество: ${item.name}`}
                                                        />
                                                        <button
                                                            type="button"
                                                            onClick={() => adjustQty(item.href, 1)}
                                                            aria-label={`Увеличить количество: ${item.name}`}
                                                        >
                                                            <Plus aria-hidden="true" />
                                                        </button>
                                                    </div>
                                                </div>
                                                <button
                                                    type="button"
                                                    onClick={() => removeItem(item.href)}
                                                    aria-label={`Удалить ${item.name}`}
                                                >
                                                    <Trash2 aria-hidden="true" />
                                                </button>
                                            </div>
                                        </StaggerItem>
                                    ))}
                                </Stagger>
                            ) : (
                                <div className="delivery-product-empty">
                                    <PackageSearch aria-hidden="true" />
                                    <p>Начните вводить название товара. Поиск показывает только готовую продукцию.</p>
                                </div>
                            )}
                        </div>

                        {resultColumn}
                    </FadeRise>
                )}
            </section>

        </div>
    );
};

export default DeliveryCalculatorPage;
