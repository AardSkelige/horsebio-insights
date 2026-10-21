import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { Button, EmptyState, ErrorState, Notice, Page, PageHeader, Skeleton } from '../../ui';
import { FadeRise } from '../../ui/motion';
import { useNotifications } from '../../../contexts/NotificationsContext';
import { rawMaterialsApi } from '../../../api/rawMaterialsApi';
import { formatDate, pluralWith } from '../../../utils/formatters';
import { formatQuantity } from '../format';
import { complete, sameAs, saved } from './draft';
import LineForm from './LineForm';
import useReceipts from './useReceipts';
import '../RawMaterialsPage.css';
import './receipt.css';

export default function ReceiptPage() {
    const { id } = useParams();
    const { data, setData, error, reload } = useReceipts();
    const { reload: reloadNotifications } = useNotifications();
    const [drafts, setDrafts] = useState({});
    const [saving, setSaving] = useState(false);
    const [saveError, setSaveError] = useState(null);

    const receipt = data?.items.find((item) => String(item.id) === id);
    const raw = useMemo(() => (receipt?.lines || []).filter((line) => !line.tara), [receipt]);
    const tara = useMemo(() => (receipt?.lines || []).filter((line) => line.tara), [receipt]);

    useEffect(() => {
        setDrafts((current) => {
            const next = { ...current };
            raw.forEach((line) => { if (!next[line.id]) next[line.id] = saved(line); });
            return next;
        });
    }, [raw]);

    const ready = raw.filter((line) => drafts[line.id] && complete(drafts[line.id]) && !(line.filled && sameAs(drafts[line.id], saved(line))));

    const save = async () => {
        setSaving(true);
        setSaveError(null);
        for (const line of ready) {
            const draft = drafts[line.id];
            try {
                const fresh = await rawMaterialsApi.fillReceiptLine(line.id, {
                    series: draft.series.trim(), expiry_date: draft.expiry_date, manufacturer: draft.manufacturer.trim(),
                });
                setData(fresh);
                const stored = fresh.items.find((r) => r.id === receipt.id)?.lines.find((l) => l.id === line.id);
                if (stored) setDrafts((current) => ({ ...current, [line.id]: saved(stored) }));
            } catch (err) {
                setSaveError(`${line.name}: ${err.message || 'не удалось сохранить'}`);
                break;
            }
        }
        setSaving(false);
        reloadNotifications();
    };

    return (
        <Page>
            <Link to="/raw-materials/receipts" className="slot-page__back">
                <ArrowLeft size={14} aria-hidden="true" />
                Все приёмки
            </Link>
            <PageHeader
                title={receipt ? `Приёмка ${receipt.name}` : 'Приёмка'}
                subtitle={receipt ? `${formatDate(receipt.moment)} · ${receipt.agent}` : undefined}
            />

            {error && <ErrorState hint={error} onRetry={() => reload()} />}
            {!error && !data && <Skeleton height={220} style={{ borderRadius: 12 }} />}
            {data && !receipt && <EmptyState title="Такой приёмки нет" hint="Вернитесь к списку приёмок" />}

            {receipt && (
                <FadeRise className="receipt">
                    {raw.map((line) => (
                        <LineForm
                            key={line.id}
                            line={line}
                            draft={drafts[line.id] || saved(line)}
                            onChange={(draft) => setDrafts((current) => ({ ...current, [line.id]: draft }))}
                        />
                    ))}
                    {tara.length > 0 && (
                        <div className="receipt__tara">
                            <span className="stock__label">Тара · серия не нужна</span>
                            {tara.map((line) => (
                                <span key={line.id} className="receipt__tara-line">
                                    <span>{line.name}</span>
                                    <span>{formatQuantity(line.quantity, line.uom)}</span>
                                </span>
                            ))}
                        </div>
                    )}
                    {saveError && <Notice tone="error">{saveError}</Notice>}
                    {raw.length > 0 && (
                        <div className="receipt__save">
                            <Button variant="primary" block loading={saving} loadingLabel="Сохраняем…" disabled={!ready.length} onClick={save}>
                                {ready.length ? `Сохранить ${pluralWith(ready.length, 'серию', 'серии', 'серий')}` : 'Впишите серию и срок'}
                            </Button>
                        </div>
                    )}
                </FadeRise>
            )}

        </Page>
    );
}
