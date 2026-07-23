import { useEffect, useState } from 'react';
import { KeyRound, Loader2, Check, AlertCircle, Users } from 'lucide-react';
import { authApi } from '../../api/authApi';
import './AccessAdminPage.css';

const arraysEqual = (a, b) => a.length === b.length && a.every((x) => b.includes(x));
const shortGroup = (g) => g.split(' ')[0];

const AccessAdminPage = () => {
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [pages, setPages] = useState([]);
    const [users, setUsers] = useState([]);
    const [draft, setDraft] = useState({}); // userId -> Set(pageKey)
    const [original, setOriginal] = useState({}); // userId -> sorted[] (сохранённое)
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
                const d = {}; const o = {};
                (data.users || []).forEach((u) => {
                    d[u.id] = new Set(u.pages || []);
                    o[u.id] = (u.pages || []).slice().sort();
                });
                setDraft(d); setOriginal(o);
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
            setOriginal((prev) => ({ ...prev, [userId]: saved.slice().sort() }));
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
                <h1 className="acc-title">Доступы</h1>
                <p className="acc-sub">Кто из пользователей какие разделы видит и может открывать. Суперпользователи видят всё и здесь не показаны.</p>
            </div>

            {error && (
                <div className="acc-error">
                    <AlertCircle style={{ width: 16, height: 16, flexShrink: 0 }} />
                    <span>{error}</span>
                </div>
            )}

            {loading ? (
                <div className="acc-loading"><Loader2 className="acc-spin" style={{ width: 20, height: 20 }} /> Загрузка…</div>
            ) : users.length === 0 ? (
                <div className="acc-empty">
                    <Users style={{ width: 34, height: 34, color: 'var(--hairline)' }} />
                    <p>Нет обычных пользователей для настройки</p>
                </div>
            ) : (
                <div className="acc-grid">
                    {users.map((u) => {
                        const set = draft[u.id] || new Set();
                        const dirty = isDirty(u.id);
                        return (
                            <div key={u.id} className="acc-card">
                                <div className="acc-card-h">
                                    <span className="acc-av"><KeyRound style={{ width: 15, height: 15 }} /></span>
                                    <div className="acc-who">
                                        <div className="acc-name">{u.fullName || u.username}</div>
                                        <div className="acc-meta">{u.username} · {set.size} из {pages.length}</div>
                                    </div>
                                </div>
                                <div className="acc-actions">
                                    <div className="acc-actions-l">
                                        <button className="acc-text" onClick={() => setAll(u.id, true)}>Все</button>
                                        <button className="acc-text" onClick={() => setAll(u.id, false)}>Ничего</button>
                                    </div>
                                    <button className="acc-save" disabled={!dirty || savingId === u.id} onClick={() => save(u.id)}>
                                        {savingId === u.id ? <Loader2 className="acc-spin" style={{ width: 13, height: 13 }} />
                                            : savedId === u.id ? <><Check style={{ width: 13, height: 13 }} /> Сохранено</>
                                            : 'Сохранить'}
                                    </button>
                                </div>
                                <div className="acc-list">
                                    {pages.map((p) => {
                                        const on = set.has(p.key);
                                        return (
                                            <button key={p.key} type="button" className={`acc-row${on ? ' on' : ''}`}
                                                aria-pressed={on} onClick={() => toggle(u.id, p.key)}>
                                                <span className={`acc-chk${on ? ' on' : ''}`}><Check style={{ width: 11, height: 11 }} /></span>
                                                <span className="acc-row-l">{p.label}</span>
                                                <span className="acc-row-g">{shortGroup(p.group)}</span>
                                            </button>
                                        );
                                    })}
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
