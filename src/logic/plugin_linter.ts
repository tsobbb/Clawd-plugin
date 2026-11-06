export interface LintRuleResult {
  id: string;
  title: string;
  passed: boolean;
  details: string;
  severity: 'critical' | 'warning' | 'info';
}

export interface LintReport {
  overallPassed: boolean;
  score: number; // 0-100
  forbiddenStringsCount: number;
  rules: LintRuleResult[];
}

export const FORBIDDEN_STRINGS = ['lastfm', 'Last.fm', 'Pano', 'RetroAudio'] as const;

export function lintClawdPluginCode(code: string): LintReport {
  const rules: LintRuleResult[] = [];
  const lowerCode = code.toLowerCase();

  // 1. Check for Forbidden Strings (Strict Case-Insensitive)
  let forbiddenFound = 0;
  const forbiddenMatches: string[] = [];

  for (const str of FORBIDDEN_STRINGS) {
    const regex = new RegExp(str.replace('.', '\\.'), 'gi');
    const matches = code.match(regex);
    if (matches && matches.length > 0) {
      forbiddenFound += matches.length;
      forbiddenMatches.push(`${str} (${matches.length}x)`);
    }
  }

  rules.push({
    id: 'forbidden_strings',
    title: 'Полный демонтаж устаревших подсистем (Запретные строки)',
    passed: forbiddenFound === 0,
    details:
      forbiddenFound === 0
        ? 'Строки lastfm, Last.fm, Pano, RetroAudio полностью отсутствуют.'
        : `Обнаружены запретные строки: ${forbiddenMatches.join(', ')}`,
    severity: 'critical',
  });

  // 2. Version 3.4 Invariant
  const hasV34 = /__version__\s*=\s*["']3\.4["']/.test(code);
  rules.push({
    id: 'version_3_4',
    title: 'Версия плагина Clawd v3.4',
    passed: hasV34,
    details: hasV34
      ? '__version__ = "3.4" установлен.'
      : 'Требуется установить __version__ = "3.4"',
    severity: 'critical',
  });

  // 3. Complete Audio Engine Removal
  const hasAudioImports = /AudioTrack|AudioFormat|audio_sfx/.test(code);
  rules.push({
    id: 'audio_engine_removed',
    title: 'Звуковой движок вырезан на 100%',
    passed: !hasAudioImports && !code.includes('RetroAudio'),
    details: !hasAudioImports
      ? 'AudioTrack, AudioFormat, audio_sfx и вызовы звуков полностью удалены.'
      : 'Обнаружены остаточные ссылки на аудио (AudioTrack/AudioFormat/audio_sfx).',
    severity: 'critical',
  });

  // 4. Clawd Bridge Gateway & Stepped Backoff (350-400ms & 3.0s)
  const hasBridgeUrl = /127\.0\.0\.1:44444\/now-playing/.test(code);
  const hasBackoff = /3\.0/.test(code) && (code.includes('350') || code.includes('380') || code.includes('400'));
  rules.push({
    id: 'bridge_gateway',
    title: 'Сетевой шлюз Clawd Bridge с Backoff',
    passed: hasBridgeUrl && hasBackoff,
    details:
      hasBridgeUrl && hasBackoff
        ? 'Шлюз http://127.0.0.1:44444/now-playing и ступенчатый backoff на 3.0с реализованы.'
        : 'Отсутствует шлюз 127.0.0.1:44444 или backoff 3.0 сек.',
    severity: 'critical',
  });

  // 5. Jitter Filter (0.25s) & user_offset
  const hasJitter = /0\.25/.test(code) && code.includes('_user_offset') && code.includes('_track_base_pos');
  rules.push({
    id: 'jitter_filter',
    title: 'Джиттер-фильтр (0.25 с) и расчет смещения',
    passed: hasJitter,
    details: hasJitter
      ? 'Фильтр джиттера 0.25с и формулы T_calc, T_karaoke реализованы.'
      : 'Не найден порог джиттера 0.25с или сохранение _user_offset.',
    severity: 'critical',
  });

  // 6. Tap-to-Sync dialog [📋]
  const hasTapToSync = (code.includes('📋') || code.includes('\\U0001f4cb')) && code.includes('_calc_raw');
  rules.push({
    id: 'tap_to_sync',
    title: 'Механика Tap-to-Sync [📋] с выбором строки',
    passed: hasTapToSync,
    details: hasTapToSync
      ? 'Диалог со строками [мм:сс] и калибровка _user_offset = T_line - T_calc_raw присутствуют.'
      : 'Кнопка [📋] или расчет калибровки строк не найдены.',
    severity: 'critical',
  });

  // 7. Safe Eating with WeakReference & RecyclerView attach proxy
  const hasWeakRef = /WeakReference/.test(code);
  const hasAttachListener = /OnChildAttachStateChangeListener/.test(code);
  rules.push({
    id: 'eating_safety',
    title: '«Абсолютный Обжора» 2.0 (WeakReference & RecyclerView Safety)',
    passed: hasWeakRef && hasAttachListener,
    details:
      hasWeakRef && hasAttachListener
        ? 'WeakReference и OnChildAttachStateChangeListener защищают память и чат.'
        : 'Требуется WeakReference и OnChildAttachStateChangeListener для ячеек RecyclerView.',
    severity: 'critical',
  });

  // 8. Rotating Logs 512 KB & collections.deque(maxlen=500)
  const hasLogRotation = /512\s*\*\s*1024|524288/.test(code) && /maxlen=500/.test(code);
  rules.push({
    id: 'logging_rotation',
    title: 'Логирование, кольцевой буфер (500) и ротация 512 КБ',
    passed: hasLogRotation,
    details: hasLogRotation
      ? 'Кольцевой буфер maxlen=500 и лимит ротации 512 КБ активны.'
      : 'Проверьте deque(maxlen=500) и лимит файлов 512 КБ.',
    severity: 'critical',
  });

  // 9. Ukrainian Keywords & Thanks category
  const hasThanks = /thanks|дякую|спасибі/i.test(code);
  const hasUaKeywords = /привіт|вітаю|бувай|кохаю|гроші|друкує/i.test(code);
  rules.push({
    id: 'localization',
    title: 'Локализация (thanks, UA-ключевые слова и «друкує»)',
    passed: hasThanks && hasUaKeywords,
    details:
      hasThanks && hasUaKeywords
        ? 'Категория thanks, украинские ключевые слова и статус «друкує» интегрированы.'
        : 'Отсутствуют ключевые слова благодаря/UA/друкує.',
    severity: 'critical',
  });

  // 10. Decoupled karaoke line switching (postDelayed)
  const hasDecoupled = /postDelayed/.test(code) && (code.includes('T_next_line') || code.includes('t_next') || code.includes('_schedule_karaoke'));
  rules.push({
    id: 'decoupled_karaoke',
    title: 'Декуплинг переключения строк (не удерживает тик 16 мс)',
    passed: hasDecoupled,
    details: hasDecoupled
      ? 'Переключение строк отвязано от UI-тика через Handler.postDelayed.'
      : 'Караоке тайминг должен быть отвязан от _step() через postDelayed.',
    severity: 'critical',
  });

  const passedCount = rules.filter((r) => r.passed).length;
  const overallPassed = rules.every((r) => r.passed);
  const score = Math.round((passedCount / rules.length) * 100);

  return {
    overallPassed,
    score,
    forbiddenStringsCount: forbiddenFound,
    rules,
  };
}
