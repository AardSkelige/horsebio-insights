import { useEffect, useMemo, useState } from 'react';
import { KeyRound, Loader2, Check, AlertCircle, Users } from 'lucide-react';
import { authApi } from '../../api/authApi';
import './AccessAdminPage.css';

const arraysEqual = (a, b) => a.length === b.length && a.every((x) => b.includes(x));

const AccessAdminPage = () => {
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [pages, setPages] = useState([]);
    const [users, setUsers] = useState([]);
    const [draft, setDraft] = useState({}); // userId -> Set(pageKey)
    const [savingId, setSavingId] = useState(null);
    const [savedId, setSavedId] = useState(null);

    useEffect(() => {
        const controller = new AbortController();
        (async () => {
            try {
                const res = await authApi.pagesAccess(controller.signal);
                const data = res.data || res;
                setPages(data.pages || []);
                setUsers(data.users || []);
                const d = {};
                (data.users || []).forEach((u) => { d[u.id] = new Set(u.pages || []); });
                setDraft(d);
            } catch (err) {
                if (err.name !== 'AbortError' && err.name !== 'CanceledError') {
                    setError('Не удалось загрузить доступы: ' + err.message);
                }
            } finally {
                setLoading(false);
            }
        })();
        return () => controller.abort();
    }, []);

    // Страницы, сгруппированные по разделу — для аккуратной раскладки чекбоксов
    const groups = useMemo(() => {
        const map = new Map();
        pages.forEach((p) => {
            if (!map.has(p.group)) map.set(p.group, []);
            map.get(p.group).push(p);
        });
        return [...map.entries()].map(([label, items]) => ({ label, items }));
    }, [pages]);

    const original = useMemo(() => {
        const m = {};
        users.forEach((u) => { m[u.id] = (u.pages || []).slice().sort(); });
        return m;
    }, [users]);

    const toggle = (userId, key) => {
        setDraft((prev) => {
            const next = new Set(prev[userId]);
            if (next.has(key)) next.delete(key); else next.add(key);
            return { ...prev, [userId]: next };
        });
        setSavedId(null);
    };

    const setAll = (userId, on) => {
        setDraft((prev) => ({ ...prev, [userId]: on ? new Set(pages.map((p) => p.key)) : new Set() }));
        setSavedId(null);
    };

    const isDirty = (userId) => !arraysEqual([...(draft[userId] || [])].sort(), original[userId] || []);

    const save = async (userId) => {
        setSavingId(userId);
        setError(null);
        try {
            const keys = [...(draft[userId] || [])];
            const res = await authApi.savePagesAccess(userId, keys);
            const saved = (res.data || res).data?.pages || keys;
            setUsers((prev) => prev.map((u) => (u.id === userId ? { ...u, pages: saved } : u)));
            setSavedId(userId);
            setTimeout(() => setSavedId((id) => (id === userId ? null : id)), 2000);
        } catch (err) {
            setError('Не удалось сохранить: ' + err.message);
        } finally {
            setSavingId(null);
        }
    };

    return (
        <div className="acc-root">
            <div className="acc-head">
                <div>
                    <h1 className="acc-title">Доступы</h1>
                    <p className="acc-sub">Кто из пользователей какие страницы видит и может открывать. Суперпользователи видят всё и здесь не показаны.</p>
                </div>
            </div>

            {error && (
                <div className="acc-error">
                    <AlertCircle style={{ width: 16, height: 16, flexShrink: 0 }} />
                    <span>{error}</span>
                </div>
            )}

            {loading ? (
                <div className="acc-loading"><Loader2 className="acc-spin" style={{ width: 22, height: 22 }} /> Загрузка…</div>
            ) : users.length === 0 ? (
                <div className="acc-empty">
                    <Users style={{ width: 36, height: 36, color: 'var(--hairline)' }} />
                    <p>Нет обычных пользователей для настройки</p>
                </div>
            ) : (
                <div className="acc-users">
                    {users.map((u) => {
                        const set = draft[u.id] || new Set();
                        const dirty = isDirty(u.id);
                        return (
                            <div key={u.id} className="acc-user">
                                <div className="acc-user-head">
                                    <div className="acc-user-id">
                                        <KeyRound style={{ width: 15, height: 15, color: 'var(--primary)' }} />
                                        <div>
                                            <div className="acc-user-name">{u.fullName || u.username}</div>
                                            <div className="acc-user-login">{u.username} · {set.size} из {pages.length}</div>
                                        </div>
                                    </div>
                                    <div className="acc-user-actions">
                                        <button className="acc-mini" onClick={() => setAll(u.id, true)}>Все</button>
                                        <button className="acc-mini" onClick={() => setAll(u.id, false)}>Ничего</button>
                                        <button className="acc-save" disabled={!dirty || savingId === u.id} onClick={() => save(u.id)}>
                                            {savingId === u.id ? <Loader2 className="acc-spin" style={{ width: 13, height: 13 }} />
                                                : savedId === u.id ? <><Check style={{ width: 13, height: 13 }} /> Сохранено</>
                                                : 'Сохранить'}
                                        </button>
                                    </div>
                                </div>
                                <div className="acc-groups">
                                    {groups.map((g) => (
                                        <div key={g.label} className="acc-group">
                                            <div className="acc-group-label">{g.label}</div>
                                            <div className="acc-checks">
                                                {g.items.map((p) => (
                                                    <label key={p.key} className={`acc-check${set.has(p.key) ? ' on' : ''}`}>
                                                        <input type="checkbox" checked={set.has(p.key)} onChange={() => toggle(u.id, p.key)} />
                                                        <span className="acc-box"><Check style={{ width: 11, height: 11 }} /></span>
                                                        {p.label}
                                                    </label>
                                                ))}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
};

export default AccessAdminPage;
