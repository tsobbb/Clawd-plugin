import React, { useState, useEffect, useRef } from 'react';
import {
  Sparkles,
  RefreshCw,
  Eye,
  Sliders,
  Send,
  Music,
  Smile,
  CheckCheck,
  Zap,
  RotateCcw,
  Target,
  ListOrdered,
  X,
  Clock,
  Heart,
} from 'lucide-react';
import { PixelPetCanvas } from './PixelPetCanvas';
import { HatType, ExpressionType, EatenItem, LyricLine } from '../types/clawd';
import { calibrateTapToSync, calculateTrackPositions, JitterFilterState } from '../logic/clawd_bridge_engine';

interface TelegramChatSimulatorProps {
  paletteId: number;
  hat: HatType;
  karaokeEnabled: boolean;
  autoReturnSeconds: number;
  bridgeTrack: {
    artist: string;
    title: string;
    isPlaying: boolean;
    positionMs: number;
    durationMs: number;
    positionKnown: boolean;
  };
  onLogAdd: (level: string, tag: string, message: string) => void;
}

const SAMPLE_LYRICS: LyricLine[] = [
  { timeSec: 0.0, text: "♪ [Интро - тяжёлый бас]" },
  { timeSec: 4.5, text: "Я снова здесь, пиксели горят огнём" },
  { timeSec: 8.2, text: "Смотри в экран, мы этот чат взорвём" },
  { timeSec: 12.0, text: "Andy Warhol в моих глазах, чистый стиль" },
  { timeSec: 16.5, text: "Синхронизация по биту, поднимаем пыль" },
  { timeSec: 21.0, text: "Никаких задержек, Clawd Bridge на волне" },
  { timeSec: 25.5, text: "Джиттер-фильтр держит базу на нуле" },
  { timeSec: 30.0, text: "♪ [Дроп бита / соло питомца]" },
  { timeSec: 35.0, text: "Полнота растёт, но танцевать легко" },
  { timeSec: 40.0, text: "Мы летим над чатом высоко-высоко" },
];

export const TelegramChatSimulator: React.FC<TelegramChatSimulatorProps> = ({
  paletteId,
  hat,
  karaokeEnabled,
  autoReturnSeconds,
  bridgeTrack,
  onLogAdd,
}) => {
  // Pet position and animation state
  const [petX, setPetX] = useState<number>(240);
  const [petY, setPetY] = useState<number>(340);
  const [expression, setExpression] = useState<ExpressionType>('open');
  const [arms, setArms] = useState<'normal' | 'up' | 'wave1' | 'wave2' | 'tuck'>('normal');
  const [legs, setLegs] = useState<'stand' | 'walk1' | 'walk2' | 'dangle' | 'tuck'>('stand');
  const [mouth, setMouth] = useState<'open' | 'chew' | null>(null);
  const [look, setLook] = useState<number>(0);
  const [squash, setSquash] = useState<number>(0);

  // Stomach & Eaten UI
  const [eatenItems, setEatenItems] = useState<EatenItem[]>([]);
  const [autoReturnCountdown, setAutoReturnCountdown] = useState<number | null>(null);

  // Bubble speech
  const [bubbleText, setBubbleText] = useState<string>('Привет! Я Clawd v3.4 🐾');
  const [bubbleSubtext, setBubbleSubtext] = useState<string>('');
  const [bubbleVisible, setBubbleVisible] = useState<boolean>(true);

  // Particles
  const [particles, setParticles] = useState<Array<{ id: number; kind: 'heart' | 'spark' | 'note'; x: number; y: number }>>([]);

  // Tap-to-Sync modal
  const [tapToSyncOpen, setTapToSyncOpen] = useState<boolean>(false);
  const [userOffset, setUserOffset] = useState<number>(0.0);
  const [lastCalibrationNotice, setLastCalibrationNotice] = useState<string | null>(null);

  // Laser Pointer tool
  const [laserActive, setLaserActive] = useState<boolean>(false);
  const [laserPos, setLaserPos] = useState<{ x: number; y: number } | null>(null);

  // Telegram chat state
  const [isSavedMessages, setIsSavedMessages] = useState<boolean>(false);
  const [inputVal, setInputVal] = useState<string>('');
  const [messages, setMessages] = useState<Array<{ id: number; text: string; isOut: boolean; time: string }>>([
    { id: 1, text: 'Привет! Как там обновление Clawd v3.4?', isOut: false, time: '12:40' },
    { id: 2, text: 'Звуки вырезали, теперь только чистый Clawd Bridge и караоке!', isOut: true, time: '12:41' },
    { id: 3, text: 'Попробуй скормить ему поле ввода или кнопку!', isOut: false, time: '12:42' },
  ]);

  // Jitter filter state ref
  const filterStateRef = useRef<JitterFilterState>({
    trackBasePos: bridgeTrack.positionMs / 1000.0,
    trackBaseTime: Date.now() / 1000.0,
    userOffset: 0.0,
    isPlaying: bridgeTrack.isPlaying,
  });

  // Keep filter state synced
  useEffect(() => {
    filterStateRef.current.userOffset = userOffset;
  }, [userOffset]);

  // Audio / Karaoke decoupled loop simulation
  useEffect(() => {
    if (!karaokeEnabled || !bridgeTrack.isPlaying) {
      return;
    }

    const interval = setInterval(() => {
      const now = Date.now() / 1000.0;
      const { tKaraoke } = calculateTrackPositions(filterStateRef.current, now);

      if (!bridgeTrack.positionKnown) {
        setBubbleText('Синхронизация недоступна');
        setBubbleSubtext('Питомец танцует под ритм');
        setBubbleVisible(true);
        setMouth(null);
        return;
      }

      // Find current lyric line
      let curIdx = -1;
      for (let i = 0; i < SAMPLE_LYRICS.length; i++) {
        if (SAMPLE_LYRICS[i].timeSec <= tKaraoke) {
          curIdx = i;
        } else {
          break;
        }
      }

      if (curIdx >= 0) {
        const curLine = SAMPLE_LYRICS[curIdx];
        const nextLine = curIdx + 1 < SAMPLE_LYRICS.length ? SAMPLE_LYRICS[curIdx + 1] : null;
        setBubbleText(curLine.text);
        setBubbleSubtext(nextLine ? `Далее: ${nextLine.text}` : '');
        setBubbleVisible(true);
        setMouth((prev) => (prev === 'open' ? 'chew' : 'open'));
      }
    }, 250);

    return () => clearInterval(interval);
  }, [karaokeEnabled, bridgeTrack.isPlaying, bridgeTrack.positionKnown]);

  // Dance beat simulation (30 fps animation rate for music)
  useEffect(() => {
    if (!bridgeTrack.isPlaying) {
      setArms('normal');
      setLegs('stand');
      setMouth(null);
      return;
    }

    const timer = setInterval(() => {
      setArms((a) => (a === 'wave1' ? 'wave2' : 'wave1'));
      setLegs((l) => (l === 'walk1' ? 'walk2' : 'walk1'));
      setSquash((s) => (s === 1 ? 0 : 1));
      if (Math.random() < 0.25) {
        spawnParticle('note', petX + 25, petY - 10);
      }
    }, 450);

    return () => clearInterval(timer);
  }, [bridgeTrack.isPlaying, petX, petY]);

  // Auto-return countdown timer
  useEffect(() => {
    if (eatenItems.length === 0) {
      setAutoReturnCountdown(null);
      return;
    }

    setAutoReturnCountdown(autoReturnSeconds);
    const interval = setInterval(() => {
      setAutoReturnCountdown((prev) => {
        if (prev === null || prev <= 1) {
          clearInterval(interval);
          spitAll('Таймер автовозврата истёк: всё съеденное вернулось на экран!');
          return null;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [eatenItems.length, autoReturnSeconds]);

  const spawnParticle = (kind: 'heart' | 'spark' | 'note', x: number, y: number) => {
    const id = Date.now() + Math.random();
    setParticles((prev) => [...prev.slice(-10), { id, kind, x, y }]);
    setTimeout(() => {
      setParticles((prev) => prev.filter((p) => p.id !== id));
    }, 1200);
  };

  // 3. «Абсолютный Обжора» 2.0: поедание элементов
  const eatTarget = (targetType: EatenItem['type'], name: string) => {
    if (eatenItems.length >= 12) {
      // 13-й выплёвывает самый старый
      const oldest = eatenItems[0];
      setEatenItems((prev) => prev.slice(1));
      onLogAdd('INFO', 'OBZHORA', `Лимит желудка (12) превышен! Старейший элемент '${oldest.name}' выплюнут`);
    }

    const newItem: EatenItem = {
      id: `elem_${Date.now()}`,
      name,
      type: targetType,
      originalAlpha: 1.0,
      w: 80,
      h: 36,
      timestamp: Date.now(),
    };

    setEatenItems((prev) => [...prev, newItem]);
    setSquash(1);
    setMouth('open');
    setExpression('happy');

    setTimeout(() => {
      setSquash(0);
      setMouth('chew');
    }, 300);

    setTimeout(() => {
      setMouth(null);
    }, 800);

    // Выбор реплики согласно ТЗ Section 3.6
    let phrase = 'Ням! Вкусный кусок UI ✨';
    if (targetType === 'edittext') {
      phrase = 'Съел поле ввода, теперь молчи 🤫';
    } else if (targetType === 'message') {
      phrase = 'Перевариваю чужие сплетни 💌';
    } else if (targetType === 'header') {
      phrase = 'Откусил кусок шапки! Тулбар был аппетитным 🎩';
    } else if (targetType === 'avatar') {
      phrase = 'Съел твою аватарку! 👤 Кругляш на десерт!';
    } else if (eatenItems.length + 1 >= 7) {
      phrase = 'Я ШАР! Я КОЛОБОК! Перекат вместо шага… *ик*';
    } else if (eatenItems.length + 1 >= 4) {
      phrase = 'Ох… кажется, я тяжелею… штаны лопнут!';
    } else if (eatenItems.length + 1 >= 2) {
      phrase = 'Хрум! Вкусновато, но щёчки растут…';
    }

    setBubbleText(phrase);
    setBubbleSubtext(`В желудке: ${eatenItems.length + 1}/12 (Стадия ${getFatStage(eatenItems.length + 1)})`);
    setBubbleVisible(true);

    onLogAdd(
      'INFO',
      'OBZHORA',
      `Clawd съел элемент: '${name}' (type=${targetType}, желудок=${eatenItems.length + 1}/12, WeakRef зарегистрирован)`
    );
  };

  const spitAll = (customReason?: string) => {
    if (eatenItems.length === 0) return;
    setEatenItems([]);
    setSquash(1);
    setExpression('surprised');
    setBubbleText(customReason || 'Ладно, отдаю! Тьфу! Забирай… Я на диете!');
    setBubbleSubtext('Все элементы возвращены с гарантией RecyclerView');
    setBubbleVisible(true);

    spawnParticle('spark', petX + 25, petY - 10);
    spawnParticle('spark', petX + 10, petY - 5);

    setTimeout(() => {
      setSquash(0);
      setExpression('happy');
    }, 400);

    onLogAdd('INFO', 'OBZHORA', 'Выплюнуто всё содержимое желудка. Элементы возвращены в исходное состояние');
  };

  const getFatStage = (count: number) => {
    if (count <= 1) return 0;
    if (count <= 3) return 1;
    if (count <= 6) return 2;
    return 3;
  };

  const fatStage = getFatStage(eatenItems.length);

  // Тап по питомцу (возвращает всё съеденное или прыгает)
  const handlePetClick = () => {
    if (eatenItems.length > 0) {
      spitAll();
      return;
    }
    // Прыжок
    setSquash(1);
    setExpression('happy');
    setPetY((y) => y - 30);
    setBubbleText('Хоп! Не щекочи! 🐾');
    setBubbleVisible(true);
    spawnParticle('heart', petX + 25, petY - 20);

    setTimeout(() => {
      setPetY((y) => y + 30);
      setSquash(0);
    }, 250);

    onLogAdd('DEBUG', 'PET', 'Тап по питомцу: прыжок');
  };

  // Лазерная указка двумя пальцами / симуляция
  const handleSimulatorAreaClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;

    if (laserActive) {
      setLaserPos({ x: clickX, y: clickY });
      // Clawd бежит к лазеру
      const targetX = Math.max(30, Math.min(360, clickX - 25));
      const targetY = Math.max(80, Math.min(420, clickY - 20));
      setLook(targetX > petX ? 1 : -1);
      setPetX(targetX);
      setPetY(targetY);
      setExpression('surprised');
      setBubbleText('ТОЧКА! ПОЙМАЮ! ОНА ТУТ! 🔴');
      setBubbleVisible(true);
      onLogAdd('DEBUG', 'LASER', `Лазерная указка активна: бег к (${clickX.toFixed(0)}, ${clickY.toFixed(0)})`);
    }
  };

  // Отправка сообщения
  const handleSendMessage = () => {
    if (!inputVal.trim()) return;
    const newMsg = {
      id: Date.now(),
      text: inputVal.trim(),
      isOut: true,
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };
    setMessages((prev) => [...prev, newMsg]);
    setInputVal('');

    // Реакция Clawd в зависимости от чата
    if (isSavedMessages) {
      setBubbleText('Записал в заметки! В копилку мыслей 📓');
      setExpression('happy');
      onLogAdd('INFO', 'TG', 'Исходящее в Избранное: реакция на заметку');
    } else {
      if (newMsg.text.length > 50) {
        setBubbleText('Ого, целое эссе! Лев Толстой в чате 📜');
      } else {
        setBubbleText('Отправлено! Улетело! Хорошо сказано! ✨');
      }
      setExpression('happy');
      onLogAdd('INFO', 'TG', `Исходящее сообщение собеседнику (${newMsg.text.length} симв)`);
    }
    setBubbleVisible(true);
  };

  // Механика Tap-to-Sync выбор строки
  const handleSelectLyricLine = (line: LyricLine, index: number) => {
    const now = Date.now() / 1000.0;
    const newOffset = calibrateTapToSync(filterStateRef.current, line.timeSec, now);
    setUserOffset(newOffset);
    setTapToSyncOpen(false);

    const notice = `Калибровка Tap-to-Sync: строка #${index + 1} (${line.timeSec.toFixed(1)}с) -> _user_offset = ${newOffset >= 0 ? '+' : ''}${newOffset.toFixed(2)}с`;
    setLastCalibrationNotice(notice);
    setBubbleText(line.text);
    setBubbleSubtext(`Смещение трека: ${newOffset.toFixed(2)} с`);
    setBubbleVisible(true);
    spawnParticle('spark', petX + 25, petY - 10);

    onLogAdd('INFO', 'SYNC', notice);
  };

  const isEaten = (type: EatenItem['type']) => eatenItems.some((item) => item.type === type);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      {/* Левая колонка: Мокап Telegram и интерактивный симулятор */}
      <div className="lg:col-span-7 flex flex-col items-center">
        {/* Телефонный фрейм */}
        <div
          onClick={handleSimulatorAreaClick}
          className="relative w-full max-w-[420px] h-[660px] bg-slate-900 rounded-[36px] p-3 shadow-2xl border-4 border-slate-700 select-none overflow-hidden flex flex-col"
        >
          {/* Динамический остров / шапка смартфона */}
          <div className="w-full flex items-center justify-between px-6 pt-1 pb-2 text-[11px] text-slate-400 font-medium">
            <span>12:44</span>
            <div className="w-24 h-4 bg-black rounded-full flex items-center justify-center">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            </div>
            <div className="flex items-center gap-1">
              <span>5G</span>
              <div className="w-5 h-2.5 border border-slate-400 rounded-sm p-0.5 flex items-center">
                <div className="w-full h-full bg-slate-300 rounded-[1px]"></div>
              </div>
            </div>
          </div>

          {/* Telegram Шапка чата (ActionBar) */}
          <div
            className={`transition-all duration-300 rounded-2xl px-4 py-2.5 flex items-center justify-between border ${
              isEaten('header')
                ? 'opacity-10 bg-red-950/20 border-dashed border-red-500/40'
                : 'bg-slate-800/90 backdrop-blur border-slate-700/60 shadow'
            }`}
          >
            <div className="flex items-center gap-3">
              <button
                type="button"
                aria-label="Сменить тип чата"
                onClick={(e) => {
                  e.stopPropagation();
                  setIsSavedMessages((prev) => !prev);
                  onLogAdd('INFO', 'TG', `Смена чата: ${!isSavedMessages ? 'Избранное' : 'Личный диалог'}`);
                }}
                className="text-xs text-sky-400 hover:text-sky-300 font-medium"
              >
                ◀ Назад
              </button>

              {/* Аватарка собеседника */}
              <div
                onClick={(e) => {
                  e.stopPropagation();
                  eatTarget('avatar', 'Аватарка профиля');
                }}
                title="Нажми, чтобы Clawd съел аватарку"
                className={`relative w-9 h-9 rounded-full flex items-center justify-center font-bold text-xs cursor-pointer transition-all ${
                  isEaten('avatar')
                    ? 'opacity-10 scale-75 bg-slate-800'
                    : 'bg-gradient-to-tr from-sky-500 to-indigo-600 text-white shadow-md hover:ring-2 hover:ring-sky-400'
                }`}
              >
                {isSavedMessages ? '⭐' : 'ИВ'}
              </div>

              <div>
                <div className="text-sm font-semibold text-white flex items-center gap-1.5">
                  <span>{isSavedMessages ? 'Избранное' : 'Иван Техлид'}</span>
                  {isSavedMessages && <span className="text-[10px] bg-amber-500/20 text-amber-300 px-1.5 py-0.5 rounded">Заметки</span>}
                </div>
                <div className="text-[11px] text-slate-400 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                  <span>{isSavedMessages ? 'твои личные заметки' : 'друкує... (распознано v3.4)'}</span>
                </div>
              </div>
            </div>

            <button
              type="button"
              aria-label="Съесть шапку приложения"
              onClick={(e) => {
                e.stopPropagation();
                eatTarget('header', 'Шапка тулбара');
              }}
              className="text-[11px] bg-slate-700 hover:bg-slate-600 text-slate-300 px-2 py-1 rounded-lg border border-slate-600"
            >
              🍴 Съесть
            </button>
          </div>

          {/* Область сообщений / RecyclerView */}
          <div className="flex-1 overflow-y-auto px-2 py-3 space-y-3 relative">
            <div className="text-center">
              <span className="text-[10px] bg-slate-800/80 text-slate-400 px-2.5 py-1 rounded-full border border-slate-700">
                Сегодня
              </span>
            </div>

            {messages.map((msg) => (
              <div
                key={msg.id}
                onClick={(e) => {
                  e.stopPropagation();
                  eatTarget('message', `Сообщение #${msg.id}`);
                }}
                className={`flex ${msg.isOut ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[78%] p-3 rounded-2xl text-xs transition-all cursor-pointer shadow-sm ${
                    msg.isOut
                      ? 'bg-sky-600 text-white rounded-br-sm hover:ring-2 hover:ring-sky-300'
                      : 'bg-slate-800 text-slate-200 border border-slate-700 rounded-bl-sm hover:ring-2 hover:ring-slate-400'
                  }`}
                  title="Нажми, чтобы съесть это сообщение"
                >
                  <p>{msg.text}</p>
                  <div className="flex items-center justify-end gap-1 mt-1 text-[10px] text-sky-200/80">
                    <span>{msg.time}</span>
                    {msg.isOut && <CheckCheck className="w-3 h-3" />}
                  </div>
                </div>
              </div>
            ))}

            {/* Симулированные частицы */}
            {particles.map((p) => (
              <div
                key={p.id}
                className="absolute pointer-events-none transition-all duration-1000 -translate-y-12 opacity-0 text-base"
                style={{ left: `${p.x}px`, top: `${p.y}px` }}
              >
                {p.kind === 'heart' && '💖'}
                {p.kind === 'spark' && '✨'}
                {p.kind === 'note' && '🎵'}
              </div>
            ))}

            {/* Точка лазера */}
            {laserActive && laserPos && (
              <div
                className="absolute pointer-events-none w-4 h-4 rounded-full bg-red-500 shadow-[0_0_12px_#ff0000] -translate-x-2 -translate-y-2 animate-ping"
                style={{ left: `${laserPos.x}px`, top: `${laserPos.y}px` }}
              />
            )}

            {/* Питомец Clawd и Речевое облачко с караоке */}
            <div
              className="absolute z-20 transition-all duration-200"
              style={{ left: `${petX}px`, top: `${petY}px` }}
            >
              {/* Речевое облачко / Караоке табло */}
              {bubbleVisible && (
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 bg-slate-950/95 text-white p-2.5 rounded-2xl shadow-xl border border-sky-500/30 text-center pointer-events-auto">
                  <div className="text-[12px] font-bold text-sky-200 leading-snug">
                    {bubbleText}
                  </div>
                  {bubbleSubtext && (
                    <div className="text-[10px] text-slate-400 mt-0.5 truncate">
                      {bubbleSubtext}
                    </div>
                  )}

                  {/* Пульт управления: кнопки [⏮] [⏯] [⏭] и [📋] */}
                  <div className="flex items-center justify-center gap-2 mt-2 pt-1.5 border-t border-slate-800">
                    <button
                      type="button"
                      aria-label="Предыдущий трек"
                      onClick={(e) => {
                        e.stopPropagation();
                        setBubbleText('⏮ Предыдущий трек');
                        onLogAdd('INFO', 'MEDIA', 'Кнопка ⏮: переход назад');
                      }}
                      className="p-1 hover:bg-slate-800 rounded text-slate-300"
                    >
                      ⏮
                    </button>
                    <button
                      type="button"
                      aria-label="Воспроизведение или пауза"
                      onClick={(e) => {
                        e.stopPropagation();
                        setBubbleText(bridgeTrack.isPlaying ? 'Плеер на паузе ⏸' : 'Воспроизведение ▶');
                        onLogAdd('INFO', 'MEDIA', 'Кнопка ⏯: play/pause');
                      }}
                      className="p-1 hover:bg-slate-800 rounded text-sky-400 font-bold"
                    >
                      ⏯
                    </button>
                    <button
                      type="button"
                      aria-label="Следующий трек"
                      onClick={(e) => {
                        e.stopPropagation();
                        setBubbleText('⏭ Следующий трек');
                        onLogAdd('INFO', 'MEDIA', 'Кнопка ⏭: переход вперед');
                      }}
                      className="p-1 hover:bg-slate-800 rounded text-slate-300"
                    >
                      ⏭
                    </button>
                    <button
                      type="button"
                      aria-label="Tap to sync выбор строки"
                      onClick={(e) => {
                        e.stopPropagation();
                        setTapToSyncOpen(true);
                        onLogAdd('INFO', 'SYNC', 'Открыт диалог Tap-to-Sync [📋]');
                      }}
                      title="Выбрать строку трека для мгновенной синхронизации (Tap-to-Sync)"
                      className="px-2 py-0.5 bg-sky-500/20 hover:bg-sky-500/30 text-sky-300 border border-sky-400/30 rounded text-[11px] font-bold flex items-center gap-1"
                    >
                      <span>📋</span>
                      <span className="text-[9px]">Стр</span>
                    </button>
                  </div>
                </div>
              )}

              {/* Холст питомца */}
              <div
                onClick={(e) => {
                  e.stopPropagation();
                  handlePetClick();
                }}
                className="cursor-pointer hover:scale-105 active:scale-95 transition-transform"
                title="Нажми, чтобы погладить или вернуть съеденное!"
              >
                <PixelPetCanvas
                  paletteId={paletteId}
                  hat={hat}
                  fatStage={fatStage}
                  expression={expression}
                  look={look}
                  arms={arms}
                  legs={legs}
                  mouth={mouth}
                  squash={squash}
                  scale={4.2}
                  isDancing={bridgeTrack.isPlaying}
                />
              </div>
            </div>
          </div>

          {/* Нижнее поле ввода Telegram (EditText + Send button) */}
          <div
            className={`p-2 transition-all duration-300 rounded-2xl border ${
              isEaten('edittext')
                ? 'opacity-10 bg-red-950/20 border-dashed border-red-500/40'
                : 'bg-slate-800/90 border-slate-700/60 shadow-lg'
            }`}
          >
            <div className="flex items-center gap-2">
              <button
                type="button"
                aria-label="Смайлики"
                onClick={(e) => {
                  e.stopPropagation();
                  eatTarget('button', 'Кнопка смайлов');
                }}
                className="text-slate-400 hover:text-slate-200 p-1"
                title="Съесть кнопку смайлов"
              >
                <Smile className="w-5 h-5" />
              </button>

              <input
                type="text"
                disabled={isEaten('edittext')}
                placeholder={isEaten('edittext') ? 'Ввод съеден Clawd…' : 'Сообщение…'}
                value={inputVal}
                onChange={(e) => setInputVal(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
                className="flex-1 bg-transparent text-white text-xs outline-none placeholder:text-slate-500"
              />

              <button
                type="button"
                aria-label="Съесть поле ввода"
                onClick={(e) => {
                  e.stopPropagation();
                  eatTarget('edittext', 'Поле ввода EditText');
                }}
                className="text-[10px] bg-slate-700 hover:bg-slate-600 text-slate-300 px-1.5 py-1 rounded"
                title="Съесть поле ввода целиком"
              >
                🍴 Съесть
              </button>

              <button
                type="button"
                aria-label="Отправить сообщение"
                onClick={handleSendMessage}
                disabled={isEaten('edittext')}
                className="w-8 h-8 rounded-full bg-sky-500 hover:bg-sky-400 text-white flex items-center justify-center transition-colors shadow"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Быстрые действия под симулятором */}
        <div className="flex flex-wrap items-center justify-center gap-2 mt-4 max-w-[420px]">
          <button
            type="button"
            onClick={() => {
              setLaserActive((v) => !v);
              onLogAdd('INFO', 'LASER', `Переключение лазера: ${!laserActive}`);
            }}
            className={`px-3 py-1.5 rounded-xl text-xs font-medium border flex items-center gap-1.5 transition-all ${
              laserActive
                ? 'bg-red-500 text-white border-red-400 shadow-md animate-pulse'
                : 'bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700'
            }`}
          >
            <Target className="w-3.5 h-3.5 text-red-400" />
            <span>{laserActive ? 'Лазер ВКЛ (кликни на экран)' : 'Лазерная указка'}</span>
          </button>

          <button
            type="button"
            onClick={() => {
              // Симуляция встряхивания и шар предсказаний 🎱
              setSquash(1);
              setExpression('dizzy');
              const fortunes = [
                '🎱 100% успех!',
                '🎱 Звёзды говорят: отправь стикер',
                '🎱 Ответ спрятан в голосовом',
                '🎱 Определенно да!',
                '🎱 Даже не думай',
              ];
              const f = fortunes[Math.floor(Math.random() * fortunes.length)];
              setBubbleText(f);
              setBubbleVisible(true);
              spawnParticle('spark', petX + 25, petY - 10);
              onLogAdd('INFO', 'SHAKE', `Встряхивание: оракул 🎱 выдал ответ: ${f}`);
              setTimeout(() => setSquash(0), 400);
            }}
            className="px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-800 text-slate-300 border border-slate-700 hover:bg-slate-700 flex items-center gap-1.5"
          >
            <span>🎱</span>
            <span>Шар предсказаний</span>
          </button>

          <button
            type="button"
            onClick={() => {
              // Имитация скролла RecyclerView (OnChildAttachStateChangeListener)
              onLogAdd('INFO', 'RECYCLER', 'Скролл чата: проверка OnChildAttachStateChangeListener, восстанавливаем alpha');
              setBubbleText('Скролл чата: ячейки не пропадают! ✔');
              setBubbleVisible(true);
            }}
            className="px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-800 text-slate-300 border border-slate-700 hover:bg-slate-700 flex items-center gap-1.5"
          >
            <RotateCcw className="w-3.5 h-3.5 text-indigo-400" />
            <span>Тест скролла чата</span>
          </button>

          <button
            type="button"
            onClick={() => spitAll()}
            disabled={eatenItems.length === 0}
            className="px-3 py-1.5 rounded-xl text-xs font-medium bg-amber-600/20 text-amber-300 border border-amber-500/30 hover:bg-amber-600/30 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5"
          >
            <span>🤮</span>
            <span>Выплюнуть всё ({eatenItems.length})</span>
          </button>
        </div>
      </div>

      {/* Правая колонка: Желудок Обжоры 2.0, Смещение трека и Настройки */}
      <div className="lg:col-span-5 space-y-5">
        {/* Карточка «Абсолютный Обжора 2.0» */}
        <div className="bg-slate-800/80 rounded-2xl p-4 border border-slate-700/80 shadow-lg">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className="text-xl">🍔</span>
              <div>
                <h3 className="text-sm font-bold text-white">«Абсолютный Обжора» 2.0</h3>
                <p className="text-[11px] text-slate-400">Безопасное поедание с WeakReference и лимитом 12</p>
              </div>
            </div>
            <span
              className={`text-[11px] px-2.5 py-0.5 rounded-full font-bold border ${
                fatStage === 0
                  ? 'bg-slate-700 text-slate-300 border-slate-600'
                  : fatStage === 1
                  ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                  : fatStage === 2
                  ? 'bg-orange-500/20 text-orange-300 border-orange-500/40'
                  : 'bg-red-500/20 text-red-300 border-red-500/40 animate-pulse'
              }`}
            >
              Стадия {fatStage}: {['Норма', 'Пухляш', 'Толстяк', 'Колобок!'][fatStage]}
            </span>
          </div>

          {/* Статус автовозврата */}
          <div className="bg-slate-900/60 rounded-xl p-3 border border-slate-800 text-xs mb-3 flex items-center justify-between">
            <div className="flex items-center gap-2 text-slate-300">
              <Clock className="w-4 h-4 text-sky-400" />
              <span>Автовозврат ({autoReturnSeconds}с):</span>
            </div>
            <span className="font-mono font-bold text-sky-400">
              {autoReturnCountdown !== null ? `${autoReturnCountdown} сек` : 'Ожидание'}
            </span>
          </div>

          {/* Содержимое желудка */}
          <div className="space-y-1.5">
            <div className="text-[11px] font-medium text-slate-400 flex items-center justify-between">
              <span>Элементы в желудке ({eatenItems.length} из 12):</span>
              {eatenItems.length > 0 && (
                <button
                  type="button"
                  onClick={() => spitAll()}
                  className="text-sky-400 hover:text-sky-300"
                >
                  Выплюнуть всё
                </button>
              )}
            </div>

            {eatenItems.length === 0 ? (
              <div className="p-4 text-center border border-dashed border-slate-700 rounded-xl text-xs text-slate-500">
                Желудок пуст. Нажмите «🍴 Съесть» в чате или кликните по сообщению/аватарке!
              </div>
            ) : (
              <div className="max-h-44 overflow-y-auto space-y-1 pr-1">
                {eatenItems.map((item, idx) => (
                  <div
                    key={item.id}
                    className="flex items-center justify-between bg-slate-900/80 p-2 rounded-lg border border-slate-800 text-xs"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-slate-500 font-mono text-[10px]">#{idx + 1}</span>
                      <span className="text-slate-200 font-medium">{item.name}</span>
                      <span className="text-[10px] bg-slate-800 text-slate-400 px-1.5 py-0.2 rounded font-mono">
                        WeakRef: OK
                      </span>
                    </div>
                    <span className="text-[10px] text-amber-400/90 font-mono">
                      {item.type}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Карточка Tap-to-Sync и Караоке */}
        <div className="bg-slate-800/80 rounded-2xl p-4 border border-slate-700/80 shadow-lg">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className="text-xl">🎵</span>
              <div>
                <h3 className="text-sm font-bold text-white">Караоке и Синхронизация</h3>
                <p className="text-[11px] text-slate-400">LRCLIB + NetEase + Tap-to-Sync [📋]</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setTapToSyncOpen(true)}
              className="text-xs bg-sky-600 hover:bg-sky-500 text-white font-medium px-3 py-1.5 rounded-xl border border-sky-400/40 flex items-center gap-1.5 shadow"
            >
              <span>📋</span>
              <span>Tap-to-Sync</span>
            </button>
          </div>

          <div className="bg-slate-900/70 p-3 rounded-xl border border-slate-800 space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-slate-400">Текущий трек:</span>
              <span className="font-semibold text-white">
                {bridgeTrack.artist} — {bridgeTrack.title}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-400">Смещение _user_offset:</span>
              <span className="font-mono font-bold text-sky-400">
                {userOffset >= 0 ? `+${userOffset.toFixed(3)}` : userOffset.toFixed(3)} с
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-400">Джиттер-фильтр (0.25 с):</span>
              <span className="text-emerald-400 font-mono">АКТИВЕН (порог 250 мс)</span>
            </div>
          </div>

          {lastCalibrationNotice && (
            <div className="mt-3 p-2 bg-emerald-500/10 border border-emerald-500/30 rounded-lg text-[11px] text-emerald-300">
              {lastCalibrationNotice}
            </div>
          )}
        </div>
      </div>

      {/* Диалог со строками Tap-to-Sync [📋] */}
      {tapToSyncOpen && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 w-full max-w-lg rounded-2xl shadow-2xl p-5 flex flex-col max-h-[85vh]">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <span className="text-xl">📋</span>
                <div>
                  <h3 className="text-base font-bold text-white">Tap-to-Sync: Выбор строки трека</h3>
                  <p className="text-xs text-slate-400">Кликните по строке, которая звучит прямо сейчас</p>
                </div>
              </div>
              <button
                type="button"
                aria-label="Закрыть окно Tap-to-Sync"
                onClick={() => setTapToSyncOpen(false)}
                className="p-1 hover:bg-slate-800 text-slate-400 hover:text-white rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="my-3 p-2.5 bg-sky-950/40 border border-sky-500/30 rounded-xl text-xs text-sky-200">
              <div className="font-semibold">Формула калибровки ТЗ Section 2.3:</div>
              <div className="font-mono text-[11px] text-sky-300 mt-0.5">
                _user_offset = T_line - T_calc_raw
              </div>
            </div>

            <div className="flex-1 overflow-y-auto space-y-1.5 my-2 pr-1">
              {SAMPLE_LYRICS.map((line, idx) => {
                const mm = Math.floor(line.timeSec / 60);
                const ss = Math.floor(line.timeSec % 60);
                const timeLabel = `[${mm.toString().padStart(2, '0')}:${ss.toString().padStart(2, '0')}]`;
                return (
                  <button
                    type="button"
                    key={idx}
                    onClick={() => handleSelectLyricLine(line, idx)}
                    className="w-full text-left p-2.5 rounded-xl bg-slate-800/80 hover:bg-sky-600/30 hover:border-sky-400 border border-slate-700/80 transition-all flex items-center justify-between text-xs group"
                  >
                    <div className="flex items-center gap-2.5">
                      <span className="font-mono text-sky-400 font-bold">{timeLabel}</span>
                      <span className="text-slate-200 group-hover:text-white font-medium">{line.text}</span>
                    </div>
                    <span className="text-[10px] text-slate-500 group-hover:text-sky-300 font-mono">
                      Синхронизировать
                    </span>
                  </button>
                );
              })}
            </div>

            <div className="pt-3 border-t border-slate-800 flex justify-end">
              <button
                type="button"
                onClick={() => setTapToSyncOpen(false)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-xl text-xs font-semibold"
              >
                Закрыть
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
