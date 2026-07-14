// src/components/home/components/LoadingProgressSimple.jsx
import { useState, useRef, useCallback, useEffect } from 'react';
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

const LoadingProgressSimple = ({ logs, progress, getCurrentStage, getProgressPercentage, currentDateRange }) => {
    const [autoScroll, setAutoScroll] = useState(true);
    const logsContainerRef = useRef(null);
    const userScrolling = useRef(false);
    const lastScrollPosition = useRef(0);

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

    const getStatusIcon = (status, message) => {
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

    return (
        <div className="bg-white rounded-xl shadow-sm border overflow-hidden">
            {/* Header with progress bar */}
            <div className="p-4 pb-0">
                <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                        <Database className="w-5 h-5 text-blue-600" />
                        <div>
                            <h3 className="font-medium text-gray-900">Обработка данных</h3>
                            {currentDateRange && (
                                <div className="text-xs text-gray-600">
                                    {currentDateRange.startDate && currentDateRange.endDate ? (
                                        `Период: ${formatDate(currentDateRange.startDate)} - ${formatDate(currentDateRange.endDate)}`
                                    ) : currentDateRange.months ? (
                                        `Последние ${currentDateRange.months} ${currentDateRange.months === 1 ? 'месяц' : 
                                          currentDateRange.months < 5 ? 'месяца' : 'месяцев'}`
                                    ) : (
                                        'Выбранный период'
                                    )}
                                </div>
                            )}
                        </div>
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

LoadingProgressSimple.propTypes = {
    logs: PropTypes.array.isRequired,
    progress: PropTypes.object.isRequired,
    getCurrentStage: PropTypes.func.isRequired,
    getProgressPercentage: PropTypes.func.isRequired,
    currentDateRange: PropTypes.object
};

export default LoadingProgressSimple;