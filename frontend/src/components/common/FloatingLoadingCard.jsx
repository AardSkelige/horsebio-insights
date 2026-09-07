// src/components/common/FloatingLoadingCard.jsx
import { useState, useEffect, useRef } from 'react';
import { m } from 'motion/react';
import { CheckCircle2, Loader2, XCircle, AlertCircle, AlertTriangle, X, ChevronUp, ChevronDown, Database, Square } from 'lucide-react';
import { useLoading } from '../../contexts/LoadingContext';
import { formatDate } from '../../utils/formatters';

const toneSurface = (token, amount = 12) => `color-mix(in srgb, var(${token}) ${amount}%, transparent)`;
const toneBorder = (token, amount = 35) => `color-mix(in srgb, var(${token}) ${amount}%, var(--hairline))`;

const iconButtonStyle = {
    width: '28px',
    height: '28px',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    border: 'none',
    borderRadius: '8px',
    background: 'transparent',
    color: 'var(--muted)',
    cursor: 'pointer',
};

const FloatingLoadingCard = () => {
    const { 
        isLoading,
        loadingProgress,
        logs,
        progress,
        cancelLoading,
        resetStates,
        getProgressPercentage,
        getCurrentStage
    } = useLoading();
    
    const [isExpanded, setIsExpanded] = useState(false);
    const [isVisible, setIsVisible] = useState(true);
    const [isHiding, setIsHiding] = useState(false);
    const [isCompleted, setIsCompleted] = useState(false);
    const hideTimerRef = useRef(null);
    const resetTimerRef = useRef(null);

    // Сущности, которые не обновились. Прогон при этом мог кончиться
    // «частично»: остальное свежее, а эти остались вчерашними — и молчать
    // об этом нельзя, отчёты считаются уже на смеси.
    const failedEntities = (loadingProgress?.entities || []).filter(entity => entity.status === 'failed');
    const keepOpen = failedEntities.length > 0;

    const clearTimers = () => {
        if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
        if (resetTimerRef.current) clearTimeout(resetTimerRef.current);
        hideTimerRef.current = null;
        resetTimerRef.current = null;
    };

    // Автоматическое скрытие после завершения загрузки
    useEffect(() => {
        // Если загрузка завершена (isLoading = false) и есть данные прогресса
        if (!isLoading && loadingProgress && !isCompleted) {
            setIsCompleted(true);
        }
    }, [isLoading, loadingProgress, isCompleted]);

    // Отдельный useEffect для таймера скрытия
    useEffect(() => {
        // Карточку с несработавшими сущностями не прячем: это единственное
        // место, где написано, что именно осталось вчерашним, а три секунды
        // на прочитать список — не время. Закрывает её пользователь сам.
        if (isCompleted && !keepOpen) {
            // Показываем результат 3 секунды, затем плавно скрываем
            hideTimerRef.current = setTimeout(() => {
                setIsHiding(true);
                // После анимации скрытия полностью убираем компонент
                resetTimerRef.current = setTimeout(() => {
                    setIsVisible(false);
                    setIsHiding(false);
                    setIsCompleted(false);
                    resetStates();
                }, 500); // время анимации fade-out
            }, 3000); // показываем результат 3 секунды

            return () => {
                clearTimers();
            };
        }
    }, [isCompleted, keepOpen, resetStates]);

    // Сброс состояния завершения при новой загрузке
    useEffect(() => {
        if (isLoading) {
            clearTimers();
            setIsCompleted(false);
            setIsHiding(false);
        }
    }, [isLoading]);

    // Не показываем карточку если нет активной загрузки и нет результатов
    if (!isLoading && !loadingProgress) {
        return null;
    }

    // Если пользователь скрыл карточку
    if (!isVisible) {
        return (
            <div style={{ position: 'fixed', right: '20px', bottom: '20px', zIndex: 50 }}>
                <button
                    onClick={() => setIsVisible(true)}
                    style={{
                        width: '36px',
                        height: '36px',
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        border: '1px solid var(--hairline)',
                        borderRadius: '999px',
                        background: 'var(--canvas)',
                        color: 'var(--primary)',
                        boxShadow: 'var(--shadow-raised)',
                        cursor: 'pointer',
                    }}
                    title="Показать статус загрузки"
                >
                    <ChevronUp size={16} />
                </button>
            </div>
        );
    }

    const getStatusIcon = () => {
        if (!loadingProgress) return null;

        switch (loadingProgress.status) {
            case 'running':
                // Строка ещё говорит «идёт», а загрузка уже кончилась —
                // прогон закрылся между опросами.
                return isCompleted
                    ? <CheckCircle2 size={16} color="var(--success)" />
                    : <Loader2 size={16} color="var(--primary)" className="animate-spin" />;
            case 'completed':
                return <CheckCircle2 size={16} color="var(--success)" />;
            case 'partial':
                return <AlertTriangle size={16} color="var(--warning)" />;
            case 'error':
                return <XCircle size={16} color="var(--error)" />;
            default:
                return <AlertCircle size={16} color="var(--warning)" />;
        }
    };

    const getTone = () => {
        if (!loadingProgress) return '--primary';
        if (loadingProgress.status === 'error') return '--error';
        if (loadingProgress.status === 'partial' || loadingProgress.status === 'stopped') return '--warning';
        if (isCompleted || loadingProgress.status === 'completed') return '--success';
        return '--primary';
    };

    const getFinalMessage = () => {
        if (!loadingProgress) return 'Загрузка...';
        
        switch (loadingProgress.status) {
            case 'completed':
                return 'Загрузка завершена успешно!';
            case 'error':
                return 'Ошибка при загрузке';
            default:
                return loadingProgress.message || 'Загрузка...';
        }
    };

    const tone = getTone();

    return (
        <div style={{ position: 'fixed', right: '20px', bottom: '20px', zIndex: 50, width: 'min(380px, calc(100vw - 40px))' }}>
            <m.div
                initial={{ opacity: 0, y: 16, scale: 0.97 }}
                animate={isHiding ? { opacity: 0, y: 8, scale: 0.98 } : { opacity: 1, y: 0, scale: 1 }}
                transition={{ type: 'spring', stiffness: 350, damping: 26 }}
                style={{
                    border: `1px solid ${toneBorder(tone)}`,
                    borderRadius: '12px',
                    background: 'var(--canvas)',
                    boxShadow: 'var(--shadow-float)',
                    overflow: 'hidden',
                }}>
                {/* Header */}
                <div style={{ padding: '14px' }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '12px' }}>
                        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', minWidth: 0 }}>
                            <div style={{
                                width: '30px',
                                height: '30px',
                                display: 'inline-flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                borderRadius: '10px',
                                background: toneSurface(tone),
                                flexShrink: 0,
                            }}>
                                {getStatusIcon()}
                            </div>
                            <div style={{ minWidth: 0 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '2px' }}>
                                    <Database size={14} color="var(--muted)" />
                                    <span style={{ fontFamily: 'var(--sans)', fontSize: '13px', fontWeight: 500, color: 'var(--ink)' }}>
                                        Обработка данных
                                    </span>
                                </div>
                                <div style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--muted)', lineHeight: 1.35, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                    {isCompleted ? getFinalMessage() : (loadingProgress?.message || 'Загрузка...')}
                                </div>
                            </div>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '2px', flexShrink: 0 }}>
                            {isLoading && (
                                <button
                                    onClick={() => setIsExpanded(!isExpanded)}
                                    style={iconButtonStyle}
                                    title={isExpanded ? "Свернуть" : "Развернуть"}
                                >
                                    {isExpanded ? 
                                        <ChevronDown size={14} /> : 
                                        <ChevronUp size={14} />
                                    }
                                </button>
                            )}
                            <button
                                onClick={() => {
                                    setIsVisible(false);
                                    if (isCompleted) {
                                        setIsCompleted(false);
                                        resetStates();
                                    }
                                }}
                                style={iconButtonStyle}
                                title="Закрыть"
                            >
                                <X size={14} />
                            </button>
                        </div>
                    </div>

                    {/* Что осталось вчерашним. Показываем и в свёрнутой карточке:
                        это то, ради чего прогон вообще отмечен «частично». */}
                    {failedEntities.length > 0 && (
                        <div style={{
                            marginTop: '12px',
                            border: `1px solid ${toneBorder('--warning')}`,
                            borderRadius: '8px',
                            background: toneSurface('--warning'),
                            padding: '8px 10px',
                        }}>
                            <div style={{ fontFamily: 'var(--sans)', fontSize: '11px', color: 'var(--muted)', marginBottom: '4px' }}>
                                Не обновились
                            </div>
                            {failedEntities.map(entity => (
                                <div key={entity.entity} style={{ marginTop: '4px' }}>
                                    <div style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--ink)', fontWeight: 500 }}>
                                        {entity.name}
                                    </div>
                                    {entity.error && (
                                        <div style={{ fontFamily: 'var(--sans)', fontSize: '11px', color: 'var(--muted)', lineHeight: 1.35 }}>
                                            {entity.error}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Progress bar */}
                    {progress.total > 0 && !isCompleted && (
                        <div style={{ marginTop: '12px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'var(--sans)', fontSize: '11px', color: 'var(--muted)', marginBottom: '6px' }}>
                                <span>{progress.processed} / {progress.total}</span>
                                <span style={{ color: 'var(--ink)', fontWeight: 500 }}>{getProgressPercentage()}%</span>
                            </div>
                            <div style={{ height: '6px', background: 'var(--surface-card)', borderRadius: '999px', overflow: 'hidden' }}>
                                <div
                                    style={{
                                        height: '100%',
                                        width: `${getProgressPercentage()}%`,
                                        background: 'var(--primary)',
                                        borderRadius: '999px',
                                        transition: 'width 300ms ease',
                                    }}
                                />
                            </div>
                        </div>
                    )}
                </div>

                {/* Expanded content */}
                {isExpanded && (
                    <div style={{ borderTop: '1px solid var(--hairline)', padding: '12px 14px 14px' }}>
                        <div>
                            {/* Current stage - только во время загрузки */}
                            {!isCompleted && (
                                <div style={{ marginBottom: '10px' }}>
                                    <div style={{ fontFamily: 'var(--sans)', fontSize: '11px', color: 'var(--muted)', marginBottom: '2px' }}>Текущий этап</div>
                                    <div style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--ink)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{getCurrentStage()}</div>
                                </div>
                            )}

                            {/* Recent logs - только во время загрузки */}
                            {logs.length > 0 && !isCompleted && (
                                <div style={{ maxHeight: '160px', overflowY: 'auto' }}>
                                    <div style={{ fontFamily: 'var(--sans)', fontSize: '11px', color: 'var(--muted)', marginBottom: '6px' }}>Последние события</div>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                                        {logs.slice(-3).map((log, index) => (
                                            <div key={index} style={{ border: '1px solid var(--hairline)', borderRadius: '8px', background: 'var(--surface-soft)', padding: '7px 8px' }}>
                                                <div style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--ink)', fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{log.message}</div>
                                                <div style={{ fontFamily: 'var(--mono)', fontSize: '10px', color: 'var(--muted-soft)', marginTop: '3px' }}>
                                                    {formatDate(log.timestamp, true)}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Action buttons */}
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '12px', paddingTop: '10px', borderTop: '1px solid var(--hairline)' }}>
                                {isLoading ? (
                                    <button
                                        onClick={cancelLoading}
                                        style={{
                                            display: 'inline-flex',
                                            alignItems: 'center',
                                            gap: '5px',
                                            padding: '6px 10px',
                                            border: '1px solid var(--hairline)',
                                            borderRadius: '8px',
                                            background: 'var(--canvas)',
                                            color: 'var(--ink)',
                                            fontFamily: 'var(--sans)',
                                            fontSize: '12px',
                                            fontWeight: 500,
                                            cursor: 'pointer',
                                        }}
                                    >
                                        <Square size={11} />
                                        Остановить
                                    </button>
                                ) : (
                                    <button
                                        onClick={() => {
                                            setIsVisible(false);
                                            setIsCompleted(false);
                                            resetStates();
                                        }}
                                        style={{
                                            border: 'none',
                                            background: 'transparent',
                                            color: 'var(--muted)',
                                            fontFamily: 'var(--sans)',
                                            fontSize: '12px',
                                            fontWeight: 500,
                                            cursor: 'pointer',
                                        }}
                                    >
                                        Закрыть
                                    </button>
                                )}
                                
                                {progress.total > 0 && (
                                    <span style={{ fontFamily: 'var(--mono)', fontSize: '11px', color: 'var(--muted)' }}>
                                        {progress.processed} / {progress.total}
                                    </span>
                                )}
                            </div>
                        </div>
                    </div>
                )}
            </m.div>
        </div>
    );
};

export default FloatingLoadingCard;
