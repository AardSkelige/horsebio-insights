import { useCallback, useEffect, useRef, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { FadeRise, Stagger, StaggerItem } from '../ui/motion';
import { discountedApi } from '../../api/discountedApi';
import DiscountedCard from './DiscountedCard';
import './Discounted.css';

const money = (value) => `${Math.round(value || 0).toLocaleString('ru-RU')} ₽`;

// Три дорожки. Порядок — от срочного к спокойному: экран читается слева направо,
// и пустая левая колонка сразу означает «делать нечего».
const LANES = [
    {
        key: 'urgent',
        title: 'Снять с продажи',
        tone: 'urgent',
        states: ['expired'],
        empty: 'Просроченного нет',
    },
    {
        key: 'soon',
        title: 'Скоро снимать',
        tone: 'warn',
        states: ['delist', 'no_date'],
        empty: 'Ничего не подходит к сроку',
    },
    {
        key: 'selling',
        title: 'В продаже',
        tone: '',
        states: ['ok'],
        empty: 'Пусто',
    },
];

function timeAgo(iso) {
    if (!iso) return null;
    const minutes = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
    if (minutes < 1) return 'только что';
    if (minutes < 60) return `${minutes} мин назад`;
    return `${Math.round(minutes / 60)} ч назад`;
}

export default function DiscountedPage() {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const abortRef = useRef(null);

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

    const positions = data?.positions ?? [];
    const inStock = positions.filter((p) => p.quantity > 0);
    const summary = data?.summary ?? {};

    return (
        <FadeRise>
            <div style={{ padding: '24px 0' }}>
                <div style={{
                    display: 'flex', alignItems: 'baseline', justifyContent: 'space-between',
                    flexWrap: 'wrap', gap: 10, marginBottom: 4,
                }}>
                    <h1 className="uc-title">
                        Уценка
                    </h1>
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

                <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: '0 0 16px' }}>
                    Склад «Уценка» в МойСклад
                    {data?.generated_at && ` · обновлено ${timeAgo(data.generated_at)}`}
                    {data?.rules && ` · скидка ${Math.round(data.rules.discount_rate * 100)} %, снимаем за ${data.rules.months_to_delist} мес до конца срока`}
                </p>

                {error && (
                    <div className="uc-error" style={{ marginBottom: 14, fontSize: 13 }}>{error}</div>
                )}

                {loading && !data && (
                    <p style={{ fontSize: 13, color: 'var(--muted)' }}>Загружаю…</p>
                )}

                {data && (
                    <>
                        <div className="uc-summary">
                            <div><div className="k">Позиций</div><div className="v">{summary.positions ?? 0}</div></div>
                            <div><div className="k">Единиц</div><div className="v">{summary.units ?? 0}</div></div>
                            <div><div className="k">Сумма</div><div className="v">{money(summary.sum)}</div></div>
                            <div><div className="k">Себестоимость</div><div className="v">{money(summary.sum_cost)}</div></div>
                            <div>
                                <div className="k">Надо разобрать</div>
                                <div className={`v${summary.needs_action ? ' alert' : ''}`}>{summary.needs_action ?? 0}</div>
                            </div>
                        </div>

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
                            <p style={{ fontSize: 13, color: 'var(--muted)', marginTop: 18 }}>
                                На складе «Уценка» сейчас пусто. Позиции появятся здесь после того,
                                как Лера проведёт техоперацию в МойСклад.
                            </p>
                        )}
                    </>
                )}
            </div>
        </FadeRise>
    );
}
