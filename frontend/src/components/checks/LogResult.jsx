import { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { Loader2 } from 'lucide-react';
import { checksApi } from './checksShared';
import RunLog from './RunLog';
import './RunLog.css';

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

    return <RunLog content={content} title="Вывод последнего запуска" maxHeight="60vh" />;
}

LogResult.propTypes = {
    scriptId: PropTypes.string.isRequired,
    runId: PropTypes.string,
};
