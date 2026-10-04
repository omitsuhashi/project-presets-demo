import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, renameSync, unlinkSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { basename, dirname, join, resolve } from 'node:path';

const workflow = '.github/workflows/update-presets.yml';

export function readProject(target) {
  const names = ['package.json', '.project-preset.json', 'eslint.config.mjs', 'tsconfig.json', workflow,
    'pnpm-lock.yaml', 'package-lock.json', 'npm-shrinkwrap.json'];
  const files = names.filter((name) => existsSync(join(target, name)));
  const json = (name) => files.includes(name) ? JSON.parse(readFileSync(join(target, name), 'utf8')) : null;
  return { target, name: basename(target), files, manifest: json('package.json'), previous: json('.project-preset.json') };
}

function pnpm(target, ...args) {
  execFileSync(process.execPath, [resolve(createRequire(import.meta.url).resolve('pnpm'), '../bin/pnpm.mjs'), ...args, '--ignore-workspace'], {
    cwd: target, stdio: 'inherit', env: { ...process.env, CI: 'true', pnpm_config_ignore_scripts: 'true' },
  });
}

export function verifyProject(project, plan) {
  const { target, previous, manifest, files } = project;
  const { release, packageManager, dependencies, devDependencies } = plan.state;
  const path = (name) => join(target, name);
  assert(files.includes(workflow), 'Run --setup to add the automatic update workflow');
  assert(manifest.packageManager === packageManager && previous?.packageManager === packageManager, 'Apply the pinned pnpm version before merging');
  assert(plan.summary.source === manifest.devDependencies?.['project-presets-demo'], 'Pin the manifest to the executing preset release');
  assert(previous?.release === release && plan.summary.changes.length === 0, 'Apply this preset release and regenerate the pnpm lock before merging');
  assert(files.includes('pnpm-lock.yaml'), 'Run --setup to generate pnpm-lock.yaml');
  assert(!files.includes('package-lock.json') && !files.includes('npm-shrinkwrap.json'), 'Complete migration to pnpm before merging');
  pnpm(target, 'install', '--lockfile-only', '--frozen-lockfile', '--ignore-scripts');
  for (const [name, version] of Object.entries({ ...dependencies, ...devDependencies })) {
    assert(JSON.parse(readFileSync(path(`node_modules/${name}/package.json`), 'utf8')).version === version, `Sync ${name} with the pnpm lock`);
  }
  assert(JSON.parse(readFileSync(path('node_modules/project-presets-demo/package.json'), 'utf8')).version === release, 'The installed preset has a different release');
}

export function applyPlan(project, plan, sync) {
  const { target } = project;
  const path = (name) => join(target, name);
  mkdirSync(target, { recursive: true });
  const staged = [];
  try {
    for (const [name, content] of Object.entries(plan.writes)) {
      mkdirSync(dirname(path(name)), { recursive: true });
      const temporary = `${path(name)}.preset-${process.pid}`;
      writeFileSync(temporary, content, { flag: 'wx' });
      staged.push([temporary, path(name)]);
    }
    for (const [temporary, destination] of staged) renameSync(temporary, destination);
  } catch (error) {
    throw new Error(`Preset write failed; inspect .preset-${process.pid} files before retrying`, { cause: error });
  }
  if (sync) {
    const legacyLocks = ['package-lock.json', 'npm-shrinkwrap.json'].filter((name) => existsSync(path(name)));
    if (legacyLocks.length && !existsSync(path('pnpm-lock.yaml'))) pnpm(target, 'import');
    pnpm(target, 'install', '--lockfile-only', '--no-frozen-lockfile', '--ignore-scripts');
    pnpm(target, 'install', '--frozen-lockfile', '--ignore-scripts');
    assert(JSON.parse(readFileSync(path('node_modules/project-presets-demo/package.json'), 'utf8')).version === plan.state.release, 'The source must contain the executing preset release');
    for (const name of legacyLocks) unlinkSync(path(name));
  }
  console.log(`Automatic update PRs: commit ${workflow} with the preset files and push to the GitHub default branch. Enable Actions > General > Allow GitHub Actions to create and approve pull requests. Existing workflows are preserved; review their schedule and tests.`);
}
