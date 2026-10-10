import { defineConfig } from 'eslint/config'
import eslintPluginVue from 'eslint-plugin-vue'
import tseslint from 'typescript-eslint'

// 规则依据见 docs/guides/工程规范.md 第 5 节。
export default defineConfig(
  { ignores: ['dist/**', 'node_modules/**', 'e2e/**', 'playwright-report/**', 'test-results/**'] },
  // 需要类型信息的规则：能查出未处理的 Promise、对 any 的不安全使用等。
  ...tseslint.configs.recommendedTypeChecked,
  ...eslintPluginVue.configs['flat/recommended'],
  {
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
        extraFileExtensions: ['.vue'],
      },
    },
  },
  {
    files: ['**/*.vue'],
    languageOptions: {
      parserOptions: {
        parser: tseslint.parser,
      },
    },
    // typescript-eslint 没有 Vue 语言服务，解析不了 SFC 组件的类型（如 InstanceType<typeof 某组件> 上的
    // validate），会当成解析失败的 any 报错。SFC 的类型由 vue-tsc（strict）检查，这组规则只对 .ts 生效。
    rules: {
      '@typescript-eslint/no-unsafe-argument': 'off',
      '@typescript-eslint/no-unsafe-assignment': 'off',
      '@typescript-eslint/no-unsafe-call': 'off',
      '@typescript-eslint/no-unsafe-member-access': 'off',
      '@typescript-eslint/no-unsafe-return': 'off',
    },
  },
  {
    rules: {
      'vue/multi-word-component-names': 'off',
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-floating-promises': 'error',
      // 与 Python 侧门槛一致（工程规范决策 D）。
      complexity: ['error', 10],
      'max-params': ['error', 6],
      'max-depth': ['error', 3],
    },
  },
  {
    // 测试按场景平铺用例，长度不代表职责过多。
    ignores: ['**/*.test.ts'],
    rules: {
      'max-lines': ['error', { max: 400 }],
    },
  },
  {
    // 配置文件本身不在任何 tsconfig 里，不做类型感知检查。
    files: ['*.config.js', '*.config.ts'],
    extends: [tseslint.configs.disableTypeChecked],
  },
)
