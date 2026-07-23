import { useState, useEffect } from 'react';
import FeatureCard from './components/FeatureCard';
import PersonalWorkspace from './components/PersonalWorkspace';
import { FadeRise } from '../ui/motion';
import NAV_GROUPS from '../layout/sidebar/navGroups';
import { authApi } from '../../api/authApi';
import { useLoading } from '../../contexts/LoadingContext';
import {
    HOME_PREFERENCES_EVENT,
    MAX_PINNED_SECTIONS,
    publishHomePreferences,
} from '../../utils/homePreferences';
import './HomePage.css';

const HomePage = () => {
    const [auth, setAuth] = useState({ isSuperuser: false, username: '', firstName: '', allowedPages: null });
    const [homeData, setHomeData] = useState(null);
    const [saveError, setSaveError] = useState('');
    const { isLoading, syncVersion } = useLoading();

    useEffect(() => {
        const controller = new AbortController();

        Promise.all([
            authApi.check(controller.signal),
            authApi.home(controller.signal),
        ]).then(([authResult, homeResult]) => {
            setAuth({
                isSuperuser: Boolean(authResult.isSuperuser),
                username: authResult.username || '',
                firstName: authResult.firstName || '',
                allowedPages: Array.isArray(authResult.allowedPages) ? authResult.allowedPages : null,
            });
            setHomeData(homeResult.data);
        }).catch((error) => {
            if (error.name !== 'AbortError') setSaveError('Не удалось загрузить персональные настройки');
        });

        return () => controller.abort();
    }, [syncVersion]);

    useEffect(() => {
        const handlePreferences = (event) => {
            if (!Array.isArray(event.detail?.pinnedPaths)) return;
            setHomeData((current) => current ? {
                ...current,
                pinnedPaths: event.detail.pinnedPaths,
            } : current);
        };
        window.addEventListener(HOME_PREFERENCES_EVENT, handlePreferences);
        return () => window.removeEventListener(HOME_PREFERENCES_EVENT, handlePreferences);
    }, []);

    const sections = NAV_GROUPS
        .filter((group) => group.label)
        .map((group) => ({
            title: group.label,
            items: group.items
                .filter((item) => {
                    if (item.superuserOnly) return auth.isSuperuser;
                    if (auth.isSuperuser) return true;
                    // фильтр по постраничным правам; пока не загружены — показываем
                    if (item.pageKey && Array.isArray(auth.allowedPages)) return auth.allowedPages.includes(item.pageKey);
                    return true;
                })
                .map((item) => ({
                    icon: item.icon,
                    title: item.label,
                    description: item.description,
                    link: item.path,
                })),
        }))
        .filter((section) => section.items.length);
    const workspaceItems = sections.flatMap((section) => section.items.map((item) => ({
        ...item,
        label: item.title,
        path: item.link,
        section: section.title,
    })));
    // Секция «Аналитика» может отсутствовать, если у пользователя нет её страниц.
    // Тогда analyticsIndex === -1 — не срезаем по нему (иначе теряем секции и
    // падаем на analyticsSection.items).
    const analyticsIndex = sections.findIndex((section) => section.title === 'Аналитика');
    const hasAnalytics = analyticsIndex !== -1;
    const workSections = hasAnalytics ? sections.slice(0, analyticsIndex) : sections;
    const analyticsSection = hasAnalytics ? sections[analyticsIndex] : null;
    const systemSections = hasAnalytics ? sections.slice(analyticsIndex + 1) : [];

    const handleTogglePin = async (path) => {
        const previous = homeData?.pinnedPaths || [];
        const isPinned = previous.includes(path);
        if (!isPinned && previous.length >= MAX_PINNED_SECTIONS) {
            setSaveError(`Можно закрепить не больше ${MAX_PINNED_SECTIONS} разделов`);
            return;
        }

        const next = isPinned
            ? previous.filter((item) => item !== path)
            : [...previous, path];
        setSaveError('');
        setHomeData((current) => ({ ...current, pinnedPaths: next }));
        publishHomePreferences(next);

        try {
            const result = await authApi.updateHome(next);
            setHomeData(result.data);
            publishHomePreferences(result.data.pinnedPaths);
        } catch {
            setHomeData((current) => ({ ...current, pinnedPaths: previous }));
            publishHomePreferences(previous);
            setSaveError('Не удалось сохранить закреплённые разделы');
        }
    };

    return (
        <div className="home-dashboard">

            {homeData && (
                <PersonalWorkspace
                    auth={auth}
                    data={homeData}
                    items={workspaceItems}
                    isSyncing={isLoading}
                    onTogglePin={handleTogglePin}
                    saveError={saveError}
                    syncVersion={syncVersion}
                />
            )}

            <div className="home-dashboard__work-grid">
                {workSections.map((section, index) => {
                    const isWide = section.items.length > 2;
                    const sectionId = `home-work-section-${index}`;

                    return (
                        <FadeRise
                            className={isWide ? 'home-dashboard__group home-dashboard__group--wide' : 'home-dashboard__group'}
                            delay={index * 0.025}
                            key={section.title}
                        >
                            <section aria-labelledby={sectionId}>
                                <div className="home-dashboard__heading">
                                    <h2 id={sectionId}>{section.title}</h2>
                                    <span />
                                </div>
                                <div className={isWide ? 'home-dashboard__links home-dashboard__links--two-columns' : 'home-dashboard__links'}>
                                    {section.items.map((item) => (
                                        <FeatureCard key={item.link} {...item} compact />
                                    ))}
                                </div>
                            </section>
                        </FadeRise>
                    );
                })}
            </div>

            {analyticsSection && (
                <FadeRise className="home-dashboard__group" delay={0.1}>
                    <section aria-labelledby="home-analytics-title">
                        <div className="home-dashboard__heading">
                            <h2 id="home-analytics-title">Аналитика</h2>
                            <span />
                        </div>
                        <div className="home-dashboard__links home-dashboard__links--analytics">
                            {analyticsSection.items.map((item) => (
                                <FeatureCard key={item.link} {...item} compact />
                            ))}
                        </div>
                    </section>
                </FadeRise>
            )}

            {systemSections.length > 0 && (
                <div className="home-dashboard__system-grid">
                    {systemSections.map((section, index) => (
                        <FadeRise className="home-dashboard__group" delay={0.125 + index * 0.025} key={section.title}>
                            <section aria-labelledby={`home-system-section-${index}`}>
                                <div className="home-dashboard__heading">
                                    <h2 id={`home-system-section-${index}`}>{section.title}</h2>
                                    <span />
                                </div>
                                <div className="home-dashboard__links">
                                    {section.items.map((item) => (
                                        <FeatureCard key={item.link} {...item} compact />
                                    ))}
                                </div>
                            </section>
                        </FadeRise>
                    ))}
                </div>
            )}
        </div>
    );
};

export default HomePage;
