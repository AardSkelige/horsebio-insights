import { useState } from 'react';
import PropTypes from 'prop-types';
import { AnimatePresence, m } from 'motion/react';
import { ExternalLink, PackageCheck, ShoppingBasket } from 'lucide-react';
import { Button, CloseButton, Notice } from '../../ui';
import { DrawerShell } from '../../ui/motion';
import { rawMaterialsApi } from '../../../api/rawMaterialsApi';
import { pluralWith } from '../../../utils/formatters';
import IssueLine from './IssueLine';

export default function IssueCart({ cart, onIssued }) {
    const [open, setOpen] = useState(false);
    const [sending, setSending] = useState(false);
    const [error, setError] = useState(null);
    const [done, setDone] = useState(null);

    const count = cart.lines.length;

    const close = () => {
        setOpen(false);
        setError(null);
        setDone(null);
    };

    const send = () => {
        setSending(true);
        setError(null);
        rawMaterialsApi.issue({ key: cart.key, lines: cart.lines.map((l) => ({ batch: l.batch, quantity: l.quantity, slot: l.slot })) })
            .then((issue) => {
                setDone(issue);
                cart.settle(issue.lines);
                onIssued();
            })
            .catch((err) => setError(err.message || 'Не удалось выдать'))
            .finally(() => setSending(false));
    };

    return (
        <>
            <AnimatePresence>
                {count > 0 && !open && (
                    <m.div
                        className="issue-cart__bar"
                        initial={{ y: 80, opacity: 0 }}
                        animate={{ y: 0, opacity: 1 }}
                        exit={{ y: 80, opacity: 0 }}
                        transition={{ duration: 0.3, ease: 'easeOut' }}
                    >
                        <ShoppingBasket size={18} aria-hidden="true" />
                        <span className="issue-cart__bar-text">В корзине {pluralWith(count, 'позиция', 'позиции', 'позиций')}</span>
                        <Button variant="primary" onClick={() => setOpen(true)}>Выдать</Button>
                    </m.div>
                )}
            </AnimatePresence>

            <DrawerShell open={open} onClose={close} label="Выдача на производство" width={460}>
                <div className="ui-drawer__head">
                    <h2 className="ui-drawer__title">Выдача на производство</h2>
                    <CloseButton onClick={close} />
                </div>
                <div className="ui-drawer__body issue-cart">
                    {done ? (
                        <div className="issue-cart__done">
                            <PackageCheck size={40} className="issue-cart__done-icon" aria-hidden="true" />
                            <p className="issue-cart__done-title">Перемещение {done.moysklad_name} проведено</p>
                            <p className="issue-cart__done-text">{done.description}</p>
                            <ul className="issue-lines">
                                {done.lines.map((line) => <IssueLine key={line.id} line={line} />)}
                            </ul>
                            {count > 0 && (
                                <Notice tone="warning">
                                    В корзине осталось {pluralWith(count, 'позиция', 'позиции', 'позиций')}: их нет в этом перемещении, выдайте отдельно
                                </Notice>
                            )}
                            <div className="issue-cart__actions">
                                <Button as="a" variant="ghost" icon={ExternalLink} href={done.moysklad_url} target="_blank" rel="noreferrer">
                                    Открыть в МойСклад
                                </Button>
                                <Button variant="primary" onClick={close}>Готово</Button>
                            </div>
                        </div>
                    ) : (
                        <>
                            <p className="issue-cart__lead">
                                Создаст в МойСклад проведённое перемещение с Шатла на склад производства.
                            </p>
                            <ul className="issue-lines">
                                {cart.lines.map((line) => (
                                    <IssueLine key={line.batch} line={line} onRemove={() => cart.remove(line.batch)} />
                                ))}
                            </ul>
                            {count === 0 && <p className="issue-cart__lead">Корзина пуста</p>}
                            {error && <Notice tone="error">{error}</Notice>}
                            <Button variant="primary" block loading={sending} loadingLabel="Выдаём…" disabled={count === 0} onClick={send}>
                                Выдать {count > 0 && pluralWith(count, 'позицию', 'позиции', 'позиций')}
                            </Button>
                        </>
                    )}
                </div>
            </DrawerShell>
        </>
    );
}

IssueCart.propTypes = {
    cart: PropTypes.shape({
        key: PropTypes.string.isRequired,
        lines: PropTypes.arrayOf(PropTypes.object).isRequired,
        remove: PropTypes.func.isRequired,
        settle: PropTypes.func.isRequired,
    }).isRequired,
    onIssued: PropTypes.func.isRequired,
};
