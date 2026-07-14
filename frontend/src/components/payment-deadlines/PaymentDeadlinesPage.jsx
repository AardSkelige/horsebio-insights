import { useState, useEffect, useRef } from 'react';
import { AlertCircle, Clock, CheckCircle, Loader2, RefreshCw, ExternalLink } from 'lucide-react';
import PropTypes from 'prop-types';
import { deadlinesApi } from '../../api/deadlinesApi';

const MS_DEMAND_URL = (id) => `https://online.moysklad.ru/app/#demand/edit?id=${id}`;
// отчёты комиссионера приносят готовую ссылку (ms_href), отгрузки строим по id
const msUrl = (r) => r.ms_href || MS_DEMAND_URL(r.doc_id);
const docLabel = (r) => r.doc_type === 'отчёт комиссионера' ? `${r.doc_name} · отчёт` : r.doc_name;

// ─── helpers ────────────────────────────────────────────────────────────────

function formatRub(kopecks) {
    if (!kopecks && kopecks !== 0) return '—';
    return (kopecks / 100).toLocaleString('ru-RU', {
        style: 'currency',
        currency: 'RUB',
        maximumFractionDigits: 0,
    });
}

function DaysChip({ daysLeft }) {
    let bg, color, text;
    if (daysLeft < 0) {
        bg = 'color-mix(in srgb, var(--error) 10%, transparent)';
        color = 'var(--error)';
        text = `просрочено ${Math.abs(daysLeft)} дн.`;
    } else if (daysLeft <= 3) {
        bg = 'color-mix(in srgb, var(--warning) 12%, transparent)';
        color = 'var(--warning)';
        text = `осталось ${daysLeft} дн.`;
    } else {
        bg = 'color-mix(in srgb, var(--success) 10%, transparent)';
        color = 'var(--success)';
        text = `осталось ${daysLeft} дн.`;
    }
    return (
        <span style={{
            display: 'inline-block',
            padding: '2px 8px',
            borderRadius: '20px',
            fontSize: '11px',
            fontFamily: 'var(--mono)',
            fontWeight: 500,
            backgroundColor: bg,
            color,
            whiteSpace: 'nowrap',
        }}>
            {text}
        </span>
    );
}
DaysChip.propTypes = { daysLeft: PropTypes.number.isRequired };

// ─── SummaryChip ─────────────────────────────────────────────────────────────

function SummaryChip({ label, count, colorVar, icon: Icon }) {
    return (
        <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            padding: '14px 18px',
            backgroundColor: 'var(--canvas)',
            border: '1px solid var(--hairline)',
            borderRadius: '10px',
        }}>
            <Icon style={{ width: 16, height: 16, color: `var(${colorVar})`, flexShrink: 0 }} />
            <div>
                <div style={{
                    fontFamily: 'var(--serif)',
                    fontSize: '24px',
                    fontWeight: 400,
                    letterSpacing: '-0.02em',
                    color: 'var(--ink)',
                    lineHeight: 1,
                    fontVariantNumeric: 'lining-nums',
                }}>
                    {count}
                </div>
                <div style={{ fontFamily: 'var(--sans)', fontSize: '11px', color: 'var(--muted)', marginTop: '2px' }}>
                    {label}
                </div>
            </div>
        </div>
    );
}
SummaryChip.propTypes = { label: PropTypes.string.isRequired, count: PropTypes.number.isRequired, colorVar: PropTypes.string.isRequired, icon: PropTypes.elementType.isRequired };

// ─── DeadlineCard (mobile) ───────────────────────────────────────────────────

function DeadlineCard({ r }) {
    return (
        <div style={{
            padding: '12px 16px',
            borderBottom: '1px solid var(--hairline)',
            display: 'flex', flexDirection: 'column', gap: 6,
        }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                <span style={{ fontFamily: 'var(--sans)', fontSize: 13, fontWeight: 500, color: 'var(--ink)' }}>
                    {r.agent_name}
                </span>
                <DaysChip daysLeft={r.days_left} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                {r.doc_id ? (
                    <a
                        href={msUrl(r)}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--primary)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4 }}
                    >
                        {docLabel(r)}
                        <ExternalLink style={{ width: 10, height: 10, flexShrink: 0 }} />
                    </a>
                ) : (
                    <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--muted)' }}>{docLabel(r)}</span>
                )}
                <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--muted)', whiteSpace: 'nowrap', flexShrink: 0 }}>
                    до {r.deadline}
                </span>
            </div>
            <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 12, color: 'var(--muted)' }}>
                    Сумма: <span style={{ color: 'var(--ink)', fontFamily: 'var(--mono)' }}>{formatRub(r.sum)}</span>
                </span>
                <span style={{ fontSize: 12, color: 'var(--muted)' }}>
                    Оплачено: <span style={{ fontFamily: 'var(--mono)', color: 'var(--success)' }}>{formatRub(r.payed)}</span>
                </span>
                <span style={{ fontSize: 12, color: 'var(--muted)' }}>
                    Долг: <span style={{ fontFamily: 'var(--mono)', fontWeight: 500, color: r.debt > 0 ? 'var(--error)' : 'var(--muted)' }}>{formatRub(r.debt)}</span>
                </span>
            </div>
        </div>
    );
}
DeadlineCard.propTypes = { r: PropTypes.object.isRequired };

// ─── DeadlineTable ───────────────────────────────────────────────────────────

const colStyle = {
    padding: '8px 12px',
    fontFamily: 'var(--sans)',
    fontSize: '13px',
    color: 'var(--ink)',
    verticalAlign: 'middle',
};

const headStyle = {
    padding: '8px 12px',
    fontFamily: 'var(--sans)',
    fontSize: '11px',
    fontWeight: 500,
    letterSpacing: '0.05em',
    textTransform: 'uppercase',
    color: 'var(--muted)',
    textAlign: 'left',
    borderBottom: '1px solid var(--hairline)',
    whiteSpace: 'nowrap',
};

function DeadlineTable({ rows, isMobile }) {
    if (!rows || rows.length === 0) return null;

    if (isMobile) {
        return (
            <div>
                {rows.map((r, i) => <DeadlineCard key={i} r={r} />)}
            </div>
        );
    }

    return (
        <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                    <tr>
                        <th style={headStyle}>Контрагент</th>
                        <th style={headStyle}>Документ</th>
                        <th style={headStyle}>Дата</th>
                        <th style={headStyle}>Дедлайн</th>
                        <th style={headStyle}>Срок</th>
                        <th style={{ ...headStyle, textAlign: 'right' }}>Сумма</th>
                        <th style={{ ...headStyle, textAlign: 'right' }}>Оплачено</th>
                        <th style={{ ...headStyle, textAlign: 'right' }}>Долг</th>
                        <th style={{ ...headStyle, width: '32px' }} />
                    </tr>
                </thead>
                <tbody>
                    {rows.map((r, i) => (
                        <tr key={i} style={{ borderBottom: '1px solid var(--hairline)' }}>
                            <td style={{ ...colStyle, fontWeight: 500 }}>{r.agent_name}</td>
                            <td style={{ ...colStyle, fontFamily: 'var(--mono)', fontSize: '12px' }}>
                                {r.doc_id ? (
                                    <a
                                        href={msUrl(r)}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        style={{ color: 'var(--primary)', textDecoration: 'none' }}
                                        onMouseEnter={e => (e.currentTarget.style.textDecoration = 'underline')}
                                        onMouseLeave={e => (e.currentTarget.style.textDecoration = 'none')}
                                    >
                                        {docLabel(r)}
                                    </a>
                                ) : (
                                    <span style={{ color: 'var(--muted)' }}>{docLabel(r)}</span>
                                )}
                            </td>
                            <td style={{ ...colStyle, fontFamily: 'var(--mono)', fontSize: '12px', whiteSpace: 'nowrap' }}>
                                {r.moment}
                            </td>
                            <td style={{ ...colStyle, fontFamily: 'var(--mono)', fontSize: '12px', whiteSpace: 'nowrap' }}>
                                {r.deadline}
                            </td>
                            <td style={colStyle}>
                                <DaysChip daysLeft={r.days_left} />
                            </td>
                            <td style={{ ...colStyle, textAlign: 'right', fontFamily: 'var(--mono)', fontSize: '12px', whiteSpace: 'nowrap' }}>
                                {formatRub(r.sum)}
                            </td>
                            <td style={{ ...colStyle, textAlign: 'right', fontFamily: 'var(--mono)', fontSize: '12px', color: 'var(--success)', whiteSpace: 'nowrap' }}>
                                {formatRub(r.payed)}
                            </td>
                            <td style={{ ...colStyle, textAlign: 'right', fontFamily: 'var(--mono)', fontSize: '12px', fontWeight: 500, color: r.debt > 0 ? 'var(--error)' : 'var(--muted)', whiteSpace: 'nowrap' }}>
                                {formatRub(r.debt)}
                            </td>
                            <td style={{ ...colStyle, padding: '8px 12px 8px 4px' }}>
                                {r.doc_id && (
                                    <a
                                        href={msUrl(r)}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        title="Открыть в МойСклад"
                                        style={{ display: 'flex', alignItems: 'center', color: 'var(--muted)', transition: 'color 120ms ease' }}
                                        onMouseEnter={e => (e.currentTarget.style.color = 'var(--primary)')}
                                        onMouseLeave={e => (e.currentTarget.style.color = 'var(--muted)')}
                                    >
                                        <ExternalLink style={{ width: 12, height: 12 }} />
                                    </a>
                                )}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
DeadlineTable.propTypes = { rows: PropTypes.array, isMobile: PropTypes.bool };

// ─── Section ─────────────────────────────────────────────────────────────────

const SECTIONS = [
    { key: 'overdue', label: 'Просрочено',      dot: '#c64545' },
    { key: 'warning', label: 'Скоро истекает',  dot: '#c4900a' },
    { key: 'ok',      label: 'В норме',          dot: '#3a7a3a' },
];

function Section({ config, rows, isMobile }) {
    if (!rows || rows.length === 0) return null;
    return (
        <div style={{
            backgroundColor: 'var(--canvas)',
            border: '1px solid var(--hairline)',
            borderRadius: '10px',
            overflow: 'hidden',
        }}>
            <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '14px 16px',
                borderBottom: '1px solid var(--hairline)',
            }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: config.dot, flexShrink: 0 }} />
                <span style={{ fontFamily: 'var(--serif)', fontSize: '18px', fontWeight: 400, letterSpacing: '-0.02em', color: 'var(--ink)' }}>
                    {config.label}
                </span>
                <span style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--muted)', marginLeft: '4px' }}>
                    {rows.length}
                </span>
            </div>
            <DeadlineTable rows={rows} isMobile={isMobile} />
        </div>
    );
}
Section.propTypes = { config: PropTypes.object.isRequired, rows: PropTypes.array, isMobile: PropTypes.bool };

// ─── PaymentDeadlinesPage ────────────────────────────────────────────────────

export default function PaymentDeadlinesPage() {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [isMobile, setIsMobile] = useState(() => window.innerWidth < 768);
    const abortRef = useRef(null);

    useEffect(() => {
        const handler = () => setIsMobile(window.innerWidth < 768);
        window.addEventListener('resize', handler);
        return () => window.removeEventListener('resize', handler);
    }, []);

    const load = () => {
        setLoading(true);
        setError(null);
        abortRef.current = new AbortController();
        deadlinesApi.get(abortRef.current.signal)
            .then(res => setData(res))
            .catch(err => { if (err.name !== 'AbortError') setError(err.message || 'Ошибка загрузки'); })
            .finally(() => setLoading(false));
    };

    useEffect(() => {
        load();
        return () => abortRef.current?.abort();
    }, []);

    const hasAny = data?.available && (
        data.overdue?.length || data.warning?.length || data.ok?.length
    );

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', color: 'var(--ink)' }}>
            {/* Заголовок */}
            <div style={{ borderBottom: '1px solid var(--hairline)', paddingBottom: '16px' }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
                    <div>
                        <h1 style={{
                            fontFamily: 'var(--serif)',
                            fontSize: isMobile ? '24px' : '32px',
                            fontWeight: 400,
                            letterSpacing: '-0.025em',
                            lineHeight: 1.1,
                            color: 'var(--ink)',
                            margin: 0,
                            marginBottom: '4px',
                        }}>
                            Сроки оплаты
                        </h1>
                        <p style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--muted)', margin: 0 }}>
                            Дебиторская задолженность с отсрочкой платежа
                            {data?.generated_at && (
                                <span style={{ marginLeft: '8px', color: 'var(--muted-soft)' }}>
                                    · обновлено {data.generated_at}
                                </span>
                            )}
                        </p>
                    </div>
                    <button
                        onClick={load}
                        disabled={loading}
                        style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '6px',
                            padding: '7px 14px',
                            borderRadius: '8px',
                            border: '1px solid var(--hairline)',
                            backgroundColor: 'var(--canvas)',
                            color: loading ? 'var(--muted)' : 'var(--ink)',
                            fontSize: '13px',
                            fontFamily: 'var(--sans)',
                            fontWeight: 500,
                            cursor: loading ? 'not-allowed' : 'pointer',
                            flexShrink: 0,
                        }}
                    >
                        <RefreshCw style={{ width: 13, height: 13 }} className={loading ? 'animate-spin' : ''} />
                        Обновить
                    </button>
                </div>
            </div>

            {/* Loading */}
            {loading && (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '80px 0' }}>
                    <Loader2 style={{ width: 20, height: 20, color: 'var(--muted)' }} className="animate-spin" />
                </div>
            )}

            {/* Error */}
            {!loading && error && (
                <div style={{
                    padding: '16px',
                    borderRadius: '10px',
                    backgroundColor: 'color-mix(in srgb, var(--error) 8%, transparent)',
                    border: '1px solid color-mix(in srgb, var(--error) 25%, transparent)',
                    fontFamily: 'var(--sans)',
                    fontSize: '13px',
                    color: 'var(--error)',
                }}>
                    {error}
                </div>
            )}

            {/* Нет данных */}
            {!loading && !error && !data?.available && (
                <div style={{
                    padding: '48px',
                    textAlign: 'center',
                    backgroundColor: 'var(--canvas)',
                    border: '1px solid var(--hairline)',
                    borderRadius: '10px',
                }}>
                    <Clock style={{ width: 32, height: 32, color: 'var(--muted)', margin: '0 auto 12px', display: 'block' }} />
                    <p style={{ fontFamily: 'var(--sans)', fontSize: '14px', color: 'var(--muted)', margin: 0 }}>
                        Данные ещё не загружены. Скрипт запускается ежедневно в&nbsp;09:00.
                    </p>
                </div>
            )}

            {/* Устаревшие данные */}
            {!loading && data?.stale && (
                <div style={{
                    padding: '12px 16px',
                    borderRadius: '8px',
                    backgroundColor: 'color-mix(in srgb, var(--warning) 8%, transparent)',
                    border: '1px solid color-mix(in srgb, var(--warning) 25%, transparent)',
                    fontFamily: 'var(--sans)',
                    fontSize: '13px',
                    color: 'var(--warning)',
                }}>
                    Данные устарели — скрипт не запускался более суток.
                </div>
            )}

            {/* Контент */}
            {!loading && !error && data?.available && (
                <>
                    {/* Счётчики */}
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '8px' }}>
                        <SummaryChip label="Просрочено"     count={data.summary.overdue}  colorVar="--error"   icon={AlertCircle} />
                        <SummaryChip label="Скоро истекает" count={data.summary.warning}  colorVar="--warning" icon={Clock} />
                        <SummaryChip label="В норме"        count={data.summary.ok}       colorVar="--success" icon={CheckCircle} />
                        <SummaryChip label="Оплачено"       count={data.summary.paid}     colorVar="--muted"   icon={CheckCircle} />
                    </div>

                    {/* Секции */}
                    {hasAny ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                            {SECTIONS.map(cfg => (
                                <Section key={cfg.key} config={cfg} rows={data[cfg.key]} isMobile={isMobile} />
                            ))}
                        </div>
                    ) : (
                        <div style={{
                            padding: '32px',
                            textAlign: 'center',
                            fontFamily: 'var(--sans)',
                            fontSize: '13px',
                            color: 'var(--muted)',
                            backgroundColor: 'var(--canvas)',
                            border: '1px solid var(--hairline)',
                            borderRadius: '10px',
                        }}>
                            Нет активных отсрочек платежа
                        </div>
                    )}
                </>
            )}
        </div>
    );
}
