import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import PropTypes from 'prop-types';
import { AnimatePresence, m } from 'motion/react';
import { BellOff, BellRing, CircleAlert, Share, SquarePlus } from 'lucide-react';
import { Button } from '../ui';
import { pushApi } from '../../api/pushApi';
import { canOffer, dismissPush, enablePush, onIOS, subscribeDevice, usePush } from '../../hooks/usePush';

const SHOW_DELAY_MS = 1200;

const deniedHint = () => (onIOS()
    ? 'Включите их в «Настройках» iPhone: Уведомления → HorseBio.'
    : 'Разрешите их в настройках браузера для этого сайта.');

export default function PushSheet({ quiet = false }) {
    const navigate = useNavigate();
    const push = usePush();
    const [ready, setReady] = useState(false);
    const [busy, setBusy] = useState(false);
    const [outcome, setOutcome] = useState(null);

    useEffect(() => {
        if (push.permission !== 'granted') return;
        subscribeDevice().catch(() => {});
    }, [push.permission]);

    useEffect(() => {
        if (!('serviceWorker' in navigator)) return undefined;
        const onMessage = (event) => {
            if (event.data?.type === 'open' && event.data.path) navigate(event.data.path);
        };
        navigator.serviceWorker.addEventListener('message', onMessage);
        return () => navigator.serviceWorker.removeEventListener('message', onMessage);
    }, [navigate]);

    useEffect(() => {
        if (quiet) return undefined;
        const timer = setTimeout(() => setReady(true), SHOW_DELAY_MS);
        return () => clearTimeout(timer);
    }, [quiet]);

    const open = ready && !quiet && (outcome !== null || (!push.dismissed && canOffer(push)));

    const enable = async () => {
        setBusy(true);
        try {
            const permission = await enablePush();
            if (permission === 'granted') {
                await pushApi.test();
                setOutcome({ kind: 'ok' });
            } else {
                setOutcome({ kind: 'denied' });
            }
        } catch (error) {
            setOutcome({ kind: 'error', text: error?.message || String(error) });
        } finally {
            setBusy(false);
        }
    };

    const close = () => {
        setOutcome(null);
        dismissPush();
    };

    const body = () => {
        if (outcome?.kind === 'ok') {
            return (
                <>
                    <h2 className="nt-sheet__title">Уведомления включены</h2>
                    <p className="nt-sheet__text">Прислали тестовое, оно появится через пару секунд.</p>
                    <Button variant="primary" size="lg" block onClick={close}>Понятно</Button>
                </>
            );
        }
        if (outcome?.kind === 'denied') {
            return (
                <>
                    <h2 className="nt-sheet__title">Уведомления запрещены</h2>
                    <p className="nt-sheet__text">{deniedHint()}</p>
                    <Button variant="primary" size="lg" block onClick={close}>Понятно</Button>
                </>
            );
        }
        if (outcome?.kind === 'error') {
            return (
                <>
                    <h2 className="nt-sheet__title">Не получилось включить</h2>
                    <p className="nt-sheet__text">Пришлите этот текст разработчику: {outcome.text}</p>
                    <Button variant="primary" size="lg" block onClick={close}>Понятно</Button>
                </>
            );
        }
        if (push.needsInstall) {
            return (
                <>
                    <h2 className="nt-sheet__title">Уведомления на iPhone</h2>
                    <p className="nt-sheet__text">Чтобы получать уведомления о делах, добавьте HorseBio на экран «Домой».</p>
                    <ol className="nt-sheet__steps">
                        <li><Share size={18} aria-hidden="true" />Нажмите «Поделиться» внизу Safari</li>
                        <li><SquarePlus size={18} aria-hidden="true" />Выберите «На экран „Домой“»</li>
                        <li><BellRing size={18} aria-hidden="true" />Откройте HorseBio с иконки и включите уведомления</li>
                    </ol>
                    <Button variant="primary" size="lg" block onClick={close}>Понятно</Button>
                </>
            );
        }
        return (
            <>
                <h2 className="nt-sheet__title">Уведомления о делах</h2>
                <p className="nt-sheet__text">Пришлём на это устройство, когда в ваших разделах появится что-то срочное.</p>
                <Button variant="primary" size="lg" block loading={busy} onClick={enable}>Включить</Button>
                <Button variant="quiet" size="lg" block onClick={close}>Не сейчас</Button>
            </>
        );
    };

    const Icon = outcome?.kind === 'denied' ? BellOff : outcome?.kind === 'error' ? CircleAlert : BellRing;

    return createPortal(
        <AnimatePresence>
            {open && (
                <m.div
                    className="nt-sheet"
                    role="dialog"
                    aria-label="Уведомления"
                    initial={{ opacity: 0, y: 40 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 40, transition: { duration: 0.2 } }}
                    transition={{ type: 'spring', stiffness: 350, damping: 32 }}
                >
                    <span className="nt-sheet__badge" aria-hidden="true"><Icon size={22} /></span>
                    {body()}
                </m.div>
            )}
        </AnimatePresence>,
        document.body,
    );
}

PushSheet.propTypes = { quiet: PropTypes.bool };
