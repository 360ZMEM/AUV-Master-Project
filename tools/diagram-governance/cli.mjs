#!/usr/bin/env node
import { spawnSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, '../..');
const python = process.env.DIAGRAM_GOVERNANCE_PYTHON || 'python3';
const deps = resolve(repo, '.diagram-governance/pydeps');
const env = {
  ...process.env,
  PYTHONPATH: [deps, process.env.PYTHONPATH].filter(Boolean).join(':'),
  PLAYWRIGHT_BROWSERS_PATH: resolve(repo, '.diagram-governance/browsers'),
  FONTCONFIG_FILE: resolve(repo, 'config/diagram-governance/fonts.conf'),
};
const result = spawnSync(python, [resolve(here, 'governance.py'), ...process.argv.slice(2)], {
  cwd: repo, env, stdio: 'inherit', timeout: 15 * 60 * 1000,
});
if (result.error) {
  console.error(result.error.message);
  process.exit(result.error.code === 'ETIMEDOUT' ? 2 : 3);
}
process.exit(result.status ?? 3);
