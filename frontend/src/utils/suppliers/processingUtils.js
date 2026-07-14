export const processSupplyData = (data) => {
    if (!Array.isArray(data)) return [];

    const materialsData = {};

    data.forEach(supply => {
        if (!Array.isArray(supply.items)) return;

        supply.items.forEach(item => {
            const materialKey = item.material_name;
            if (!materialKey) return;

            if (!materialsData[materialKey]) {
                materialsData[materialKey] = {
                    name: materialKey,
                    group: item.raw_material?.group || 'Не указано',
                    total_quantity: 0,
                    total_sum: 0,
                    average_price: 0,
                    suppliers: new Set(),
                    supplies: []
                };
            }

            const material = materialsData[materialKey];
            const quantity = parseFloat(item.quantity) || 0;
            const total = parseFloat(item.total) || 0;

            material.total_quantity += quantity;
            material.total_sum += total;
            material.suppliers.add(supply.supplier_name);

            material.supplies.push({
                date: supply.supply_date,
                supplier: supply.supplier_name,
                quantity: quantity,
                price: parseFloat(item.price) || 0,
                total: total,
                supply_number: supply.supply_number,
                uom: item.uom || 'шт.'
            });
        });
    });

    return Object.values(materialsData).map(material => {
        material.average_price = material.total_quantity > 0
            ? material.total_sum / material.total_quantity
            : 0;
        material.suppliers = Array.from(material.suppliers);
        material.supplies.sort((a, b) => new Date(b.date) - new Date(a.date));
        return material;
    });
};

export const groupSuppliesByPeriod = (supplies, period = 'month') => {
    const groupedData = {};

    supplies.forEach(supply => {
        const date = new Date(supply.date);
        const key = period === 'month'
            ? `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
            : date.toISOString().split('T')[0];

        if (!groupedData[key]) {
            groupedData[key] = {
                period: key,
                quantity: 0,
                total_sum: 0,
                average_price: 0,
                supplies_count: 0
            };
        }

        groupedData[key].quantity += supply.quantity;
        groupedData[key].total_sum += supply.total;
        groupedData[key].supplies_count++;
    });

    return Object.values(groupedData)
        .map(data => ({
            ...data,
            average_price: data.quantity > 0 ? data.total_sum / data.quantity : 0
        }))
        .sort((a, b) => a.period.localeCompare(b.period));
};