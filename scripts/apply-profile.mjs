#!/usr/bin/env node
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';

const root = fileURLToPath(new URL('../', import.meta.url));
const catalog = JSON.parse(readFileSync(join(root, 'profiles.json'), 'utf8'));
const release = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8')).version;
const { values: options, positionals } = parseArgs({
  options: {
    setup: { type: 'boolean' }, write: { type: 'boolean' }, check: { type: 'boolean' },
    adopt: { type: 'boolean' }, sync: { type: 'boolean' }, source: { type: 'string' },
  },
  allowPositionals: true,
});
assert([options.setup, options.write, options.check].filter(Boolean).length <= 1, 'Choose --setup, --write or --check');
assert(options.source === undefined || /^(https?:\/\/|file:|git\+)/.test(options.source), '--source must be an artifact URL or a Git source');
const write = options.setup || options.write;
const sync = options.setup || options.sync;
assert(!sync || write, '--sync requires --write or --setup');
assert(positionals.length >= 1 && positionals.length <= 2, 'Usage: project-presets PROFILE [DIRECTORY] [--setup | --write | --check] [--adopt] [--sync] [--source URL]');
const [id, directory = '.'] = positionals;
assert(Object.hasOwn(catalog, id), `Unknown profile: ${id}. Choose ${Object.keys(catalog).join(', ')}`);
const profile = catalog[id];
if (profile.language === 'python') {
  console.log(JSON.stringify(profile, null, 2));
  assert(!write && !options.check, 'Python uses the wheel and project-presets-python; see README');
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
    assert(!previous || existsSync(path(name)), `${name} was deleted locally; restore before updating`);
    assert(previous || options.adopt || !existsSync(path(name)), `${name} exists; integrate the documented import/extends, then use --adopt to preserve it`);
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
  const base = 'https://github.com/omitsuhashi/project-presets-demo/releases/download/';
  const artifact = `${base}v${release}/project-presets-demo-${release}.tgz`;
  const previousSource = manifest.devDependencies['project-presets-demo'];
  assert(previousSource === undefined || typeof previousSource === 'string', 'Invalid preset dependency');
  const source = options.source ?? (previousSource === undefined || previousSource.startsWith(base) ? artifact : previousSource);
  // Official releases follow the executing CLI; custom sources remain explicit.
  manifest.devDependencies['project-presets-demo'] = source.startsWith('git+')
    ? `${source.split('#')[0]}#v${release}`
    : /^(https?:|file:)/.test(source) ? source : release;
  const state = { profile: id, release, dependencies: profile.dependencies, devDependencies: profile.devDependencies };
  const writes = {
    'package.json': JSON.stringify(manifest, null, 2) + '\n',
    [marker]: JSON.stringify(state, null, 2) + '\n',
    ...Object.fromEntries(Object.entries(files).filter(([name]) => !existsSync(path(name)))),
  };
  console.log(JSON.stringify({ profile: id, release, source: manifest.devDependencies['project-presets-demo'], changes, create: Object.keys(writes).filter((name) => !existsSync(path(name))) }, null, 2));
  if (options.check) {
    assert(manifest.devDependencies['project-presets-demo'] === previousSource, 'Pin the manifest to the executing preset release');
    assert(previous?.release === release && changes.length === 0 && Object.keys(files).every((name) => existsSync(path(name))), 'Apply this preset release and regenerate the npm lock before merging');
    const lock = JSON.parse(readFileSync(path('package-lock.json'), 'utf8'));
    for (const field of ['dependencies', 'devDependencies']) {
      for (const [name, version] of Object.entries(profile[field])) {
        assert(lock.packages[''][field]?.[name] === version && lock.packages[`node_modules/${name}`]?.version === version, `Regenerate the npm lock for ${name}`);
      }
    }
    assert(lock.packages['node_modules/project-presets-demo']?.version === release, 'The npm lock has a different preset release');
    assert(lock.packages[''].devDependencies?.['project-presets-demo'] === source, 'The npm lock and manifest use different preset sources');
  }
  if (write) {
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
    if (sync) {
      const flags = ['--ignore-scripts', '--no-audit', '--no-fund'];
      if (source.startsWith('git+')) flags.push('--allow-git=root');
      if (/^https?:/.test(source)) flags.push('--allow-remote=root');
      execFileSync('npm', ['install', '--package-lock-only', ...flags], { cwd: target, stdio: 'inherit' });
      execFileSync('npm', ['ci', ...flags], { cwd: target, stdio: 'inherit' });
      const lock = JSON.parse(readFileSync(path('package-lock.json'), 'utf8'));
      assert(lock.packages['node_modules/project-presets-demo']?.version === release, 'The source must contain the executing preset release');
    }
  }
}
