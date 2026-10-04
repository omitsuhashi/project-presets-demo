import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { planProfile } from '../scripts/presets/plan.mjs';
import { applyPlan, readProject } from '../scripts/presets/project.mjs';

const preset = {
  id: 'typescript-hono', presetVersion: '2.2.1', publicationTag: 'v2.3.0', packageManager: 'pnpm@11.28.0',
  artifact: 'https://github.com/omitsuhashi/project-presets-demo/releases/download/v2.3.0/typescript-hono-2.2.1.tgz',
  workflowTemplate: 'uses: update-consumer.yml@PRESET_TAG\n',
  profile: { eslint: 'hono', tsconfig: 'node', dependencies: { hono: '4.13.12' }, devDependencies: { typescript: '6.0.3' } },
};
const empty = () => ({ name: 'My project', files: [], manifest: null, previous: null });
const adopted = () => {
  const plan = planProfile(empty(), preset);
  return { name: 'project', files: Object.keys(plan.writes), manifest: JSON.parse(plan.writes['package.json']), previous: structuredClone(plan.state) };
};

test('planning a new project is deterministic and leaves the snapshot untouched', () => {
  const project = empty();
  const original = structuredClone(project);
  const plan = planProfile(project, preset);
  assert.deepEqual(planProfile(project, preset), plan);
  assert.deepEqual(project, original);
  assert.equal(JSON.parse(plan.writes['package.json']).name, 'my-project');
  assert.equal(plan.summary.release, '2.2.1');
  assert.equal(plan.summary.source, preset.artifact);
  assert.equal(plan.writes['.github/workflows/update-presets.yml'], 'uses: update-consumer.yml@v2.3.0\n');
});

test('the applied plan is exactly the preview and a subsequent plan has no dependency changes', () => {
  const target = mkdtempSync(join(tmpdir(), 'preset-plan-'));
  try {
    const project = readProject(target);
    const plan = planProfile(project, preset);
    applyPlan(project, plan, false);
    for (const [name, content] of Object.entries(plan.writes)) {
      assert.equal(readFileSync(join(target, name), 'utf8'), content);
    }
    const next = planProfile(readProject(target), preset);
    assert.deepEqual(next.summary.changes, []);
    assert.deepEqual(next.summary.create, []);
  } finally {
    rmSync(target, { recursive: true, force: true });
  }
});

test('updates change managed pins while preserving unrelated dependencies and project settings', () => {
  const project = adopted();
  project.previous.dependencies.hono = '4.13.11';
  project.manifest.dependencies.hono = '4.13.11';
  project.manifest.dependencies['project-library'] = '^1.0.0';
  project.manifest.scripts = { test: 'my-test' };
  const original = structuredClone(project);
  const plan = planProfile(project, preset);
  const manifest = JSON.parse(plan.writes['package.json']);
  assert.equal(manifest.dependencies.hono, '4.13.12');
  assert.equal(manifest.dependencies['project-library'], '^1.0.0');
  assert.deepEqual(manifest.scripts, { test: 'my-test' });
  assert.deepEqual(plan.summary.changes, [{ field: 'dependencies', name: 'hono', from: '4.13.11', to: '4.13.12' }]);
  assert.deepEqual(project, original);
  assert.equal(plan.writes['eslint.config.mjs'], undefined);
  assert.equal(plan.writes['.github/workflows/update-presets.yml'], undefined);
});

test('adoption preserves existing config files and requires explicit consent', () => {
  const project = empty();
  project.files = ['package.json', 'eslint.config.mjs', 'tsconfig.json'];
  project.manifest = { name: 'existing', private: true };
  assert.throws(() => planProfile(project, preset), /exists; integrate/);
  const plan = planProfile(project, preset, { adopt: true });
  assert.equal(plan.writes['eslint.config.mjs'], undefined);
  assert.equal(plan.writes['tsconfig.json'], undefined);
});

test('local managed changes, deletions and profile switches fail during planning', () => {
  const modified = adopted();
  modified.manifest.dependencies.hono = '^5.0.0';
  assert.throws(() => planProfile(modified, preset), /hono was changed locally/);
  const deleted = adopted();
  delete deleted.manifest.dependencies.hono;
  assert.throws(() => planProfile(deleted, preset), /hono was changed locally/);
  deleted.files = deleted.files.filter((name) => name !== 'tsconfig.json');
  assert.throws(() => planProfile(deleted, preset), /tsconfig.json was deleted/);
  const switched = adopted();
  switched.previous.profile = 'typescript-next';
  assert.throws(() => planProfile(switched, preset), /Changing frameworks/);
});

test('custom Git sources follow the publication tag rather than the profile version', () => {
  const project = adopted();
  project.manifest.devDependencies['project-presets-demo'] = 'git+https://example.com/presets.git#v2.2.0';
  const plan = planProfile(project, preset);
  assert.equal(plan.summary.source, 'git+https://example.com/presets.git#v2.3.0');
});
