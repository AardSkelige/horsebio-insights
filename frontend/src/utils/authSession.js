const SESSION_KEY = 'horsebio_auth';
const AUTH_STATUS_MAX_AGE_MS = 60 * 1000;
const listeners = new Set();

const _readStorage = () => {
    try {
        const raw = sessionStorage.getItem(SESSION_KEY);
        return raw ? JSON.parse(raw) : null;
    } catch { return null; }
};

const _writeStorage = (status) => {
    if (status.isAuthenticated !== true) {
        _clearStorage();
        return;
    }
    try {
        sessionStorage.setItem(SESSION_KEY, JSON.stringify(status));
    } catch {}
};

const _clearStorage = () => {
    try {
        sessionStorage.removeItem(SESSION_KEY);
    } catch {}
};

let authStatus = _readStorage() ?? {
    isAuthenticated: null,
    isSuperuser: null,
    username: '',
    email: '',
    firstName: '',
    lastName: '',
    checkedAt: 0,
};

export const subscribeAuth = (fn) => {
    listeners.add(fn);
    return () => listeners.delete(fn);
};

export const getAuthStatus = () => authStatus;

export const getFreshAuthStatus = () => {
    if (authStatus.isAuthenticated === false) return authStatus;
    if (!authStatus.checkedAt) return { ...authStatus, isAuthenticated: null, isSuperuser: null };

    const isFresh = Date.now() - authStatus.checkedAt <= AUTH_STATUS_MAX_AGE_MS;
    return isFresh ? authStatus : { ...authStatus, isAuthenticated: null, isSuperuser: null };
};

export const setAuthStatus = ({ isAuthenticated, isSuperuser, username, email, firstName, lastName }) => {
    authStatus = {
        isAuthenticated: typeof isAuthenticated === 'boolean' ? isAuthenticated : authStatus.isAuthenticated,
        isSuperuser: typeof isSuperuser === 'boolean' ? isSuperuser : authStatus.isSuperuser,
        username: username !== undefined ? username : authStatus.username,
        email: email !== undefined ? email : authStatus.email,
        firstName: firstName !== undefined ? firstName : authStatus.firstName,
        lastName: lastName !== undefined ? lastName : authStatus.lastName,
        checkedAt: Date.now(),
    };
    _writeStorage(authStatus);
    listeners.forEach(fn => fn(authStatus));
};

export const clearAuthStatus = () => {
    authStatus = {
        isAuthenticated: false,
        isSuperuser: false,
        username: '',
        email: '',
        firstName: '',
        lastName: '',
        checkedAt: Date.now(),
    };
    _clearStorage();
    listeners.forEach(fn => fn(authStatus));
};
