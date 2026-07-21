import { useState, useEffect, useCallback } from 'react';
import PropTypes from 'prop-types';
import { ArrowLeft, ExternalLink, Loader2, PackageOpen, ChevronRight } from 'lucide-react';
import { checksApi, relTime, fmtRub, plural, PENDING_RETURNS_HINT } from './checksShared';
import { AccountBadge } from './ScriptCard';
import InfoTip from './InfoTip';

const HEALTH_ID = 'horsebio_health_check';

// Корзины возраста для ленты: [от, до) дней, цвет, подпись
const BUCKETS = [
    { from: 0, to: 10, color: '#ecd9cf', label: 'до 10 дней', darkText: true },
    { from: 10, to: 20, color: '#dcae99', label: '10–20 дней' },
    { from: 20, to: 30, color: '#cc785c', label: '20–30 дней' },
    { from: 30, to: Infinity, color: 'var(--warning)', label: '⚠ дольше 30', warn: true },
];

const numStyle = (color, size = 26) => ({
    fontFamily: 'var(--serif)', fontSize: size, fontWeight: 400, letterSpacing: '-0.02em',
    lineHeight: 1.15, color, fontVariantNumeric: 'lining-nums', fontFeatureSettings: '"lnum" 1',
});

/** Плоская лента: вся зависшая сумма, разбитая по возрасту возвратов.
 *  Легенда — отдельным рядом чипов, не под сегментами: реальное распределение
 *  бывает очень неравномерным (один сегмент 90%), и подписи под узкими наезжают. */
function AgeStrip({ items }) {
    // Плавающий тултип у курсора (нативный title медленный и не в стиле приложения)
    const [tip, setTip] = useState(null); // {x, y, text}
    const buckets = BUCKETS.map((b) => {
        const inb = items.filter((it) => (it.age_days ?? 0) >= b.from && (it.age_days ?? 0) < b.to);
        return { ...b, count: inb.length, sum: inb.reduce((acc, it) => acc + (it.sum_rub || 0), 0) };
    }).filter((b) => b.count > 0);
    const total = buckets.reduce((acc, b) => acc + b.sum, 0);
    if (total <= 0 || buckets.length === 0) return null;

    return (
        <div style={{ marginTop: 18 }}>
            {tip && (
                <div style={{
                    position: 'fixed', top: tip.y + 16, zIndex: 50, pointerEvents: 'none',
                    // У правого края зеркалим влево — иначе nowrap-плашка (последний сегмент)
                    // уезжает за вьюпорт (позиционирование фиксированное от курсора).
                    ...(tip.x > window.innerWidth - 260
                        ? { right: window.innerWidth - tip.x + 14 }
                        : { left: tip.x + 14 }),
                    background: 'var(--surface-dark, #262521)', color: 'var(--on-dark, #f5f2ea)',
                    fontSize: 12, fontWeight: 500, lineHeight: 1.4, borderRadius: 9, padding: '7px 11px',
                    boxShadow: '0 6px 22px rgba(0,0,0,0.25)', whiteSpace: 'nowrap',
                }}>{tip.text}</div>
            )}
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 8 }}>
                Сколько дней уже едут — по сумме
            </div>
            <div style={{ display: 'flex', gap: 2, height: 30, borderRadius: 8, overflow: 'hidden' }}>
                {buckets.map((b) => (
                    <div key={b.label}
                        onMouseMove={(e) => setTip({
                            x: e.clientX, y: e.clientY,
                            text: `${b.label}: ${b.count} ${plural(b.count, 'возврат', 'возврата', 'возвратов')} · ${fmtRub(b.sum)}`,
                        })}
                        onMouseLeave={() => setTip(null)}
                        style={{ flex: b.sum, position: 'relative', background: b.color, minWidth: 14 }}>
                        {b.sum / total >= 0.14 && (
                            <span style={{
                                position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
                                fontSize: 11.5, fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden',
                                color: b.darkText ? '#6b4632' : '#fff',
                                textShadow: b.darkText ? 'none' : '0 1px 2px rgba(0,0,0,0.18)',
                            }}>{fmtRub(b.sum)}</span>
                        )}
                    </div>
                ))}
            </div>
            <div style={{ display: 'flex', gap: '6px 18px', flexWrap: 'wrap', marginTop: 8 }}>
                {buckets.map((b) => (
                    <div key={b.label} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--muted)', whiteSpace: 'nowrap' }}>
                        <span style={{ width: 10, height: 10, borderRadius: 3, background: b.color, flexShrink: 0 }} />
                        <b style={{ fontWeight: 600, color: b.warn ? '#8a5a13' : 'var(--ink)' }}>{b.label}</b>
                        <span>— {b.count} {plural(b.count, 'возврат', 'возврата', 'возвратов')} · {fmtRub(b.sum)}</span>
                    </div>
                ))}
            </div>
        </div>
    );
}
AgeStrip.propTypes = { items: PropTypes.array.isRequired };

// Старые запуски не отдавали moment/agent отдельными полями — достаём из строки detail
// («2026-04-21 · 43 дн · 1 912р · Wildberries»)
function momentOf(it) {
    if (it.moment) return it.moment;
    return (it.detail || '').match(/\d{4}-\d{2}-\d{2}/)?.[0] || '';
}
function agentOf(it) {
    if (it.agent) return it.agent;
    const parts = (it.detail || '').split(' · ');
    return parts.length >= 4 ? parts[3] : '';
}

/** Таблица возвратов: № | маркетплейс/контрагент | создан | едет уже | сумма | МС */
function ReturnsTable({ items, warn }) {
    const PAGE = 20;
    const [shown, setShown] = useState(PAGE);
    return (
        <div style={{ overflowX: 'auto' }}>
            <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 13, fontVariantNumeric: 'tabular-nums', background: 'var(--canvas)' }}>
                <thead>
                    <tr>
                        {['Возврат', 'Откуда', 'Создан', 'Едет уже', 'Сумма', ''].map((h, i) => (
                            <th key={i} style={{
                                textAlign: i >= 3 && i <= 4 ? 'right' : 'left',
                                fontSize: 10.5, fontWeight: 700, letterSpacing: '0.07em', textTransform: 'uppercase',
                                color: 'var(--muted-soft)', padding: '8px 12px', borderBottom: '1px solid var(--hairline)',
                            }}>{h}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {items.slice(0, shown).map((it) => (
                        <tr key={it.ms_id || it.object}>
                            <td style={td()}><span style={{ fontWeight: 600, color: 'var(--ink)' }}>{it.object}</span></td>
                            <td style={td()}>{agentOf(it) || '—'}</td>
                            <td style={td()}>{momentOf(it)}</td>
                            <td style={{ ...td(), textAlign: 'right', whiteSpace: 'nowrap', color: warn ? '#8a5a13' : 'var(--body)', fontWeight: warn ? 600 : 400 }}>
                                {it.age_days} {plural(it.age_days ?? 0, 'день', 'дня', 'дней')}
                            </td>
                            <td style={{ ...td(), textAlign: 'right', whiteSpace: 'nowrap' }}>{fmtRub(it.sum_rub)}</td>
                            <td style={{ ...td(), textAlign: 'right' }}>
                                {it.ms_href && (
                                    <a href={it.ms_href} target="_blank" rel="noreferrer" style={{
                                        display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 8px', borderRadius: 7,
                                        background: 'var(--surface-soft)', color: 'var(--muted)', fontSize: 12, fontWeight: 600,
                                        textDecoration: 'none', whiteSpace: 'nowrap',
                                    }}>
                                        <ExternalLink size={12} /> МС
                                    </a>
                                )}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
            {items.length > shown && (
                <button onClick={() => setShown((n) => n + PAGE)} style={{
                    width: '100%', padding: '9px 12px', border: 'none', borderTop: '1px solid var(--hairline-soft)',
                    background: 'var(--surface-soft)', color: 'var(--primary)', fontSize: 12.5, fontWeight: 600, cursor: 'pointer',
                }}>
                    Показать ещё {Math.min(PAGE, items.length - shown)} из {items.length - shown} оставшихся
                </button>
            )}
        </div>
    );
}
ReturnsTable.propTypes = { items: PropTypes.array.isRequired, warn: PropTypes.bool };

function td() {
    return { padding: '8px 12px', borderBottom: '1px solid var(--hairline-soft)', color: 'var(--body)', verticalAlign: 'top' };
}

/** Деталка «Возвратов в пути»: сводка (две плитки + лента возраста), таблица застрявших,
 *  свёрнутая таблица едущих в срок. Формат C1. */
export default function PendingReturnsDetail({ onBack }) {
    const [data, setData] = useState(undefined); // undefined=loading, null=нет данных
    const [showOnTime, setShowOnTime] = useState(false);

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
    const overdue = items.filter((it) => (it.age_days || 0) >= warnDays);
    const onTime = items.filter((it) => (it.age_days || 0) < warnDays);

    return (
        <div style={{ maxWidth: 1100, margin: '0 auto' }}>
            <button onClick={onBack} style={{
                display: 'inline-flex', alignItems: 'center', gap: 6, marginBottom: 16,
                background: 'none', border: 'none', color: 'var(--muted)', fontSize: 13, fontWeight: 600, cursor: 'pointer', padding: 0,
            }}>
                <ArrowLeft size={15} /> Все проверки
            </button>

            {/* Шапка — как строка на главной */}
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 4 }}>
                <PackageOpen size={20} style={{ color: 'var(--muted)', flexShrink: 0, marginTop: 4 }} />
                <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 9, flexWrap: 'wrap', fontFamily: 'var(--serif)', fontSize: 24, fontWeight: 600, color: 'var(--ink)', lineHeight: 1.15 }}>
                        Возвраты в пути
                        <AccountBadge account="HorseBio" />
                        <InfoTip text={PENDING_RETURNS_HINT} width={320} />
                    </div>
                    <div style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 5, lineHeight: 1.5 }}>
                        <div><b style={{ color: 'var(--body)', fontWeight: 600 }}>Что проверяем:</b> черновики возвратов не висят без товара дольше {warnDays} дней</div>
                        <div><b style={{ color: 'var(--body)', fontWeight: 600 }}>Как:</b> робот создал черновик, когда маркетплейс объявил возврат; проводим, когда товар доехал</div>
                    </div>
                    {data?.finished_at && (
                        <div style={{ fontSize: 12, color: 'var(--muted-soft)', marginTop: 6 }}>
                            по данным Health Check · {relTime(data.finished_at)}
                        </div>
                    )}
                </div>
            </div>

            {data === undefined && (
                <div style={{ display: 'flex', gap: 8, color: 'var(--muted)', padding: 30, justifyContent: 'center' }}>
                    <Loader2 size={18} className="animate-spin" /> Загрузка…
                </div>
            )}
            {data === null && (
                <div style={{ textAlign: 'center', padding: 50, color: 'var(--muted)' }}>
                    Данных пока нет — запустите Health Check.
                </div>
            )}

            {data && (
                <>
                    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 16 }}>
                        <div style={kpi()}>
                            <div style={kpiLabel()}>Едут к нам</div>
                            <div style={numStyle('var(--ink)')}>{items.length}</div>
                            <div style={kpiSub()}>{plural(items.length, 'возврат', 'возврата', 'возвратов')} с ВБ и Озона</div>
                        </div>
                        <div style={kpi()}>
                            <div style={kpiLabel()}>Денег в дороге</div>
                            <div style={numStyle('var(--ink)')}>{fmtRub(pending.total_rub ?? items.reduce((a, it) => a + (it.sum_rub || 0), 0))}</div>
                            <div style={kpiSub()}>вернутся на склад товаром</div>
                        </div>
                    </div>

                    <AgeStrip items={items} />

                    {items.length === 0 ? (
                        <div style={{ textAlign: 'center', padding: 40, color: 'var(--success)', fontWeight: 600 }}>
                            ✓ Все возвраты дошли — в ожидании ничего нет
                        </div>
                    ) : (
                        <>
                            {overdue.length > 0 && (
                                <div style={sect()}>
                                    <div style={sectHead()}>
                                        <span style={{ width: 9, height: 9, borderRadius: 999, background: 'var(--warning)', flexShrink: 0 }} />
                                        Застряли дольше {warnDays} дней — проверить в кабинете маркетплейса
                                        <span style={{ marginLeft: 'auto', fontSize: 12, fontWeight: 700, color: '#8a5a13', background: 'rgba(176,138,31,0.12)', padding: '1px 9px', borderRadius: 999 }}>
                                            {overdue.length}
                                        </span>
                                    </div>
                                    <ReturnsTable items={overdue} warn />
                                </div>
                            )}
                            {onTime.length > 0 && (
                                <div style={sect()}>
                                    <button onClick={() => setShowOnTime((v) => !v)} style={{
                                        ...sectHead(), width: '100%', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left',
                                    }}>
                                        <ChevronRight size={15} style={{ color: 'var(--muted-soft)', transform: showOnTime ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s', flexShrink: 0 }} />
                                        Едут в срок
                                        <span style={{ marginLeft: 'auto', fontSize: 12, fontWeight: 700, color: 'var(--muted)', background: 'var(--surface-soft)', padding: '1px 9px', borderRadius: 999 }}>
                                            {onTime.length}
                                        </span>
                                    </button>
                                    {showOnTime && <ReturnsTable items={onTime} />}
                                </div>
                            )}
                        </>
                    )}
                </>
            )}
        </div>
    );
}

function kpi() {
    return { background: 'var(--surface-card)', border: '1px solid var(--hairline)', borderRadius: 12, padding: '12px 18px', minWidth: 160 };
}
function kpiLabel() {
    return { fontSize: 10.5, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--muted)', marginBottom: 5 };
}
function kpiSub() {
    return { fontSize: 11.5, color: 'var(--muted-soft)', marginTop: 3 };
}
function sect() {
    return { background: 'var(--surface-card)', border: '1px solid var(--hairline)', borderRadius: 12, marginTop: 14, overflow: 'hidden' };
}
function sectHead() {
    return { display: 'flex', alignItems: 'center', gap: 9, padding: '11px 14px', fontSize: 13.5, fontWeight: 600, color: 'var(--ink)', borderBottom: '1px solid var(--hairline)' };
}

PendingReturnsDetail.propTypes = { onBack: PropTypes.func.isRequired };
