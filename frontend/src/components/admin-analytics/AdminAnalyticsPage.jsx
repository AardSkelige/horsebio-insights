import { useEffect, useState } from 'react';
import { Activity, Users, CalendarDays, TrendingUp } from 'lucide-react';
import { authApi } from '../../api/authApi';

const sectionLabel = {
    fontSize: 11, fontWeight: 500,
    letterSpacing: '0.1em', textTransform: 'uppercase',
    color: 'var(--muted)', whiteSpace: 'nowrap',
};

const card = {
    backgroundColor: 'var(--surface-card)',
    borderRadius: 12,
    padding: 20,
};

const MONTH_NAMES = [
    '', 'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
    'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
];

const formatMonth = (ym) => {
    if (!ym) return '';
    const [year, month] = ym.split('-').map(Number);
    return `${MONTH_NAMES[month]} ${year}`;
};

const formatMinutes = (minutes) => {
    if (!minutes) return '0';
    if (minutes < 60) return `${minutes} мин`;
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return m > 0 ? `${h} ч ${m} м` : `${h} ч`;
};

const formatDateTime = (value) => {
    if (!value) return '—';
    return new Intl.DateTimeFormat('ru-RU', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
    }).format(new Date(value));
};

const AdminAnalyticsPage = () => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [selectedMonth, setSelectedMonth] = useState('');
    const [isMobile, setIsMobile] = useState(() => window.innerWidth < 768);

    useEffect(() => {
        const handler = () => setIsMobile(window.innerWidth < 768);
        window.addEventListener('resize', handler);
        return () => window.removeEventListener('resize', handler);
    }, []);

    useEffect(() => {
        const ctrl = new AbortController();
        setLoading(true);
        authApi.adminAnalytics(ctrl.signal, selectedMonth)
            .then(d => { if (d.status === 'success') setData(d.data); })
            .catch(() => {})
            .finally(() => setLoading(false));
        return () => ctrl.abort();
    }, [selectedMonth]);

    if (!data && loading) {
        return (
            <div style={{ color: 'var(--muted)', fontSize: 13, padding: 40, textAlign: 'center' }}>
                Загрузка...
            </div>
        );
    }

    if (!data) return null;

    const maxVisits = data.topPages[0]?.visits || 1;

    const summaryItems = [
        { label: 'Всего пользователей', value: data.totalUsers,    icon: Users },
        { label: 'Активны за 7 дней',   value: data.active7d,       icon: Activity },
        { label: 'Активны за 30 дней',  value: data.active30d,      icon: TrendingUp },
        { label: 'Сессий за период',    value: data.sessionsPeriod, icon: CalendarDays },
    ];

    return (
        <div style={{ color: 'var(--ink)', maxWidth: 1180, margin: '0 auto' }}>

            {/* Header */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 18, flexWrap: 'wrap' }}>
                <span style={sectionLabel}>Аналитика системы</span>
                <div style={{ flex: 1, height: 1, backgroundColor: 'var(--hairline)', minWidth: 20 }} />
                {data.availableMonths.length > 0 && (
                    <select
                        value={selectedMonth || data.period}
                        onChange={e => setSelectedMonth(e.target.value)}
                        style={{
                            fontFamily: 'var(--sans)', fontSize: 13,
                            color: 'var(--ink)', backgroundColor: 'var(--surface-card)',
                            border: '1px solid var(--hairline)', borderRadius: 8,
                            padding: '5px 10px', cursor: 'pointer', outline: 'none',
                        }}
                    >
                        {data.availableMonths.map(m => (
                            <option key={m} value={m}>{formatMonth(m)}</option>
                        ))}
                    </select>
                )}
            </div>

            {/* Summary cards */}
            <div style={{
                display: 'grid',
                gridTemplateColumns: isMobile ? 'repeat(2, 1fr)' : 'repeat(4, 1fr)',
                gap: 12, marginBottom: 12,
            }}>
                {summaryItems.map(({ label, value, icon: Icon }) => (
                    <div key={label} style={card}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                            <Icon size={14} color="var(--primary)" />
                            <span style={{ ...sectionLabel, whiteSpace: 'normal', lineHeight: 1.3 }}>{label}</span>
                        </div>
                        <div style={{
                            fontFamily: 'var(--serif)', fontSize: isMobile ? 28 : 36, fontWeight: 400,
                            letterSpacing: '-0.025em', lineHeight: 1, color: 'var(--ink)',
                            fontVariantNumeric: 'lining-nums', fontFeatureSettings: '"lnum" 1',
                        }}>
                            {loading ? '…' : value}
                        </div>
                    </div>
                ))}
            </div>

            {/* Main grid */}
            <div style={{
                display: 'grid',
                gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr',
                gap: 12, alignItems: 'start',
            }}>

                {/* Top pages */}
                <section style={card}>
                    <div style={{ marginBottom: 20 }}>
                        <span style={sectionLabel}>Топ страниц — {formatMonth(data.period)}</span>
                    </div>
                    {data.topPages.length === 0 ? (
                        <div style={{ color: 'var(--muted)', fontSize: 13, fontStyle: 'italic', padding: '20px 0', textAlign: 'center' }}>
                            Нет данных за этот период
                        </div>
                    ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                            {data.topPages.map((p, i) => (
                                <div key={p.page_path}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6, gap: 8 }}>
                                        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, minWidth: 0 }}>
                                            <span style={{
                                                fontFamily: 'var(--sans)', fontSize: 12, fontWeight: 500,
                                                color: i === 0 ? 'var(--primary)' : 'var(--muted-soft)',
                                                minWidth: 18, lineHeight: 1, flexShrink: 0,
                                            }}>
                                                {i + 1}
                                            </span>
                                            <span style={{ fontSize: 13, color: 'var(--ink)', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                                {p.page_name}
                                            </span>
                                        </div>
                                        <span style={{ fontSize: 12, color: 'var(--muted)', flexShrink: 0, textAlign: 'right' }}>
                                            {p.visits} {p.visits === 1 ? 'визит' : p.visits < 5 ? 'визита' : 'визитов'}
                                            {!isMobile && <>{' · '}{p.unique_users} {p.unique_users === 1 ? 'юзер' : 'юзера'}</>}
                                        </span>
                                    </div>
                                    <div style={{ height: 3, borderRadius: 2, backgroundColor: 'var(--hairline)' }}>
                                        <div style={{
                                            height: '100%', borderRadius: 2,
                                            backgroundColor: i === 0 ? 'var(--primary)' : 'var(--muted-soft)',
                                            opacity: i === 0 ? 1 : 0.5 + (0.5 * (data.topPages.length - i) / data.topPages.length),
                                            width: `${Math.round((p.visits / maxVisits) * 100)}%`,
                                            transition: 'width 600ms ease',
                                        }} />
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </section>

                {/* Users */}
                <section style={card}>
                    <div style={{ marginBottom: 16 }}>
                        <span style={sectionLabel}>Пользователи — {formatMonth(data.period)}</span>
                    </div>

                    {isMobile ? (
                        /* Mobile: cards */
                        <div style={{ display: 'flex', flexDirection: 'column' }}>
                            {data.users.map(u => (
                                <div key={u.id} style={{
                                    padding: '10px 0',
                                    borderBottom: '1px solid var(--hairline)',
                                }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                                        <div style={{ minWidth: 0, flex: 1 }}>
                                            <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--ink)' }}>
                                                {u.fullName || u.username}
                                            </span>
                                            {u.isSuperuser && (
                                                <span style={{
                                                    marginLeft: 6, fontSize: 10, fontWeight: 500,
                                                    color: 'var(--primary)', letterSpacing: '0.05em',
                                                    textTransform: 'uppercase',
                                                }}>
                                                    admin
                                                </span>
                                            )}
                                        </div>
                                        <span style={{ fontSize: 12, color: 'var(--muted)', flexShrink: 0, marginLeft: 8 }}>
                                            {formatDateTime(u.lastLogin)}
                                        </span>
                                    </div>
                                    <div style={{ display: 'flex', gap: 16 }}>
                                        <span style={{ fontSize: 12, color: 'var(--muted)' }}>
                                            Сессий: <span style={{ color: 'var(--ink)', fontWeight: 500 }}>{u.sessionsPeriod}</span>
                                        </span>
                                        <span style={{ fontSize: 12, color: 'var(--muted)' }}>
                                            Время: <span style={{ color: 'var(--ink)', fontWeight: 500 }}>{formatMinutes(u.minutesPeriod)}</span>
                                        </span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : (
                        /* Desktop: grid table */
                        <div style={{ display: 'flex', flexDirection: 'column' }}>
                            <div style={{
                                display: 'grid', gridTemplateColumns: '1fr 60px 70px 110px',
                                gap: 8, paddingBottom: 8,
                                borderBottom: '1px solid var(--hairline)',
                            }}>
                                {['Пользователь', 'Сессий', 'Время', 'Последний вход'].map(h => (
                                    <span key={h} style={{ color: 'var(--muted)', fontSize: 11, fontWeight: 500, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                                        {h}
                                    </span>
                                ))}
                            </div>
                            {data.users.map(u => (
                                <div key={u.id} style={{
                                    display: 'grid', gridTemplateColumns: '1fr 60px 70px 110px',
                                    gap: 8, padding: '9px 0',
                                    borderBottom: '1px solid var(--hairline)',
                                }}>
                                    <div style={{ minWidth: 0 }}>
                                        <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--ink)' }}>
                                            {u.fullName || u.username}
                                        </span>
                                        {u.fullName && (
                                            <span style={{ fontSize: 11, color: 'var(--muted)', marginLeft: 6 }}>
                                                {u.username}
                                            </span>
                                        )}
                                        {u.isSuperuser && (
                                            <span style={{
                                                marginLeft: 6, fontSize: 10, fontWeight: 500,
                                                color: 'var(--primary)', letterSpacing: '0.05em',
                                                textTransform: 'uppercase',
                                            }}>
                                                admin
                                            </span>
                                        )}
                                    </div>
                                    <span style={{
                                        fontSize: 13, color: u.sessionsPeriod > 0 ? 'var(--ink)' : 'var(--muted)',
                                        fontVariantNumeric: 'lining-nums', fontFeatureSettings: '"lnum" 1',
                                    }}>
                                        {u.sessionsPeriod}
                                    </span>
                                    <span style={{ fontSize: 13, color: u.minutesPeriod > 0 ? 'var(--ink)' : 'var(--muted)' }}>
                                        {formatMinutes(u.minutesPeriod)}
                                    </span>
                                    <span style={{ fontSize: 12, color: 'var(--muted)' }}>
                                        {formatDateTime(u.lastLogin)}
                                    </span>
                                </div>
                            ))}
                        </div>
                    )}
                </section>
            </div>
        </div>
    );
};

export default AdminAnalyticsPage;
