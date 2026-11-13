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
    (code.includes('drift > 1.2') || code.includes('drift > 0.25')) && code.includes('self._track_base_time == 0.0 or resumed'),
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

  // РАЗДЕЛ 1: Караоке-тайминги, устранение джиттера и синхронизация
  // 1.1 Порог джиттера drift > 1.2 с
  assert.ok(
    code.includes('drift > 1.2'),
    '1.1: Дрейф времени должен проверяться по порогу drift > 1.2'
  );

  // 1.2 Компенсация задержки моста Δ_comp = 0.22 с
  assert.ok(
    code.includes('(track_position_ms / 1000.0) + 0.22'),
    '1.2: Должна прибавляться компенсация задержки моста +0.22с'
  );

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
  // 2.1 Изоляция стилей обычной речи (_say: setMinimumWidth(0) и WRAP_CONTENT)
  assert.ok(
    code.includes('self._bubble.setMinimumWidth(0)'),
    '2.1: В _say() минимальная ширина сбрасывается в 0'
  );

  // 2.2 Стабилизация караоке-виджета (_show_karaoke_line: 210dp-260dp, center)
  assert.ok(
    code.includes('self._bubble.setMinimumWidth(AndroidUtilities.dp(210))'),
    '2.2: В _show_karaoke_line минимальная ширина фиксируется на 210dp'
  );
  assert.ok(
    code.includes('setMaxWidth(AndroidUtilities.dp(260))'),
    '2.2: Максимальная ширина текста 260dp'
  );
  assert.ok(
    code.includes('Gravity.CENTER_HORIZONTAL'),
    '2.2: Выравнивание текста строго по центру Gravity.CENTER_HORIZONTAL'
  );

  // 2.3 Бесшовная смена строк (5dp смещение за 150мс)
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
  // 4.1 Пакетная заливка пикселей спрайта
  assert.ok(
    code.includes('Bitmap.createBitmap(jarray(jint)(pixel_array), GRID_W, GRID_H'),
    '4.1: Рендеринг кадра спрайта выполняется пакетной передачей массива пикселей'
  );

  // 4.2 Мемоизация и кэширование _dp
  assert.ok(
    code.includes('_dp_cache') && code.includes('self._dp_cache.get(value)'),
    '4.2: Метод _dp() мемоизирует результаты в _dp_cache'
  );

  // 4.3 Ленивое сканирование платформ (500 мс кэш)
  assert.ok(
    code.includes('0.50') && code.includes('_last_platforms_scan_time'),
    '4.3: Время жизни кэша платформ 500 мс с заморозкой в idle/sleep'
  );
});

test('Clawd Bridge SSE, playback_speed, artwork and accent_color support', () => {
  const filePath = path.resolve(process.cwd(), 'public/clawd_v3_4.py');
  const code = fs.readFileSync(filePath, 'utf-8');

  assert.ok(
    code.includes('http://127.0.0.1:44444/events') &&
    code.includes('text/event-stream') &&
    code.includes('line.startswith(":")'),
    'SSE: /events stream with keepalive comment ignoring required'
  );
  assert.ok(
    code.includes('http://127.0.0.1:44444/now-playing') &&
    code.includes('_bridge_poll_once'),
    'SSE: Fallback polling to /now-playing required'
  );
  assert.ok(
    code.includes('playback_speed') &&
    code.includes('_received_mono') &&
    code.includes('* self._playback_speed'),
    'Playback speed extrapolation with local receive timestamp required'
  );
  assert.ok(
    code.includes('http://127.0.0.1:44444/artwork') &&
    code.includes('has_artwork') &&
    code.includes('BitmapFactory.decodeByteArray'),
    'Artwork: /artwork fetch on track change when has_artwork is true'
  );
  assert.ok(
    code.includes('accent_color') &&
    code.includes('parse_hex_color') &&
    code.includes('_aura_view'),
    'Accent color: #RRGGBB parsing and UI/aura highlighting required'
  );
});

