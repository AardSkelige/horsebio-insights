import NAV_GROUPS from '../layout/sidebar/navGroups';

const SECTIONS = 3;

const navItemsFor = (auth) => NAV_GROUPS
    .filter((group) => group.label)
    .flatMap((group) => group.items)
    .filter((item) => {
        if (item.superuserOnly) return auth.isSuperuser === true;
        if (auth.isSuperuser === true || !item.pageKey || !Array.isArray(auth.allowedPages)) return true;
        return auth.allowedPages.includes(item.pageKey);
    });

export const pickSections = (auth, frequentPaths = []) => {
    const items = navItemsFor(auth);
    const byPath = new Map(items.map((item) => [item.path, item]));
    const chosen = frequentPaths.map((path) => byPath.get(path)).filter(Boolean);
    items.forEach((item) => {
        if (chosen.length < SECTIONS && !chosen.includes(item)) chosen.push(item);
    });
    return chosen.slice(0, SECTIONS);
};
