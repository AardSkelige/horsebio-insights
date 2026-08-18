import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import { Loader2, ShieldCheck } from 'lucide-react';
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
    const location = useLocation();

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
        // Открыто из ЛК (StarPony) — помечено state.from; «назад» ведёт в кабинет
        const fromProfile = location.state?.from === 'profile';
        // idx === 0 — деталка открыта по прямой ссылке, «назад» из истории увёл бы из приложения
        const goBack = () => {
            if (fromProfile) navigate('/profile');
            else if (window.history.state?.idx > 0) navigate(-1);
            else navigate('/checks', { replace: true });
        };
        const backLabel = fromProfile ? 'Личный кабинет' : 'Все проверки';
        // У «Возвратов в пути» своя деталка: плитки, лента возраста, группы по статусу
        if (scriptId === PENDING_RETURNS_ID) return <PendingReturnsDetail onBack={goBack} />;
        return <CheckDetail scriptId={scriptId} initial={script} onBack={goBack} backLabel={backLabel} />;
    }

    // Группировка по темам (аккаунт — бейдж в строке, не секция).
    // StarPony на сетке проверок не показываем — он виден только в личном кабинете
    // суперпользователя. При этом сам скрипт остаётся в списке scripts, чтобы
    // деталь по прямой ссылке /checks/<id> получала свои данные (name, summary…).
    const topics = [];
    (scripts || []).forEach((s) => {
        if (s.account === 'StarPony') return;
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

            {topics.map((t) => (
                <section key={t.topic || 'other'} style={{ marginBottom: 24 }}>
                    {t.topic && (
                        <h2 style={{
                            fontSize: 12, fontWeight: 700, letterSpacing: 0.6, textTransform: 'uppercase',
                            color: 'var(--muted)', marginBottom: 10,
                        }}>{t.topic}</h2>
                    )}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                        {t.items.map((s) => (
                            <ScriptCard key={s.id} script={s} onOpen={(id) => navigate(`/checks/${id}`)} />
                        ))}
                    </div>
                </section>
            ))}
        </div>
    );
}
