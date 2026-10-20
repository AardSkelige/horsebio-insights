import { useEffect, useRef, useState } from 'react';
import PropTypes from 'prop-types';
import { Badge, Button, CloseButton, Input, SectionLabel } from '../../ui';
import { DrawerShell } from '../../ui/motion';
import { formatDate } from '../../../utils/formatters';
import { expiryState, formatQuantity, round3 } from '../format';

const EXPIRY_TONE = { expired: 'error', soon: 'warning', ok: 'neutral' };

const parse = (text) => round3(Number(String(text).replace(',', '.').replace(/\s/g, '')));

function firstChoice(item, taken) {
    const live = item.batches.filter((b) => round3(b.quantity - taken(b.id)) > 0);
    return (live.find((b) => expiryState(b.expiry_date) !== 'expired') || live[0] || item.batches[0])?.id;
}

function SeriesOption({ batch, uom, left, selected, onSelect }) {
    const state = expiryState(batch.expiry_date);
    return (
        <button
            type="button"
            role="radio"
            aria-checked={selected}
            className={`take-sheet__series${selected ? ' is-selected' : ''}`}
            onClick={onSelect}
            disabled={left <= 0}
        >
            <span className={batch.series ? 'take-sheet__series-name' : 'take-sheet__series-name is-none'}>
                {batch.series || 'Без серии'}
            </span>
            {state && (
                <Badge tone={EXPIRY_TONE[state]}>
                    {state === 'expired' ? 'Просрочена ' : 'до '}{formatDate(batch.expiry_date)}
                </Badge>
            )}
            <span className="take-sheet__series-left">{formatQuantity(left, uom)}</span>
        </button>
    );
}

SeriesOption.propTypes = {
    batch: PropTypes.object.isRequired,
    uom: PropTypes.string,
    left: PropTypes.number.isRequired,
    selected: PropTypes.bool.isRequired,
    onSelect: PropTypes.func.isRequired,
};

export default function TakeSheet({ item, onClose, onAdd, taken }) {
    const shown = useRef(item);
    if (item) shown.current = item;
    const current = shown.current;

    const [batchId, setBatchId] = useState(null);
    const [quantity, setQuantity] = useState('');

    useEffect(() => {
        if (!item) return;
        setBatchId(firstChoice(item, taken));
        setQuantity('');
    }, [item]); // eslint-disable-line react-hooks/exhaustive-deps

    const batch = current?.batches.find((b) => b.id === batchId);
    const left = batch ? round3(batch.quantity - taken(batch.id)) : 0;
    const value = parse(quantity);
    const tooMuch = value > left;
    const valid = batch && value > 0 && !tooMuch;

    const submit = (event) => {
        event.preventDefault();
        if (!valid) return;
        onAdd({
            batch: batch.id,
            name: current.name,
            series: batch.series,
            expiry_date: batch.expiry_date,
            uom: current.uom,
            slot: current.slot,
            quantity: value,
        });
        onClose();
    };

    return (
        <DrawerShell open={Boolean(item)} onClose={onClose} label="Взять со склада" width={440}>
            <div className="ui-drawer__head">
                <h2 className="ui-drawer__title">{current?.name}</h2>
                <CloseButton onClick={onClose} />
            </div>
            {current && (
                <form className="ui-drawer__body take-sheet" onSubmit={submit}>
                    {current.batches.length > 1 && (
                        <section>
                            <SectionLabel>Серия</SectionLabel>
                            <div className="take-sheet__options" role="radiogroup" aria-label="Серия">
                                {current.batches.map((b) => (
                                    <SeriesOption
                                        key={b.id}
                                        batch={b}
                                        uom={current.uom}
                                        left={round3(b.quantity - taken(b.id))}
                                        selected={b.id === batchId}
                                        onSelect={() => setBatchId(b.id)}
                                    />
                                ))}
                            </div>
                        </section>
                    )}

                    <section>
                        <SectionLabel>Сколько взять</SectionLabel>
                        <div className="take-sheet__amount">
                            <Input
                                block
                                inputMode="decimal"
                                autoComplete="off"
                                aria-label={`Количество, ${current.uom || ''}`}
                                placeholder="0"
                                value={quantity}
                                onChange={(e) => setQuantity(e.target.value)}
                                aria-invalid={tooMuch || undefined}
                            />
                            <span className="take-sheet__unit">{current.uom}</span>
                            <Button variant="soft" onClick={() => setQuantity(String(left))} disabled={left <= 0}>Всё</Button>
                        </div>
                        <p className={`take-sheet__hint${tooMuch ? ' is-error' : ''}`}>
                            {tooMuch ? `На полке только ${formatQuantity(left, current.uom)}` : `На полке ${formatQuantity(left, current.uom)}`}
                            {!tooMuch && value > 0 && ` · берёте ${formatQuantity(value, current.uom)}`}
                        </p>
                    </section>

                    <Button type="submit" variant="primary" block disabled={!valid}>В корзину</Button>
                </form>
            )}
        </DrawerShell>
    );
}

TakeSheet.propTypes = {
    item: PropTypes.object,
    onClose: PropTypes.func.isRequired,
    onAdd: PropTypes.func.isRequired,
    taken: PropTypes.func.isRequired,
};
