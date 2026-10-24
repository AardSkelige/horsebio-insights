import { useEffect, useState } from 'react';

const KEY = 'viewport-debug';

const readFlag = () => {
    const param = new URLSearchParams(window.location.search).get('debug');
    try {
        if (param === '1') localStorage.setItem(KEY, '1');
        if (param === '0') localStorage.removeItem(KEY);
        return localStorage.getItem(KEY) === '1';
    } catch {
        return param === '1';
    }
};

const probe = (style) => {
    const el = document.createElement('div');
    Object.assign(el.style, { position: 'fixed', visibility: 'hidden', pointerEvents: 'none', top: '0', left: '0', ...style });
    document.body.appendChild(el);
    const cs = getComputedStyle(el);
    const values = {
        h: Math.round(el.getBoundingClientRect().height),
        top: parseFloat(cs.paddingTop) || 0,
        right: parseFloat(cs.paddingRight) || 0,
        bottom: parseFloat(cs.paddingBottom) || 0,
        left: parseFloat(cs.paddingLeft) || 0,
    };
    el.remove();
    return values;
};

const rect = (selector) => {
    const el = document.querySelector(selector);
    if (!el) return '—';
    const r = el.getBoundingClientRect();
    return `${Math.round(r.top)}…${Math.round(r.bottom)} (h${Math.round(r.height)})`;
};

const measure = () => {
    const vv = window.visualViewport;
    const safe = probe({ paddingTop: 'env(safe-area-inset-top)', paddingRight: 'env(safe-area-inset-right)', paddingBottom: 'env(safe-area-inset-bottom)', paddingLeft: 'env(safe-area-inset-left)' });
    const unit = (u) => probe({ height: `100${u}` }).h;
    const standalone = window.navigator.standalone === true || window.matchMedia('(display-mode: standalone)').matches;
    return [
        `ios ${(navigator.userAgent.match(/OS (\d+[_\d]*)/) || [])[1] || '?'} · приложение ${standalone ? 'да' : 'нет'}`,
        `screen ${screen.width}×${screen.height} · inner ${innerWidth}×${innerHeight} · outerH ${outerHeight}`,
        vv ? `visual ${Math.round(vv.width)}×${Math.round(vv.height)} · offTop ${Math.round(vv.offsetTop)} · offLeft ${Math.round(vv.offsetLeft)} · pageTop ${Math.round(vv.pageTop)} · scale ${vv.scale.toFixed(2)}` : 'visual —',
        `doc client ${document.documentElement.clientHeight} · scrollH ${document.documentElement.scrollHeight} · scrollY ${Math.round(scrollY)} · scrollX ${Math.round(scrollX)}`,
        `safe top ${safe.top} · bottom ${safe.bottom} · left ${safe.left} · right ${safe.right}`,
        `vh ${unit('vh')} · dvh ${unit('dvh')} · svh ${unit('svh')} · lvh ${unit('lvh')}`,
        `shell ${rect('.app-shell')}`,
        `topbar ${rect('.app-topbar')}`,
        `login ${rect('.login-page')}`,
    ];
};

const TAPS = 5;
const TAP_WINDOW_MS = 2000;

const toggle = (next) => {
    try {
        if (next) localStorage.setItem(KEY, '1');
        else localStorage.removeItem(KEY);
    } catch {
        return;
    }
    window.location.reload();
};

export default function ViewportDebug() {
    const [on] = useState(readFlag);
    const [lines, setLines] = useState([]);

    useEffect(() => {
        let taps = [];
        const onClick = (event) => {
            if (!event.target.closest?.('[data-debug-tap]')) return;
            const now = Date.now();
            taps = [...taps.filter((t) => now - t < TAP_WINDOW_MS), now];
            if (taps.length >= TAPS) toggle(!on);
        };
        document.addEventListener('click', onClick);
        return () => document.removeEventListener('click', onClick);
    }, [on]);

    useEffect(() => {
        if (!on) return undefined;
        document.documentElement.classList.add('vp-debug');
        const update = () => setLines(measure());
        update();
        const timer = setInterval(update, 500);
        const vv = window.visualViewport;
        window.addEventListener('scroll', update, { passive: true });
        window.addEventListener('resize', update);
        vv?.addEventListener('resize', update);
        vv?.addEventListener('scroll', update);
        return () => {
            clearInterval(timer);
            window.removeEventListener('scroll', update);
            window.removeEventListener('resize', update);
            vv?.removeEventListener('resize', update);
            vv?.removeEventListener('scroll', update);
            document.documentElement.classList.remove('vp-debug');
        };
    }, [on]);

    if (!on) return null;

    return (
        <pre className="vp-debug__panel" aria-hidden="true">{lines.join('\n')}</pre>
    );
}
