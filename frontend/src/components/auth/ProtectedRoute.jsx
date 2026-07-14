// frontend/src/components/auth/ProtectedRoute.jsx
import { useEffect, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import AuthLoadingScreen from './AuthLoadingScreen';
import PropTypes from 'prop-types';
import { getFreshAuthStatus, setAuthStatus } from '../../utils/authSession';
import { authApi } from '../../api/authApi';

const ProtectedRoute = ({ children }) => {
    const cachedAuth = getFreshAuthStatus().isAuthenticated;
    const [isAuthenticated, setIsAuthenticated] = useState(cachedAuth);
    const [isLoading, setIsLoading] = useState(cachedAuth === null);
    const location = useLocation();

    useEffect(() => {
        let isMounted = true;
        const controller = new AbortController();

        const checkAuth = async () => {
            if (isMounted && getFreshAuthStatus().isAuthenticated === null) setIsLoading(true);

            try {
                const data = await authApi.check(controller.signal);
                const nextStatus = Boolean(data.isAuthenticated);
                setAuthStatus({
                    isAuthenticated: nextStatus,
                    isSuperuser: nextStatus ? Boolean(data.isSuperuser) : false,
                    username: data.username || '',
                    email: data.email || '',
                    firstName: data.firstName || '',
                    lastName: data.lastName || '',
                });
                if (isMounted) setIsAuthenticated(nextStatus);
            } catch (error) {
                if (error.name !== 'AbortError' && isMounted) {
                    setAuthStatus({ isAuthenticated: false, isSuperuser: false });
                    setIsAuthenticated(false);
                }
            } finally {
                if (isMounted) setIsLoading(false);
            }
        };

        checkAuth();

        const handlePageShow = (event) => {
            if (event.persisted) checkAuth();
        };

        window.addEventListener('pageshow', handlePageShow);

        return () => {
            isMounted = false;
            controller.abort();
            window.removeEventListener('pageshow', handlePageShow);
        };
    }, [location.pathname]);

    if (isLoading) {
        return <AuthLoadingScreen />;
    }

    if (!isAuthenticated) {
        return <Navigate to="/login" state={{ from: location }} replace />;
    }

    return children;
};

// Добавляем валидацию пропсов
ProtectedRoute.propTypes = {
    children: PropTypes.node.isRequired
};

export default ProtectedRoute;
