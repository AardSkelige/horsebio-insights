import { useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Plus } from 'lucide-react';
import { Button, Card, EmptyState, ErrorState, Page, PageHeader, Skeleton } from '../../ui';
import { FadeRise } from '../../ui/motion';
import MaterialRow from '../MaterialRow';
import useStock from '../useStock';
import BackLink from './BackLink';
import IssueCart from './IssueCart';
import ScanButton from './ScanButton';
import TakeSheet from './TakeSheet';
import useIssueCart from './useIssueCart';
import '../RawMaterialsPage.css';
import './issue.css';

export default function SlotPage() {
    const { slot } = useParams();
    const { data, loading, error, reload } = useStock();
    const cart = useIssueCart();
    const [taking, setTaking] = useState(null);

    const items = useMemo(() => (data?.items || []).filter((i) => i.slot === slot || i.slots?.includes(slot)), [data, slot]);
    const known = data?.slots?.includes(slot);

    return (
        <Page className="slot-page">
            <BackLink />
            <PageHeader
                title={`Ячейка ${slot}`}
                subtitle="Шатл · выдача на производство"
                actions={<ScanButton slots={data?.slots || []} variant="soft" />}
            />

            {error && <ErrorState hint={error} onRetry={() => reload()} />}
            {!error && loading && (
                <div aria-busy="true">
                    {[...Array(3)].map((_, i) => <Skeleton key={i} height={72} style={{ borderRadius: 12, marginBottom: 10 }} />)}
                </div>
            )}

            {!error && !loading && (
                items.length > 0 ? (
                    <FadeRise>
                        <Card className="slot-page__card">
                            <ul className="raw-materials__items">
                                {items.map((item) => (
                                    <MaterialRow
                                        key={item.id}
                                        item={item}
                                        action={(
                                            <Button
                                                variant="subtle"
                                                tone="accent"
                                                size="sm"
                                                icon={Plus}
                                                aria-label={`Взять ${item.name}`}
                                                onClick={() => setTaking(item)}
                                            >
                                                Взять
                                            </Button>
                                        )}
                                    />
                                ))}
                            </ul>
                        </Card>
                    </FadeRise>
                ) : (
                    <EmptyState
                        title={known ? 'Ячейка пуста' : 'Такой ячейки нет'}
                        hint={known ? 'По МойСклад здесь ничего не лежит' : 'Проверьте QR или выберите ячейку на странице склада'}
                    />
                )
            )}

            <TakeSheet item={taking} onClose={() => setTaking(null)} onAdd={(line) => cart.add({ ...line, slot })} taken={cart.taken} />
            <IssueCart cart={cart} onIssued={() => reload()} />
        </Page>
    );
}
