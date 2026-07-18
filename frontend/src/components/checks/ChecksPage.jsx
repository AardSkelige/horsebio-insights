import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Loader2, ShieldCheck } from 'lucide-react';
import { checksApi } from './checksShared';
import ScriptCard from './ScriptCard';
import CheckDetail from './CheckDetail';
import PendingReturnsCard from './PendingReturnsCard';
import PendingReturnsDetail from './PendingReturnsDetail';

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

    // Индикатор возвратов — из сводки последнего запуска хелс-чека
    const pendingReturns = (scripts || []).find((s) => s.is_health)?.summary?.pending_returns;

    // Группировка по аккаунтам с сохранением порядка появления
    const groups = [];
    (scripts || []).forEach((s) => {
        let g = groups.find((x) => x.account === s.account);
        if (!g) { g = { account: s.account, items: [] }; groups.push(g); }
        g.items.push(s);
    });

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

            <PendingReturnsCard pending={pendingReturns} onOpen={() => navigate('/checks/pending-returns')} />

            {groups.map((g) => (
                <section key={g.account} style={{ marginBottom: 28 }}>
                    <h2 style={{
                        fontSize: 12, fontWeight: 700, letterSpacing: 0.6, textTransform: 'uppercase',
                        color: 'var(--muted)', marginBottom: 12,
                    }}>{g.account}</h2>
                    <div style={{
                        display: 'grid', gap: 14,
                        gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                    }}>
                        {g.items.map((s) => (
                            <ScriptCard key={s.id} script={s} onOpen={(id) => navigate(`/checks/${id}`)} />
                        ))}
                    </div>
                </section>
            ))}
        </div>
    );
}
