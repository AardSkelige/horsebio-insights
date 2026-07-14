/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'primary': {
          DEFAULT: '#cc785c',
          'active': '#a9583e',
          'disabled': '#e6dfd8',
        }
      }
    },
  },
  plugins: [],
}
