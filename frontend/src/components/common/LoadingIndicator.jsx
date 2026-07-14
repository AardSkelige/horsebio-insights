// src/components/common/LoadingIndicator.jsx
import { useEffect, useState } from 'react';
import PropTypes from 'prop-types';

const LoadingIndicator = ({
    isLoading,
    progress,
    message = 'Загрузка данных...',
    minDisplayTime = 500 // Минимальное время показа для быстрых загрузок
}) => {
    const [shouldShow, setShouldShow] = useState(false);

    useEffect(() => {
        if (isLoading) {
            setShouldShow(true);
            const timer = setTimeout(() => {
                if (!isLoading) {
                    setShouldShow(false);
                }
            }, minDisplayTime);
            return () => clearTimeout(timer);
        } else {
            // Добавляем небольшую задержку перед скрытием для плавности
            const timer = setTimeout(() => {
                setShouldShow(false);
            }, 300);
            return () => clearTimeout(timer);
        }
    }, [isLoading, minDisplayTime]);

    if (!shouldShow) return null;

    return (
        <div className="space-y-4 animate-fade-in">
            {/* Прогресс-бар */}
            <div className="bg-white rounded-lg p-4">
                <div className="text-sm text-gray-600 mb-2 flex items-center justify-between">
                    <span>{message}</span>
                    {progress !== undefined && <span>{Math.round(progress)}%</span>}
                </div>
                <div className="relative w-full h-2 bg-gray-200 rounded-full overflow-hidden">
                    <div
                        className={`absolute top-0 left-0 h-full bg-primary rounded-full ${progress === undefined ? 'animate-pulse w-full' : 'transition-all duration-300 ease-out'}`}
                        style={progress !== undefined ? { width: `${progress}%` } : undefined}
                    />
                </div>
            </div>
        </div>
    );
};

LoadingIndicator.propTypes = {
    isLoading: PropTypes.bool.isRequired,
    progress: PropTypes.number,
    message: PropTypes.string,
    minDisplayTime: PropTypes.number
};

export default LoadingIndicator;