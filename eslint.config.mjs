import js from '@eslint/js';
import { defineConfig } from 'eslint/config';
import globals from 'globals';
import node from './typescript/node.js';

export default defineConfig(node, {
  files: ['**/*.{js,mjs}'],
  extends: [js.configs.recommended],
  languageOptions: { globals: globals.node },
});
