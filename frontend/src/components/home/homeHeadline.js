export const pickHeadline = (items, visits = {}) => {
    const unseen = items.filter((item) => !item.seen);
    if (!unseen.length) return null;
    const candidates = unseen.filter((item) => item.level === unseen[0].level);
    const chosen = candidates.reduce((best, item) => ((visits[item.source] || 0) > (visits[best.source] || 0) ? item : best));
    return { ...chosen, more: unseen.length - 1 };
};

export const readSummary = (items) => {
    const read = items.filter((item) => item.seen);
    return { total: read.length, critical: read.filter((item) => item.level === 'critical').length };
};
