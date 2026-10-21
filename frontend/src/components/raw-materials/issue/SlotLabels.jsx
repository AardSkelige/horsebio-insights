import { useEffect, useMemo, useState } from 'react';
import PropTypes from 'prop-types';
import { createPortal } from 'react-dom';
import QRCode from 'qrcode';
import { Printer } from 'lucide-react';
import { Button, EmptyState, ErrorState, Page, PageHeader, Skeleton } from '../../ui';
import { FadeRise } from '../../ui/motion';
import useStock from '../useStock';
import StockTabs from '../StockTabs';
import BackLink from './BackLink';
import './issue.css';

const slotUrl = (slot) => `${window.location.origin}/raw-materials/slot/${encodeURIComponent(slot)}`;

function useQrImages(slots) {
    const [images, setImages] = useState({});

    useEffect(() => {
        let alive = true;
        Promise.all(slots.map((slot) => QRCode.toDataURL(slotUrl(slot), { margin: 0, width: 360, errorCorrectionLevel: 'M' })))
            .then((urls) => { if (alive) setImages(Object.fromEntries(slots.map((slot, i) => [slot, urls[i]]))); });
        return () => { alive = false; };
    }, [slots]);

    return images;
}

function Labels({ slots, images, className }) {
    return (
        <div className={className}>
            {slots.map((slot) => (
                <figure key={slot} className="slot-label">
                    {images[slot]
                        ? <img className="slot-label__qr" src={images[slot]} alt={`QR ячейки ${slot}`} />
                        : <div className="slot-label__qr" />}
                    <figcaption>
                        <span className="slot-label__name">{slot}</span>
                        <span className="slot-label__store">Шатл · склад сырья</span>
                    </figcaption>
                </figure>
            ))}
        </div>
    );
}

Labels.propTypes = {
    slots: PropTypes.arrayOf(PropTypes.string).isRequired,
    images: PropTypes.object.isRequired,
    className: PropTypes.string.isRequired,
};

export default function SlotLabels() {
    const { data, loading, error, refresh } = useStock();
    const slots = useMemo(
        () => [...(data?.slots || [])].sort((a, b) => a.localeCompare(b, 'ru', { numeric: true })),
        [data],
    );
    const images = useQrImages(slots);

    return (
        <Page>
            <BackLink mobileOnly />
            <PageHeader
                title="QR ячеек"
                subtitle="Наклейки на полки Шатла: QR открывает ячейку для выдачи"
                actions={<Button variant="primary" icon={Printer} onClick={() => window.print()} disabled={!slots.length}>Печать</Button>}
            />
            <StockTabs />

            {error && <ErrorState hint={error} onRetry={refresh} />}
            {!error && loading && <Skeleton height={240} style={{ borderRadius: 12 }} />}
            {!error && !loading && slots.length === 0 && <EmptyState title="Ячеек нет" hint="Нажмите «Обновить» на странице склада" />}
            {slots.length > 0 && (
                <FadeRise>
                    <Labels slots={slots} images={images} className="slot-labels" />
                </FadeRise>
            )}
            {slots.length > 0 && createPortal(
                <Labels slots={slots} images={images} className="slot-labels slot-labels--print" />,
                document.body,
            )}
        </Page>
    );
}
