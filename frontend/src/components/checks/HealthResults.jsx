import { useState, useEffect, useCallback } from 'react';
import PropTypes from 'prop-types';
import { ExternalLink, Plus, Check, Undo2, Loader2, ShieldCheck, ChevronRight, Trash2 } from 'lucide-react';
import { Button } from '../ui';
import { checksApi, SEV, sevOf, msLink, relTime } from './checksShared';
import { useConfirmDelete } from '../../hooks/useConfirmDelete';
import InfoTip from './InfoTip';
import './HealthResults.css';

// Подсказки по неочевидным категориям и стат-карточкам
const DEV_HINT =
    'Сравниваем две цены одного товара: по какой он числится на складе сейчас (FIFO — '
    + 'средняя по партиям, что лежат) и почём его закупили в последний раз. '
    + '«Склад дороже закупки» — доедаем старую дорогую партию, себестоимость продукции пока '
    + 'завышена и снизится, когда партия кончится. «Склад дешевле закупки» — наоборот: '
    + 'лежит старый дешёвый запас, и себестоимость вырастет на эти проценты, когда он кончится. '
    + 'Само по себе расхождение не ошибка — так выглядит обычный рост или падение закупочных цен. '
    + 'Разбираться стоит, если цены не менялись: тогда причина в документах.';

const JUMP_HINT =
    'Сравниваем цену последней приёмки со средней по трём прошлым приёмкам этого же товара. '
    + '«Приёмка дороже обычной» — закупили выше привычной цены, «дешевле обычной» — ниже. '
    + 'Частая причина «дешевле» — в приёмку попало не то же самое, что обычно: например, '
    + 'к наклейке заказали только задник, а провели его тем же артикулом.';

const CAT_HINTS = {
    critical: DEV_HINT,
    important: DEV_HINT,
    supply_jumps: JUMP_HINT,
    deviations_normal: 'Товары, у которых остаток на складе числится по одной цене (FIFO), а последняя закупка была по другой — но ты уже разбирался и подтвердил: это не ошибка, обычно на складе просто лежат старые партии по прошлой цене. Если после разбора расхождение заметно вырастет, товар автоматически вернётся в проблемные.',
};
const STAT_HINTS = {
    'Уже актуальны': 'Цены уже совпадают с FIFO — обновление не требуется.',
    'Себестоимость 0': 'У этих товаров FIFO-себестоимость нулевая: нет ни одной приёмки, обновлять нечего. Полный список — в секции ниже.',
    'Нет остатков': 'Этих товаров нет на складе (или FIFO = 0) — их себестоимость не пересчитывается. Полный список — в секции ниже.',
    'Нет отгрузки': 'Заказ есть, но отгрузки нет — возврат создать не из чего.',
    'Не ВБ/Озон': 'Заказы не от ВБ/Озон — этим монитором не обрабатываются.',
    'Уже существуют': 'Возврат по заказу уже создан ранее.',
};

const RECENT_CHANGES_HINT =
    'Это журнал прошлых проверок за последние две недели, а не текущее состояние прямо сейчас. '
    + 'Находка остаётся видна тут, даже если вы уже что-то поправили вручную — просто как запись '
    + '«тогда-то робот это увидел». Со временем (когда пройдёт две недели с того прогона) запись '
    + 'сама пропадёт из списка.';

// Цифры — по дизайн-системе: сериф (Cormorant) weight 400, отрицательный трекинг, lining-nums
const numStyle = (color, size = 28) => ({
    fontFamily: 'var(--serif)', fontSize: size, fontWeight: 400, letterSpacing: '-0.02em',
    lineHeight: 1.15, color, fontVariantNumeric: 'lining-nums', fontFeatureSettings: '"lnum" 1',
});
const statLabelStyle = {
    fontFamily: 'var(--sans)', fontSize: 11, fontWeight: 500, letterSpacing: '0.1em',
    textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 8,
};
const TONE = {
    ok: 'var(--success)', critical: 'var(--error)', warning: 'var(--cat-orange)', neutral: 'var(--ink)',
};

/** Счётчики робота (Закупочные цены и т.п.) — только ненулевые, чтобы не было «Ошибки: 0». */
function StatsRow({ stats, onJump }) {
    const visible = stats.filter((s) => s.value > 0);
    if (visible.length === 0) return null;
    return (
        <div className="checks-stats-row">
            {visible.map((s, i) => {
                const color = TONE[s.tone] || TONE.neutral;
                const clickable = Boolean(s.cat);
                return (
                    <div key={i}
                        onClick={clickable ? () => onJump?.(s.cat) : undefined}
                        style={{
                            minWidth: 140, padding: '14px 18px', borderRadius: 12,
                            background: 'var(--surface-card)', border: '1px solid var(--hairline)',
                            cursor: clickable ? 'pointer' : 'default',
                        }}
                        title={clickable ? 'Показать подробности ниже' : undefined}>
                        <div style={{ ...statLabelStyle, display: 'flex', alignItems: 'center', gap: 6 }}>
                            <span>{s.label}</span>
                            {clickable && <span style={{ color: 'var(--primary)' }}>↓</span>}
                            {STAT_HINTS[s.label] && <span style={{ textTransform: 'none', letterSpacing: 0 }}><InfoTip text={STAT_HINTS[s.label]} width={230} /></span>}
                        </div>
                        <div style={numStyle(color)}>{s.value}</div>
                    </div>
                );
            })}
        </div>
    );
}
StatsRow.propTypes = { stats: PropTypes.array.isRequired, onJump: PropTypes.func };

// Плитки проверок хелс-чека: короткое имя; «что/как» — в подсказке по «i»
const TILE_META = {
    deviations: {
        label: 'FIFO',
        what: 'цена, по которой товар числится на складе, совпадает с ценой последней закупки',
        how: 'пишем словами, в какую сторону расхождение: «склад дороже закупки» — доедаем старую '
            + 'дорогую партию, «склад дешевле» — себестоимость вырастет, когда запас кончится',
    },
    negative_stock: {
        label: 'Остатки',
        what: 'нет товаров с минусовым остатком',
        how: 'минус физически невозможен — значит, ошибка в документах',
    },
    enters: {
        label: 'Оприходования',
        what: 'на внутренних складах нет лишних оприходований',
        how: 'товар туда попадает перемещением; оприходование — возможный дубль остатка',
    },
    enter_prices: {
        label: 'Цены',
        what: 'цены оприходований совпадают с приёмками',
        how: 'сверяем свежие оприходования с ценой приёмки на тот момент',
    },
    enter_zero: {
        label: 'Нулевые',
        what: 'нет оприходований с нулевой ценой',
        how: 'нулевая цена занижает себестоимость — прибыль в отчётах врёт',
    },
    losses: {
        label: 'Списания',
        what: 'списания оформлены корректно',
        how: 'ловим списания без описания, с нулевой ценой или без ячейки',
    },
    inventories: {
        label: 'Инвентаризации',
        what: 'инвентаризации закрыты: остатки исправлены, цены не нулевые',
        how: 'смотрим документы за 3 месяца; расхождение без корректировок — критично',
    },
    moves: {
        label: 'Перемещения',
        what: 'перемещения оформлены корректно',
        how: 'ловим без ячейки, нетипичное направление, крупные без описания',
    },
    supplies: {
        label: 'Приёмки',
        what: 'приёмки оформлены корректно',
        how: 'ловим нулевые цены, неожиданный склад, доставку отдельной позицией',
    },
    salesreturns: {
        label: 'Возвраты',
        what: 'возвраты покупателей не портят себестоимость',
        how: 'ловим возвраты с нулевой себестоимостью позиций',
    },
    supply_jumps: {
        label: 'Скачки',
        what: 'цены в приёмках без внезапных скачков',
        how: 'сравниваем цену последней приёмки со средней по трём прошлым; расхождение больше '
            + '15% — повод спросить, что именно закупили',
    },
    codes: {
        label: 'Коды',
        what: 'у товаров корректные коды',
        how: 'ловим отсутствующие, дубли и не по шаблону группы',
    },
    stale_drafts: {
        label: 'Черновики',
        what: 'нет забытых непроведённых документов',
        how: 'флагаем черновики, не тронутые дольше 7 дней',
    },
};

/** Сетка проверок хелс-чека: одно слово + «i» (что/как) + счёт. Клик по проблемной — к её таблице. */
function ChecksGrid({ checks, onJump }) {
    return (
        <div style={{
            display: 'grid', gap: 8, marginBottom: 18,
            gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))',
        }}>
            {checks.map((ch) => {
                const clean = ch.status === 'ok';
                const skipped = ch.status === 'skipped';
                const c = sevOf(ch.severity);
                const meta = TILE_META[ch.id] || {};
                const clickable = !clean && !skipped && ch.cats.length > 0;
                const hint = meta.what && (
                    <span><b>Что проверяем:</b> {meta.what}.<br /><b>Как:</b> {meta.how}.</span>
                );
                return (
                    <div key={ch.id}
                        onClick={clickable ? () => onJump?.(ch.cats[0]) : undefined}
                        title={clickable ? 'Показать находки ниже' : undefined}
                        style={{
                            display: 'flex', alignItems: 'center', gap: 7, padding: '8px 11px',
                            borderRadius: 10, border: '1px solid var(--hairline)',
                            background: clean ? 'var(--success-bg)' : skipped ? 'var(--surface-soft)' : c.bg,
                            cursor: clickable ? 'pointer' : 'default',
                            opacity: skipped ? 0.6 : 1,
                        }}>
                        <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink)', lineHeight: 1.25, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {meta.label || ch.title}
                        </span>
                        {hint && <InfoTip text={hint} width={260} />}
                        <span style={{ marginLeft: 'auto', fontSize: 12.5, fontWeight: 700, flexShrink: 0, color: clean ? 'var(--success)' : skipped ? 'var(--muted)' : c.color }}>
                            {clean ? '✓' : skipped ? '—' : ch.count}
                        </span>
                    </div>
                );
            })}
        </div>
    );
}
ChecksGrid.propTypes = { checks: PropTypes.array.isRequired, onJump: PropTypes.func };

function FindingRow({ cat, item, excepted, prevReason, onAdded, onDeleted }) {
    const [state, setState] = useState('idle'); // idle | reason | busy | added
    const [reason, setReason] = useState('');
    const [excId, setExcId] = useState(null);
    // Скачки цен: 'once' — глушит только этот скачок (по приёмке), 'always' — товар навсегда
    const [scope, setScope] = useState('once');
    const c = sevOf(item.severity);
    const link = item.ms_href || msLink(cat.ms_type, item.ms_id);
    const canExcept = cat.kind && item.key;
    const isJump = cat.kind === 'supply_jumps';

    const { deleting, trigger: handleDelete } = useConfirmDelete({
        confirm: item.delete_action?.confirm || `Удалить «${item.object}» из журнала?`,
        run: () => checksApi.deleteRecord(item.delete_action.url),
        onDone: onDeleted,
    });

    const add = async () => {
        setState('busy');
        try {
            let extra = {};
            if (cat.kind === 'deviations') {
                // deviation_pct — размер отклонения на момент разбора: вырастет заметно — снова флаг
                extra = { status: 'норма', ms_id: item.ms_id || '', ms_href: item.ms_href || '', deviation_pct: item.deviation_pct ?? null };
            }
            if (isJump && scope === 'once' && item.last_doc) extra = { supply_doc: item.last_doc };
            const res = await checksApi.addException({
                kind: cat.kind, key: item.key, label: item.object, reason: reason.trim(), extra,
            });
            setExcId(res.exception.id);
            setState('added');
            onAdded?.();
        } catch (e) { alert(e.message); setState('reason'); }
    };

    const undo = async () => {
        if (!excId) return;
        try { await checksApi.removeException(excId); setState('idle'); setExcId(null); onAdded?.(); }
        catch (e) { alert(e.message); }
    };

    if (state === 'added') {
        return (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, padding: '9px 14px', background: SEV.ok.bg }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontSize: 13, color: 'var(--success)', fontWeight: 600 }}>
                    <Check size={15} /> Добавлено в исключения — {item.object}
                    {reason.trim() && <span style={{ color: 'var(--muted)', fontWeight: 400 }}>({reason.trim()})</span>}
                </span>
                <Button variant="subtle" size="sm" icon={Undo2} onClick={undo}>Отменить</Button>
            </div>
        );
    }

    if (state === 'reason' || state === 'busy') {
        return (
            <div style={{ padding: '10px 14px', borderTop: '1px solid var(--hairline-soft)', background: 'var(--surface-soft)' }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)', marginBottom: 7 }}>
                    В исключения: {item.object}
                </div>
                {isJump && (
                    <div style={{ display: 'flex', gap: 14, marginBottom: 8, fontSize: 12.5, color: 'var(--body)', flexWrap: 'wrap' }}>
                        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 5, cursor: 'pointer' }}>
                            <input type="radio" checked={scope === 'once'} onChange={() => setScope('once')} />
                            Разовый случай — только этот скачок (приёмка №{item.last_doc || '?'})
                        </label>
                        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 5, cursor: 'pointer' }}>
                            <input type="radio" checked={scope === 'always'} onChange={() => setScope('always')} />
                            У товара всегда так — не проверять больше
                        </label>
                    </div>
                )}
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, flexWrap: 'wrap' }}>
                    <textarea
                        autoFocus
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                        rows={2}
                        placeholder="Причина: почему это не проблема?"
                        style={{
                            flex: 1, minWidth: 220, fontSize: 12.5, padding: '7px 9px', borderRadius: 8,
                            resize: 'vertical', border: '1px solid var(--primary)', background: 'var(--canvas)',
                            color: 'var(--body)', fontFamily: 'inherit',
                        }}
                    />
                    <div style={{ display: 'flex', gap: 6 }}>
                        <Button variant="primary" size="sm" icon={Plus} loading={state === 'busy'} onClick={add}>
                            Добавить
                        </Button>
                        <Button variant="subtle" size="sm" disabled={state === 'busy'} onClick={() => { setState('idle'); setReason(''); }}>
                            Отмена
                        </Button>
                    </div>
                </div>
            </div>
        );
    }

    // Строка находки: точка + объект + детали слитно в одну строку (перенос —
    // только у блока действий справа, на узких экранах он падает вниз)
    return (
        <div className="finding-row">
            <div className="finding-row__text">
                <span style={{ width: 7, height: 7, borderRadius: 999, background: c.color, flexShrink: 0 }} />
                <span style={{ fontSize: 13, lineHeight: 1.4, minWidth: 0 }}>
                    <span style={{ fontWeight: 600, color: 'var(--ink)' }}>{item.object}</span>
                    {item.detail && <span style={{ color: 'var(--body)' }}> · {item.detail}</span>}
                </span>
                {prevReason && (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--success)', lineHeight: 1.4 }}>
                        <ShieldCheck size={13} style={{ flexShrink: 0 }} />
                        уже разбирали: {prevReason}
                    </span>
                )}
            </div>
            <div className="finding-row__actions">
                {link && (
                    <Button as="a" variant="subtle" size="sm" icon={ExternalLink}
                        href={link} target="_blank" rel="noreferrer">
                        МС
                    </Button>
                )}
                {(item.links || []).map((l, i) => (
                    <Button key={i} as="a" variant="subtle" size="sm" icon={ExternalLink}
                        href={l.href} target="_blank" rel="noreferrer">
                        {l.label}
                    </Button>
                ))}
                {excepted ? (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--success)', fontWeight: 600 }}>
                        <ShieldCheck size={13} /> в исключениях
                    </span>
                ) : canExcept ? (
                    <Button variant="subtle" tone="accent" size="sm" icon={Plus} onClick={() => setState('reason')}>
                        в искл.
                    </Button>
                ) : null}
                {item.delete_action && (
                    <Button variant="subtle" tone="danger" size="sm" icon={Trash2} loading={deleting}
                        onClick={handleDelete} title="Убрать запись из журнала">
                        Удалить
                    </Button>
                )}
            </div>
        </div>
    );
}
FindingRow.propTypes = {
    cat: PropTypes.object, item: PropTypes.object, excepted: PropTypes.bool,
    prevReason: PropTypes.string, onAdded: PropTypes.func, onDeleted: PropTypes.func,
};

/** Секция находок одной проверки: проблемные развёрнуты, «норма» — свёрнута до строки. */
function Category({ cat, excKeys, excMap, onChanged }) {
    const [hidden, setHidden] = useState(new Set());
    // Списки длинные и почти всегда справочные — сворачиваем всё, разворачивает человек.
    // Открытыми оставляем только то, что требует действия прямо сейчас.
    const collapsible = true;
    const [open, setOpen] = useState(cat.severity === 'critical');
    const c = sevOf(cat.severity);

    const excFor = (it) => (cat.kind && it.key ? (excMap[cat.kind] || {})[it.key] : undefined);

    // ack-типы, уже добавленные в исключения, из снимка не показываем — при следующем
    // запуске скрипт их и так не выдаст; deviations остаются (помечаются бейджем).
    // Скачки цен: разовое исключение прячет только скачок своей приёмки — новый скачок
    // того же товара (другая приёмка) должен быть виден.
    const isAckExcepted = (it) => {
        if (!cat.kind || cat.kind === 'deviations') return false;
        const e = excFor(it);
        if (!e) return false;
        if (cat.kind === 'supply_jumps') return !e.supply_doc || e.supply_doc === it.last_doc;
        return true;
    };
    const visible = cat.items.filter((it) => !hidden.has(it.key || it.object) && !isAckExcepted(it));
    // Длинные списки — порциями, чтобы не скроллить экран бесконечно
    const PAGE = 20;
    const [shown, setShown] = useState(PAGE);
    // Все находки ушли в исключения — категория схлопывается целиком
    if (visible.length === 0) return null;

    const HeaderTag = collapsible ? 'button' : 'div';
    return (
        <div id={`cat-${cat.key}`} style={{ background: 'var(--surface-card)', border: '1px solid var(--hairline)', borderRadius: 12, marginBottom: 12, overflow: 'hidden' }}>
            <HeaderTag
                onClick={collapsible ? () => setOpen((v) => !v) : undefined}
                style={{
                    display: 'flex', alignItems: 'center', gap: 9, padding: '11px 14px', width: '100%',
                    background: 'none', border: 'none', textAlign: 'left',
                    cursor: collapsible ? 'pointer' : 'default',
                }}>
                {collapsible && (
                    <ChevronRight size={15} style={{ color: 'var(--muted-soft)', transform: open ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s', flexShrink: 0 }} />
                )}
                <span style={{ width: 9, height: 9, borderRadius: 999, background: c.color, flexShrink: 0 }} />
                <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink)' }}>{cat.title}</span>
                {CAT_HINTS[cat.key] && <InfoTip text={CAT_HINTS[cat.key]} width={330} />}
                <span style={{ marginLeft: 'auto', fontSize: 12, fontWeight: 700, color: c.color, background: c.bg, padding: '1px 9px', borderRadius: 999 }}>
                    {visible.length}
                </span>
            </HeaderTag>
            <div style={{ display: open ? 'block' : 'none' }}>
                {cat.note && (
                    <div style={{
                        padding: '9px 14px 11px', fontSize: 12.5, color: 'var(--muted)',
                        lineHeight: 1.5, borderBottom: '1px solid var(--hairline)',
                    }}>{cat.note}</div>
                )}
                {visible.slice(0, shown).map((it) => {
                    const ekey = it.key || it.object;
                    const excepted = cat.kind && it.key && (excKeys[cat.kind] || []).includes(it.key);
                    // Прошлый разбор этого товара: причина исключения прямо в находке
                    const prevReason = excFor(it)?.reason || '';
                    return (
                        <FindingRow
                            key={ekey}
                            cat={cat}
                            item={it}
                            excepted={excepted}
                            prevReason={prevReason}
                            onAdded={() => {
                                // ack-типы исчезают при следующем запуске — прячем сразу;
                                // deviations остаются (помечаются), не прячем
                                if (cat.kind && cat.kind !== 'deviations') {
                                    setHidden((s) => new Set(s).add(ekey));
                                }
                                onChanged?.();
                            }}
                            onDeleted={() => {
                                setHidden((s) => new Set(s).add(ekey));
                                onChanged?.();
                            }}
                        />
                    );
                })}
                {visible.length > shown && (
                    <button onClick={() => setShown((n) => n + PAGE)} style={{
                        width: '100%', padding: '9px 14px', border: 'none', borderTop: '1px solid var(--hairline-soft)',
                        background: 'var(--surface-soft)', color: 'var(--primary)', fontSize: 12.5, fontWeight: 600, cursor: 'pointer',
                    }}>
                        Показать ещё {Math.min(PAGE, visible.length - shown)} из {visible.length - shown} оставшихся
                    </button>
                )}
            </div>
        </div>
    );
}
Category.propTypes = { cat: PropTypes.object, excKeys: PropTypes.object, excMap: PropTypes.object, onChanged: PropTypes.func };

export default function HealthResults({ scriptId, runId, running, onExceptionChange }) {
    const [data, setData] = useState(undefined); // undefined=loading, null=нет данных
    const [refreshKey, setRefreshKey] = useState(0);

    const handleJump = (key) => {
        const el = document.getElementById(`cat-${key}`);
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    };

    const load = useCallback(async () => {
        try {
            const res = await checksApi.results(scriptId, runId);
            setData(res.results || null);
        } catch { setData(null); }
    }, [scriptId, runId]);

    useEffect(() => { load(); }, [load, refreshKey]);

    if (data === undefined) {
        return <div style={{ display: 'flex', gap: 8, color: 'var(--muted)', padding: 30, justifyContent: 'center' }}><Loader2 size={18} className="animate-spin" /> Загрузка…</div>;
    }
    if (data === null) {
        return (
            <div style={{ textAlign: 'center', padding: 50, color: 'var(--muted)' }}>
                {running ? 'Проверка выполняется — результаты появятся после завершения…' : 'Результатов пока нет. Запустите проверку.'}
            </div>
        );
    }

    const excKeys = data.exception_keys || {};
    const excMap = data.exceptions_map || {};
    const isRobot = Array.isArray(data.summary?.stats) && data.summary.stats.length > 0;
    // Возвраты ВБ/Озон: стат-карточки дублируют список ниже — прячем их (робот-режим
    // держится на наличии stats, поэтому саму строку скрываем на фронте, а не в бэке).
    const hideStats = scriptId === 'horsebio_returns';
    // Роботы: показываем слитые изменения за последние N дней (снимок одного запуска
    // почти всегда пуст — интересное случается раз в несколько дней).
    // Хелс-чек: снимок последнего запуска; «помечены нормой» — вниз.
    const robotCats = data.recent_changes || [];
    // view: 'snapshot' — скрипт просит показывать последний прогон, а не слепок за 14 дней.
    // Иначе цифры в плитках расходятся со списками, а устаревшие записи висят неделями.
    const snapshot = data.summary?.view === 'snapshot';
    const visibleCats = isRobot && !runId && !snapshot
        ? robotCats
        : [...data.categories.filter((c) => c.key !== 'pending_returns')]
            .sort((a, b) => (a.severity === 'ok') - (b.severity === 'ok'));
    return (
        <div>
            {runId && (
                <div style={{ fontSize: 12.5, color: 'var(--muted)', marginBottom: 12 }}>
                    Запуск {relTime(data.finished_at)} (исторический снимок)
                </div>
            )}
            {isRobot && !hideStats && <StatsRow stats={data.summary.stats} onJump={handleJump} />}
            {Array.isArray(data.summary?.checks) && data.summary.checks.length > 0 && (
                <ChecksGrid checks={data.summary.checks} onJump={handleJump} />
            )}
            {isRobot && !runId && !snapshot && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, fontWeight: 700, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--muted)', margin: '4px 0 10px' }}>
                    <span>Что робот делал за последние {data.recent_days || 14} дней</span>
                    <span style={{ textTransform: 'none', letterSpacing: 0 }}><InfoTip text={RECENT_CHANGES_HINT} width={280} /></span>
                </div>
            )}
            {visibleCats.length === 0 ? (
                <div style={{
                    maxWidth: 620, margin: '8px auto', padding: '26px 22px', textAlign: 'center',
                    background: 'var(--surface-card)', border: '1px solid var(--hairline)', borderRadius: 12,
                    color: 'var(--muted)', fontSize: 13.5, lineHeight: 1.6,
                }}>
                    <div style={{ color: 'var(--success)', fontWeight: 600, marginBottom: data.summary?.empty_note ? 8 : 0 }}>
                        ✓ Всё чисто
                    </div>
                    {data.summary?.empty_note
                        || (isRobot ? `Ничего не менялось за ${data.recent_days || 14} дней` : 'Проблем не найдено')}
                </div>
            ) : (
                visibleCats.map((cat) => (
                    <Category key={cat.key} cat={cat} excKeys={excKeys} excMap={excMap} onChanged={() => { setRefreshKey((k) => k + 1); onExceptionChange?.(); }} />
                ))
            )}
        </div>
    );
}


HealthResults.propTypes = {
    scriptId: PropTypes.string.isRequired,
    runId: PropTypes.string,
    running: PropTypes.bool,
    onExceptionChange: PropTypes.func,
};
