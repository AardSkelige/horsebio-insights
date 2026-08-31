import { useCallback, useEffect, useRef, useState } from 'react';
import { timeOnly } from '../../utils/formatters';
import { Download } from 'lucide-react';
import { Button, EmptyState, ErrorState, Page, PageHeader, Skeleton, StatCard, StatGrid } from '../ui';
import { FadeRise, Stagger, StaggerItem } from '../ui/motion';
import { SectionNotifications } from '../notifications';
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
    { key: 'selling', title: 'В продаже',       tone: 'ok',     states: ['ok'],                empty: 'Пусто' },
];

// Процесс живёт в трёх местах сразу, и без подсказки на экране приходится каждый
// раз вспоминать, кто где нажимает.
const FLOW = [
    ['Лера', 'Находит товар с подходящим сроком и проводит техоперацию в МойСклад — товар переезжает на склад «Уценка»'],
    ['Система', 'Позиция появляется здесь: цена, остаток и дата, до которой её можно продавать. Если «Годен до» в карточке не заполнено — придёт уведомление: без даты не посчитать, когда снимать'],
    ['Сергей', 'Жмёт «Файл для сайта» и загружает его в админке: Магазин → Импорт → CSV. Карточка заводится с фотографиями, ценой, остатком и текстом про уценку, но скрытой от покупателей'],
    ['Сергей', 'Проверяет карточку и переключает «Доступность товара на сайте» на «Доступен» — с этого момента товар продаётся'],
    ['Система', 'Здесь видно, что стоит на витрине: цена и остаток с сайта. Когда до конца срока остаётся два месяца, остаток разошёлся или товар раскуплен — приходит уведомление: в колокольчик и наверх этой страницы'],
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
                    actions={
                        inStock.length > 0 && (
                            <Button
                                as="a"
                                variant="ghost"
                                size="sm"
                                icon={Download}
                                href={discountedApi.csvUrl()}
                                title="Файл для импорта в админке сайта — на случай, когда обмен не применяет изменения"
                            >
                                Файл для сайта
                            </Button>
                        )
                    }
                    updatedAt={data?.generated_at ? timeOnly(data.generated_at) : undefined}
                    onRefresh={() => load(true)}
                    refreshing={loading}
                />

                {error && <ErrorState hint={error} onRetry={() => load(true)} />}

                {/* Что требует действия — выше доски: на доске это видно по
                    дорожкам, но не видно, что именно надо нажать */}
                <SectionNotifications source="discounted" />

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

                                <p className="uc-fallback">
                                    <strong>Перед импортом проверьте одну настройку.</strong> «Операция
                                    над товарами, не участвующими в импорте» должна стоять прочерком —
                                    любое другое значение удалит или скроет весь остальной каталог.
                                    Файл приводит витрину в соответствие со складом: обновляет остатки,
                                    заводит скрытыми карточки, которых на витрине ещё нет, и убирает
                                    с неё то, что пора снять по сроку или уже раскуплено.
                                </p>
                                <p className="uc-fallback">
                                    <strong>Почему через файл, а не автоматически.</strong> Обмен с сайтом
                                    работает в демо-режиме, и лимит на число загруженных предложений
                                    исчерпан: сайт отвечает «принято», но изменения молча не применяет.
                                    Пока не оплачена полная версия, публикация и обновление остатков идут
                                    через файл.
                                </p>
                            </section>
                        </div>
                    </>
                )}
            </Page>
        </FadeRise>
    );
}
