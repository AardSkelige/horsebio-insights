import { useEffect, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import AuthLoadingScreen from './AuthLoadingScreen';
import PropTypes from 'prop-types';
import { getFreshAuthStatus, setAuthStatus } from '../../utils/authSession';
import { authApi } from '../../api/authApi';

const SuperuserRoute = ({ children }) => {
    const cachedAuth = getFreshAuthStatus();
    const initialStatus = cachedAuth.isAuthenticated === false
        ? 'unauthenticated'
        : cachedAuth.isSuperuser === true
            ? 'ok'
            : 'loading';
    const [status, setStatus] = useState(initialStatus); // loading | ok | forbidden | unauthenticated
    const location = useLocation();

    useEffect(() => {
        let isMounted = true;
        const controller = new AbortController();

        const checkAuth = async () => {
            if (isMounted && getFreshAuthStatus().isSuperuser !== true) setStatus('loading');

            try {
                const data = await authApi.check(controller.signal);
                if (!isMounted) return;

                setAuthStatus({
                    isAuthenticated: Boolean(data.isAuthenticated),
                    isSuperuser: Boolean(data.isAuthenticated && data.isSuperuser),
                });

                if (!data.isAuthenticated) setStatus('unauthenticated');
                else if (!data.isSuperuser) setStatus('forbidden');
                else setStatus('ok');
            } catch (error) {
                if (error.name !== 'AbortError' && isMounted) {
                    setAuthStatus({ isAuthenticated: false, isSuperuser: false });
                    setStatus('unauthenticated');
                }
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

    if (status === 'loading') {
        return <AuthLoadingScreen />;
    }
    if (status === 'unauthenticated') return <Navigate to="/login" replace />;
    if (status === 'forbidden') return <Navigate to="/" replace />;

    return children;
};

SuperuserRoute.propTypes = {
    children: PropTypes.node.isRequired,
};

export default SuperuserRoute;
