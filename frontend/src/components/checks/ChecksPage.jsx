import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Loader2, ShieldCheck, PackageOpen, ChevronRight, CheckCircle, AlertCircle } from 'lucide-react';
import PropTypes from 'prop-types';
import { checksApi, plural, SEV, PENDING_RETURNS_HINT } from './checksShared';
import ScriptCard, { AccountBadge, StatusBadge } from './ScriptCard';
import CheckDetail from './CheckDetail';
import PendingReturnsDetail from './PendingReturnsDetail';
import InfoTip from './InfoTip';

// Порядок тем внутри аккаунта; скрипты без темы — в конец без заголовка
const TOPIC_ORDER = ['Себестоимость', 'Возвраты', 'Оплаты', 'Производство'];

/** Строка-индикатор «Возвраты в пути» — самостоятельный пункт в теме «Возвраты»:
 *  робот создаёт черновики, а этот пункт следит, сколько их ждёт товара и как долго. */
function PendingReturnsRow({ pending, onOpen }) {
    const { overdue = 0, warn_days = 30 } = pending;
    return (
        <div
            role="button"
            tabIndex={0}
            onClick={onOpen}
            onKeyDown={(e) => { if (e.key === 'Enter') onOpen(); }}
            style={{
                width: '100%', textAlign: 'left',
                background: 'var(--surface-card)', border: '1px solid var(--hairline)',
                borderRadius: 12, padding: '13px 16px', cursor: 'pointer',
                transition: 'background 0.15s, border-color 0.15s',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--surface-cream-strong)'; e.currentTarget.style.borderColor = 'var(--primary)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--surface-card)'; e.currentTarget.style.borderColor = 'var(--hairline)'; }}
        >
            <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 14.5, fontWeight: 600, color: 'var(--ink)', lineHeight: 1.3 }}>
                        <PackageOpen size={16} style={{ color: 'var(--muted)', flexShrink: 0 }} />
                        Возвраты в пути
                        <AccountBadge account="HorseBio" />
                        <InfoTip text={PENDING_RETURNS_HINT} width={300} />
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 3, lineHeight: 1.45 }}>
                        <div><b style={{ color: 'var(--body)', fontWeight: 600 }}>Что проверяем:</b> черновики возвратов не висят без товара дольше {warn_days} дней</div>
                        <div><b style={{ color: 'var(--body)', fontWeight: 600 }}>Как:</b> считаем возраст и сумму каждого непроведённого возврата</div>
                    </div>
                </div>
                {overdue > 0 ? (
                    <StatusBadge color={SEV.warning.color} icon={AlertCircle}>
                        {overdue} {plural(overdue, 'проблема', 'проблемы', 'проблем')}
                    </StatusBadge>
                ) : (
                    <StatusBadge color="var(--success)" icon={CheckCircle}>ОК</StatusBadge>
                )}
                <ChevronRight size={17} style={{ color: 'var(--muted-soft)', flexShrink: 0 }} />
            </div>
        </div>
    );
}
PendingReturnsRow.propTypes = { pending: PropTypes.object.isRequired, onOpen: PropTypes.func };

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

    // Группировка по темам (аккаунт — бейдж в строке, не секция)
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
                        {t.topic === 'Возвраты' && pendingReturns && (
                            <PendingReturnsRow
                                pending={pendingReturns}
                                onOpen={() => navigate('/checks/pending-returns')}
                            />
                        )}
                    </div>
                </section>
            ))}
        </div>
    );
}
