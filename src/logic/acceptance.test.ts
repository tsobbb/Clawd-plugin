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

test('Clawd v3.4 contains all 5 critical bugfixes from ТЗ', () => {
  const filePath = path.resolve(process.cwd(), 'public/clawd_v3_4.py');
  const code = fs.readFileSync(filePath, 'utf-8');

  // Bugfix 1.1: Normalization of timestamp in fallback sync.json
  assert.ok(
    code.includes('ts > 1e11') && code.includes('ts / 1000.0'),
    '1.1: Missing timestamp magnitude normalization (ts > 1e11 -> ts / 1000.0)'
  );
  assert.ok(
    code.includes('abs(time.time() - ts) <= 5.0'),
    '1.1: Missing freshness check abs(time.time() - ts) <= 5.0'
  );

  // Bugfix 1.2: Reset of time base on playback resumption
  assert.ok(
    code.includes('was_paused') && code.includes('resumed = is_playing and was_paused'),
    '1.2: Missing was_paused and resumed state transition tracking'
  );
  assert.ok(
    code.includes('drift > 0.25 or self._track_base_time == 0.0 or resumed'),
    '1.2: Missing base update condition on resumed == True'
  );

  // Bugfix 1.3: Instrumental pause scheduling and mouth closure
  assert.ok(
    code.includes('sing_until = t_curr + min(line_dur - 0.7, 5.0) if line_dur > 5.5 else t_next_line'),
    '1.3: Missing sing_until formula for long/short lines'
  );
  assert.ok(
    code.includes('wake_at = sing_until') && code.includes('wake_at = t_next_line'),
    '1.3: Missing wake_at targeting sing_until during singing and t_next_line during instrumental breaks'
  );

  // Bugfix 1.4: Key unification in Tap-to-Sync
  assert.ok(
    code.includes('canon_key = f"{clean_a} - {clean_t}"') &&
    code.includes('self._session_offsets[canon_key] = new_offset'),
    '1.4: Missing canonical key storage in _session_offsets[canon_key]'
  );

  // Bugfix 1.5: Hierarchy check in RecyclerAttachStateListener
  assert.ok(
    code.includes('curr = target.getParent()') &&
    code.includes('if curr.equals(view) or (curr is view):'),
    '1.5: Missing recursive target.getParent() ancestor traversal in RecyclerAttachStateListener'
  );

  // Extra: Climber instinct
  assert.ok(
    code.includes('_next_climb_attempt') && code.includes('platforms_above'),
    '2.5: Missing climber instinct for ascending from screen bottom'
  );
});

test('Clawd v3.4.1 contains all 6 enhancements from Правка 3.4.1', () => {
  const filePath = path.resolve(process.cwd(), 'public/clawd_v3_4.py');
  const code = fs.readFileSync(filePath, 'utf-8');

  // 1. Karaoke loop survival during hops/taps
  assert.ok(
    code.includes('postDelayed(self._karaoke_switch_r, 120)'),
    '3.4.1.1: Missing 120ms reschedule when state is not idle/walk'
  );

  // 2. Tap-flee mechanic (+15% speed and jump upwards)
  assert.ok(
    code.includes('tap_flee') && code.includes('_flee_boost_until') && code.includes('speed_factor *= 1.15'),
    '3.4.1.2: Missing tap_flee phrase, boost timer, or 15% speed multiplication'
  );

  // 3. Laser dot visual rendering
  assert.ok(
    code.includes('_update_laser_view') && code.includes('0xFFFF0033'),
    '3.4.1.3: Missing laser view creation and red gradient drawing'
  );

  // 4. Recycled bitmap safety
  assert.ok(
    code.includes('view.setImageBitmap(None)') || code.includes('copy.setImageBitmap(None)'),
    '3.4.1.4: Missing setImageBitmap(None) before bitmap recycling'
  );
  assert.ok(
    code.includes('animate().cancel()'),
    '3.4.1.4: Missing animate().cancel() before bitmap recycling'
  );

  // 5. MAX_FRAME_CACHE = 128 and frame bitmap recycling
  assert.ok(
    code.includes('MAX_FRAME_CACHE = 128'),
    '3.4.1.5: MAX_FRAME_CACHE must be increased to 128'
  );
  assert.ok(
    code.includes('old_bmp.recycle()'),
    '3.4.1.5: Missing explicit old_bmp.recycle() on frame eviction'
  );

  // 6. Recycler listener leak prevention
  assert.ok(
    code.includes('already = any(p is parent') || code.includes('already_attached'),
    '3.4.1.6: Missing already-attached listener check before adding to RecyclerView'
  );
});
