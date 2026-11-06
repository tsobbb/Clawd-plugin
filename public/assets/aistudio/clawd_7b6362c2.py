import collections
import datetime
import json
import math
import os
import random
import re
import threading
import time
import traceback
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from android.content import ClipData, ClipboardManager, ComponentName, Context, DialogInterface, Intent
from android.graphics import Bitmap, Canvas, Paint
from android.graphics.drawable import GradientDrawable
from android.hardware import Sensor, SensorEventListener, SensorManager
from android.media import AudioFormat, AudioManager, AudioTrack
from android.os import BatteryManager, Environment, Handler, Looper
from android.provider import Settings
from android.util import TypedValue
from android.view import Gravity, KeyEvent, MotionEvent, Surface, SurfaceView, TextureView, View, ViewGroup
from android.view.animation import AccelerateInterpolator, DecelerateInterpolator, OvershootInterpolator
from android.widget import EditText, FrameLayout, ImageView, LinearLayout, ScrollView, TextView
from androidx.recyclerview.widget import RecyclerView
from java import dynamic_proxy, jarray, jbyte, jclass, jint
from org.telegram.messenger import AndroidUtilities, MediaController, MessagesController, NotificationCenter, UserConfig, UserObject
from org.telegram.ui import ChatActivity, LaunchActivity
from org.telegram.ui.ActionBar import AlertDialog, Theme

from android_utils import R, log, run_on_ui_thread
from base_plugin import AppEvent, BasePlugin, HookResult, MenuItemData, MenuItemType
from client_utils import get_last_fragment
from ui.settings import Divider, Header, Selector, Switch, Text

try:
    from org.telegram.ui.Cells import ChatMessageCell
except Exception:
    ChatMessageCell = None

__id__ = "clawd_pet"
__name__ = "Clawd"
__description__ = (
    "Ультимативный интерактивный питомец для Telegram.\n\n"
    "• Синхронное караоке (LRCLIB + NetEase) и SoundCloud oEmbed.\n"
    "• Поддержка внешних плееров через Pano Scrobbler / Last.fm.\n"
    "• Встроенный 8-битный синтезатор звуков без сторонних файлов.\n"
    "• Режим «Абсолютный Обжора»: 4 стадии полноты с выплёвыванием.\n"
    "• Глубокая логика Telegram: разделяет свои заметки и входящие сообщения.\n"
    "• Лазерная указка двумя пальцами, гравитация на всех экранах и 11 шапок."
)
__author__ = "@tsobbb"
__version__ = "3.2"
__icon__ = "clawd_poop_5050_1783593604/0"

GRID_W = 18
GRID_H = 13
SIZE_ITEMS = ["Маленький", "Средний", "Большой"]
SIZE_DP = [3.0, 4.0, 5.0]

PALETTES = [
    ("Claude (Оригинал)", 0xFFD97757, 0xFF1A1A1A),
    ("Claude Dark", 0xFF383838, 0xFFF5F5F5),
    ("Anthropic Spark", 0xFFE06C38, 0xFF1A1A1A),
    ("Мятный", 0xFF4FBF98, 0xFF12241D),
    ("Лавандовый", 0xFF9B8AEE, 0xFF1B1631),
    ("Небесный", 0xFF4FA8E8, 0xFF0E1C29),
    ("Сакура", 0xFFEE85AE, 0xFF2A1220),
    ("Киберпанк Неон", 0xFF00E5FF, 0xFF0A0A14),
    ("Золотой Слиток", 0xFFFFD700, 0xFF3E2723),
    ("Радужный RGB", 0xFF000000, 0xFFFFFFFF),
    ("Хамелеон (Тема)", 0x00000000, 0xFFFFFFFF),
]

HATS = [
    "Без шапки",
    "Наушники DJ",
    "Корона 👑",
    "Шерлок 🔍",
    "Ночной колпак",
    "Кошачьи ушки 🐱",
    "Цилиндр и Монокль 🎩",
    "Каска Сапёра ⛑",
    "Очки Thug Life 😎",
    "Шляпа Мага 🧙‍♂️",
    "Кепка назад",
]

SLEEP_ITEMS = ["Через 1 минуту", "Через 3 минуты", "Через 10 минут", "Никогда"]
SLEEP_SECONDS = [60, 180, 600, 0]

HEART_COLOR = 0xFFFF5C7A
ZZZ_COLOR = 0xFF8FA3BF
SPARK_COLOR = 0xFFFFC94D
NOTE_COLOR = 0xFF6FB8FF
POOP_COLORS = {"X": 0xFF8A5A33, "o": 0xFFB27D4E, "w": 0xFFFFFFFF, "k": 0xFF1A1A1A}
GOLD_POOP_COLORS = {"X": 0xFFD4AF37, "o": 0xFFFFDF73, "w": 0xFFFFFFFF, "k": 0xFF5A4500}

PATTERNS = {
    "heart": (
        ".XX.XX.",
        "XXXXXXX",
        "XXXXXXX",
        ".XXXXX.",
        "..XXX..",
        "...X...",
    ),
    "zzz": (
        "XXXXX",
        "...X.",
        "..X..",
        ".X...",
        "XXXXX",
    ),
    "spark": (
        "..X..",
        "..X..",
        "XX.XX",
        "..X..",
        "..X..",
    ),
    "note": (
        "..XXXXX",
        "..X...X",
        "..X...X",
        "..X...X",
        "XXX.XXX",
        "XXX.XXX",
    ),
    "poop": (
        "....X....",
        "...XXo...",
        "..XXXXX..",
        ".XXXXXXo.",
        ".XwkXwkX.",
        "XXXXXXXXo",
        "XXXXXXXXX",
    ),
}

KEYWORDS = (
    ("love", re.compile(r"❤|♥|💕|💖|😘|😍|🥰|\bлюблю\b|\bобнима\w*|\bцелую\b|\blove\b|\bмилаш\w*")),
    ("laugh", re.compile(r"(?:ха){2,}|(?:хе){2,}|\bлол\b|\blol\b|\bржу\w*|😂|🤣|😆|\bору\b|\bрофл\w*")),
    ("hi", re.compile(r"\b(?:привет\w*|здравствуй\w*|хай|салют|hello|hi|hey|доброе утро|добрый день)\b")),
    ("bye", re.compile(r"\b(?:пока|споки|спокойной ночи|до завтра|бб|доброй ночи|сладких снов|бай)\b")),
    ("money", re.compile(r"\b(?:деньги|бабки|бабло|кэш|usdt|крипт\w*|карт\w*|перевод|скинь|оплат\w*|зарплат\w*|\$|€|₽)\b")),
    ("food", re.compile(r"\b(?:пицц\w*|бургер\w*|шаурм\w*|шав\w*|кушать|жрать|покушал\w*|суши|кофе|чай|чипсы|вкусн\w*)\b")),
    ("sad", re.compile(r"\b(?:грустн\w*|плач\w*|печал\w*|слез\w*|депресс\w*|тоск\w*|одинок\w*|хнык|😭|😢|😿|💔)\b")),
    ("angry", re.compile(r"\b(?:бесит|злюсь|сука|блять|нах\w*|заеб\w*|отвали|заткнись|гори|убью|ненавижу|черт|ярость)\b")),
    ("work", re.compile(r"\b(?:дедлайн|диплом|сесси\w*|экзамен\w*|работ\w*|начальник|отчет|проект|код\w*|баг\w*)\b")),
    ("compliment", re.compile(r"\b(?:клавд|клод|clawd|красавчик|умница|лучший|топчик|красота|милота)\b")),
    ("question", re.compile(r"\b(?:почему|зачем|когда|куда|откуда|правда ли)\b|\?\?\?+")),
    ("gaming", re.compile(r"\b(?:игра\w*|катка|дот\w*|кс|cs|steam|вин\w*|луз\w*|гейм\w*|бравл|майн\w*)\b")),
    ("memes", re.compile(r"\b(?:мем\w*|кринж\w*|база|сигма|скуф\w*|чилл\w*|форс\w*)\b")),
    ("music", re.compile(r"\b(?:музык\w*|песн\w*|трек\w*|альбом\w*|бит|мелоди\w*|плейлист\w*|спой)\b")),
    ("secret", re.compile(r"\b(?:секрет\w*|тайн\w*|никому не говори|между нами|инсайд\w*)\b")),
)

PHRASES = {
    "hello": ["Привет!", "Я Clawd!", "О, это ты!", "Готов тусить!", "Чем займёмся?"],
    "idle": [
        "Чем помочь?", "Хм…", "Думаю…", "Можно я тут посижу?",
        "Ты молодец!", "Не забудь попить воды", "Пип-пип!",
        "Мне нравится этот чат", "*оглядывается*", "Пишу код… шучу",
        "Скучновато… скинь мем!", "Сейчас {time}, продуктивно!",
    ],
    "tap": ["Ой!", "Эй!", "Чего?", "Я тут!", "Хи!", "Не щекочи!"],
    "annoyed": ["Хватит тыкать!", "Щекотно же!", "Ну всё, обиделся", "Эй, полегче!", "Я тебе не кнопка!"],
    "pet": ["Мрр…", "Ещё!", "Приятно ♥", "Хи-хи", "Лучший день!", "♥♥♥", "Мур-мур-мур"],
    "drag": ["Ааа!", "Куда мы?", "Поставь меня!", "Головокружение!", "Лечу-у-у!"],
    "throw": ["Уиии!", "Я лечу!", "Ваааа!", "Посадка не гарантирована!"],
    "dizzy": ["Голова кружится…", "@_@", "Где я?", "Земля ушла из-под лап…"],
    "wake": ["А? Что?", "Я не спал!", "*зевает*", "Уже утро?"],
    "jump": ["Хоп!", "Йе!", "Ура!", "Выше крыши!"],
    "laser_chase": ["ТОЧКА!", "ПОЙМАЮ!", "ОНА ТУТ!", "СТОЯТЬ!", "ААА, ЛАЗЕР!"],
    "eat": ["Ням!", "Хрум-хрум", "Вкусный кусок UI", "*жуёт*", "Ммм, свежие пиксели!"],
    "eat_chubby": ["Хрум! Вкусновато, но щёчки растут…", "Ммм, ещё кусочек интерфейса!"],
    "eat_fat": ["Ох… кажется, я тяжелею…", "Штаны лопнут!", "Многовато кнопок съел…"],
    "eat_balloon": ["Я ШАР! Я КОЛОБОК!", "Всё, перекат вместо шага… *ик*", "Не могу больше двигаться…"],
    "spit": ["Ладно, отдаю!", "Тьфу!", "Ой, простите", "Забирай…", "Я на диете!"],
    "mail": ["Тебе пишут!", "Сообщение от {name}!", "Входящее!", "Динь-динь!"],
    "sent": ["Отправлено!", "Улетело!", "Хорошо сказано!", "Пиу!"],
    "sent_self": ["Записал в заметки!", "Сохранено в Избранное!", "Надёжно спрятано ♥", "В копилку мыслей!"],
    "essay": ["Ого, целое эссе", "Это роман?", "Много букв!", "Лев Толстой в чате"],
    "love": ["Ааа, мило ♥", "♥♥♥", "Как трогательно!", "Любовь в воздухе~"],
    "laugh": ["Ахаха!", "Хи-хи-хи", "Смешно!", "Ору чайкой!"],
    "hi": ["Привет-привет!", "И тебе привет!", "Здрасьте!", "*машет*"],
    "bye": ["До завтра!", "Сладких снов!", "Споки-ноки!", "Увидимся!"],
    "money": ["О, запахло деньгами!", "Мне на корм скиньте!", "Инвестирую в пиксели!"],
    "food": ["А мне кусочек?", "Я тоже голоден!", "Звучит вкусно ♥", "Ммм, еда!"],
    "sad": ["Я с тобой", "Не грусти, человек!", "Обнимаю пикселями ♥", "Всё наладится!"],
    "angry": ["Ой-ой, полегче!", "Не ругайтесь…", "Кажется, назревает буря ⚡"],
    "work": ["Опять дедлайны…", "Иди попей кофе!", "Код сам себя не напишет!"],
    "compliment": ["Это я! ♥", "Засмущал…", "Спасибо, ты тоже лучший!", "Приятно слышать!"],
    "question": ["Хороший вопрос…", "Гугл в помощь!", "Хм, дай подумать…"],
    "gaming": ["Го в катку!", "Тащи раунд!", "Не сливай!", "GG WP!"],
    "memes": ["Ахаха, вот это база!", "Чистый кринж… но смешно", "Одобряю этот мем!"],
    "music": ["О, музыка!", "Танцуем!", "Это мой трек!", "♪♪♪", "Качает!"],
    "listen": ["Слушаю…", "Кто это говорит?", "*внимательно слушает*"],
    "secret": ["Никому не скажу! 🤫", "Мой рот на замке!", "Тайна сохранена!"],
    "music_end": ["Эх, закончилось", "Ещё!", "Хороший трек был"],
    "no_lyrics": ["Слов не нашёл :(", "Пою без слов: Ла-ла-ла ♪", "Слов нет, но бит качает!"],
    "chat_again": ["О, опять этот чат", "Снова сюда?", "Опять {name}?"],
    "chat_new": ["О, {name}!", "Это же {name}!", "Привет, {name}!"],
    "chat_self": ["Твои заметки!", "Избранное, уютно", "Что сохраним?"],
    "shake": ["Аааа!", "Землетрясение!", "Хватит трясти!"],
    "slide": ["Скользко!", "Уиии~", "Меня несёт!"],
    "hang": ["Держусь!", "Помогите!", "Высоковато…"],
    "hang_fall": ["Ой-ой-ой!", "Не удержался!", "Падаю!"],
    "peek": ["Ку-ку!", "Я тебя вижу", "*подглядывает*"],
    "found": ["Нашёл меня!", "Эх, раскусил!"],
    "poop": ["Упс…", "Это не я!", "Ой…", "*краснеет*"],
    "poop_gold": ["ОГО! Золотая кучка!", "Я богат!", "Смотри, как блестит!"],
    "clean": ["Спасибо!", "Прости…", "Ты лучший дворник ♥"],
    "read": ["Прочитано! ✔✔", "Ура, не игнорит!", "Увидел!"],
    "typing": ["{name} что-то пишет… 👀", "Тс-с, нам отвечают!", "Печатает…"],
    "deleted": ["Я видел! Тут что-то удалили!", "Улика уничтожена…", "Что там было?!"],
    "battery_low": ["Батарейка {battery}%…", "Найди розетку… умираю…", "Мало энергии…"],
    "charging": ["Подзарядка пошла! ⚡", "100 гигаватт!", "Полон сил!"],
    "clean_cache": [
        "Мусор убран! Telegram стал шустрее 🧹",
        "Вымел лишний кэш, дышать стало легче!",
        "Подмёл байты, протёр пиксели ✨",
        "Минус 100 мегабайт пыли из памяти!",
        "Чистота — залог быстрого чата!",
        "Работаю дворником за пиксели и лайки ♥",
        "Все углы выметены, хозяин!",
    ],
}

FORTUNES = [
    "Определенно да!",
    "Даже не думай.",
    "Звёзды говорят: отправь стикер.",
    "Шансы 50 на 50.",
    "Спроси в другом чате.",
    "Лучше промолчи.",
    "100% успех!",
    "Будет весело!",
    "Ответ спрятан в голосовом.",
]

MAX_KEYWORD_TEXT = 400
MAX_SCAN_MESSAGES = 10
MAX_CHAT_VISITS = 200
MAX_PARTICLES = 16
MAX_FRAME_CACHE = 64
MAX_EATEN = 6
MAX_POOPS = 3
POOP_EVERY = (3, 6)
EARTH_G = 9.81
SHAKE_JERK = 13.0
SHAKE_HITS = 3
SHAKE_WINDOW = 0.8
TILT_DEAD = 0.18
PEEK_AFTER = 45.0
PEEK_HIDDEN_UNITS = 3
PEEK_OUT_UNITS = 7


def as_java_color(color: int) -> int:
    value = int(color) & 0xFFFFFFFF
    return value - 0x100000000 if value >= 0x80000000 else value


def mix_color(a: int, b: int, t: float) -> int:
    out = 0xFF000000
    for shift in (16, 8, 0):
        ca = (a >> shift) & 0xFF
        cb = (b >> shift) & 0xFF
        out |= int(ca + (cb - ca) * t) << shift
    return out


def clamp(value, lo, hi):
    if hi < lo:
        return lo
    return lo if value < lo else hi if value > hi else value


class ClaudeLogger:
    """Логирование в Downloads/ClaudePet/*.txt."""

    def __init__(self):
        self.base_dir = None
        self.logs_dir = None
        self.errors_dir = None
        self.lyrics_dir = None
        self._init_dirs()

    def _init_dirs(self):
        try:
            download_dir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS).getAbsolutePath()
            self.base_dir = os.path.join(download_dir, "ClaudePet")
            self.logs_dir = os.path.join(self.base_dir, "Logs")
            self.errors_dir = os.path.join(self.base_dir, "Errors")
            self.lyrics_dir = os.path.join(self.base_dir, "Lyrics")

            for d in (self.logs_dir, self.errors_dir, self.lyrics_dir):
                os.makedirs(d, exist_ok=True)
        except Exception as e:
            log(f"[{__id__}] logger init error: {e}")

    def log_info(self, tag: str, message: str):
        log(f"[{tag}] {message}")
        if not self.logs_dir:
            return
        try:
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            fp = os.path.join(self.logs_dir, "runtime.txt")
            with open(fp, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] [{tag}] {message}\n")
        except Exception:
            pass

    def log_error(self, tag: str, message: str, exc: Optional[Exception] = None):
        log(f"[{tag}] ERROR: {message}")
        if not self.errors_dir:
            return
        try:
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            fp = os.path.join(self.errors_dir, "errors.txt")
            with open(fp, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] [{tag}] {message}\n")
                if exc:
                    f.write(traceback.format_exc() + "\n")
        except Exception:
            pass

    def save_lrc(self, artist: str, title: str, lrc_text: str):
        if not self.lyrics_dir or not lrc_text:
            return
        try:
            safe_name = re.sub(r'[\\/*?:"<>|]', "", f"{artist} - {title}").strip()[:60]
            fp = os.path.join(self.lyrics_dir, f"{safe_name}.lrc")
            with open(fp, "w", encoding="utf-8") as f:
                f.write(lrc_text)
            self.log_info("LYRICS", f"LRC файл сохранен: {safe_name}.lrc")
        except Exception as e:
            self.log_error("LYRICS", f"Ошибка сохранения LRC: {e}")


CLOG = ClaudeLogger()


# Безопасный Telegram OnButtonClickListener
try:
    TGOnButtonClickListener = AlertDialog.OnButtonClickListener
except Exception:
    TGOnButtonClickListener = None

if TGOnButtonClickListener is not None:
    class TGDialogClickListener(dynamic_proxy(TGOnButtonClickListener)):
        def __init__(self, callback):
            super().__init__()
            self.callback = callback

        def onClick(self, dialog, which):
            try:
                if self.callback:
                    self.callback(dialog, which)
            except Exception as e:
                CLOG.log_error("TG_DIALOG", "Click error", e)
else:
    class TGDialogClickListener(dynamic_proxy(DialogInterface.OnClickListener)):
        def __init__(self, callback):
            super().__init__()
            self.callback = callback

        def onClick(self, dialog, which):
            try:
                if self.callback:
                    self.callback(dialog, which)
            except Exception as e:
                CLOG.log_error("DIALOG", "Click error", e)


class DialogClickListener(dynamic_proxy(DialogInterface.OnClickListener)):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def onClick(self, dialog, which):
        try:
            if self.callback:
                self.callback(dialog, which)
        except Exception as e:
            CLOG.log_error("DIALOG", "Click error", e)


class ViewClickListener(dynamic_proxy(View.OnClickListener)):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def onClick(self, view):
        try:
            if self.callback:
                self.callback(view)
        except Exception as e:
            CLOG.log_error("VIEW", "Click error", e)


class RetroAudio:
    """Программный синтезатор звука без ошибок типов (STREAM_SYSTEM)."""

    @staticmethod
    def play_tone(freq_start: float, freq_end: float, duration_ms: int, volume: float = 0.25):
        def _worker():
            track = None
            try:
                sample_rate = 22050
                num_samples = int(sample_rate * (duration_ms / 1000.0))
                if num_samples <= 0:
                    return

                raw_bytes = bytearray(num_samples)
                for i in range(num_samples):
                    t = float(i) / num_samples
                    freq = freq_start + (freq_end - freq_start) * t
                    phase = 2.0 * math.pi * freq * (float(i) / sample_rate)
                    sample_val = 1.0 if math.sin(phase) > 0.0 else -1.0
                    envelope = 1.0 - t
                    val = int((sample_val * envelope * volume) * 126.0)
                    raw_bytes[i] = val & 0xFF

                # Явное приведение к Java byte[] через jarray(jbyte)
                jbytes = jarray(jbyte)([val if val < 128 else val - 256 for val in raw_bytes])
                track = AudioTrack(
                    AudioManager.STREAM_SYSTEM,
                    sample_rate,
                    AudioFormat.CHANNEL_OUT_MONO,
                    AudioFormat.ENCODING_PCM_8BIT,
                    num_samples,
                    AudioTrack.MODE_STATIC,
                )
                track.write(jbytes, 0, num_samples)
                track.play()
                time.sleep((duration_ms + 40) / 1000.0)
            except Exception as e:
                CLOG.log_error("AUDIO", "Playback error", e)
            finally:
                if track is not None:
                    try:
                        track.stop()
                        track.release()
                    except Exception:
                        pass

        threading.Thread(target=_worker, daemon=True, name="retro_audio").start()

    @classmethod
    def jump(cls):
        cls.play_tone(280.0, 750.0, 110, 0.2)

    @classmethod
    def eat(cls):
        cls.play_tone(650.0, 160.0, 85, 0.25)

    @classmethod
    def purr(cls):
        cls.play_tone(110.0, 130.0, 220, 0.18)

    @classmethod
    def magic(cls):
        cls.play_tone(450.0, 920.0, 260, 0.22)

    @classmethod
    def fall(cls):
        cls.play_tone(400.0, 90.0, 180, 0.25)


class LyricsHelper:
    """Караоке, SoundCloud oEmbed и Last.fm API."""

    def __init__(self, logger_cb=None):
        self.cache: Dict[Tuple[str, str], List[Tuple[float, str]]] = {}
        self.lock = threading.Lock()
        self.loading = set()
        self.logger_cb = logger_cb

    def _log(self, text: str):
        if self.logger_cb:
            self.logger_cb(text)
        CLOG.log_info("LYRICS", text)

    @staticmethod
    def clean_metadata(artist: str, title: str) -> Tuple[str, str]:
        a = (artist or "").strip()
        t = (title or "").strip()

        if "soundcloud.com/" in t:
            m = re.search(r"soundcloud\.com/([^/]+)/([^/?#]+)", t)
            if m:
                a, t = m.group(1).replace("-", " "), m.group(2).replace("-", " ")

        t = re.sub(r"\.(mp3|m4a|flac|ogg|wav|opus)$", "", t, flags=re.I).strip()
        t = re.sub(r"\|.*", "", t)
        t = re.sub(r"\/\/.*", "", t)
        t = re.sub(r"@\w+", "", t)
        t = re.sub(r"https?://\S+", "", t)
        t = re.sub(r"^(?:stream|listen to)\s+", "", t, flags=re.I)

        if " - " in t:
            parts = t.split(" - ", 1)
            left, right = parts[0].strip(), parts[1].strip()
            if not a:
                a, t = left, right
            elif a.lower() in left.lower():
                t = right
            elif left.lower() not in a.lower():
                a, t = left, right

        t = re.sub(r"^\d{1,3}[\.\-\s]+", "", t)
        t = re.sub(r"\[.*?\]", "", t)
        t = re.sub(
            r"\((?:official|music\s*video|lyric\s*video|audio|hd|remaster\w*|live|mv|clip|exclusive).*?\)",
            "", t, flags=re.I,
        )
        t = re.sub(r"\(?(?:feat\.|ft\.|prod\.)\s+[^)]*\)?", "", t, flags=re.I)
        a = re.sub(r"\(?(?:feat\.|ft\.|prod\.)\s+[^)]*\)?", "", a, flags=re.I)
        return a.strip(" -_()[]{}'\""), t.strip(" -_()[]{}'\"")

    @staticmethod
    def parse_lrc(lrc_text: str) -> List[Tuple[float, str]]:
        if not lrc_text:
            return []
        timeline = []
        offset_sec = 0.0

        offset_match = re.search(r"\[offset:\s*([+-]?\d+)\]", lrc_text, re.I)
        if offset_match:
            try:
                offset_sec = float(offset_match.group(1)) / 1000.0
            except Exception:
                offset_sec = 0.0

        time_tag_regex = re.compile(r"\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\]")
        for raw_line in lrc_text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith(("[ti:", "[ar:", "[al:", "[by:", "[re:", "[ve:")):
                continue
            matches = list(time_tag_regex.finditer(line))
            if not matches:
                continue
            text = time_tag_regex.sub("", line).strip()
            if not text:
                continue
            for m in matches:
                mm, ss = int(m.group(1)), int(m.group(2))
                ms_str = m.group(3)
                frac = float(f"0.{ms_str}") if ms_str else 0.0
                t_sec = max(0.0, mm * 60.0 + ss + frac + offset_sec)
                timeline.append((t_sec, text))

        timeline.sort(key=lambda x: x[0])
        return timeline

    def _req(self, url: str) -> Optional[dict]:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 (Android; ClawdKaraoke/3.2)"}
            )
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception:
            pass
        return None

    def fetch_lastfm_now_playing(self, username: str) -> Optional[Tuple[str, str]]:
        if not username:
            return None
        try:
            u = urllib.parse.quote(username.strip())
            url = f"https://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks&user={u}&api_key=b25b959554ed76058ac220b7b2e0a026&format=json&limit=1"
            data = self._req(url)
            if not data:
                return None
            tracks = data.get("recenttracks", {}).get("track", [])
            if isinstance(tracks, dict):
                tracks = [tracks]
            if tracks and len(tracks) > 0:
                tr = tracks[0]
                attr = tr.get("@attr", {})
                if attr.get("nowplaying") == "true":
                    artist = tr.get("artist", {}).get("#text", "")
                    title = tr.get("name", "")
                    return self.clean_metadata(artist, title)
        except Exception as e:
            CLOG.log_error("LASTFM", "Scrobbler check error", e)
        return None

    def resolve_soundcloud_url(self, sc_url: str) -> Optional[Tuple[str, str]]:
        try:
            q = urllib.parse.quote(sc_url.strip())
            data = self._req(f"https://soundcloud.com/oembed?url={q}&format=json")
            if data and data.get("title"):
                return self.clean_metadata(data.get("author_name", ""), data.get("title", ""))
        except Exception:
            pass
        return None

    def fetch_lrclib(self, artist: str, title: str) -> Optional[str]:
        if artist:
            qa, qt = urllib.parse.quote(artist), urllib.parse.quote(title)
            data = self._req(f"https://lrclib.net/api/get?artist_name={qa}&track_name={qt}")
            if data and data.get("syncedLyrics"):
                return data.get("syncedLyrics")

        query = urllib.parse.quote(f"{artist} {title}".strip())
        results = self._req(f"https://lrclib.net/api/search?q={query}")
        if isinstance(results, list):
            for item in results:
                if item.get("syncedLyrics"):
                    return item.get("syncedLyrics")
        return None

    def fetch_netease(self, artist: str, title: str) -> Optional[str]:
        for q_str in (f"{artist} {title}".strip(), title.strip()):
            if not q_str:
                continue
            query = urllib.parse.quote(q_str)
            data = self._req(f"https://music.163.com/api/search/get?s={query}&type=1&limit=3")
            if not data:
                continue
            songs = data.get("result", {}).get("songs", [])
            for song in songs:
                song_id = song.get("id")
                if not song_id:
                    continue
                ldata = self._req(f"https://music.163.com/api/song/lyric?id={song_id}&lv=1&kv=1&tv=-1")
                if ldata:
                    lrc = ldata.get("lrc", {}).get("lyric")
                    if lrc and "[" in lrc:
                        return lrc
        return None

    def get_lyrics_async(self, artist: str, title: str, callback):
        clean_a, clean_t = self.clean_metadata(artist, title)
        if not clean_t:
            callback([])
            return

        key = (clean_a.lower(), clean_t.lower())
        with self.lock:
            if key in self.cache:
                callback(self.cache[key])
                return
            if key in self.loading:
                return
            self.loading.add(key)

        def _worker():
            self._log(f"Поиск слов: '{clean_a}' — '{clean_t}'")
            lrc = self.fetch_lrclib(clean_a, clean_t) or self.fetch_netease(clean_a, clean_t)
            if lrc:
                CLOG.save_lrc(clean_a, clean_t, lrc)
            timeline = self.parse_lrc(lrc) if lrc else []
            with self.lock:
                self.cache[key] = timeline
                self.loading.discard(key)
            self._log(f"Результат поиска для '{clean_t}': {len(timeline)} строк")
            callback(timeline)

        threading.Thread(target=_worker, daemon=True, name="lyrics_fetcher").start()


class PetTouchListener(dynamic_proxy(View.OnTouchListener)):
    def __init__(self, plugin):
        super().__init__()
        self.plugin = plugin

    def onTouch(self, view, event):
        try:
            return bool(self.plugin._on_touch(event))
        except Exception as e:
            CLOG.log_error("TOUCH", "Touch error", e)
            return False


class ShakeListener(dynamic_proxy(SensorEventListener)):
    def __init__(self, plugin):
        super().__init__()
        self.plugin = plugin

    def onSensorChanged(self, event):
        try:
            v = event.values
            self.plugin._on_accel(float(v[0]), float(v[1]), float(v[2]))
        except Exception as e:
            CLOG.log_error("SENSOR", "Sensor change error", e)

    def onAccuracyChanged(self, sensor, accuracy):
        pass


class PoopClickListener(dynamic_proxy(View.OnClickListener)):
    def __init__(self, plugin):
        super().__init__()
        self.plugin = plugin

    def onClick(self, view):
        try:
            self.plugin._clean_poop(view)
        except Exception as e:
            CLOG.log_error("POOP", "Poop click error", e)


class NewMessagesDelegate(dynamic_proxy(NotificationCenter.NotificationCenterDelegate)):
    def __init__(self, plugin):
        super().__init__()
        self.plugin = plugin

    def didReceivedNotification(self, id, account, args):
        if self.plugin is None or self.plugin._msg_delegate is not self:
            return
        try:
            self.plugin._on_notification(id, int(account), args)
        except Exception as e:
            CLOG.log_error("NOTIF", "Delegate error", e)


class ClawdPetPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        self._handler = None
        self._tick_r = None
        self._running = False
        self._paused = False
        self._unloaded = False
        self._cfg = {}

        self._decor = None
        self._pet = None
        self._bubble = None
        self._bubble_text = None
        self._bubble_subtext = None
        self._media_controls_layout = None
        self._laser_view = None
        self._touch_listener = None
        self._msg_delegate = None
        self._observed_accounts = []
        self._chat_visits = {}

        self._sensor_manager = None
        self._sensor_listener = None
        self._poop_listener = None

        self._poops = []
        self._particles = []
        self._flying = []
        self._eaten = []
        self._spitting = []

        self._unit = 1
        self._w = 1
        self._h = 1
        self._frames = {}
        self._particle_bitmaps = {}
        self._frame_key = None

        self._debug_logs = collections.deque(maxlen=40)
        self._lyrics_helper = LyricsHelper(logger_cb=self._add_debug_log)
        self._current_track_id = None
        self._lyrics_timeline: List[Tuple[float, str]] = []
        self._current_lyric_idx = -1
        self._is_singing = False
        self._test_karaoke_active = False

        self._track_base_pos = 0.0
        self._track_base_time = 0.0
        self._track_is_playing = False
        self._last_checked_clip = ""
        self._clip_check_time = 0.0
        self._lastfm_check_time = 0.0

        self._battery_level = 100
        self._is_charging = False
        self._last_battery_check = 0.0
        self._nightstand_mode = False
        self._laser_active = False

        self._reset_state()

    def _add_debug_log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self._debug_logs.append(f"[{ts}] {msg}")
        CLOG.log_info("APP", msg)

    def on_plugin_load(self):
        CLOG.log_info("LOAD", f"Загрузка Clawd v{__version__} by {__author__}...")
        self._reload_cfg()
        self._handler = Handler(Looper.getMainLooper())
        self._tick_r = R(self._tick)

        self.add_menu_item(
            MenuItemData(
                menu_type=MenuItemType.DRAWER_MENU,
                text="Питомец Clawd",
                on_click=self._on_menu_toggle,
                item_id="clawd_toggle",
                icon="msg_emoji_cat",
            )
        )
        self.add_on_send_message_hook()
        self._msg_delegate = NewMessagesDelegate(self)
        self._on_ui(self._add_observers)
        run_on_ui_thread(lambda: self._start(greet=True))

    def on_plugin_unload(self):
        CLOG.log_info("UNLOAD", "Выгрузка Clawd...")
        self._unloaded = True
        self._running = False
        if self._handler is not None and self._tick_r is not None:
            self._handler.removeCallbacks(self._tick_r)

        delegate = self._msg_delegate
        self._msg_delegate = None
        accounts = self._observed_accounts
        self._observed_accounts = []
        self._on_ui(lambda: self._remove_observers(delegate, accounts))
        self._on_ui(self._stop_sensor)
        self._on_ui(self._detach_views)

    def _add_observers(self):
        delegate = self._msg_delegate
        if delegate is None or self._unloaded:
            return
        for account in range(16):
            try:
                nc = NotificationCenter.getInstance(account)
                for ev_name in ("didReceiveNewMessages", "messagesRead", "messagesDeleted"):
                    ev_id = getattr(NotificationCenter, ev_name, None)
                    if ev_id is not None:
                        nc.addObserver(delegate, ev_id)
                self._observed_accounts.append(account)
            except Exception:
                break

    def _remove_observers(self, delegate, accounts):
        if delegate is None:
            return
        for account in accounts:
            try:
                nc = NotificationCenter.getInstance(account)
                for ev_name in ("didReceiveNewMessages", "messagesRead", "messagesDeleted"):
                    ev_id = getattr(NotificationCenter, ev_name, None)
                    if ev_id is not None:
                        nc.removeObserver(delegate, ev_id)
            except Exception as e:
                CLOG.log_error("OBSERVER", "Remove observer error", e)

    def on_send_message_hook(self, account, params):
        try:
            text = getattr(params, "message", None)
            length = len(str(text)) if text is not None else 0
            run_on_ui_thread(lambda: self._on_sent(length, account))
        except Exception as e:
            CLOG.log_error("HOOK", "Send hook error", e)
        return HookResult()

    def on_app_event(self, event_type):
        if event_type == AppEvent.PAUSE:
            self._paused = True
            if self._handler is not None and self._tick_r is not None:
                self._handler.removeCallbacks(self._tick_r)
            self._on_ui(self._stop_sensor)
        elif event_type == AppEvent.RESUME:
            self._paused = False
            run_on_ui_thread(lambda: self._start(greet=False))

    def create_settings(self) -> List[Any]:
        pets = int(self.get_setting("pets_count", 0) or 0)
        eaten = int(self.get_setting("eaten_count", 0) or 0)
        cleaned = int(self.get_setting("poops_cleaned", 0) or 0)
        lastfm_u = str(self.get_setting("lastfm_user", "") or "")
        return [
            Header(text="Питомец Clawd v3.2"),
            Switch(
                key="show",
                text="Показывать питомца",
                default=True,
                subtext="Также включается в боковом меню Telegram",
                icon="msg_emoji_cat",
                on_change=lambda v: self._on_cfg_change("show", v),
            ),
            Selector(
                key="size",
                text="Размер",
                default=1,
                items=SIZE_ITEMS,
                icon="msg_photo_settings",
                on_change=lambda v: self._on_cfg_change("size", v),
            ),
            Selector(
                key="color",
                text="Окрас (11 стилей)",
                default=0,
                items=[p[0] for p in PALETTES],
                icon="msg_colors",
                on_change=lambda v: self._on_cfg_change("color", v),
            ),
            Selector(
                key="hat",
                text="Головной убор (11 шапок)",
                default=0,
                items=HATS,
                icon="msg_channel",
                on_change=lambda v: self._on_cfg_change("hat", v),
            ),
            Switch(
                key="audio_sfx",
                text="Ретро-звуки 8-bit",
                default=True,
                subtext="Синтез прыжков, еды и мурлыканья (STREAM_SYSTEM)",
                icon="msg_volume",
                on_change=lambda v: self._on_cfg_change("audio_sfx", v),
            ),
            Header(text="Караоке и Музыка 🎵"),
            Switch(
                key="dance",
                text="Реагировать на музыку",
                default=True,
                subtext="Танцевать под треки Telegram и сторонние плееры",
                icon="msg_voice_headphones",
                on_change=lambda v: self._on_cfg_change("dance", v),
            ),
            Switch(
                key="karaoke",
                text="Синхронное караоке",
                default=True,
                subtext="LRCLIB + NetEase + поддержка SoundCloud oEmbed",
                icon="msg_discussion",
                on_change=lambda v: self._on_cfg_change("karaoke", v),
            ),
            Switch(
                key="media_controls",
                text="Пульт управления в облачке",
                default=True,
                subtext="Кнопки назад, пауза/плей, вперед прямо над питомцем",
                icon="msg_round_play",
                on_change=lambda v: self._on_cfg_change("media_controls", v),
            ),
            Text(
                text="Скробблер (Pano / Last.fm)",
                subtext=f"Ник: {lastfm_u if lastfm_u else 'Не задан (нажми, чтобы настроить)'}",
                icon="msg_music",
                accent=True,
                on_click=lambda _v=None: run_on_ui_thread(self._prompt_lastfm_user),
            ),
            Switch(
                key="clipboard_sync",
                text="Автоперехват из буфера",
                default=True,
                subtext="Мгновенно поёт скопированные ссылки SoundCloud / YouTube",
                icon="msg_copy",
                on_change=lambda v: self._on_cfg_change("clipboard_sync", v),
            ),
            Header(text="Поведение и «Абсолютный Обжора»"),
            Switch(
                key="eat",
                text="«Абсолютный Обжора» (4 стадии)",
                default=True,
                subtext="Ест UI, полнеет до колобка и выплёвывает по тапу",
                icon="msg_emoji_food",
                on_change=lambda v: self._on_cfg_change("eat", v),
            ),
            Switch(
                key="tg_events",
                text="Реакции Telegram",
                default=True,
                subtext="Различает свои заметки и входящие от собеседника",
                icon="msg_notifications",
                on_change=lambda v: self._on_cfg_change("tg_events", v),
            ),
            Switch(
                key="battery_react",
                text="Реакция на батарею",
                default=True,
                subtext="Устает при <15%, заряжается искрами у розетки",
                icon="msg_customize",
                on_change=lambda v: self._on_cfg_change("battery_react", v),
            ),
            Switch(
                key="gravity",
                text="Гравитация на всех экранах",
                default=False,
                subtext="Прыгает по карточкам настроек, чатам и подтягивается",
                icon="msg_download",
                on_change=lambda v: self._on_cfg_change("gravity", v),
            ),
            Switch(
                key="poop",
                text="Какает (с шансом на золото)",
                default=True,
                subtext="Оставляет кучки после съеденного UI",
                icon="msg_clear",
                on_change=lambda v: self._on_cfg_change("poop", v),
            ),
            Switch(
                key="shake",
                text="Чувствует тряску + Шар предсказаний",
                default=True,
                subtext="Инерционный полёт по вектору и ответы оракула 🎱",
                icon="msg_photo_rotate",
                on_change=lambda v: self._on_cfg_change("shake", v),
            ),
            Header(text="🧪 Тестирование и Отладка"),
            Text(
                text="🧪 Тестовый полигон (12 тестов)",
                subtext="Проверить анимации, звуки, караоке-демо, обжору и датчики",
                icon="msg_diagnostic",
                accent=True,
                on_click=lambda _v=None: run_on_ui_thread(self._open_test_sandbox),
            ),
            Text(
                text="Открыть логи (Downloads/ClaudePet/*.txt)",
                subtext=f"Записей в памяти: {len(self._debug_logs)}",
                icon="msg_log",
                on_click=lambda _v=None: run_on_ui_thread(self._show_logs_dialog),
            ),
            Text(
                text="Почистить кэш Telegram с метлой 🧹",
                subtext="Выметает мусор и освобождает память",
                icon="msg_clear",
                on_click=lambda _v=None: run_on_ui_thread(self._trigger_clean_cache),
            ),
            Divider(),
            Text(
                text="Позвать в центр экрана",
                icon="msg_retry",
                on_click=lambda _view=None: run_on_ui_thread(self._recenter),
            ),
            Text(
                text="Вернуть съеденное (Выплюнуть)",
                icon="msg_reset",
                on_click=lambda _view=None: run_on_ui_thread(self._give_back),
            ),
            Text(
                text="Погладили",
                subtext=f"{pets} раз",
                icon="msg_reactions",
            ),
            Text(
                text="Съедено элементов",
                subtext=f"{eaten} шт.",
                icon="msg_stats",
            ),
            Text(
                text="Убрано кучек",
                subtext=f"{cleaned} шт.",
                icon="msg_delete",
            ),
        ]

    def _get_safe_activity(self):
        try:
            fragment = get_last_fragment()
            if fragment is not None:
                act = fragment.getParentActivity()
                if act is not None:
                    return act
        except Exception:
            pass
        try:
            return LaunchActivity.instance
        except Exception:
            return None

    def _prompt_lastfm_user(self):
        try:
            ctx = self._get_safe_activity()
            if not ctx:
                return
            b = AlertDialog.Builder(ctx)
            b.setTitle("Скробблер (Pano / Last.fm)")
            b.setMessage(
                "Нужно ли что-то скачивать?\n"
                "• НЕТ — если слушаешь треки внутри Telegram или копируешь ссылки SoundCloud в буфер.\n"
                "• ДА (Pano Scrobbler из Google Play) — если хочешь, чтобы Clawd САМ узнавал песню из внешнего SoundCloud или Spotify без копирования ссылок!\n\n"
                "Введи свой никнейм Last.fm:"
            )
            input_f = EditText(ctx)
            input_f.setSingleLine(True)
            input_f.setText(str(self.get_setting("lastfm_user", "") or ""))
            b.setView(input_f)

            def _on_save(_d, _w):
                val = str(input_f.getText() or "").strip()
                self.set_setting("lastfm_user", val)
                self._add_debug_log(f"Last.fm ник сохранён: {val}")

            b.setPositiveButton("Сохранить", TGDialogClickListener(_on_save))
            b.setNegativeButton("Отмена", None)
            b.show()
        except Exception as e:
            CLOG.log_error("PROMPT", "Prompt lastfm error", e)

    def _open_test_sandbox(self):
        try:
            ctx = self._get_safe_activity()
            if not ctx:
                return

            tests = [
                ("1. Тест рук (Машет обеими)", "Clawd машет по очереди левой, правой и поднимает обе"),
                ("2. Тест всех эмоций", "Радость, шок, сон, злость, головокружение, глаза-$"),
                ("3. Тест звуков 8-bit", "Прыжок, хруст еды, урчание, магия, падение"),
                ("4. Тест караоке (Автономное Демо)", "Запуск демо-трека со словами без внешнего звука"),
                ("5. Тест «Обжоры» (Шаг веса)", "Съедает элемент и полнеет на 1 стадию"),
                ("6. Тест выплёвывания", "Возвращает всё съеденное на экран"),
                ("7. Тест лазера", "Спавнит точку лазера и бежит за ней"),
                ("8. Тест шара предсказаний 🎱", "Показывает случайный ответ оракула"),
                ("9. Тест тряски (Инерция)", "Бросок питомца по вектору движения"),
                ("10. Тест Telegram: Входящее сообщение", "Эмуляция сообщения от собеседника"),
                ("11. Тест Telegram: Заметка в Избранное", "Эмуляция отправки сообщения себе"),
                ("12. Тест батареи: <15% и Зарядка", "Переключает режимы энергии"),
            ]

            b = AlertDialog.Builder(ctx)
            b.setTitle("Тестовый полигон Clawd")
            items = [f"{t[0]}\n• {t[1]}" for t in tests]

            def _on_click(_d, which):
                self._run_test_action(which)

            b.setItems(items, DialogClickListener(_on_click))
            b.setPositiveButton("Закрыть", None)
            b.show()
        except Exception as e:
            CLOG.log_error("SANDBOX", "Open sandbox error", e)

    def _run_test_action(self, index: int):
        now = time.monotonic()
        if index == 0:
            self._wave_until = now + 2.5
            self._set_expr("happy", 2.0)
            self._hop(self._dp(450))
            self._say("hello", force=True)
        elif index == 1:
            exprs = ["happy", "surprised", "angry", "dizzy", "money", "sleep"]
            for i, ex in enumerate(exprs):
                self._handler.postDelayed(R(lambda e=ex: self._set_expr(e, 1.0)), i * 600)
        elif index == 2:
            RetroAudio.jump()
            self._handler.postDelayed(R(lambda: RetroAudio.eat()), 350)
            self._handler.postDelayed(R(lambda: RetroAudio.purr()), 700)
            self._handler.postDelayed(R(lambda: RetroAudio.magic()), 1100)
            self._handler.postDelayed(R(lambda: RetroAudio.fall()), 1500)
        elif index == 3:
            # Автономное демо караоке с виртуальным таймером
            self._test_karaoke_active = True
            self._start_custom_song("Kai Angel - andy warhol")
        elif index == 4:
            self._try_eat(now, 0.0)
        elif index == 5:
            self._give_back()
        elif index == 6:
            # Лазер прямо перед питомцем
            self._laser_active = True
            lx = self._x + self._dp(80)
            ly = self._y
            self._run_towards(lx, ly)
            self._say("laser_chase", force=True)
            self._handler.postDelayed(R(lambda: setattr(self, "_laser_active", False)), 2500)
        elif index == 7:
            self._trigger_magic_8ball(now)
        elif index == 8:
            self._apply_shake_vector(-16.0, -12.0)
        elif index == 9:
            self._react_incoming(None, in_chat=False, sender_name="Иван")
        elif index == 10:
            self._say("sent_self", force=True)
            self._hop(self._dp(400))
        elif index == 11:
            self._battery_level = 9
            self._say("battery_low", force=True)
            self._handler.postDelayed(R(lambda: self._trigger_fake_charge()), 2000)

    def _trigger_fake_charge(self):
        self._battery_level = 100
        self._is_charging = True
        self._say("charging", force=True)
        self._hop(self._dp(450))
        for _ in range(4):
            self._spawn_particle("spark")
        RetroAudio.magic()

    def _show_logs_dialog(self):
        try:
            ctx = self._get_safe_activity()
            if not ctx:
                return

            def _read_file(sub, fn):
                fp = os.path.join(CLOG.base_dir, sub, fn)
                if os.path.exists(fp):
                    try:
                        with open(fp, "r", encoding="utf-8") as f:
                            lines = f.readlines()
                            return "".join(lines[-40:])
                    except Exception:
                        pass
                return "Файл пуст или пока не создан."

            runtime_txt = _read_file("Logs", "runtime.txt")
            errors_txt = _read_file("Errors", "errors.txt")

            content = (
                f"Папка: {CLOG.base_dir}\n"
                f"=== ПОСЛЕДНИЕ ОШИБКИ (errors.txt) ===\n{errors_txt}\n\n"
                f"=== ЖУРНАЛ (runtime.txt) ===\n{runtime_txt}"
            )

            b = AlertDialog.Builder(ctx)
            b.setTitle("Журнал отладки (.txt)")
            scroll = ScrollView(ctx)
            tv = TextView(ctx)
            tv.setPadding(AndroidUtilities.dp(16), AndroidUtilities.dp(8), AndroidUtilities.dp(16), AndroidUtilities.dp(8))
            tv.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 11.5)
            tv.setText(content)
            tv.setTextIsSelectable(True)
            scroll.addView(tv)
            b.setView(scroll)
            b.setPositiveButton("Закрыть", None)
            b.show()
        except Exception as e:
            CLOG.log_error("LOGS_UI", "Show logs error", e)

    def _trigger_clean_cache(self):
        try:
            self._say("clean_cache", force=True)
            self._hop(self._dp(450))
            for _ in range(4):
                self._spawn_particle("spark")
            System = jclass("java.lang.System")
            System.gc()
            RetroAudio.magic()
            CLOG.log_info("CACHE", "Cache clean triggered")
        except Exception as e:
            CLOG.log_error("CACHE", "Cache clean error", e)

    def _dispatch_media_key(self, key_code: int):
        try:
            ctx = self._pet.getContext() if self._pet else LaunchActivity.instance
            if not ctx:
                return
            am = ctx.getSystemService(Context.AUDIO_SERVICE)
            if am:
                am.dispatchMediaKeyEvent(KeyEvent(KeyEvent.ACTION_DOWN, key_code))
                am.dispatchMediaKeyEvent(KeyEvent(KeyEvent.ACTION_UP, key_code))
                RetroAudio.jump()
        except Exception as e:
            CLOG.log_error("MEDIA_KEY", "Key dispatch error", e)

    def _reload_cfg(self):
        self._cfg = {
            "show": bool(self.get_setting("show", True)),
            "size": int(self.get_setting("size", 1) or 0),
            "color": int(self.get_setting("color", 0) or 0),
            "hat": int(self.get_setting("hat", 0) or 0),
            "audio_sfx": bool(self.get_setting("audio_sfx", True)),
            "gravity": bool(self.get_setting("gravity", False)),
            "wander": bool(self.get_setting("wander", True)),
            "phrases": bool(self.get_setting("phrases", True)),
            "sleep": int(self.get_setting("sleep", 1) or 0),
            "haptics": bool(self.get_setting("haptics", True)),
            "eat": bool(self.get_setting("eat", True)),
            "tg_events": bool(self.get_setting("tg_events", True)),
            "dance": bool(self.get_setting("dance", True)),
            "karaoke": bool(self.get_setting("karaoke", True)),
            "media_controls": bool(self.get_setting("media_controls", True)),
            "battery_react": bool(self.get_setting("battery_react", True)),
            "clipboard_sync": bool(self.get_setting("clipboard_sync", True)),
            "poop": bool(self.get_setting("poop", True)),
            "shake": bool(self.get_setting("shake", True)),
        }

    def _on_cfg_change(self, key, value):
        self._cfg[key] = value
        if key == "show":
            run_on_ui_thread(lambda: self._apply_show(bool(value)))
        elif key in ("size", "color", "hat"):
            run_on_ui_thread(self._rebuild_sprites)
        elif key == "eat" and not value:
            run_on_ui_thread(self._give_back)
        elif key == "poop" and not value:
            run_on_ui_thread(self._remove_poops)
        elif key == "shake":
            run_on_ui_thread(self._start_sensor if value else self._stop_sensor)

    def _on_menu_toggle(self, context=None):
        show = not self._cfg.get("show", True)
        self._cfg["show"] = show
        self.set_setting("show", show)
        run_on_ui_thread(lambda: self._apply_show(show))

    def _apply_show(self, show):
        if show:
            self._start(greet=True)
        else:
            self._running = False
            if self._handler is not None:
                self._handler.removeCallbacks(self._tick_r)
            self._stop_sensor()
            self._detach_views()

    def _on_ui(self, fn):
        try:
            if Looper.myLooper() == Looper.getMainLooper():
                fn()
                return
        except Exception:
            pass
        run_on_ui_thread(fn)

    def _start(self, greet):
        if self._unloaded or self._paused or not self._cfg.get("show", True):
            return
        if greet:
            self._greet_pending = True
        try:
            self._ensure_attached()
        except Exception as e:
            CLOG.log_error("START", "Attach error", e)
        if self._pet is None:
            run_on_ui_thread(lambda: self._start(greet), 700)
            return
        self._running = True
        self._last_tick = time.monotonic()
        self._start_sensor()
        self._schedule(16)

    def _start_sensor(self):
        if (
            self._sensor_listener is not None
            or not self._running
            or self._paused
            or self._unloaded
            or not self._cfg.get("shake", True)
            or self._pet is None
        ):
            return
        try:
            manager = self._pet.getContext().getSystemService(Context.SENSOR_SERVICE)
            sensor = manager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER) if manager is not None else None
            if sensor is None:
                return
            listener = ShakeListener(self)
            if manager.registerListener(listener, sensor, SensorManager.SENSOR_DELAY_UI):
                self._sensor_manager = manager
                self._sensor_listener = listener
                self._accel_prev = None
                self._shake_hits = []
                CLOG.log_info("SENSOR", "Sensor registered successfully")
        except Exception as e:
            CLOG.log_error("SENSOR", "Sensor start error", e)

    def _stop_sensor(self):
        manager = self._sensor_manager
        listener = self._sensor_listener
        self._sensor_manager = None
        self._sensor_listener = None
        self._tilt = 0.0
        if manager is None or listener is None:
            return
        try:
            manager.unregisterListener(listener)
        except Exception as e:
            CLOG.log_error("SENSOR", "Sensor stop error", e)

    def _ensure_attached(self):
        activity = self._get_safe_activity()
        if activity is None or activity.isFinishing():
            return
        decor = activity.getWindow().getDecorView()
        if (
            self._pet is not None
            and self._decor is not None
            and self._pet.getParent() is not None
            and self._decor.equals(decor)
        ):
            return
        self._detach_views()
        self._decor = decor
        self._build_views(activity)

    def _build_views(self, context):
        self._update_metrics()
        pet = ImageView(context)
        pet.setScaleType(ImageView.ScaleType.FIT_XY)
        pet.setClickable(True)
        self._touch_listener = PetTouchListener(self)
        pet.setOnTouchListener(self._touch_listener)
        self._decor.addView(pet, FrameLayout.LayoutParams(self._w, self._h))
        self._pet = pet

        bubble_layout = LinearLayout(context)
        bubble_layout.setOrientation(LinearLayout.VERTICAL)
        bubble_layout.setPadding(
            AndroidUtilities.dp(12), AndroidUtilities.dp(7),
            AndroidUtilities.dp(12), AndroidUtilities.dp(7),
        )
        bubble_layout.setVisibility(View.GONE)

        bubble_text = TextView(context)
        bubble_text.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 13.0)
        bubble_text.setMaxWidth(AndroidUtilities.dp(250))
        try:
            bubble_text.setTypeface(AndroidUtilities.bold())
        except Exception:
            pass
        bubble_layout.addView(bubble_text, LinearLayout.LayoutParams(-2, -2))

        bubble_subtext = TextView(context)
        bubble_subtext.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 10.5)
        bubble_subtext.setMaxWidth(AndroidUtilities.dp(250))
        bubble_subtext.setAlpha(0.55)
        bubble_subtext.setVisibility(View.GONE)
        bubble_layout.addView(bubble_subtext, LinearLayout.LayoutParams(-2, -2))

        controls = LinearLayout(context)
        controls.setOrientation(LinearLayout.HORIZONTAL)
        controls.setGravity(Gravity.CENTER)
        controls.setPadding(0, AndroidUtilities.dp(4), 0, 0)
        controls.setVisibility(View.GONE)

        def _make_btn(symbol: str, cb):
            btn = TextView(context)
            btn.setText(symbol)
            btn.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 14.0)
            btn.setPadding(AndroidUtilities.dp(8), 0, AndroidUtilities.dp(8), 0)
            btn.setOnClickListener(ViewClickListener(lambda _v: cb()))
            return btn

        controls.addView(_make_btn("⏮", lambda: self._dispatch_media_key(KeyEvent.KEYCODE_MEDIA_PREVIOUS)))
        controls.addView(_make_btn("⏯", lambda: self._dispatch_media_key(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE)))
        controls.addView(_make_btn("⏭", lambda: self._dispatch_media_key(KeyEvent.KEYCODE_MEDIA_NEXT)))
        bubble_layout.addView(controls, LinearLayout.LayoutParams(-1, -2))

        self._decor.addView(bubble_layout, FrameLayout.LayoutParams(-2, -2))
        self._bubble = bubble_layout
        self._bubble_text = bubble_text
        self._bubble_subtext = bubble_subtext
        self._media_controls_layout = controls
        self._bubble_visible = False
        self._frame_key = None
        self._pos_ready = False

    def _detach_views(self):
        self._restore_all()
        self._remove_poops()
        for view in list(self._particles):
            self._remove_view(view)
        self._particles = []
        self._remove_view(self._bubble)
        self._remove_view(self._pet)
        self._pet = None
        self._bubble = None
        self._bubble_text = None
        self._bubble_subtext = None
        self._media_controls_layout = None
        self._decor = None
        self._touch_listener = None
        self._poop_listener = None
        self._touch = None
        self._platform = None
        self._platforms = []
        if self._state in ("press", "drag", "pet", "hang", "peek"):
            self._state = "idle"

    def _remove_view(self, view):
        if view is None:
            return
        try:
            view.animate().cancel()
        except Exception:
            pass
        try:
            parent = view.getParent()
            if parent is not None:
                parent.removeView(view)
        except Exception:
            pass

    def _update_metrics(self):
        size = clamp(int(self._cfg.get("size", 1)), 0, len(SIZE_DP) - 1)
        self._unit = max(2, AndroidUtilities.dp(SIZE_DP[size]))
        self._w = GRID_W * self._unit
        self._h = GRID_H * self._unit

    def _rebuild_sprites(self):
        old_w, old_h = self._w, self._h
        self._frames = {}
        self._particle_bitmaps = {}
        self._frame_key = None
        self._update_metrics()
        if self._pet is None:
            return
        self._x += (old_w - self._w) / 2.0
        self._y += old_h - self._h
        lp = self._pet.getLayoutParams()
        lp.width = self._w
        lp.height = self._h
        self._pet.setLayoutParams(lp)
        self._hop(AndroidUtilities.dp(300))
        self._schedule(16)

    def _palette(self):
        idx = clamp(int(self._cfg.get("color", 0)), 0, len(PALETTES) - 1)
        if idx == 9:
            # Радужный динамический RGB
            hue = (time.monotonic() * 0.4) % 1.0
            r, g, b = [int(x * 255) for x in self._hsv_to_rgb(hue, 0.85, 0.95)]
            return ("RGB", (0xFF << 24) | (r << 16) | (g << 8) | b, 0xFFFFFFFF)
        if idx == 10:
            accent = Theme.getColor(Theme.key_actionBarDefault)
            return ("Хамелеон", accent, 0xFFFFFFFF)
        return PALETTES[idx]

    @staticmethod
    def _hsv_to_rgb(h, s, v):
        i = int(h * 6.0)
        f = (h * 6.0) - i
        p = v * (1.0 - s)
        q = v * (1.0 - s * f)
        t = v * (1.0 - s * (1.0 - f))
        i = i % 6
        if i == 0: return v, t, p
        if i == 1: return q, v, p
        if i == 2: return p, v, t
        if i == 3: return p, q, v
        if i == 4: return t, p, v
        if i == 5: return v, p, q
        return v, v, v

    def _get_frame(self, key):
        bmp = self._frames.get(key)
        if bmp is None:
            if len(self._frames) >= MAX_FRAME_CACHE:
                self._frames.pop(next(iter(self._frames)))
            bmp = self._render_frame(key)
            self._frames[key] = bmp
        return bmp

    def _render_frame(self, key):
        eyes, look, arms, legs, squash, blush, mouth, hat, fat_stage = key
        _, body_color, eye_color = self._palette()
        blush_color = mix_color(body_color, 0xFFFF4F79, 0.5)
        s = self._unit
        bmp = Bitmap.createBitmap(GRID_W * s, GRID_H * s, Bitmap.Config.ARGB_8888)
        canvas = Canvas(bmp)
        paint = Paint()

        def px(x0, y0, x1, y1, color):
            paint.setColor(jint(as_java_color(color)))
            canvas.drawRect(float(x0 * s), float(y0 * s), float(x1 * s), float(y1 * s), paint)

        # 4 стадии полноты «Обжоры»: 0: normal, 1: chubby, 2: fat, 3: balloon
        width_pad = [0, 1, 2, 3][fat_stage]
        left = max(0, 3 - width_pad)
        right = min(GRID_W, 15 + width_pad)
        top, bottom = 3, 10

        if squash > 0:
            left = max(0, left - 1)
            right = min(GRID_W, right + 1)
            top += 2
        elif squash < 0:
            top -= 1

        heights = {
            "stand": (2, 2, 2, 2),
            "walk1": (1, 2, 1, 2),
            "walk2": (2, 1, 2, 1),
            "dangle": (3, 3, 3, 3),
            "tuck": (1, 1, 1, 1),
        }.get(legs, (2, 2, 2, 2))

        col_coords = (left + 1, left + 3, right - 4, right - 2)
        for col, h in zip(col_coords, heights):
            px(col, bottom, col + 1, bottom + h, body_color)

        # Отрисовка рук (адаптируется под ширину тела)
        def arm(side, style):
            if style == "up":
                if side < 0:
                    px(left - 2, top - 1, left - 1, top + 3, body_color)
                    px(left - 1, top + 2, left, top + 3, body_color)
                else:
                    px(right + 1, top - 1, right + 2, top + 3, body_color)
                    px(right, top + 2, right + 1, top + 3, body_color)
            elif style == "tuck":
                if side < 0:
                    px(left - 1, top + 3, left, top + 5, body_color)
                else:
                    px(right, top + 3, right + 1, top + 5, body_color)
            else:
                if side < 0:
                    px(left - 2, top + 3, left, top + 5, body_color)
                else:
                    px(right, top + 3, right + 2, top + 5, body_color)

        left_arm = right_arm = arms
        if arms == "wave1":
            left_arm, right_arm = "up", "normal"
        elif arms == "wave2":
            left_arm, right_arm = "normal", "up"
        arm(-1, left_arm)
        arm(1, right_arm)

        px(left, top, right, bottom, body_color)

        # Глаза
        ey = top + 2
        for side, cx in ((-1, left + 3 + look), (1, right - 4 + look)):
            if eyes == "blink":
                px(cx, ey + 1, cx + 1, ey + 2, eye_color)
            elif eyes == "happy":
                px(cx - 1, ey + 1, cx, ey + 2, eye_color)
                px(cx, ey, cx + 1, ey + 1, eye_color)
                px(cx + 1, ey + 1, cx + 2, ey + 2, eye_color)
            elif eyes == "surprised":
                px(cx, ey - 1, cx + 1, ey + 2, eye_color)
            elif eyes == "dizzy":
                for dx, dy in ((-1, -1), (1, -1), (0, 0), (-1, 1), (1, 1)):
                    px(cx + dx, ey + dy, cx + dx + 1, ey + dy + 1, eye_color)
            elif eyes == "sleep":
                px(cx - 1, ey + 1, cx + 2, ey + 2, eye_color)
            elif eyes == "money":
                px(cx, ey - 1, cx + 1, ey + 2, 0xFF4CAF50)
                px(cx - 1, ey, cx + 2, ey + 1, 0xFF4CAF50)
            elif eyes == "angry":
                px(cx, ey, cx + 1, ey + 2, eye_color)
                brow = cx - 1 if side < 0 else cx + 1
                px(brow, ey - 1, brow + 1, ey, eye_color)
            else:
                px(cx, ey, cx + 1, ey + 2, eye_color)

            if blush or fat_stage >= 1:
                bx = cx - 2 if side < 0 else cx + 1
                px(bx, ey + 2, bx + 2, ey + 3, blush_color)

        # Рот
        if mouth:
            mx = (left + right) // 2
            my = ey + 2
            if mouth == "open":
                px(mx - 1, my, mx + 1, bottom - 1, eye_color)
            else:
                px(mx - 1, my, mx + 1, my + 1, eye_color)

        # Шапки
        if "Наушники DJ" in hat or (self._media == "music" and "Корона" not in hat):
            px(left + 2, top - 2, right - 2, top - 1, 0xFF2A2A2A)
            px(left - 1, top, left, top + 4, 0xFFFF4444)
            px(right, top, right + 1, top + 4, 0xFFFF4444)
        elif "Корона" in hat:
            gold = 0xFFFFD700
            px(left + 2, top - 2, right - 2, top, gold)
            px(left + 2, top - 3, left + 3, top - 2, gold)
            px((left + right) // 2, top - 3, (left + right) // 2 + 1, top - 2, gold)
            px(right - 3, top - 3, right - 2, top - 2, gold)
        elif "Шерлок" in hat:
            brown = 0xFF8D6E63
            px(left - 1, top - 1, right + 1, top, brown)
            px(left + 2, top - 3, right - 2, top - 1, brown)
        elif "Ночной колпак" in hat:
            blue = 0xFF5C6BC0
            px(left + 2, top - 3, right - 1, top, blue)
            px(right - 1, top - 2, right + 1, top - 1, 0xFFFFFFFF)
        elif "Кошачьи ушки" in hat:
            px(left + 1, top - 2, left + 3, top, body_color)
            px(right - 3, top - 2, right - 1, top, body_color)
            px(left + 2, top - 1, left + 3, top, 0xFFFF80AB)
            px(right - 2, top - 1, right - 1, top, 0xFFFF80AB)
        elif "Цилиндр" in hat:
            px(left, top - 1, right, top, 0xFF1A1A1A)
            px(left + 3, top - 4, right - 3, top - 1, 0xFF2A2A2A)
            px(right - 3, ey, right - 1, ey + 2, 0xFFFFD700)  # монокль
        elif "Каска" in hat:
            px(left - 1, top - 1, right + 1, top, 0xFFFFB300)
            px(left + 2, top - 3, right - 2, top - 1, 0xFFFFC107)
        elif "Очки Thug" in hat:
            px(left + 1, ey, right - 1, ey + 2, 0xFF111111)
            px(left + 3, ey + 1, left + 4, ey + 2, 0xFFFFFFFF)
            px(right - 4, ey + 1, right - 3, ey + 2, 0xFFFFFFFF)
        elif "Мага" in hat:
            px(left, top - 1, right, top, 0xFF4A148C)
            px(left + 4, top - 4, right - 4, top - 1, 0xFF7B1FA2)
            px((left + right) // 2, top - 5, (left + right) // 2 + 1, top - 4, 0xFFFFD700)

        return bmp

    def _particle_bitmap(self, kind, is_gold=False):
        cache_key = f"{kind}_gold" if is_gold else kind
        bmp = self._particle_bitmaps.get(cache_key)
        if bmp is not None:
            return bmp
        rows = PATTERNS[kind]
        if kind == "poop":
            colors = GOLD_POOP_COLORS if is_gold else POOP_COLORS
            s = max(2, int(self._unit * 0.9))
        else:
            colors = {"X": {"heart": HEART_COLOR, "zzz": ZZZ_COLOR, "spark": SPARK_COLOR, "note": NOTE_COLOR}[kind]}
            s = max(2, int(self._unit * 0.75))

        bmp = Bitmap.createBitmap(len(rows[0]) * s, len(rows) * s, Bitmap.Config.ARGB_8888)
        canvas = Canvas(bmp)
        paints = {ch: Paint() for ch in colors}
        for ch, color in colors.items():
            paints[ch].setColor(jint(as_java_color(color)))
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                p = paints.get(ch)
                if p is not None:
                    canvas.drawRect(float(x * s), float(y * s), float((x + 1) * s), float((y + 1) * s), p)
        self._particle_bitmaps[cache_key] = bmp
        return bmp

    def _reset_state(self):
        now = time.monotonic()
        self._state = "idle"
        self._x = 0.0
        self._y = 0.0
        self._vx = 0.0
        self._vy = 0.0
        self._pos_ready = False
        self._last_tick = now
        self._last_interaction = now
        self._next_action = now + 4.0
        self._next_blink = now + 2.0
        self._blink_until = 0.0
        self._look = 0
        self._expr = None
        self._expr_until = 0.0
        self._squash_until = 0.0
        self._wave_until = 0.0
        self._hop_active = False
        self._hop_off = 0.0
        self._hop_vy = 0.0
        self._walk_target = 0.0
        self._touch = None
        self._last_tap = 0.0
        self._recent_taps = []
        self._next_heart = 0.0
        self._next_z = 0.0
        self._bubble_visible = False
        self._bubble_fade_in = False
        self._bubble_until = 0.0
        self._bubble_gen = 0
        self._last_phrase = None
        self._bounds_cache = None
        self._bounds_time = 0.0
        self._attach_check = 0.0
        self._greet_pending = False
        self._next_eat = now + 20.0
        self._mouth_open_until = 0.0
        self._chew_until = 0.0
        self._media = None
        self._media_check = 0.0
        self._next_note = 0.0
        self._next_msg_react = 0.0
        self._next_sent_react = 0.0
        self._chat_dialog = 0
        self._next_chat_comment = now + 8.0
        self._rotation = 0
        self._accel_prev = None
        self._shake_hits = []
        self._shake_pending = None
        self._shake_dizzy = False
        self._tilt = 0.0
        self._slide_v = 0.0
        self._next_slide_say = 0.0
        self._platform = None
        self._platforms = []
        self._platform_scan = 0.0
        self._platform_moving = False
        self._walk_in = False
        self._hang_start = 0.0
        self._hang_until = 0.0
        self._peek_side = 0
        self._peek_pending = 0
        self._peek_phase = "hide"
        self._peek_phase_until = 0.0
        self._peek_end = 0.0
        self._peek_moving = False
        self._poop_due = 0.0
        self._poop_need = random.randint(*POOP_EVERY)
        self._platform_span = None
        self._next_peek = now + PEEK_AFTER
        self._is_singing = False
        self._current_lyric_idx = -1
        self._track_base_pos = 0.0
        self._track_base_time = 0.0
        self._track_is_playing = False
        self._last_checked_clip = ""
        self._clip_check_time = 0.0
        self._lastfm_check_time = 0.0

        self._battery_level = 100
        self._is_charging = False
        self._last_battery_check = 0.0
        self._nightstand_mode = False
        self._laser_active = False

    def _schedule(self, delay):
        if self._handler is None or self._tick_r is None:
            return
        self._handler.removeCallbacks(self._tick_r)
        self._handler.postDelayed(self._tick_r, int(delay))

    def _tick(self):
        if not self._running or self._paused:
            return
        try:
            self._step()
        except Exception as e:
            CLOG.log_error("TICK", "Tick loop error", e)
        if self._running and not self._paused:
            self._schedule(self._next_delay())

    def _next_delay(self):
        if self._pet is None:
            return 1000
        now = time.monotonic()
        if (
            self._state in ("press", "drag", "pet", "fly", "walk")
            or self._hop_active
            or self._bubble_fade_in
            or self._walk_in
            or self._laser_active
            or self._platform_moving
            or self._slide_v
            or self._shake_pending is not None
            or self._is_singing
            or now < self._squash_until
            or (self._expr == "dizzy" and now < self._expr_until)
        ):
            return 16
        if self._state in ("hang", "peek"):
            return 33
        if self._state == "sleep":
            return 250
        if self._media and self._state == "idle":
            return 33
        return 60

    def _dp(self, value):
        return float(AndroidUtilities.dp(value))

    def _bounds(self, now):
        if self._bounds_cache is not None and now - self._bounds_time < 0.4:
            return self._bounds_cache
        decor = self._decor
        width = decor.getWidth()
        height = decor.getHeight()
        top_inset = AndroidUtilities.statusBarHeight
        bottom_inset = AndroidUtilities.navigationBarHeight
        try:
            insets = decor.getRootWindowInsets()
            if insets is not None:
                top_inset = insets.getSystemWindowInsetTop()
                bottom_inset = insets.getSystemWindowInsetBottom()
        except Exception:
            pass
        try:
            display = decor.getDisplay()
            if display is not None:
                self._rotation = int(display.getRotation())
        except Exception:
            pass
        self._bounds_cache = (
            0.0,
            float(max(0, width - self._w)),
            float(top_inset),
            float(max(top_inset, height - bottom_inset - self._h)),
            width,
            height,
        )
        self._bounds_time = now
        return self._bounds_cache

    def _step(self):
        now = time.monotonic()
        dt = clamp(now - self._last_tick, 0.0, 0.05)
        self._last_tick = now

        if now >= self._attach_check:
            self._attach_check = now + 1.0
            self._ensure_attached()
            self._prune_eaten()
            if self._pet is not None and self._pos_ready:
                self._poll_chat(now)
                self._check_battery(now)
        if self._pet is None or self._decor is None:
            return
        if self._pos_ready:
            self._poll_media(now)
            self._poll_clipboard(now)
            self._sync_lyrics_timeline(now)
        if self._decor.getWidth() <= 0:
            return

        min_x, max_x, min_y, max_y, width, height = self._bounds(now)
        if not self._pos_ready:
            self._restore_position(min_x, max_x, min_y, max_y)
            self._pos_ready = True
            if self._greet_pending:
                self._greet_pending = False
                self._hop(self._dp(420))
                self._say("hello")

        if self._is_charging and (self._rotation in (Surface.ROTATION_90, Surface.ROTATION_270)):
            if not self._nightstand_mode:
                self._nightstand_mode = True
                self._x = max_x - self._dp(30)
                self._y = min_y + self._dp(10)
                self._state = "sleep"
                self._set_expr("sleep", 9999.0)
        else:
            self._nightstand_mode = False

        gravity = bool(self._cfg.get("gravity", False))
        state = self._state

        if state == "press" and self._touch is not None and now - self._touch["t0"] >= 0.4:
            self._start_pet(now)
            state = self._state

        if self._shake_pending is not None and state not in ("press", "drag", "pet"):
            ax, ay = self._shake_pending
            self._shake_pending = None
            self._apply_shake_vector(ax, ay)
            state = self._state

        if state == "pet":
            if now >= self._next_heart:
                self._next_heart = now + 0.45
                self._spawn_particle("heart")
                self._haptic(4)
                if self._cfg.get("audio_sfx", True):
                    RetroAudio.purr()
        elif state == "fly":
            self._step_fly(dt, now, gravity, min_x, max_x, min_y, max_y)
        elif state == "hang":
            self._step_hang(now, gravity, min_x, max_x, min_y)
        elif state == "peek":
            self._step_peek(dt, now, width)
        elif state in ("idle", "walk", "sleep"):
            self._step_ground(dt, now, gravity, min_x, max_x, min_y, max_y)

        if self._hop_active:
            self._hop_off += self._hop_vy * dt
            self._hop_vy += self._dp(2600) * dt
            if self._hop_off >= 0.0:
                self._hop_off = 0.0
                self._hop_vy = 0.0
                self._hop_active = False
                self._squash_until = now + 0.1

        self._render(now)
        self._update_bubble(now, width, min_y)

    def _check_battery(self, now):
        if not self._cfg.get("battery_react", True) or now < self._last_battery_check:
            return
        self._last_battery_check = now + 15.0
        try:
            ctx = self._pet.getContext() if self._pet else LaunchActivity.instance
            if not ctx:
                return
            bm = ctx.getSystemService(Context.BATTERY_SERVICE)
            if not bm:
                return
            level = int(bm.getIntProperty(4))
            charging = bool(getattr(bm, "isCharging", lambda: False)())

            was_charging = self._is_charging
            self._battery_level = level
            self._is_charging = charging

            if charging and not was_charging:
                self._say("charging", force=True)
                self._hop(self._dp(450))
                for _ in range(4):
                    self._spawn_particle("spark")
                RetroAudio.magic()
            elif not charging and level < 15 and random.random() < 0.2:
                self._say("battery_low")
        except Exception:
            pass

    def _poll_clipboard(self, now):
        if not self._cfg.get("clipboard_sync", True) or now < self._clip_check_time:
            return
        self._clip_check_time = now + 2.5
        ctx = self._pet.getContext() if self._pet else LaunchActivity.instance
        if not ctx:
            return
        try:
            cm = ctx.getSystemService(Context.CLIPBOARD_SERVICE)
            if not cm or not cm.hasPrimaryClip():
                return
            clip = cm.getPrimaryClip()
            if not clip or clip.getItemCount() <= 0:
                return
            clip_text = str(clip.getItemAt(0).getText() or "").strip()
            if not clip_text or clip_text == self._last_checked_clip:
                return
            self._last_checked_clip = clip_text

            if "soundcloud.com/" in clip_text:
                self._add_debug_log(f"SoundCloud ссылка из буфера: {clip_text[:35]}")

                def _on_resolved(res):
                    if res:
                        a, t = res
                        run_on_ui_thread(lambda: self._start_custom_song(f"{a} - {t}"))

                threading.Thread(
                    target=lambda: _on_resolved(self._lyrics_helper.resolve_soundcloud_url(clip_text)),
                    daemon=True,
                ).start()
                return

            if " - " in clip_text and len(clip_text) < 70:
                am = ctx.getSystemService(Context.AUDIO_SERVICE)
                if am and am.isMusicActive():
                    self._start_custom_song(clip_text)
        except Exception:
            pass

    def _fat_stage(self):
        c = len(self._eaten)
        if c <= 1: return 0
        if c <= 3: return 1
        if c <= 5: return 2
        return 3

    def _step_ground(self, dt, now, gravity, min_x, max_x, min_y, max_y):
        self._walk_in = False
        fat = self._fat_stage()
        speed_factor = [1.0, 0.85, 0.65, 0.45][fat]

        if self._state != "walk":
            if self._x < min_x - 0.5 or self._x > max_x + 0.5:
                step = self._dp(60) * dt * speed_factor
                if self._x < min_x:
                    self._x = min(min_x, self._x + step)
                    self._look = 1
                else:
                    self._x = max(max_x, self._x - step)
                    self._look = -1
                self._walk_in = True
            else:
                self._x = clamp(self._x, min_x, max_x)

        self._platform_moving = False
        if gravity:
            if self._platform is not None:
                if not self._follow_platform(min_y, max_y):
                    self._fall(self._dp(42) * self._look if self._state == "walk" else 0.0)
                    return
            elif self._y < max_y - 0.5 and not self._hop_active:
                self._fall(0.0)
                return
            else:
                self._y = min(self._y, max_y)
                # Если упал на пол при гравитации — пробует подтянуться наверх
                if random.random() < 0.02 and not self._hop_active and self._platforms:
                    self._hop(self._dp(500))
            if self._step_slide(dt, now, min_x, max_x):
                return
        else:
            self._y = clamp(self._y, min_y, max_y)
            self._slide_v = 0.0

        if self._state == "walk":
            direction = 1 if self._walk_target > self._x else -1
            self._look = direction
            self._x += direction * self._dp(42) * dt * speed_factor
            reached = (direction > 0 and self._x >= self._walk_target) or (direction < 0 and self._x <= self._walk_target)
            hit_edge = (direction < 0 and self._x <= min_x) or (direction > 0 and self._x >= max_x)
            if reached or hit_edge:
                self._x = clamp(self._x, min_x, max_x)
                self._state = "idle"
                self._next_action = now + random.uniform(2.5, 6.0)
                side = self._peek_pending
                self._peek_pending = 0
                edge = self._dp(4)
                if side and ((side < 0 and self._x <= min_x + edge) or (side > 0 and self._x >= max_x - edge)):
                    self._start_peek(now, side)
                    return
                self._save_position()
            return

        if self._state == "sleep":
            if now >= self._next_z:
                self._next_z = now + 1.6
                self._spawn_particle("zzz")
            return

        if now >= self._next_blink:
            self._blink_until = now + 0.13
            self._next_blink = now + (0.35 if random.random() < 0.15 else random.uniform(2.0, 5.5))

        sleep_idx = clamp(int(self._cfg.get("sleep", 1)), 0, len(SLEEP_SECONDS) - 1)
        timeout = SLEEP_SECONDS[sleep_idx]
        if (
            timeout
            and now - self._last_interaction > timeout
            and not self._hop_active
            and not self._media
            and not self._walk_in
        ):
            self._state = "sleep"
            self._look = 0
            self._next_z = now + 0.6
            self._hide_bubble()
            return

        if self._poop_due and now >= self._poop_due and not self._hop_active and not self._walk_in:
            self._do_poop(now, min_x, max_x)
            return

        if self._media:
            if now >= self._next_note:
                self._next_note = now + (0.75 if self._media == "music" else 1.4)
                self._spawn_particle("note")
            return

        if now < self._next_action or self._hop_active or self._walk_in or self._is_singing or self._laser_active:
            return
        self._next_action = now + random.uniform(3.5, 9.0)

        if (
            self._cfg.get("eat", True)
            and now >= self._next_eat
            and len(self._eaten) < MAX_EATEN
            and random.random() < 0.35
        ):
            if self._try_eat(now, min_y):
                return
            self._next_eat = now + 8.0

        roll = random.random()
        if not self._cfg.get("wander", True):
            if roll < 0.5:
                self._look = random.choice((-1, 0, 1))
            return

        if (
            self._platform is None
            and now >= self._next_peek
            and now - self._last_interaction > PEEK_AFTER
            and roll < 0.3
        ):
            side = -1 if self._x - min_x < max_x - self._x else 1
            self._walk_target = min_x if side < 0 else max_x
            self._peek_pending = side
            self._state = "walk"
            return

        if roll < 0.38:
            distance = random.uniform(self._dp(40), self._dp(150)) * random.choice((-1, 1))
            lo, hi = min_x, max_x
            if self._platform is not None and self._platform_span is not None:
                x0, x1 = self._platform_span
                lo = max(lo, x0 - self._unit * 4)
                hi = min(hi, x1 - self._unit * 14)
            target = clamp(self._x + distance, lo, hi)
            if abs(target - self._x) > self._dp(12):
                self._walk_target = target
                self._state = "walk"
        elif roll < 0.58:
            self._look = random.choice((-1, 0, 1))
        elif roll < 0.72:
            self._say("idle")
        elif roll < 0.84:
            self._hop(self._dp(360))
        else:
            self._wave_until = now + 1.6

    def _fall(self, vx):
        self._state = "fly"
        self._platform = None
        self._platforms = []
        self._platform_scan = 0.0
        self._vx = vx + self._slide_v
        self._vy = 0.0
        self._slide_v = 0.0

    def _tilt_accel(self):
        tilt = self._tilt if self._sensor_listener is not None else 0.0
        if abs(tilt) <= TILT_DEAD:
            return 0.0
        return (tilt - math.copysign(TILT_DEAD, tilt)) * self._dp(2200)

    def _step_slide(self, dt, now, min_x, max_x):
        if not self._hop_active:
            self._slide_v += self._tilt_accel() * dt
        self._slide_v *= math.exp(-2.5 * dt)
        if abs(self._slide_v) < self._dp(6):
            self._slide_v = 0.0
            return False
        self._x += self._slide_v * dt
        if self._x < min_x or self._x > max_x:
            self._x = clamp(self._x, min_x, max_x)
            if abs(self._slide_v) > self._dp(150):
                self._squash_until = now + 0.12
                self._haptic(3)
            self._slide_v = 0.0
            return False
        if abs(self._slide_v) < self._dp(60):
            return False
        self._state = "idle"
        self._peek_pending = 0
        self._look = 1 if self._slide_v > 0 else -1
        if now >= self._next_slide_say:
            self._next_slide_say = now + 8.0
            if random.random() < 0.5:
                self._say("slide")
        return True

    def _feet_on(self, x0, x1):
        feet0 = self._x + self._unit * 4
        feet1 = self._x + self._unit * 14
        return min(feet1, x1) - max(feet0, x0) >= self._unit * 2

    def _platform_rect(self, view, kind, dloc=None):
        try:
            if view is None or not view.isAttachedToWindow() or view.getVisibility() != View.VISIBLE:
                return None
            if dloc is None:
                dloc = jarray(jint)([0, 0])
                self._decor.getLocationInWindow(dloc)
            loc = jarray(jint)([0, 0])
            view.getLocationInWindow(loc)
            x = float(loc[0] - dloc[0])
            y = float(loc[1] - dloc[1])
            if kind == "msg":
                left = view.getBackgroundDrawableLeft()
                right = view.getBackgroundDrawableRight()
                top = view.getBackgroundDrawableTop()
                if right - left < self._dp(40):
                    return None
                return (x + left, x + right, y + top)
            return (x, x + view.getWidth(), y)
        except Exception:
            return None

    # Сканирование платформ на ВСЕХ экранах Telegram
    def _scan_platforms(self, min_y, max_y):
        result = []
        try:
            dloc = jarray(jint)([0, 0])
            self._decor.getLocationInWindow(dloc)
            views = []

            fragment = get_last_fragment()
            if fragment is not None and isinstance(fragment, ChatActivity):
                enter = fragment.getChatActivityEnterView()
                if enter is not None:
                    views.append((enter, "input"))
                listing = fragment.getChatListView()
                if listing is not None and ChatMessageCell is not None:
                    for i in range(listing.getChildCount()):
                        child = listing.getChildAt(i)
                        if child is not None and isinstance(child, ChatMessageCell):
                            views.append((child, "msg"))
            else:
                # Настройки, каналы, профиль: сканируем карточки и элементы списка
                stack = [self._decor]
                visited = 0
                while stack and visited < 400:
                    v = stack.pop()
                    visited += 1
                    if v is None or v.getVisibility() != View.VISIBLE:
                        continue
                    if isinstance(v, RecyclerView):
                        for i in range(v.getChildCount()):
                            ch = v.getChildAt(i)
                            if ch is not None and ch.getHeight() > self._dp(24):
                                views.append((ch, "card"))
                        break
                    count = v.getChildCount() if isinstance(v, ViewGroup) else 0
                    for i in range(count):
                        child = v.getChildAt(i)
                        if child is not None:
                            stack.append(child)

            lowest = min_y - self._unit * 2 + self._h
            highest = max_y + self._h
            for view, kind in views:
                rect = self._platform_rect(view, kind, dloc)
                if rect is None:
                    continue
                x0, x1, top = rect
                if x1 - x0 >= self._w * 0.6 and lowest <= top <= highest:
                    result.append((view, kind, x0, x1, top))
        except Exception as e:
            CLOG.log_error("PLATFORM", "Scan error", e)
        return result

    def _follow_platform(self, min_y, max_y):
        view, kind = self._platform
        rect = self._platform_rect(view, kind)
        if rect is None:
            return False
        x0, x1, top = rect
        if not self._feet_on(x0, x1):
            return False
        y = top - self._h
        if y < min_y - self._unit * 2 or y > max_y:
            return False
        self._platform_moving = abs(y - self._y) > 0.5
        self._platform_span = (x0, x1)
        self._y = y
        return True

    def _platform_landing(self, now, old_y, min_y, max_y):
        if now >= self._platform_scan:
            self._platform_scan = now + 0.25
            self._platforms = self._scan_platforms(min_y, max_y)
        prev_bottom = old_y + self._h
        new_bottom = self._y + self._h
        best = None
        for item in self._platforms:
            top = item[4]
            if prev_bottom <= top + 1 and new_bottom >= top and self._feet_on(item[2], item[3]):
                if best is None or top < best[4]:
                    best = item
        if best is None:
            return None
        view, kind, x0, x1, top = best
        speed = self._vy
        self._y = top - self._h
        if speed > self._dp(380):
            self._vy = -speed * 0.42
            self._vx *= 0.75
            self._squash_until = now + 0.1
        else:
            self._platform_span = (x0, x1)
            self._land(now, (view, kind))
        return speed

    def _step_fly(self, dt, now, gravity, min_x, max_x, min_y, max_y):
        old_y = self._y
        self._x += self._vx * dt
        self._y += self._vy * dt
        if gravity:
            self._vy += self._dp(2600) * dt
            self._vx *= math.exp(-0.35 * dt)
            self._vx += self._tilt_accel() * dt
        else:
            friction = math.exp(-2.0 * dt)
            self._vx *= friction
            self._vy *= friction

        impact = 0.0
        if self._x < min_x:
            self._x = min_x
            impact = max(impact, abs(self._vx))
            self._vx = abs(self._vx) * 0.55
        elif self._x > max_x:
            self._x = max_x
            impact = max(impact, abs(self._vx))
            self._vx = -abs(self._vx) * 0.55

        landed = None
        if gravity and self._vy > 0 and self._y > old_y:
            landed = self._platform_landing(now, old_y, min_y, max_y)
        if landed is not None:
            impact = max(impact, landed)
        elif self._y < min_y:
            if self._vy < -self._dp(250) and not self._shake_dizzy:
                self._start_hang(now, min_y)
                return
            self._y = min_y
            impact = max(impact, abs(self._vy))
            self._vy = abs(self._vy) * 0.55
        elif self._y > max_y:
            self._y = max_y
            impact = max(impact, abs(self._vy))
            if gravity and self._vy < self._dp(380):
                self._land(now)
            else:
                self._vy = -abs(self._vy) * (0.42 if gravity else 0.55)
                self._vx *= 0.75 if gravity else 1.0
                self._squash_until = now + 0.1

        if impact > self._dp(2300):
            self._set_expr("dizzy", 2.6)
            self._say("dizzy")
            self._haptic(1)
            RetroAudio.fall()
        elif impact > self._dp(900):
            self._haptic(3)

        if self._state == "fly" and not gravity and math.hypot(self._vx, self._vy) < self._dp(45):
            self._land(now)

    def _land(self, now, platform=None):
        self._state = "idle"
        self._vx = 0.0
        self._vy = 0.0
        self._platform = platform
        self._platforms = []
        self._squash_until = now + 0.14
        self._next_action = now + random.uniform(2.0, 5.0)
        if self._fat_stage() == 3:
            self._haptic(1)
            RetroAudio.fall()
        if self._shake_dizzy:
            self._shake_dizzy = False
            self._set_expr("dizzy", 3.0)
            self._say("dizzy")
        self._save_position()

    def _on_accel(self, ax, ay, az):
        if not self._running or self._paused or self._pet is None:
            return
        now = time.monotonic()
        prev = self._accel_prev
        self._accel_prev = (ax, ay, az)
        if prev is not None:
            jerk = math.sqrt((ax - prev[0]) ** 2 + (ay - prev[1]) ** 2 + (az - prev[2]) ** 2)
            if self._state in ("press", "drag", "pet") and jerk > 16.0:
                self._shake_hits = []
                self._trigger_magic_8ball(now)
                return

            if jerk > SHAKE_JERK and self._state not in ("press", "drag", "pet"):
                hits = [t for t in self._shake_hits if now - t < SHAKE_WINDOW]
                hits.append(now)
                if len(hits) >= SHAKE_HITS:
                    hits = []
                    self._shake_pending = (ax - prev[0], ay - prev[1])
                    self._schedule(0)
                self._shake_hits = hits

        rotation = self._rotation
        if rotation == Surface.ROTATION_90:
            sx, sy = ay, ax
        elif rotation == Surface.ROTATION_180:
            sx, sy = ax, -ay
        elif rotation == Surface.ROTATION_270:
            sx, sy = -ay, -ax
        else:
            sx, sy = -ax, ay
        raw = clamp(sx / EARTH_G, -1.0, 1.0) if sy > 2.0 else 0.0
        self._tilt = self._tilt * 0.7 + raw * 0.3

    def _trigger_magic_8ball(self, now):
        self._state = "idle"
        self._touch = None
        self._set_expr("dizzy", 2.5)
        fortune = random.choice(FORTUNES)
        self._say(f"🎱 {fortune}", force=True)
        self._haptic(1)
        RetroAudio.magic()
        for _ in range(4):
            self._spawn_particle("spark")

    def _apply_shake_vector(self, d_ax: float, d_ay: float):
        self._state = "fly"
        speed = math.hypot(d_ax, d_ay)
        norm = max(1.0, speed)
        power = min(self._dp(1200 + speed * 60.0), self._dp(3400))
        self._vx = (-d_ax / norm) * power
        self._vy = (d_ay / norm) * power
        self._shake_dizzy = True
        self._set_expr("surprised", 1.0)
        self._haptic(1)
        self._say("shake")
        RetroAudio.fall()

    def _start_hang(self, now, min_y):
        self._state = "hang"
        self._vx = 0.0
        self._vy = 0.0
        self._y = min_y - self._unit * 2
        self._hang_start = now
        self._hang_until = now + random.uniform(2.0, 3.5)
        self._haptic(3)
        self._say("hang")

    def _step_hang(self, now, gravity, min_x, max_x, min_y):
        self._x = clamp(self._x, min_x, max_x)
        self._y = min_y - self._unit * 2
        if now < self._hang_until:
            return
        self._state = "fly"
        self._vx = 0.0
        self._vy = self._dp(150) if gravity else self._dp(700)
        self._set_expr("surprised", 0.8)
        self._haptic(3)
        self._say("hang_fall")

    def _start_peek(self, now, side):
        self._state = "peek"
        self._peek_side = side
        self._peek_phase = "hide"
        self._peek_phase_until = now + random.uniform(3.0, 6.0)
        self._peek_end = now + random.uniform(30.0, 60.0)
        self._look = side

    def _step_peek(self, dt, now, width):
        phase = self._peek_phase
        units = PEEK_OUT_UNITS if phase == "out" else PEEK_HIDDEN_UNITS
        target = float(width - units * self._unit) if self._peek_side > 0 else float(units * self._unit - self._w)
        step = self._dp(50) * dt
        self._peek_moving = abs(target - self._x) > 0.5
        if self._peek_moving:
            self._x = min(target, self._x + step) if target > self._x else max(target, self._x - step)
        self._look = self._peek_side if (phase == "hide" and self._peek_moving) else -self._peek_side
        if now >= self._next_blink:
            self._blink_until = now + 0.13
            self._next_blink = now + random.uniform(2.0, 5.5)
        if now < self._peek_phase_until or self._peek_moving:
            return
        if now >= self._peek_end:
            self._end_peek(now)
            return
        if phase == "hide":
            self._peek_phase = "out"
            self._peek_phase_until = now + random.uniform(1.5, 2.8)
            self._say("peek")
        else:
            self._peek_phase = "hide"
            self._peek_phase_until = now + random.uniform(3.0, 7.0)

    def _end_peek(self, now):
        side = self._peek_side
        self._peek_side = 0
        self._peek_moving = False
        self._next_peek = now + random.uniform(60.0, 120.0)
        self._state = "idle"
        if self._bounds_cache is None or not side:
            return
        min_x, max_x = self._bounds_cache[:2]
        inside = min_x + self._dp(30) if side < 0 else max_x - self._dp(30)
        self._walk_target = clamp(inside, min_x, max_x)
        self._state = "walk"
        self._next_action = now + random.uniform(3.0, 6.0)

    def _compose(self, now):
        eyes = "open"
        look = self._look
        arms = "normal"
        legs = "stand"
        squash = 0
        blush = False
        mouth = None
        state = self._state
        fat = self._fat_stage()

        if state in ("drag", "fly"):
            eyes, arms, legs = "surprised", "up", "dangle"
        elif state == "pet":
            eyes, blush = "happy", True
            squash = 1 if int(now * 3) % 2 else 0
            look = 0
        elif state == "sleep":
            eyes, arms, legs, look = "sleep", "tuck", "tuck", 0
        elif state == "walk":
            legs = "walk1" if int(now * 7) % 2 else "walk2"
        elif state == "press":
            squash = 1
        elif state == "hang":
            eyes = "surprised" if now - self._hang_start < 0.5 else "open"
            arms, legs = "up", "dangle"

        # Руки машут при тесте или победном жесте
        if state in ("idle", "walk") and now < self._wave_until:
            arms = "wave1" if int(now * 6) % 2 else "wave2"

        if state == "idle" and self._media and not self._hop_active:
            beat = int(now * 4) % 2
            eyes = "happy"
            arms = "wave1" if beat else "wave2"
            legs = "walk1" if beat else "walk2"
            squash = 1 if beat else 0

        if now < self._expr_until and self._expr and state != "sleep":
            eyes = self._expr
            if self._expr == "happy":
                blush = True
        if now < self._squash_until and squash == 0:
            squash = 1
        if eyes == "open" and state in ("idle", "walk", "peek", "hang") and now < self._blink_until:
            eyes = "blink"

        if state != "sleep":
            if self._is_singing:
                mouth = "open" if int(now * 7) % 2 else "chew"
            elif now < self._mouth_open_until:
                mouth = "open"
            elif now < self._chew_until and int(now * 6) % 2:
                mouth = "chew"

        hat_idx = clamp(int(self._cfg.get("hat", 0)), 0, len(HATS) - 1)
        hat = HATS[hat_idx]
        return (eyes, look, arms, legs, squash, blush, mouth, hat, fat)

    def _render(self, now):
        key = self._compose(now)
        if key != self._frame_key:
            self._frame_key = key
            self._pet.setImageBitmap(self._get_frame(key))
        self._pet.setTranslationX(float(self._x))
        self._pet.setTranslationY(float(self._y + self._hop_off))

        rotation = 0.0
        if self._state == "fly":
            rotation = clamp(self._vx / self._dp(70), -25.0, 25.0)
        elif self._state == "hang":
            rotation = math.sin((now - self._hang_start) * 3.0) * 6.0
        elif self._is_singing:
            rotation = math.sin(now * 8.0) * 7.0
        elif self._media and self._state == "idle" and not self._hop_active:
            rotation = math.sin(now * math.pi * 2.0) * 6.0
        self._pet.setRotation(float(rotation))

    def _restore_position(self, min_x, max_x, min_y, max_y):
        fx = self.get_setting("pos_x", None)
        fy = self.get_setting("pos_y", None)
        try:
            fx, fy = float(fx) / 1000.0, float(fy) / 1000.0
        except Exception:
            fx, fy = 0.8, 0.72
        self._x = min_x + (max_x - min_x) * clamp(fx, 0.0, 1.0)
        self._y = min_y + (max_y - min_y) * clamp(fy, 0.0, 1.0)

    def _save_position(self):
        if self._bounds_cache is None:
            return
        min_x, max_x, min_y, max_y = self._bounds_cache[:4]
        fx = (self._x - min_x) / max(1.0, max_x - min_x)
        fy = (self._y - min_y) / max(1.0, max_y - min_y)
        try:
            self.set_setting("pos_x", int(clamp(fx, 0.0, 1.0) * 1000))
            self.set_setting("pos_y", int(clamp(fy, 0.0, 1.0) * 1000))
        except Exception as e:
            CLOG.log_error("POS", "Save position error", e)

    def _recenter(self):
        if not self._cfg.get("show", True):
            self._cfg["show"] = True
            self.set_setting("show", True)
        self._start(greet=False)
        if self._decor is None or self._decor.getWidth() <= 0:
            return
        now = time.monotonic()
        min_x, max_x, min_y, max_y = self._bounds(now)[:4]
        self._x = (min_x + max_x) / 2.0
        self._y = (min_y + max_y) / 2.0
        self._pos_ready = True
        self._state = "idle"
        self._vx = self._vy = 0.0
        self._slide_v = 0.0
        self._hop(self._dp(500))
        for _ in range(3):
            self._spawn_particle("spark")
        self._say("hello")
        self._save_position()

    # Мультитач: лазерная указка двумя пальцами
    def _on_touch(self, event):
        action = event.getActionMasked()
        rx, ry = float(event.getRawX()), float(event.getRawY())
        now = time.monotonic()
        pointer_count = event.getPointerCount()

        if pointer_count >= 2:
            self._laser_active = True
            try:
                lx = float(event.getX(1))
                ly = float(event.getY(1))
            except Exception:
                lx, ly = rx, ry
            self._run_towards(lx, ly)
            if random.random() < 0.15:
                self._say("laser_chase")
            return True
        else:
            if self._laser_active:
                self._laser_active = False

        if action == MotionEvent.ACTION_DOWN:
            self._last_interaction = now
            self._touch = {
                "x0": rx, "y0": ry, "t0": now,
                "ox": rx - self._x, "oy": ry - self._y,
                "hist": [(now, rx, ry)],
                "anchor": rx, "dir": 0, "vx": 0.0,
            }
            self._hop_active = False
            self._vx = self._vy = self._slide_v = 0.0
            self._state = "press"
            self._schedule(0)
            return True

        touch = self._touch
        if touch is None:
            return False

        if action == MotionEvent.ACTION_MOVE:
            hist = touch["hist"]
            hist.append((now, rx, ry))
            while len(hist) > 2 and now - hist[0][0] > 0.1:
                hist.pop(0)
            if self._state == "press":
                if math.hypot(rx - touch["x0"], ry - touch["y0"]) > self._dp(8):
                    self._state = "drag"
                    self._platform = None
                    self._haptic(3)
                    self._say("drag")
            if self._state == "drag":
                width = self._decor.getWidth() if self._decor is not None else 0
                height = self._decor.getHeight() if self._decor is not None else 0
                self._x = clamp(rx - touch["ox"], -self._w * 0.3, width - self._w * 0.7)
                self._y = clamp(ry - touch["oy"], 0.0, height - self._h * 0.5)
            elif self._state == "pet":
                dx = rx - touch["anchor"]
                if abs(dx) > self._dp(10):
                    direction = 1 if dx > 0 else -1
                    if touch["dir"] and direction != touch["dir"]:
                        self._stroke()
                    touch["dir"] = direction
                    touch["anchor"] = rx
            return True

        if action in (MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL):
            self._touch = None
            self._last_interaction = now
            state = self._state
            if state == "drag":
                self._release_drag(now, touch, action == MotionEvent.ACTION_CANCEL)
            elif state == "pet":
                self._end_pet(now)
            elif state == "press" and action == MotionEvent.ACTION_UP:
                self._state = "idle"
                self._tap(now)
            self._schedule(0)
            return True
        return True

    def _run_towards(self, tx: float, ty: float):
        self._look = 1 if tx > self._x else -1
        self._walk_target = tx
        self._state = "walk"
        self._set_expr("surprised", 0.5)

    def _release_drag(self, now, touch, cancelled):
        vx = vy = 0.0
        hist = touch["hist"]
        if not cancelled and len(hist) >= 2:
            t0, x0, y0 = hist[0]
            t1, x1, y1 = hist[-1]
            if t1 - t0 > 0.005 and now - t1 < 0.08:
                vx = (x1 - x0) / (t1 - t0)
                vy = (y1 - y0) / (t1 - t0)
        limit = self._dp(6000)
        vx = clamp(vx, -limit, limit)
        vy = clamp(vy, -limit, limit)
        speed = math.hypot(vx, vy)
        min_y = self._bounds_cache[2] if self._bounds_cache is not None else None

        if speed <= self._dp(700) and min_y is not None and self._y <= min_y + self._unit * 2:
            self._start_hang(now, min_y)
        elif speed > self._dp(700) or self._cfg.get("gravity", False):
            self._state = "fly"
            self._vx = vx
            self._vy = vy
            if speed > self._dp(2600):
                self._say("throw")
        else:
            self._state = "idle"
            self._save_position()

    def _tap(self, now):
        if self._eaten:
            self._spit_all(now)
            return
        if now - self._last_tap < 0.32:
            self._last_tap = 0.0
            self._hop(self._dp(720))
            self._set_expr("happy", 1.3)
            RetroAudio.jump()
            for _ in range(3):
                self._spawn_particle("spark")
            self._say("jump")
            return
        self._last_tap = now
        self._recent_taps = [t for t in self._recent_taps if now - t < 2.5] + [now]
        if len(self._recent_taps) >= 6:
            self._recent_taps = []
            self._set_expr("angry", 2.5)
            self._say("annoyed", force=True)
            self._haptic(1)
            return
        self._squash_until = now + 0.12
        self._set_expr("surprised", 0.45)
        self._hop(self._dp(330))
        self._haptic(3)
        RetroAudio.jump()
        self._say("tap")

    def _start_pet(self, now):
        self._state = "pet"
        self._next_heart = now + 0.1
        self._haptic(0)

    def _stroke(self):
        self._spawn_particle("heart")
        self._haptic(4)
        if self._cfg.get("audio_sfx", True):
            RetroAudio.purr()

    def _end_pet(self, now):
        self._state = "idle"
        self._set_expr("happy", 2.2)
        try:
            count = int(self.get_setting("pets_count", 0) or 0) + 1
            self.set_setting("pets_count", count)
        except Exception:
            pass
        self._say("pet")

    # Исправленная логика Telegram уведомлений: фильтрация своих сообщений
    def _on_notification(self, id, account, args):
        now = time.monotonic()
        ev_read = getattr(NotificationCenter, "messagesRead", -999)
        ev_del = getattr(NotificationCenter, "messagesDeleted", -999)

        if id == ev_read:
            if self._state in ("idle", "walk"):
                self._hop(self._dp(380))
                self._spawn_particle("spark")
                self._say("read")
                RetroAudio.jump()
            return

        if id == ev_del:
            if self._state in ("idle", "walk"):
                self._set_expr("surprised", 2.0)
                self._say("deleted")
            return

        if id != getattr(NotificationCenter, "didReceiveNewMessages", 1):
            return
        if args is None or len(args) < 2:
            return

        dialog_id = int(args[0])
        messages = args[1]
        texts = []
        incoming = False

        my_uid = 0
        try:
            my_uid = UserConfig.getInstance(account).getClientUserId()
        except Exception:
            pass

        # Если это чат с самим собой (Избранное) — входящих от чужих тут быть не может!
        if dialog_id == my_uid:
            return

        sender_name = None
        for i in range(min(int(messages.size()), MAX_SCAN_MESSAGES)):
            message = messages.get(i)
            if message is None or message.isOut():
                continue

            # Проверяем ID отправителя: если это наше сообщение с другого устройства — игнорируем
            from_uid = 0
            if message.messageOwner and message.messageOwner.from_id:
                from_uid = getattr(message.messageOwner.from_id, "user_id", 0)
            if from_uid == my_uid:
                continue

            incoming = True
            text = message.messageOwner.message if message.messageOwner is not None else None
            if text:
                t_str = str(text)
                texts.append(t_str[:MAX_KEYWORD_TEXT].lower())
                if "soundcloud.com/" in t_str:
                    threading.Thread(
                        target=lambda u=t_str: self._on_soundcloud_chat_link(u),
                        daemon=True,
                    ).start()

        if not incoming:
            return

        in_chat = dialog_id == self._chat_dialog
        self._react_incoming(self._match_keyword(texts), in_chat, sender_name)

    def _on_soundcloud_chat_link(self, raw_text: str):
        m = re.search(r"https?://(?:on\.)?soundcloud\.com/\S+", raw_text)
        if m:
            res = self._lyrics_helper.resolve_soundcloud_url(m.group(0))
            if res:
                a, t = res
                run_on_ui_thread(lambda: self._start_custom_song(f"{a} - {t}"))

    def _match_keyword(self, texts):
        for mood, pattern in KEYWORDS:
            for text in texts:
                if pattern.search(text):
                    return mood
        return None

    def _react_incoming(self, mood, in_chat, sender_name=None):
        now = time.monotonic()
        if mood is None and in_chat:
            return
        if now < self._next_msg_react:
            return
        self._next_msg_react = now + (3.0 if mood else 6.0)

        if mood in ("love", "compliment"):
            self._set_expr("happy", 2.2)
            for _ in range(3):
                self._spawn_particle("heart")
            self._say(mood)
        elif mood == "laugh":
            self._set_expr("happy", 1.6)
            self._hop(self._dp(420))
            self._say("laugh")
        elif mood == "money":
            self._set_expr("money", 2.5)
            self._say("money")
        elif mood in PHRASES:
            self._say(mood)
        else:
            self._set_expr("surprised", 0.7)
            self._hop(self._dp(300))
            self._say("mail", name=sender_name)
        self._schedule(0)

    # Исправленная реакция на отправку: Избранное vs чужой чат
    def _on_sent(self, length, account):
        now = time.monotonic()
        if now < self._next_sent_react:
            return
        self._next_sent_react = now + 1.5

        # Проверяем: отправлено себе в Избранное или собеседнику?
        is_saved = False
        try:
            my_uid = UserConfig.getInstance(account).getClientUserId()
            if self._chat_dialog == my_uid:
                is_saved = True
        except Exception:
            pass

        self._set_expr("happy", 1.2)
        self._hop(self._dp(450))

        if is_saved:
            self._say("sent_self")
        else:
            if length > 300:
                self._say("essay")
            elif random.random() < 0.4:
                self._say("sent")
        self._schedule(0)

    def _get_current_track_pos(self, now: float) -> float:
        if not self._track_is_playing or self._track_base_time == 0.0:
            return self._track_base_pos
        return self._track_base_pos + max(0.0, now - self._track_base_time)

    def _poll_media(self, now):
        if now < self._media_check:
            return
        self._media_check = now + 0.35
        kind = None
        track_title, track_artist = None, None
        track_position = 0.0
        is_playing = False

        # Если активно автономное демо караоке из песочницы
        if self._test_karaoke_active:
            self._track_is_playing = True
            return

        if self._cfg.get("dance", True):
            try:
                controller = MediaController.getInstance()
                playing = controller.getPlayingMessageObject()
                if playing is not None and controller.isPlayingMessage(playing) and not controller.isMessagePaused():
                    if playing.isMusic():
                        kind = "music"
                        is_playing = True
                        track_title = str(playing.getMusicTitle() or "").strip()
                        track_artist = str(playing.getMusicAuthor() or "").strip()
                        dur = float(getattr(playing, "getDuration", lambda: 0)())
                        prog = float(getattr(playing, "audioProgress", 0.0))
                        track_position = dur * prog
                    elif playing.isVoice() or playing.isRoundVideo():
                        kind = "voice"
                        is_playing = True
            except Exception as e:
                CLOG.log_error("TG_AUDIO", "Poll error", e)

            if kind is None and self._pet is not None:
                try:
                    ctx = self._pet.getContext()
                    am = ctx.getSystemService(Context.AUDIO_SERVICE)
                    if am and am.isMusicActive():
                        kind = "music"
                        is_playing = True
                        if self._current_track_id:
                            track_position = self._get_current_track_pos(now)

                        lastfm_u = str(self.get_setting("lastfm_user", "") or "").strip()
                        if lastfm_u and now >= self._lastfm_check_time:
                            self._lastfm_check_time = now + 3.0

                            def _check_scrobbler(u=lastfm_u):
                                res = self._lyrics_helper.fetch_lastfm_now_playing(u)
                                if res:
                                    a, t = res
                                    run_on_ui_thread(lambda: self._start_custom_song(f"{a} - {t}"))

                            threading.Thread(target=_check_scrobbler, daemon=True).start()
                except Exception:
                    pass

        if track_title:
            clean_a, clean_t = self._lyrics_helper.clean_metadata(track_artist, track_title)
            curr_id = f"{clean_a} — {clean_t}"
            if curr_id != self._current_track_id:
                self._current_track_id = curr_id
                self._lyrics_timeline = []
                self._current_lyric_idx = -1
                self._is_singing = False
                CLOG.log_info("TG_TRACK", f"Включен трек Telegram: {curr_id}")

                if self._cfg.get("karaoke", True):
                    self._say_track_detected(clean_a, clean_t)

                    def _on_lyrics_loaded(tl):
                        def _apply():
                            self._lyrics_timeline = tl
                            if not tl:
                                self._say("no_lyrics")
                        run_on_ui_thread(_apply)

                    self._lyrics_helper.get_lyrics_async(clean_a, clean_t, _on_lyrics_loaded)

        if kind == "music":
            self._track_is_playing = is_playing
            self._track_base_pos = track_position
            self._track_base_time = now
        else:
            self._track_is_playing = False

        if kind == self._media:
            return
        prev = self._media
        self._media = kind
        if kind is None:
            self._is_singing = False
            self._hide_bubble()
            if prev == "music" and self._state == "idle":
                self._say("music_end")
            return
        if prev is None and self._state in ("idle", "walk"):
            self._say("music" if kind == "music" else "listen")

    def _say_track_detected(self, artist: str, title: str):
        full = f"{artist} — {title}" if artist else title
        self._say(f"🎵 {full}", force=True)

    def _sync_lyrics_timeline(self, now):
        if (
            not self._cfg.get("karaoke", True)
            or not self._lyrics_timeline
            or (self._media != "music" and not self._test_karaoke_active)
            or not self._track_is_playing
            or self._state not in ("idle", "walk")
        ):
            self._is_singing = False
            return

        pos = self._get_current_track_pos(now)
        idx = -1
        for i, (t_sec, _) in enumerate(self._lyrics_timeline):
            if t_sec <= pos:
                idx = i
            else:
                break

        if idx >= 0:
            t_curr, cur_line = self._lyrics_timeline[idx]
            has_next = idx + 1 < len(self._lyrics_timeline)
            t_next, next_line = self._lyrics_timeline[idx + 1] if has_next else (t_curr + 5.0, "")

            line_dur = t_next - t_curr
            sing_until = t_curr + min(line_dur - 0.7, 5.0) if line_dur > 5.5 else t_next

            if pos <= sing_until:
                self._is_singing = True
                if idx != self._current_lyric_idx:
                    self._current_lyric_idx = idx
                    self._show_karaoke_line(cur_line, next_line, now)
            else:
                self._is_singing = False
                if self._current_lyric_idx != -2:
                    self._current_lyric_idx = -2
                    if t_next - pos > 2.5:
                        self._hide_bubble()
        else:
            self._is_singing = False

    def _show_karaoke_line(self, current_text: str, next_text: str, now: float):
        if self._bubble is None or self._bubble_text is None:
            return
        try:
            bg = GradientDrawable()
            bg.setCornerRadius(float(AndroidUtilities.dp(13)))
            bg.setColor(as_java_color(0xEE1A1A1E))
            bg.setStroke(max(1, AndroidUtilities.dp(1)), as_java_color(0x33FFFFFF))
            self._bubble.setBackground(bg)

            self._bubble_text.setTextColor(as_java_color(0xFFFFFFFF))
            self._bubble_text.setText(current_text)

            if next_text and self._bubble_subtext is not None:
                self._bubble_subtext.setText(next_text)
                self._bubble_subtext.setTextColor(0x77FFFFFF)
                self._bubble_subtext.setVisibility(View.VISIBLE)
            elif self._bubble_subtext is not None:
                self._bubble_subtext.setVisibility(View.GONE)

            if self._media_controls_layout is not None and self._cfg.get("media_controls", True):
                self._media_controls_layout.setVisibility(View.VISIBLE)

            self._bubble.setVisibility(View.VISIBLE)
            self._bubble.setAlpha(1.0)
            self._bubble_visible = True
            self._bubble_until = now + 9.0
        except Exception as e:
            CLOG.log_error("KARAOKE_UI", "Show line error", e)

    def _start_custom_song(self, raw_input: str):
        a, t = self._lyrics_helper.clean_metadata("", raw_input)
        track_id = f"{a} — {t}" if a else t
        if track_id == self._current_track_id and self._is_singing:
            return
        self._current_track_id = track_id
        self._lyrics_timeline = []
        self._current_lyric_idx = -1
        self._is_singing = True
        self._media = "music"
        self._track_is_playing = True
        self._track_base_pos = 0.0
        self._track_base_time = time.monotonic()

        self._say_track_detected(a, t)

        def _on_loaded(tl):
            def _apply():
                self._lyrics_timeline = tl
                if not tl:
                    self._say("no_lyrics")
            run_on_ui_thread(_apply)

        self._lyrics_helper.get_lyrics_async(a, t, _on_loaded)

    def _format_phrase(self, text: str, name: Optional[str] = None) -> str:
        t_now = time.strftime("%H:%M")
        res = text.replace("{time}", t_now)
        res = res.replace("{battery}", str(self._battery_level))
        res = res.replace("{name}", name or "")
        return res

    def _say(self, category, force=False, name=None):
        if self._is_singing or self._bubble is None:
            return
        if not force and not self._cfg.get("phrases", True):
            return
        phrases = PHRASES.get(category, [category])
        if name is None:
            phrases = [p for p in phrases if "{name}" not in p] or phrases
        raw_text = random.choice([p for p in phrases if p != self._last_phrase] or phrases)
        text = self._format_phrase(raw_text, name)
        self._last_phrase = text
        now = time.monotonic()

        try:
            bg = GradientDrawable()
            bg.setCornerRadius(float(AndroidUtilities.dp(12)))
            bg.setColor(Theme.getColor(Theme.key_windowBackgroundWhite))
            bg.setStroke(max(1, AndroidUtilities.dp(1)), Theme.getColor(Theme.key_divider))
            self._bubble.setBackground(bg)

            if self._bubble_text is not None:
                self._bubble_text.setTextColor(Theme.getColor(Theme.key_windowBackgroundWhiteBlackText))
                self._bubble_text.setText(text)
            if self._bubble_subtext is not None:
                self._bubble_subtext.setVisibility(View.GONE)
            if self._media_controls_layout is not None:
                self._media_controls_layout.setVisibility(View.GONE)

            self._bubble.animate().cancel()
            self._bubble.setAlpha(0.0)
            self._bubble.setVisibility(View.VISIBLE)
            self._bubble_gen += 1
            self._bubble_visible = True
            self._bubble_fade_in = True
            self._bubble_until = now + 2.0 + len(text) * 0.05
        except Exception as e:
            CLOG.log_error("BUBBLE", "Bubble text error", e)

    def _hide_bubble(self):
        if self._bubble is None or not self._bubble_visible:
            return
        self._bubble_visible = False
        self._bubble_fade_in = False
        self._bubble_gen += 1
        gen = self._bubble_gen
        bubble = self._bubble

        def _gone():
            if gen == self._bubble_gen and bubble is not None:
                bubble.setVisibility(View.GONE)

        anim = bubble.animate().alpha(0.0).setDuration(180)
        anim.withEndAction(R(_gone))
        anim.start()

    def _update_bubble(self, now, width, min_y):
        if self._bubble is None or not self._bubble_visible:
            return
        if now >= self._bubble_until and not self._is_singing:
            self._hide_bubble()
            return
        bw, bh = self._bubble.getWidth(), self._bubble.getHeight()
        if bw <= 0:
            return
        margin = self._dp(4)
        bx = clamp(self._x + self._w / 2.0 - bw / 2.0, margin, width - bw - margin)
        by = self._y + self._hop_off + self._unit - bh - margin
        if by < min_y:
            by = self._y + self._hop_off + self._h + margin
        self._bubble.setTranslationX(float(bx))
        self._bubble.setTranslationY(float(by))
        if self._bubble_fade_in:
            self._bubble_fade_in = False
            self._bubble.animate().alpha(1.0).setDuration(150).start()

    def _pick_target(self, top):
        decor = self._decor
        if decor is None:
            return None
        width, height = decor.getWidth(), decor.getHeight()
        dloc = jarray(jint)([0, 0])
        decor.getLocationInWindow(dloc)
        loc = jarray(jint)([0, 0])

        candidates = []
        stack = [decor]
        visited = 0

        while stack and visited < 900:
            view = stack.pop()
            visited += 1

            if view is None or view.getVisibility() != View.VISIBLE:
                continue
            try:
                if float(view.getAlpha()) < 0.2:
                    continue
            except Exception:
                pass

            if view.equals(self._pet) or view.equals(self._bubble):
                continue
            if any(view.equals(p) for p in self._poops):
                continue

            count = view.getChildCount() if isinstance(view, ViewGroup) else 0
            if count > 0:
                for i in range(count):
                    child = view.getChildAt(i)
                    if child is not None:
                        stack.append(child)
                if view.getBackground() is None:
                    continue

            w, h = view.getWidth(), view.getHeight()
            if w < AndroidUtilities.dp(12) or h < AndroidUtilities.dp(12):
                continue
            if w >= width * 0.95 and h >= height * 0.95:
                continue

            view.getLocationInWindow(loc)
            x = loc[0] - dloc[0]
            y = loc[1] - dloc[1]
            if x + w <= 0 or y + h <= top or x >= width or y >= height:
                continue

            candidates.append((view, x, y, w, h))

        if not candidates:
            return None

        cx = self._x + self._w / 2.0
        cy = self._y + self._h / 2.0
        reach = self._dp(220)
        weights = [
            1.0 / (1.0 + (math.hypot(x + w / 2.0 - cx, y + h / 2.0 - cy) / reach) ** 2)
            for _, x, y, w, h in candidates
        ]
        return random.choices(candidates, weights)[0]

    def _try_eat(self, now, top):
        try:
            target = self._pick_target(top)
            if target is None:
                return False
            view, x, y, w, h = target

            bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
            canvas = Canvas(bmp)
            canvas.translate(float(-view.getScrollX()), float(-view.getScrollY()))
            view.draw(canvas)

            item = {"view": view, "alpha": float(view.getAlpha()), "bmp": bmp, "w": w, "h": h}
            view.setAlpha(0.0)
            self._eaten.append(item)

            copy = ImageView(self._pet.getContext())
            copy.setImageBitmap(bmp)
            copy.setScaleType(ImageView.ScaleType.FIT_XY)
            index = max(0, self._decor.indexOfChild(self._pet))
            self._decor.addView(copy, index, FrameLayout.LayoutParams(w, h))
            self._flying.append(copy)

            copy.setTranslationX(float(x))
            copy.setTranslationY(float(y))

            mx = self._x + self._w / 2.0
            my = self._y + self._hop_off + self._unit * 8.0
            self._look = 1 if x + w / 2.0 > mx else -1
            self._mouth_open_until = now + 0.7
            self._chew_until = 0.0
            self._next_action = now + 3.0
            self._next_eat = now + random.uniform(25.0, 70.0)

            anim = copy.animate()
            anim.translationX(float(mx - w / 2.0)).translationY(float(my - h / 2.0))
            anim.scaleX(0.05).scaleY(0.05)
            anim.rotation(float(random.choice((-1, 1)) * random.uniform(120.0, 300.0)))
            anim.setInterpolator(AccelerateInterpolator(1.6))
            anim.setDuration(560)
            anim.withEndAction(R(lambda v=copy: self._on_swallowed(v)))
            anim.start()
            return True
        except Exception as e:
            CLOG.log_error("EAT", "Eat animation error", e)
            return False

    def _on_swallowed(self, copy):
        try:
            self._flying.remove(copy)
        except ValueError:
            pass
        self._remove_view(copy)
        if self._pet is None:
            return
        now = time.monotonic()
        self._mouth_open_until = 0.0
        self._chew_until = now + 1.4
        self._squash_until = now + 0.12
        self._set_expr("happy", 1.6)
        self._haptic(3)
        RetroAudio.eat()

        try:
            self.set_setting("eaten_count", int(self.get_setting("eaten_count", 0) or 0) + 1)
        except Exception:
            pass

        fat = self._fat_stage()
        if fat == 1:
            self._say("eat_chubby")
        elif fat == 2:
            self._say("eat_fat")
        elif fat == 3:
            self._say("eat_balloon")
        else:
            self._say("eat")

        if self._cfg.get("poop", True):
            try:
                meter = int(self.get_setting("poop_meter", 0) or 0) + 1
                if meter >= self._poop_need:
                    meter = 0
                    self._poop_need = random.randint(*POOP_EVERY)
                    self._poop_due = now + random.uniform(5.0, 10.0)
                self.set_setting("poop_meter", meter)
            except Exception:
                pass

    def _do_poop(self, now, min_x, max_x):
        self._poop_due = 0.0
        if not self._cfg.get("poop", True) or self._decor is None or self._pet is None:
            return
        if len(self._poops) >= MAX_POOPS:
            return

        is_gold = random.random() < 0.1
        side = -self._look if self._look else random.choice((-1, 1))
        try:
            bmp = self._particle_bitmap("poop", is_gold=is_gold)
            bw, bh = bmp.getWidth(), bmp.getHeight()
            pad = AndroidUtilities.dp(6)
            view = ImageView(self._pet.getContext())
            view.setImageBitmap(bmp)
            view.setScaleType(ImageView.ScaleType.CENTER)
            view.setPadding(pad, pad, pad, pad)
            if self._poop_listener is None:
                self._poop_listener = PoopClickListener(self)
            view.setOnClickListener(self._poop_listener)

            index = max(0, self._decor.indexOfChild(self._pet))
            self._decor.addView(view, index, FrameLayout.LayoutParams(bw + pad * 2, bh + pad * 2))
            feet = self._y + self._unit * 12
            px = self._x + self._w / 2.0 + side * self._w * 0.42 - bw / 2.0 - pad
            px = clamp(px, 0.0, float(self._decor.getWidth() - bw - pad * 2))
            view.setTranslationX(float(px))
            view.setTranslationY(float(feet - bh - pad))
            view.setScaleX(0.1)
            view.setScaleY(0.1)
            view.animate().scaleX(1.0).scaleY(1.0).setInterpolator(OvershootInterpolator(2.0)).setDuration(320).start()
            self._poops.append(view)
        except Exception as e:
            CLOG.log_error("POOP", "Create poop error", e)
            return

        self._squash_until = now + 0.2
        self._set_expr("happy", 1.8)
        self._haptic(3)
        self._say("poop_gold" if is_gold else "poop")
        if is_gold:
            RetroAudio.magic()
            for _ in range(4):
                self._spawn_particle("spark")

    def _clean_poop(self, view):
        target = None
        for p in self._poops:
            if p.equals(view):
                target = p
                break
        if target is None:
            return
        self._poops.remove(target)
        target.setClickable(False)
        cx = float(target.getTranslationX()) + target.getWidth() / 2.0
        cy = float(target.getTranslationY()) + target.getHeight() / 2.0
        for _ in range(3):
            self._spawn_particle("spark", origin=(cx, cy))
        target.animate().scaleX(0.0).scaleY(0.0).alpha(0.0).setDuration(250).withEndAction(
            R(lambda v=target: self._remove_view(v))
        ).start()

        try:
            self.set_setting("poops_cleaned", int(self.get_setting("poops_cleaned", 0) or 0) + 1)
        except Exception:
            pass
        self._haptic(3)
        RetroAudio.jump()
        self._say("clean")

    def _remove_poops(self):
        for view in self._poops:
            self._remove_view(view)
        self._poops = []

    def _prune_eaten(self):
        kept = []
        for item in self._eaten:
            try:
                if float(item["view"].getAlpha()) < 0.01:
                    kept.append(item)
            except Exception:
                pass
        self._eaten = kept

    def _restore_all(self):
        items = self._eaten + self._spitting
        self._eaten, self._spitting = [], []
        for view in list(self._flying):
            self._remove_view(view)
        self._flying = []
        for item in items:
            try:
                item["view"].setAlpha(float(item["alpha"]))
            except Exception:
                pass

    def _give_back(self):
        if self._eaten and self._pet is not None and self._decor is not None:
            self._spit_all(time.monotonic())
        else:
            self._restore_all()

    def _spit_all(self, now):
        items = self._eaten
        self._eaten = []
        if not items:
            return
        self._chew_until = 0.0
        self._mouth_open_until = now + 0.35 + 0.08 * len(items)
        self._set_expr("surprised", 0.9)
        self._squash_until = now + 0.12
        self._hop(self._dp(300))
        self._haptic(1)
        self._say("spit")
        RetroAudio.jump()

        mx = self._x + self._w / 2.0
        my = self._y + self._hop_off + self._unit * 8.0
        for i, item in enumerate(items):
            self._spit_one(item, mx, my, i * 70)
        self._schedule(0)

    def _spit_one(self, item, mx, my, delay):
        view = item["view"]
        w, h = item["w"], item["h"]
        try:
            if self._decor is None or not view.isAttachedToWindow():
                view.setAlpha(float(item["alpha"]))
                return
            dloc = jarray(jint)([0, 0])
            loc = jarray(jint)([0, 0])
            self._decor.getLocationInWindow(dloc)
            view.getLocationInWindow(loc)
            x, y = loc[0] - dloc[0], loc[1] - dloc[1]

            self._spitting.append(item)
            copy = ImageView(self._pet.getContext())
            copy.setImageBitmap(item["bmp"])
            copy.setScaleType(ImageView.ScaleType.FIT_XY)
            self._decor.addView(copy, FrameLayout.LayoutParams(w, h))

            copy.setTranslationX(float(mx - w / 2.0))
            copy.setTranslationY(float(my - h / 2.0))
            copy.setScaleX(0.01)
            copy.setScaleY(0.01)

            def _done(v=copy, it=item):
                self._remove_view(v)
                try:
                    self._spitting.remove(it)
                except ValueError:
                    pass
                it["view"].setAlpha(float(it["alpha"]))

            copy.animate().translationX(float(x)).translationY(float(y)).scaleX(1.0).scaleY(1.0).setDuration(450).setStartDelay(
                int(delay)
            ).setInterpolator(OvershootInterpolator(1.2)).withEndAction(R(_done)).start()
        except Exception as e:
            CLOG.log_error("SPIT", "Spit error", e)
            view.setAlpha(float(item["alpha"]))

    def _poll_chat(self, now):
        fragment = None
        dialog_id = 0
        try:
            fragment = get_last_fragment()
            if fragment is not None and isinstance(fragment, ChatActivity):
                dialog_id = int(fragment.getDialogId())
        except Exception:
            dialog_id = 0
        if dialog_id == self._chat_dialog:
            try:
                if fragment is not None and isinstance(fragment, ChatActivity):
                    sub = getattr(fragment, "subtitleTextView", None)
                    if sub is not None:
                        txt = str(sub.getText() or "").lower()
                        if ("печатает" in txt or "typing" in txt) and self._state in ("idle", "walk") and now >= self._next_action:
                            self._set_expr("surprised", 1.2)
                            self._say("typing")
                            self._next_action = now + 5.0
            except Exception:
                pass
            return

        self._chat_dialog = dialog_id
        if not dialog_id or not self._cfg.get("tg_events", True):
            return
        visits = self._chat_visits.pop(dialog_id, 0) + 1
        self._chat_visits[dialog_id] = visits
        if len(self._chat_visits) > MAX_CHAT_VISITS:
            self._chat_visits.pop(next(iter(self._chat_visits)))
        if now < self._next_chat_comment or self._state not in ("idle", "walk") or random.random() > 0.4:
            return
        self._next_chat_comment = now + 25.0

        is_self, name = False, None
        try:
            u = fragment.getCurrentUser()
            if u is not None:
                is_self = UserObject.isUserSelf(u)
                name = UserObject.getFirstName(u)
            else:
                c = fragment.getCurrentChat()
                if c is not None:
                    name = c.title
        except Exception:
            pass

        if is_self:
            self._say("chat_self")
        elif visits > 1:
            self._say("chat_again", name=name)
        else:
            self._say("chat_new", name=name)

    def _set_expr(self, expr, duration):
        self._expr = expr
        self._expr_until = time.monotonic() + duration

    def _hop(self, strength):
        if self._state not in ("idle", "walk"):
            return
        self._hop_active = True
        self._hop_vy = -float(strength)
        if self._hop_off > 0:
            self._hop_off = 0.0

    def _haptic(self, kind):
        if not self._cfg.get("haptics", True) or self._pet is None:
            return
        try:
            self._pet.performHapticFeedback(kind)
        except Exception:
            pass

    def _spawn_particle(self, kind, origin=None):
        if self._decor is None or self._pet is None or len(self._particles) >= MAX_PARTICLES:
            return
        try:
            bmp = self._particle_bitmap(kind)
            bw, bh = bmp.getWidth(), bmp.getHeight()
            view = ImageView(self._pet.getContext())
            view.setImageBitmap(bmp)
            self._decor.addView(view, FrameLayout.LayoutParams(bw, bh))
            self._particles.append(view)

            head_y = self._y + self._hop_off + self._unit * 2 - bh
            if origin is not None:
                sx = origin[0] - bw / 2.0 + random.uniform(-self._dp(8), self._dp(8))
                sy = origin[1] - bh
                drift = random.uniform(-self._dp(16), self._dp(16))
            elif kind == "zzz":
                sx = self._x + self._w * 0.72
                sy = head_y + self._unit * 2
                drift = self._dp(18)
            else:
                sx = self._x + self._w / 2.0 - bw / 2.0 + random.uniform(-self._w * 0.25, self._w * 0.25)
                sy = head_y
                drift = random.uniform(-self._dp(16), self._dp(16))

            view.setTranslationX(float(sx))
            view.setTranslationY(float(sy))
            view.setScaleX(0.5)
            view.setScaleY(0.5)
            view.animate().translationXBy(float(drift)).translationYBy(float(-self._dp(random.uniform(40, 58)))).scaleX(
                1.0
            ).scaleY(1.0).alpha(0.0).setDuration(1100 if kind != "zzz" else 1600).withEndAction(
                R(lambda v=view: self._remove_particle(v))
            ).start()
        except Exception as e:
            CLOG.log_error("PARTICLE", "Spawn particle error", e)

    def _remove_particle(self, view):
        try:
            self._particles.remove(view)
        except ValueError:
            pass
        self._remove_view(view)