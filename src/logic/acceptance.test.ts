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
    code.includes('self._anchor_mono <= 0.0') && code.includes('resumed'),
    '1.2: Missing anchor reset condition on resumed == True'
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
    code.includes('postDelayed(self._karaoke_switch_r, 100)') || code.includes('postDelayed(self._karaoke_switch_r, 120)'),
    '3.4.1.1: Missing reschedule (100ms/120ms) when state is not idle/walk'
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

  // 1.3 Отказоустойчивый чекер строк в _step() раз в 100 мс
  assert.ok(
    code.includes('_last_failsafe_check') && code.includes('0.10'),
    '1.3: Отказоустойчивый чекер строк в _step должен проверять позицию раз в 100 мс'
  );

  // 1.4 Tap-to-Sync и сдвиг времени _user_offset
  assert.ok(
    code.includes('📋') && code.includes('t_line - t_calc_raw') && code.includes('_session_offsets'),
    '1.4: Кнопка 📋, расчет _user_offset и сохранение в _session_offsets'
  );

  // 1.5 Инструментальные паузы и 100 мс повтор при прыжке/тапе
  assert.ok(
    code.includes('postDelayed(self._karaoke_switch_r, 100)'),
    '1.5: Повтор вызова караоке при прыжке/тапе строго через 100 мс'
  );

  // 1.6 LyricsHelper stability
  assert.ok(
    /finally:\s+with self\.lock:\s+self\.loading\.discard\(key\)/.test(code),
    '1.6: Снятие loading.discard строго в блоке finally'
  );
  assert.ok(
    code.includes('if timeline:') && code.includes('self.cache[key] = timeline'),
    '1.6: Запрещено сохранять пустые результаты в self.cache'
  );

  // РАЗДЕЛ 2: Разделение UI облачка: речь vs караоке
  assert.ok(
    code.includes('self._bubble.setMinimumWidth(0)'),
    '2.1: В _say() минимальная ширина сбрасывается в 0'
  );
  assert.ok(
    code.includes('self._bubble.setMinimumWidth(AndroidUtilities.dp(210.0 * s))') ||
    code.includes('self._bubble.setMinimumWidth(AndroidUtilities.dp(210))'),
    '2.2: В _show_karaoke_line минимальная ширина фиксируется на 210dp (с поддержкой bubble_scale)'
  );
  assert.ok(
    code.includes('setMaxWidth(AndroidUtilities.dp(260.0 * s))') ||
    code.includes('setMaxWidth(AndroidUtilities.dp(260))'),
    '2.2: Максимальная ширина текста 260dp (с поддержкой bubble_scale)'
  );
  assert.ok(
    code.includes('Gravity.CENTER_HORIZONTAL'),
    '2.2: Выравнивание текста строго по центру Gravity.CENTER_HORIZONTAL'
  );
  assert.ok(
    code.includes('AndroidUtilities.dp(5)'),
    '2.3: Анимация сдвига строки строго 5dp'
  );

  // РАЗДЕЛ 3: Суточное логирование
  assert.ok(
    code.includes('ClaudePet_{day_str}.txt'),
    '3.1: Лог пишется в посуточный файл ClaudePet_YYYY-MM-DD.txt'
  );
  assert.ok(
    !code.includes('key="log_level"'),
    '3.2: Селектор уровня логирования удален'
  );

  // РАЗДЕЛ 4: Оптимизация производительности
  assert.ok(
    code.includes('Bitmap.createBitmap(jarray(jint)(pixel_array), GRID_W, GRID_H'),
    '4.1: Рендеринг кадра спрайта выполняется пакетной передачей массива пикселей'
  );
  assert.ok(
    code.includes('_dp_cache') && code.includes('self._dp_cache.get(value)'),
    '4.2: Метод _dp() мемоизирует результаты в _dp_cache'
  );
  assert.ok(
    code.includes('0.50') && code.includes('_last_platforms_scan_time'),
    '4.3: Время жизни кэша платформ 500 мс с заморозкой в idle/sleep'
  );
});

test('Clawd Bridge v2.0: clean pet background, singing mouth toggle, 3-color gradients, SSE and monotonic anti-drift', () => {
  const filePath = path.resolve(process.cwd(), 'public/clawd_v3_4.py');
  const code = fs.readFileSync(filePath, 'utf-8');

  // 1. Pet visual: NO aura oval + singing_mouth_enabled toggle defaulting to False
  assert.ok(
    !code.includes('_aura_view') && !code.includes('GradientDrawable.OVAL') || (code.includes('GradientDrawable.OVAL') && !code.includes('_aura_view')),
    '1.1: Blue aura view around pet must be completely removed'
  );
  assert.ok(!code.includes('_aura_view'), '1.1: _aura_view must not exist');
  assert.ok(
    code.includes('key="singing_mouth_enabled"') &&
    code.includes('default=False') &&
    code.includes('self._cfg.get("singing_mouth_enabled", False)'),
    '1.2: singing_mouth_enabled toggle with default False must gate mouth animation'
  );

  // 2. 3-color gradient border & background + artwork fetch condition
  assert.ok(
    code.includes('accent_colors') &&
    code.includes('derive_palette_3') &&
    code.includes('LayerDrawable') &&
    code.includes('GradientDrawable.Orientation.TL_BR') &&
    code.includes('_step_gradient_anim'),
    '2.1: Smooth 3-color gradient border and background via LayerDrawable + animation required'
  );
  assert.ok(
    code.includes('http://127.0.0.1:44444/artwork') &&
    code.includes('has_artwork') &&
    code.includes('_artwork_last_has_flag') &&
    code.includes('BitmapFactory.decodeByteArray'),
    '2.2: /artwork fetch on track change or has_artwork False->True required'
  );

  // 3. SSE >= 25s timeout, 1-2s reconnect, fallback polling 1.5-2.0s only when SSE disconnected
  assert.ok(
    code.includes('http://127.0.0.1:44444/events') &&
    code.includes('text/event-stream') &&
    code.includes('timeout=28.0') &&
    code.includes('line.startswith(":")') &&
    code.includes('not self._bridge_sse_connected'),
    '3.1: SSE /events with >=25s timeout, keepalive ignore, and polling disabled while SSE connected required'
  );
  assert.ok(
    code.includes('http://127.0.0.1:44444/now-playing') &&
    code.includes('_bridge_poll_once') &&
    code.includes('wait(1.6)'),
    '3.2: Fallback polling /now-playing at 1.5-2.0s interval required'
  );

  // 4. Monotonic anchor math, no +0.22 hack, 3-tier anti-drift, live anchor after LRC fetch
  assert.ok(
    !code.includes('+ 0.22'),
    '4.1: Legacy +0.22s offset hack must be removed'
  );
  assert.ok(
    code.includes('_anchor_pos_ms') &&
    code.includes('_anchor_mono') &&
    code.includes('_anchor_speed') &&
    code.includes('* 1000.0 * self._anchor_speed') &&
    code.includes('abs(delta) >= 180.0') &&
    code.includes('abs(delta) > 50.0') &&
    code.includes('_apply_fresh_bridge_anchor_and_jump') &&
    code.includes('_clear_playback_anchors'),
    '4.2: Monotonic anchor extrapolation, 3-tier anti-drift (>=180ms / >50ms), post-LRC live re-anchoring, and clean reset required'
  );
});

test('Clawd Bridge v2.1: Telegram artwork/accents, animated gradient toggle, DM scope toggle, lag fixes, rational headphones, bubble_scale 0.4x-2.0x', () => {
  const filePath = path.resolve(process.cwd(), 'public/clawd_v3_4.py');
  const code = fs.readFileSync(filePath, 'utf-8');

  // 1. Telegram playback enriched with Bridge artwork, accent colors & SSE timing via _bridge_matches
  assert.ok(
    code.includes('def _bridge_matches(self, snap, tg_a: str, tg_t: str)') &&
    code.includes('if self._bridge_matches(bridge_snapshot, track_artist or "", track_title or "")') &&
    code.includes('if self._bridge_matches(bridge_snapshot, track_artist, track_title)'),
    '1. Telegram playing/paused must merge artwork, accent_colors & SSE position from matching Clawd Bridge'
  );

  // 2. Animated rotating gradient border toggle (default True)
  assert.ok(
    code.includes('key="animated_gradient_border"') &&
    code.includes('default=True') &&
    code.includes('def _rotate_palette(') &&
    code.includes('border_pal = self._rotate_palette(cur, now)'),
    '2. animated_gradient_border toggle (default True) and _rotate_palette circular animation required'
  );

  // 3. DM vs Group chat scope toggle (default 0: DMs only)
  assert.ok(
    code.includes('TG_CHAT_SCOPE_ITEMS') &&
    code.includes('key="tg_chat_scope"') &&
    code.includes('default=0') &&
    code.includes('if scope == 0 and dialog_id <= 0:'),
    '3. tg_chat_scope selector defaulting to 0 (DMs only, ignoring group dialog_id <= 0) required'
  );

  // 4. Lyric lag reduction: 850ms non-Bridge seek threshold, math.ceil + 8ms wakeup padding, 65ms/85ms anim, failsafe seek-back
  assert.ok(
    code.includes('abs(delta) >= 850.0') &&
    code.includes('math.ceil(((wake_at - t_karaoke) / speed) * 1000.0)) + 8') &&
    code.includes('setDuration(65)') &&
    code.includes('setDuration(85)') &&
    code.includes('elif self._current_lyric_idx >= 0:'),
    '4. Remaining lyric lag fixes (850ms TG threshold, ceil+8ms wakeup, 65/85ms text anim, failsafe <0 index) required'
  );

  // 5. Rational connected headphones (no air gap, cached with music_phones, avoids clobbering full hats)
  assert.ok(
    code.includes('music_phones = bool(self._media == "music" and self._track_is_playing and state != "sleep")') &&
    code.includes('if "Наушники DJ" in hat or (music_phones and ("Без шапки" in hat or "Очки Thug" in hat)):') &&
    code.includes('px(left + 1, top - 1, right - 1, top, band_c)'),
    '5. Connected headphone headband at top-1, music_phones cache key, and hat-preserving condition required'
  );

  // 6. Configurable text frame scale 0.4x - 2.0x
  assert.ok(
    code.includes('def _bubble_scale(self) -> float:') &&
    code.includes('clamp(float(self._cfg.get("bubble_scale", 1.0) or 1.0), 0.4, 2.0)') &&
    code.includes('def _open_bubble_scale_dialog(self):') &&
    code.includes('seek.setMax(32)'),
    '6. bubble_scale 0.4x-2.0x dialog and geometry scaling required'
  );
});

