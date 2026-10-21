import { useMemo, useState } from 'react';
import { Download, ListX } from 'lucide-react';
import { Button, Card, EmptyState, ErrorState, Notice, Page, PageHeader, SearchInput, Segmented, StatCard, StatGrid, Toolbar } from '../ui';
import { FadeRise } from '../ui/motion';
import { useIsMobile } from '../../hooks/useIsMobile';
import { formatDateTimeShort } from '../../utils/formatters';
import { matchesQuery, parseQuery, searchIndex } from '../fbo-stock/search';
import ExclusionsDrawer from './ExclusionsDrawer';
import PlanCards from './PlanCards';
import PlanTable from './PlanTable';
import { FILTERS, monthIn, qty, wbSource } from './format';
import useProductionPlan from './useProductionPlan';
import './ProductionPlanPage.css';

export default function ProductionPlanPage() {
    const { data, loading, refreshing, exporting, error, reload, refresh, exportExcel, toggleGreen } = useProductionPlan();
    const [filter, setFilter] = useState('todo');
    const [search, setSearch] = useState('');
    const [open, setOpen] = useState(null);
    const [exclusionsOpen, setExclusionsOpen] = useState(false);
    const isMobile = useIsMobile();

    const allRows = useMemo(() => data?.rows || [], [data]);
    const rows = useMemo(() => {
        const parts = parseQuery(search);
        const { test } = FILTERS.find((f) => f.value === filter);
        return allRows.filter((row) => test(row) && matchesQuery(searchIndex(row), parts));
    }, [allRows, filter, search]);

    const toProduce = allRows.filter((row) => row.produce > 0);
    const missingOzon = (data?.months || []).filter((month) => !data.ozon_months.includes(month));
    const toggleOpen = (article) => setOpen((prev) => (prev === article ? null : article));
    const emptyText = search ? 'Ничего не найдено' : 'Здесь пусто';
    const listProps = { rows, months: data?.months || [], loading, open, onOpen: toggleOpen, onToggleGreen: toggleGreen };

    return (
        <Page>
            <PageHeader
                title="Производственный план"
                subtitle="Что и сколько произвести, чтобы товара хватило на 2 месяца"
                updatedAt={data?.stock_at ? formatDateTimeShort(data.stock_at) : undefined}
                onRefresh={refresh}
                refreshing={refreshing}
                actions={(
                    <>
                        <Button variant="secondary" icon={ListX} onClick={() => setExclusionsOpen(true)}>Исключения</Button>
                        <Button variant="primary" icon={Download} loading={exporting} disabled={!data} onClick={exportExcel}>Скачать Excel</Button>
                    </>
                )}
            />

            <Card tone="quiet" className="plan-note">
                <b>Как считается.</b> Продажи за 3 полных месяца по всем каналам, отменённые заказы не считаются. «Обычно в месяц» — середина из трёх месяцев,
                поэтому один всплеск не раздувает план. Произвести = нужно на 2 месяца − можно взять со склада − уже в производстве.
                Ozon — все продажи, вместе со складами Ozon. {wbSource(data?.months, data?.wb_months)} Яндекс — то, что мы ему отгрузили.
            </Card>

            {missingOzon.length > 0 && (
                <Notice tone="warning">Нет продаж Ozon в {missingOzon.map(monthIn).join(', ')}. Нажмите «Обновить».</Notice>
            )}
            {error && <ErrorState hint={error} onRetry={() => reload()} />}

            <StatGrid loading={loading} count={4}>
                <StatCard title="К производству" hint="Сколько товаров нужно произвести, чтобы хватило на 2 месяца" value={`${toProduce.length} позиций`} />
                <StatCard title="Всего произвести" hint="Сумма колонки «Произвести» по всем товарам" value={`${qty(toProduce.reduce((sum, row) => sum + row.produce, 0))} шт`} />
                <StatCard title="Срочно — меньше месяца" hint="Товары, которых на складе хватит меньше чем на 30 дней" value={allRows.filter((row) => row.status === 'urgent').length} />
                <StatCard title="Всего в плане" hint="Товары с продажами за 3 месяца, кроме исключений" value={allRows.length} />
            </StatGrid>

            <Toolbar className="plan-toolbar">
                <SearchInput value={search} onChange={setSearch} placeholder="Поиск: хондрофит 500, 11-36" />
                <Segmented options={FILTERS} value={filter} onChange={setFilter} layoutId="plan-filter" />
            </Toolbar>

            <FadeRise>
                {isMobile ? <PlanCards {...listProps} /> : <PlanTable {...listProps} emptyText={emptyText} />}
                {isMobile && !loading && rows.length === 0 && <EmptyState title={emptyText} />}
            </FadeRise>

            <ExclusionsDrawer open={exclusionsOpen} onClose={() => setExclusionsOpen(false)} onChanged={() => reload()} />
        </Page>
    );
}
