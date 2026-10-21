export const saved = (line) => ({ series: line.series || '', expiry_date: line.expiry_date || '', manufacturer: line.manufacturer || '' });
export const sameAs = (a, b) => a.series.trim() === b.series && a.expiry_date === b.expiry_date && a.manufacturer.trim() === b.manufacturer;
export const complete = (draft) => draft.series.trim() && draft.expiry_date;
