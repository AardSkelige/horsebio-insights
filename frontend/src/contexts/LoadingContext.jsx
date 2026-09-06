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

    // Номер прогона, который запустили мы. Без него первый же опрос находит
    // прошлый прогон — законченный — и гасит полосу через полсекунды после
    // нажатия, пока запущенная синхронизация идёт незаметно.
    const runIdRef = useRef(null);
    
    // Как часто спрашивать сервер, что там с синхронизацией. Три секунды —
    // столько же, сколько у StarPony: полоса двигается по этапам, а не
    // по документам, и чаще спрашивать нечего.
    const POLL_INTERVAL_MS = 3000;

    const resetStates = useCallback(() => {
        setIsLoading(false);
        setLoadingProgress(null);
        setLogs([]);
        setProgress({ processed: 0, total: 0 });
        setError(null);
        setLoadingKey(prev => prev + 1);
        setCurrentDateRange(null);
    }, []);

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

            runIdRef.current = response.run_id ?? null;

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

    // Опрос состояния синхронизации.
    //
    // Раньше здесь было открытое соединение (SSE): сервер сам слал новости,
    // пока шла загрузка. Убрано по двум причинам. Открытый поток не переживает
    // gunicorn — тот перезапускает воркер по счётчику запросов и рвёт
    // соединение на середине, а полоса при этом замирает молча. И состояние
    // всё равно живёт теперь в базе, откуда его видно любому процессу
    // и любому пользователю, а не только тому, кто нажал кнопку.
    useEffect(() => {
        if (!isLoading) return;

        let isMounted = true;

        const applyState = (state, isRunning) => {
            if (!isMounted || !state) return;

            // Чужой прогон — не наш: страница показывает его как чужой,
            // но завершать по нему свою загрузку нельзя.
            if (runIdRef.current && state.id && state.id !== runIdRef.current) return;

            // Прогон, о котором сервер давно не слышал: процесс умер,
            // не закрыв запись. Статус в ней навсегда остался бы «идёт»,
            // а полоса — застывшей, пока страницу не перезагрузят.
            if (!isRunning && state.status === 'running') {
                setProgress({ processed: 0, total: 0 });
                window.setTimeout(() => {
                    if (isMounted) handleLoadingComplete('error');
                }, 500);
                return;
            }

            const newLog = {
                timestamp: new Date().toISOString(),
                message: state.message || 'Загрузка завершена',
                status: state.status,
            };

            setLogs(prevLogs => {
                const lastLog = prevLogs[prevLogs.length - 1];
                if (lastLog && lastLog.message === newLog.message) {
                    return prevLogs;
                }
                return [...prevLogs, newLog].slice(-100);
            });

            if (state.processed !== undefined && state.total !== undefined) {
                setProgress({ processed: state.processed, total: state.total });
                setLoadingProgress({
                    status: state.status || 'running',
                    message: state.message || 'Загрузка данных...',
                    processed: state.processed,
                    total: state.total,
                });
            }

            if (state.status === 'completed' || state.status === 'error' || state.status === 'stopped') {
                setProgress({ processed: 0, total: 0 });
                window.setTimeout(() => {
                    if (isMounted) handleLoadingComplete(state.status);
                }, 500);
            }
        };

        const poll = async () => {
            try {
                const data = await parserAPI.getTaskStatus();
                applyState(data.state, data.is_running);
            } catch (error) {
                if (isMounted) console.error('Error polling sync status:', error);
            }
        };

        poll();
        const timer = window.setInterval(poll, POLL_INTERVAL_MS);

        return () => {
            isMounted = false;
            window.clearInterval(timer);
        };
    }, [isLoading, handleLoadingComplete]);

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
