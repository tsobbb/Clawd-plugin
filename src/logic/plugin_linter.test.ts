import test from 'node:test';
import assert from 'node:assert/strict';
import { lintClawdPluginCode } from './plugin_linter';

test('Linter flags forbidden strings when present in code', () => {
  const badCode = `
# Some legacy lastfm code
__version__ = "3.2"
class RetroAudio:
    pass
# Pano scrobbler
`;
  const report = lintClawdPluginCode(badCode);
  assert.equal(report.overallPassed, false);
  assert.equal(report.forbiddenStringsCount >= 3, true);
  const forbiddenRule = report.rules.find((r) => r.id === 'forbidden_strings');
  assert.equal(forbiddenRule?.passed, false);
});

test('Linter passes clean v3.4 code snippet', () => {
  const goodCode = `
__version__ = "3.4"
# Clawd Bridge client
BRIDGE_URL = "http://127.0.0.1:44444/now-playing"
# 350 ms standard, 3.0 s backoff
# 0.25 s jitter filter, _user_offset, _track_base_pos, _calc_raw
# [📋] tap to sync dialog
# WeakReference and OnChildAttachStateChangeListener
# maxlen=500 and 512 * 1024 rotation
# thanks, дякую, привіт, вітаю, бувай, кохаю, гроші, друкує
# Handler.postDelayed for _schedule_karaoke and t_next
`;
  const report = lintClawdPluginCode(goodCode);
  assert.equal(report.forbiddenStringsCount, 0);
  assert.equal(report.overallPassed, true);
  assert.equal(report.score, 100);
});
