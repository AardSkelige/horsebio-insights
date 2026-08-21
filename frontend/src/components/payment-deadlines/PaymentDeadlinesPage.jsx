import { useState, useEffect, useRef } from 'react';
import { AlertCircle, Clock, CheckCircle, ExternalLink } from 'lucide-react';
import PropTypes from 'prop-types';
import { Button, DataTable, EmptyState, IconButton, Page, PageHeader, Skeleton, StatCard, StatGrid } from '../ui';
import { deadlinesApi } from '../../api/deadlinesApi';

const MS_DEMAND_URL = (id) => `https://online.moysklad.ru/app/#demand/edit?id=${id}`;
// отчёты комиссионера приносят готовую ссылку (ms_href), отгрузки строим по id
const msUrl = (r) => r.ms_href || MS_DEMAND_URL(r.doc_id);
const docLabel = (r) => r.doc_type === 'отчёт комиссионера' ? `${r.doc_name} · отчёт` : r.doc_name;

// ─── helpers ────────────────────────────────────────────────────────────────

/** Суммы в этом отчёте приходят в копейках, поэтому общий `money` не подходит. */
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
        <DataTable
            columns={[
                { key: 'agent_name', label: 'Контрагент', strong: true, sortable: false },
                {
                    key: 'doc',
                    label: 'Документ',
                    sortable: false,
                    render: (r) => r.doc_id ? (
                        <Button as="a" variant="link" size="sm" href={msUrl(r)} target="_blank" rel="noopener noreferrer">
                            {docLabel(r)}
                        </Button>
                    ) : <span style={{ color: 'var(--muted)' }}>{docLabel(r)}</span>,
                },
                { key: 'moment', label: 'Дата', sortable: false, render: (r) => <span style={{ fontFamily: 'var(--mono)', fontSize: 'var(--size-sm)', whiteSpace: 'nowrap' }}>{r.moment}</span> },
                { key: 'deadline', label: 'Дедлайн', sortable: false, render: (r) => <span style={{ fontFamily: 'var(--mono)', fontSize: 'var(--size-sm)', whiteSpace: 'nowrap' }}>{r.deadline}</span> },
                { key: 'days_left', label: 'Срок', sortable: false, render: (r) => <DaysChip daysLeft={r.days_left} /> },
                { key: 'sum', label: 'Сумма', numeric: true, sortable: false, render: (r) => formatRub(r.sum) },
                {
                    key: 'payed',
                    label: 'Оплачено',
                    numeric: true,
                    sortable: false,
                    render: (r) => <span style={{ color: 'var(--success-ink)' }}>{formatRub(r.payed)}</span>,
                },
                {
                    key: 'debt',
                    label: 'Долг',
                    numeric: true,
                    sortable: false,
                    render: (r) => (
                        <span style={{ color: r.debt > 0 ? 'var(--error-ink)' : 'var(--muted)', fontWeight: 500 }}>
                            {formatRub(r.debt)}
                        </span>
                    ),
                },
                {
                    key: 'link',
                    label: '',
                    sortable: false,
                    render: (r) => r.doc_id && (
                        <IconButton as="a" icon={ExternalLink} label="Открыть в МойСклад" size={12}
                            href={msUrl(r)} target="_blank" rel="noopener noreferrer" />
                    ),
                },
            ]}
            rows={rows}
            rowKey={(r) => `${r.doc_id || r.agent_name}-${r.deadline}`}
            emptyText="Нет документов"
        />
    );
}
DeadlineTable.propTypes = { rows: PropTypes.array, isMobile: PropTypes.bool };

// ─── Section ─────────────────────────────────────────────────────────────────

const SECTIONS = [
    { key: 'overdue', label: 'Просрочено',      dot: 'var(--error)' },
    { key: 'warning', label: 'Скоро истекает',  dot: 'var(--warning-ink)' },
    { key: 'ok',      label: 'В норме',          dot: 'var(--success-ink)' },
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
        <Page>
            <PageHeader
                title="Сроки оплаты"
                subtitle="Дебиторская задолженность с отсрочкой платежа"
                updatedAt={data?.generated_at}
                onRefresh={load}
                refreshing={loading}
            />

            {/* Loading */}
            {loading && !data && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    <Skeleton height={72} />
                    <Skeleton height={220} />
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
                    <div>
                        <StatGrid>
                            <StatCard icon={AlertCircle}  title="Просрочено"     value={data.summary.overdue} />
                            <StatCard icon={Clock}        title="Скоро истекает" value={data.summary.warning} />
                            <StatCard icon={CheckCircle}  title="В норме"        value={data.summary.ok} />
                            <StatCard icon={CheckCircle}  title="Оплачено"       value={data.summary.paid} />
                        </StatGrid>
                    </div>

                    {/* Секции */}
                    {hasAny ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                            {SECTIONS.map(cfg => (
                                <Section key={cfg.key} config={cfg} rows={data[cfg.key]} isMobile={isMobile} />
                            ))}
                        </div>
                    ) : (
                        <EmptyState title="Нет активных отсрочек платежа" />
                    )}
                </>
            )}
        </Page>
    );
}
