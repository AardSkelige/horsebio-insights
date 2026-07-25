import { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { Loader2 } from 'lucide-react';
import { checksApi } from './checksShared';

/**
 * Вывод последнего запуска для «лог»-заданий (без структурированных находок) —
 * синхронизация данных, инвентаризация и т.п. Показывает stdout прогона, а не
 * пустой экран находок.
 */
export default function LogResult({ scriptId, runId = null }) {
    const [content, setContent] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let mounted = true;
        setLoading(true);
        checksApi.log(scriptId, runId)
            .then((res) => { if (mounted) setContent(res.content || ''); })
            .catch(() => { if (mounted) setContent(''); })
            .finally(() => { if (mounted) setLoading(false); });
        return () => { mounted = false; };
    }, [scriptId, runId]);

    if (loading) {
        return (
            <div style={{ display: 'flex', gap: 8, color: 'var(--muted)', padding: 30, justifyContent: 'center' }}>
                <Loader2 size={18} className="animate-spin" /> Загрузка…
            </div>
        );
    }

    if (!content) {
        return (
            <div style={{ color: 'var(--muted)', padding: 30, textAlign: 'center', fontSize: 13.5 }}>
                Ещё не запускалось — нажмите «Запустить», чтобы увидеть вывод.
            </div>
        );
    }

    return (
        <div style={{
            background: 'var(--surface-soft)', border: '1px solid var(--hairline)', borderRadius: 10,
            padding: '12px 14px', fontFamily: 'var(--mono)', fontSize: 12, lineHeight: 1.55, color: 'var(--muted)',
            whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: '60vh', overflowY: 'auto',
        }}>{content}</div>
    );
}

LogResult.propTypes = {
    scriptId: PropTypes.string.isRequired,
    runId: PropTypes.string,
};
