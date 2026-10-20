import { useCallback, useEffect, useState } from 'react';
import { round3 } from '../format';

const STORAGE_KEY = 'raw-materials-issue-cart';

const fresh = () => ({ key: crypto.randomUUID(), lines: [] });

function load() {
    try {
        const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
        if (saved?.key && Array.isArray(saved.lines)) return saved;
    } catch {
        return fresh();
    }
    return fresh();
}

function save(cart) {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(cart));
    } catch {
        return;
    }
}

export default function useIssueCart() {
    const [cart, setCart] = useState(load);

    useEffect(() => save(cart), [cart]);

    const add = useCallback((line) => setCart((current) => {
        const existing = current.lines.find((l) => l.batch === line.batch);
        const lines = existing
            ? current.lines.map((l) => (l.batch === line.batch ? { ...l, quantity: round3(l.quantity + line.quantity) } : l))
            : [...current.lines, line];
        return { ...current, lines };
    }), []);

    const remove = useCallback((batch) => setCart((current) => (
        { ...current, lines: current.lines.filter((l) => l.batch !== batch) }
    )), []);

    const settle = useCallback((issued) => setCart((current) => {
        const given = (batch) => issued.filter((i) => i.batch === batch).reduce((sum, i) => sum + i.quantity, 0);
        const lines = current.lines
            .map((l) => ({ ...l, quantity: round3(l.quantity - given(l.batch)) }))
            .filter((l) => l.quantity > 0);
        return { ...fresh(), lines };
    }), []);

    const taken = useCallback(
        (batch) => cart.lines.find((l) => l.batch === batch)?.quantity || 0,
        [cart.lines],
    );

    return { key: cart.key, lines: cart.lines, add, remove, settle, taken };
}
