import { useEffect, useMemo, useState } from 'react';
import PropTypes from 'prop-types';
import { Link } from 'react-router-dom';
import { CheckCircle2, Clock3, Pin, RefreshCw, Star } from 'lucide-react';
import { inventoryApi } from '../../../api/inventoryApi';
import { deadlinesApi } from '../../../api/deadlinesApi';
import { checksApi } from '../../checks/checksShared';
import { MAX_PINNED_SECTIONS } from '../../../utils/homePreferences';

const HUMOR = [
    'Сегодня данные ведут себя прилично. Пользуемся моментом.',
    'Цифры на месте. Осталось договориться, что они означают.',
    'План простой: открыть нужное и победить одну маленькую таблицу.',
    'Рабочий день загружен. В отличие от этой шутки.',
    'Всё важное рядом. Даже искать по сайдбару не придётся.',
    'Система готова к работе. Кофе, как обычно, приобретается отдельно.',
];

const hashString = (value) => [...value].reduce((sum, char) => sum + char.charCodeAt(0), 0);

const getGreeting = (date) => {
    const hour = date.getHours();
    if (hour < 6) return 'Доброй ночи';
    if (hour < 12) return 'Доброе утро';
    if (hour < 18) return 'Добрый день';
    return 'Добрый вечер';
};

const getDailyHumor = (username, date) => {
    const dayKey = `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}-${username}`;
    return HUMOR[hashString(dayKey) % HUMOR.length];
};

const formatUpdateTime = (value) => {
    if (!value) return 'Время обновления данных пока неизвестно';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return 'Время обновления данных пока неизвестно';

    const now = new Date();
    const yesterday = new Date(now);
    yesterday.setDate(now.getDate() - 1);
    const time = date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });

    if (date.toDateString() === now.toDateString()) return `Данные МойСклад обновлены сегодня в ${time}`;
    if (date.toDateString() === yesterday.toDateString()) return `Данные МойСклад обновлены вчера в ${time}`;
    return `Данные МойСклад обновлены ${date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })} в ${time}`;
};

const summarizeChecks = (scripts = []) => {
    if (scripts.some((script) => script.is_running)) return 'Проверка выполняется';

    let problems = 0;
    let failedRuns = 0;
    let hasRuns = false;
    scripts.forEach((script) => {
        const summary = script.summary;
        if (summary) {
            hasRuns = true;
            problems += (summary.critical || 0) + (summary.important || 0) + (summary.warnings || 0);
        }
        if (script.last_run?.exit_code != null) {
            hasRuns = true;
            if (script.last_run.exit_code !== 0) failedRuns += 1;
        }
    });

    if (failedRuns) return `${failedRuns} запуск${failedRuns === 1 ? '' : 'а'} с ошибкой`;
    if (problems) return `${problems} сигналов требуют внимания`;
    return hasRuns ? 'Проверки без ошибок' : 'Проверки ещё не запускались';
};

const loadCardDetails = async (paths) => {
    const details = {};
    const requests = [];

    if (paths.includes('/inventory')) {
        requests.push(inventoryApi.getCurrent('', undefined)
            .then((result) => {
                if (result.status !== 'success') {
                    details['/inventory'] = 'За текущий месяц данных пока нет';
                    return;
                }
                const { inventoried = 0, total = 0 } = result.data;
                const percent = total ? Math.round((inventoried / total) * 100) : 0;
                details['/inventory'] = `${inventoried} из ${total} позиций · ${percent}%`;
            })
            .catch(() => {}));
    }

    if (paths.includes('/deadlines')) {
        requests.push(deadlinesApi.get()
            .then((result) => {
                if (!result.available) return;
                const overdue = result.summary?.overdue || 0;
                const warning = result.summary?.warning || 0;
                details['/deadlines'] = overdue || warning
                    ? `${overdue} просрочено · ${warning} скоро`
                    : 'Срочных оплат нет';
            })
            .catch(() => {}));
    }

    if (paths.includes('/checks')) {
        requests.push(checksApi.overview()
            .then((result) => { details['/checks'] = summarizeChecks(result.scripts); })
            .catch(() => {}));
    }

    await Promise.all(requests);
    return details;
};

function WorkspaceCard({ item, pinned, recent, detail, pinDisabled, onTogglePin }) {
    const Icon = item.icon;
    return (
        <article className="personal-workspace__card">
            <Link to={item.path} className="personal-workspace__card-link">
                <span className="personal-workspace__icon"><Icon size={17} /></span>
                <span className="personal-workspace__card-copy">
                    <span className="personal-workspace__card-kicker">
                        {pinned ? 'Закреплено' : recent ? 'Недавно' : 'Для начала'}
                    </span>
                    <strong>{item.label}</strong>
                    <small>{detail || item.description}</small>
                </span>
            </Link>
            <button
                type="button"
                className={pinned ? 'personal-workspace__pin personal-workspace__pin--active' : 'personal-workspace__pin'}
                onClick={() => onTogglePin(item.path)}
                disabled={pinDisabled}
                title={pinned ? 'Открепить от главной' : pinDisabled ? `Можно закрепить до ${MAX_PINNED_SECTIONS} разделов` : 'Закрепить на главной'}
                aria-label={pinned ? `Открепить ${item.label}` : `Закрепить ${item.label}`}
            >
                {pinned ? <Pin size={14} /> : <Star size={14} />}
            </button>
        </article>
    );
}

WorkspaceCard.propTypes = {
    item: PropTypes.object.isRequired,
    pinned: PropTypes.bool.isRequired,
    recent: PropTypes.bool.isRequired,
    detail: PropTypes.string,
    pinDisabled: PropTypes.bool.isRequired,
    onTogglePin: PropTypes.func.isRequired,
};

export default function PersonalWorkspace({ auth, data, items, isSyncing, onTogglePin, saveError, syncVersion }) {
    const [details, setDetails] = useState({});
    const now = useMemo(() => new Date(), []);
    const itemByPath = useMemo(() => new Map(items.map((item) => [item.path, item])), [items]);
    const pinnedPaths = (data?.pinnedPaths || []).filter((path) => itemByPath.has(path));
    const recentPaths = (data?.recentPaths || []).filter((path) => itemByPath.has(path));
    const fallbackPaths = auth.isSuperuser
        ? ['/checks', '/inventory', '/analysis/abc']
        : ['/inventory', '/analysis/abc', '/shipments/products'];
    const displayPaths = [...pinnedPaths];

    [...recentPaths, ...fallbackPaths].forEach((path) => {
        if (displayPaths.length < MAX_PINNED_SECTIONS && itemByPath.has(path) && !displayPaths.includes(path)) {
            displayPaths.push(path);
        }
    });

    const displayItems = displayPaths.map((path) => itemByPath.get(path));
    const displayName = auth.firstName || auth.username || '';

    useEffect(() => {
        let active = true;
        loadCardDetails(displayPaths).then((next) => {
            if (active) setDetails(next);
        });
        return () => { active = false; };
    // displayPaths is derived from primitive paths; joining keeps the request stable.
    }, [displayPaths.join('|'), syncVersion]); // eslint-disable-line react-hooks/exhaustive-deps

    return (
        <section className="personal-workspace" aria-labelledby="personal-workspace-title">
            <header className="personal-workspace__header">
                <div>
                    <h1 id="personal-workspace-title">
                        {getGreeting(now)}{displayName ? `, ${displayName}` : ''}!
                    </h1>
                    <p>{saveError || getDailyHumor(auth.username || displayName, now)}</p>
                </div>
                <div className="personal-workspace__hint">
                    <Pin size={13} /> Закрепите до трёх своих разделов
                </div>
            </header>

            <div className="personal-workspace__cards">
                {displayItems.map((item) => (
                    <WorkspaceCard
                        key={item.path}
                        item={item}
                        pinned={pinnedPaths.includes(item.path)}
                        recent={recentPaths.includes(item.path)}
                        detail={details[item.path]}
                        pinDisabled={!pinnedPaths.includes(item.path) && pinnedPaths.length >= MAX_PINNED_SECTIONS}
                        onTogglePin={onTogglePin}
                    />
                ))}
            </div>

            <footer className="personal-workspace__footer">
                <div className={data?.dataUpdatedAt ? 'personal-workspace__status personal-workspace__status--ok' : 'personal-workspace__status'}>
                    {isSyncing
                        ? <RefreshCw className="animate-spin" size={13} />
                        : data?.dataUpdatedAt
                            ? <CheckCircle2 size={13} />
                            : <Clock3 size={13} />}
                    {isSyncing ? 'Данные МойСклад обновляются' : formatUpdateTime(data?.dataUpdatedAt)}
                </div>
            </footer>
        </section>
    );
}

PersonalWorkspace.propTypes = {
    auth: PropTypes.shape({
        firstName: PropTypes.string,
        isSuperuser: PropTypes.bool,
        username: PropTypes.string,
    }).isRequired,
    data: PropTypes.shape({
        dataUpdatedAt: PropTypes.string,
        pinnedPaths: PropTypes.arrayOf(PropTypes.string),
        recentPaths: PropTypes.arrayOf(PropTypes.string),
    }),
    items: PropTypes.arrayOf(PropTypes.object).isRequired,
    isSyncing: PropTypes.bool.isRequired,
    onTogglePin: PropTypes.func.isRequired,
    saveError: PropTypes.string,
    syncVersion: PropTypes.number.isRequired,
};
