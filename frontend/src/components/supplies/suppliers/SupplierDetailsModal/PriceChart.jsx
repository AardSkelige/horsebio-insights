// src/components/supplies/suppliers/SupplierDetailsModal/PriceChart.jsx

import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { CHART_ANIMATION } from '../../../../utils/chartAnimation';
import PropTypes from 'prop-types';

const formatNumber = (value) => value.toLocaleString('ru-RU');

// Массив цветов для разных линий графика
const CHART_COLORS = [
    '#2563eb', '#dc2626', '#059669', '#7c3aed', '#ea580c',
    '#0891b2', '#be185d', '#4f46e5', '#b45309', '#065f46'
];

const PriceChart = ({ materialsData }) => {
    if (!materialsData || materialsData.length === 0) {
        return <div className="text-gray-500 text-center py-8">Нет данных для отображения графика</div>;
    }

    // Формируем общий набор дат для всех материалов
    const allDates = [...new Set(materialsData.flatMap(
        material => material.price_history.map(item => item.date)
    ))].sort();

    // Создаем общий массив данных для графика
    const chartData = allDates.map(date => {
        const dataPoint = { date };
        materialsData.forEach(material => {
            const priceItem = material.price_history.find(item => item.date === date);
            if (priceItem) {
                dataPoint[`price_${material.id}`] = priceItem.price;
            }
        });
        return dataPoint;
    });

    return (
        <div style={{ width: '100%', height: 400 }}>
            <ResponsiveContainer>
                <LineChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                        dataKey="date"
                        tick={{ fontSize: 12 }}
                    />
                    <YAxis
                        tickFormatter={(value) => `${formatNumber(value)}₽`}
                        tick={{ fontSize: 12 }}
                    />
                    <Tooltip
                        formatter={(value, name) => {
                            const materialId = name.split('_')[1];
                            const material = materialsData.find(m => m.id === Number(materialId));
                            return [`${formatNumber(value)}₽`, `${material?.name} (${material?.uom})`];
                        }}
                        labelFormatter={(label) => new Date(label).toLocaleDateString('ru-RU')}
                    />
                    <Legend
                        formatter={(value) => {
                            const materialId = value.split('_')[1];
                            const material = materialsData.find(m => m.id === Number(materialId));
                            return material?.name || value;
                        }}
                    />
                    {materialsData.map((material, index) => (
                        <Line
                            {...CHART_ANIMATION}
                            key={material.id}
                            type="monotone"
                            dataKey={`price_${material.id}`}
                            name={`price_${material.id}`}
                            stroke={CHART_COLORS[index % CHART_COLORS.length]}
                            dot={{ r: 4 }}
                            activeDot={{ r: 6 }}
                        />
                    ))}
                </LineChart>
            </ResponsiveContainer>
        </div>
    );
};

PriceChart.propTypes = {
    materialsData: PropTypes.arrayOf(PropTypes.shape({
        id: PropTypes.number.isRequired,
        name: PropTypes.string.isRequired,
        uom: PropTypes.string.isRequired,
        price_history: PropTypes.arrayOf(PropTypes.shape({
            date: PropTypes.string.isRequired,
            price: PropTypes.number.isRequired
        })).isRequired
    })).isRequired
};

export default PriceChart;