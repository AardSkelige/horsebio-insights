// frontend/src/components/auth/LoginPage.jsx
import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { AnimatePresence, m, useAnimate, useReducedMotion } from 'motion/react';
import { UserRound } from 'lucide-react';
import './LoginPage.css';
import LoginField from './LoginField';
import LoginThreads from './LoginThreads';
import { setAuthStatus } from '../../utils/authSession';
import { authApi } from '../../api/authApi';
import { useIsMobile } from '../../hooks/useIsMobile';
import { smoothNavigate, Stagger, StaggerItem, switchTheme, ThemeIcon } from '../ui/motion';

const LoginPage = () => {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [step, setStep] = useState('user');
    const [errorMessage, setErrorMessage] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'light');
    const usernameRef = useRef(null);
    const passwordRef = useRef(null);
    const [fieldRef, animate] = useAnimate();
    const reduceMotion = useReducedMotion();
    const isMobile = useIsMobile();
    const navigate = useNavigate();
    const location = useLocation();
    const from = location.state?.from?.pathname || '/';
    const onPassword = step === 'password';
    const ready = onPassword ? password.length > 0 : username.trim().length > 0;

    useEffect(() => {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
    }, [theme]);

    const shake = () => {
        if (reduceMotion || !fieldRef.current) return;
        animate(fieldRef.current, { x: [0, -8, 8, -5, 5, 0] }, { duration: 0.4, ease: 'easeOut' });
    };

    const editUser = () => {
        setStep('user');
        setErrorMessage('');
        usernameRef.current?.focus({ preventScroll: true });
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!ready) {
            shake();
            return;
        }
        if (!onPassword) {
            setErrorMessage('');
            setStep('password');
            passwordRef.current?.focus({ preventScroll: true });
            return;
        }

        setErrorMessage('');
        setIsLoading(true);
        try {
            const data = await authApi.login(username.trim(), password);

            if (data.status === 'success') {
                setAuthStatus({ isAuthenticated: true });
                smoothNavigate(navigate, from, { replace: true, slow: true });
            } else {
                setErrorMessage(data.message || 'Ошибка входа в систему');
                shake();
            }
        } catch (error) {
            if (!error.status) setErrorMessage('Нет связи с сервером');
            else if (error.status >= 500) setErrorMessage('Сервер временно недоступен, попробуйте позже');
            else setErrorMessage(error.data?.message || 'Не удалось войти');
            shake();
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <main className="login-page">
            {!isMobile && <LoginThreads />}
            <button
                type="button"
                className="login-theme-toggle"
                onClick={(event) => switchTheme(theme === 'dark' ? 'light' : 'dark', setTheme, event)}
                title={theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}
            >
                <ThemeIcon dark={theme === 'dark'} size={16} />
            </button>

            <Stagger className="login-column">
                <StaggerItem>
                    <span className="app-logo-mark login-mark" aria-hidden="true" />
                </StaggerItem>
                <StaggerItem>
                    <h1 className="login-title">Вход в Insights</h1>
                    <div className="login-subtitle">
                        <p data-off={onPassword || undefined} aria-hidden={onPassword || undefined}>Система аналитики HorseBio</p>
                        <p data-off={!onPassword || undefined} aria-hidden={!onPassword || undefined}>Введите пароль</p>
                    </div>
                </StaggerItem>

                <StaggerItem className="login-form-wrap">
                    <AnimatePresence initial={false}>
                        {onPassword && (
                            <m.div
                                className="login-who-row"
                                initial={{ height: 0, opacity: 0 }}
                                animate={{ height: 'auto', opacity: 1 }}
                                exit={{ height: 0, opacity: 0 }}
                                transition={{ duration: 0.25, ease: 'easeOut' }}
                            >
                                <span className="login-who">
                                    <UserRound size={14} aria-hidden="true" />
                                    <span className="login-who__name">{username.trim()}</span>
                                    <button type="button" onClick={editUser}>Изменить</button>
                                </span>
                            </m.div>
                        )}
                    </AnimatePresence>

                    <form onSubmit={handleSubmit} noValidate>
                        <LoginField
                            fieldRef={fieldRef}
                            usernameRef={usernameRef}
                            passwordRef={passwordRef}
                            step={step}
                            username={username}
                            password={password}
                            onUsernameChange={setUsername}
                            onPasswordChange={setPassword}
                            ready={ready}
                            busy={isLoading}
                        />
                        <AnimatePresence>
                            {errorMessage && (
                                <m.p
                                    className="login-error"
                                    role="alert"
                                    initial={{ height: 0, opacity: 0 }}
                                    animate={{ height: 'auto', opacity: 1 }}
                                    exit={{ height: 0, opacity: 0 }}
                                    transition={{ duration: 0.2, ease: 'easeOut' }}
                                >
                                    {errorMessage}
                                </m.p>
                            )}
                        </AnimatePresence>
                    </form>
                </StaggerItem>
            </Stagger>
        </main>
    );
};

export default LoginPage;
