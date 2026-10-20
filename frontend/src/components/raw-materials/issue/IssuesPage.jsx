import { useEffect, useState } from 'react';
import { ExternalLink } from 'lucide-react';
import { Button, Card, EmptyState, ErrorState, Page, PageHeader, Skeleton } from '../../ui';
import { Stagger, StaggerItem } from '../../ui/motion';
import { rawMaterialsApi } from '../../../api/rawMaterialsApi';
import { formatDateTimeShort } from '../../../utils/formatters';
import BackLink from './BackLink';
import IssueLine from './IssueLine';
import './issue.css';

export default function IssuesPage() {
    const [items, setItems] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
        const controller = new AbortController();
        rawMaterialsApi.issues(controller.signal)
            .then((data) => setItems(data.items))
            .catch((err) => { if (err.name !== 'AbortError') setError(err.message || 'Не удалось загрузить журнал'); });
        return () => controller.abort();
    }, []);

    return (
        <Page>
            <BackLink />
            <PageHeader title="Журнал выдач" subtitle="Перемещения с Шатла на производство, созданные из Insights" />

            {error && <ErrorState hint={error} />}
            {!error && !items && (
                <div aria-busy="true">
                    {[...Array(3)].map((_, i) => <Skeleton key={i} height={120} style={{ borderRadius: 12, marginBottom: 12 }} />)}
                </div>
            )}
            {items?.length === 0 && <EmptyState title="Выдач пока не было" hint="Отсканируйте QR ячейки, чтобы выдать сырьё" />}
            {items?.length > 0 && (
                <Stagger className="issues">
                    {items.map((issue) => (
                        <StaggerItem key={issue.id}>
                            <Card className="issues__card">
                                <div className="issues__head">
                                    <div className="issues__title">
                                        <span className="issues__number">№ {issue.moysklad_name}</span>
                                        <span className="issues__meta">{formatDateTimeShort(issue.created_at)} · {issue.created_by}</span>
                                    </div>
                                    <Button as="a" variant="link" size="sm" icon={ExternalLink} href={issue.moysklad_url} target="_blank" rel="noreferrer">
                                        МойСклад
                                    </Button>
                                </div>
                                <ul className="issue-lines">
                                    {issue.lines.map((line) => <IssueLine key={line.id} line={line} />)}
                                </ul>
                            </Card>
                        </StaggerItem>
                    ))}
                </Stagger>
            )}
        </Page>
    );
}
