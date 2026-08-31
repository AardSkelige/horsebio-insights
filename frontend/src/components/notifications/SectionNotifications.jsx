import PropTypes from 'prop-types';
import { FadeRise } from '../ui/motion';
import { useSectionNotifications } from '../../contexts/NotificationsContext';
import NotificationItem from './NotificationItem';
import './notifications.css';

const LEVELS = ['critical', 'warning', 'info'];

/**
 * Уведомления раздела — над содержимым страницы.
 *
 * Только заголовок и действие: цифры уже есть в самом разделе, и повторять их
 * значит написать одно и то же дважды. Ссылки тоже не нужны — человек уже здесь.
 */
export default function SectionNotifications({ source }) {
    const { items } = useSectionNotifications(source);
    if (items.length === 0) return null;

    const tone = LEVELS.find((level) => items.some((item) => item.level === level));

    return (
        <FadeRise className={`nt-section nt-section--${tone}`}>
            {items.map((item) => (
                <NotificationItem key={item.key} item={item} variant="line" />
            ))}
        </FadeRise>
    );
}

SectionNotifications.propTypes = { source: PropTypes.string.isRequired };
