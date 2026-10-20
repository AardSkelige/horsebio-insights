import { useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { ErrorState, Page, PageHeader } from '../../ui';
import { FadeRise } from '../../ui/motion';
import { useIsMobile } from '../../../hooks/useIsMobile';
import StockList from '../StockList';
import useStock from '../useStock';
import BackLink from './BackLink';
import IssueCart from './IssueCart';
import MaterialSheet from './MaterialSheet';
import ScanButton from './ScanButton';
import useIssueCart from './useIssueCart';
import '../RawMaterialsPage.css';
import './issue.css';

export default function SlotPage() {
    const { slot } = useParams();
    const isMobile = useIsMobile();
    const { data, loading, error, reload } = useStock();
    const cart = useIssueCart();
    const [opened, setOpened] = useState(null);

    const items = useMemo(
        () => (data?.items || [])
            .filter((i) => i.slot === slot || i.slots?.includes(slot))
            .sort((a, b) => a.name.localeCompare(b.name, 'ru')),
        [data, slot],
    );
    const known = data?.slots?.includes(slot);
    const scan = <ScanButton slots={data?.slots || []} variant={isMobile ? 'primary' : 'soft'} block={isMobile} />;

    return (
        <Page className="stock-page slot-page">
            <BackLink />
            <PageHeader
                title={`Ячейка ${slot}`}
                subtitle="Шатл · нажмите на сырьё, чтобы взять"
                actions={isMobile ? undefined : scan}
            />
            {isMobile && scan}

            {error && <ErrorState hint={error} onRetry={() => reload()} />}
            {!error && (
                <FadeRise>
                    <StockList
                        items={items}
                        loading={loading}
                        single
                        onOpen={setOpened}
                        emptyText={known ? 'Ячейка пуста: по МойСклад здесь ничего не лежит' : 'Такой ячейки нет: проверьте QR или найдите сырьё на странице склада'}
                    />
                </FadeRise>
            )}

            <MaterialSheet
                item={opened}
                onClose={() => setOpened(null)}
                onAdd={(line) => cart.add({ ...line, slot })}
                taken={cart.taken}
            />
            <IssueCart cart={cart} onIssued={() => reload()} />
        </Page>
    );
}
