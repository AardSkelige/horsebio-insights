import PropTypes from 'prop-types';
import { ChartPieIcon, ShoppingCart, TrendingUp } from 'lucide-react';

const TabNavigation = ({ activeTab, onTabChange, className = '' }) => {
    const tabs = [
        {
            id: 'shipments',
            label: 'Отгрузки',
            icon: TrendingUp,
            description: 'Товары, клиенты, материалы'
        },
        {
            id: 'supplies',
            label: 'Приёмки',
            icon: ShoppingCart,
            description: 'Материалы, поставщики'
        },
        {
            id: 'analytics',
            label: 'Аналитика',
            icon: ChartPieIcon,
            description: 'ABC, сезонность, помощник'
        }
    ];

    return (
        <div className={`bg-white rounded-xl shadow-sm p-1 ${className}`}>
            <div className="flex space-x-1">
                {tabs.map((tab) => {
                    const Icon = tab.icon;
                    const isActive = activeTab === tab.id;
                    
                    return (
                        <button
                            key={tab.id}
                            onClick={() => onTabChange(tab.id)}
                            className={`
                                flex-1 flex flex-col items-center px-2 py-2 sm:px-4 sm:py-3 rounded-lg transition-all duration-200
                                ${isActive 
                                    ? 'bg-blue-50 text-blue-700 shadow-sm' 
                                    : 'text-gray-600 hover:text-gray-800 hover:bg-gray-50'
                                }
                            `}
                        >
                            <Icon className={`w-4 h-4 sm:w-5 sm:h-5 mb-1 ${isActive ? 'text-blue-600' : 'text-gray-500'}`} />
                            <span className="text-xs sm:text-sm font-medium">{tab.label}</span>
                            <span className="text-xs text-gray-500 mt-0.5 text-center leading-tight hidden md:block">
                                {tab.description}
                            </span>
                        </button>
                    );
                })}
            </div>
        </div>
    );
};

TabNavigation.propTypes = {
    activeTab: PropTypes.string.isRequired,
    onTabChange: PropTypes.func.isRequired,
    className: PropTypes.string
};

export default TabNavigation;