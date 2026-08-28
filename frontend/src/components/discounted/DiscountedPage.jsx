import { useCallback, useEffect, useRef, useState } from 'react';
import { timeOnly } from '../../utils/formatters';
import { EmptyState, ErrorState, Page, PageHeader, Skeleton, StatCard, StatGrid } from '../ui';
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
    ['Система', 'Позиция появляется здесь: цена, остаток и дата, до которой её можно продавать'],
    ['Сергей', 'Жмёт «Отправить на сайт» — карточка заводится с фотографиями, ценой, остатком и текстом про уценку. Остаётся открыть её в админке'],
    ['Система', 'Остаток на сайте едет за МойСклад сам; за два месяца до конца срока позиция снимается с продажи'],
];

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

    const inStock = (data?.positions ?? []).filter((p) => p.quantity > 0);
    const stats = data?.analytics;

    return (
        <FadeRise>
            <Page>
                <PageHeader
                    title="Уценка"
                    subtitle={
                        <>
                            Товар с подходящим сроком годности на складе «Уценка»
                            {data?.rules && ` — скидка ${Math.round(data.rules.discount_rate * 100)} %, снимаем с продажи за ${data.rules.months_to_delist} месяца до конца срока`}
                        </>
                    }
                    updatedAt={data?.generated_at ? timeOnly(data.generated_at) : undefined}
                    onRefresh={() => load(true)}
                    refreshing={loading}
                />

                {error && <ErrorState hint={error} onRetry={() => load(true)} />}

                {/* Первая загрузка: три дорожки-заглушки на месте будущих колонок,
                    чтобы страница не выглядела пустой, пока идёт запрос */}
                {loading && !data && !error && (
                    <div className="uc-board">
                        {LANES.map((lane) => (
                            <div key={lane.key} className="uc-col">
                                <div className="uc-col-head"><span>{lane.title}</span></div>
                                <Skeleton height={64} style={{ marginBottom: 9 }} />
                                <Skeleton height={64} />
                            </div>
                        ))}
                    </div>
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
                                                        <DiscountedCard position={position} />
                                                    </StaggerItem>
                                                ))}
                                            </Stagger>
                                        )}
                                    </section>
                                );
                            })}
                        </div>

                        {inStock.length === 0 && (
                            <EmptyState
                                title="На складе «Уценка» сейчас пусто"
                                hint="Позиции появятся здесь после того, как Лера проведёт техоперацию в МойСклад."
                            />
                        )}

                        {/* Итоги и порядок работы стоят рядом: оба блока справочные
                            и короткие, вместе помещаются в один экран */}
                        <div className="uc-footer">
                            {stats && (
                                <section className="uc-block">
                                    <StatGrid min={150}>
                                        <StatCard title="Уценено" value={units(stats.marked.quantity)}
                                            note={`себестоимость ${money(stats.marked.cost)}`} />
                                        <StatCard title="Продано" value={units(stats.sold.quantity)}
                                            note={`выручка ${money(stats.sold.revenue)}`} />
                                        <StatCard title="Списано" value={units(stats.written_off.quantity)}
                                            note={`потеряно ${money(stats.written_off.cost)}`} />
                                    </StatGrid>
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
                        </div>
                    </>
                )}
            </Page>
        </FadeRise>
    );
}
