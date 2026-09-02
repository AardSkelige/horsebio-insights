import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ErrorState, Page, PageHeader, SectionLabel, Skeleton } from '../ui';
import { checksApi, PENDING_RETURNS_ID } from './checksShared';
import ScriptCard from './ScriptCard';
import CheckDetail from './CheckDetail';
import PendingReturnsDetail from './PendingReturnsDetail';

// Порядок тем внутри аккаунта; скрипты без темы — в конец без заголовка
const TOPIC_ORDER = ['Себестоимость', 'Возвраты', 'Оплаты', 'Производство'];


export default function ChecksPage() {
    const [scripts, setScripts] = useState(null);
    const [error, setError] = useState(null);
    const { scriptId } = useParams();
    const navigate = useNavigate();

    const load = useCallback(async () => {
        try {
            const res = await checksApi.overview();
            setScripts(res.scripts);
            setError(null);
        } catch (e) {
            setError(e.message);
        }
    }, []);

    useEffect(() => {
        load();
        const t = setInterval(load, 15000);
        return () => clearInterval(t);
    }, [load]);

    if (scriptId) {
        const script = (scripts || []).find((s) => s.id === scriptId);
        // idx === 0 — деталка открыта по прямой ссылке, «назад» из истории увёл бы из приложения
        const goBack = () => {
            if (window.history.state?.idx > 0) navigate(-1);
            else navigate('/checks', { replace: true });
        };
        const backLabel = 'Все проверки';
        // У «Возвратов в пути» своя деталка: плитки, лента возраста, группы по статусу
        if (scriptId === PENDING_RETURNS_ID) return <PendingReturnsDetail onBack={goBack} />;
        return <CheckDetail scriptId={scriptId} initial={script} onBack={goBack} backLabel={backLabel} />;
    }

    // Группировка по темам (аккаунт — бейдж в строке, не секция).
    const topics = [];
    (scripts || []).forEach((s) => {
        const topic = s.topic || '';
        let t = topics.find((x) => x.topic === topic);
        if (!t) { t = { topic, items: [] }; topics.push(t); }
        t.items.push(s);
    });
    topics.sort((a, b) => {
        const ia = TOPIC_ORDER.indexOf(a.topic), ib = TOPIC_ORDER.indexOf(b.topic);
        return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
    });

    return (
        <Page>
            <PageHeader
                title="Проверки"
                subtitle="Результаты автоматических проверок МойСклад, исключения и история запусков"
            />

            {error && <ErrorState hint={error} onRetry={load} />}

            {/* Первая загрузка: карточки-заглушки на месте будущего списка */}
            {scripts === null && !error && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {[0, 1, 2, 3].map((i) => <Skeleton key={i} height={58} />)}
                </div>
            )}

            {topics.map((t) => (
                <section key={t.topic || 'other'}>
                    {t.topic && <SectionLabel>{t.topic}</SectionLabel>}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                        {t.items.map((s) => (
                            <ScriptCard key={s.id} script={s} onOpen={(id) => navigate(`/checks/${id}`)} />
                        ))}
                    </div>
                </section>
            ))}
        </Page>
    );
}
