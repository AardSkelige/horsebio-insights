import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { History, PackagePlus, QrCode } from 'lucide-react';
import { ErrorState, Page, PageHeader, SearchInput, Segmented } from '../ui';
import { FadeRise } from '../ui/motion';
import { SectionNotifications } from '../notifications';
import { useIsMobile } from '../../hooks/useIsMobile';
import { formatDateTimeShort } from '../../utils/formatters';
import StockList from './StockList';
import StockTabs from './StockTabs';
import useStock from './useStock';
import IssueCart from './issue/IssueCart';
import MaterialSheet from './issue/MaterialSheet';
import ScanButton from './issue/ScanButton';
import useIssueCart from './issue/useIssueCart';
import { TARA_GROUP, matches } from './format';
import './RawMaterialsPage.css';

const KINDS = [
    { value: 'all', label: 'Все' },
    { value: 'raw', label: 'Сырьё' },
    { value: 'tara', label: 'Тара' },
];

const ofKind = (item, kind) => kind === 'all' || (kind === 'tara') === (item.group === TARA_GROUP);

export default function RawMaterialsPage() {
    const navigate = useNavigate();
    const isMobile = useIsMobile();
    const { data, loading, refreshing, error, refresh, reload } = useStock();
    const cart = useIssueCart();
    const [search, setSearch] = useState('');
    const [kind, setKind] = useState('all');
    const [opened, setOpened] = useState(null);

    const visible = useMemo(
        () => (data?.items || []).filter((i) => ofKind(i, kind) && matches(i, search)),
        [data, kind, search],
    );

    const waiting = data?.receipts_waiting || 0;
    const tiles = [
        { label: 'Приёмка', icon: PackagePlus, to: '/raw-materials/receipts', badge: waiting },
        { label: 'Выдачи', icon: History, to: '/raw-materials/issues' },
        { label: 'QR ячеек', icon: QrCode, to: '/raw-materials/qr' },
    ];

    return (
        <Page className="stock-page">
            <PageHeader
                title="Склад сырья"
                subtitle="Шатл: остатки и ячейки из МойСклад, серии и сроки годности"
                updatedAt={data?.synced_at ? formatDateTimeShort(data.synced_at) : undefined}
                onRefresh={refresh}
                refreshing={refreshing || loading}
                actions={isMobile ? undefined : <ScanButton slots={data?.slots || []} />}
            />
            <StockTabs />

            {isMobile && (
                <div className="stock-page__mobile-actions">
                    <ScanButton slots={data?.slots || []} block />
                    <div className="stock-page__tiles">
                        {tiles.map(({ label, icon: Icon, to, badge }) => (
                            <button key={to} type="button" className="stock-page__tile" onClick={() => navigate(to)}>
                                <Icon size={20} aria-hidden="true" />
                                {label}
                                {badge > 0 && <span className="stock-page__badge">{badge}</span>}
                            </button>
                        ))}
                    </div>
                </div>
            )}

            <SectionNotifications source="raw-materials" />

            <div className="stock-page__filters">
                <SearchInput value={search} onChange={setSearch} placeholder="Сырьё, серия или ячейка" />
                <Segmented options={KINDS} value={kind} onChange={setKind} layoutId="raw-materials-kind" />
            </div>

            {error && <ErrorState hint={error} onRetry={refresh} />}
            {!error && (
                <FadeRise>
                    <StockList
                        items={visible}
                        loading={loading}
                        onOpen={setOpened}
                        emptyText={data?.items?.length ? 'Ничего не найдено: поиск идёт по названию, серии и ячейке' : 'Склад пуст. Нажмите «Обновить», чтобы сверить с МойСклад'}
                    />
                </FadeRise>
            )}

            <MaterialSheet item={opened} onClose={() => setOpened(null)} onAdd={cart.add} taken={cart.taken} />
            <IssueCart cart={cart} onIssued={() => reload()} />
        </Page>
    );
}
