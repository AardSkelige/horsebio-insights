import { useState, useEffect, useCallback, useLayoutEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import PropTypes from 'prop-types';
import { ArrowLeft, ExternalLink, Loader2, PackageOpen, ChevronRight } from 'lucide-react';
import { Button } from '../ui';
import { checksApi, relTime, fmtRub, plural, PENDING_RETURNS_HINT, PENDING_RETURNS_ID } from './checksShared';
import { AccountBadge } from './ScriptCard';
import InfoTip from './InfoTip';



// Корзины возраста для ленты: [от, до) дней, цвет, подпись
const BUCKETS = [
    // Шкала «свежести»: чем дольше возврат висит, тем плотнее заливка
    { from: 0, to: 10, color: 'color-mix(in srgb, var(--primary) 25%, var(--canvas))', label: 'до 10 дней', darkText: true },
    { from: 10, to: 20, color: 'color-mix(in srgb, var(--primary) 55%, var(--canvas))', label: '10–20 дней' },
    { from: 20, to: 30, color: 'var(--primary)', label: '20–30 дней' },
    { from: 30, to: Infinity, color: 'var(--warning)', label: '⚠ дольше 30', warn: true },
];

// Маркетплейсы: короткая подпись + цвет точки. Порядок — как показываем в разбивке.
const MP_ORDER = ['ozon', 'wb', 'other'];
const MP_META = {
    ozon:  { label: 'Озон',   color: 'var(--primary)' },
    wb:    { label: 'ВБ',     color: 'var(--cat-clay)' },
    other: { label: 'Прочее', color: 'var(--muted-soft)' },
};

// Относим возврат к маркетплейсу по имени контрагента (agentOf). Значения в МойСклад —
// «Озон», «Вайлдберриз (Вб)»; старые записи могли писать Ozon/Wildberries — ловим по подстроке.
function mpKey(it) {
    const a = (agentOf(it) || '').toLowerCase();
    if (a.includes('озон') || a.includes('ozon')) return 'ozon';
    if (a.includes('вайлдбер') || a.includes('wildber') || a.includes('вб')) return 'wb';
    return 'other';
}

// Разбивка списка возвратов по маркетплейсам → строки {key,label,color,count,sum}
// только для непустых групп, в порядке MP_ORDER.
function mpRows(list) {
    const g = { ozon: { count: 0, sum: 0 }, wb: { count: 0, sum: 0 }, other: { count: 0, sum: 0 } };
    for (const it of list) {
        const b = g[mpKey(it)];
        b.count += 1;
        b.sum += it.sum_rub || 0;
    }
    return MP_ORDER.filter((k) => g[k].count > 0).map((k) => ({ key: k, ...MP_META[k], ...g[k] }));
}

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
    const tipRef = useRef(null);

    // Держим плашку у курсора, но не даём вылезти за край вьюпорта. Ширину меряем
    // по факту (текст разной длины) в useLayoutEffect — до отрисовки, без мигания.
    useLayoutEffect(() => {
        const el = tipRef.current;
        if (!el || !tip) return;
        const pad = 8;
        const w = el.offsetWidth;
        const h = el.offsetHeight;
        let left = tip.x + 14;
        let top = tip.y + 16;
        if (left + w > window.innerWidth - pad) left = window.innerWidth - w - pad;
        if (left < pad) left = pad;
        if (top + h > window.innerHeight - pad) top = tip.y - h - 12; // не влезает снизу — над курсором
        el.style.left = `${left}px`;
        el.style.top = `${top}px`;
    }, [tip]);

    const buckets = BUCKETS.map((b) => {
        const inb = items.filter((it) => (it.age_days ?? 0) >= b.from && (it.age_days ?? 0) < b.to);
        return {
            ...b, count: inb.length,
            sum: inb.reduce((acc, it) => acc + (it.sum_rub || 0), 0),
            rows: mpRows(inb),
        };
    }).filter((b) => b.count > 0);
    const total = buckets.reduce((acc, b) => acc + b.sum, 0);
    if (total <= 0 || buckets.length === 0) return null;

    return (
        <div style={{ marginTop: 18 }}>
            {tip && createPortal(
                // Портал в body: внутри страницы предки с transform (route-анимация,
                // свайп-карточки) ломают position:fixed — плашка уезжала от курсора.
                <div ref={tipRef} style={{
                    position: 'fixed', left: tip.x + 14, top: tip.y + 16, zIndex: 50, pointerEvents: 'none',
                    background: 'var(--surface-dark)', color: 'var(--on-dark)',
                    fontSize: 12, fontWeight: 500, lineHeight: 1.4, borderRadius: 9, padding: '7px 11px',
                    boxShadow: 'var(--shadow-float)', whiteSpace: 'nowrap',
                }}>
                    <div style={{ fontWeight: 700 }}>{tip.title}</div>
                    {tip.rows?.map((r) => (
                        <div key={r.key} style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 3, opacity: 0.92 }}>
                            <span style={{ width: 7, height: 7, borderRadius: 999, background: r.color, flexShrink: 0 }} />
                            {r.label} — {r.count} шт · {fmtRub(r.sum)}
                        </div>
                    ))}
                </div>,
                document.body
            )}
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 8 }}>
                Сколько дней уже едут — по сумме
            </div>
            <div style={{ display: 'flex', gap: 2, height: 30, borderRadius: 8, overflow: 'hidden' }}>
                {buckets.map((b) => (
                    <div key={b.label}
                        onMouseMove={(e) => setTip({
                            x: e.clientX, y: e.clientY,
                            title: `${b.label}: ${b.count} ${plural(b.count, 'возврат', 'возврата', 'возвратов')} · ${fmtRub(b.sum)}`,
                            rows: b.rows,
                        })}
                        onMouseLeave={() => setTip(null)}
                        style={{ flex: b.sum, position: 'relative', background: b.color, minWidth: 14 }}>
                        {b.sum / total >= 0.14 && (
                            <span style={{
                                position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
                                fontSize: 11.5, fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden',
                                color: b.darkText ? 'var(--cat-clay-ink)' : 'var(--on-primary)',
                                textShadow: b.darkText ? 'none' : 'var(--shadow-card)',
                            }}>{fmtRub(b.sum)}</span>
                        )}
                    </div>
                ))}
            </div>
            <div style={{ display: 'flex', gap: '6px 18px', flexWrap: 'wrap', marginTop: 8 }}>
                {buckets.map((b) => (
                    <div key={b.label} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--muted)', whiteSpace: 'nowrap' }}>
                        <span style={{ width: 10, height: 10, borderRadius: 3, background: b.color, flexShrink: 0 }} />
                        <b style={{ fontWeight: 600, color: b.warn ? 'var(--warning-ink)' : 'var(--ink)' }}>{b.label}</b>
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
                            <td style={{ ...td(), textAlign: 'right', whiteSpace: 'nowrap', color: warn ? 'var(--warning-ink)' : 'var(--body)', fontWeight: warn ? 600 : 400 }}>
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
                <Button variant="subtle" tone="accent" block onClick={() => setShown((n) => n + PAGE)}
                    style={{ borderTop: '1px solid var(--hairline-soft)', borderRadius: 0 }}>
                    Показать ещё {Math.min(PAGE, items.length - shown)} из {items.length - shown} оставшихся
                </Button>
            )}
        </div>
    );
}
ReturnsTable.propTypes = { items: PropTypes.array.isRequired, warn: PropTypes.bool };

function td() {
    return { padding: '8px 12px', borderBottom: '1px solid var(--hairline-soft)', color: 'var(--body)', verticalAlign: 'top' };
}

/** Разбивка метрики карточки по маркетплейсам: точка + подпись + значение.
 *  mode='count' — штуки (для «Едут к нам»), mode='sum' — деньги (для «Денег в дороге»). */
function MpBreakdown({ rows, mode }) {
    return (
        <div style={{ display: 'flex', gap: '4px 12px', flexWrap: 'wrap', marginTop: 7 }}>
            {rows.map((r) => (
                <span key={r.key} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11.5, color: 'var(--muted)', whiteSpace: 'nowrap' }}>
                    <span style={{ width: 7, height: 7, borderRadius: 999, background: r.color, flexShrink: 0 }} />
                    <b style={{ fontWeight: 600, color: 'var(--body)' }}>{r.label}</b> {mode === 'sum' ? fmtRub(r.sum) : r.count}
                </span>
            ))}
        </div>
    );
}
MpBreakdown.propTypes = { rows: PropTypes.array.isRequired, mode: PropTypes.oneOf(['count', 'sum']).isRequired };

/** Деталка «Возвратов в пути»: сводка (две плитки + лента возраста), таблица застрявших,
 *  свёрнутая таблица едущих в срок. Формат C1. */
export default function PendingReturnsDetail({ onBack }) {
    const [data, setData] = useState(undefined); // undefined=loading, null=нет данных
    const [showOnTime, setShowOnTime] = useState(false);

    const load = useCallback(async () => {
        try {
            const res = await checksApi.results(PENDING_RETURNS_ID);
            setData(res.results || null);
        } catch { setData(null); }
    }, []);

    useEffect(() => { load(); }, [load]);

    const cat = data?.categories?.find((c) => c.key === 'pending_returns');
    const items = [...(cat?.items || [])].sort((a, b) => (b.age_days || 0) - (a.age_days || 0));
    const pending = data?.summary?.pending_returns || {};
    const warnDays = pending.warn_days || 30;
    // Товар уже на складе — возраст тут значит «не разобрали», а не «потерялся
    // по дороге». Такие не едут и в счётчиках дороги не участвуют.
    const atSite = items.filter((it) => it.at_our_site);
    // Доехали до пункта выдачи и ждут, пока заберут. Отдельное действие и
    // отдельный человек — если не показать, срок хранения истечёт и товар пропадёт.
    const atPickup = items.filter((it) => it.at_pickup);
    const inTransit = items.filter((it) => !it.at_our_site && !it.at_pickup);
    const overdue = inTransit.filter((it) => (it.age_days || 0) >= warnDays);
    const onTime = inTransit.filter((it) => (it.age_days || 0) < warnDays);
    const sumOf = (list) => list.reduce((a, it) => a + (it.sum_rub || 0), 0);
    const transitRub = sumOf(inTransit);
    const atSiteRub = pending.at_our_site_rub ?? sumOf(atSite);
    const atPickupRub = pending.at_pickup_rub ?? sumOf(atPickup);
    const mp = mpRows(inTransit); // разбивка едущих возвратов по маркетплейсам

    return (
        <div style={{ maxWidth: 1100, margin: '0 auto' }}>
            <Button variant="quiet" icon={ArrowLeft} onClick={onBack} style={{ marginBottom: 16 }}>
                Все проверки
            </Button>

            {/* Шапка — как строка на главной */}
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 4 }}>
                <PackageOpen size={20} style={{ color: 'var(--muted)', flexShrink: 0, marginTop: 4 }} />
                <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 9, flexWrap: 'wrap', fontFamily: 'var(--serif)', fontSize: 24, fontWeight: 600, color: 'var(--ink)', lineHeight: 1.15 }}>
                        Что разобрать из возвратов
                        <AccountBadge account="HorseBio" />
                        <InfoTip text={PENDING_RETURNS_HINT} width={320} />
                    </div>
                    <div style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 5, lineHeight: 1.5 }}>
                        <div><b style={{ color: 'var(--body)', fontWeight: 600 }}>Что проверяем:</b> какие возвраты требуют действия и сколько в них денег</div>
                        <div><b style={{ color: 'var(--body)', fontWeight: 600 }}>Как:</b> считаем возраст и сумму каждого незакрытого возврата, группируем по статусу</div>
                    </div>
                    {data?.finished_at && (
                        <div style={{ fontSize: 12, color: 'var(--muted-soft)', marginTop: 6 }}>
                            проверка · {relTime(data.finished_at)}
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
                        <Kpi
                            label="Едут к нам" value={inTransit.length} color="var(--ink)"
                            sub={mp.length > 0
                                ? <MpBreakdown rows={mp} mode="count" />
                                : <div style={kpiSub()}>{plural(inTransit.length, 'возврат', 'возврата', 'возвратов')} с ВБ и Озона</div>}
                        />
                        <Kpi
                            label="Денег в дороге" value={fmtRub(transitRub)} color="var(--ink)"
                            sub={mp.length > 0
                                ? <MpBreakdown rows={mp} mode="sum" />
                                : <div style={kpiSub()}>вернутся на склад товаром</div>}
                        />
                        {atPickup.length > 0 && (
                            <Kpi
                                label="Забрать в ПВЗ" value={atPickup.length} color="var(--cat-orange-ink)" jumpTo="grp-pickup"
                                sub={<div style={kpiSub()}>{fmtRub(atPickupRub)} · ждут в пункте выдачи</div>}
                            />
                        )}
                        {atSite.length > 0 && (
                            <Kpi
                                label="Уже у нас" value={atSite.length} color="var(--warning)" jumpTo="grp-atsite"
                                sub={<div style={kpiSub()}>{fmtRub(atSiteRub)} · ждут проведения</div>}
                            />
                        )}
                        {overdue.length > 0 && (
                            <Kpi
                                label={`Застряли ${warnDays}+ дней`} value={overdue.length} color="var(--warning)" jumpTo="grp-overdue"
                                sub={<div style={kpiSub()}>{fmtRub(sumOf(overdue))} · писать в поддержку</div>}
                            />
                        )}
                    </div>

                    <AgeStrip items={inTransit} />

                    {items.length === 0 ? (
                        <div style={{ textAlign: 'center', padding: 40, color: 'var(--success)', fontWeight: 600 }}>
                            ✓ Все возвраты дошли — в ожидании ничего нет
                        </div>
                    ) : (
                        <>
                            <Group
                                id="grp-pickup" dot="var(--cat-orange-ink)" items={atPickup} openByDefault
                                title="Лежат в пункте выдачи — съездить забрать"
                                note="Коробка доехала до пункта выдачи и ждёт. Срок хранения ограничен — если не забрать, товар пропадёт. Это к тому, кто ездит за возвратами."
                            />
                            <Group
                                id="grp-atsite" dot="var(--warning)" items={atSite}
                                title="Товар у нас — проверить и провести"
                                note="Коробки уже на складе. Осталось разобрать и провести документ — после этого возврат отсюда исчезнет, а товар встанет на остатки."
                            />
                            <Group
                                id="grp-overdue" dot="var(--warning)" items={overdue} openByDefault
                                title={`Застряли дольше ${warnDays} дней — проверить в кабинете маркетплейса`}
                                note="Товар едет к нам, но встал по дороге. Сам не поедет — нужно писать в поддержку маркетплейса по номеру возврата."
                            />
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

/** Плитка-итог. Если у неё есть своя группа ниже — кликается и ведёт туда. */
function Kpi({ label, value, sub, color, jumpTo }) {
    const go = () => {
        const el = document.getElementById(jumpTo);
        if (!el) return;
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        // Свёрнутую группу раскрываем: человек пришёл именно за этим списком
        if (el.querySelectorAll('table').length === 0) el.querySelector('button')?.click();
    };
    return (
        <div
            onClick={jumpTo ? go : undefined}
            role={jumpTo ? 'button' : undefined}
            tabIndex={jumpTo ? 0 : undefined}
            onKeyDown={jumpTo ? (e) => { if (e.key === 'Enter') go(); } : undefined}
            style={{ ...kpi(), cursor: jumpTo ? 'pointer' : 'default' }}
        >
            <div style={kpiLabel()}>{label}{jumpTo && <span style={{ color: 'var(--primary)' }}> ↓</span>}</div>
            <div style={numStyle(color)}>{value}</div>
            {sub}
        </div>
    );
}
Kpi.propTypes = {
    label: PropTypes.string, value: PropTypes.node, sub: PropTypes.node,
    color: PropTypes.string, jumpTo: PropTypes.string,
};

/** Секция с группой возвратов: заголовок-кнопка, подпись «что делать», таблица.
 *  Свёрнута по умолчанию — списки длинные, а сверху уже есть плитки с итогами. */
function Group({ id, title, note, items, dot, openByDefault }) {
    const [open, setOpen] = useState(!!openByDefault);
    if (items.length === 0) return null;
    return (
        <div id={id} style={sect()}>
            <button onClick={() => setOpen((v) => !v)} style={{
                ...sectHead(), width: '100%', background: 'none', border: 'none',
                cursor: 'pointer', textAlign: 'left',
            }}>
                <ChevronRight size={15} style={{
                    color: 'var(--muted-soft)', transform: open ? 'rotate(90deg)' : 'none',
                    transition: 'transform 0.15s', flexShrink: 0,
                }} />
                <span style={{ width: 9, height: 9, borderRadius: 999, background: dot, flexShrink: 0 }} />
                {title}
                <span style={{
                    marginLeft: 'auto', fontSize: 12, fontWeight: 700, color: 'var(--warning-ink)',
                    background: 'var(--warning-bg)', padding: '1px 9px', borderRadius: 999,
                }}>{items.length}</span>
            </button>
            {open && (
                <>
                    <SectNote>{note}</SectNote>
                    <ReturnsTable items={items} warn />
                </>
            )}
        </div>
    );
}
Group.propTypes = {
    id: PropTypes.string, title: PropTypes.string, note: PropTypes.node,
    items: PropTypes.array, dot: PropTypes.string, openByDefault: PropTypes.bool,
};

/** Подпись под заголовком группы: чьё это дело и что именно сделать.
 *  Без неё список читается как «просто данные» — непонятно, кому идти работать. */
function SectNote({ children }) {
    return (
        <div style={{
            padding: '8px 14px 10px', fontSize: 12.5, color: 'var(--muted)',
            lineHeight: 1.5, borderBottom: '1px solid var(--hairline)',
        }}>{children}</div>
    );
}
SectNote.propTypes = { children: PropTypes.node };

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
