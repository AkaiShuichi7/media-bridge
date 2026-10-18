import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    rules: {
      // 放行伴随组件导出的标准模式：useAuth 类 hook 与 shadcn 的 *Variants 常量
      'react-refresh/only-export-components': [
        'error',
        { allowConstantExport: true, allowExportNames: ['useAuth', 'badgeVariants', 'buttonVariants', 'tabsListVariants'] },
      ],
    },
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
  },
])
