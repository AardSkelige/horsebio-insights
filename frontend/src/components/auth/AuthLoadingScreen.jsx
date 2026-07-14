const AuthLoadingScreen = () => (
    <div style={{
        position: 'fixed',
        inset: 0,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--canvas)',
        gap: 24,
    }}>
        {/* Логотип */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span
                className="app-logo-mark"
                style={{
                    color: 'var(--primary)',
                    '--logo-mark-width': '28px',
                    '--logo-mark-height': '17px',
                }}
                aria-hidden="true"
            />
            <span style={{
                fontFamily: 'var(--serif)',
                fontSize: 22,
                fontWeight: 400,
                color: 'var(--ink)',
                letterSpacing: '-0.3px',
            }}>
                HorseBio Insights
            </span>
        </div>

        {/* Прогресс-бар */}
        <div style={{
            width: 200,
            height: 2,
            background: 'var(--hairline)',
            borderRadius: 9999,
            overflow: 'hidden',
        }}>
            <div style={{
                height: '100%',
                width: '40%',
                background: 'var(--primary)',
                borderRadius: 9999,
                animation: 'auth-slide 1.4s ease-in-out infinite',
            }} />
        </div>

        {/* Подпись */}
        <span style={{
            fontSize: 13,
            color: 'var(--muted-soft)',
            fontFamily: 'var(--sans)',
        }}>
            Проверка авторизации…
        </span>

        <style>{`
            @keyframes auth-slide {
                0%   { transform: translateX(-100%); }
                50%  { transform: translateX(350%); }
                100% { transform: translateX(-100%); }
            }
        `}</style>
    </div>
);

export default AuthLoadingScreen;
