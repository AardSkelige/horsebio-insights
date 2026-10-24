import { useEffect, useMemo, useRef } from 'react';
import PropTypes from 'prop-types';
import { useReducedMotion } from 'motion/react';
import { createWalker, drawPulse } from './pulseDraw';

const BLEED = 24;
const LABEL_SPACE = 52;
const DATES_SPACE = 28;
const GLOW_BELOW = 260;
const INTRO_MS = 2600;
const IDLE_FRAME_MS = 50;

const readColors = () => {
    const s = getComputedStyle(document.documentElement);
    const v = (name) => s.getPropertyValue(name).trim();
    return {
        line: v('--primary'),
        glow: v('--accent-glow'),
        ink: v('--ink'),
        muted: v('--muted'),
        canvas: v('--canvas'),
        hairline: v('--hairline'),
        font: v('--sans'),
    };
};

export default function PulseChart({ points, unit, label }) {
    const wrapRef = useRef(null);
    const canvasRef = useRef(null);
    const reduced = useReducedMotion();
    const pointsKey = JSON.stringify(points);
    const series = useMemo(() => JSON.parse(pointsKey), [pointsKey]);

    useEffect(() => {
        const wrap = wrapRef.current;
        const canvas = canvasRef.current;
        if (!wrap || !canvas || series.length < 2) return undefined;
        const ctx = canvas.getContext('2d');
        const pointer = { x: 0, y: 0, on: false };
        const walker = createWalker();
        let colors = readColors();
        let size = { w: 0, h: 0 };
        let raf = 0;
        let timer = 0;
        let visible = true;
        const t0 = performance.now();

        const resize = () => {
            const r = canvas.getBoundingClientRect();
            const dpr = Math.min(window.devicePixelRatio || 1, 2);
            size = { w: r.width, h: r.height };
            canvas.width = r.width * dpr;
            canvas.height = r.height * dpr;
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        };

        const frame = (t) => {
            raf = 0;
            const boxH = wrap.clientHeight - LABEL_SPACE - DATES_SPACE;
            ctx.clearRect(0, 0, size.w, size.h);
            drawPulse(ctx, {
                width: size.w,
                box: { x: BLEED, y: BLEED + LABEL_SPACE, w: size.w - BLEED * 2, h: boxH },
                points: series, unit, colors, t, reduced,
                el: t - t0,
                pointer, walker,
                dark: document.documentElement.dataset.theme === 'dark',
            });
            if (reduced || !visible || document.hidden) return;
            if (!pointer.on && t - t0 > INTRO_MS) {
                timer = setTimeout(() => { timer = 0; wake(); }, IDLE_FRAME_MS);
            } else {
                raf = requestAnimationFrame(frame);
            }
        };
        const wake = () => {
            if (raf) return;
            clearTimeout(timer);
            timer = 0;
            raf = requestAnimationFrame(frame);
        };

        const onMove = (event) => {
            const r = canvas.getBoundingClientRect();
            Object.assign(pointer, { x: event.clientX - r.left, y: event.clientY - r.top, on: true });
            wake();
        };
        const onLeave = () => { pointer.on = false; wake(); };
        const onVisibility = () => { if (!document.hidden) wake(); };

        const resizeObserver = new ResizeObserver(() => { resize(); wake(); });
        resizeObserver.observe(wrap);
        const intersection = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; if (visible) wake(); });
        intersection.observe(wrap);
        const themeObserver = new MutationObserver(() => { colors = readColors(); wake(); });
        themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

        wrap.addEventListener('pointermove', onMove);
        wrap.addEventListener('pointerleave', onLeave);
        document.addEventListener('visibilitychange', onVisibility);
        resize();
        wake();

        return () => {
            cancelAnimationFrame(raf);
            clearTimeout(timer);
            resizeObserver.disconnect();
            intersection.disconnect();
            themeObserver.disconnect();
            wrap.removeEventListener('pointermove', onMove);
            wrap.removeEventListener('pointerleave', onLeave);
            document.removeEventListener('visibilitychange', onVisibility);
        };
    }, [series, unit, reduced]);

    return (
        <figure ref={wrapRef} className="home-pulse" aria-label={label}>
            <figcaption className="home-pulse__caption">{label}</figcaption>
            <canvas
                ref={canvasRef}
                className="home-pulse__canvas"
                style={{
                    left: -BLEED,
                    top: -BLEED,
                    width: `calc(100% + ${BLEED * 2}px)`,
                    height: `calc(100% + ${BLEED + GLOW_BELOW}px)`,
                }}
                aria-hidden="true"
            />
        </figure>
    );
}

PulseChart.propTypes = {
    points: PropTypes.arrayOf(PropTypes.shape({
        date: PropTypes.string.isRequired,
        value: PropTypes.number.isRequired,
    })).isRequired,
    unit: PropTypes.string.isRequired,
    label: PropTypes.string.isRequired,
};
