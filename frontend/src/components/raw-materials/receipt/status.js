export function receiptStatus(receipt) {
    if (receipt.raw === 0) return { tone: 'neutral', label: 'Только тара' };
    if (receipt.waiting > 0) return { tone: 'warning', label: `Ждёт серий · ${receipt.waiting}` };
    return { tone: 'success', label: 'Серии внесены' };
}
