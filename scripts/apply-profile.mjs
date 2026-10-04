#!/usr/bin/env node
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { planProfile } from './presets/plan.mjs';
import { applyPlan, readProject, verifyProject } from './presets/project.mjs';

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
  const preset = {
    id, profile, presetVersion: release, publicationTag: tag, packageManager,
    artifact: `https://github.com/omitsuhashi/project-presets-demo/releases/download/${tag}/${publication?.asset ?? `project-presets-demo-${release}.tgz`}`,
    workflowTemplate: readFileSync(join(root, 'python/project_presets_demo/update-presets.yml'), 'utf8'),
  };
  const project = readProject(resolve(directory));
  const plan = planProfile(project, preset, options);
  console.log(JSON.stringify(plan.summary, null, 2));
  if (options.check) verifyProject(project, plan);
  if (write) applyPlan(project, plan, sync);
}
