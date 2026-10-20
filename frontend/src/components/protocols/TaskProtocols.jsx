import { useCallback, useEffect, useState } from 'react';
import PropTypes from 'prop-types';
import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { EmptyState, ErrorState, PageHeader, Skeleton } from '../ui';
import { FadeRise } from '../ui/motion';
import { protocolsApi } from '../../api/protocolsApi';
import { formatDate } from '../../utils/formatters';
import VariantCard from './VariantCard';

export default function TaskProtocols({ taskId }) {
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);
    const [version, setVersion] = useState(0);

    const reload = useCallback(() => setVersion((v) => v + 1), []);

    useEffect(() => {
        const controller = new AbortController();
        setError(null);
        protocolsApi.task(taskId, controller.signal)
            .then(setData)
            .catch((err) => { if (err.name !== 'AbortError') setError(err.message || 'Не удалось загрузить задание'); });
        return () => controller.abort();
    }, [taskId, version]);

    return (
        <>
            <Link to="/protocols" className="protocols__back"><ArrowLeft size={14} /> Все задания</Link>
            <PageHeader
                title={data ? `Задание ${data.task.name}` : 'Задание'}
                subtitle={data ? `от ${formatDate(data.task.moment)} · проверьте серии и скачайте протокол` : undefined}
            />
            {error && <ErrorState hint={error} onRetry={reload} />}
            {!error && !data && <Skeleton height={320} style={{ borderRadius: 12 }} />}
            {data && (
                <FadeRise>
                    {data.variants.length === 0 && <EmptyState title="В задании нет продукции" />}
                    {data.variants.map((variant, index) => (
                        <VariantCard
                            key={`${version}-${variant.plan_ids.join()}`}
                            taskId={data.task.id}
                            taskName={data.task.name}
                            onDate={data.task.moment}
                            index={index}
                            variant={variant}
                            templates={data.templates}
                            onReload={reload}
                        />
                    ))}
                </FadeRise>
            )}
        </>
    );
}

TaskProtocols.propTypes = {
    taskId: PropTypes.string.isRequired,
};
