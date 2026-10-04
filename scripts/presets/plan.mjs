import assert from 'node:assert/strict';

// This module only computes changes. It does not read files or run pnpm.
export function planProfile(project, preset, options = {}) {
  const { id, profile, presetVersion, publicationTag, packageManager, artifact, workflowTemplate } = preset;
  const { previous, files: existing } = project;
  const has = (name) => existing.includes(name);
  const initialize = !has('package.json');
  assert(!initialize || !previous, 'package.json was deleted locally; restore it before updating');
  assert(!initialize || !options.check, 'Run --setup to create package.json and apply this preset');
  const name = project.name.toLowerCase().replace(/[^a-z0-9._-]+/g, '-').replace(/^[._-]+|[._-]+$/g, '').slice(0, 214) || 'project';
  const manifest = initialize
    ? { name, version: '0.0.0', private: true, type: 'module' }
    : structuredClone(project.manifest);
  assert(manifest && typeof manifest === 'object' && !Array.isArray(manifest), 'package.json must contain a JSON object');
  const previousManager = manifest.packageManager;
  assert(!previousManager || /^(npm|pnpm)@/.test(previousManager), 'Migrate the existing package manager to pnpm before adopting');
  assert(!previous?.packageManager || previousManager === previous.packageManager || previousManager === packageManager, 'packageManager was changed locally; restore before updating');
  manifest.packageManager = packageManager;
  assert(!previous || previous.profile === id, 'Changing frameworks requires an application migration; use a separate project');
  const settings = {
    'eslint.config.mjs': `import preset from 'project-presets-demo/${profile.eslint}';\n\nexport default preset;\n`,
    'tsconfig.json': JSON.stringify({ extends: `project-presets-demo/tsconfig/${profile.tsconfig}.json` }, null, 2) + '\n',
  };
  for (const name of Object.keys(settings)) {
    assert(!previous || has(name), `${name} was deleted locally; restore before updating`);
    assert(previous || options.adopt || !has(name), `${name} exists; integrate the documented import/extends, then use --adopt to preserve it`);
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
  const previousSource = manifest.devDependencies['project-presets-demo'];
  assert(previousSource === undefined || typeof previousSource === 'string', 'Invalid preset dependency');
  const source = options.source ?? (previousSource === undefined || previousSource.startsWith(base) ? artifact : previousSource);
  // Official releases follow the executing CLI; custom sources remain explicit.
  manifest.devDependencies['project-presets-demo'] = source.startsWith('git+')
    ? `${source.split('#')[0]}#${publicationTag}`
    : /^(https?:|file:)/.test(source) ? source : presetVersion;
  const state = { profile: id, release: presetVersion, packageManager, dependencies: profile.dependencies, devDependencies: profile.devDependencies };
  const workflow = '.github/workflows/update-presets.yml';
  const writes = {
    'package.json': JSON.stringify(manifest, null, 2) + '\n',
    '.project-preset.json': JSON.stringify(state, null, 2) + '\n',
    ...Object.fromEntries(Object.entries(settings).filter(([name]) => !has(name))),
    ...(!has(workflow) ? { [workflow]: workflowTemplate.replaceAll('PRESET_TAG', publicationTag) } : {}),
  };
  return {
    writes,
    state,
    summary: { profile: id, release: presetVersion, packageManager, source: manifest.devDependencies['project-presets-demo'], changes, create: Object.keys(writes).filter((name) => !has(name)) },
  };
}
