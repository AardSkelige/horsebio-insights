// frontend/src/components/auth/LoginPage.jsx
import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { AlertCircle, ArrowRight, Database, FileSpreadsheet, LockKeyhole, Moon, PackageSearch, Sparkles, Sun } from 'lucide-react';
import './LoginPage.css';
import { setAuthStatus } from '../../utils/authSession';
import { authApi } from '../../api/authApi';

const LoginPage = () => {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [errorMessage, setErrorMessage] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'light');
    const navigate = useNavigate();
    const location = useLocation();
    const from = location.state?.from?.pathname || '/';

    useEffect(() => {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
    }, [theme]);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setErrorMessage('');
        setIsLoading(true);

        try {
            const response = await authApi.login(username, password);
            const data = await response.json();

            if (response.ok) {
                setAuthStatus({ isAuthenticated: true });
                navigate(from, { replace: true });
            } else {
                setErrorMessage(data.message || 'Ошибка входа в систему');
            }
        } catch {
            setErrorMessage('Ошибка соединения с сервером');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <main className="login-page">
            <button
                type="button"
                className="login-theme-toggle"
                onClick={() => setTheme(current => current === 'dark' ? 'light' : 'dark')}
                title={theme === 'dark' ? 'Светлая тема' : 'Темная тема'}
            >
                {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
            </button>

            <section className="login-shell">
                <div className="login-brand">
                    <div className="login-wordmark">
                        <span className="app-logo-mark login-wordmark__mark" aria-hidden="true" />
                        HorseBio Insights
                    </div>
                    <div>
                        <p className="login-kicker">
                            <Sparkles size={14} />
                            Операционная аналитика
                        </p>
                        <h1>Панель управления HorseBio</h1>
                        <p className="login-lead">
                            Отчеты, синхронизации, закупки и маркетплейс-аналитика в одном рабочем контуре.
                        </p>
                    </div>

                    <div className="login-product-panel login-data-map" aria-label="Схема потоков данных">
                        <div className="login-product-panel__header">
                            <span>Потоки данных</span>
                            <span>Рабочий контур</span>
                        </div>

                        <div className="login-data-map__canvas">
                            <svg className="login-flow-svg" viewBox="0 0 520 250" preserveAspectRatio="none" aria-hidden="true">
                                <path className="login-flow-path" d="M370 78 H150" />
                                <path className="login-flow-path" d="M150 138 L260 184" />
                                <path className="login-flow-path" d="M370 138 L260 184" />
                                <path className="login-flow-path-active login-flow-path-active--one" d="M370 78 H150" />
                                <path className="login-flow-path-active login-flow-path-active--two" d="M150 138 L260 184" />
                                <path className="login-flow-path-active login-flow-path-active--three" d="M370 138 L260 184" />
                            </svg>

                            <div className="login-data-node login-data-node--source">
                                <span><Database size={17} /></span>
                                <strong>МойСклад</strong>
                                <small>продажи<br />и остатки</small>
                            </div>

                            <div className="login-data-node login-data-node--market">
                                <span><PackageSearch size={17} /></span>
                                <strong>OZON</strong>
                                <small>реклама<br />и FBO</small>
                            </div>

                            <div className="login-data-node login-data-node--report">
                                <span><FileSpreadsheet size={17} /></span>
                                <strong>HorseBio Insights</strong>
                                <small>аналитика<br />и решения</small>
                            </div>
                        </div>

                        <div className="login-data-map__footer">
                            <span className="login-process-dot" />
                            Данные из МойСклад и OZON собираются в HorseBio Insights
                        </div>
                    </div>
                </div>

                <form className="login-card" onSubmit={handleSubmit}>
                    <div className="login-card__icon">
                        <LockKeyhole size={18} />
                    </div>
                    <div className="login-card__heading">
                        <h2>Авторизация</h2>
                        <p>Введите учетные данные для доступа к панели.</p>
                    </div>

                    <div className="login-fields">
                        <label>
                            <span>Имя пользователя</span>
                            <input
                                id="username"
                                name="username"
                                type="text"
                                required
                                value={username}
                                onChange={(e) => setUsername(e.target.value)}
                                placeholder="Имя пользователя"
                            />
                        </label>
                        <label>
                            <span>Пароль</span>
                            <input
                                id="password"
                                name="password"
                                type="password"
                                required
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                placeholder="Пароль"
                            />
                        </label>
                    </div>

                    {errorMessage && (
                        <div className="login-error">
                            <AlertCircle size={16} />
                            <span>{errorMessage}</span>
                        </div>
                    )}

                    <button type="submit" disabled={isLoading} className="login-submit">
                        {isLoading ? 'Вход...' : 'Войти'}
                        <ArrowRight size={16} />
                    </button>
                </form>
            </section>
        </main>
    );
};

export default LoginPage;
