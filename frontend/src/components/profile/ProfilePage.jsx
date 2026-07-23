import { useCallback, useEffect, useMemo, useState } from 'react';
import { CalendarClock, Database, DoorClosed, DoorOpen, LogOut, Monitor, Smartphone, ShieldCheck, Mail, ExternalLink } from 'lucide-react';
import { setAuthStatus } from '../../utils/authSession';
import { useAuthStatus } from '../../hooks/useAuthStatus';
import { authApi } from '../../api/authApi';

const card = {
    backgroundColor: 'var(--surface-card)',
    borderRadius: 12,
    padding: 20,
};

const sectionLabel = {
    fontSize: 11, fontWeight: 500,
    letterSpacing: '0.1em', textTransform: 'uppercase',
    color: 'var(--muted)', whiteSpace: 'nowrap',
};

const formatDateTime = (value) => {
    if (!value) return '—';
    return new Intl.DateTimeFormat('ru-RU', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
    }).format(new Date(value));
};

const browserLabel = (ua) => {
    if (!ua) return '';
    if (ua.includes('YaBrowser')) return 'Яндекс Браузер';
    if (ua.includes('OPR') || ua.includes('Opera')) return 'Opera';
    if (ua.includes('Edg')) return 'Edge';
    if (ua.includes('Chrome')) return 'Chrome';
    if (ua.includes('Safari')) return 'Safari';
    if (ua.includes('Firefox')) return 'Firefox';
    if (ua.includes('curl')) return ua.slice(0, 20);
    return ua.slice(0, 30);
};

const osLabel = (ua) => {
    if (!ua) return '';
    if (ua.includes('iPhone') || ua.includes('iPad')) return 'iOS';
    if (ua.includes('Android')) return 'Android';
    if (ua.includes('Windows')) return 'Windows';
    if (ua.includes('Mac OS')) return 'macOS';
    if (ua.includes('Linux')) return 'Linux';
    return '';
};

const isMobileUA = (ua) => /Mobi|Android|iPhone|iPad/i.test(ua || '');

const relativeTime = (isoStr) => {
    if (!isoStr) return '';
    const diff = Math.floor((Date.now() - new Date(isoStr)) / 1000);
    if (diff < 60) return 'только что';
    if (diff < 3600) return `${Math.floor(diff / 60)} мин назад`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} ч назад`;
    return `${Math.floor(diff / 86400)} дн назад`;
};

const formatMinutes = (minutes) => {
    if (!minutes) return '0';
    if (minutes < 60) return `${minutes} мин`;
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return m > 0 ? `${h} ч ${m} м` : `${h} ч`;
};

const ProfilePage = () => {
    const auth = useAuthStatus();
    const [activity, setActivity] = useState([]);
    const [usage, setUsage] = useState(null);
    const [sessions, setSessions] = useState([]);
    const [revokingId, setRevokingId] = useState(null);
    const [isMobile, setIsMobile] = useState(() => window.innerWidth < 768);

    useEffect(() => {
        const handler = () => setIsMobile(window.innerWidth < 768);
        window.addEventListener('resize', handler);
        return () => window.removeEventListener('resize', handler);
    }, []);

    useEffect(() => {
        const ctrl = new AbortController();

        authApi.check(ctrl.signal)
            .then(d => setAuthStatus({
                isAuthenticated: Boolean(d.isAuthenticated),
                isSuperuser: Boolean(d.isSuperuser),
                username: d.username || '',
                email: d.email || '',
                firstName: d.firstName || '',
                lastName: d.lastName || '',
            }))
            .catch(() => {});

        authApi.activity(ctrl.signal)
            .then(d => setActivity(Array.isArray(d.activity) ? d.activity : []))
            .catch(() => {});

        authApi.usage(ctrl.signal)
            .then(d => { if (d.status === 'success') setUsage(d.data); })
            .catch(() => {});

        authApi.sessions(ctrl.signal)
            .then(d => { if (d.status === 'success') setSessions(d.sessions || []); })
            .catch(() => {});

        return () => ctrl.abort();
    }, []);

    const handleRevoke = useCallback(async (sessionId) => {
        setRevokingId(sessionId);
        try {
            const d = await authApi.revokeSession(sessionId);
            if (d.status === 'success') {
                setSessions(prev => prev.filter(s => s.id !== sessionId));
            }
        } finally {
            setRevokingId(null);
        }
    }, []);

    const displayName = useMemo(() => {
        const full = [auth.firstName, auth.lastName].filter(Boolean).join(' ');
        return full || auth.username || 'Пользователь';
    }, [auth.firstName, auth.lastName, auth.username]);

    const initials = useMemo(() => {
        const src = [auth.firstName?.[0], auth.lastName?.[0]].filter(Boolean).join('');
        return (src || auth.username?.slice(0, 2) || 'HB').toUpperCase();
    }, [auth.firstName, auth.lastName, auth.username]);

    const badge = usage?.badge;
    const topPages = usage?.top_pages || [];
    const maxVisits = topPages[0]?.visits || 1;

    return (
        <div style={{ color: 'var(--ink)', maxWidth: 1180, margin: '0 auto' }}>

            {/* Header */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 18 }}>
                <span style={sectionLabel}>Личный кабинет</span>
                <div style={{ flex: 1, height: 1, backgroundColor: 'var(--hairline)' }} />
            </div>

            {/* Hero */}
            <section style={{
                backgroundColor: 'var(--surface-dark)', borderRadius: 12,
                padding: isMobile ? 16 : 24,
                display: 'flex',
                flexDirection: isMobile ? 'column' : 'row',
                justifyContent: 'space-between', alignItems: isMobile ? 'flex-start' : 'center',
                gap: 16, marginBottom: 12,
            }}>
                <div style={{ display: 'flex', gap: 16, alignItems: 'center', minWidth: 0 }}>
                    <div style={{
                        width: isMobile ? 48 : 64, height: isMobile ? 48 : 64, borderRadius: '50%',
                        backgroundColor: 'var(--primary)', color: 'var(--on-primary)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontFamily: 'var(--sans)', fontSize: isMobile ? 16 : 20, fontWeight: 600, flexShrink: 0,
                    }}>
                        {initials}
                    </div>
                    <div style={{ minWidth: 0 }}>
                        <h1 style={{
                            margin: 0, fontFamily: 'var(--serif)',
                            fontSize: isMobile ? 24 : 34,
                            fontWeight: 400, letterSpacing: '-0.025em', lineHeight: 1.1,
                            color: 'var(--on-dark)',
                            fontVariantNumeric: 'lining-nums', fontFeatureSettings: '"lnum" 1',
                        }}>
                            {displayName}
                        </h1>
                        <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                            <span style={{
                                display: 'inline-flex', alignItems: 'center', gap: 6,
                                borderRadius: 999, padding: '5px 10px',
                                backgroundColor: 'rgba(255,255,255,0.08)',
                                color: 'var(--on-dark-soft)', fontSize: 12,
                            }}>
                                <ShieldCheck size={14} />
                                {auth.isSuperuser ? 'Суперпользователь' : 'Пользователь'}
                            </span>
                            {auth.email && (
                                <span style={{
                                    display: 'inline-flex', alignItems: 'center', gap: 6,
                                    borderRadius: 999, padding: '5px 10px',
                                    backgroundColor: 'rgba(255,255,255,0.08)',
                                    color: 'var(--on-dark-soft)', fontSize: 12,
                                }}>
                                    <Mail size={12} />
                                    {auth.email}
                                </span>
                            )}
                        </div>
                    </div>
                </div>

                {/* Badge */}
                {badge && (
                    <div style={{
                        padding: isMobile ? '12px 16px' : '14px 24px',
                        textAlign: 'center',
                        backgroundColor: 'var(--surface-dark-elevated)',
                        border: '1px solid rgba(255,255,255,0.10)',
                        borderRadius: 12,
                        minWidth: isMobile ? 0 : 160,
                        alignSelf: isMobile ? 'stretch' : 'auto',
                    }}>
                        <div style={{
                            fontFamily: 'var(--serif)', fontSize: 20, fontWeight: 400,
                            letterSpacing: '-0.02em', color: 'var(--on-dark)', marginBottom: 4,
                        }}>
                            {badge.title}
                        </div>
                        <div style={{
                            fontFamily: 'var(--sans)', fontSize: 11,
                            color: 'var(--on-dark-soft)', lineHeight: 1.4,
                        }}>
                            {badge.description}
                        </div>
                    </div>
                )}
            </section>

            {/* Main grid */}
            <div style={{
                display: 'grid',
                gridTemplateColumns: isMobile ? '1fr' : '1fr 2fr',
                gap: 12,
                alignItems: 'start',
            }}>

                {/* Left column: профиль + статистика + история */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

                    <section style={card}>
                        <div style={{ marginBottom: 16 }}>
                            <span style={sectionLabel}>Профиль</span>
                        </div>
                        {[
                            ['Логин', auth.username || '—'],
                            ['Email', auth.email || '—'],
                            ['Роль', auth.isSuperuser ? 'Суперпользователь' : 'Пользователь'],
                        ].map(([l, v]) => (
                            <div key={l} style={{
                                display: 'flex', justifyContent: 'space-between', gap: 14,
                                padding: '7px 0', borderTop: '1px solid var(--hairline)',
                            }}>
                                <span style={{ color: 'var(--muted)', fontSize: 13, flexShrink: 0 }}>{l}</span>
                                <span style={{ color: 'var(--ink)', fontSize: 13, fontWeight: 500, textAlign: 'right', wordBreak: 'break-all' }}>{v}</span>
                            </div>
                        ))}
                    </section>

                    {auth.isSuperuser && (
                        <section style={card}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                                <ShieldCheck size={15} color="var(--primary)" />
                                <span style={sectionLabel}>Администрирование</span>
                            </div>
                            <a
                                href="/admin/"
                                target="_blank"
                                rel="noopener noreferrer"
                                style={{
                                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                                    padding: '11px 16px', borderRadius: 8,
                                    backgroundColor: 'var(--primary)', color: 'var(--on-primary)',
                                    fontSize: 13, fontWeight: 500, textDecoration: 'none',
                                    transition: 'opacity 0.15s',
                                }}
                                onMouseEnter={e => e.currentTarget.style.opacity = '0.9'}
                                onMouseLeave={e => e.currentTarget.style.opacity = '1'}
                            >
                                <ExternalLink size={15} />
                                Django-админка
                            </a>
                            <div style={{ color: 'var(--muted)', fontSize: 11, marginTop: 8, lineHeight: 1.4 }}>
                                Панель управления Django. Откроется в новой вкладке.
                            </div>
                        </section>
                    )}

                    {usage && (
                        <section style={card}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                                <Database size={15} color="var(--primary)" />
                                <span style={sectionLabel}>Этот месяц</span>
                            </div>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                                {[
                                    ['Сессий', String(usage.sessions_this_month ?? '—')],
                                    ['Времени', formatMinutes(usage.total_minutes_this_month)],
                                ].map(([l, v]) => (
                                    <div key={l} style={{ borderTop: '1px solid var(--hairline)', paddingTop: 12 }}>
                                        <div style={{
                                            fontFamily: 'var(--serif)', fontSize: 28, fontWeight: 400,
                                            letterSpacing: '-0.025em', lineHeight: 1, color: 'var(--ink)',
                                            fontVariantNumeric: 'lining-nums', fontFeatureSettings: '"lnum" 1',
                                        }}>
                                            {v}
                                        </div>
                                        <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 6 }}>{l}</div>
                                    </div>
                                ))}
                            </div>
                        </section>
                    )}

                    <section style={card}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                            <Monitor size={15} color="var(--primary)" />
                            <span style={sectionLabel}>Активные сессии</span>
                            <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--muted)' }}>
                                {sessions.length} {sessions.length === 1 ? 'устройство' : sessions.length < 5 ? 'устройства' : 'устройств'}
                            </span>
                        </div>
                        {sessions.length === 0 ? (
                            <span style={{ color: 'var(--muted)', fontSize: 13 }}>Нет активных сессий</span>
                        ) : (
                            <div style={{ display: 'flex', flexDirection: 'column' }}>
                                {sessions.map(s => {
                                    const mobile = isMobileUA(s.user_agent);
                                    const DevIcon = mobile ? Smartphone : Monitor;
                                    const browser = browserLabel(s.user_agent);
                                    const os = osLabel(s.user_agent);
                                    const label = [browser, os].filter(Boolean).join(' · ');
                                    return (
                                        <div key={s.id} style={{
                                            display: 'flex', gap: 10, alignItems: 'center',
                                            borderTop: '1px solid var(--hairline)', padding: '9px 0',
                                        }}>
                                            <DevIcon size={14} color="var(--muted)" style={{ flexShrink: 0 }} />
                                            <div style={{ flex: 1, minWidth: 0 }}>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                                                    <span style={{ fontSize: 13, color: 'var(--ink)', fontWeight: 500 }}>
                                                        {label || 'Неизвестный браузер'}
                                                    </span>
                                                    {s.is_current && (
                                                        <span style={{
                                                            fontSize: 10, fontWeight: 500,
                                                            color: 'var(--success)',
                                                            background: 'rgba(52,199,89,0.12)',
                                                            borderRadius: 4, padding: '1px 6px',
                                                        }}>
                                                            это устройство
                                                        </span>
                                                    )}
                                                </div>
                                                <div style={{ fontSize: 11, color: 'var(--muted-soft)', marginTop: 2 }}>
                                                    {[s.ip_address, relativeTime(s.last_seen_at)].filter(Boolean).join(' · ')}
                                                </div>
                                            </div>
                                            {!s.is_current && (
                                                <button
                                                    onClick={() => handleRevoke(s.id)}
                                                    disabled={revokingId === s.id}
                                                    title="Завершить сессию"
                                                    style={{
                                                        background: 'none', border: 'none',
                                                        cursor: revokingId === s.id ? 'default' : 'pointer',
                                                        padding: 4, borderRadius: 6, flexShrink: 0,
                                                        opacity: revokingId === s.id ? 0.4 : 1,
                                                        display: 'flex', alignItems: 'center',
                                                        color: 'var(--muted)',
                                                        transition: 'color 0.15s',
                                                    }}
                                                    onMouseEnter={e => e.currentTarget.style.color = 'var(--error)'}
                                                    onMouseLeave={e => e.currentTarget.style.color = 'var(--muted)'}
                                                >
                                                    <LogOut size={14} />
                                                </button>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </section>

                    <section style={card}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                            <CalendarClock size={15} color="var(--primary)" />
                            <span style={sectionLabel}>История входов</span>
                        </div>
                        {activity.length === 0 && (
                            <span style={{ color: 'var(--muted)', fontSize: 13 }}>Событий пока нет.</span>
                        )}
                        <div style={{ display: 'flex', flexDirection: 'column' }}>
                            {activity.slice(0, 3).map(item => {
                                const Icon = item.action === 'logout' ? DoorClosed : DoorOpen;
                                return (
                                    <div key={item.id} style={{
                                        display: 'flex', gap: 10, alignItems: 'flex-start',
                                        borderTop: '1px solid var(--hairline)', padding: '9px 0',
                                    }}>
                                        <Icon size={14} color={item.action === 'logout' ? 'var(--muted)' : 'var(--primary)'} style={{ flexShrink: 0, marginTop: 2 }} />
                                        <div style={{ minWidth: 0, flex: 1 }}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                                                <span style={{ color: 'var(--ink)', fontSize: 13, fontWeight: 500 }}>
                                                    {item.actionLabel}
                                                </span>
                                                <span style={{ color: 'var(--muted)', fontSize: 12, flexShrink: 0 }}>
                                                    {formatDateTime(item.createdAt)}
                                                </span>
                                            </div>
                                            <div style={{
                                                color: 'var(--muted-soft)', fontSize: 11, marginTop: 2,
                                                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                                            }}>
                                                {[item.ipAddress, browserLabel(item.userAgent)].filter(Boolean).join(' · ')}
                                            </div>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </section>
                </div>

                {/* Right column: популярные разделы */}
                <section style={{ ...card, alignSelf: 'start' }}>
                    <div style={{ marginBottom: 20 }}>
                        <span style={sectionLabel}>Популярные разделы</span>
                    </div>

                    {topPages.length === 0 ? (
                        <div style={{
                            padding: '40px 0', textAlign: 'center',
                            color: 'var(--muted)', fontSize: 13, fontStyle: 'italic',
                        }}>
                            Данные появятся после нескольких переходов между разделами
                        </div>
                    ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                            {topPages.map((p, i) => (
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
                                        <span style={{ fontSize: 12, color: 'var(--muted)', flexShrink: 0 }}>
                                            {p.visits} {p.visits === 1 ? 'визит' : p.visits < 5 ? 'визита' : 'визитов'}
                                            {p.avg_duration >= 60 && ` · ~${Math.round(p.avg_duration / 60)} мин`}
                                        </span>
                                    </div>
                                    <div style={{ height: 3, borderRadius: 2, backgroundColor: 'var(--hairline)' }}>
                                        <div style={{
                                            height: '100%', borderRadius: 2,
                                            backgroundColor: i === 0 ? 'var(--primary)' : 'var(--muted-soft)',
                                            opacity: i === 0 ? 1 : 0.5 + (0.5 * (topPages.length - i) / topPages.length),
                                            width: `${Math.round((p.visits / maxVisits) * 100)}%`,
                                            transition: 'width 600ms ease',
                                        }} />
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </section>
            </div>
        </div>
    );
};

export default ProfilePage;
