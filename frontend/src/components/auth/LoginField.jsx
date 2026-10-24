import PropTypes from 'prop-types';
import { ArrowRight, Loader2 } from 'lucide-react';

const LoginField = ({
    fieldRef, usernameRef, passwordRef, step, username, password,
    onUsernameChange, onPasswordChange, ready, busy,
}) => {
    const onPassword = step === 'password';

    return (
        <div ref={fieldRef} className="login-field">
            <div className="login-track" data-step={step}>
                <input
                    ref={usernameRef}
                    name="username"
                    type="text"
                    autoComplete="username"
                    autoCapitalize="none"
                    autoCorrect="off"
                    spellCheck={false}
                    enterKeyHint="next"
                    placeholder="Имя пользователя"
                    aria-label="Имя пользователя"
                    value={username}
                    tabIndex={onPassword ? -1 : 0}
                    aria-hidden={onPassword || undefined}
                    onChange={(e) => onUsernameChange(e.target.value)}
                />
                <input
                    ref={passwordRef}
                    name="password"
                    type="password"
                    autoComplete="current-password"
                    enterKeyHint="go"
                    placeholder="Пароль"
                    aria-label="Пароль"
                    value={password}
                    tabIndex={onPassword ? 0 : -1}
                    aria-hidden={!onPassword || undefined}
                    onChange={(e) => onPasswordChange(e.target.value)}
                />
            </div>
            <button
                type="submit"
                className="login-go"
                data-ready={ready || undefined}
                disabled={busy}
                aria-label={onPassword ? 'Войти' : 'Дальше'}
            >
                <span className="login-go__icon" data-off={busy || undefined}>
                    <ArrowRight size={18} />
                </span>
                <span className="login-go__icon" data-off={!busy || undefined}>
                    <Loader2 size={18} className="animate-spin" />
                </span>
            </button>
        </div>
    );
};

LoginField.propTypes = {
    fieldRef: PropTypes.object.isRequired,
    usernameRef: PropTypes.object.isRequired,
    passwordRef: PropTypes.object.isRequired,
    step: PropTypes.oneOf(['user', 'password']).isRequired,
    username: PropTypes.string.isRequired,
    password: PropTypes.string.isRequired,
    onUsernameChange: PropTypes.func.isRequired,
    onPasswordChange: PropTypes.func.isRequired,
    ready: PropTypes.bool.isRequired,
    busy: PropTypes.bool.isRequired,
};

export default LoginField;
