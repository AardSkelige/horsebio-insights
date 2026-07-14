// src/hooks/useFetchWithCache.js
import { useState, useEffect } from 'react';

const CACHE_TTL = 5 * 60 * 1000; // 5 минут

export const useFetchWithCache = (url, cacheKey) => {
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [progress, setProgress] = useState(0);

    useEffect(() => {
        let isMounted = true;

        const fetchData = async () => {
            try {
                const cachedData = sessionStorage.getItem(cacheKey);
                const cachedTimestamp = sessionStorage.getItem(`${cacheKey}Timestamp`);

                if (cachedData && cachedTimestamp) {
                    const cacheAge = Date.now() - parseInt(cachedTimestamp);
                    if (cacheAge < CACHE_TTL) {
                        if (isMounted) {
                            setData(JSON.parse(cachedData));
                            setLoading(false);
                        }
                        return;
                    }
                }

                setLoading(true);
                const response = await fetch(url);

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const reader = response.body.getReader();
                const contentLength = +response.headers.get('Content-Length');

                let receivedLength = 0;
                const chunks = [];

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    chunks.push(value);
                    receivedLength += value.length;

                    if (contentLength && isMounted) {
                        setProgress((receivedLength / contentLength) * 100);
                    }
                }

                const chunksAll = new Uint8Array(receivedLength);
                let position = 0;
                for (const chunk of chunks) {
                    chunksAll.set(chunk, position);
                    position += chunk.length;
                }

                const result = JSON.parse(new TextDecoder('utf-8').decode(chunksAll));

                if (isMounted) {
                    if (result.status === 'success') {
                        try {
                            sessionStorage.setItem(cacheKey, JSON.stringify(result.data));
                            sessionStorage.setItem(`${cacheKey}Timestamp`, Date.now().toString());
                        } catch (e) {
                            console.warn('Failed to cache data:', e);
                        }
                        setData(result.data);
                    } else {
                        throw new Error(result.message || 'Failed to load data');
                    }
                }
            } catch (err) {
                console.error('Error fetching data:', err);
                if (isMounted) setError(err.message);
            } finally {
                if (isMounted) {
                    setLoading(false);
                    setProgress(100);
                }
            }
        };

        fetchData();

        return () => {
            isMounted = false;
        };
    }, [url, cacheKey]);

    return { data, loading, error, progress };
};

export default useFetchWithCache;
