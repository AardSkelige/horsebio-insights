import { useState, useEffect, useRef, useCallback } from 'react';
import PropTypes from 'prop-types';
import { Search, Clock, Star } from 'lucide-react';

const useDebounce = (fn, delay) => {
    const timer = useRef(null);
    return useCallback((...args) => {
        clearTimeout(timer.current);
        timer.current = setTimeout(() => fn(...args), delay);
    }, [fn, delay]);
};

const pillStyle = (accent) => ({
    fontFamily: 'var(--sans)', fontSize: '12px',
    color: accent ? 'var(--primary)' : 'var(--body)',
    backgroundColor: accent ? 'rgba(204,120,92,0.08)' : 'var(--surface-card)',
    border: `1px solid ${accent ? 'rgba(204,120,92,0.3)' : 'var(--hairline)'}`,
    borderRadius: '20px', padding: '3px 10px',
    cursor: 'pointer', transition: 'opacity 150ms',
});

const LabelRow = ({ icon: Icon, text }) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: '5px', fontFamily: 'var(--sans)', fontSize: '11px', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: '6px' }}>
        <Icon style={{ width: 11, height: 11 }} /> {text}
    </div>
);

LabelRow.propTypes = { icon: PropTypes.elementType.isRequired, text: PropTypes.string.isRequired };

const matShape = PropTypes.shape({ id: PropTypes.number.isRequired, name: PropTypes.string.isRequired, code: PropTypes.string, group: PropTypes.string });

const MaterialSearchPanel = ({ materials, onSearch, onSelect }) => {
    const [value, setValue] = useState('');
    const [open, setOpen] = useState(false);
    const [recent, setRecent] = useState([]);
    const [favs, setFavs] = useState([]);
    const rootRef = useRef(null);
    const inputRef = useRef(null);

    useEffect(() => {
        setRecent(JSON.parse(localStorage.getItem('recentMaterials') || '[]'));
        setFavs(JSON.parse(localStorage.getItem('favoriteMaterials') || '[]'));
    }, []);

    useEffect(() => {
        const handler = (e) => { if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false); };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, []);

    const debouncedSearch = useDebounce(onSearch, 300);

    const handleInput = (e) => {
        setValue(e.target.value);
        setOpen(true);
        debouncedSearch(e.target.value);
    };

    const addToRecent = (mat) => {
        const updated = [mat, ...recent.filter(m => m.id !== mat.id)].slice(0, 5);
        setRecent(updated);
        localStorage.setItem('recentMaterials', JSON.stringify(updated));
    };

    const toggleFav = (mat, e) => {
        e.stopPropagation();
        const isFav = favs.some(f => f.id === mat.id);
        const updated = isFav ? favs.filter(f => f.id !== mat.id) : [...favs, mat].slice(0, 10);
        setFavs(updated);
        localStorage.setItem('favoriteMaterials', JSON.stringify(updated));
    };

    const selectMaterial = (mat) => {
        setValue(mat.name);
        setOpen(false);
        addToRecent(mat);
        onSelect(mat);
        onSearch(mat.name);
    };

    return (
        <div ref={rootRef} style={{ position: 'relative', maxWidth: '560px' }}>
            <div style={{ position: 'relative' }}>
                <Search style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', width: 15, height: 15, color: 'var(--muted)', pointerEvents: 'none' }} />
                <input
                    ref={inputRef}
                    value={value}
                    onChange={handleInput}
                    onFocus={(e) => { e.target.style.borderColor = 'var(--primary)'; setOpen(true); }}
                    onBlur={(e) => e.target.style.borderColor = 'var(--hairline)'}
                    placeholder="Поиск материала по названию или коду"
                    style={{ width: '100%', height: '40px', padding: '0 12px 0 36px', fontFamily: 'var(--sans)', fontSize: '14px', color: 'var(--ink)', backgroundColor: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: '8px', outline: 'none', boxSizing: 'border-box', transition: 'border-color 150ms' }}
                />
            </div>

            {open && materials.length > 0 && (
                <div style={{ position: 'absolute', top: 'calc(100% + 4px)', left: 0, right: 0, backgroundColor: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: '8px', boxShadow: '0 4px 16px rgba(0,0,0,0.1)', zIndex: 100, maxHeight: '280px', overflowY: 'auto' }}>
                    {materials.map((mat, i) => (
                        <div
                            key={mat.id}
                            onMouseDown={() => selectMaterial(mat)}
                            style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 14px', cursor: 'pointer', borderBottom: i < materials.length - 1 ? '1px solid var(--hairline-soft)' : 'none' }}
                            onMouseEnter={e => e.currentTarget.style.backgroundColor = 'var(--surface-soft)'}
                            onMouseLeave={e => e.currentTarget.style.backgroundColor = 'transparent'}
                        >
                            <div>
                                <div style={{ fontFamily: 'var(--sans)', fontSize: '14px', fontWeight: 500, color: 'var(--ink)' }}>{mat.name}</div>
                                <div style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--muted)', marginTop: 2 }}>
                                    Код: {mat.code}{mat.group ? ` · ${mat.group}` : ''}
                                </div>
                            </div>
                            <button
                                onMouseDown={e => toggleFav(mat, e)}
                                style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '4px', color: favs.some(f => f.id === mat.id) ? '#e6a817' : 'var(--muted)', flexShrink: 0 }}
                            >
                                <Star style={{ width: 14, height: 14, fill: favs.some(f => f.id === mat.id) ? 'currentColor' : 'none' }} />
                            </button>
                        </div>
                    ))}
                </div>
            )}

            {(recent.length > 0 || favs.length > 0) && (
                <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap', marginTop: '12px' }}>
                    {recent.length > 0 && (
                        <div>
                            <LabelRow icon={Clock} text="Недавние" />
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                                {recent.map(mat => (
                                    <button key={mat.id} onClick={() => selectMaterial(mat)} style={pillStyle(false)}>{mat.name}</button>
                                ))}
                            </div>
                        </div>
                    )}
                    {favs.length > 0 && (
                        <div>
                            <LabelRow icon={Star} text="Избранные" />
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                                {favs.map(mat => (
                                    <button key={mat.id} onClick={() => selectMaterial(mat)} style={pillStyle(true)}>{mat.name}</button>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

MaterialSearchPanel.propTypes = {
    materials: PropTypes.arrayOf(matShape).isRequired,
    onSearch: PropTypes.func.isRequired,
    onSelect: PropTypes.func.isRequired,
};

export default MaterialSearchPanel;
