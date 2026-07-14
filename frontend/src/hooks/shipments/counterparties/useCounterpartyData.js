// src/hooks/shipments/counterparties/useCounterpartyData.js
import { useFetchWithCache } from '../../useFetchWithCache';

export const useCounterpartyData = () =>
    useFetchWithCache('/api/shipments/', 'counterpartiesData');

export default useCounterpartyData;
