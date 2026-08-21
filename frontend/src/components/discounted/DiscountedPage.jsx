import { useCallback, useEffect, useRef, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { FadeRise, Stagger, StaggerItem } from '../ui/motion';
import { discountedApi } from '../../api/discountedApi';
import DiscountedCard from './DiscountedCard';
import './Discounted.css';

const money = (value) => `${Math.round(value || 0).toLocaleString('ru-RU')} ₽`;
const units = (value) => `${Math.round(value || 0).toLocaleString('ru-RU')} шт`;

// Три дорожки. Порядок — от срочного к спокойному: экран читается слева направо,
// и пустая левая колонка сразу означает «делать нечего».
const LANES = [
    { key: 'urgent',  title: 'Снять с продажи', tone: 'urgent', states: ['expired'],           empty: 'Просроченного нет' },
    { key: 'soon',    title: 'Скоро снимать',   tone: 'warn',   states: ['delist', 'no_date'], empty: 'Ничего не подходит к сроку' },
    { key: 'selling', title: 'В продаже',       tone: '',       states: ['ok'],                empty: 'Пусто' },
];

// Процесс живёт в трёх местах сразу, и без подсказки на экране приходится каждый
// раз вспоминать, кто где нажимает.
const FLOW = [
    ['Лера', 'Находит товар с подходящим сроком и проводит техоперацию в МойСклад — товар переезжает на склад «Уценка»'],
    ['Система', 'Позиция появляется здесь, а обмен отправляет карточку, цену и остаток на сайт'],
    ['Сергей', 'Дописывает в карточке на сайте срок годности и текст про уценку'],
    ['Система', 'Остаток на сайте едет за МойСклад сам; за два месяца до конца срока позиция снимается с продажи'],
];

function formatTime(iso) {
    if (!iso) return null;
    return new Date(iso).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}

export default function DiscountedPage() {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [isMobile, setIsMobile] = useState(() => window.innerWidth < 768);
    const abortRef = useRef(null);

    useEffect(() => {
        const handler = () => setIsMobile(window.innerWidth < 768);
        window.addEventListener('resize', handler);
        return () => window.removeEventListener('resize', handler);
    }, []);

    const load = useCallback(async (refresh = false) => {
        abortRef.current?.abort();
        const controller = new AbortController();
        abortRef.current = controller;

        setLoading(true);
        setError(null);
        try {
            const params = refresh ? { refresh: 1 } : undefined;
            // Интерцептор в utils/api.js уже разворачивает ответ до response.data,
            // так что здесь приходит сам объект, а не axios-response.
            setData(await discountedApi.getList(params, controller.signal));
        } catch (e) {
            if (e.name === 'CanceledError' || e.name === 'AbortError') return;
            setError(e?.message || 'Не удалось загрузить данные');
        } finally {
            if (!controller.signal.aborted) setLoading(false);
        }
    }, []);

    useEffect(() => {
        load();
        return () => abortRef.current?.abort();
    }, [load]);

    const inStock = (data?.positions ?? []).filter((p) => p.quantity > 0);
    const stats = data?.analytics;

    return (
        <FadeRise>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 18, color: 'var(--ink)' }}>
                <div style={{
                    display: 'flex', justifyContent: 'space-between',
                    alignItems: 'flex-start', gap: 16, flexWrap: 'wrap',
                }}>
                    <div>
                        <h1 style={{
                            fontFamily: 'var(--serif)', fontWeight: 400, fontSize: isMobile ? 24 : 30,
                            letterSpacing: '-0.02em', margin: '0 0 4px',
                        }}>
                            Уценка
                        </h1>
                        <p style={{ fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--muted)', margin: 0 }}>
                            Товар с подходящим сроком годности на складе «Уценка»
                            {data?.rules && ` — скидка ${Math.round(data.rules.discount_rate * 100)} %, снимаем с продажи за ${data.rules.months_to_delist} месяца до конца срока`}
                            {data?.generated_at && (
                                <>
                                    {' · '}
                                    <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--muted-soft)' }}>
                                        данные на {formatTime(data.generated_at)}
                                    </span>
                                </>
                            )}
                        </p>
                    </div>
                    <button
                        type="button"
                        className="uc-btn ghost"
                        onClick={() => load(true)}
                        disabled={loading}
                    >
                        <RefreshCw size={13} aria-hidden="true" />
                        Обновить
                    </button>
                </div>

                {error && <div className="uc-error" style={{ fontSize: 13 }}>{error}</div>}

                {loading && !data && (
                    <p style={{ fontSize: 13, color: 'var(--muted)' }}>Загружаю…</p>
                )}

                {data && (
                    <>
                        <div className="uc-board">
                            {LANES.map((lane) => {
                                const items = inStock.filter((p) => lane.states.includes(p.state));
                                return (
                                    <section
                                        key={lane.key}
                                        className={`uc-col ${lane.tone}${items.length === 0 ? ' empty' : ''}`}
                                    >
                                        <div className="uc-col-head">
                                            <span>{lane.title}</span>
                                            <span className="uc-col-count">{items.length}</span>
                                        </div>
                                        {items.length === 0 ? (
                                            <div className="uc-empty">{lane.empty}</div>
                                        ) : (
                                            <Stagger className="uc-list">
                                                {items.map((position) => (
                                                    <StaggerItem key={position.id}>
                                                        <DiscountedCard
                                                            position={position}
                                                            siteAdminUrl={data.site_admin_url}
                                                        />
                                                    </StaggerItem>
                                                ))}
                                            </Stagger>
                                        )}
                                    </section>
                                );
                            })}
                        </div>

                        {inStock.length === 0 && (
                            <p style={{ fontSize: 13, color: 'var(--muted)' }}>
                                На складе «Уценка» сейчас пусто. Позиции появятся здесь после того,
                                как Лера проведёт техоперацию в МойСклад.
                            </p>
                        )}

                        {stats && (
                            <section className="uc-block">
                                <h2 className="uc-h2">
                                    Итоги за год
                                    <span className="uc-h2-note">с {stats.period_from}</span>
                                </h2>
                                <div className="uc-stats">
                                    <div>
                                        <div className="k">Уценено</div>
                                        <div className="v">{units(stats.marked.quantity)}</div>
                                        <div className="s">себестоимость {money(stats.marked.cost)}</div>
                                    </div>
                                    <div>
                                        <div className="k">Продано</div>
                                        <div className="v">{units(stats.sold.quantity)}</div>
                                        <div className="s">выручка {money(stats.sold.revenue)}</div>
                                    </div>
                                    <div>
                                        <div className="k">Списано</div>
                                        <div className="v">{units(stats.written_off.quantity)}</div>
                                        <div className="s">потеряно {money(stats.written_off.cost)}</div>
                                    </div>
                                </div>
                                <p className="uc-note">
                                    Выручка от уценки — это деньги, которых иначе не было бы вовсе:
                                    товар с истекающим сроком ушёл бы в списание. «Списано» считается
                                    как разница — всё, что ушло со склада, но не продалось.
                                </p>
                            </section>
                        )}

                        <section className="uc-block">
                            <h2 className="uc-h2">Как это работает</h2>
                            <ol className="uc-flow">
                                {FLOW.map(([who, what]) => (
                                    <li key={what}>
                                        <span className="who">{who}</span>
                                        <span className="what">{what}</span>
                                    </li>
                                ))}
                            </ol>
                        </section>
                    </>
                )}
            </div>
        </FadeRise>
    );
}
