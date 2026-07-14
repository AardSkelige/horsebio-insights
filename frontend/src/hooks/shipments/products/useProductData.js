// src/hooks/shipments/products/useProductData.js
import { useFetchWithCache } from '../../useFetchWithCache';

export const useProductData = () =>
    useFetchWithCache('/api/shipments/', 'productsData');

export default useProductData;
