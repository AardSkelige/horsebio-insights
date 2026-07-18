import { useState, useEffect, useCallback } from 'react';
import PropTypes from 'prop-types';
import { ExternalLink, Plus, Check, Undo2, Loader2, ShieldCheck, ChevronRight } from 'lucide-react';
import { checksApi, SEV, sevOf, msLink, relTime } from './checksShared';
import InfoTip from './InfoTip';

// Подсказки по неочевидным категориям и стат-карточкам
const CAT_HINTS = {
    deviations_normal: 'Товары, у которых остаток на складе числится по одной цене (FIFO), а последняя закупка была по другой — но ты уже разбирался и подтвердил: это не ошибка, обычно на складе просто лежат старые партии по прошлой цене. Если после разбора расхождение заметно вырастет, товар автоматически вернётся в проблемные.',
};
const STAT_HINTS = {
    'Уже актуальны': 'Цены уже совпадают с FIFO — обновление не требуется.',
    'Себестоимость 0': 'Товары с нулевой себестоимостью — пропущены.',
    'Нет остатков': 'Нет остатков или FIFO = 0 — пропущены.',
    'Нет отгрузки': 'Заказ есть, но отгрузки нет — возврат создать не из чего.',
    'Не ВБ/Озон': 'Заказы не от ВБ/Озон — этим монитором не обрабатываются.',
    'Уже существуют': 'Возврат по заказу уже создан ранее.',
};

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
    ok: 'var(--success)', critical: 'var(--error)', warning: '#c47d2f', neutral: 'var(--ink)',
};

/** Счётчики робота (Закупочные цены и т.п.) — только ненулевые, чтобы не было «Ошибки: 0». */
function StatsRow({ stats, onJump }) {
    const visible = stats.filter((s) => s.value > 0);
    if (visible.length === 0) return null;
    return (
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 18 }}>
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
        what: 'себестоимость остатка совпадает с ценой последней приёмки',
        how: 'сравниваем FIFO с приёмкой; сильное расхождение — ошибка в документах или реально новые цены',
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
        how: 'сравниваем последнюю приёмку со средней по прошлым; скачок >15% — вопрос',
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
                            background: clean ? 'rgba(93,184,114,0.07)' : skipped ? 'var(--surface-soft)' : c.bg,
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

function FindingRow({ cat, item, excepted, prevReason, onAdded }) {
    const [state, setState] = useState('idle'); // idle | reason | busy | added
    const [reason, setReason] = useState('');
    const [excId, setExcId] = useState(null);
    // Скачки цен: 'once' — глушит только этот скачок (по приёмке), 'always' — товар навсегда
    const [scope, setScope] = useState('once');
    const c = sevOf(item.severity);
    const link = item.ms_href || msLink(cat.ms_type, item.ms_id);
    const canExcept = cat.kind && item.key;
    const isJump = cat.kind === 'supply_jumps';

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
                <button onClick={undo} style={linkBtn('var(--muted)')}>
                    <Undo2 size={13} /> Отменить
                </button>
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
                        <button onClick={add} disabled={state === 'busy'} style={{ ...linkBtn('var(--on-primary, #fff)'), background: 'var(--primary)', padding: '7px 12px' }}>
                            {state === 'busy' ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />} Добавить
                        </button>
                        <button onClick={() => { setState('idle'); setReason(''); }} disabled={state === 'busy'} style={{ ...linkBtn('var(--muted)'), padding: '7px 12px' }}>
                            Отмена
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    // Табличная строка: объект | детали | действия
    return (
        <div style={{
            display: 'grid', gridTemplateColumns: 'minmax(120px, 200px) minmax(0, 1fr) auto',
            alignItems: 'start', gap: 12,
            padding: '9px 14px', borderTop: '1px solid var(--hairline-soft)', background: 'var(--canvas)',
        }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', minWidth: 0 }}>
                <span style={{ width: 7, height: 7, borderRadius: 999, background: c.color, marginTop: 5, flexShrink: 0 }} />
                <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)', lineHeight: 1.4, minWidth: 0 }}>{item.object}</span>
            </div>
            <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 12.5, color: 'var(--body)', lineHeight: 1.45 }}>{item.detail}</div>
                {prevReason && (
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 5, fontSize: 12, color: 'var(--success)', marginTop: 3, lineHeight: 1.4 }}>
                        <ShieldCheck size={13} style={{ flexShrink: 0, marginTop: 1 }} />
                        <span>уже разбирали: {prevReason}</span>
                    </div>
                )}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                {link && (
                    <a href={link} target="_blank" rel="noreferrer" style={linkBtn('var(--muted)')}>
                        <ExternalLink size={13} /> МС
                    </a>
                )}
                {excepted ? (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--success)', fontWeight: 600 }}>
                        <ShieldCheck size={13} /> в исключениях
                    </span>
                ) : canExcept ? (
                    <button onClick={() => setState('reason')} style={linkBtn('var(--primary)')}>
                        <Plus size={13} /> в искл.
                    </button>
                ) : null}
            </div>
        </div>
    );
}
FindingRow.propTypes = { cat: PropTypes.object, item: PropTypes.object, excepted: PropTypes.bool, prevReason: PropTypes.string, onAdded: PropTypes.func };

/** Секция находок одной проверки: проблемные развёрнуты, «норма» — свёрнута до строки. */
function Category({ cat, excKeys, excMap, onChanged }) {
    const [hidden, setHidden] = useState(new Set());
    const collapsible = cat.severity === 'ok';
    const [open, setOpen] = useState(!collapsible);
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
                {CAT_HINTS[cat.key] && <InfoTip text={CAT_HINTS[cat.key]} />}
                <span style={{ marginLeft: 'auto', fontSize: 12, fontWeight: 700, color: c.color, background: c.bg, padding: '1px 9px', borderRadius: 999 }}>
                    {visible.length}
                </span>
            </HeaderTag>
            <div style={{ display: open ? 'block' : 'none' }}>
                {visible.map((it) => {
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
                        />
                    );
                })}
            </div>
        </div>
    );
}
Category.propTypes = { cat: PropTypes.object, excKeys: PropTypes.object, excMap: PropTypes.object, onChanged: PropTypes.func };

export default function HealthResults({ scriptId, runId, running }) {
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
    // Возвраты в пути — не находки чека, показываются отдельной строкой на /checks;
    // «помечены нормой» — вниз, сначала реальные проблемы
    const visibleCats = [...data.categories.filter((c) => c.key !== 'pending_returns')]
        .sort((a, b) => (a.severity === 'ok') - (b.severity === 'ok'));
    const isRobot = Array.isArray(data.summary?.stats) && data.summary.stats.length > 0;
    return (
        <div>
            {runId && (
                <div style={{ fontSize: 12.5, color: 'var(--muted)', marginBottom: 12 }}>
                    Запуск {relTime(data.finished_at)} (исторический снимок)
                </div>
            )}
            {isRobot && <StatsRow stats={data.summary.stats} onJump={handleJump} />}
            {Array.isArray(data.summary?.checks) && data.summary.checks.length > 0 && (
                <ChecksGrid checks={data.summary.checks} onJump={handleJump} />
            )}
            {visibleCats.length === 0 ? (
                <div style={{ textAlign: 'center', padding: 32, color: isRobot ? 'var(--muted)' : 'var(--success)', fontWeight: isRobot ? 400 : 600 }}>
                    {isRobot ? 'Изменений нет — всё актуально' : '✓ Проблем не найдено'}
                </div>
            ) : (
                visibleCats.map((cat) => (
                    <Category key={cat.key} cat={cat} excKeys={excKeys} excMap={excMap} onChanged={() => setRefreshKey((k) => k + 1)} />
                ))
            )}
        </div>
    );
}

function linkBtn(color) {
    return {
        display: 'inline-flex', alignItems: 'center', gap: 4, padding: '4px 9px', borderRadius: 7,
        background: 'var(--surface-soft)', border: 'none', color, fontSize: 12, fontWeight: 600,
        cursor: 'pointer', textDecoration: 'none', whiteSpace: 'nowrap',
    };
}

HealthResults.propTypes = {
    scriptId: PropTypes.string.isRequired,
    runId: PropTypes.string,
    running: PropTypes.bool,
};
