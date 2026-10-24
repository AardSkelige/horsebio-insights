import { useState } from 'react';
import PropTypes from 'prop-types';
import { BellRing, ChevronRight, Loader2, Send } from 'lucide-react';
import { Notice } from '../ui';
import { pushApi } from '../../api/pushApi';
import { pluralWith } from '../../utils/formatters';
import { canOffer, enablePush, offerPush, onIOS, subscribeDevice, usePush } from '../../hooks/usePush';

const PushRow = ({ icon: Icon, busy = false, onClick, children }) => (
    <button type="button" className="nt-push-row" onClick={onClick} disabled={busy}>
        {busy ? <Loader2 size={16} className="animate-spin" aria-hidden="true" /> : <Icon size={16} aria-hidden="true" />}
        <span className="nt-push-row__text">{children}</span>
        <ChevronRight size={16} aria-hidden="true" />
    </button>
);

PushRow.propTypes = {
    icon: PropTypes.elementType.isRequired,
    busy: PropTypes.bool,
    onClick: PropTypes.func.isRequired,
    children: PropTypes.node.isRequired,
};

export default function PushPanelAction() {
    const push = usePush();
    const [busy, setBusy] = useState(false);
    const [result, setResult] = useState(null);

    const sendTest = async () => {
        setBusy(true);
        setResult(null);
        try {
            await subscribeDevice();
            const { sent, devices } = await pushApi.test();
            setResult(sent
                ? { tone: 'success', text: `Отправлено на ${pluralWith(sent, 'устройство', 'устройства', 'устройств')}` }
                : { tone: 'error', text: devices ? 'Не дошло ни до одного устройства' : 'Это устройство не подписано' });
        } catch (error) {
            setResult({ tone: 'error', text: error.message || 'Не удалось отправить' });
        } finally {
            setBusy(false);
        }
    };

    if (push.permission === 'granted') {
        return (
            <div className="nt-panel__push">
                <PushRow icon={Send} busy={busy} onClick={sendTest}>Прислать тестовое уведомление</PushRow>
                {result && <Notice tone={result.tone}>{result.text}</Notice>}
            </div>
        );
    }

    if (push.permission === 'denied') {
        return (
            <div className="nt-panel__push">
                <Notice tone="warning">
                    {onIOS() ? 'Уведомления не включились. Если HorseBio нет в «Настройках» → «Уведомления», удалите иконку с экрана «Домой» и добавьте заново из Safari.' : 'Уведомления запрещены в настройках браузера для этого сайта.'}
                </Notice>
            </div>
        );
    }

    if (!canOffer(push)) return null;

    return (
        <div className="nt-panel__push">
            <PushRow icon={BellRing} onClick={push.needsInstall ? offerPush : () => enablePush().catch(() => {})}>
                {push.needsInstall ? 'Получать на телефон' : 'Включить на этом устройстве'}
            </PushRow>
        </div>
    );
}
