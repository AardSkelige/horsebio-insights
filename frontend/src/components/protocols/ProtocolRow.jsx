import PropTypes from 'prop-types';
import { Badge, Input, Select } from '../ui';
import { formatDate } from '../../utils/formatters';

const MANUAL = 'manual';

const optionKey = (o) => `${o.series}|${o.expiry_date || ''}`;
const optionLabel = (o) => [o.series, o.expiry_date && `до ${formatDate(o.expiry_date)}`].filter(Boolean).join(' · ');

const isExpired = (iso, onDate) => Boolean(iso) && iso < onDate;

export default function ProtocolRow({ row, onDate, candidates, onChange, onMap }) {
    const known = row.options.find((o) => optionKey(o) === optionKey(row));
    const choice = known ? optionKey(known) : MANUAL;
    const expired = isExpired(row.expiry_date, onDate);
    const used = Number(row.qty) > 0;

    const pick = (value) => {
        if (value === MANUAL) return onChange({ ...row, series: '', expiry_date: null, manufacturer: row.manufacturer });
        const option = row.options.find((o) => optionKey(o) === value);
        return onChange({ ...row, ...option });
    };

    return (
        <li className={`protocols__row${used ? '' : ' protocols__row--idle'}`}>
            <div className="protocols__row-head">
                <span className="protocols__row-name">{row.row_name}</span>
                <label className="protocols__qty">
                    <Input
                        inputMode="decimal"
                        value={row.qty === 0 ? '' : String(row.qty)}
                        placeholder="0"
                        onChange={(e) => onChange({ ...row, qty: e.target.value.replace(',', '.') })}
                        aria-label={`Количество: ${row.row_name}`}
                    />
                    <span>{row.uom || 'г'}</span>
                </label>
            </div>

            {!row.material_id && (
                <Select
                    value=""
                    placeholder="Какое сырьё задания это?"
                    options={candidates.map((c) => ({ value: c.material_id, label: c.name }))}
                    onChange={(e) => onMap(row.row_name, e.target.value)}
                />
            )}

            {row.material_id && used && (
                <div className="protocols__series">
                    <Select
                        value={choice}
                        onChange={(e) => pick(e.target.value)}
                        options={[
                            ...row.options.map((o) => ({ value: optionKey(o), label: optionLabel(o) })),
                            { value: MANUAL, label: 'Вписать вручную' },
                        ]}
                        aria-label={`Серия: ${row.row_name}`}
                    />
                    {choice === MANUAL && (
                        <div className="protocols__manual">
                            <Input placeholder="Серия" value={row.series} onChange={(e) => onChange({ ...row, series: e.target.value })} />
                            <Input type="date" value={row.expiry_date || ''} onChange={(e) => onChange({ ...row, expiry_date: e.target.value || null })} aria-label="Годен до" />
                            <Input placeholder="Производитель" value={row.manufacturer} onChange={(e) => onChange({ ...row, manufacturer: e.target.value })} />
                        </div>
                    )}
                    <div className="protocols__flags">
                        {expired && <Badge tone="error">Просрочена {formatDate(row.expiry_date)}</Badge>}
                        {!row.series && <Badge tone="warning">Нет серии</Badge>}
                    </div>
                </div>
            )}
        </li>
    );
}

ProtocolRow.propTypes = {
    row: PropTypes.shape({
        row_name: PropTypes.string.isRequired,
        material_id: PropTypes.string,
        uom: PropTypes.string,
        qty: PropTypes.oneOfType([PropTypes.number, PropTypes.string]).isRequired,
        series: PropTypes.string,
        expiry_date: PropTypes.string,
        manufacturer: PropTypes.string,
        options: PropTypes.arrayOf(PropTypes.object).isRequired,
    }).isRequired,
    onDate: PropTypes.string.isRequired,
    candidates: PropTypes.arrayOf(PropTypes.object).isRequired,
    onChange: PropTypes.func.isRequired,
    onMap: PropTypes.func.isRequired,
};
