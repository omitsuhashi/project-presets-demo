#!/usr/bin/env node
import assert from 'node:assert/strict';
import { existsSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const catalog = JSON.parse(readFileSync(join(root, 'profiles.json'), 'utf8'));
const release = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8')).version;
const args = process.argv.slice(2);
assert(args.every((arg) => !arg.startsWith('--') || ['--write', '--check', '--adopt'].includes(arg)), 'Unknown option');
assert(!(args.includes('--write') && args.includes('--check')), 'Choose --write or --check');
const positional = args.filter((arg) => !arg.startsWith('--'));
assert(positional.length >= 1 && positional.length <= 2, 'Usage: project-presets PROFILE [DIRECTORY] [--write | --check] [--adopt]');
const [id, directory = '.'] = positional;
assert(Object.hasOwn(catalog, id), `Unknown profile: ${id}. Choose ${Object.keys(catalog).join(', ')}`);
const profile = catalog[id];
if (profile.language === 'python') {
  console.log(JSON.stringify(profile, null, 2));
  assert(!args.includes('--write') && !args.includes('--check'), 'Python uses Git submodule + uv add -r; see README');
} else {
  const target = resolve(directory);
  const path = (name) => join(target, name);
  const manifest = JSON.parse(readFileSync(path('package.json'), 'utf8'));
  const marker = '.project-preset.json';
  const previous = existsSync(path(marker)) ? JSON.parse(readFileSync(path(marker), 'utf8')) : null;
  assert(!previous || previous.profile === id, 'Changing frameworks requires an application migration; use a separate project');
  const files = {
    'eslint.config.mjs': `import preset from 'project-presets-demo/${profile.eslint}';\n\nexport default preset;\n`,
    'tsconfig.json': JSON.stringify({ extends: `project-presets-demo/tsconfig/${profile.tsconfig}.json` }, null, 2) + '\n',
  };
  for (const name of Object.keys(files)) {
    assert(previous || args.includes('--adopt') || !existsSync(path(name)), `${name} exists; integrate the documented import/extends, then use --adopt to preserve it`);
  }
  const changes = [];
  for (const field of ['dependencies', 'devDependencies']) {
    manifest[field] ??= {};
    assert(typeof manifest[field] === 'object' && !Array.isArray(manifest[field]), `Invalid ${field}`);
    assert(Object.keys(previous?.[field] ?? {}).every((name) => Object.hasOwn(profile[field], name)), 'Removing managed dependencies requires an application migration');
    for (const [name, version] of Object.entries(profile[field])) {
      const current = manifest[field][name];
      const otherField = field === 'dependencies' ? 'devDependencies' : 'dependencies';
      assert(!Object.hasOwn(manifest[otherField] ?? {}, name), `${name} is declared in ${otherField}; resolve before adoption`);
      const wasManaged = Object.hasOwn(previous?.[field] ?? {}, name);
      assert(current === version || (wasManaged ? current === previous[field][name] : current === undefined), `${name} was changed locally (${current}); resolve before updating`);
      if (current !== version) changes.push({ field, name, from: current ?? null, to: version });
      manifest[field][name] = version;
    }
  }
  assert(!Object.hasOwn(manifest.dependencies, 'project-presets-demo'), 'The preset package must be a devDependency');
  const source = manifest.devDependencies['project-presets-demo'] ?? 'git+https://github.com/omitsuhashi/project-presets-demo.git';
  assert(typeof source === 'string' && source.startsWith('git+'), 'Use a Git dependency for this demo preset package');
  manifest.devDependencies['project-presets-demo'] = `${source.split('#')[0]}#v${release}`;
  const state = { profile: id, release, dependencies: profile.dependencies, devDependencies: profile.devDependencies };
  const writes = {
    'package.json': JSON.stringify(manifest, null, 2) + '\n',
    [marker]: JSON.stringify(state, null, 2) + '\n',
    ...Object.fromEntries(Object.entries(files).filter(([name]) => !existsSync(path(name)))),
  };
  console.log(JSON.stringify({ profile: id, release, changes, create: Object.keys(writes).filter((name) => !existsSync(path(name))) }, null, 2));
  if (args.includes('--check')) {
    assert(previous?.release === release && changes.length === 0 && Object.keys(files).every((name) => existsSync(path(name))), 'Apply this preset release and regenerate the npm lock before merging');
  }
  if (args.includes('--write')) {
    // Validate and stage every file before replacing any destination.
    const staged = [];
    try {
      for (const [name, content] of Object.entries(writes)) {
        const temporary = `${path(name)}.preset-${process.pid}`;
        writeFileSync(temporary, content, { flag: 'wx' });
        staged.push([temporary, path(name)]);
      }
      for (const [temporary, destination] of staged) renameSync(temporary, destination);
    } catch (error) {
      // Staged files are retained for recovery if the filesystem rejects a write.
      throw new Error(`Preset write failed; inspect .preset-${process.pid} files before retrying`, { cause: error });
    }
  }
}
