import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import PulseChart from './components/PulseChart';
import PulseWait from './components/PulseWait';
import { endIntro, introChartStart, introEndAt, introLeadAt, useIntro } from '../ui/motion';
import { ErrorState } from '../ui';
import { authApi } from '../../api/authApi';
import { useAuthStatus } from '../../hooks/useAuthStatus';
import { useLoading } from '../../contexts/LoadingContext';
import { useNotifications } from '../../contexts/NotificationsContext';
import { greeting, headlineDetails, quietLead, today, updatedLabel } from './homeText';
import { canSeePulse, pickSections } from './homeSections';
import { pickHeadline, readSummary } from './homeHeadline';
import { pluralWith } from '../../utils/formatters';
import './HomePage.css';

const FOOT_GAP = 150;

export default function HomePage() {
    const auth = useAuthStatus();
    const { syncVersion } = useLoading();
    const { bySource, openPanel, items, complete, loaded } = useNotifications();
    const [home, setHome] = useState(null);
    const [failed, setFailed] = useState(false);
    const [attempt, setAttempt] = useState(0);
    const [now] = useState(() => new Date());
    const intro = useIntro();
    const pulseAt = useRef(null);

    useEffect(() => {
        const controller = new AbortController();
        setFailed(false);
        authApi.home(controller.signal)
            .then((result) => setHome(result.data))
            .catch((error) => { if (error.name !== 'AbortError') setFailed(true); });
        return () => controller.abort();
    }, [syncVersion, attempt]);

    const sections = useMemo(() => pickSections(auth, home?.frequentPaths), [auth, home]);
    const headline = useMemo(() => pickHeadline(items, home?.sectionVisits), [items, home]);
    if (home && pulseAt.current === null) pulseAt.current = introChartStart(performance.now());
    const ready = Boolean(home && loaded);
    const leadAtRef = useRef(null);
    const leadDelayRef = useRef(null);
    if (ready && leadDelayRef.current === null) {
        leadAtRef.current = introLeadAt(canSeePulse(auth) ? pulseAt.current : null);
        leadDelayRef.current = Math.max(0, leadAtRef.current - performance.now());
    }
    const leadDelay = leadDelayRef.current ?? 0;

    useEffect(() => {
        if (!ready || !intro) return undefined;
        const timer = setTimeout(endIntro, Math.max(0, introEndAt(leadAtRef.current) - performance.now()));
        return () => clearTimeout(timer);
    }, [ready, intro]);

    if (failed && !home) {
        return (
            <div className="home">
                <ErrorState title="Не удалось загрузить главную" onRetry={() => setAttempt((n) => n + 1)} />
            </div>
        );
    }
    const name = auth.firstName || auth.username || '';
    const more = headline?.more || 0;
    const quiet = headline ? null : quietLead({ complete, read: readSummary(items) });

    return (
        <div className="home" aria-busy={ready ? undefined : 'true'}>
            {home ? home.pulse && <PulseChart points={home.pulse.points} unit={home.pulse.unit} label={home.pulse.label} startAt={pulseAt.current} intro={intro} />
                : canSeePulse(auth) && <PulseWait />}

            {ready && (
                <>
                    <div className="home__lead intro-late" style={{ '--intro-delay': `${leadDelay}ms` }}>
                        <p className="home__hello">{greeting(now)}{name ? `, ${name}` : ''}. Сегодня {today(now)}</p>
                        <h1 className="home__title">{headline ? headline.title : quiet.title}</h1>
                        <p className="home__sub">{headline ? headlineDetails(headline) : quiet.sub}</p>
                        {(headline || quiet.showRead) && (
                            <div className="home__actions">
                                {headline && (
                                    <Link className="home__cta" to={headline.route}>
                                        Открыть: {headline.source_label}
                                        <ArrowRight size={18} aria-hidden="true" />
                                    </Link>
                                )}
                                {more > 0 && (
                                    <button type="button" className="home__more" onClick={openPanel}>
                                        Ещё {pluralWith(more, 'дело', 'дела', 'дел')}
                                    </button>
                                )}
                                {quiet?.showRead && (
                                    <button type="button" className="home__more" onClick={() => openPanel({ showRead: true })}>
                                        Показать прочитанные
                                    </button>
                                )}
                            </div>
                        )}
                    </div>

                    <div className="home__foot intro-late" style={{ '--intro-delay': `${leadDelay + FOOT_GAP}ms` }}>
                        <nav className="home__sections" aria-label="Мои разделы">
                            {sections.map((item) => {
                                const total = bySource[item.pageKey]?.total || 0;
                                return (
                                    <Link key={item.path} to={item.path} className="home__section">
                                        <b>{item.label}</b>
                                        <span>{total ? pluralWith(total, 'дело', 'дела', 'дел') : item.description}</span>
                                    </Link>
                                );
                            })}
                        </nav>
                        <span className={home.dataUpdatedAt ? 'home__fresh home__fresh--ok' : 'home__fresh'}>
                            {updatedLabel(home.dataUpdatedAt)}
                        </span>
                    </div>
                </>
            )}
        </div>
    );
}
