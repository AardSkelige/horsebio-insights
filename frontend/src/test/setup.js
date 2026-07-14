import '@testing-library/jest-dom/vitest';

// jsdom не реализует matchMedia — нужен компонентам antd
if (!window.matchMedia) {
    window.matchMedia = () => ({
        matches: false,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
    });
}
