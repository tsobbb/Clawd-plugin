import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { lintClawdPluginCode } from './plugin_linter';

test('Clawd v3.4 python file satisfies 100% of acceptance criteria', () => {
  const filePath = path.resolve(process.cwd(), 'public/clawd_v3_4.py');
  const code = fs.readFileSync(filePath, 'utf-8');

  const report = lintClawdPluginCode(code);

  assert.equal(report.forbiddenStringsCount, 0, 'Must have 0 forbidden strings');
  for (const rule of report.rules) {
    assert.equal(rule.passed, true, `Rule failed: ${rule.title} - ${rule.details}`);
  }
  assert.equal(report.overallPassed, true);
  assert.equal(report.score, 100);
});
