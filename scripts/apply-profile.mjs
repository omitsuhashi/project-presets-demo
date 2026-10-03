#!/usr/bin/env node
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, renameSync, unlinkSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { basename, dirname, resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';

const root = fileURLToPath(new URL('../', import.meta.url));
const catalog = JSON.parse(readFileSync(join(root, 'profiles.json'), 'utf8'));
const { version: release, dependencies } = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'));
const publication = existsSync(join(root, 'preset-release.json')) ? JSON.parse(readFileSync(join(root, 'preset-release.json'), 'utf8')) : null;
const tag = publication?.tag ?? `v${release}`;
const packageManager = `pnpm@${dependencies.pnpm}`;
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
assert(!publication || (publication.profile === id && publication.version === release), 'The artifact does not match the selected template/version');
const profile = catalog[id];
if (profile.language === 'python') {
  console.log(JSON.stringify(profile, null, 2));
  assert(!write && !options.check, 'Python uses the wheel and project-presets-python; see README');
} else {
  const target = resolve(directory);
  const path = (name) => join(target, name);
  const marker = '.project-preset.json';
  const previous = existsSync(path(marker)) ? JSON.parse(readFileSync(path(marker), 'utf8')) : null;
  const initialize = !existsSync(path('package.json'));
  assert(!initialize || !previous, 'package.json was deleted locally; restore it before updating');
  assert(!initialize || !options.check, 'Run --setup to create package.json and apply this preset');
  const name = basename(target).toLowerCase().replace(/[^a-z0-9._-]+/g, '-').replace(/^[._-]+|[._-]+$/g, '').slice(0, 214) || 'project';
  const manifest = initialize
    ? { name, version: '0.0.0', private: true, type: 'module' }
    : JSON.parse(readFileSync(path('package.json'), 'utf8'));
  assert(manifest && typeof manifest === 'object' && !Array.isArray(manifest), 'package.json must contain a JSON object');
  const previousManager = manifest.packageManager;
  assert(!previousManager || /^(npm|pnpm)@/.test(previousManager), 'Migrate the existing package manager to pnpm before adopting');
  assert(!previous?.packageManager || previousManager === previous.packageManager || previousManager === packageManager, 'packageManager was changed locally; restore before updating');
  manifest.packageManager = packageManager;
  const pnpm = (...args) => execFileSync(process.execPath, [resolve(createRequire(import.meta.url).resolve('pnpm'), '../bin/pnpm.mjs'), ...args, '--ignore-workspace'], {
    cwd: target, stdio: 'inherit', env: { ...process.env, CI: 'true', pnpm_config_ignore_scripts: 'true' },
  });
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
  const artifact = `${base}${tag}/${publication?.asset ?? `project-presets-demo-${release}.tgz`}`;
  const previousSource = manifest.devDependencies['project-presets-demo'];
  assert(previousSource === undefined || typeof previousSource === 'string', 'Invalid preset dependency');
  const source = options.source ?? (previousSource === undefined || previousSource.startsWith(base) ? artifact : previousSource);
  // Official releases follow the executing CLI; custom sources remain explicit.
  manifest.devDependencies['project-presets-demo'] = source.startsWith('git+')
    ? `${source.split('#')[0]}#${tag}`
    : /^(https?:|file:)/.test(source) ? source : release;
  const state = { profile: id, release, packageManager, dependencies: profile.dependencies, devDependencies: profile.devDependencies };
  // ponytail: one standalone project root; shared repository workflows need explicit directory inputs.
  const workflow = '.github/workflows/update-presets.yml';
  const updateWorkflow = readFileSync(join(root, 'python/project_presets_demo/update-presets.yml'), 'utf8')
    .replaceAll('PRESET_TAG', tag);
  const writes = {
    'package.json': JSON.stringify(manifest, null, 2) + '\n',
    [marker]: JSON.stringify(state, null, 2) + '\n',
    ...Object.fromEntries(Object.entries(files).filter(([name]) => !existsSync(path(name)))),
    ...(!existsSync(path(workflow)) ? { [workflow]: updateWorkflow } : {}),
  };
  console.log(JSON.stringify({ profile: id, release, packageManager, source: manifest.devDependencies['project-presets-demo'], changes, create: Object.keys(writes).filter((name) => !existsSync(path(name))) }, null, 2));
  if (options.check) {
    assert(existsSync(path(workflow)), 'Run --setup to add the automatic update workflow');
    assert(previousManager === packageManager && previous?.packageManager === packageManager, 'Apply the pinned pnpm version before merging');
    assert(manifest.devDependencies['project-presets-demo'] === previousSource, 'Pin the manifest to the executing preset release');
    assert(previous?.release === release && changes.length === 0 && Object.keys(files).every((name) => existsSync(path(name))), 'Apply this preset release and regenerate the pnpm lock before merging');
    assert(existsSync(path('pnpm-lock.yaml')), 'Run --setup to generate pnpm-lock.yaml');
    assert(!existsSync(path('package-lock.json')) && !existsSync(path('npm-shrinkwrap.json')), 'Complete migration to pnpm before merging');
    pnpm('install', '--lockfile-only', '--frozen-lockfile', '--ignore-scripts');
    for (const field of ['dependencies', 'devDependencies']) {
      for (const [name, version] of Object.entries(profile[field])) {
        assert(JSON.parse(readFileSync(path(`node_modules/${name}/package.json`), 'utf8')).version === version, `Sync ${name} with the pnpm lock`);
      }
    }
    assert(JSON.parse(readFileSync(path('node_modules/project-presets-demo/package.json'), 'utf8')).version === release, 'The installed preset has a different release');
  }
  if (write) {
    // Validate and stage every file before replacing any destination.
    mkdirSync(target, { recursive: true });
    const staged = [];
    try {
      for (const [name, content] of Object.entries(writes)) {
        mkdirSync(dirname(path(name)), { recursive: true });
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
      const legacyLocks = ['package-lock.json', 'npm-shrinkwrap.json'].filter((name) => existsSync(path(name)));
      if (legacyLocks.length && !existsSync(path('pnpm-lock.yaml'))) pnpm('import');
      pnpm('install', '--lockfile-only', '--no-frozen-lockfile', '--ignore-scripts');
      pnpm('install', '--frozen-lockfile', '--ignore-scripts');
      assert(JSON.parse(readFileSync(path('node_modules/project-presets-demo/package.json'), 'utf8')).version === release, 'The source must contain the executing preset release');
      for (const name of legacyLocks) unlinkSync(path(name));
    }
    console.log(`Automatic update PRs: commit ${workflow} with the preset files and push to the GitHub default branch. Enable Actions > General > Allow GitHub Actions to create and approve pull requests. Existing workflows are preserved; review their schedule and tests.`);
  }
}
