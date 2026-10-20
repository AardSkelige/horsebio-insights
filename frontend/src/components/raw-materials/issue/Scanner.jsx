import { useEffect, useMemo, useRef, useState } from 'react';
import PropTypes from 'prop-types';
import { Button, CloseButton, Notice, SectionLabel } from '../../ui';
import { DrawerShell } from '../../ui/motion';
import slotFromCode from './slotFromCode';

const SCAN_EVERY_MS = 150;
const FRAME_WIDTH = 640;

const PROBLEMS = {
    denied: 'Нет доступа к камере. Разрешите его в настройках браузера или выберите ячейку ниже',
    unavailable: 'Камера недоступна. Выберите ячейку ниже',
};

function useSlotScanner(open, videoRef, onFound) {
    const [status, setStatus] = useState('starting');
    const [wrong, setWrong] = useState(false);
    const found = useRef(onFound);
    found.current = onFound;

    useEffect(() => {
        if (!open) return undefined;
        let stopped = false;
        let stream = null;
        let frame = 0;
        let last = 0;
        const canvas = document.createElement('canvas');
        const context = canvas.getContext('2d', { willReadFrequently: true });
        setStatus('starting');
        setWrong(false);

        const start = async () => {
            if (!navigator.mediaDevices?.getUserMedia || !context) {
                setStatus('unavailable');
                return;
            }
            try {
                const [{ default: jsQR }, media] = await Promise.all([
                    import('jsqr'),
                    navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false }),
                ]);
                stream = media;
                const video = videoRef.current;
                if (stopped || !video) {
                    media.getTracks().forEach((track) => track.stop());
                    return;
                }
                video.srcObject = media;
                await video.play();
                setStatus('live');

                const scan = (time) => {
                    if (stopped) return;
                    frame = requestAnimationFrame(scan);
                    if (time - last < SCAN_EVERY_MS || video.readyState < 2 || !video.videoWidth) return;
                    last = time;
                    const width = Math.min(FRAME_WIDTH, video.videoWidth);
                    const height = Math.round((video.videoHeight * width) / video.videoWidth);
                    canvas.width = width;
                    canvas.height = height;
                    context.drawImage(video, 0, 0, width, height);
                    const code = jsQR(context.getImageData(0, 0, width, height).data, width, height, { inversionAttempts: 'dontInvert' });
                    if (!code) return;
                    const slot = slotFromCode(code.data);
                    if (slot) {
                        stopped = true;
                        found.current(slot);
                    } else {
                        setWrong(true);
                    }
                };
                frame = requestAnimationFrame(scan);
            } catch (error) {
                if (!stopped) setStatus(error?.name === 'NotAllowedError' ? 'denied' : 'unavailable');
            }
        };

        start();
        return () => {
            stopped = true;
            cancelAnimationFrame(frame);
            stream?.getTracks().forEach((track) => track.stop());
        };
    }, [open, videoRef]);

    useEffect(() => {
        if (!wrong) return undefined;
        const timer = setTimeout(() => setWrong(false), 2000);
        return () => clearTimeout(timer);
    }, [wrong]);

    return { status, wrong };
}

export default function Scanner({ open, onClose, onFound, slots }) {
    const videoRef = useRef(null);
    const { status, wrong } = useSlotScanner(open, videoRef, onFound);
    const sorted = useMemo(() => [...slots].sort((a, b) => a.localeCompare(b, 'ru', { numeric: true })), [slots]);
    const problem = PROBLEMS[status];

    return (
        <DrawerShell open={open} onClose={onClose} label="Сканировать QR" width={520}>
            <div className="ui-drawer__head">
                <h2 className="ui-drawer__title">Наведите на QR ячейки</h2>
                <CloseButton onClick={onClose} />
            </div>
            <div className="ui-drawer__body scanner">
                {!problem && (
                    <div className="scanner__view">
                        <video ref={videoRef} className="scanner__video" playsInline muted aria-label="Камера" />
                        <div className="scanner__frame" aria-hidden="true" />
                        {status === 'starting' && <span className="scanner__hint">Включаем камеру…</span>}
                    </div>
                )}
                {problem && <Notice tone="warning">{problem}</Notice>}
                {wrong && <Notice tone="warning">Это не QR ячейки Шатла</Notice>}

                {sorted.length > 0 && (
                    <section>
                        <SectionLabel>Или выберите ячейку</SectionLabel>
                        <div className="scanner__slots">
                            {sorted.map((slot) => (
                                <Button key={slot} variant="soft" size="sm" onClick={() => onFound(slot)}>{slot}</Button>
                            ))}
                        </div>
                    </section>
                )}
            </div>
        </DrawerShell>
    );
}

Scanner.propTypes = {
    open: PropTypes.bool.isRequired,
    onClose: PropTypes.func.isRequired,
    onFound: PropTypes.func.isRequired,
    slots: PropTypes.arrayOf(PropTypes.string).isRequired,
};
