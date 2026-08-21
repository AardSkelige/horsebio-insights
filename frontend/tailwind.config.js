/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      // Единственный источник цвета — CSS-переменные в index.css.
      // Здесь только проброс, чтобы утилиты Tailwind следовали теме,
      // а не хранили вторую копию палитры.
      colors: {
        'primary': {
          DEFAULT: 'var(--primary)',
          'active': 'var(--primary-active)',
        }
      }
    },
  },
  plugins: [],
}
