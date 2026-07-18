import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Loader2, ShieldCheck } from 'lucide-react';
import { checksApi } from './checksShared';
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
        if (scriptId === 'pending-returns') return <PendingReturnsDetail onBack={goBack} />;
        return <CheckDetail scriptId={scriptId} initial={script} onBack={goBack} />;
    }

    // Индикатор возвратов — из сводки последнего запуска хелс-чека;
    // встроен в карточку робота возвратов (horsebio_returns)
    const pendingReturns = (scripts || []).find((s) => s.is_health)?.summary?.pending_returns;

    // Группировка: аккаунт → тема (в порядке TOPIC_ORDER)
    const groups = [];
    (scripts || []).forEach((s) => {
        let g = groups.find((x) => x.account === s.account);
        if (!g) { g = { account: s.account, topics: [] }; groups.push(g); }
        const topic = s.topic || '';
        let t = g.topics.find((x) => x.topic === topic);
        if (!t) { t = { topic, items: [] }; g.topics.push(t); }
        t.items.push(s);
    });
    groups.forEach((g) => g.topics.sort((a, b) => {
        const ia = TOPIC_ORDER.indexOf(a.topic), ib = TOPIC_ORDER.indexOf(b.topic);
        return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
    }));

    return (
        <div style={{ maxWidth: 1100, margin: '0 auto' }}>
            <header style={{ marginBottom: 28 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <ShieldCheck size={26} style={{ color: 'var(--primary)' }} />
                    <h1 style={{ fontFamily: 'var(--serif)', fontSize: 30, fontWeight: 600, color: 'var(--ink)', margin: 0 }}>
                        Проверки
                    </h1>
                </div>
                <p style={{ color: 'var(--muted)', marginTop: 6, fontSize: 14 }}>
                    Результаты автоматических проверок МойСклад, исключения и история запусков
                </p>
            </header>

            {error && (
                <div style={{ color: 'var(--error)', background: 'var(--error-bg, rgba(198,69,69,0.08))', padding: 12, borderRadius: 10, marginBottom: 16 }}>
                    {error}
                </div>
            )}

            {scripts === null && !error && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--muted)', padding: 40, justifyContent: 'center' }}>
                    <Loader2 size={18} className="animate-spin" /> Загрузка…
                </div>
            )}

            {groups.map((g) => (
                <section key={g.account} style={{ marginBottom: 32 }}>
                    <h2 style={{
                        fontSize: 12, fontWeight: 700, letterSpacing: 0.6, textTransform: 'uppercase',
                        color: 'var(--muted)', marginBottom: 14,
                    }}>{g.account}</h2>
                    {g.topics.map((t) => (
                        <div key={t.topic || 'other'} style={{ marginBottom: 18 }}>
                            {t.topic && (
                                <h3 style={{
                                    fontSize: 11, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase',
                                    color: 'var(--muted-soft)', margin: '0 0 8px',
                                }}>{t.topic}</h3>
                            )}
                            <div style={{
                                display: 'grid', gap: 14,
                                gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                            }}>
                                {t.items.map((s) => (
                                    <ScriptCard
                                        key={s.id}
                                        script={s}
                                        onOpen={(id) => navigate(`/checks/${id}`)}
                                        pending={s.id === 'horsebio_returns' ? pendingReturns : undefined}
                                        onOpenPending={() => navigate('/checks/pending-returns')}
                                    />
                                ))}
                            </div>
                        </div>
                    ))}
                </section>
            ))}
        </div>
    );
}
