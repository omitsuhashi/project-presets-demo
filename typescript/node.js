import { defineConfig } from 'eslint/config';
import globals from 'globals';
import base from './base.js';

export default defineConfig(base, {
  name: 'lint-presets/typescript-node',
  files: ['**/*.{ts,mts,cts}'],
  languageOptions: { globals: globals.node },
});
