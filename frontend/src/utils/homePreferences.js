export const HOME_PREFERENCES_EVENT = 'horsebio:home-preferences';
export const MAX_PINNED_SECTIONS = 3;

export const publishHomePreferences = (pinnedPaths) => {
    window.dispatchEvent(new CustomEvent(HOME_PREFERENCES_EVENT, {
        detail: { pinnedPaths },
    }));
};
