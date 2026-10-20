import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Badge, EmptyState, ErrorState, Page, PageHeader, SearchInput, Skeleton, Toolbar } from '../ui';
import { FadeRise } from '../ui/motion';
import { protocolsApi } from '../../api/protocolsApi';
import { formatDate } from '../../utils/formatters';
import TaskProtocols from './TaskProtocols';
import './ProtocolsPage.css';

function TaskList() {
    const [search, setSearch] = useState('');
    const [tasks, setTasks] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
        const controller = new AbortController();
        const timer = setTimeout(() => {
            setError(null);
            protocolsApi.tasks(search.trim(), controller.signal)
                .then((res) => setTasks(res.tasks))
                .catch((err) => { if (err.name !== 'AbortError') setError(err.message || 'Не удалось загрузить задания'); });
        }, search ? 300 : 0);
        return () => { clearTimeout(timer); controller.abort(); };
    }, [search]);

    return (
        <>
            <PageHeader title="Протоколы" subtitle="Производственные задания из МойСклад: выберите задание, проверьте серии и скачайте протокол" />
            <Toolbar>
                <SearchInput value={search} onChange={setSearch} placeholder="Номер задания или комментарий" />
            </Toolbar>
            {error && <ErrorState hint={error} />}
            {!error && !tasks && <Skeleton height={240} style={{ borderRadius: 12 }} />}
            {tasks && (
                <FadeRise>
                    <ul className="protocols__tasks">
                        {tasks.map((task) => (
                            <li key={task.id}>
                                <Link to={`/protocols/${task.id}`} className="protocols__task">
                                    <span className="protocols__task-name">{task.name}</span>
                                    <span className="protocols__task-date">{formatDate(task.moment)}</span>
                                    {task.state && <Badge>{task.state}</Badge>}
                                    <span className="protocols__task-note">{task.description}</span>
                                </Link>
                            </li>
                        ))}
                    </ul>
                    {tasks.length === 0 && <EmptyState title="Заданий не найдено" />}
                </FadeRise>
            )}
        </>
    );
}

export default function ProtocolsPage() {
    const { taskId } = useParams();
    return <Page>{taskId ? <TaskProtocols taskId={taskId} /> : <TaskList />}</Page>;
}
