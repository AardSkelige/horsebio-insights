import { useCallback, useEffect, useMemo, useState } from 'react';
import { EmptyState, ErrorState, Page, PageHeader, SearchInput, Segmented, Select, Skeleton, Toolbar } from '../ui';
import { FadeRise } from '../ui/motion';
import { rawMaterialsApi } from '../../api/rawMaterialsApi';
import { formatDateTimeShort } from '../../utils/formatters';
import SlotCard from './SlotCard';
import { TARA_GROUP, groupBySlot, matches } from './format';

const KINDS = [
    { value: 'all', label: 'Все' },
    { value: 'raw', label: 'Сырьё' },
    { value: 'tara', label: 'Тара' },
];

const ofKind = (item, kind) => kind === 'all' || (kind === 'tara') === (item.group === TARA_GROUP);
import './RawMaterialsPage.css';

export default function RawMaterialsPage() {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState(null);
    const [search, setSearch] = useState('');
    const [slot, setSlot] = useState('');
    const [kind, setKind] = useState('all');

    useEffect(() => {
        const controller = new AbortController();
        rawMaterialsApi.list(controller.signal)
            .then(setData)
            .catch((err) => { if (err.name !== 'AbortError') setError(err.message || 'Не удалось загрузить склад'); })
            .finally(() => { if (!controller.signal.aborted) setLoading(false); });
        return () => controller.abort();
    }, []);

    const refresh = useCallback(() => {
        setRefreshing(true);
        setError(null);
        rawMaterialsApi.refresh()
            .then(setData)
            .catch((err) => setError(err.message || 'Не удалось сверить с МойСклад'))
            .finally(() => setRefreshing(false));
    }, []);

    const items = useMemo(() => data?.items || [], [data]);
    const slots = useMemo(() => [...new Set(items.map((i) => i.slot).filter(Boolean))].sort(), [items]);
    const visible = useMemo(
        () => items.filter((i) => ofKind(i, kind) && (!slot || i.slot === slot) && matches(i, search)),
        [items, kind, slot, search],
    );
    const groups = useMemo(() => groupBySlot(visible), [visible]);

    return (
        <Page>
            <PageHeader
                title="Склад сырья"
                subtitle="Шатл: остатки и ячейки из МойСклад, серии и сроки годности"
                updatedAt={data?.synced_at ? formatDateTimeShort(data.synced_at) : undefined}
                onRefresh={refresh}
                refreshing={refreshing || loading}
            />

            <Toolbar>
                <SearchInput value={search} onChange={setSearch} placeholder="Сырьё, серия или ячейка" />
                <div className="raw-materials__filters">
                    <Select value={slot} onChange={(e) => setSlot(e.target.value)} placeholder="Все ячейки" options={slots} />
                    <Segmented options={KINDS} value={kind} onChange={setKind} layoutId="raw-materials-kind" />
                </div>
            </Toolbar>

            {error && <ErrorState hint={error} onRetry={refresh} />}
            {!error && loading && (
                <div className="raw-materials__shelves" aria-busy="true">
                    {[...Array(6)].map((_, i) => <Skeleton key={i} height={140} style={{ borderRadius: 12, marginBottom: 12 }} />)}
                </div>
            )}

            {!error && !loading && (
                <FadeRise>
                    <div className="raw-materials__shelves">
                        {groups.map((group) => <SlotCard key={group.slot} slot={group.slot} items={group.items} />)}
                    </div>
                    {visible.length === 0 && (
                        <EmptyState
                            title={items.length ? 'Ничего не найдено' : 'Склад пуст'}
                            hint={items.length ? 'Ищет по названию, серии и ячейке' : 'Нажмите «Обновить», чтобы сверить с МойСклад'}
                        />
                    )}
                </FadeRise>
            )}
        </Page>
    );
}
