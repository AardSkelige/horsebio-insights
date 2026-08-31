import PropTypes from 'prop-types';
import { Bell } from 'lucide-react';
import { useNotifications } from '../../contexts/NotificationsContext';
import UtilBtn from '../layout/sidebar/UtilBtn';
import './notifications.css';

// Уровень значка считает сервер — по самому серьёзному непрочитанному
// (`counts.level`). Складывать его на клиенте из counts.critical/warning нельзя:
// те считаются по всему списку, и одно прочитанное критическое красило бы точку
// в красный, когда нового осталось только информационное.
const toneOf = (counts) => (counts.unseen > 0 ? counts.level : null);

/**
 * Колокольчик в сайдбаре — рядом с «Обновить данные».
 *
 * Показывает непрочитанные: прочитанное уже не сигнал, а список никуда
 * не делся — он в панели. Когда всё прочитано, значка нет вовсе.
 */
export default function NotificationsBell({ expanded }) {
    const { counts, openPanel } = useNotifications();
    const tone = toneOf(counts);
    const unread = counts.unseen || 0;
    const show = Boolean(tone) && unread > 0;

    return (
        <UtilBtn
            icon={Bell}
            label="Уведомления"
            expanded={expanded}
            onClick={openPanel}
            badge={show && (
                <span className="nt-count">
                    <span className={`nt-dot nt-dot--${tone}`} />
                    {unread}
                </span>
            )}
            marker={show && <span className={`nt-dot nt-dot--${tone} nt-dot--corner`} />}
        />
    );
}

NotificationsBell.propTypes = { expanded: PropTypes.bool.isRequired };

/**
 * Колокольчик в мобильной шапке: на телефоне сайдбар закрыт, и значка из него
 * не видно.
 */
export function NotificationsBarButton() {
    const { counts, openPanel } = useNotifications();
    const tone = toneOf(counts);
    const show = Boolean(tone) && counts.unseen > 0;

    return (
        <button
            type="button"
            onClick={openPanel}
            aria-label={show ? `Уведомления: ${counts.unseen} новых` : 'Уведомления'}
            style={{
                position: 'relative',
                marginLeft: 'auto',
                width: 32,
                height: 32,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: 8,
                border: 'none',
                background: 'transparent',
                color: 'var(--muted)',
                cursor: 'pointer',
                flexShrink: 0,
            }}
        >
            <Bell size={18} />
            {show && (
                <span
                    className={`nt-dot nt-dot--${tone} nt-dot--corner`}
                    style={{ top: 6, right: 6, boxShadow: '0 0 0 2px var(--canvas)' }}
                />
            )}
        </button>
    );
}
