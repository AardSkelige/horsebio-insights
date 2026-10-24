const DRAW_MS = 1200;
const FILL_FROM = 700;
const FILL_MS = 800;
const WALK_MS = 100000;
const HOLD_MS = 2500;
const IDLE_MS = 1200;

const clamp01 = (p) => Math.min(1, Math.max(0, p));
const easeOut = (p) => 1 - (1 - clamp01(p)) ** 3;

export const withAlpha = (hex, alpha) => {
    const h = hex.replace('#', '');
    const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
    const n = parseInt(full, 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
};

export const formatValue = (value, unit) => (value >= 10000
    ? `${Math.round(value / 1000).toLocaleString('ru-RU')} тыс. ${unit}`
    : `${value.toLocaleString('ru-RU')} ${unit}`);

const dayLabel = (iso, long) => new Date(`${iso}T12:00:00`)
    .toLocaleDateString('ru-RU', { day: 'numeric', month: long ? 'long' : 'short' })
    .replace('.', '');

export const createWalker = () => ({ x: null, idle: -Infinity, hold: 0, fade: 0, last: null, a: 0 });

export function drawPulse(ctx, view) {
    const { width: W, box, points, unit, colors, el, t, reduced, intro, pointer, walker, dark } = view;
    const n = points.length;
    const values = points.map((p) => p.value);
    const max = Math.max(1, ...values) * 1.1;
    const left = box.x, span = box.w, top = box.y, base = box.y + box.h;
    const X = (i) => left + span * i / (n - 1);
    const Y = (v) => top + box.h * (1 - v / max);
    const yAt = (px) => {
        const fi = Math.min(n - 1, Math.max(0, (px - left) / span * (n - 1)));
        const i0 = Math.min(n - 2, Math.floor(fi)), u = fi - i0;
        return Y(values[i0]) + (Y(values[i0 + 1]) - Y(values[i0])) * (u * u * (3 - 2 * u));
    };
    const play = intro && !reduced;
    const drawMs = play ? DRAW_MS : 0;
    const draw = play ? easeOut(el / DRAW_MS) : 1;
    const fillIn = play ? easeOut((el - FILL_FROM) / FILL_MS) : 1;
    const tt = reduced ? 0 : t;

    const glowK = dark ? 1.6 : 1.5;
    const fadeIn = play ? easeOut(el / 2500) : 1;
    const blob = (x, y, r, a) => {
        const g = ctx.createRadialGradient(x, y, 0, x, y, r);
        g.addColorStop(0, withAlpha(colors.glow, a));
        g.addColorStop(0.5, withAlpha(colors.glow, a * 0.35));
        g.addColorStop(1, withAlpha(colors.glow, 0));
        ctx.fillStyle = g;
        ctx.fillRect(x - r, y - r, r * 2, r * 2);
    };
    const reach = Math.max(W, box.h * 3);
    blob(left + span * (0.45 + 0.3 * Math.sin(tt * 0.00009)), top + box.h * (0.55 + 0.35 * Math.sin(tt * 0.00013 + 1.3)), reach * 0.32, 0.075 * glowK * fadeIn * (0.85 + 0.15 * Math.sin(tt * 0.0006)));
    blob(left + span * (0.2 + 0.15 * Math.sin(tt * 0.00011 + 2)), top + box.h * (0.4 + 0.3 * Math.sin(tt * 0.00017)), reach * 0.2, 0.05 * glowK * fadeIn);

    ctx.font = `12px ${colors.font}`;
    ctx.textBaseline = 'top';
    ctx.globalAlpha = play ? clamp01(el / 900) : 1;
    ctx.strokeStyle = colors.hairline;
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(left, base); ctx.lineTo(left + span, base); ctx.stroke();
    ctx.fillStyle = colors.muted;
    for (let i = n - 1; i >= 0; i -= 7) {
        const label = i === n - 1 ? 'сегодня' : dayLabel(points[i].date, false);
        const tw = ctx.measureText(label).width;
        ctx.fillText(label, Math.min(Math.max(X(i) - tw / 2, left), left + span - tw), base + 8);
        ctx.fillRect(X(i) - 0.5, base, 1, 4);
    }
    ctx.globalAlpha = 1;

    const path = new Path2D();
    path.moveTo(X(0), Y(values[0]));
    for (let i = 0; i < n - 1; i++) {
        const xm = (X(i) + X(i + 1)) / 2;
        path.bezierCurveTo(xm, Y(values[i]), xm, Y(values[i + 1]), X(i + 1), Y(values[i + 1]));
    }
    const area = new Path2D(path);
    area.lineTo(X(n - 1), base); area.lineTo(X(0), base); area.closePath();
    const fill = ctx.createLinearGradient(0, top, 0, base);
    fill.addColorStop(0, withAlpha(colors.line, 0.19));
    fill.addColorStop(1, withAlpha(colors.line, 0));

    ctx.save();
    ctx.beginPath(); ctx.rect(0, 0, left + span * draw + 1, base + 1); ctx.clip();
    ctx.globalAlpha = fillIn;
    ctx.fillStyle = fill; ctx.fill(area);
    ctx.globalAlpha = 1;
    ctx.shadowColor = withAlpha(colors.glow, dark ? 0.4 : 0.8);
    ctx.shadowBlur = (dark ? 10 : 16) + (reduced ? 0 : 4 * Math.sin(t * 0.0011));
    ctx.strokeStyle = colors.line; ctx.lineWidth = 2.2; ctx.lineJoin = 'round';
    ctx.stroke(path);
    ctx.restore();

    const ex = X(n - 1), ey = Y(values[n - 1]);
    if (draw < 0.999) {
        if (el <= 0) return;
        const px = left + span * draw;
        ctx.fillStyle = colors.line;
        ctx.beginPath(); ctx.arc(px, yAt(px), 4, 0, Math.PI * 2); ctx.fill();
    } else {
        const ph = reduced ? 0 : ((el - drawMs) % 1800) / 1800;
        blob(ex, ey, 150, 0.11 * glowK * (0.7 + 0.3 * Math.sin(tt * 0.0012)));
        ctx.fillStyle = colors.line;
        ctx.globalAlpha = 0.3 * (1 - ph);
        ctx.beginPath(); ctx.arc(ex, ey, 5 + 18 * easeOut(ph), 0, Math.PI * 2); ctx.fill();
        ctx.globalAlpha = 1;
        ctx.beginPath(); ctx.arc(ex, ey, 5, 0, Math.PI * 2); ctx.fill();
    }

    const inBand = draw >= 0.999 && pointer.on && pointer.y > top - 40 && pointer.y < base + 30 && pointer.x > left - 20 && pointer.x < left + span + 20;
    const dt = walker.last == null ? 0 : Math.min(64, el - walker.last);
    walker.last = el;
    if (walker.x == null) walker.x = left;
    if (inBand) {
        walker.x += (Math.min(Math.max(pointer.x, left), left + span) - walker.x) * 0.18;
        walker.idle = el; walker.hold = 0; walker.fade = 1;
    } else if (play && el < DRAW_MS) {
        walker.x = left; walker.fade = 0;
    } else if (!reduced && el - walker.idle > IDLE_MS) {
        if (walker.x < left + span - 0.5) {
            walker.x = Math.min(left + span, walker.x + span / WALK_MS * dt);
            walker.fade += (1 - walker.fade) * 0.04;
        } else if ((walker.hold += dt) > HOLD_MS) {
            walker.fade -= dt / 600;
            if (walker.fade <= 0) Object.assign(walker, { x: left, hold: 0, fade: 0 });
        }
    }
    walker.a += ((inBand ? 1 : reduced ? 0 : Math.max(0, walker.fade)) - walker.a) * 0.12;

    const hx = walker.x, hy = yAt(hx);
    const hi = Math.round((hx - left) / span * (n - 1));
    if (walker.a > 0.02) {
        ctx.globalAlpha = 0.45 * walker.a;
        ctx.strokeStyle = colors.muted; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(hx, top - 6); ctx.lineTo(hx, base); ctx.stroke();
        ctx.globalAlpha = walker.a;
        ctx.fillStyle = colors.canvas; ctx.strokeStyle = colors.line; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(hx, hy, 4.5, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
        ctx.globalAlpha = 1;
    }

    const tag = (idx, x, y, alpha) => {
        if (alpha < 0.02) return;
        const label = `${idx === n - 1 ? 'Сегодня' : dayLabel(points[idx].date, true)}: ${formatValue(values[idx], unit)}`;
        ctx.font = `600 13px ${colors.font}`;
        ctx.textBaseline = 'bottom';
        const tw = ctx.measureText(label).width;
        ctx.globalAlpha = alpha;
        ctx.fillStyle = colors.ink;
        ctx.fillText(label, Math.min(Math.max(x - tw / 2, left), left + span - tw), Math.min(y, top) - 14);
        ctx.globalAlpha = 1;
    };
    tag(n - 1, ex, ey, draw < 0.999 ? 0 : 1 - walker.a);
    tag(Math.min(n - 1, Math.max(0, hi)), hx, hy, walker.a);
}
