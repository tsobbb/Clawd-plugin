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

test('Clawd v3.5 satisfies all requirements from ТЗ v3.5', () => {
  const filePath = path.resolve(process.cwd(), 'public/clawd_v3_4.py');
  const code = fs.readFileSync(filePath, 'utf-8');

  // BLOCK 1: Karaoke UI Stabilization
  // 1.1 Stabilized width (min 220dp, max 260dp, center horizontal)
  assert.ok(
    code.includes('setMinimumWidth(AndroidUtilities.dp(220))'),
    'v3.5.1: bubble layout must have minimumWidth of 220dp'
  );
  assert.ok(
    code.includes('setMaxWidth(AndroidUtilities.dp(260))'),
    'v3.5.1: bubble text must have maxWidth of 260dp'
  );
  assert.ok(
    code.includes('Gravity.CENTER_HORIZONTAL'),
    'v3.5.1: text alignment inside bubble must be Gravity.CENTER_HORIZONTAL'
  );

  // 1.2 Persistent background (never hide bubble on instrumental break during playback)
  assert.ok(
    code.includes('♪ ♪ ♪'),
    'v3.5.1: bubble must show instrumental indicator ♪ ♪ ♪ without hiding bubble'
  );
  assert.ok(
    code.includes('is_karaoke_active') && code.includes('not is_karaoke_active:'),
    'v3.5.1: _update_bubble must keep bubble visible while karaoke is active'
  );

  // 1.3 Smooth text transition (Cross-fade & Slide-up 6dp in 150ms)
  assert.ok(
    code.includes('_animate_text_change') && code.includes('AndroidUtilities.dp(6)'),
    'v3.5.1: text change must use 6dp vertical translation'
  );
  assert.ok(
    code.includes('setDuration(150)'),
    'v3.5.1: text animation duration must be 150ms'
  );

  // 1.4 Fixed height in two lines
  assert.ok(
    code.includes('setAlpha(0.45)') || code.includes('target_alpha=0.45'),
    'v3.5.1: second line must have 45% alpha'
  );

  // BLOCK 2: LyricsHelper Stability & Deadlock Fix
  // 2.1 finally block for discard(key)
  assert.ok(
    /finally:\s+with self\.lock:\s+self\.loading\.discard\(key\)/.test(code),
    'v3.5.2: LyricsHelper must discard loading key in finally: block'
  );

  // 2.2 Prohibition of caching empty failures
  assert.ok(
    code.includes('if timeline:') && code.includes('self.cache[key] = timeline'),
    'v3.5.2: empty failure timeline must NOT be cached in self.cache[key]'
  );

  // 2.3 Soft Auto-Retry
  assert.ok(
    code.includes('_lyrics_retry_count < 3') && code.includes('_last_lyrics_retry'),
    'v3.5.2: must auto-retry lyrics fetch up to 3 times for active tracks'
  );

  // BLOCK 3: Daily Single-Stream Logging
  // 3.1 Removal of log level selector
  assert.ok(
    !code.includes('key="log_level"'),
    'v3.5.3: log_level selector must be removed from settings menu'
  );

  // 3.2 Daily files ClaudePet_YYYY-MM-DD.txt
  assert.ok(
    code.includes('ClaudePet_{day_str}.txt') || code.includes('ClaudePet_%Y-%m-%d'),
    'v3.5.3: log files must be named ClaudePet_YYYY-MM-DD.txt'
  );

  // 3.3 Detailed HTTP context in _req
  assert.ok(
    code.includes('HTTP {status} len=') && code.includes('LYRICS_NET'),
    'v3.5.3: _req must log detailed HTTP status code, URL, and body length'
  );
});
