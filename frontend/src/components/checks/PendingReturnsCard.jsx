import PropTypes from 'prop-types';
import { ChevronRight, PackageOpen } from 'lucide-react';
import InfoTip from './InfoTip';

export const PENDING_RETURNS_HINT =
    'Когда маркетплейс ставит заказу статус «возврат», монитор возвратов сам создаёт черновик документа — '
    + 'так видно, что товар должен вернуться и сколько денег в нём зависло. Когда товар физически приходит '
    + 'на склад, документ проводят — и возврат отсюда исчезает. Если возврат висит дольше месяца, товар, '
    + 'похоже, застрял — надо смотреть в кабинете маркетплейса, где он.';

const numStyle = (color, size = 24) => ({
    fontFamily: 'var(--serif)', fontSize: size, fontWeight: 400, letterSpacing: '-0.02em',
    lineHeight: 1.15, color, fontVariantNumeric: 'lining-nums', fontFeatureSettings: '"lnum" 1',
});

export function fmtRub(v) {
    return `${Math.round(v || 0).toLocaleString('ru-RU')} ₽`;
}

/** Индикатор возвратов, ждущих поступления товара — на странице /checks.
 *  Не проверка: черновики возвратов создаются намеренно, это счётчик зависших денег. */
export default function PendingReturnsCard({ pending, onOpen }) {
    if (!pending) return null;
    const { count = 0, total_rub = 0, overdue = 0, overdue_rub = 0, warn_days = 30 } = pending;

    return (
        <button
            onClick={count > 0 ? onOpen : undefined}
            style={{
                width: '100%', display: 'flex', alignItems: 'center', gap: 14, padding: '16px 18px',
                marginBottom: 28, borderRadius: 14, textAlign: 'left',
                background: 'var(--surface-card)', border: '1px solid var(--hairline)',
                cursor: count > 0 ? 'pointer' : 'default',
            }}>
            <PackageOpen size={22} style={{ color: overdue ? '#b08a1f' : 'var(--muted)', flexShrink: 0 }} />
            <div style={{ minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 14, fontWeight: 600, color: 'var(--ink)' }}>
                    Возвраты в пути
                    <InfoTip text={PENDING_RETURNS_HINT} width={300} />
                </div>
                <div style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 2 }}>
                    Черновики возвратов ВБ/Озон — ждут поступления товара на склад
                </div>
            </div>
            <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 22, flexShrink: 0 }}>
                {count === 0 ? (
                    <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--success)' }}>✓ Нет возвратов в ожидании</span>
                ) : (
                    <>
                        <div>
                            <div style={numStyle('var(--ink)')}>{count}</div>
                            <div style={{ fontSize: 11, color: 'var(--muted)' }}>возвратов</div>
                        </div>
                        <div>
                            <div style={numStyle('var(--ink)')}>{fmtRub(total_rub)}</div>
                            <div style={{ fontSize: 11, color: 'var(--muted)' }}>зависло</div>
                        </div>
                        {overdue > 0 && (
                            <div style={{ padding: '6px 12px', borderRadius: 10, background: 'rgba(176,138,31,0.10)' }}>
                                <div style={numStyle('#b08a1f', 18)}>{overdue} · {fmtRub(overdue_rub)}</div>
                                <div style={{ fontSize: 11, color: '#b08a1f', fontWeight: 600 }}>дольше {warn_days} дн.</div>
                            </div>
                        )}
                        <ChevronRight size={17} style={{ color: 'var(--muted-soft)' }} />
                    </>
                )}
            </div>
        </button>
    );
}

PendingReturnsCard.propTypes = {
    pending: PropTypes.shape({
        count: PropTypes.number, total_rub: PropTypes.number,
        overdue: PropTypes.number, overdue_rub: PropTypes.number, warn_days: PropTypes.number,
    }),
    onOpen: PropTypes.func,
};
