// frontend/src/components/home/components/LoadingProgress.jsx

import { useState, useEffect, useRef, useCallback } from 'react';
import PropTypes from 'prop-types';
import { formatDate } from '../../../utils/formatters';
import { 
    CheckCircle2, 
    Clock, 
    Pause, 
    AlertCircle, 
    Loader2, 
    ArrowDown,
    Database
} from 'lucide-react';

const messageThrottleTime = 1000;

const LoadingProgress = ({ logs, progress, setLogs, setProgress, onComplete, onProgressUpdate, onCancel }) => {
    const [autoScroll, setAutoScroll] = useState(true);
    const logsContainerRef = useRef(null);
    const userScrolling = useRef(false);
    const lastScrollPosition = useRef(0);
    const eventSourceRef = useRef(null);
    const lastMessageTimestamps = useRef(new Map());

    const cleanupEventSource = useCallback(() => {
        if (eventSourceRef.current) {
            eventSourceRef.current.close();
            eventSourceRef.current = null;
        }
    }, []);


    const scrollToBottom = useCallback(() => {
        if (logsContainerRef.current && autoScroll) {
            const { scrollHeight } = logsContainerRef.current;
            logsContainerRef.current.scrollTo({
                top: scrollHeight,
                behavior: 'smooth'
            });
        }
    }, [autoScroll]);

    const handleScroll = useCallback(() => {
        if (!logsContainerRef.current || !userScrolling.current) return;

        const { scrollTop, scrollHeight, clientHeight } = logsContainerRef.current;
        const isAtBottom = scrollTop + clientHeight >= scrollHeight - 10;

        if (isAtBottom) {
            setAutoScroll(true);
        } else if (scrollTop < lastScrollPosition.current) {
            setAutoScroll(false);
        }

        lastScrollPosition.current = scrollTop;
    }, []);

    const handleScrollStart = () => {
        userScrolling.current = true;
    };

    const handleScrollEnd = () => {
        userScrolling.current = false;
        if (logsContainerRef.current) {
            const { scrollTop, scrollHeight, clientHeight } = logsContainerRef.current;
            if (scrollTop + clientHeight >= scrollHeight - 10) {
                setAutoScroll(true);
            }
        }
    };

    useEffect(() => {
        scrollToBottom();
    }, [logs, scrollToBottom]);

    useEffect(() => {
        let isMounted = true;

        const handleStreamMessage = (event) => {
            if (!isMounted) return;

            try {
                const data = JSON.parse(event.data);

                // Создаем уникальный ключ для сообщения
                const messageKey = `${data.message}${data.details || ''}`;
                const currentTime = Date.now();
                const lastTime = lastMessageTimestamps.current.get(messageKey);

                // Проверяем, не слишком ли рано для нового сообщения
                if (lastTime && (currentTime - lastTime < messageThrottleTime)) {
                    return;
                }

                // Обновляем время последнего сообщения
                lastMessageTimestamps.current.set(messageKey, currentTime);

                const newLog = {
                    timestamp: data.timestamp || new Date().toISOString(),
                    message: data.message || 'Загрузка завершена',
                    details: data.details,
                    status: data.status
                };

                setLogs(prevLogs => {
                    // Проверяем последнее сообщение
                    const lastLog = prevLogs[prevLogs.length - 1];
                    if (lastLog &&
                        lastLog.message === newLog.message &&
                        lastLog.details === newLog.details) {
                        return prevLogs;
                    }

                    const newLogs = [...prevLogs, newLog];
                    return newLogs.slice(-100); // Сохраняем только последние 100 сообщений
                });

                // Проверяем статус завершения
                if (data.status === 'completed' || data.status === 'error' || data.status === 'stopped') {
                    setProgress({ processed: 0, total: 0 });
                    cleanupEventSource();

                    if (onComplete) {
                        window.setTimeout(() => {
                            if (isMounted) {
                                onComplete(data.status);
                            }
                        }, 500);
                    }
                    return;
                }

                // Обновляем прогресс
                if (data.processed !== undefined && data.total !== undefined) {
                    setProgress({
                        processed: data.processed,
                        total: data.total
                    });
                    if (onProgressUpdate) {
                        onProgressUpdate(data);
                    }
                }
            } catch (error) {
                console.error('Error parsing SSE message:', error);
            }
        };

        try {
            if (!eventSourceRef.current) {
                eventSourceRef.current = new EventSource('/parser/stream-progress/');
                eventSourceRef.current.onmessage = handleStreamMessage;
                eventSourceRef.current.onerror = (error) => {
                    console.error('SSE Error:', error);
                    if (eventSourceRef.current?.readyState === EventSource.CLOSED) {
                        return;
                    }
                    if (onComplete) {
                        onComplete('error');
                    }
                };
            }
        } catch (err) {
            console.error('Error setting up SSE:', err);
            if (onComplete) {
                onComplete('error');
            }
        }

        return () => {
            isMounted = false;
            cleanupEventSource();
        };
    }, [onCancel, onComplete, onProgressUpdate]); // eslint-disable-line react-hooks/exhaustive-deps

    const getStatusIcon = (status, message) => {
        // Определяем статус по содержимому сообщения
        if (message?.includes('✅') || status === 'completed') {
            return <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0" />;
        }
        if (message?.includes('⏳') || message?.includes('Обработка')) {
            return <Loader2 className="w-4 h-4 text-blue-500 animate-spin flex-shrink-0" />;
        }
        if (message?.includes('⏸️') || message?.includes('Ожидание')) {
            return <Pause className="w-4 h-4 text-orange-500 flex-shrink-0" />;
        }
        if (status === 'error') {
            return <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0" />;
        }
        return <Clock className="w-4 h-4 text-gray-500 flex-shrink-0" />;
    };

    const getStatusStyle = (status, message) => {
        if (message?.includes('✅') || status === 'completed') {
            return 'text-green-700 bg-green-50 border-l-green-400';
        }
        if (message?.includes('⏳') || message?.includes('Обработка')) {
            return 'text-blue-700 bg-blue-50 border-l-blue-400';
        }
        if (message?.includes('⏸️') || message?.includes('Ожидание')) {
            return 'text-orange-700 bg-orange-50 border-l-orange-400';
        }
        if (status === 'error') {
            return 'text-red-700 bg-red-50 border-l-red-400';
        }
        return 'text-gray-700 bg-gray-50 border-l-gray-400';
    };

    const getCurrentStage = () => {
        if (logs.length === 0) return 'Подготовка к загрузке...';
        const lastLog = logs[logs.length - 1];
        return lastLog.message || 'Обработка данных';
    };

    const getProgressPercentage = () => {
        if (progress.total === 0) return 0;
        return Math.round((progress.processed / progress.total) * 100);
    };

    return (
        <div className="bg-white rounded-xl shadow-sm border overflow-hidden">
            {/* Header with progress bar */}
            <div className="p-4 pb-0">
                <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                        <Database className="w-5 h-5 text-blue-600" />
                        <h3 className="font-medium text-gray-900">Обработка данных</h3>
                    </div>
                    <div className="flex items-center gap-3">
                        {progress.total > 0 && (
                            <span className="text-sm font-medium text-gray-700">
                                {getProgressPercentage()}%
                            </span>
                        )}
                        <button
                            onClick={() => setAutoScroll(!autoScroll)}
                            className={`flex items-center gap-1 text-xs px-2 py-1 rounded-md transition-colors ${autoScroll
                                ? 'bg-blue-100 text-blue-700 hover:bg-blue-200'
                                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                                }`}
                        >
                            <ArrowDown className="w-3 h-3" />
                            {autoScroll ? 'Автопрокрутка' : 'Прокрутка выкл'}
                        </button>
                    </div>
                </div>

                {/* Progress bar */}
                {progress.total > 0 && (
                    <div className="mb-4">
                        <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                            <div
                                className="h-full bg-gradient-to-r from-blue-500 to-blue-600 transition-all duration-500 ease-out"
                                style={{ width: `${getProgressPercentage()}%` }}
                            />
                        </div>
                    </div>
                )}

                {/* Current stage */}
                <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                    <div className="flex items-center gap-2">
                        <Loader2 className="w-4 h-4 text-blue-600 animate-spin" />
                        <span className="text-sm font-medium text-blue-900">
                            Текущий этап: {getCurrentStage()}
                        </span>
                    </div>
                    {progress.total > 0 && (
                        <div className="mt-2 text-xs text-blue-700">
                            Обработано: {progress.processed} из {progress.total}
                        </div>
                    )}
                </div>
            </div>

            {/* Logs section */}
            <div className="px-4 pb-4">
                <div
                    ref={logsContainerRef}
                    className="max-h-64 overflow-auto border border-gray-200 rounded-lg"
                    onScroll={handleScroll}
                    onMouseDown={handleScrollStart}
                    onMouseUp={handleScrollEnd}
                    onTouchStart={handleScrollStart}
                    onTouchEnd={handleScrollEnd}
                >
                    <div className="divide-y divide-gray-100">
                        {logs.length === 0 ? (
                            <div className="p-4 text-center text-gray-500 text-sm">
                                Ожидание начала процесса...
                            </div>
                        ) : (
                            logs.map((log, index) => (
                                <div
                                    key={index}
                                    className={`px-3 py-2 border-l-4 ${getStatusStyle(log.status, log.message)}`}
                                >
                                    <div className="flex items-start gap-2">
                                        {getStatusIcon(log.status, log.message)}
                                        <div className="flex-1 min-w-0">
                                            <div className="text-sm font-medium">
                                                {log.message}
                                            </div>
                                            {log.details && (
                                                <div className="text-xs text-gray-600 mt-1">
                                                    {log.details}
                                                </div>
                                            )}
                                            <div className="text-xs text-gray-500 mt-1">
                                                {formatDate(log.timestamp, true)}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

LoadingProgress.propTypes = {
    logs: PropTypes.arrayOf(PropTypes.shape({ message: PropTypes.string, details: PropTypes.string, timestamp: PropTypes.string, status: PropTypes.string })).isRequired,
    progress: PropTypes.shape({ processed: PropTypes.number, total: PropTypes.number }).isRequired,
    setLogs: PropTypes.func,
    setProgress: PropTypes.func,
    onCancel: PropTypes.func,
    onComplete: PropTypes.func,
    onProgressUpdate: PropTypes.func,
};

export default LoadingProgress;