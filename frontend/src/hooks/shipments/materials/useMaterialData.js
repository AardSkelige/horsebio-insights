// src/hooks/shipments/materials/useMaterialData.js
import { useFetchWithCache } from '../../useFetchWithCache';

export const useMaterialData = () =>
    useFetchWithCache('/api/materials/', 'materialsData');

export default useMaterialData;
