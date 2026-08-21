import PropTypes from 'prop-types';
import { RefreshCw } from 'lucide-react';
import Button from './Button';

/**
 * Шапка страницы: заголовок, пояснение, действия и время последнего обновления.
 *
 * До появления этого компонента шапка была скопирована примерно в двадцать мест,
 * и заголовок в них разъехался по размерам от 20 до 32 пикселей.
 *
 * Кнопка «Обновить» встроена, потому что она есть почти на каждой странице:
 * передайте `onRefresh`, и она появится в правильном виде и в правильном месте.
 * Дополнительные действия идут в `actions` и встают слева от неё.
 *
 * `refreshLabel` меняет подпись, когда действие называется иначе («Загрузить
 * июль»). Заводить ради этого свою кнопку не нужно — именно так на одной
 * странице появлялась залитая «Обновить» вместо текстовой, как на остальных.
 */
export default function PageHeader({ title, subtitle, actions, onRefresh, refreshing = false, refreshLabel = 'Обновить', updatedAt }) {
    return (
        <header className="ui-page-header">
            <div>
                <h1 className="ui-page-header__title">{title}</h1>
                {subtitle && <p className="ui-page-header__subtitle">{subtitle}</p>}
            </div>

            {(actions || onRefresh || updatedAt) && (
                <div className="ui-page-header__actions">
                    {updatedAt && (
                        <span className="ui-page-header__meta">Обновлено {updatedAt}</span>
                    )}
                    {actions}
                    {onRefresh && (
                        <Button
                            variant="link"
                            icon={RefreshCw}
                            loading={refreshing}
                            onClick={onRefresh}
                        >
                            {refreshLabel}
                        </Button>
                    )}
                </div>
            )}
        </header>
    );
}

PageHeader.propTypes = {
    title: PropTypes.node.isRequired,
    subtitle: PropTypes.node,
    actions: PropTypes.node,
    onRefresh: PropTypes.func,
    refreshing: PropTypes.bool,
    refreshLabel: PropTypes.node,
    updatedAt: PropTypes.string,
};
