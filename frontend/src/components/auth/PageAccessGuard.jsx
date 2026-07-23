import PropTypes from 'prop-types';
import { useLocation, Navigate } from 'react-router-dom';
import NAV_GROUPS from '../layout/sidebar/navGroups';
import { useAuthStatus } from '../../hooks/useAuthStatus';

// Пункты меню, у которых есть pageKey — источник соответствия «путь → страница».
const PAGE_ITEMS = NAV_GROUPS
    .flatMap((g) => g.items)
    .filter((i) => i.pageKey);

// Ключ страницы для текущего пути: самое длинное совпадение по префиксу пути.
const pageKeyForPath = (pathname) => {
    let best = null;
    for (const item of PAGE_ITEMS) {
        if (pathname === item.path || pathname.startsWith(item.path + '/')) {
            if (!best || item.path.length > best.path.length) best = item;
        }
    }
    return best?.pageKey || null;
};

// Защита от прямого ввода URL: обычный пользователь без права на страницу
// перенаправляется на главную. Серверный контроль (middleware) — основной;
// это дублирующая защита для UX (не показывать заведомо 403-ящую страницу).
const PageAccessGuard = ({ children }) => {
    const location = useLocation();
    const auth = useAuthStatus();

    if (auth.isSuperuser === true) return children;

    const pageKey = pageKeyForPath(location.pathname);
    // права ещё не загружены — не редиректим (ProtectedRoute уже проверил вход)
    if (!pageKey || !Array.isArray(auth.allowedPages)) return children;

    if (!auth.allowedPages.includes(pageKey)) {
        return <Navigate to="/" replace />;
    }
    return children;
};

PageAccessGuard.propTypes = {
    children: PropTypes.node.isRequired,
};

export default PageAccessGuard;
