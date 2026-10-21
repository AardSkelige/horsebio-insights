import { useEffect, useState } from 'react';
import PropTypes from 'prop-types';
import { X } from 'lucide-react';
import { Button, CloseButton, IconButton, Input } from '../ui';
import { DrawerShell } from '../ui/motion';
import { productionPlanApi } from '../../api/productionPlanApi';

export default function ExclusionsDrawer({ open, onClose, onChanged }) {
    const [items, setItems] = useState([]);
    const [text, setText] = useState('');
    const [error, setError] = useState(null);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        if (!open) return undefined;
        const controller = new AbortController();
        productionPlanApi.exclusions(controller.signal)
            .then((res) => setItems(res.items))
            .catch((err) => { if (err.name !== 'AbortError') setError(err.message); });
        return () => controller.abort();
    }, [open]);

    const apply = (request) => {
        setSaving(true);
        setError(null);
        return request
            .then((res) => { setItems(res.items); onChanged(); return true; })
            .catch((err) => { setError(err.message); return false; })
            .finally(() => setSaving(false));
    };

    const add = (event) => {
        event.preventDefault();
        apply(productionPlanApi.addExclusion(text)).then((saved) => { if (saved) setText(''); });
    };

    return (
        <DrawerShell open={open} onClose={onClose} label="Исключения">
            <div className="ui-drawer__head">
                <h2 className="ui-drawer__title">Исключения</h2>
                <CloseButton onClick={onClose} />
            </div>
            <div className="ui-drawer__body plan-exclusions">
                <p className="plan-exclusions__hint">Артикул убирает из плана один товар. Слово убирает все товары, в названии которых оно есть.</p>
                <form className="plan-exclusions__form" onSubmit={add}>
                    <Input block value={text} onChange={(e) => setText(e.target.value)} placeholder="Артикул или слово, например «мармелад»" />
                    <Button type="submit" variant="primary" loading={saving} disabled={!text.trim()}>Добавить</Button>
                </form>
                {error && <p className="plan-exclusions__error">{error}</p>}
                <ul className="plan-exclusions__list">
                    {items.map((item) => (
                        <li key={item.id}>
                            <span>{item.text}{item.note && <small>{item.note}</small>}</span>
                            <IconButton icon={X} label="Убрать" disabled={saving} onClick={() => apply(productionPlanApi.removeExclusion(item.id))} />
                        </li>
                    ))}
                </ul>
            </div>
        </DrawerShell>
    );
}

ExclusionsDrawer.propTypes = {
    open: PropTypes.bool.isRequired,
    onClose: PropTypes.func.isRequired,
    onChanged: PropTypes.func.isRequired,
};
