// src/contexts/LoadingContext.jsx
/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useState, useRef, useCallback, useEffect } from 'react';
import PropTypes from 'prop-types';
import { parserAPI } from '../utils/api';
import { getFreshAuthStatus, subscribeAuth } from '../utils/authSession';

const LoadingContext = createContext();

export const useLoading = () => {
    const context = useContext(LoadingContext);
    if (!context) {
        throw new Error('useLoading must be used within a LoadingProvider');
    }
    return context;
};

export const LoadingProvider = ({ children }) => {
    const [isLoading, setIsLoading] = useState(false);
    const [loadingProgress, setLoadingProgress] = useState(null);
    const [logs, setLogs] = useState([]);
    const [progress, setProgress] = useState({ processed: 0, total: 0 });
    const [error, setError] = useState(null);
    const [loadingKey, setLoadingKey] = useState(0);
    const [currentDateRange, setCurrentDateRange] = useState(null);
    const [syncVersion, setSyncVersion] = useState(0);
    
    const eventSourceRef = useRef(null);
    const lastMessageTimestamps = useRef(new Map());
    const messageThrottleTime = 100;

    const cleanupEventSource = useCallback(() => {
        if (eventSourceRef.current) {
            eventSourceRef.current.close();
            eventSourceRef.current = null;
        }
        lastMessageTimestamps.current.clear();
    }, []);

    const resetStates = useCallback(() => {
        setIsLoading(false);
        setLoadingProgress(null);
        setLogs([]);
        setProgress({ processed: 0, total: 0 });
        setError(null);
        setLoadingKey(prev => prev + 1);
        setCurrentDateRange(null);
        cleanupEventSource();
    }, [cleanupEventSource]);

    const startLoading = useCallback(async (dateRange) => {
        try {
            setIsLoading(true);
            setError(null);
            setLoadingKey(prev => prev + 1);
            setLogs([]);
            setProgress({ processed: 0, total: 0 });
            setCurrentDateRange(dateRange);

            const csrfResponse = await parserAPI.getCsrfToken();
            if (!csrfResponse?.csrfToken) {
                throw new Error('Не удалось получить CSRF токен');
            }

            const response = await parserAPI.loadData(csrfResponse.csrfToken, {
                startDate: dateRange.startDate,
                endDate: dateRange.endDate,
                months: dateRange.months
            });

            if (!response || response.status !== 'started') {
                throw new Error(response?.message || 'Не удалось начать загрузку данных');
            }

            setLoadingProgress({
                status: 'running',
                message: 'Загрузка данных...',
                processed: 0,
                total: 100
            });

        } catch (err) {
            console.error('Error starting load:', err);
            setError(err.message || 'Произошла ошибка при загрузке данных');
            resetStates();
        }
    }, [resetStates]);

    const cancelLoading = useCallback(async () => {
        try {
            await parserAPI.stopLoading();

            resetStates();

        } catch (err) {
            console.error('Cancel loading error:', err);
            setError(err.message || 'Ошибка при отмене загрузки');
            resetStates();
        }
    }, [resetStates]);

    const handleLoadingComplete = useCallback((status) => {
        if (status === 'error') {
            setError('Произошла ошибка при загрузке данных');
        } else if (status === 'completed') {
            setSyncVersion(v => v + 1);
        }
        // Не сбрасываем состояние сразу, оставляем для отображения результата
        setIsLoading(false);
    }, []);

    // SSE подключение
    useEffect(() => {
        if (!isLoading) return;

        let isMounted = true;

        const handleStreamMessage = (event) => {
            if (!isMounted) return;

            try {
                const data = JSON.parse(event.data);

                // Throttling для предотвращения спама
                const messageKey = `${data.message}${data.details || ''}`;
                const currentTime = Date.now();
                const lastTime = lastMessageTimestamps.current.get(messageKey);

                if (lastTime && (currentTime - lastTime < messageThrottleTime)) {
                    return;
                }

                lastMessageTimestamps.current.set(messageKey, currentTime);

                const newLog = {
                    timestamp: data.timestamp || new Date().toISOString(),
                    message: data.message || 'Загрузка завершена',
                    details: data.details,
                    status: data.status
                };

                setLogs(prevLogs => {
                    const lastLog = prevLogs[prevLogs.length - 1];
                    if (lastLog &&
                        lastLog.message === newLog.message &&
                        lastLog.details === newLog.details) {
                        return prevLogs;
                    }

                    const newLogs = [...prevLogs, newLog];
                    return newLogs.slice(-100);
                });

                // Обновляем прогресс
                if (data.processed !== undefined && data.total !== undefined) {
                    setProgress({
                        processed: data.processed,
                        total: data.total
                    });
                    
                    setLoadingProgress({
                        status: data.status || 'running',
                        message: data.message || 'Загрузка данных...',
                        details: data.details,
                        processed: data.processed,
                        total: data.total
                    });
                }

                // Проверяем статус завершения
                if (data.status === 'completed' || data.status === 'error' || data.status === 'stopped') {
                    setProgress({ processed: 0, total: 0 });
                    cleanupEventSource();

                    window.setTimeout(() => {
                        if (isMounted) {
                            handleLoadingComplete(data.status);
                        }
                    }, 500);
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
                    handleLoadingComplete('error');
                };
            }
        } catch (err) {
            console.error('Error setting up SSE:', err);
            handleLoadingComplete('error');
        }

        return () => {
            isMounted = false;
            cleanupEventSource();
        };
    }, [isLoading, cleanupEventSource, handleLoadingComplete]);

    // Проверяем фоновую задачу только для подтверждённой пользовательской
    // сессии. LoadingProvider также оборачивает публичную страницу входа, где
    // запрос к защищённому /parser/task-status/ создавал лишний 401 в console.
    useEffect(() => {
        let isMounted = true;
        let wasAuthenticated = getFreshAuthStatus().isAuthenticated === true;

        const checkTaskStatus = async () => {
            try {
                const data = await parserAPI.getTaskStatus();

                if (isMounted && data.is_running && data.state) {
                    setIsLoading(true);
                    setLoadingProgress(data.state);
                    setLoadingKey(prev => prev + 1);
                }
            } catch (error) {
                if (isMounted) console.error('Error checking task status:', error);
            }
        };

        if (wasAuthenticated) checkTaskStatus();

        const unsubscribe = subscribeAuth((status) => {
            const isAuthenticated = status.isAuthenticated === true;
            if (isAuthenticated && !wasAuthenticated) checkTaskStatus();
            wasAuthenticated = isAuthenticated;
        });

        return () => {
            isMounted = false;
            unsubscribe();
        };
    }, []);

    const value = {
        // State
        isLoading,
        loadingProgress,
        logs,
        progress,
        error,
        loadingKey,
        currentDateRange,
        syncVersion,
        
        // Actions
        startLoading,
        cancelLoading,
        resetStates,
        
        // Computed
        getProgressPercentage: () => {
            if (progress.total === 0) return 0;
            return Math.round((progress.processed / progress.total) * 100);
        },
        
        getCurrentStage: () => {
            if (logs.length === 0) return 'Подготовка к загрузке...';
            const lastLog = logs[logs.length - 1];
            return lastLog.message || 'Обработка данных';
        }
    };

    return (
        <LoadingContext.Provider value={value}>
            {children}
        </LoadingContext.Provider>
    );
};

LoadingProvider.propTypes = {
    children: PropTypes.node.isRequired
};
