import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const temp = mkdtempSync(join(tmpdir(), 'project-presets-check-'));
const provider = join(temp, 'provider');
const ts = join(temp, 'typescript-consumer');
const py = join(temp, 'python-consumer');
const run = (cwd, command, args, expected = 0) => {
  const result = spawnSync(command, args, { cwd, encoding: 'utf8', env: { ...process.env, NEXT_TELEMETRY_DISABLED: '1' } });
  assert.ifError(result.error);
  assert.equal(result.status, expected, `${command} ${args.join(' ')}\n${result.stdout}\n${result.stderr}`);
  return result.stdout;
};
const git = (cwd, ...args) => run(cwd, 'git', args).trim();
const init = (cwd) => {
  mkdirSync(cwd, { recursive: true });
  git(cwd, 'init', '-b', 'main');
  git(cwd, 'config', 'user.name', 'Demo Check');
  git(cwd, 'config', 'user.email', 'demo@example.invalid');
};
const commit = (cwd, message) => {
  git(cwd, 'add', '.');
  git(cwd, 'commit', '-m', message);
  return git(cwd, 'rev-parse', 'HEAD');
};
const install = (version) => {
  const manifest = JSON.parse(readFileSync(join(ts, 'package.json'), 'utf8'));
  manifest.devDependencies = {
    ...manifest.devDependencies,
    'project-presets-demo': `git+file://${provider}#${version}`,
  };
  writeFileSync(join(ts, 'package.json'), JSON.stringify(manifest, null, 2) + '\n');
  run(ts, 'npm', ['install', '--package-lock-only', '--allow-git=root', '--ignore-scripts', '--no-audit', '--no-fund']);
  run(ts, 'npm', ['ci', '--allow-git=root', '--ignore-scripts', '--no-audit', '--no-fund']);
  run(ts, 'node', ['node_modules/project-presets-demo/scripts/apply-profile.mjs', 'typescript-node', '--check'], 1);
  run(ts, 'node', ['node_modules/project-presets-demo/scripts/apply-profile.mjs', 'typescript-node', '--write']);
  run(ts, 'node', ['node_modules/project-presets-demo/scripts/apply-profile.mjs', 'typescript-node', '--check'], 1);
  run(ts, 'npm', ['install', '--package-lock-only', '--allow-git=root', '--ignore-scripts', '--no-audit', '--no-fund']);
  run(ts, 'npm', ['ci', '--allow-git=root', '--ignore-scripts', '--no-audit', '--no-fund']);
  run(ts, 'node', ['node_modules/project-presets-demo/scripts/apply-profile.mjs', 'typescript-node', '--check']);
};
const lintTs = (expected = 0) => JSON.parse(run(ts, join(ts, 'node_modules/.bin/eslint'), [
  'main.ts', '--format', 'json',
], expected));
const pythonSettings = () => run(py, 'uv', ['run', '--locked', 'python', '-c',
  "import json,tomllib; print(json.dumps(tomllib.load(open('pyproject.toml', 'rb'))['tool']['ruff'], sort_keys=True))"]);
const uvLint = (expected = 0) => JSON.parse(run(py, 'uv', ['run', '--locked', 'ruff', 'check', 'main.py', '--output-format', 'json'], expected));

try {
  const declared = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'));
  for (const profile of Object.values(JSON.parse(readFileSync(join(root, 'profiles.json'), 'utf8')))) {
    if (profile.language !== 'typescript') continue;
    for (const [name, version] of Object.entries({ ...profile.dependencies, ...profile.devDependencies })) {
      assert.equal(declared.dependencies[name] ?? declared.devDependencies[name], version, `Profile and validation dependency differ: ${name}`);
    }
  }
  init(provider);
  for (const path of ['package.json', 'typescript', 'python', 'profiles.json', 'profiles', 'scripts', 'LICENSE']) {
    cpSync(join(root, path), join(provider, path), { recursive: true });
  }
  const catalog = JSON.parse(readFileSync(join(provider, 'profiles.json'), 'utf8'));
  const currentNodeTypes = catalog['typescript-node'].devDependencies['@types/node'];
  const currentRuff = catalog['python-scripts'].devDependencies.ruff;
  declared.version = '1.0.0';
  writeFileSync(join(provider, 'package.json'), JSON.stringify(declared, null, 2) + '\n');
  catalog['typescript-node'].devDependencies['@types/node'] = '24.19.0';
  catalog['python-scripts'].devDependencies.ruff = '0.16.9';
  writeFileSync(join(provider, 'profiles/python-scripts/requirements-dev.txt'), 'ruff==0.16.9\n');
  writeFileSync(join(provider, 'profiles.json'), JSON.stringify(catalog, null, 2) + '\n');
  const oldSha = commit(provider, 'Release v1.0.0');
  git(provider, 'tag', 'v1.0.0');
  git(provider, 'branch', 'release/v1');

  const adoption = join(temp, 'existing-project');
  mkdirSync(adoption);
  writeFileSync(join(adoption, 'package.json'), '{"name":"existing","private":true}\n');
  const existingLint = "import preset from 'project-presets-demo/node';\nexport default [...preset, {rules:{'no-console':'off'}}];\n";
  writeFileSync(join(adoption, 'eslint.config.mjs'), existingLint);
  run(root, 'node', ['scripts/apply-profile.mjs', 'typescript-node', adoption, '--write'], 1);
  assert(!readFileSync(join(adoption, 'package.json'), 'utf8').includes('devDependencies'));
  run(root, 'node', ['scripts/apply-profile.mjs', 'typescript-node', adoption, '--adopt', '--write']);
  assert.equal(readFileSync(join(adoption, 'eslint.config.mjs'), 'utf8'), existingLint);

  mkdirSync(ts);
  writeFileSync(join(ts, 'package.json'), '{"name":"consumer","private":true,"type":"module"}\n');
  const beforePreview = readFileSync(join(ts, 'package.json'));
  run(root, 'node', ['scripts/apply-profile.mjs', 'typescript-node', ts]);
  assert.deepEqual(readFileSync(join(ts, 'package.json')), beforePreview);
  assert(!readFileSync(join(ts, 'package.json'), 'utf8').includes('devDependencies'));
  run(root, 'node', ['scripts/apply-profile.mjs', '../unknown', ts, '--write'], 1);
  assert.deepEqual(readFileSync(join(ts, 'package.json')), beforePreview);
  install('v1.0.0');
  writeFileSync(join(ts, 'eslint.config.mjs'), `import node from 'project-presets-demo/node';
export default [...node, { files: ['**/*.ts'], rules: { '@typescript-eslint/no-explicit-any': 'off' } }];\n`);
  writeFileSync(join(ts, 'main.ts'), "const message: any = 'consumer override survives';\nconsole.log(message);\n");
  const oldManifest = readFileSync(join(ts, 'package.json'));
  const oldLock = readFileSync(join(ts, 'package-lock.json'));
  const oldState = readFileSync(join(ts, '.project-preset.json'));
  const originalSource = readFileSync(join(ts, 'main.ts'));
  const originalTsconfig = readFileSync(join(ts, 'tsconfig.json'));
  assert.equal(JSON.parse(oldManifest).devDependencies['@types/node'], '24.19.0');
  run(ts, 'node', ['node_modules/project-presets-demo/scripts/apply-profile.mjs', 'typescript-next', '--write'], 1);
  assert.deepEqual(readFileSync(join(ts, 'package.json')), oldManifest);
  const edited = JSON.parse(oldManifest);
  edited.devDependencies.typescript = '5.0.0';
  writeFileSync(join(ts, 'package.json'), JSON.stringify(edited));
  run(ts, 'node', ['node_modules/project-presets-demo/scripts/apply-profile.mjs', 'typescript-node', '--write'], 1);
  assert.equal(JSON.parse(readFileSync(join(ts, 'package.json'))).devDependencies.typescript, '5.0.0');
  writeFileSync(join(ts, 'package.json'), oldManifest);

  init(py);
  git(py, '-c', 'protocol.file.allow=always', 'submodule', 'add', '-b', 'release/v1', provider, '.lint-presets');
  writeFileSync(join(py, '.gitignore'), '.venv/\n.ruff_cache/\n__pycache__/\n');
  writeFileSync(join(py, 'pyproject.toml'), `[project]
name = "python-consumer"
version = "0.0.0"
requires-python = ">=3.12,<3.13"

[tool.ruff]
extend = ".lint-presets/python/scripts.toml"
target-version = "py312"
line-length = 100
extend-exclude = [".lint-presets"]

[tool.ruff.lint]
ignore = ["F401"]\n`);
  writeFileSync(join(py, 'main.py'), 'import math\n\nprint("consumer override survives")\n');
  run(py, 'uv', ['add', '--dev', '-r', '.lint-presets/profiles/python-scripts/requirements-dev.txt']);
  run(py, 'uv', ['run', '--locked', 'python', '-c', 'import sys; assert sys.version_info[:2] == (3, 12)']);
  commit(py, 'Pin preset v1.0.0');
  const originalTsConfig = readFileSync(join(ts, 'eslint.config.mjs'));
  const originalPyConfig = pythonSettings();
  assert.equal(lintTs()[0].errorCount, 0);
  assert.deepEqual(uvLint(), []);
  assert.equal(run(py, 'uv', ['run', '--locked', 'ruff', '--version']).trim(), 'ruff 0.16.9');
  console.log('PASS: both consumers use v1.0.0 and preserve local overrides');

  for (const [id, example] of [['typescript-hono', 'hono'], ['typescript-next', 'next']]) {
    const consumer = join(temp, id);
    mkdirSync(consumer);
    writeFileSync(join(consumer, 'package.json'), '{"name":"framework-consumer","private":true,"type":"module","scripts":{"custom":"keep"}}\n');
    run(consumer, 'npm', ['install', '--package-lock-only', '--allow-git=root', '--ignore-scripts', '--no-audit', '--no-fund', '--save-dev', '--save-exact',
      `git+file://${provider}#v1.0.0`]);
    run(consumer, 'npm', ['ci', '--allow-git=root', '--ignore-scripts', '--no-audit', '--no-fund']);
    run(consumer, 'npm', ['exec', '--', 'project-presets', id, '--setup']);
    run(consumer, 'npm', ['exec', '--', 'project-presets', id, '--check']);
    const applied = JSON.parse(readFileSync(join(consumer, 'package.json')));
    assert.deepEqual(applied.dependencies, catalog[id].dependencies);
    for (const [name, version] of Object.entries(catalog[id].devDependencies)) assert.equal(applied.devDependencies[name], version);
    assert.equal(applied.scripts.custom, 'keep');
    cpSync(join(root, 'examples', example), consumer, { recursive: true });
    run(consumer, join(consumer, 'node_modules/.bin/eslint'), ['.']);
    run(consumer, join(consumer, 'node_modules/.bin/tsc'), ['--noEmit']);
    if (example === 'hono') {
      run(consumer, 'node', ['--input-type=module', '-e',
        "import assert from 'node:assert/strict'; import app from './app.ts'; assert.deepEqual(await (await app.request('/health')).json(), {ok:true});"]);
    } else {
      run(consumer, join(consumer, 'node_modules/.bin/next'), ['build', '--webpack']);
    }
    console.log(`PASS: ${id} installs matching dependencies, lint and TypeScript settings; framework check passes`);
  }

  // New blocking checks are a major release. Change only the central provider.
  const nodePath = join(provider, 'typescript/node.js');
  writeFileSync(nodePath, readFileSync(nodePath, 'utf8').replace(
    'languageOptions: { globals: globals.node },',
    "languageOptions: { globals: globals.node },\n  rules: { 'no-console': 'error' },",
  ));
  writeFileSync(join(provider, 'python/scripts.toml'), 'extend = "base.toml"\n\n[lint]\nextend-select = ["T20"]\n');
  const manifest = JSON.parse(readFileSync(join(provider, 'package.json'), 'utf8'));
  manifest.version = '2.0.0';
  writeFileSync(join(provider, 'package.json'), JSON.stringify(manifest, null, 2) + '\n');
  catalog['typescript-node'].devDependencies['@types/node'] = currentNodeTypes;
  catalog['python-scripts'].devDependencies.ruff = currentRuff;
  writeFileSync(join(provider, 'profiles/python-scripts/requirements-dev.txt'), `ruff==${currentRuff}\n`);
  writeFileSync(join(provider, 'profiles.json'), JSON.stringify(catalog, null, 2) + '\n');
  const newSha = commit(provider, 'Release v2.0.0');
  git(provider, 'tag', 'v2.0.0');
  install('v2.0.0');
  git(join(py, '.lint-presets'), 'fetch', 'origin', '--tags');
  git(join(py, '.lint-presets'), 'checkout', 'v2.0.0');
  run(py, 'uv', ['add', '--dev', '-r', '.lint-presets/profiles/python-scripts/requirements-dev.txt']);
  const updateCommit = commit(py, 'Update pinned preset to v2.0.0');
  assert.deepEqual(lintTs(1)[0].messages.map((message) => message.ruleId), ['no-console']);
  assert.deepEqual(uvLint(1).map((message) => message.code), ['T201']);
  assert.equal(run(py, 'uv', ['run', '--locked', 'ruff', '--version']).trim(), `ruff ${currentRuff}`);
  assert.equal(git(join(py, '.lint-presets'), 'rev-parse', 'HEAD'), newSha);
  assert.deepEqual(readFileSync(join(ts, 'eslint.config.mjs')), originalTsConfig);
  assert.equal(pythonSettings(), originalPyConfig);
  assert.deepEqual(readFileSync(join(ts, 'main.ts')), originalSource);
  assert.deepEqual(readFileSync(join(ts, 'tsconfig.json')), originalTsconfig);
  assert.equal(JSON.parse(readFileSync(join(ts, 'package.json'))).devDependencies['@types/node'], currentNodeTypes);
  console.log('PASS: central v2.0.0 updates managed dependency versions and lint together; consumer code and overrides survive');

  writeFileSync(join(ts, 'package.json'), oldManifest);
  writeFileSync(join(ts, 'package-lock.json'), oldLock);
  writeFileSync(join(ts, '.project-preset.json'), oldState);
  run(ts, 'npm', ['ci', '--offline', '--allow-git=root', '--ignore-scripts', '--no-audit', '--no-fund']);
  git(py, 'revert', '--no-edit', updateCommit);
  git(py, '-c', 'protocol.file.allow=always', 'submodule', 'update', '--init', '--recursive');
  assert.equal(git(join(py, '.lint-presets'), 'rev-parse', 'HEAD'), oldSha);
  assert.equal(lintTs()[0].errorCount, 0);
  assert.deepEqual(uvLint(), []);
  assert.equal(run(py, 'uv', ['run', '--locked', 'ruff', '--version']).trim(), 'ruff 0.16.9');
  assert.equal(JSON.parse(readFileSync(join(ts, 'package.json'))).devDependencies['@types/node'], '24.19.0');
  console.log('PASS: restoring the npm lock/state and reverting the submodule pin rolls dependencies and configuration back');
} finally {
  rmSync(temp, { recursive: true, force: true });
}
