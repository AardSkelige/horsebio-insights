// src/components/home/components/LoadingCard.jsx
import PropTypes from 'prop-types';
import { CheckCircle2, Loader2, XCircle, AlertCircle } from 'lucide-react';

const LoadingCard = ({ progress, onCancel }) => {
    const getStatusColor = (status) => {
        switch (status) {
            case 'running':
                return 'text-blue-500';
            case 'completed':
                return 'text-green-500';
            case 'error':
                return 'text-red-500';
            default:
                return 'text-gray-500';
        }
    };

    if (!progress) return null;

    return (
        <div className="bg-gradient-to-r from-blue-50 to-blue-100 rounded-lg border border-blue-200 p-3">
            <div className="flex justify-between items-center mb-2">
                <div className="flex items-center space-x-2">
                    {progress.status === 'running' ? (
                        <Loader2 className="w-4 h-4 animate-spin text-blue-600" />
                    ) : progress.status === 'completed' ? (
                        <CheckCircle2 className="w-4 h-4 text-green-600" />
                    ) : progress.status === 'error' ? (
                        <XCircle className="w-4 h-4 text-red-600" />
                    ) : (
                        <AlertCircle className="w-4 h-4 text-orange-600" />
                    )}
                    <span className={`text-sm font-medium ${getStatusColor(progress.status)}`}>
                        {progress.message}
                    </span>
                </div>
                {progress.status === 'running' && (
                    <button
                        onClick={onCancel}
                        className="px-2 py-1 text-xs text-red-600 hover:text-red-700 hover:bg-red-50 rounded font-medium transition-colors"
                    >
                        Остановить
                    </button>
                )}
            </div>

            {progress.total > 0 && (
                <div className="space-y-1">
                    <div className="flex justify-between text-xs text-blue-700">
                        <span>Общий прогресс:</span>
                        <span className="font-medium">{Math.round((progress.processed / progress.total) * 100)}%</span>
                    </div>
                    <div className="h-1.5 bg-blue-200 rounded-full overflow-hidden">
                        <div
                            className="h-full bg-gradient-to-r from-blue-500 to-blue-600 transition-all duration-300"
                            style={{ width: `${(progress.processed / progress.total) * 100}%` }}
                        />
                    </div>
                    {progress.details && (
                        <p className="text-xs text-blue-700 mt-1 leading-relaxed">{progress.details}</p>
                    )}
                </div>
            )}
        </div>
    );
};

LoadingCard.propTypes = {
    progress: PropTypes.shape({
        status: PropTypes.string,
        message: PropTypes.string,
        details: PropTypes.string,
        processed: PropTypes.number,
        total: PropTypes.number
    }),
    onCancel: PropTypes.func.isRequired
};

export default LoadingCard;