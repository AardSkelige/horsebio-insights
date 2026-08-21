import js from '@eslint/js'
import globals from 'globals'
import react from 'eslint-plugin-react'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'

export default [
  { ignores: ['dist'] },
  {
    files: ['**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
      parserOptions: {
        ecmaVersion: 'latest',
        ecmaFeatures: { jsx: true },
        sourceType: 'module',
      },
    },
    settings: { react: { version: '18.3' } },
    plugins: {
      react,
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...js.configs.recommended.rules,
      ...react.configs.recommended.rules,
      ...react.configs['jsx-runtime'].rules,
      ...reactHooks.configs.recommended.rules,
      'react/jsx-no-target-blank': 'off',
      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true },
      ],
      // Цвет в компоненте — это цвет мимо темы: он не переключится в тёмном
      // режиме и не поменяется при смене акцента. Палитра живёт в токенах
      // `src/index.css`, компонент обращается к ней через `var(--…)`.
      // Уровень error, а не warn: на момент введения правила хардкода в коде
      // не осталось, поэтому любое новое срабатывание — это регресс, а не долг
      'no-restricted-syntax': [
        'error',
        {
          selector: "Literal[value=/^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/]",
          message: 'Цвет задан хексом мимо темы. Используйте токен: var(--ink), var(--error-ink), var(--chart-1) и т. д.',
        },
        {
          selector: "Literal[value=/rgba?\\(/]",
          message: 'Полупрозрачный цвет задан вручную. Для плашек статуса есть var(--success-bg), var(--error-border) и т. д.',
        },
      ],
    },
  },
  {
    // Токены — единственное место, где хексы уместны по определению.
    files: ['src/theme/**', 'src/**/*.test.{js,jsx}'],
    rules: { 'no-restricted-syntax': 'off' },
  },
]
