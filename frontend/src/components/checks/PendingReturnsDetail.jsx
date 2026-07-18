import { useState, useEffect, useCallback } from 'react';
import PropTypes from 'prop-types';
import { ArrowLeft, ExternalLink, Loader2, PackageOpen } from 'lucide-react';
import { checksApi, relTime } from './checksShared';
import InfoTip from './InfoTip';
import { PENDING_RETURNS_HINT, fmtRub } from './PendingReturnsCard';

const HEALTH_ID = 'horsebio_health_check';

const numStyle = (color, size = 26) => ({
    fontFamily: 'var(--serif)', fontSize: size, fontWeight: 400, letterSpacing: '-0.02em',
    lineHeight: 1.15, color, fontVariantNumeric: 'lining-nums', fontFeatureSettings: '"lnum" 1',
});

function Row({ item }) {
    const overdue = item.severity === 'warning';
    return (
        <div style={{
            display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px',
            borderTop: '1px solid var(--hairline-soft)',
            background: overdue ? 'rgba(176,138,31,0.05)' : 'transparent',
        }}>
            <span style={{ width: 7, height: 7, borderRadius: 999, flexShrink: 0, background: overdue ? '#b08a1f' : 'var(--muted-soft)' }} />
            <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink)' }}>{item.object}</div>
                <div style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 2 }}>{item.detail}</div>
            </div>
            <div style={{ ...numStyle(overdue ? '#b08a1f' : 'var(--ink)', 16), flexShrink: 0 }}>
                {fmtRub(item.sum_rub)}
            </div>
            {item.ms_href && (
                <a href={item.ms_href} target="_blank" rel="noreferrer" style={{
                    display: 'inline-flex', alignItems: 'center', gap: 4, padding: '4px 9px', borderRadius: 7,
                    background: 'var(--surface-soft)', color: 'var(--muted)', fontSize: 12, fontWeight: 600,
                    textDecoration: 'none', whiteSpace: 'nowrap', flexShrink: 0,
                }}>
                    <ExternalLink size={13} /> МС
                </a>
            )}
        </div>
    );
}
Row.propTypes = { item: PropTypes.object.isRequired };

/** Деталка индикатора «Возвраты в пути»: список черновиков возвратов из последнего
 *  запуска хелс-чека, просроченные сверху. */
export default function PendingReturnsDetail({ onBack }) {
    const [data, setData] = useState(undefined); // undefined=loading, null=нет данных

    const load = useCallback(async () => {
        try {
            const res = await checksApi.results(HEALTH_ID);
            setData(res.results || null);
        } catch { setData(null); }
    }, []);

    useEffect(() => { load(); }, [load]);

    const cat = data?.categories?.find((c) => c.key === 'pending_returns');
    const items = [...(cat?.items || [])].sort((a, b) => (b.age_days || 0) - (a.age_days || 0));
    const pending = data?.summary?.pending_returns || {};
    const warnDays = pending.warn_days || 30;
    const overdueItems = items.filter((it) => it.severity === 'warning');

    return (
        <div style={{ maxWidth: 820, margin: '0 auto' }}>
            <button onClick={onBack} style={{
                display: 'inline-flex', alignItems: 'center', gap: 6, marginBottom: 18,
                background: 'none', border: 'none', color: 'var(--muted)', fontSize: 13, fontWeight: 600, cursor: 'pointer',
            }}>
                <ArrowLeft size={15} /> Все проверки
            </button>

            <header style={{ marginBottom: 20 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <PackageOpen size={24} style={{ color: 'var(--primary)' }} />
                    <h1 style={{ fontFamily: 'var(--serif)', fontSize: 26, fontWeight: 600, color: 'var(--ink)', margin: 0 }}>
                        Возвраты в пути
                    </h1>
                    <InfoTip text={PENDING_RETURNS_HINT} width={320} />
                </div>
                {data?.finished_at && (
                    <p style={{ color: 'var(--muted)', marginTop: 6, fontSize: 13 }}>
                        По данным хелс-чека — {relTime(data.finished_at)}
                    </p>
                )}
            </header>

            {data === undefined && (
                <div style={{ display: 'flex', gap: 8, color: 'var(--muted)', padding: 30, justifyContent: 'center' }}>
                    <Loader2 size={18} className="animate-spin" /> Загрузка…
                </div>
            )}
            {data === null && (
                <div style={{ textAlign: 'center', padding: 50, color: 'var(--muted)' }}>
                    Данных пока нет — запустите хелс-чек.
                </div>
            )}

            {data && (
                <>
                    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 18 }}>
                        <div style={statCard()}>
                            <div style={statLabel()}>Ждут товара</div>
                            <div style={numStyle('var(--ink)')}>{pending.count ?? items.length}</div>
                        </div>
                        <div style={statCard()}>
                            <div style={statLabel()}>Зависло денег</div>
                            <div style={numStyle('var(--ink)')}>{fmtRub(pending.total_rub)}</div>
                        </div>
                        {(pending.overdue > 0 || overdueItems.length > 0) && (
                            <div style={{ ...statCard(), background: 'rgba(176,138,31,0.08)' }}>
                                <div style={{ ...statLabel(), color: '#b08a1f' }}>Дольше {warnDays} дн.</div>
                                <div style={numStyle('#b08a1f')}>
                                    {pending.overdue ?? overdueItems.length} · {fmtRub(pending.overdue_rub)}
                                </div>
                            </div>
                        )}
                    </div>

                    {items.length === 0 ? (
                        <div style={{ textAlign: 'center', padding: 40, color: 'var(--success)', fontWeight: 600 }}>
                            ✓ Непроведённых возвратов нет
                        </div>
                    ) : (
                        <div style={{ background: 'var(--surface-card)', border: '1px solid var(--hairline)', borderRadius: 12 }}>
                            <div style={{ padding: '10px 14px', fontSize: 12, color: 'var(--muted)' }}>
                                Старые сверху. Висит дольше {warnDays} дней — проверить статус возврата в кабинете маркетплейса.
                                Товар пришёл на склад — провести документ в МойСклад.
                            </div>
                            {items.map((it) => <Row key={it.ms_id || it.object} item={it} />)}
                        </div>
                    )}
                </>
            )}
        </div>
    );
}

function statCard() {
    return {
        minWidth: 150, padding: '14px 18px', borderRadius: 12,
        background: 'var(--surface-card)', border: '1px solid var(--hairline)',
    };
}
function statLabel() {
    return {
        fontFamily: 'var(--sans)', fontSize: 11, fontWeight: 500, letterSpacing: '0.1em',
        textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 8,
    };
}

PendingReturnsDetail.propTypes = { onBack: PropTypes.func.isRequired };
