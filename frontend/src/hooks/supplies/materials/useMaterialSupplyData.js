// src/hooks/supplies/materials/useMaterialSupplyData.js
import { useFetchWithCache } from '../../useFetchWithCache';

export const useMaterialSupplyData = () =>
    useFetchWithCache('/api/supplies/materials/', 'materialSuppliesData');

export default useMaterialSupplyData;
