import { useState, useEffect, useCallback } from 'react';
import PropTypes from 'prop-types';
import { Search, Trash2, Loader2, Pencil, Check, X, ExternalLink, ChevronRight } from 'lucide-react';
import { checksApi, KIND_MS_TYPE, KIND_BADGE, msLink } from './checksShared';

const STATUS_COLOR = {
    'норма': '#5db872', 'исправлено': '#5c8acc', 'ошибка': '#c64545', 'ошибка-некритично': '#c47d2f',
};

// Типы, чьи исключения привязаны к документу (а не к товару)
const DOC_KINDS = new Set(['enters', 'losses', 'inventories', 'moves', 'supplies', 'salesreturns', 'enter_zero']);
// Окно сканирования документных проверок (doc_months = 3)
const SCAN_WINDOW_DAYS = 90;

function StatusBadge({ status }) {
    const c = STATUS_COLOR[status] || 'var(--muted)';
    return (
        <span style={{ fontSize: 11, fontWeight: 600, color: c, background: `${c}1a`, padding: '2px 9px', borderRadius: 6, whiteSpace: 'nowrap' }}>{status}</span>
    );
}
StatusBadge.propTypes = { status: PropTypes.string };

function shortDate(s) {
    if (!s) return '';
    const m = s.match(/(\d{4})-(\d{2})-(\d{2})/);
    return m ? `${m[3]}.${m[2]}.${m[1]}` : s;
}

function docDateOf(exc) {
    return exc.extra?.date || exc.extra?.doc_date || '';
}

/** Документ вышел из окна сканирования — исключение больше ничего не глушит. */
function isExpired(exc) {
    if (!DOC_KINDS.has(exc.kind)) return false;
    const d = docDateOf(exc);
    if (!d) return false;
    const parsed = new Date(d);
    if (Number.isNaN(parsed.getTime())) return false;
    return (Date.now() - parsed.getTime()) / 86400000 > SCAN_WINDOW_DAYS;
}

const chip = (color = 'var(--muted)') => ({
    fontSize: 11, fontWeight: 600, color, background: 'var(--surface-soft)',
    padding: '2px 8px', borderRadius: 6, whiteSpace: 'nowrap',
});

function ExceptionRow({ exc, first, onSaved, onRemove }) {
    const [editing, setEditing] = useState(false);
    const [value, setValue] = useState(exc.reason || '');
    const [saving, setSaving] = useState(false);
    const docLink = exc.kind === 'deviations'
        ? (exc.extra?.ms_href || null)
        : msLink(KIND_MS_TYPE[exc.kind], exc.key);
    const status = exc.kind === 'deviations' ? exc.extra?.status : null;
    // Скачки цен: разовое исключение (одна приёмка) или постоянное (товар не проверяется)
    const jumpScope = exc.kind === 'supply_jumps'
        ? (exc.extra?.supply_doc ? `разовое (приёмка №${exc.extra.supply_doc})` : 'постоянное')
        : null;
    const isDoc = DOC_KINDS.has(exc.kind);
    // У документов единый вид номера: «№00051» независимо от того, как записан label
    const rawLabel = exc.label || exc.key;
    const label = isDoc && rawLabel && !rawLabel.startsWith('№') ? `№${rawLabel}` : rawLabel;
    const docDate = docDateOf(exc);
    const expired = isExpired(exc);

    const save = async () => {
        setSaving(true);
        try { await checksApi.updateException(exc.id, { reason: value }); setEditing(false); onSaved?.(); }
        catch (e) { alert(e.message); }
        finally { setSaving(false); }
    };

    return (
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, padding: '12px 16px', borderTop: first ? 'none' : '1px solid var(--hairline-soft)', opacity: expired ? 0.65 : 1 }}>
            <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink)' }}>{label}</span>
                    {status && <StatusBadge status={status} />}
                    {jumpScope && (
                        <span style={chip(exc.extra?.supply_doc ? 'var(--muted)' : '#b08a1f')}
                            title={exc.extra?.supply_doc
                                ? 'Заглушен только этот скачок: новая приёмка с новым скачком снова попадёт в отчёт'
                                : 'Товар исключён из проверки скачков полностью — цены по нему всегда пляшут'}>
                            {jumpScope}
                        </span>
                    )}
                    {docDate && <span style={chip()}>документ от {shortDate(docDate)}</span>}
                    <span style={chip()} title={exc.created_by ? `добавил ${exc.created_by}` : ''}>
                        вердикт от {shortDate(exc.created_at)}
                    </span>
                    {expired && (
                        <span style={chip('var(--muted-soft)')}
                            title={`Документ старше ${SCAN_WINDOW_DAYS} дней и больше не попадает в проверку — исключение ничего не глушит и скоро удалится автоматически`}>
                            отработало
                        </span>
                    )}
                    {docLink && (
                        <a href={docLink} target="_blank" rel="noreferrer"
                            style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 11.5, color: 'var(--primary)', textDecoration: 'none' }}>
                            <ExternalLink size={12} /> {exc.kind === 'deviations' ? 'товар' : 'документ'}
                        </a>
                    )}
                </div>

                {editing ? (
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 6, marginTop: 7 }}>
                        <textarea autoFocus value={value} onChange={(e) => setValue(e.target.value)} rows={2}
                            style={{ flex: 1, fontSize: 12.5, padding: '7px 9px', borderRadius: 8, resize: 'vertical', border: '1px solid var(--primary)', background: 'var(--canvas)', color: 'var(--body)', fontFamily: 'inherit' }} />
                        <button onClick={save} disabled={saving} style={iconBtn('var(--success)')}>{saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}</button>
                        <button onClick={() => { setEditing(false); setValue(exc.reason || ''); }} style={iconBtn('var(--muted)')}><X size={14} /></button>
                    </div>
                ) : (
                    <div style={{ fontSize: 12.5, color: exc.reason ? 'var(--body)' : 'var(--muted-soft)', marginTop: 4, lineHeight: 1.5 }}>
                        {exc.reason || 'без причины'}
                    </div>
                )}
            </div>

            {!editing && (
                <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                    <button onClick={() => setEditing(true)} style={iconBtn('var(--muted)')} title="Изменить причину"><Pencil size={14} /></button>
                    <button onClick={() => onRemove(exc.id)} style={iconBtn('var(--error)')} title="Убрать исключение"><Trash2 size={14} /></button>
                </div>
            )}
        </div>
    );
}
ExceptionRow.propTypes = { exc: PropTypes.object, first: PropTypes.bool, onSaved: PropTypes.func, onRemove: PropTypes.func };

function Group({ group, defaultOpen, onSaved, onRemove }) {
    const [open, setOpen] = useState(defaultOpen);
    const dot = KIND_BADGE[group.kind] || 'var(--muted)';
    return (
        <section style={{ background: 'var(--surface-card)', border: '1px solid var(--hairline)', borderRadius: 12, marginBottom: 10, overflow: 'hidden' }}>
            <button onClick={() => setOpen((v) => !v)} style={{
                width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '13px 16px',
                background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left',
            }}>
                <ChevronRight size={16} style={{ color: 'var(--muted-soft)', transform: open ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s' }} />
                <span style={{ width: 8, height: 8, borderRadius: 999, background: dot, flexShrink: 0 }} />
                <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink)' }}>{group.label}</span>
                <span style={{ marginLeft: 'auto', fontSize: 12.5, fontWeight: 600, color: 'var(--muted)', background: 'var(--surface-soft)', padding: '2px 10px', borderRadius: 999 }}>{group.items.length}</span>
            </button>
            {open && group.items.map((e, i) => (
                <ExceptionRow key={e.id} exc={e} first={i === 0} onSaved={onSaved} onRemove={onRemove} />
            ))}
        </section>
    );
}
Group.propTypes = { group: PropTypes.object, defaultOpen: PropTypes.bool, onSaved: PropTypes.func, onRemove: PropTypes.func };

export default function ExceptionsPanel() {
    const [items, setItems] = useState(null);
    const [query, setQuery] = useState('');

    const load = useCallback(async () => {
        try { const res = await checksApi.listExceptions(); setItems(res.exceptions); }
        catch { setItems([]); }
    }, []);
    useEffect(() => { load(); }, [load]);

    const remove = async (id) => {
        if (!confirm('Убрать исключение? Находка снова появится в результатах.')) return;
        try { await checksApi.removeException(id); setItems((arr) => arr.filter((e) => e.id !== id)); }
        catch (e) { alert(e.message); }
    };

    if (items === null) {
        return <div style={{ display: 'flex', gap: 8, color: 'var(--muted)', padding: 30, justifyContent: 'center' }}><Loader2 size={18} className="animate-spin" /> Загрузка…</div>;
    }

    const q = query.trim().toLowerCase();
    const filtered = q ? items.filter((e) => `${e.label} ${e.key} ${e.reason} ${e.kind_label}`.toLowerCase().includes(q)) : items;

    const groups = [];
    filtered.forEach((e) => {
        let g = groups.find((x) => x.kind === e.kind);
        if (!g) { g = { kind: e.kind, label: e.kind_label, items: [] }; groups.push(g); }
        g.items.push(e);
    });

    const expiredCount = items.filter(isExpired).length;

    return (
        <div>
            <div style={{
                fontSize: 12.5, color: 'var(--muted)', lineHeight: 1.55, marginBottom: 14,
                padding: '10px 14px', background: 'var(--surface-soft)', borderRadius: 10,
            }}>
                Это твои вердикты по находкам: проверка читает их перед каждым запуском, чтобы не показывать
                уже разобранное. Сюда заходят только перечитать или отменить вердикт — делать здесь ничего
                не нужно. Записи с бейджем «отработало» уже ничего не глушат и удалятся автоматически.
            </div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
                <div style={{ position: 'relative', flex: 1, minWidth: 220, maxWidth: 380 }}>
                    <Search size={15} style={{ position: 'absolute', left: 11, top: 10, color: 'var(--muted-soft)' }} />
                    <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Поиск по исключениям…"
                        style={{ width: '100%', padding: '8px 12px 8px 34px', borderRadius: 9, fontSize: 13, border: '1px solid var(--hairline)', background: 'var(--canvas)', color: 'var(--body)' }} />
                </div>
                <span style={{ fontSize: 13, color: 'var(--muted)' }}>
                    Всего: {items.length}
                    {expiredCount > 0 && <span style={{ color: 'var(--muted-soft)' }}> · отработало: {expiredCount}</span>}
                </span>
            </div>

            {groups.length === 0 ? (
                <div style={{ textAlign: 'center', padding: 40, color: 'var(--muted)' }}>{q ? 'Ничего не найдено' : 'Исключений пока нет'}</div>
            ) : (
                groups.map((g) => (
                    <Group key={g.kind} group={g} defaultOpen={Boolean(q)} onSaved={load} onRemove={remove} />
                ))
            )}
        </div>
    );
}

function iconBtn(color) {
    return {
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 30, height: 30,
        borderRadius: 8, background: 'var(--surface-soft)', border: 'none', color, cursor: 'pointer', flexShrink: 0,
    };
}
