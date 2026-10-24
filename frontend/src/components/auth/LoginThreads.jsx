import { useEffect, useRef } from 'react';

const LINES = 12;
const FRAME_MS = 1000 / 30;

const draw = (ctx, color, width, height, t) => {
    ctx.clearRect(0, 0, width, height);
    ctx.strokeStyle = color;
    ctx.lineWidth = 1;
    for (let i = 0; i < LINES; i += 1) {
        const share = i / (LINES - 1);
        const base = height * (0.58 + share * 0.3);
        const amp = height * (0.02 + share * 0.05);
        ctx.globalAlpha = 0.08 + 0.14 * Math.sin(Math.PI * share);
        ctx.beginPath();
        for (let x = 0; x <= width; x += 8) {
            const k = x / width;
            const y = base
                + amp * Math.sin(k * 5 + t * 0.35 + i * 0.45)
                + amp * 0.6 * Math.sin(k * 11 - t * 0.22 + i * 0.9);
            if (x === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.stroke();
    }
};

const LoginThreads = () => {
    const canvasRef = useRef(null);

    useEffect(() => {
        const canvas = canvasRef.current;
        const ctx = canvas.getContext('2d');
        const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
        const readColor = () => getComputedStyle(canvas).getPropertyValue('--thread-color').trim();
        let color = readColor();
        let width = 0;
        let height = 0;
        let frame = 0;
        let last = 0;

        const resize = () => {
            const dpr = window.devicePixelRatio || 1;
            width = canvas.clientWidth;
            height = canvas.clientHeight;
            canvas.width = Math.round(width * dpr);
            canvas.height = Math.round(height * dpr);
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            draw(ctx, color, width, height, last / 1000);
        };

        const tick = (now) => {
            frame = requestAnimationFrame(tick);
            if (now - last < FRAME_MS) return;
            last = now;
            draw(ctx, color, width, height, now / 1000);
        };

        const start = () => {
            if (motion.matches || document.hidden || frame) return;
            frame = requestAnimationFrame(tick);
        };

        const stop = () => {
            cancelAnimationFrame(frame);
            frame = 0;
        };

        const onVisibility = () => (document.hidden ? stop() : start());
        const onMotion = () => (motion.matches ? stop() : start());
        const themeWatch = new MutationObserver(() => {
            color = readColor();
            draw(ctx, color, width, height, last / 1000);
        });
        const sizeWatch = new ResizeObserver(resize);

        sizeWatch.observe(canvas);
        themeWatch.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
        document.addEventListener('visibilitychange', onVisibility);
        motion.addEventListener('change', onMotion);
        start();

        return () => {
            stop();
            sizeWatch.disconnect();
            themeWatch.disconnect();
            document.removeEventListener('visibilitychange', onVisibility);
            motion.removeEventListener('change', onMotion);
        };
    }, []);

    return <canvas ref={canvasRef} className="login-threads" aria-hidden="true" />;
};

export default LoginThreads;
