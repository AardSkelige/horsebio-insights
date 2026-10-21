import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import { Badge, EmptyState, ErrorState, Notice, Page, PageHeader, Skeleton } from '../../ui';
import { Stagger, StaggerItem } from '../../ui/motion';
import { formatDate } from '../../../utils/formatters';
import StockTabs from '../StockTabs';
import BackLink from '../issue/BackLink';
import { formatQuantity } from '../format';
import { receiptStatus } from './status';
import useReceipts from './useReceipts';
import '../RawMaterialsPage.css';
import './receipt.css';

export default function ReceiptsPage() {
    const { data, error, reload } = useReceipts();

    return (
        <Page>
            <BackLink mobileOnly />
            <PageHeader title="Приёмка" subtitle="Приёмки на Шатл из МойСклад. Впишите серию и срок с мешка" />
            <StockTabs />

            {error && <ErrorState hint={error} onRetry={() => reload()} />}
            {data?.stale && <Notice tone="warning">МойСклад не ответил, показаны приёмки, загруженные раньше</Notice>}
            {!error && !data && [...Array(3)].map((_, i) => <Skeleton key={i} height={110} style={{ borderRadius: 12 }} />)}
            {data?.items.length === 0 && (
                <EmptyState title="Новых приёмок нет" hint="Когда Вика проведёт приёмку на Шатл в МойСклад, она появится здесь" />
            )}
            {data?.items.length > 0 && (
                <Stagger className="receipts">
                    {data.items.map((receipt) => {
                        const status = receiptStatus(receipt);
                        return (
                            <StaggerItem key={receipt.id}>
                                <Link to={`/raw-materials/receipts/${receipt.id}`} className="receipts__card">
                                    <span className="receipts__head">
                                        <span className="receipts__number">№ {receipt.name}</span>
                                        <span className="receipts__date">{formatDate(receipt.moment)}</span>
                                        <Badge tone={status.tone}>{status.label}</Badge>
                                        <ChevronRight size={18} className="shelf__chevron" aria-hidden="true" />
                                    </span>
                                    <span className="receipts__agent">{receipt.agent}</span>
                                    <span className="receipts__items">
                                        {receipt.lines.map((line) => `${line.name} ${formatQuantity(line.quantity, line.uom)}`).join(', ')}
                                    </span>
                                </Link>
                            </StaggerItem>
                        );
                    })}
                </Stagger>
            )}
        </Page>
    );
}
