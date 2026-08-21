/**
 * Числовые шкалы дизайн-системы.
 *
 * Цвета живут в CSS-переменных (`src/index.css`) — они должны переключаться вместе
 * с темой, а JS о смене темы не знает. Здесь только размеры: они нужны там, где
 * inline-стиль остаётся уместным — динамическая вёрстка, размеры иконок, настройки
 * графиков Recharts, которые принимают числа, а не классы.
 *
 * Те же значения продублированы как CSS-переменные в `:root` для `ui.css`.
 * Правило простое: если значение можно выразить классом — оно живёт в CSS,
 * если его требует JS-библиотека — берётся отсюда.
 */

/** Размеры текста. Названия по роли, а не по числу: 13px — это «обычный текст». */
export const size = {
    xs: 11,      // подписи колонок, капслок-метки
    sm: 12,      // вторичный текст, пагинация, мелкие бейджи
    md: 13,      // основной текст интерфейса, ячейки таблиц, контролы
    lg: 16,      // заголовок карточки
    xl: 22,      // заголовок раздела внутри страницы
    display: 32, // заголовок страницы
};

/** Радиусы скругления. */
export const radius = {
    sm: 6,    // мелкие кнопки, ячейки пагинации
    md: 8,    // контролы, кнопки, инпуты
    lg: 12,   // карточки, панели
    pill: 999,
};

/** Отступы. Шаг 4px — сетка, к которой сводится вся вёрстка. */
export const space = {
    1: 4,
    2: 8,
    3: 12,
    4: 16,
    5: 24,
    6: 32,
};

/** Геометрия контролов — кнопок, инпутов, селектов. */
export const control = {
    padY: 7,
    padX: 12,
    height: 34,
};

/** Размеры иконок lucide-react под каждый размер текста. */
export const icon = {
    xs: 11,
    sm: 13,
    md: 14,
    lg: 16,
};

/**
 * Палитра графиков для Recharts: библиотека принимает строку цвета, а не класс,
 * поэтому переменные отдаются в виде `var(--chart-N)`. Первый цвет — акцент темы.
 */
export const chartColors = [
    'var(--chart-1)',
    'var(--chart-2)',
    'var(--chart-3)',
    'var(--chart-4)',
    'var(--chart-5)',
    'var(--chart-6)',
    'var(--chart-7)',
    'var(--chart-8)',
];

/**
 * Категориальная палитра по именам — для случаев, когда категория постоянна
 * и цвет должен быть закреплён за ней (зима всегда бирюзовая), а не выдаваться
 * по порядку из массива.
 */
export const categoryColor = {
    coral: 'var(--cat-coral)',
    blue: 'var(--cat-blue)',
    green: 'var(--cat-green)',
    amber: 'var(--cat-amber)',
    violet: 'var(--cat-violet)',
    teal: 'var(--cat-teal)',
    pink: 'var(--cat-pink)',
    orange: 'var(--cat-orange)',
    clay: 'var(--cat-clay)',
};

/** Их текстовые варианты. */
export const categoryInk = {
    coral: 'var(--cat-coral-ink)',
    blue: 'var(--cat-blue-ink)',
    green: 'var(--cat-green-ink)',
    amber: 'var(--cat-amber-ink)',
    violet: 'var(--cat-violet-ink)',
    teal: 'var(--cat-teal-ink)',
    pink: 'var(--cat-pink-ink)',
    orange: 'var(--cat-orange-ink)',
    clay: 'var(--cat-clay-ink)',
};

/** Семантические цвета для тех же случаев — когда цвет нужен строкой в JS. */
export const statusColor = {
    success: 'var(--success)',
    warning: 'var(--warning)',
    error: 'var(--error)',
    info: 'var(--info)',
};

/** Текстовый вариант статуса: на кремовом фоне базовый цвет слишком светлый. */
export const statusInk = {
    success: 'var(--success-ink)',
    warning: 'var(--warning-ink)',
    error: 'var(--error-ink)',
    info: 'var(--info-ink)',
};

/** Точка перехода на мобильную раскладку. Совпадает с `useIsMobile`. */
export const MOBILE_BREAKPOINT = 768;
