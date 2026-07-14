// src/components/common/LoadingState.jsx
const LoadingState = () => {
    return (
        <div className="animate-pulse">
            <div className="space-y-4">
                <div className="h-4 bg-gray-200 rounded w-3/4"></div>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {[1, 2, 3].map((i) => (
                        <div key={i} className="bg-gray-200 rounded h-32"></div>
                    ))}
                </div>
            </div>
        </div>
    );
};

export default LoadingState;