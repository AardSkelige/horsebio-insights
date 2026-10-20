import { useState } from 'react';
import PropTypes from 'prop-types';
import { Download } from 'lucide-react';
import { Button, Card, Notice, Select } from '../ui';
import { num } from '../../utils/formatters';
import { protocolsApi } from '../../api/protocolsApi';
import { downloadBlob } from '../../utils/api';
import ProtocolRow from './ProtocolRow';

export default function VariantCard({ taskId, taskName, onDate, index, variant, templates, onReload }) {
    const [rows, setRows] = useState(variant.rows);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);

    const plans = variant.plan_ids.map((id, i) => ({ id, name: variant.plans[i] }));
    const raw = variant.unplaced.filter((u) => !u.is_tara);
    const withoutSeries = rows.filter((r) => Number(r.qty) > 0 && !r.series).length;

    const run = (action) => {
        setBusy(true);
        setError(null);
        return action().catch((err) => setError(err.message || 'Не получилось')).finally(() => setBusy(false));
    };

    const chooseTemplate = (templateId) => {
        if (!templateId || Number(templateId) === variant.template?.id) return;
        run(() => protocolsApi.linkTemplate(Number(templateId), plans).then(onReload));
    };
    const mapRow = (rowName, materialId) => run(() => protocolsApi.linkMaterial(variant.template.id, rowName, materialId).then(onReload));
    const download = () => run(() => protocolsApi.docx(taskId, index, rows)
        .then((blob) => downloadBlob(blob, `Протокол ${taskName} ${variant.template.title}.docx`)));

    return (
        <Card className="protocols__variant">
            <div className="protocols__variant-head">
                <Select
                    value={variant.template ? String(variant.template.id) : ''}
                    placeholder="Выберите шаблон протокола"
                    options={templates.map((t) => ({ value: String(t.id), label: t.title }))}
                    onChange={(e) => chooseTemplate(e.target.value)}
                    disabled={busy}
                    aria-label="Шаблон протокола"
                />
                <ul className="protocols__products">
                    {variant.products.map((p) => (
                        <li key={p.source_name}>{p.source_name} <b>× {num(p.qty)}</b></li>
                    ))}
                </ul>
            </div>

            {variant.template && (
                <ul className="protocols__rows">
                    {rows.map((row, i) => (
                        <ProtocolRow
                            key={row.row_name}
                            row={row}
                            onDate={onDate}
                            candidates={raw}
                            onChange={(next) => setRows((all) => all.map((r, j) => (j === i ? next : r)))}
                            onMap={mapRow}
                        />
                    ))}
                </ul>
            )}

            {variant.template && raw.length > 0 && (
                <Notice tone="warning">
                    Нет строки в шаблоне: {raw.map((r) => r.name).join(', ')}. В протокол не попадут.
                </Notice>
            )}
            {error && <Notice tone="error">{error}</Notice>}

            {variant.template && (
                <div className="protocols__actions">
                    <Button variant="primary" icon={Download} loading={busy} onClick={download}>
                        Скачать Word
                    </Button>
                    {withoutSeries > 0 && <span className="protocols__hint">Без серии: {withoutSeries}, в протоколе будет прочерк</span>}
                </div>
            )}
        </Card>
    );
}

VariantCard.propTypes = {
    taskId: PropTypes.string.isRequired,
    taskName: PropTypes.string.isRequired,
    onDate: PropTypes.string.isRequired,
    index: PropTypes.number.isRequired,
    variant: PropTypes.shape({
        template: PropTypes.shape({ id: PropTypes.number, title: PropTypes.string }),
        plan_ids: PropTypes.arrayOf(PropTypes.string).isRequired,
        plans: PropTypes.arrayOf(PropTypes.string).isRequired,
        products: PropTypes.arrayOf(PropTypes.object).isRequired,
        rows: PropTypes.arrayOf(PropTypes.object).isRequired,
        unplaced: PropTypes.arrayOf(PropTypes.object).isRequired,
    }).isRequired,
    templates: PropTypes.arrayOf(PropTypes.object).isRequired,
    onReload: PropTypes.func.isRequired,
};
