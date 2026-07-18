import { useState } from 'react';
import PropTypes from 'prop-types';
import { ChevronDown, ChevronUp } from 'lucide-react';

function fmt(dateStr) {
    if (!dateStr) return '—';
    const d = new Date(dateStr);
    return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

export default function CellsInfoPanel({ cellsLog, selectedMonth, isMobile }) {
    const [open, setOpen] = useState(false);

    // Filter to selected month if chosen, otherwise show all
    const logForMonth = selectedMonth
        ? cellsLog.filter(e => e.month_start?.slice(0, 7) === selectedMonth)
        : cellsLog;

    const lastEntry = logForMonth.length
        ? logForMonth[logForMonth.length - 1]
        : null;

    const hasAny = logForMonth.length > 0;

    return (
        <div style={{
            border: '1px solid var(--hairline)',
            borderRadius: 12,
            marginBottom: 24,
            overflow: 'hidden',
            background: 'var(--surface-card)',
        }}>
            {/* ── Header — always visible ── */}
            <button
                onClick={() => setOpen(v => !v)}
                className="no-tap-scale"
                style={{
                    width: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 12,
                    padding: '12px 20px',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    textAlign: 'left',
                }}
            >
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
                    <span style={{
                        fontFamily: 'var(--sans)',
                        fontSize: 13,
                        fontWeight: 500,
                        color: 'var(--ink)',
                        flexShrink: 0,
                    }}>
                        Инвентаризации с ячейками
                    </span>
                    {hasAny ? (
                        <span style={{
                            fontFamily: 'var(--sans)',
                            fontSize: 12,
                            color: 'var(--muted)',
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                        }}>
                            {logForMonth.length === 1
                                ? `загружена 1 — №${lastEntry.inventory_name} от ${fmt(lastEntry.inventory_date)}`
                                : `загружено ${logForMonth.length} — последняя №${lastEntry.inventory_name} от ${fmt(lastEntry.inventory_date)}`
                            }
                        </span>
                    ) : (
                        <span style={{
                            fontFamily: 'var(--sans)',
                            fontSize: 12,
                            color: 'var(--muted-soft)',
                        }}>
                            ещё не загружено
                        </span>
                    )}
                </div>
                {open
                    ? <ChevronUp size={15} color="var(--muted)" style={{ flexShrink: 0 }} />
                    : <ChevronDown size={15} color="var(--muted)" style={{ flexShrink: 0 }} />
                }
            </button>

            {/* ── Expanded body ── */}
            {open && (
                <div style={{ padding: '0 20px 16px', borderTop: '1px solid var(--hairline-soft)' }}>

                    {/* Instruction */}
                    <div style={{ paddingTop: 14, marginBottom: hasAny ? 16 : 0 }}>
                        <p style={{
                            fontFamily: 'var(--sans)',
                            fontSize: 13,
                            color: 'var(--body)',
                            margin: '0 0 8px',
                            lineHeight: 1.55,
                        }}>
                            МойСклад не отдаёт инвентаризации с ячейками через API — их нужно выгружать вручную.
                        </p>
                        <ol style={{
                            fontFamily: 'var(--sans)',
                            fontSize: 13,
                            color: 'var(--body)',
                            margin: 0,
                            paddingLeft: 18,
                            lineHeight: 1.7,
                        }}>
                            <li>Зайди в МойСклад → <b>Склад → Инвентаризации</b></li>
                            <li>Отфильтруй по типу документа: <b>«Инвентаризация с ячейками»</b></li>
                            <li>Выбери нужные документы (можно несколько)</li>
                            <li>Нажми <b>Печать → «Инвентаризация с ячейками»</b> — скачается <code style={{ fontFamily: 'monospace', fontSize: 12, background: 'var(--hairline-soft)', padding: '1px 5px', borderRadius: 4 }}>.xls</code> файл на каждую</li>
                            <li>Загрузи файлы кнопкой <b>«С ячейками»</b> — можно сразу несколько</li>
                        </ol>
                    </div>

                    {/* Uploaded log table */}
                    {hasAny && (
                        <div>
                            <p style={{
                                fontFamily: 'var(--sans)',
                                fontSize: 12,
                                fontWeight: 500,
                                color: 'var(--muted)',
                                margin: '0 0 8px',
                                textTransform: 'uppercase',
                                letterSpacing: '0.05em',
                            }}>
                                Уже загружено{selectedMonth ? ` за ${selectedMonth}` : ''}
                            </p>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                {logForMonth.map(entry => (
                                    <div key={entry.id} style={{
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: isMobile ? 8 : 16,
                                        flexWrap: 'wrap',
                                        padding: '6px 10px',
                                        background: 'var(--canvas)',
                                        borderRadius: 8,
                                        border: '1px solid var(--hairline-soft)',
                                    }}>
                                        <span style={{
                                            fontFamily: 'var(--sans)',
                                            fontSize: 13,
                                            fontWeight: 500,
                                            color: 'var(--ink)',
                                            minWidth: 52,
                                        }}>
                                            №{entry.inventory_name}
                                        </span>
                                        <span style={{
                                            fontFamily: 'var(--sans)',
                                            fontSize: 13,
                                            color: 'var(--body)',
                                        }}>
                                            {fmt(entry.inventory_date)}
                                        </span>
                                        {!isMobile && (
                                            <span style={{
                                                fontFamily: 'var(--sans)',
                                                fontSize: 12,
                                                color: 'var(--muted)',
                                                flex: 1,
                                                whiteSpace: 'nowrap',
                                                overflow: 'hidden',
                                                textOverflow: 'ellipsis',
                                            }}>
                                                {entry.warehouse}
                                            </span>
                                        )}
                                        <span style={{
                                            fontFamily: 'var(--sans)',
                                            fontSize: 12,
                                            color: 'var(--muted)',
                                            marginLeft: 'auto',
                                            flexShrink: 0,
                                        }}>
                                            {entry.matched_count} поз · загружено {fmt(entry.uploaded_at)}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

CellsInfoPanel.propTypes = {
    cellsLog: PropTypes.arrayOf(PropTypes.object).isRequired,
    selectedMonth: PropTypes.string,
    isMobile: PropTypes.bool,
};
