import js from '@eslint/js';
import { defineConfig } from 'eslint/config';
import tseslint from 'typescript-eslint';

export default defineConfig({
  name: 'lint-presets/typescript',
  files: ['**/*.{ts,mts,cts}'],
  extends: [js.configs.recommended, tseslint.configs.recommended],
});
