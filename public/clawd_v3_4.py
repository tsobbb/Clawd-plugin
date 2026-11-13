import collections
import datetime
import json
import math
import os
import queue
import random
import re
import socket
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from android.content import ClipData, ClipboardManager, ComponentName, Context, DialogInterface, Intent
from android.graphics import Bitmap, BitmapFactory, Canvas, Paint
from android.graphics.drawable import Drawable, GradientDrawable, LayerDrawable
from android.hardware import Sensor, SensorEventListener, SensorManager
from android.media import AudioManager
from android.os import BatteryManager, Environment, Handler, Looper, PowerManager, SystemClock
from android.provider import Settings
from android.util import TypedValue
from android.view import Gravity, KeyEvent, MotionEvent, Surface, SurfaceView, TextureView, View, ViewGroup
from android.view.animation import AccelerateInterpolator, DecelerateInterpolator, OvershootInterpolator
from android.widget import EditText, FrameLayout, ImageView, LinearLayout, ScrollView, SeekBar, TextView
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
    from android.text import TextUtils
except Exception:
    TextUtils = None

try:
    from org.telegram.ui.Cells import ChatMessageCell
except Exception:
    ChatMessageCell = None

WeakReference = jclass("java.lang.ref.WeakReference")

__id__ = "clawd_pet"
__name__ = "Clawd"
__description__ = (
    "Ультимативный интерактивный питомец для Telegram v3.5.\n\n"
    "• Стабилизированное двухстрочное караоке со сглаживанием текста и защитой от скачков.\n"
    "• Автоповтор поиска слов, защита от deadlock и сохранение архивов.\n"
    "• Единое суточное логирование ClaudePet_YYYY-MM-DD.txt без потерь.\n"
    "• Бесшовная интеграция с Clawd Bridge и Tap-to-Sync [📋].\n"
    "• Режим «Абсолютный Обжора» 2.0: безопасное поедание любого View с WeakReference.\n"
    "• Глубокая логика Telegram: разделяет свои заметки и входящие сообщения."
)
__author__ = "@tsobbb"
__version__ = "3.5"
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

AUTO_RETURN_ITEMS = ["Через 30 секунд", "Через 2 минуты", "Через 10 минут"]
AUTO_RETURN_SECONDS = [30.0, 120.0, 600.0]

TG_CHAT_SCOPE_ITEMS = ["Только в личках", "В личках и группах"]

LOG_LEVELS = ["DEBUG", "INFO", "WARN", "ERROR"]
LEVEL_VALUES = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}

HEART_COLOR = 0xFFFF5C7A
ZZZ_COLOR = 0xFF8FA3BF
SPARK_COLOR = 0xFFFFC94D
NOTE_COLOR = 0xFF6FB8FF
POOP_COLORS = {"X": 0xFF8A5A33, "o": 0xFFB27D4E, "w": 0xFFFFFFFF, "k": 0xFF1A1A1A}
GOLD_POOP_COLORS = {"X": 0xFFD4AF37, "o": 0xFFFFDF73, "w": 0xFFFFFFFF, "k": 0xFF5A4500}

MAX_LOG_FILE_SIZE = 512 * 1024  # строго 512 КБ
MAX_LYRICS_FILES = 200

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
    ("love", re.compile(r"❤|♥|💕|💖|😘|😍|🥰|\bлюблю\b|\bобнима\w*|\bцелую\b|\blove\b|\bмилаш\w*|\bкохаю\b")),
    ("laugh", re.compile(r"(?:ха){2,}|(?:хе){2,}|\bлол\b|\blol\b|\bржу\w*|😂|🤣|😆|\bору\b|\bрофл\w*")),
    ("hi", re.compile(r"\b(?:привет\w*|здравствуй\w*|хай|салют|hello|hi|hey|доброе утро|добрый день|привіт|вітаю)\b")),
    ("bye", re.compile(r"\b(?:пока|споки|спокойной ночи|до завтра|бб|доброй ночи|сладких снов|бай|бувай|до побачення)\b")),
    ("thanks", re.compile(r"\b(?:спасибо|благодарю|thanks|thx|thank you|дякую|спасибі)\b")),
    ("money", re.compile(r"\b(?:деньги|бабки|бабло|кэш|usdt|крипт\w*|карт\w*|перевод|скинь|оплат\w*|зарплат\w*|\$|€|₽|гроші|кошти)\b")),
    ("food", re.compile(r"\b(?:пицц\w*|бургер\w*|шаурм\w*|шав\w*|кушать|жрать|покушал\w*|суши|кофе|чай|чипсы|вкусн\w*|їсти|смачно)\b")),
    ("sad", re.compile(r"\b(?:грустн\w*|плач\w*|печал\w*|слез\w*|депресс\w*|тоск\w*|одинок\w*|хнык|😭|😢|😿|💔|сумно)\b")),
    ("angry", re.compile(r"\b(?:бесит|злюсь|сука|блять|нах\w*|заеб\w*|отвали|заткнись|гори|убью|ненавижу|черт|ярость)\b")),
    ("work", re.compile(r"\b(?:дедлайн|диплом|сесси\w*|экзамен\w*|работ\w*|начальник|отчет|проект|код\w*|баг\w*|робота)\b")),
    ("compliment", re.compile(r"\b(?:клавд|клод|clawd|красавчик|умница|лучший|топчик|красота|милота|гарний)\b")),
    ("question", re.compile(r"\b(?:почему|зачем|когда|куда|откуда|правда ли|чому|навіщо|коли)\b|\?\?\?+")),
    ("gaming", re.compile(r"\b(?:игра\w*|катка|дот\w*|кс|cs|steam|вин\w*|луз\w*|гейм\w*|бравл|майн\w*|грати)\b")),
    ("memes", re.compile(r"\b(?:мем\w*|кринж\w*|база|сигма|скуф\w*|чилл\w*|форс\w*)\b")),
    ("music", re.compile(r"\b(?:музык\w*|песн\w*|трек\w*|альбом\w*|бит|мелоди\w*|плейлист\w*|спой|пісня|музика)\b")),
    ("secret", re.compile(r"\b(?:секрет\w*|тайн\w*|никому не говори|между нами|инсайд\w*|таємниця)\b")),
)

PHRASES = {
    "hello": ["Привет!", "Я Clawd v3.5!", "О, это ты!", "Готов тусить!", "Чем займёмся?"],
    "idle": [
        "Чем помочь?", "Хм…", "Думаю…", "Можно я тут посижу?",
        "Ты молодец!", "Не забудь попить воды", "Пип-пип!",
        "Мне нравится этот чат", "*оглядывается*", "Пишу код… шучу",
        "Скучновато… скинь мем!", "Сейчас {time}, продуктивно!",
    ],
    "tap": ["Ой!", "Эй!", "Чего?", "Я тут!", "Хи!", "Не щекочи!"],
    "tap_flee": ["Не догонишь!", "Я побежал!", "Побег!", "Хи-хи, догоняй!", "Ой, щекотно!", "Быстрее ветра!"],
    "annoyed": ["Хватит тыкать!", "Щекотно же!", "Ну всё, обиделся", "Эй, полегче!", "Я тебе не кнопка!"],
    "pet": ["Мрр…", "Ещё!", "Приятно ♥", "Хи-хи", "Лучший день!", "♥♥♥", "Мур-мур-мур"],
    "drag": ["Ааа!", "Куда мы?", "Поставь меня!", "Головокружение!", "Лечу-у-у!"],
    "throw": ["Уиии!", "Я лечу!", "Ваааа!", "Посадка не гарантирована!"],
    "dizzy": ["Голова кружится…", "@_@", "Где я?", "Земля ушла из-под лап…"],
    "wake": ["А? Что?", "Я не спал!", "*зевает*", "Уже утро?"],
    "jump": ["Хоп!", "Йе!", "Ура!", "Выше крыши!"],
    "laser_chase": ["ТОЧКА!", "ПОЙМАЮ!", "ОНА ТУТ!", "СТОЯТЬ!", "ААА, ЛАЗЕР!"],
    "eat": [
        "Ням!", "Хрум-хрум", "Вкусный кусок UI", "*жуёт*", "Ммм, свежие пиксели!",
        "Хрустящая кнопка!", "Пиксели тают во рту!", "Интерфейс сегодня особенно аппетитный ✨",
        "Закусил элементом экрана", "Сытный пиксельный перекус!", "Мням, интерфейс стал чище!",
    ],
    "eat_edittext": [
        "Съел поле ввода, теперь молчи 🤫",
        "Клавиатура временно заблокирована моим желудком!",
        "Больше никаких сообщений 🤐",
        "Ввод проглочен! Тишина в эфире",
        "Меньше слов — больше дела, поле ввода у меня внутри!",
    ],
    "eat_message": [
        "Перевариваю чужие сплетни 💌",
        "Вкусное сообщение!",
        "Слишком много текста было… пришлось съесть!",
        "Слопал важное сообщение, ой!",
        "Питательный чат! Текст оказался сытным",
    ],
    "eat_header": [
        "Откусил кусок шапки!",
        "Тулбар был аппетитным 🎩",
        "Где теперь название чата? В животе!",
        "Шапка съедена, гуляем без неё!",
        "Верхняя панель оказалась на удивление хрустящей!",
    ],
    "eat_avatar": [
        "Съел твою аватарку! 👤",
        "Кругляш на десерт!",
        "Красивая фотка была… ням!",
        "Аватарка отправилась в желудок!",
        "Портрет переварен с удовольствием!",
    ],
    "eat_chubby": ["Хрум! Вкусновато, но щёчки растут…", "Ммм, ещё кусочек интерфейса!"],
    "eat_fat": ["Ох… кажется, я тяжелею…", "Штаны лопнут!", "Многовато кнопок съел…"],
    "eat_balloon": ["Я ШАР! Я КОЛОБОК!", "Всё, перекат вместо шага… *ик*", "Не могу больше двигаться…"],
    "spit": ["Ладно, отдаю!", "Тьфу!", "Ой, простите", "Забирай…", "Я на диете!"],
    "mail": ["Тебе пишут!", "Сообщение от {name}!", "Входящее!", "Динь-динь!"],
    "sent": ["Отправлено!", "Улетело!", "Хорошо сказано!", "Пиу!"],
    "sent_self": ["Записал в заметки!", "Сохранено в Избранное!", "Надёжно спрятано ♥", "В копилку мыслей!"],
    "thanks": [
        "Всегда пожалуйста! ♥", "Обращайся!", "Рад помочь!", "Ты супер!",
        "Мурр, на здоровье!", "Не за что!", "Для тебя — всё что угодно!",
        "Пип-пип, обращайся!", "Всегда к твоим услугам!", "Приятно слышать ♥",
    ],
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
    "sync_unavailable": ["Синхронизация недоступна", "Таймлайн не найден, но бит качает! 🎵"],
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
MAX_FRAME_CACHE = 128
MAX_EATEN = 12
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


# === [SHARED_BLOCK:COLOR_LOGGER_PROXIES] ===
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


def parse_hex_color(raw: Optional[str]) -> Optional[int]:
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    if s.startswith("#"):
        s = s[1:]
    if len(s) == 6:
        try:
            return 0xFF000000 | int(s, 16)
        except Exception:
            return None
    if len(s) == 8:
        try:
            return int(s, 16) & 0xFFFFFFFF
        except Exception:
            return None
    return None


DEFAULT_KARAOKE_PALETTE: Tuple[int, int, int] = (0xFF6B778D, 0xFF434C5E, 0xFF2B303B)


def derive_palette_3(accent_color: Any, accent_colors: Any) -> Tuple[int, int, int]:
    parsed: List[int] = []
    if isinstance(accent_colors, (list, tuple)):
        for item in accent_colors:
            c = parse_hex_color(item) if isinstance(item, str) else (int(item) & 0xFFFFFFFF if isinstance(item, int) else None)
            if c is not None:
                parsed.append(c | 0xFF000000)
                if len(parsed) == 3:
                    break
    if len(parsed) >= 3:
        return (parsed[0], parsed[1], parsed[2])
    base = parsed[0] if parsed else (
        parse_hex_color(accent_color) if isinstance(accent_color, str) else (int(accent_color) & 0xFFFFFFFF if isinstance(accent_color, int) else None)
    )
    if len(parsed) == 2:
        return (parsed[0], parsed[1], mix_color(parsed[1], 0xFF141828, 0.28))
    if base is not None:
        base_opaque = base | 0xFF000000
        return (
            mix_color(base_opaque, 0xFFFFFFFF, 0.24),
            base_opaque,
            mix_color(base_opaque, 0xFF121626, 0.30),
        )
    return DEFAULT_KARAOKE_PALETTE


class ClaudeLogger:
    """Асинхронное структурированное логирование с ротацией 512 КБ и кольцевым буфером на 500 записей."""

    def __init__(self):
        self.base_dir = None
        self.logs_dir = None
        self.errors_dir = None
        self.lyrics_dir = None
        self.ring_buffer = collections.deque(maxlen=500)
        self.min_level_str = "DEBUG"
        self._write_queue = queue.Queue()
        self._stop_event = threading.Event()
        self._writer_thread = None
        self._last_rate_limited = {}
        self._init_dirs()
        self._start_writer()

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

    def _start_writer(self):
        self._stop_event.clear()
        self._writer_thread = threading.Thread(target=self._writer_worker, daemon=True, name="claude_log_writer")
        self._writer_thread.start()

    def ensure_started(self):
        if self._writer_thread is None or not self._writer_thread.is_alive():
            self._init_dirs()
            self._start_writer()

    def _writer_worker(self):
        batch = []
        last_flush = time.monotonic()
        while not self._stop_event.is_set():
            try:
                item = self._write_queue.get(timeout=0.4)
                if item is None:
                    break
                batch.append(item)
                # Если накопилось 10 записей или есть ERROR — сбрасываем немедленно
                is_urgent = item[0] == "ERROR" or len(batch) >= 10 or (time.monotonic() - last_flush > 2.0)
                if is_urgent:
                    self._flush_batch(batch)
                    batch = []
                    last_flush = time.monotonic()
            except queue.Empty:
                if batch:
                    self._flush_batch(batch)
                    batch = []
                    last_flush = time.monotonic()
            except Exception:
                pass
        if batch:
            self._flush_batch(batch)

    def _flush_batch(self, batch: List[Tuple[str, str, str]]):
        if not self.logs_dir:
            return
        day_str = datetime.datetime.now().strftime("%Y-%m-%d")
        daily_fp = os.path.join(self.logs_dir, f"ClaudePet_{day_str}.txt")
        errors_fp = os.path.join(self.errors_dir, "ClaudePet_Errors.txt")

        try:
            daily_lines = []
            error_lines = []
            for level, tag, line in batch:
                daily_lines.append(line + "\n")
                if level in ("ERROR", "WARN"):
                    error_lines.append(line + "\n")

            if daily_lines:
                with open(daily_fp, "a", encoding="utf-8") as f:
                    f.writelines(daily_lines)

            if error_lines:
                self._rotate_if_needed(errors_fp, is_runtime=False)
                with open(errors_fp, "a", encoding="utf-8") as f:
                    f.writelines(error_lines)
        except Exception:
            pass

    def _rotate_if_needed(self, fp: str, is_runtime: bool):
        try:
            if not os.path.exists(fp):
                return
            size = os.path.getsize(fp)
            if size < MAX_LOG_FILE_SIZE:
                return
            if is_runtime:
                pass
            else:
                # ClaudePet_Errors.txt: усекается с сохранением последних 200 строк
                with open(fp, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                kept = lines[-200:]
                with open(fp, "w", encoding="utf-8") as f:
                    f.writelines(kept)
        except Exception:
            pass

    def flush_and_stop(self):
        self._stop_event.set()
        try:
            self._write_queue.put_nowait(None)
        except Exception:
            pass
        if self._writer_thread and self._writer_thread.is_alive():
            self._writer_thread.join(timeout=1.0)

    def log(self, level: str, tag: str, message: str, key_values: Optional[Dict[str, Any]] = None):
        # Формат: ГГГГ-ММ-ДД ЧЧ:ММ:СС.mmm | LEVEL | TAG | сообщение | key=value
        ts_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        kv_str = ""
        if key_values:
            kv_str = " | " + " ".join(f"{k}={v}" for k, v in key_values.items())
        line = f"{ts_now} | {level:<5} | {tag} | {message}{kv_str}"

        # Добавляем в кольцевой буфер всегда
        self.ring_buffer.append(line)
        log(f"[{tag}] {message}")

        # Единый поток: пишем все уровни в очередь суточного лога
        try:
            self._write_queue.put_nowait((level, tag, line))
        except Exception:
            pass

    def log_debug(self, tag: str, message: str, **kwargs):
        self.log("DEBUG", tag, message, kwargs if kwargs else None)

    def log_info(self, tag: str, message: str, **kwargs):
        self.log("INFO", tag, message, kwargs if kwargs else None)

    def log_warn(self, tag: str, message: str, **kwargs):
        self.log("WARN", tag, message, kwargs if kwargs else None)

    def log_error(self, tag: str, message: str, exc: Optional[Exception] = None, rate_limit_key: Optional[str] = None, **kwargs):
        now = time.monotonic()
        if rate_limit_key:
            last = self._last_rate_limited.get(rate_limit_key, 0.0)
            if now - last < 5.0:
                return
            self._last_rate_limited[rate_limit_key] = now

        msg = message
        if exc:
            msg += f" (exc: {exc})"
        self.log("ERROR", tag, msg, kwargs if kwargs else None)

    def check_lyrics_archive(self, artist: str, title: str) -> Optional[str]:
        if not self.lyrics_dir:
            return None
        safe = re.sub(r'[\\/*?:"<>|]', "", f"{artist} - {title}").strip()[:60]
        for ext in (".txt", ".lrc"):
            fp = os.path.join(self.lyrics_dir, f"{safe}{ext}")
            if os.path.exists(fp):
                try:
                    with open(fp, "r", encoding="utf-8") as f:
                        text = f.read().strip()
                        if text:
                            self.log_info("LYRICS", f"Текст мгновенно загружен из архива: {safe}{ext}")
                            return text
                except Exception:
                    pass
        return None

    def save_lyrics_archive(self, artist: str, title: str, text: str):
        if not self.lyrics_dir or not text:
            return
        try:
            files = []
            for fn in os.listdir(self.lyrics_dir):
                if fn.endswith((".txt", ".lrc")):
                    p = os.path.join(self.lyrics_dir, fn)
                    try:
                        files.append((p, os.path.getmtime(p)))
                    except Exception:
                        pass

            # Лимит 200 файлов: удаляем старейший
            if len(files) >= MAX_LYRICS_FILES:
                files.sort(key=lambda x: x[1])
                oldest_fp = files[0][0]
                try:
                    os.remove(oldest_fp)
                    self.log_info("LYRICS", f"Ротация кэша слов: удален старый файл {os.path.basename(oldest_fp)}")
                except Exception:
                    pass

            safe = re.sub(r'[\\/*?:"<>|]', "", f"{artist} - {title}").strip()[:60]
            fp = os.path.join(self.lyrics_dir, f"{safe}.txt")
            with open(fp, "w", encoding="utf-8") as f:
                f.write(text)
            self.log_info("LYRICS", f"Текст сохранен в архив: {safe}.txt")
        except Exception as e:
            self.log_error("LYRICS", f"Ошибка архивации текста: {e}")

    def delete_lyrics_archive(self, artist: str, title: str) -> bool:
        if not self.lyrics_dir:
            return False
        safe = re.sub(r'[\\/*?:"<>|]', "", f"{artist} - {title}").strip()[:60]
        removed = False
        for ext in (".txt", ".lrc"):
            fp = os.path.join(self.lyrics_dir, f"{safe}{ext}")
            if os.path.exists(fp):
                try:
                    os.remove(fp)
                    removed = True
                    self.log_info("LYRICS", f"Удален неверный архив слов: {safe}{ext}")
                except Exception:
                    pass
        return removed


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


class BubbleScaleSeekListener(dynamic_proxy(SeekBar.OnSeekBarChangeListener)):
    def __init__(self, on_progress):
        super().__init__()
        self.on_progress = on_progress

    def onProgressChanged(self, seek_bar, progress, from_user):
        try:
            if self.on_progress:
                self.on_progress(int(progress))
        except Exception as e:
            CLOG.log_error("SEEKBAR", "SeekBar change error", e)

    def onStartTrackingTouch(self, seek_bar):
        pass

    def onStopTrackingTouch(self, seek_bar):
        pass
# === [/SHARED_BLOCK:COLOR_LOGGER_PROXIES] ===


class RecyclerAttachStateListener(dynamic_proxy(RecyclerView.OnChildAttachStateChangeListener)):
    """Безопасный listener переиспользования и скролла ячеек RecyclerView."""

    def __init__(self, plugin, target_view, original_alpha: float):
        super().__init__()
        self.plugin = plugin
        self.target_ref = WeakReference(target_view)
        self.original_alpha = original_alpha

    def onChildViewAttachedToWindow(self, view):
        pass

    def onChildViewDetachedFromWindow(self, view):
        try:
            target = self.target_ref.get() if self.target_ref else None
            if target is not None:
                # 1.5 Иерархическая проверка: прямое совпадение или принадлежность поддереву открепляемой ячейки
                is_match = False
                if view.equals(target) or (view is target):
                    is_match = True
                else:
                    curr = target.getParent()
                    while curr is not None:
                        if curr.equals(view) or (curr is view):
                            is_match = True
                            break
                        if hasattr(curr, "getParent"):
                            curr = curr.getParent()
                        else:
                            break
                if is_match:
                    # Мгновенно восстанавливаем alpha при откреплении (скролле) ячейки
                    target.setAlpha(float(self.original_alpha))
                    if self.plugin:
                        self.plugin._on_recycler_cell_detached(target)
        except Exception as e:
            CLOG.log_error("RECYCLER", "Attach listener error", e)


# === [SHARED_BLOCK:LYRICS_HELPER] ===
class LyricsHelper:
    """Караоке, SoundCloud oEmbed и локальный архив LRCLIB / NetEase с проверкой длительности."""

    _VERSION_TAGS = (
        "slowed", "reverb", "sped up", "speed up", "nightcore", "remix",
        "instrumental", "karaoke", "cover", "8d", "mashup", "acoustic", "live",
        "pitched", "bass boosted", "lo-fi", "lofi",
    )

    def __init__(self, logger_cb=None):
        self.cache: Dict[Tuple[str, str], List[Tuple[float, str]]] = {}
        self.meta: Dict[Tuple[str, str], Dict[str, Any]] = {}
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
    def _norm_cmp(s: str) -> str:
        s = re.sub(r"\(.*?\)|\[.*?\]", " ", (s or "").lower())
        s = re.sub(r"[^\w\s]", " ", s, flags=re.U)
        return re.sub(r"\s+", " ", s).strip()

    @classmethod
    def _score_candidate(
        cls,
        cand_artist: str,
        cand_title: str,
        cand_dur_sec: float,
        exp_artist: str,
        exp_title: str,
        exp_dur_sec: float,
        source_name: str,
    ) -> float:
        score = 0.0
        ca = cls._norm_cmp(cand_artist)
        ct = cls._norm_cmp(cand_title)
        ea = cls._norm_cmp(exp_artist)
        et = cls._norm_cmp(exp_title)

        # Название трека (главный вес)
        if et and ct:
            if ct == et:
                score += 60.0
            elif et in ct or ct in et:
                score += 36.0
            else:
                e_words = set(et.split())
                c_words = set(ct.split())
                overlap = len(e_words & c_words)
                if overlap > 0:
                    score += 24.0 * (overlap / max(1, len(e_words)))
                else:
                    score -= 70.0
        elif not ct:
            score -= 50.0

        # Штраф за ремиксы / slowed / nightcore / инструменталы если их нет в названии трека
        ct_raw = (cand_title or "").lower()
        et_raw = (exp_title or "").lower()
        for tag in cls._VERSION_TAGS:
            if tag in ct_raw and tag not in et_raw:
                score -= 38.0

        # Исполнитель
        if ea and ca:
            if ca == ea or ea in ca or ca in ea:
                score += 40.0
            else:
                e_aw = set(ea.split())
                c_aw = set(ca.split())
                overlap_a = len(e_aw & c_aw)
                if overlap_a > 0:
                    score += 22.0 * (overlap_a / max(1, len(e_aw)))
                else:
                    score -= 45.0

        # Длительность трека (ключевая защита от ремиксов и чужих версий)
        if exp_dur_sec > 15.0 and cand_dur_sec > 15.0:
            diff = abs(cand_dur_sec - exp_dur_sec)
            if diff <= 3.0:
                score += 50.0
            elif diff <= 8.0:
                score += 30.0
            elif diff <= 15.0:
                score += 10.0
            elif diff <= 28.0:
                score -= 25.0
            else:
                score -= 90.0

        if source_name == "LRCLIB":
            score += 4.0
        return score

    @staticmethod
    def parse_lrc(lrc_text: str) -> List[Tuple[float, str]]:
        if not lrc_text:
            return []
        raw_timeline: List[Tuple[float, str]] = []
        offset_sec = 0.0

        offset_match = re.search(r"\[offset:\s*([+-]?\d+)\]", lrc_text, re.I)
        if offset_match:
            try:
                offset_sec = float(offset_match.group(1)) / 1000.0
            except Exception:
                offset_sec = 0.0

        time_tag_regex = re.compile(r"\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\]")
        inline_word_tag = re.compile(r"<\d{1,2}:\d{2}(?:[.:]\d{1,3})?>")
        for raw_line in lrc_text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith(("[ti:", "[ar:", "[al:", "[by:", "[re:", "[ve:", "[length:")):
                continue
            matches = list(time_tag_regex.finditer(line))
            if not matches:
                continue
            text = time_tag_regex.sub("", line)
            text = inline_word_tag.sub("", text)
            text = re.sub(r"\s{2,}", " ", text).strip()
            if not text:
                continue
            for m in matches:
                mm, ss = int(m.group(1)), int(m.group(2))
                ms_str = m.group(3)
                frac = float(f"0.{ms_str}") if ms_str else 0.0
                t_sec = max(0.0, mm * 60.0 + ss + frac + offset_sec)
                raw_timeline.append((t_sec, text))

        raw_timeline.sort(key=lambda x: x[0])

        # Дедупликация строк с одинаковым таймингом (например, перевод в NetEase/LRCLIB)
        timeline: List[Tuple[float, str]] = []
        for t_sec, text in raw_timeline:
            if timeline and abs(t_sec - timeline[-1][0]) < 0.04:
                prev_text = timeline[-1][1]
                # Оставляем первую непустую строку, если новая дубликат или перевод-комментарий
                if text == prev_text or not prev_text:
                    if not prev_text:
                        timeline[-1] = (t_sec, text)
                continue
            timeline.append((t_sec, text))
        return timeline

    def _req(self, url: str) -> Optional[Any]:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 (Android; ClawdKaraoke/3.5)"}
            )
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                status = getattr(resp, "status", 200)
                body = resp.read()
                length = len(body)
                CLOG.log_debug("LYRICS_NET", f"HTTP {status} len={length} url={url}", status=status, len=length, url=url)
                if status == 200:
                    try:
                        return json.loads(body.decode("utf-8"))
                    except Exception as pe:
                        CLOG.log_warn("LYRICS_NET", f"JSON parse error: {pe} url={url}")
                        return None
        except urllib.error.HTTPError as he:
            CLOG.log_warn("LYRICS_NET", f"HTTP {he.code} {he.reason} url={url}", status=he.code, url=url)
        except urllib.error.URLError as ue:
            CLOG.log_warn("LYRICS_NET", f"Network URLError: {ue.reason} url={url}", url=url)
        except socket.timeout:
            CLOG.log_warn("LYRICS_NET", f"Timeout 3.5s url={url}", status="Timeout", url=url)
        except Exception as e:
            CLOG.log_warn("LYRICS_NET", f"Request failed: {e} url={url}", url=url)
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

    def fetch_lrclib_candidates(self, artist: str, title: str, duration_ms: int = 0) -> List[Dict[str, Any]]:
        exp_dur_sec = float(duration_ms) / 1000.0 if duration_ms and duration_ms > 1000 else 0.0
        candidates: List[Dict[str, Any]] = []
        seen_lrc = set()

        def _add_item(item: Any, boost: float = 0.0):
            if not isinstance(item, dict):
                return
            lrc = item.get("syncedLyrics")
            if not lrc or "[" not in lrc:
                return
            sig = lrc[:120]
            if sig in seen_lrc:
                return
            seen_lrc.add(sig)
            ca = str(item.get("artistName") or artist or "")
            ct = str(item.get("trackName") or title or "")
            cdur = float(item.get("duration") or 0.0)
            sc = self._score_candidate(ca, ct, cdur, artist, title, exp_dur_sec, "LRCLIB") + boost
            candidates.append({
                "source": "LRCLIB",
                "artist": ca,
                "title": ct,
                "duration": cdur,
                "lrc": lrc,
                "score": sc,
            })

        if artist:
            qa, qt = urllib.parse.quote(artist), urllib.parse.quote(title)
            dur_q = f"&duration={int(round(exp_dur_sec))}" if exp_dur_sec > 15.0 else ""
            data = self._req(f"https://lrclib.net/api/get?artist_name={qa}&track_name={qt}{dur_q}")
            _add_item(data, boost=12.0)

        query = urllib.parse.quote(f"{artist} {title}".strip())
        results = self._req(f"https://lrclib.net/api/search?q={query}")
        if isinstance(results, list):
            for item in results:
                _add_item(item)

        if not candidates and artist and title:
            qt_only = urllib.parse.quote(title)
            results2 = self._req(f"https://lrclib.net/api/search?track_name={qt_only}")
            if isinstance(results2, list):
                for item in results2:
                    _add_item(item)

        candidates.sort(key=lambda c: c["score"], reverse=True)
        return candidates[:8]

    def fetch_lrclib(self, artist: str, title: str, duration_ms: int = 0) -> Optional[str]:
        cands = self.fetch_lrclib_candidates(artist, title, duration_ms=duration_ms)
        if not cands:
            return None
        best = cands[0]
        if duration_ms > 15000 and best["score"] < -15.0:
            CLOG.log_warn(
                "LYRICS",
                f"LRCLIB отклонен из-за несовпадения (score={best['score']:.1f}, match='{best['artist']} - {best['title']}', dur={best['duration']:.0f}s vs track={duration_ms/1000.0:.0f}s)",
            )
            return None
        return best["lrc"]

    def fetch_netease_candidates(self, artist: str, title: str, duration_ms: int = 0) -> List[Dict[str, Any]]:
        exp_dur_sec = float(duration_ms) / 1000.0 if duration_ms and duration_ms > 1000 else 0.0
        candidates: List[Dict[str, Any]] = []
        seen_ids = set()

        for q_str in (f"{artist} {title}".strip(), title.strip()):
            if not q_str:
                continue
            query = urllib.parse.quote(q_str)
            data = self._req(f"https://music.163.com/api/search/get?s={query}&type=1&limit=5")
            if not data:
                continue
            songs = data.get("result", {}).get("songs", [])
            scored_songs = []
            for song in songs:
                song_id = song.get("id")
                if not song_id or song_id in seen_ids:
                    continue
                seen_ids.add(song_id)
                ca = ", ".join(str(ar.get("name") or "") for ar in (song.get("artists") or []) if isinstance(ar, dict))
                ct = str(song.get("name") or "")
                cdur = float(song.get("duration") or 0.0) / 1000.0
                sc = self._score_candidate(ca, ct, cdur, artist, title, exp_dur_sec, "NETEASE")
                scored_songs.append((sc, song_id, ca, ct, cdur))

            scored_songs.sort(key=lambda x: x[0], reverse=True)
            for sc, song_id, ca, ct, cdur in scored_songs[:3]:
                if sc < -35.0:
                    continue
                ldata = self._req(f"https://music.163.com/api/song/lyric?id={song_id}&lv=1&kv=1&tv=-1")
                if ldata:
                    lrc = ldata.get("lrc", {}).get("lyric")
                    if lrc and "[" in lrc:
                        candidates.append({
                            "source": "NETEASE",
                            "artist": ca,
                            "title": ct,
                            "duration": cdur,
                            "lrc": lrc,
                            "score": sc,
                        })
            if candidates:
                break

        candidates.sort(key=lambda c: c["score"], reverse=True)
        return candidates[:6]

    def fetch_netease(self, artist: str, title: str, duration_ms: int = 0) -> Optional[str]:
        cands = self.fetch_netease_candidates(artist, title, duration_ms=duration_ms)
        return cands[0]["lrc"] if cands else None

    def get_lyrics_meta(self, artist: str, title: str) -> Dict[str, Any]:
        clean_a, clean_t = self.clean_metadata(artist, title)
        key = (clean_a.lower(), clean_t.lower())
        with self.lock:
            return dict(self.meta.get(key) or {})

    def apply_manual_candidate(self, artist: str, title: str, cand: Dict[str, Any]) -> List[Tuple[float, str]]:
        clean_a, clean_t = self.clean_metadata(artist, title)
        key = (clean_a.lower(), clean_t.lower())
        lrc = cand.get("lrc") or ""
        timeline = self.parse_lrc(lrc)
        if timeline:
            CLOG.save_lyrics_archive(clean_a, clean_t, lrc)
            with self.lock:
                self.cache[key] = timeline
                meta = dict(self.meta.get(key) or {})
                meta.update({
                    "source": cand.get("source", "MANUAL"),
                    "matched_artist": cand.get("artist", clean_a),
                    "matched_title": cand.get("title", clean_t),
                    "duration_sec": float(cand.get("duration") or 0.0),
                    "lines": len(timeline),
                })
                self.meta[key] = meta
        return timeline

    def get_lyrics_async(self, artist: str, title: str, callback, duration_ms: int = 0, force_refresh: bool = False):
        clean_a, clean_t = self.clean_metadata(artist, title)
        if not clean_t:
            callback([])
            return

        key = (clean_a.lower(), clean_t.lower())
        with self.lock:
            if force_refresh:
                self.cache.pop(key, None)
                self.meta.pop(key, None)
            elif key in self.cache:
                callback(self.cache[key])
                return
            if key in self.loading:
                return
            self.loading.add(key)

        def _worker():
            try:
                exp_dur_sec = float(duration_ms) / 1000.0 if duration_ms and duration_ms > 1000 else 0.0
                if force_refresh:
                    CLOG.delete_lyrics_archive(clean_a, clean_t)

                # 1. Проверяем локальный архив на диске
                cached_text = None if force_refresh else CLOG.check_lyrics_archive(clean_a, clean_t)
                source_tag = "ARCHIVE"
                lrc = cached_text
                matched_cand: Optional[Dict[str, Any]] = None
                all_cands: List[Dict[str, Any]] = []

                if not lrc:
                    self._log(f"Поиск слов: '{clean_a}' — '{clean_t}' (dur={exp_dur_sec:.0f}с)")
                    lrclib_cands = self.fetch_lrclib_candidates(clean_a, clean_t, duration_ms=duration_ms)
                    netease_cands = []
                    if not lrclib_cands or lrclib_cands[0]["score"] < 45.0:
                        netease_cands = self.fetch_netease_candidates(clean_a, clean_t, duration_ms=duration_ms)
                    all_cands = sorted(lrclib_cands + netease_cands, key=lambda c: c["score"], reverse=True)
                    if all_cands:
                        best = all_cands[0]
                        if exp_dur_sec <= 15.0 or best["score"] >= -15.0:
                            matched_cand = best
                            lrc = best["lrc"]
                            source_tag = best["source"]
                        else:
                            CLOG.log_warn("LYRICS", f"Все найденные LRC отклонены по score ({best['score']:.1f})")
                    if lrc:
                        CLOG.save_lyrics_archive(clean_a, clean_t, lrc)

                timeline = self.parse_lrc(lrc) if lrc else []
                lrc_last_t = timeline[-1][0] if timeline else 0.0
                meta_obj = {
                    "source": source_tag,
                    "matched_artist": matched_cand.get("artist", clean_a) if matched_cand else clean_a,
                    "matched_title": matched_cand.get("title", clean_t) if matched_cand else clean_t,
                    "duration_sec": (matched_cand.get("duration") or lrc_last_t) if matched_cand else lrc_last_t,
                    "query_dur_sec": exp_dur_sec,
                    "score": matched_cand.get("score", 0.0) if matched_cand else 0.0,
                    "lines": len(timeline),
                    "candidates": all_cands,
                }
                with self.lock:
                    self.meta[key] = meta_obj
                    if timeline:
                        self.cache[key] = timeline
                self._log(
                    f"Загружено строк ({source_tag}) для '{clean_t}': {len(timeline)} "
                    f"(LRC~{meta_obj['duration_sec']:.0f}с / трек~{exp_dur_sec:.0f}с)"
                )
                callback(timeline)
            except Exception as e:
                CLOG.log_error("LYRICS", f"Ошибка получения слов для '{clean_t}'", e)
                callback([])
            finally:
                with self.lock:
                    self.loading.discard(key)

        threading.Thread(target=_worker, daemon=True, name="lyrics_fetcher").start()
# === [/SHARED_BLOCK:LYRICS_HELPER] ===


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
        self._karaoke_switch_r = None
        self._auto_return_r = None
        self._grad_anim_r = None
        self._running = False
        self._paused = False
        self._unloaded = False
        self._cfg = {}

        self._decor = None
        self._pet = None
        self._bubble = None
        self._artwork_row = None
        self._artwork_view = None
        self._artwork_bg_gd = None
        self._artwork_title_tv = None
        self._artwork_bmp = None
        self._artwork_track_key = None
        self._artwork_last_has_flag = False
        self._bubble_text = None
        self._bubble_subtext = None
        self._sync_debug_tv = None
        self._media_controls_layout = None
        self._media_ctrl_btns = []
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
        self._eaten = []  # список словарей: view_ref, alpha, bmp, w, h, cls_name
        self._spitting = []
        self._recycler_listeners = []

        self._unit = 1
        self._w = 1
        self._h = 1
        self._frames = {}
        self._particle_bitmaps = {}
        self._frame_key = None

        # Dirty flag кэш кадра
        self._last_rendered_x = None
        self._last_rendered_y = None
        self._last_rendered_rot = None
        self._last_rendered_frame_key = None
        self._last_rendered_bmp = None
        self._bubble_mode = None
        self._last_bubble_palette: Optional[Tuple[int, int, int]] = None
        self._target_palette: Tuple[int, int, int] = DEFAULT_KARAOKE_PALETTE
        self._grad_curr: Tuple[int, int, int] = DEFAULT_KARAOKE_PALETTE
        self._grad_from: Tuple[int, int, int] = DEFAULT_KARAOKE_PALETTE
        self._grad_target: Tuple[int, int, int] = DEFAULT_KARAOKE_PALETTE
        self._grad_anim_start = 0.0
        self._karaoke_border_gd = None
        self._karaoke_bg_gd = None
        self._karaoke_layer_drawable = None

        self._lyrics_helper = LyricsHelper(logger_cb=self._add_debug_log)
        self._current_track_id = None
        self._lyrics_timeline: List[Tuple[float, str]] = []
        self._current_lyric_idx = -1
        self._is_singing = False
        self._test_karaoke_active = False
        self._lyrics_retry_count = 0
        self._last_lyrics_retry = 0.0
        self._last_failsafe_check = 0.0
        self._last_active_clean_a = ""
        self._last_active_clean_t = ""
        self._active_duration_ms = 0
        self._dp_cache: Dict[Any, float] = {}

        # Монотонный якорь синхронизации (ms + monotonic + speed) и анти-дрейф + отладка
        self._anchor_pos_ms = 0.0
        self._anchor_mono = 0.0
        self._anchor_speed = 1.0
        self._sync_offset_ms = 0.0
        self._track_base_pos = 0.0
        self._track_base_time = 0.0
        self._track_is_playing = False
        self._playback_speed = 1.0
        self._accent_color: Optional[int] = None
        self._user_offset = 0.0
        self._session_offsets: Dict[str, float] = {}
        self._position_known = True
        self._text_anim_seq: Dict[int, int] = {}
        self._sync_trace_log = collections.deque(maxlen=40)
        self._last_sync_source = "NONE"
        self._last_sync_delta_ms = 0.0
        self._last_raw_pos_ms = 0
        self._last_bridge_raw_pos_ms = -1
        self._last_bridge_raw_rx_mono = 0.0
        self._last_tg_raw_pos_ms = -1
        self._bridge_back_snap_streak = 0
        self._last_hud_upd = 0.0
        self._last_hud_text = ""

        # Clawd Bridge сетевой шлюз (SSE + Polling Fallback)
        self._bridge_thread = None
        self._bridge_stop_event = threading.Event()
        self._bridge_consecutive_errors = 0
        self._bridge_interval = 1.6  # fallback polling 1.5–2.0 с только при отключенном SSE
        self._bridge_last_ping_latency = 0.0
        self._bridge_data: Optional[Dict[str, Any]] = None
        self._bridge_lock = threading.Lock()
        self._bridge_mode = "INIT"
        self._bridge_sse_resp = None
        self._bridge_sse_connected = False
        self._bridge_push_pending = False
        self._last_sse_rx_mono = 0.0
        self._last_processed_bridge_rx_mono = 0.0

        # Буфер обмена
        self._last_checked_clip = ""
        self._clip_check_time = 0.0

        # Батарея и питание
        self._battery_level = 100
        self._is_charging = False
        self._power_save_mode = False
        self._last_battery_check = 0.0
        self._nightstand_mode = False
        self._laser_active = False

        # Телеметрия производительности (60с сводка)
        self._last_summary_time = time.monotonic()
        self._tick_times = collections.deque(maxlen=120)
        self._frame_intervals = collections.deque(maxlen=120)
        self._last_tick_start = 0.0
        self._platform_scan_times = collections.deque(maxlen=20)
        self._platforms_cache = []
        self._last_platforms_scan_time = 0.0

        self._reset_state()

    def _add_debug_log(self, msg: str):
        CLOG.log_info("APP", msg)

    def on_plugin_load(self):
        CLOG.ensure_started()
        CLOG.log_info("LOAD", f"Загрузка Clawd v{__version__} by {__author__}...")
        with self._bridge_lock:
            self._bridge_data = None
        self._clear_playback_anchors(reset_user_offset=True)
        self._reload_cfg()
        self._handler = Handler(Looper.getMainLooper())
        self._tick_r = R(self._tick)
        self._karaoke_switch_r = R(self._do_karaoke_line_switch)
        self._auto_return_r = R(self._on_auto_return_triggered)
        self._grad_anim_r = R(self._step_gradient_anim)

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
        self._start_bridge_daemon()
        run_on_ui_thread(lambda: self._start(greet=True))

    def on_plugin_unload(self):
        CLOG.log_info("UNLOAD", f"Выгрузка Clawd v{__version__}...")
        self._unloaded = True
        self._running = False

        # Остановка колбэков
        if self._handler is not None:
            if self._tick_r is not None:
                self._handler.removeCallbacks(self._tick_r)
            if self._karaoke_switch_r is not None:
                self._handler.removeCallbacks(self._karaoke_switch_r)
            if self._auto_return_r is not None:
                self._handler.removeCallbacks(self._auto_return_r)
            if self._grad_anim_r is not None:
                self._handler.removeCallbacks(self._grad_anim_r)

        # Остановка фонового потока моста и полная очистка якорей/буферов
        self._stop_bridge_daemon()
        with self._bridge_lock:
            self._bridge_data = None
        self._clear_playback_anchors(reset_user_offset=True)

        delegate = self._msg_delegate
        self._msg_delegate = None
        accounts = self._observed_accounts
        self._observed_accounts = []
        self._on_ui(lambda: self._remove_observers(delegate, accounts))
        self._on_ui(self._stop_sensor)
        self._on_ui(self._detach_views)

        # Сброс логов на диск
        CLOG.flush_and_stop()

# === [SHARED_BLOCK:BRIDGE_DAEMON] ===
    def _start_bridge_daemon(self):
        if self._bridge_thread is not None and self._bridge_thread.is_alive():
            return
        self._bridge_stop_event.clear()
        self._bridge_thread = threading.Thread(target=self._bridge_worker, daemon=True, name="clawd_bridge_client")
        self._bridge_thread.start()
        CLOG.log_info("BRIDGE", "Поток Clawd Bridge запущен: SSE (/events) + fallback polling (/now-playing)")

    def _stop_bridge_daemon(self):
        self._bridge_stop_event.set()
        resp = self._bridge_sse_resp
        self._bridge_sse_resp = None
        if resp is not None:
            try:
                resp.close()
            except Exception:
                pass
        if self._bridge_thread and self._bridge_thread.is_alive():
            self._bridge_thread.join(timeout=0.6)
        self._bridge_thread = None

    def _schedule_bridge_sse_wake(self):
        if self._unloaded or self._bridge_push_pending:
            return
        self._bridge_push_pending = True

        def _wake():
            self._bridge_push_pending = False
            if self._unloaded or not self._running or self._paused:
                return
            self._media_check = 0.0
            if self._pos_ready:
                self._poll_media(time.monotonic())
            self._schedule(0)

        run_on_ui_thread(_wake)

    def _on_bridge_payload(self, data: Dict[str, Any], mode: str, dt_ping: float = 0.0):
        rx_mono = time.monotonic()
        if self._bridge_consecutive_errors >= 5:
            CLOG.log_info("BRIDGE", f"Связь восстановлена ({mode})! Сброс backoff")
        self._bridge_consecutive_errors = 0
        self._bridge_interval = 1.6
        self._bridge_mode = mode
        if dt_ping > 0.0:
            self._bridge_last_ping_latency = dt_ping
        payload = dict(data)
        payload["_received_mono"] = rx_mono
        payload["_is_sse_event"] = (mode == "SSE")
        with self._bridge_lock:
            self._bridge_data = payload
        if mode == "SSE":
            self._schedule_bridge_sse_wake()

    def _bridge_poll_once(self) -> Tuple[bool, Optional[Dict[str, Any]], float]:
        url = "http://127.0.0.1:44444/now-playing"
        t0 = time.monotonic()
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": f"ClawdPet/{__version__} (Android)",
                    "Host": "127.0.0.1:44444",
                },
            )
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    raw = resp.read().decode("utf-8")
                    data = json.loads(raw)
                    dt_ping = (time.monotonic() - t0) * 1000.0
                    return True, data, dt_ping
        except Exception:
            pass
        return False, None, (time.monotonic() - t0) * 1000.0

    def _bridge_sse_loop(self) -> bool:
        sse_url = "http://127.0.0.1:44444/events"
        t0 = time.monotonic()
        resp = None
        connected = False
        try:
            req = urllib.request.Request(
                sse_url,
                headers={
                    "Accept": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "User-Agent": f"ClawdPet/{__version__} (Android)",
                    "Host": "127.0.0.1:44444",
                },
            )
            resp = urllib.request.urlopen(req, timeout=28.0)
            self._bridge_sse_resp = resp
            if getattr(resp, "status", 200) != 200:
                return False
            connected = True
            self._bridge_sse_connected = True
            self._bridge_mode = "SSE"
            self._bridge_consecutive_errors = 0
            self._bridge_last_ping_latency = (time.monotonic() - t0) * 1000.0
            CLOG.log_info("BRIDGE", "Подключен SSE-поток /events (polling отключен)")

            event_name = ""
            data_lines: List[str] = []
            while not self._bridge_stop_event.is_set():
                raw_line = resp.readline()
                if not raw_line:
                    break
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                if line.startswith(":"):
                    # Keep-alive комментарий (: keepalive)
                    self._bridge_consecutive_errors = 0
                    continue
                if line == "":
                    if data_lines:
                        raw_data = "\n".join(data_lines)
                        if event_name in ("", "now_playing"):
                            try:
                                parsed = json.loads(raw_data)
                                if isinstance(parsed, dict):
                                    self._on_bridge_payload(parsed, "SSE")
                            except Exception as pe:
                                CLOG.log_warn("BRIDGE", f"SSE JSON parse error: {pe}")
                    event_name = ""
                    data_lines = []
                    continue
                if line.startswith("event:"):
                    event_name = line[6:].strip()
                elif line.startswith("data:"):
                    val = line[5:]
                    if val.startswith(" "):
                        val = val[1:]
                    data_lines.append(val)
        except Exception as e:
            if not self._bridge_stop_event.is_set():
                CLOG.log_debug("BRIDGE", f"SSE поток отключен ({e}), переход в fallback")
        finally:
            self._bridge_sse_connected = False
            self._bridge_sse_resp = None
            if resp is not None:
                try:
                    resp.close()
                except Exception:
                    pass
        return connected

    def _bridge_worker(self):
        while not self._bridge_stop_event.is_set():
            was_sse_connected = self._bridge_sse_loop()
            if self._bridge_stop_event.is_set():
                break

            if was_sse_connected:
                # Переподключение SSE через 1.2 секунды после разрыва
                self._bridge_stop_event.wait(1.2)
                continue

            # Fallback polling GET /now-playing (1.5–2.0 с) ТОЛЬКО пока SSE не подключён
            poll_cycles = 0
            while not self._bridge_stop_event.is_set() and not self._bridge_sse_connected and poll_cycles < 5:
                poll_cycles += 1
                ok, data, dt_ping = self._bridge_poll_once()
                self._bridge_last_ping_latency = dt_ping
                if ok and isinstance(data, dict):
                    self._on_bridge_payload(data, "Polling", dt_ping)
                    self._bridge_stop_event.wait(1.6)
                else:
                    self._bridge_consecutive_errors += 1
                    self._bridge_mode = "Fallback"
                    if self._bridge_consecutive_errors >= 5:
                        self._bridge_interval = 3.0
                        if self._bridge_consecutive_errors == 5:
                            CLOG.log_warn("BRIDGE", "5 ошибок связи подряд! Переход в backoff на 3.0 секунды")
                    else:
                        self._bridge_interval = 1.6

                    fallback_data = self._read_fallback_sync_json()
                    with self._bridge_lock:
                        self._bridge_data = fallback_data

                    self._bridge_stop_event.wait(self._bridge_interval)
                    if self._bridge_consecutive_errors >= 5:
                        break

    def _read_fallback_sync_json(self) -> Optional[Dict[str, Any]]:
        if not CLOG.base_dir:
            return None
        sync_fp = os.path.join(CLOG.base_dir, "sync.json")
        try:
            if not os.path.exists(sync_fp):
                return None
            with open(sync_fp, "r", encoding="utf-8") as f:
                d = json.load(f)
            ts = float(d.get("timestamp", 0))
            # 1.1 Нормализация timestamp: если в миллисекундах (> 1e11), приводим к секундам
            if ts > 1e11:
                ts = ts / 1000.0
            # Считывается только если timestamp внутри файла не старше 5 секунд!
            if abs(time.time() - ts) <= 5.0:
                has_media = bool(d.get("has_media", True))
                is_playing = bool(d.get("is_playing", True))
                if not has_media:
                    return None
                # Извлекаются исключительно метаданные для поиска текста и статус паузы!
                return {
                    "has_media": True,
                    "is_playing": is_playing,
                    "player": d.get("player", "sync_file"),
                    "artist": d.get("artist", ""),
                    "title": d.get("title", ""),
                    "position_ms": 0,
                    "duration_ms": 0,
                    "position_known": False,
                    "timestamp": ts,
                    "_received_mono": time.monotonic(),
                    "is_fallback": True,
                }
        except Exception:
            pass
        return None
# === [/SHARED_BLOCK:BRIDGE_DAEMON] ===

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
            if self._handler is not None:
                if self._tick_r is not None:
                    self._handler.removeCallbacks(self._tick_r)
                if self._karaoke_switch_r is not None:
                    self._handler.removeCallbacks(self._karaoke_switch_r)
                if self._auto_return_r is not None:
                    self._handler.removeCallbacks(self._auto_return_r)
                if self._grad_anim_r is not None:
                    self._handler.removeCallbacks(self._grad_anim_r)
            self._on_ui(self._stop_sensor)
            # Принудительный возврат съеденного при PAUSE
            self._on_ui(self._give_back)
        elif event_type == AppEvent.RESUME:
            self._paused = False
            run_on_ui_thread(lambda: self._start(greet=False))

    def create_settings(self) -> List[Any]:
        pets = int(self.get_setting("pets_count", 0) or 0)
        eaten = int(self.get_setting("eaten_count", 0) or 0)
        cleaned = int(self.get_setting("poops_cleaned", 0) or 0)
        return [
            Header(text=f"Питомец Clawd v{__version__}"),
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
            Text(
                text="Размер рамки текста (0.4x – 2.0x)",
                subtext=f"Текущий масштаб: {clamp(float(self.get_setting('bubble_scale', 1.0) or 1.0), 0.4, 2.0):.2f}x",
                icon="msg_customize",
                on_click=lambda _v=None: run_on_ui_thread(self._open_bubble_scale_dialog),
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
            Header(text="Караоке и Clawd Bridge 🎵"),
            Switch(
                key="dance",
                text="Реагировать на музыку",
                default=True,
                subtext="Танцевать под треки Telegram и Clawd Bridge (30 fps)",
                icon="msg_voice_headphones",
                on_change=lambda v: self._on_cfg_change("dance", v),
            ),
            Switch(
                key="karaoke",
                text="Синхронное караоке",
                default=True,
                subtext="LRCLIB + NetEase + архив Lyrics/ + кнопка выбора строки [📋]",
                icon="msg_discussion",
                on_change=lambda v: self._on_cfg_change("karaoke", v),
            ),
            Switch(
                key="singing_mouth_enabled",
                text="Анимация рта при пении",
                default=False,
                subtext="Открывать рот в ритм слов (по умолчанию выкл — только танец)",
                icon="msg_voice",
                on_change=lambda v: self._on_cfg_change("singing_mouth_enabled", v),
            ),
            Switch(
                key="animated_gradient_border",
                text="Анимированная градиентная рамка",
                default=True,
                subtext="Плавное вращение акцентных цветов обложки по кругу",
                icon="msg_colors",
                on_change=lambda v: self._on_cfg_change("animated_gradient_border", v),
            ),
            Switch(
                key="media_controls",
                text="Пульт управления в облачке",
                default=True,
                subtext="Кнопки [⏮], [⏯], [⏭] и [📋] прямо над питомцем",
                icon="msg_round_play",
                on_change=lambda v: self._on_cfg_change("media_controls", v),
            ),
            Switch(
                key="sync_debug_hud",
                text="Отладка синхронизации (HUD)",
                default=False,
                subtext="Показывать SRC, raw/calc, Δms и источник LRC прямо под текстом",
                icon="msg_diagnostic",
                on_change=lambda v: self._on_cfg_change("sync_debug_hud", v),
            ),
            Switch(
                key="clipboard_sync",
                text="Автоперехват из буфера (SoundCloud)",
                default=False,
                subtext="Поёт скопированные ссылки SoundCloud (по умолчанию выкл)",
                icon="msg_copy",
                on_change=lambda v: self._on_cfg_change("clipboard_sync", v),
            ),
            Switch(
                key="sc_autostart_incoming",
                text="Автозапуск SoundCloud из чатов",
                default=False,
                subtext="Запускать караоке при ссылках в сообщениях (по умолчанию выкл)",
                icon="msg_link",
                on_change=lambda v: self._on_cfg_change("sc_autostart_incoming", v),
            ),
            Header(text="Поведение и «Абсолютный Обжора» 2.0"),
            Switch(
                key="eat",
                text="«Абсолютный Обжора» 2.0",
                default=True,
                subtext="Безопасно ест любой View (до 12 шт), не ломает списки",
                icon="msg_emoji_food",
                on_change=lambda v: self._on_cfg_change("eat", v),
            ),
            Selector(
                key="auto_return",
                text="Автовозврат съеденного",
                default=1,
                items=AUTO_RETURN_ITEMS,
                icon="msg_reset",
                on_change=lambda v: self._on_cfg_change("auto_return", v),
            ),
            Switch(
                key="tg_events",
                text="Реакции Telegram",
                default=True,
                subtext="Разделяет заметки Избранного и входящие от других лиц",
                icon="msg_notifications",
                on_change=lambda v: self._on_cfg_change("tg_events", v),
            ),
            Selector(
                key="tg_chat_scope",
                text="Реагировать на сообщения",
                default=0,
                items=TG_CHAT_SCOPE_ITEMS,
                icon="msg_discussion",
                on_change=lambda v: self._on_cfg_change("tg_chat_scope", v),
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
                subtext="Проверить анимации, Clawd Bridge, Tap-to-Sync, обжору и датчики",
                icon="msg_diagnostic",
                accent=True,
                on_click=lambda _v=None: run_on_ui_thread(self._open_test_sandbox),
            ),
            Text(
                text="Открыть суточный лог (Downloads/ClaudePet/Logs/*.txt)",
                subtext=f"Записей в буфере: {len(CLOG.ring_buffer)}",
                icon="msg_log",
                on_click=lambda _v=None: run_on_ui_thread(self._show_logs_dialog),
            ),
            Text(
                text="Скопировать отчёт системы 📋",
                subtext="Дамп моста, LRC-метаданных, трассировки синхронизации и лога",
                icon="msg_copy",
                on_click=lambda _v=None: run_on_ui_thread(self._copy_system_report),
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
                text="Вернуть съеденное (Выплюнуть всё)",
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

    def _open_test_sandbox(self):
        try:
            ctx = self._get_safe_activity()
            if not ctx:
                return

            tests = [
                ("1. Тест рук (Машет обеими)", "Clawd машет по очереди левой, правой и поднимает обе"),
                ("2. Тест всех эмоций", "Радость, шок, сон, злость, головокружение, глаза-$"),
                ("3. Тест Clawd Bridge (Шлюз)", "Проверка подключения к 127.0.0.1:44444 и backoff"),
                ("4. Тест караоке (Автономное Демо)", "Запуск трека со словами и проверка джиттер-фильтра"),
                ("5. Тест «Обжоры» (Шаг веса)", "Съедает элемент с WeakReference и полнеет на 1 стадию"),
                ("6. Тест выплёвывания", "Возвращает всё съеденное на экран без пустых мест"),
                ("7. Тест лазера", "Спавнит точку лазера и бежит за ней"),
                ("8. Тест шара предсказаний 🎱", "Показывает случайный ответ оракула"),
                ("9. Тест тряски (Инерция)", "Бросок питомца по вектору движения"),
                ("10. Тест Telegram: Входящее сообщение", "Эмуляция сообщения от собеседника"),
                ("11. Тест Telegram: Заметка в Избранное", "Эмуляция отправки сообщения себе"),
                ("12. Тест батареи: <15% и Зарядка", "Переключает режимы энергии"),
            ]

            b = AlertDialog.Builder(ctx)
            b.setTitle(f"Тестовый полигон Clawd v{__version__}")
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
            mode = self._bridge_mode
            status = "В бэкоффе (3.0с)" if self._bridge_consecutive_errors >= 5 else f"{mode} ({self._bridge_interval*1000:.0f} мс)"
            errs = self._bridge_consecutive_errors
            ping = self._bridge_last_ping_latency
            self._say(f"Bridge [{mode}]: {status}, пинг {ping:.1f}мс, ошибок: {errs}", force=True)
            self._hop(self._dp(400))
        elif index == 3:
            # Автономное демо караоке с виртуальным таймером
            self._test_karaoke_active = True
            self._start_custom_song("Kai Angel - andy warhol")
        elif index == 4:
            self._try_eat(now, 0.0)
        elif index == 5:
            self._give_back()
        elif index == 6:
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

    def _show_logs_dialog(self):
        try:
            ctx = self._get_safe_activity()
            if not ctx:
                return

            # Читаем из кольцевого буфера
            lines = list(CLOG.ring_buffer)[-50:]
            content = "=== КОЛЬЦЕВОЙ БУФЕР В ПАМЯТИ (500 строк) ===\n" + "\n".join(lines)

            b = AlertDialog.Builder(ctx)
            b.setTitle("Журнал диагностики Clawd")
            scroll = ScrollView(ctx)
            tv = TextView(ctx)
            tv.setPadding(AndroidUtilities.dp(16), AndroidUtilities.dp(8), AndroidUtilities.dp(16), AndroidUtilities.dp(8))
            tv.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 11.5)
            tv.setText(content)
            tv.setTextIsSelectable(True)
            scroll.addView(tv)
            b.setView(scroll)
            b.setPositiveButton("Закрыть", None)
            b.setNeutralButton("Скопировать всё", TGDialogClickListener(lambda _d, _w: self._copy_system_report()))
            b.show()
        except Exception as e:
            CLOG.log_error("LOGS_UI", "Show logs error", e)

    def _copy_system_report(self):
        try:
            ctx = self._get_safe_activity()
            if not ctx:
                return
            cm = ctx.getSystemService(Context.CLIPBOARD_SERVICE)
            if not cm:
                return

            lrc_meta = self._lyrics_helper.get_lyrics_meta(self._last_active_clean_a, self._last_active_clean_t) if self._last_active_clean_t else {}
            sync_trace_lines = list(self._sync_trace_log)
            last_lines = list(CLOG.ring_buffer)[-200:]
            report = (
                f"=== ДАМП СИСТЕМЫ CLAWD v{__version__} ===\n"
                f"Время: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Статус моста: mode={self._bridge_mode}, errors={self._bridge_consecutive_errors}, interval={self._bridge_interval*1000:.0f}ms, latency={self._bridge_last_ping_latency:.1f}ms\n"
                f"Текущий трек: {self._current_track_id} (dur={self._active_duration_ms/1000.0:.1f}s, speed={self._playback_speed:.2f}x, src={self._last_sync_source})\n"
                f"Якорь: raw={self._last_raw_pos_ms}ms, calc={self._get_current_track_pos_ms():.0f}ms, Δ={self._last_sync_delta_ms:+.0f}ms, idx={self._current_lyric_idx}/{len(self._lyrics_timeline)}\n"
                f"LRC совпадение: src={lrc_meta.get('source', 'NONE')}, '{lrc_meta.get('matched_artist', '')} - {lrc_meta.get('matched_title', '')}', lrc_dur={lrc_meta.get('duration_sec', 0):.1f}s, score={lrc_meta.get('score', 0):.1f}\n"
                f"Смещение _user_offset: {self._user_offset:.3f} с\n"
                f"Полнота желудка: {len(self._eaten)}/12 (стадия {self._fat_stage()})\n"
                f"Батарея: {self._battery_level}% (зарядка={self._is_charging}, эконом={self._power_save_mode})\n"
                f"\n=== ТРАССИРОВКА СИНХРОНИЗАЦИИ (ПОСЛЕДНИЕ {len(sync_trace_lines)} СОБЫТИЙ) ===\n"
                + ("\n".join(sync_trace_lines) if sync_trace_lines else "(пусто)")
                + f"\n\n=== ПОСЛЕДНИЕ 200 СТРОК ЛОГА ===\n"
                + "\n".join(last_lines)
            )

            clip = ClipData.newPlainText("Clawd Diagnostics Report", report)
            cm.setPrimaryClip(clip)
            self._say("Отчёт скопирован в буфер! 📋", force=True)
            self._hop(self._dp(400))
        except Exception as e:
            CLOG.log_error("REPORT", "Report copy error", e)

    def _trigger_clean_cache(self):
        try:
            self._say("clean_cache", force=True)
            self._hop(self._dp(450))
            for _ in range(4):
                self._spawn_particle("spark")
            System = jclass("java.lang.System")
            System.gc()
            CLOG.log_info("CACHE", "Очистка кэша завершена успешно")
        except Exception as e:
            CLOG.log_error("CACHE", "Cache clean error", e)

# === [SHARED_BLOCK:MEDIA_KEYS] ===
    def _dispatch_media_key(self, key_code: int):
        try:
            ctx = self._pet.getContext() if self._pet else (self._bubble.getContext() if self._bubble else LaunchActivity.instance)
            if not ctx:
                return
            am = ctx.getSystemService(Context.AUDIO_SERVICE)
            if am:
                am.dispatchMediaKeyEvent(KeyEvent(KeyEvent.ACTION_DOWN, key_code))
                am.dispatchMediaKeyEvent(KeyEvent(KeyEvent.ACTION_UP, key_code))
                self._hop(self._dp(200))
        except Exception as e:
            CLOG.log_error("MEDIA_KEY", "Key dispatch error", e)
# === [/SHARED_BLOCK:MEDIA_KEYS] ===

    def _reload_cfg(self):
        try:
            raw_scale = float(self.get_setting("bubble_scale", 1.0) or 1.0)
        except Exception:
            raw_scale = 1.0
        self._cfg = {
            "show": bool(self.get_setting("show", True)),
            "size": int(self.get_setting("size", 1) or 0),
            "bubble_scale": clamp(raw_scale, 0.4, 2.0),
            "color": int(self.get_setting("color", 0) or 0),
            "hat": int(self.get_setting("hat", 0) or 0),
            "gravity": bool(self.get_setting("gravity", False)),
            "wander": bool(self.get_setting("wander", True)),
            "phrases": bool(self.get_setting("phrases", True)),
            "sleep": int(self.get_setting("sleep", 1) or 0),
            "haptics": bool(self.get_setting("haptics", True)),
            "eat": bool(self.get_setting("eat", True)),
            "auto_return": int(self.get_setting("auto_return", 1) or 0),
            "tg_events": bool(self.get_setting("tg_events", True)),
            "tg_chat_scope": clamp(int(self.get_setting("tg_chat_scope", 0) or 0), 0, 1),
            "dance": bool(self.get_setting("dance", True)),
            "karaoke": bool(self.get_setting("karaoke", True)),
            "singing_mouth_enabled": bool(self.get_setting("singing_mouth_enabled", False)),
            "animated_gradient_border": bool(self.get_setting("animated_gradient_border", True)),
            "media_controls": bool(self.get_setting("media_controls", True)),
            "sync_debug_hud": bool(self.get_setting("sync_debug_hud", False)),
            "battery_react": bool(self.get_setting("battery_react", True)),
            "clipboard_sync": bool(self.get_setting("clipboard_sync", False)),
            "sc_autostart_incoming": bool(self.get_setting("sc_autostart_incoming", False)),
            "poop": bool(self.get_setting("poop", True)),
            "shake": bool(self.get_setting("shake", True)),
        }
        self._sync_offset_ms = 0.0
        self._user_offset = 0.0

    def _on_cfg_change(self, key, value):
        self._cfg[key] = value
        if key == "show":
            run_on_ui_thread(lambda: self._apply_show(bool(value)))
        elif key in ("size", "color", "hat"):
            run_on_ui_thread(self._rebuild_sprites)
        elif key == "dance" and not value:
            def _stop_music_state():
                self._media = None
                self._track_is_playing = False
                self._is_singing = False
                self._test_karaoke_active = False
                self._current_track_id = None
                self._lyrics_timeline = []
                self._clear_playback_anchors(reset_user_offset=False)
                self._accent_color = None
                self._target_palette = DEFAULT_KARAOKE_PALETTE
                self._clear_artwork()
                if self._handler and self._karaoke_switch_r:
                    self._handler.removeCallbacks(self._karaoke_switch_r)
                self._hide_bubble()
                self._last_rendered_frame_key = None
                self._schedule(0)
            run_on_ui_thread(_stop_music_state)
        elif key == "karaoke" and not value:
            def _stop_karaoke_state():
                self._is_singing = False
                self._test_karaoke_active = False
                if self._handler and self._karaoke_switch_r:
                    self._handler.removeCallbacks(self._karaoke_switch_r)
                if self._bubble_mode == "karaoke":
                    self._hide_bubble()
                self._last_rendered_frame_key = None
                self._schedule(0)
            run_on_ui_thread(_stop_karaoke_state)
        elif key == "animated_gradient_border":
            run_on_ui_thread(self._apply_karaoke_bubble_style)
        elif key == "bubble_scale":
            run_on_ui_thread(self._refresh_bubble_scale)
        elif key == "sync_debug_hud":
            run_on_ui_thread(lambda: (setattr(self, "_last_hud_upd", 0.0), self._update_sync_debug_hud(time.monotonic()), self._relayout_bubble()))
        elif key == "eat" and not value:
            run_on_ui_thread(self._give_back)
        elif key == "poop" and not value:
            run_on_ui_thread(self._remove_poops)
        elif key == "shake":
            run_on_ui_thread(self._start_sensor if value else self._stop_sensor)

# === [SHARED_BLOCK:BUBBLE_SCALE_UI] ===
    def _bubble_scale(self) -> float:
        try:
            return clamp(float(self._cfg.get("bubble_scale", 1.0) or 1.0), 0.4, 2.0)
        except Exception:
            return 1.0

    def _refresh_bubble_scale(self):
        s = self._bubble_scale()
        if self._bubble is None:
            return
        try:
            if self._artwork_view is not None:
                art_sz = max(12, AndroidUtilities.dp(32.0 * s))
                self._artwork_view.setLayoutParams(LinearLayout.LayoutParams(art_sz, art_sz))
                if self._artwork_bg_gd is not None:
                    self._artwork_bg_gd.setCornerRadius(float(AndroidUtilities.dp(7.0 * s)))
            if self._artwork_row is not None:
                self._artwork_row.setPadding(0, 0, 0, max(2, AndroidUtilities.dp(5.0 * s)))
            if self._artwork_title_tv is not None:
                self._artwork_title_tv.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 10.5 * s)
                self._artwork_title_tv.setPadding(max(3, AndroidUtilities.dp(8.0 * s)), 0, 0, 0)
            if self._media_controls_layout is not None:
                self._media_controls_layout.setPadding(0, max(2, AndroidUtilities.dp(4.0 * s)), 0, 0)
            for btn in self._media_ctrl_btns:
                if btn is not None:
                    btn.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 14.0 * s)
                    hpad = max(3, AndroidUtilities.dp(8.0 * s))
                    btn.setPadding(hpad, 0, hpad, 0)
            if self._sync_debug_tv is not None:
                self._sync_debug_tv.setTextSize(TypedValue.COMPLEX_UNIT_DIP, max(7.0, 9.0 * s))
                self._sync_debug_tv.setPadding(
                    max(3, AndroidUtilities.dp(6.0 * s)), max(1, AndroidUtilities.dp(2.0 * s)),
                    max(3, AndroidUtilities.dp(6.0 * s)), max(1, AndroidUtilities.dp(2.0 * s)),
                )
            prev_mode = self._bubble_mode
            self._bubble_mode = prev_mode
            self._karaoke_layer_drawable = None
            if prev_mode == "karaoke":
                self._apply_karaoke_geometry(s)
                self._apply_karaoke_bubble_style()
            elif prev_mode == "speech" and hasattr(self, "_apply_speech_geometry"):
                self._apply_speech_geometry(s)
            else:
                self._relayout_bubble()
            if hasattr(self, "_on_bubble_resized"):
                self._on_bubble_resized()
        except Exception as e:
            CLOG.log_error("BUBBLE_SCALE", "Scale refresh error", e)

    def _open_bubble_scale_dialog(self):
        try:
            ctx = self._get_safe_activity()
            if not ctx:
                return
            orig_scale = self._bubble_scale()
            cur_val = [orig_scale]

            root = LinearLayout(ctx)
            root.setOrientation(LinearLayout.VERTICAL)
            p20 = AndroidUtilities.dp(20)
            p12 = AndroidUtilities.dp(12)
            root.setPadding(p20, p12, p20, p12)

            label_tv = TextView(ctx)
            label_tv.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 15.0)
            label_tv.setGravity(Gravity.CENTER_HORIZONTAL)
            label_tv.setPadding(0, 0, 0, p12)
            label_tv.setText(f"Масштаб: {cur_val[0]:.2f}x (от 0.40x до 2.00x)")
            root.addView(label_tv, LinearLayout.LayoutParams(-1, -2))

            seek = SeekBar(ctx)
            seek.setMax(32)  # 32 шага по 0.05x: 0.40x .. 2.00x
            seek.setProgress(clamp(int(round((orig_scale - 0.4) / 0.05)), 0, 32))

            def _apply_preview(val: float):
                val = round(clamp(val, 0.4, 2.0), 2)
                cur_val[0] = val
                label_tv.setText(f"Масштаб: {val:.2f}x (от 0.40x до 2.00x)")
                self._cfg["bubble_scale"] = val
                self._refresh_bubble_scale()

            seek.setOnSeekBarChangeListener(
                BubbleScaleSeekListener(lambda prog: _apply_preview(0.4 + prog * 0.05))
            )
            root.addView(seek, LinearLayout.LayoutParams(-1, -2))

            presets_row = LinearLayout(ctx)
            presets_row.setOrientation(LinearLayout.HORIZONTAL)
            presets_row.setGravity(Gravity.CENTER)
            presets_row.setPadding(0, p12, 0, 0)
            for p_val in (0.4, 0.7, 1.0, 1.4, 2.0):
                btn = TextView(ctx)
                btn.setText(f"{p_val:.1f}x")
                btn.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 13.0)
                btn.setPadding(AndroidUtilities.dp(10), AndroidUtilities.dp(6), AndroidUtilities.dp(10), AndroidUtilities.dp(6))
                btn.setOnClickListener(
                    ViewClickListener(lambda _v, pv=p_val: (
                        seek.setProgress(clamp(int(round((pv - 0.4) / 0.05)), 0, 32)),
                        _apply_preview(pv),
                    ))
                )
                presets_row.addView(btn, LinearLayout.LayoutParams(-2, -2))
            root.addView(presets_row, LinearLayout.LayoutParams(-1, -2))

            def _save(_d, _w):
                self.set_setting("bubble_scale", float(cur_val[0]))
                self._cfg["bubble_scale"] = float(cur_val[0])
                self._refresh_bubble_scale()
                self._say(f"Рамка: {cur_val[0]:.2f}x", force=True)

            def _reset(_d, _w):
                self.set_setting("bubble_scale", 1.0)
                self._cfg["bubble_scale"] = 1.0
                self._refresh_bubble_scale()

            def _cancel(_d, _w):
                self._cfg["bubble_scale"] = orig_scale
                self._refresh_bubble_scale()

            b = AlertDialog.Builder(ctx)
            b.setTitle("Размер рамки текста")
            b.setView(root)
            b.setPositiveButton("Сохранить", TGDialogClickListener(_save))
            b.setNeutralButton("1.0x", TGDialogClickListener(_reset))
            b.setNegativeButton("Отмена", TGDialogClickListener(_cancel))
            b.show()
        except Exception as e:
            CLOG.log_error("BUBBLE_SCALE", "Scale dialog error", e)
# === [/SHARED_BLOCK:BUBBLE_SCALE_UI] ===

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
                CLOG.log_info("SENSOR", "Акселерометр успешно подключен")
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
        # При смене экрана/фрагмента — принудительный возврат съеденного
        self._give_back()
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

        s = self._bubble_scale()
        bubble_layout = LinearLayout(context)
        bubble_layout.setOrientation(LinearLayout.VERTICAL)
        bubble_layout.setGravity(Gravity.CENTER_HORIZONTAL)
        bubble_layout.setMinimumWidth(0)
        bubble_layout.setPadding(
            max(4, AndroidUtilities.dp(12.0 * s)), max(2, AndroidUtilities.dp(7.0 * s)),
            max(4, AndroidUtilities.dp(12.0 * s)), max(2, AndroidUtilities.dp(7.0 * s)),
        )
        bubble_layout.setVisibility(View.GONE)

        artwork_row = LinearLayout(context)
        artwork_row.setOrientation(LinearLayout.HORIZONTAL)
        artwork_row.setGravity(Gravity.CENTER_VERTICAL)
        artwork_row.setPadding(0, 0, 0, max(2, AndroidUtilities.dp(5.0 * s)))
        artwork_row.setVisibility(View.GONE)

        artwork_view = ImageView(context)
        artwork_view.setScaleType(ImageView.ScaleType.CENTER_CROP)
        art_gd = GradientDrawable()
        art_gd.setCornerRadius(float(AndroidUtilities.dp(7.0 * s)))
        art_gd.setColor(as_java_color(0x22FFFFFF))
        artwork_view.setBackground(art_gd)
        try:
            artwork_view.setClipToOutline(True)
        except Exception:
            pass
        art_sz = max(12, AndroidUtilities.dp(32.0 * s))
        artwork_row.addView(artwork_view, LinearLayout.LayoutParams(art_sz, art_sz))

        artwork_title_tv = TextView(context)
        artwork_title_tv.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 10.5 * s)
        artwork_title_tv.setTextColor(as_java_color(0xCCFFFFFF))
        artwork_title_tv.setMaxLines(1)
        artwork_title_tv.setSingleLine(True)
        if TextUtils is not None:
            artwork_title_tv.setEllipsize(TextUtils.TruncateAt.END)
        artwork_title_tv.setPadding(max(3, AndroidUtilities.dp(8.0 * s)), 0, 0, 0)
        artwork_row.addView(artwork_title_tv, LinearLayout.LayoutParams(-2, -2))
        bubble_layout.addView(artwork_row, LinearLayout.LayoutParams(-2, -2))

        bubble_text = TextView(context)
        bubble_text.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 13.0 * s)
        bubble_text.setMinimumWidth(0)
        bubble_text.setMaxWidth(AndroidUtilities.dp(260.0 * s))
        bubble_text.setGravity(Gravity.CENTER_HORIZONTAL)
        try:
            bubble_text.setTypeface(AndroidUtilities.bold())
        except Exception:
            pass
        bubble_layout.addView(bubble_text, LinearLayout.LayoutParams(-2, -2))

        bubble_subtext = TextView(context)
        bubble_subtext.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 10.5 * s)
        bubble_subtext.setMinimumWidth(0)
        bubble_subtext.setMaxWidth(AndroidUtilities.dp(260.0 * s))
        bubble_subtext.setGravity(Gravity.CENTER_HORIZONTAL)
        bubble_subtext.setAlpha(0.45)
        bubble_subtext.setVisibility(View.GONE)
        bubble_layout.addView(bubble_subtext, LinearLayout.LayoutParams(-2, -2))

        controls = LinearLayout(context)
        controls.setOrientation(LinearLayout.HORIZONTAL)
        controls.setGravity(Gravity.CENTER)
        controls.setPadding(0, max(2, AndroidUtilities.dp(4.0 * s)), 0, 0)
        controls.setVisibility(View.GONE)

        self._media_ctrl_btns = []

        def _make_btn(symbol: str, cb):
            btn = TextView(context)
            btn.setText(symbol)
            btn.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 14.0 * s)
            hpad = max(3, AndroidUtilities.dp(8.0 * s))
            btn.setPadding(hpad, 0, hpad, 0)
            btn.setOnClickListener(ViewClickListener(lambda _v: cb()))
            self._media_ctrl_btns.append(btn)
            return btn

        # Пульт управления: кнопки [⏮], [⏯], [⏭] и [📋]
        controls.addView(_make_btn("⏮", lambda: self._dispatch_media_key(KeyEvent.KEYCODE_MEDIA_PREVIOUS)))
        controls.addView(_make_btn("⏯", lambda: self._dispatch_media_key(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE)))
        controls.addView(_make_btn("⏭", lambda: self._dispatch_media_key(KeyEvent.KEYCODE_MEDIA_NEXT)))
        controls.addView(_make_btn("📋", lambda: self._open_tap_to_sync_dialog()))
        bubble_layout.addView(controls, LinearLayout.LayoutParams(-2, -2))

        sync_debug_tv = TextView(context)
        sync_debug_tv.setTextSize(TypedValue.COMPLEX_UNIT_DIP, max(7.0, 9.0 * s))
        sync_debug_tv.setTextColor(as_java_color(0xFFB8E6FF))
        sync_debug_tv.setGravity(Gravity.CENTER_HORIZONTAL)
        sync_debug_tv.setPadding(
            max(3, AndroidUtilities.dp(6.0 * s)), max(1, AndroidUtilities.dp(2.0 * s)),
            max(3, AndroidUtilities.dp(6.0 * s)), max(1, AndroidUtilities.dp(2.0 * s)),
        )
        sync_debug_tv.setVisibility(View.GONE)
        bubble_layout.addView(sync_debug_tv, LinearLayout.LayoutParams(-2, -2))

        self._decor.addView(bubble_layout, FrameLayout.LayoutParams(-2, -2))
        self._bubble = bubble_layout
        self._artwork_row = artwork_row
        self._artwork_view = artwork_view
        self._artwork_bg_gd = art_gd
        self._artwork_title_tv = artwork_title_tv
        self._bubble_text = bubble_text
        self._bubble_subtext = bubble_subtext
        self._sync_debug_tv = sync_debug_tv
        self._media_controls_layout = controls
        self._bubble_visible = False
        self._frame_key = None
        self._last_rendered_frame_key = None
        self._pos_ready = False

    def _clear_artwork(self):
        if self._artwork_view is not None:
            try:
                self._artwork_view.setImageBitmap(None)
            except Exception:
                pass
        if self._artwork_row is not None:
            try:
                self._artwork_row.setVisibility(View.GONE)
            except Exception:
                pass
        old_art = self._artwork_bmp
        self._artwork_bmp = None
        self._artwork_track_key = None
        self._artwork_last_has_flag = False
        if old_art is not None:
            try:
                old_art.recycle()
            except Exception:
                pass

    def _detach_views(self):
        self._restore_all()
        self._remove_poops()
        for view in list(self._particles):
            self._remove_view(view)
        self._particles = []
        self._clear_artwork()
        if self._handler is not None and self._grad_anim_r is not None:
            self._handler.removeCallbacks(self._grad_anim_r)
        self._remove_view(self._laser_view)
        self._remove_view(self._bubble)
        self._remove_view(self._pet)
        self._pet = None
        self._bubble = None
        self._artwork_row = None
        self._artwork_view = None
        self._artwork_bg_gd = None
        self._artwork_title_tv = None
        self._bubble_text = None
        self._bubble_subtext = None
        self._sync_debug_tv = None
        self._media_controls_layout = None
        self._media_ctrl_btns = []
        self._laser_view = None
        self._decor = None
        self._touch_listener = None
        self._poop_listener = None
        self._touch = None
        self._platform = None
        self._platforms = []
        self._bubble_mode = None
        self._last_bubble_palette = None
        self._karaoke_border_gd = None
        self._karaoke_bg_gd = None
        self._karaoke_layer_drawable = None
        self._last_rendered_bmp = None
        self._last_rendered_frame_key = None
        for bmp in list(self._frames.values()):
            try:
                if bmp is not None:
                    bmp.recycle()
            except Exception:
                pass
        self._frames = {}
        for bmp in list(self._particle_bitmaps.values()):
            try:
                if bmp is not None:
                    bmp.recycle()
            except Exception:
                pass
        self._particle_bitmaps = {}
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
        self._dp_cache.clear()
        if self._pet is not None:
            try:
                self._pet.setImageBitmap(None)
            except Exception:
                pass
        self._last_rendered_bmp = None
        for bmp in list(self._frames.values()):
            try:
                if bmp is not None:
                    bmp.recycle()
            except Exception:
                pass
        self._frames = {}
        self._particle_bitmaps = {}
        self._frame_key = None
        self._last_rendered_frame_key = None
        self._update_metrics()
        if self._pet is None:
            return
        self._x += (old_w - self._w) / 2.0
        self._y += old_h - self._h
        lp = self._pet.getLayoutParams()
        lp.width = self._w
        lp.height = self._h
        self._pet.setLayoutParams(lp)
        self._hop(self._dp(300))
        self._schedule(16)

    def _palette(self):
        idx = clamp(int(self._cfg.get("color", 0)), 0, len(PALETTES) - 1)
        if idx == 9:
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
        if bmp is not None:
            # LRU-обновление порядка использования
            self._frames[key] = self._frames.pop(key)
            return bmp
        if len(self._frames) >= MAX_FRAME_CACHE:
            evict_key = None
            for cand_key, cand_bmp in self._frames.items():
                if cand_bmp != self._last_rendered_bmp:
                    evict_key = cand_key
                    break
            if evict_key is None:
                evict_key = next(iter(self._frames))
            old_bmp = self._frames.pop(evict_key)
            if old_bmp is not None and old_bmp != getattr(self, "_last_rendered_bmp", None):
                try:
                    old_bmp.recycle()
                except Exception:
                    pass
        bmp = self._render_frame(key)
        self._frames[key] = bmp
        return bmp

    def _render_frame(self, key):
        eyes, look, arms, legs, squash, blush, mouth, hat, fat_stage, color_signature, music_phones = key
        _, body_color, eye_color = self._palette()
        blush_color = mix_color(body_color, 0xFFFF4F79, 0.5)
        # 4.1 Пакетная заливка пикселей спрайта без JNI-перегрузки (18x13 = 234 элемента)
        pixel_array = [0] * (GRID_W * GRID_H)

        def px(x0, y0, x1, y1, color):
            c = as_java_color(color)
            for y in range(max(0, y0), min(GRID_H, y1)):
                row_start = y * GRID_W
                for x in range(max(0, x0), min(GRID_W, x1)):
                    pixel_array[row_start + x] = c

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

        # Шапки (не затираются наушниками, рациональная посадка)
        if "Корона" in hat:
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
            px(right - 3, ey, right - 1, ey + 2, 0xFFFFD700)
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

        # Рациональные цельные наушники (дужка плотно соединена с амбушюрами без разрыва в воздухе;
        # при музыке надеваются только если не мешают головному убору)
        if "Наушники DJ" in hat or (music_phones and ("Без шапки" in hat or "Очки Thug" in hat)):
            band_c = 0xFF262933
            cup_c = 0xFF1E2028
            led_c = 0xFFFF4D5A if "Наушники DJ" in hat else 0xFF4FC3F7
            # Верхняя дужка, прилегающая к голове, и боковые стойки к ушам
            px(left + 1, top - 1, right - 1, top, band_c)
            px(left, top, left + 1, top + 1, band_c)
            px(right - 1, top, right, top + 1, band_c)
            # Амбушюры по бокам
            px(left - 1, top + 1, left, top + 4, cup_c)
            px(right, top + 1, right + 1, top + 4, cup_c)
            px(left - 1, top + 2, left, top + 3, led_c)
            px(right, top + 2, right + 1, top + 3, led_c)

        small_bmp = Bitmap.createBitmap(jarray(jint)(pixel_array), GRID_W, GRID_H, Bitmap.Config.ARGB_8888)
        s = max(2, int(self._unit))
        bmp = Bitmap.createScaledBitmap(small_bmp, GRID_W * s, GRID_H * s, False)
        small_bmp.recycle()
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
        self._anchor_pos_ms = 0.0
        self._anchor_mono = 0.0
        self._anchor_speed = 1.0
        self._sync_offset_ms = 0.0
        self._track_base_pos = 0.0
        self._track_base_time = 0.0
        self._track_is_playing = False
        self._playback_speed = 1.0
        self._accent_color = None
        self._target_palette = DEFAULT_KARAOKE_PALETTE
        self._grad_curr = DEFAULT_KARAOKE_PALETTE
        self._grad_from = DEFAULT_KARAOKE_PALETTE
        self._grad_target = DEFAULT_KARAOKE_PALETTE
        self._last_processed_bridge_rx_mono = 0.0
        self._last_bridge_raw_pos_ms = -1
        self._last_bridge_raw_rx_mono = 0.0
        self._bridge_back_snap_streak = 0
        self._last_sync_source = "NONE"
        self._last_sync_delta_ms = 0.0
        self._last_raw_pos_ms = 0
        self._active_duration_ms = 0
        self._last_hud_upd = 0.0
        self._last_hud_text = ""
        self._artwork_last_has_flag = False
        self._user_offset = 0.0
        self._position_known = True

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
        t0 = time.monotonic()
        if self._last_tick_start > 0.0:
            interval_ms = (t0 - self._last_tick_start) * 1000.0
            if 1.0 <= interval_ms <= 160.0:
                self._frame_intervals.append(interval_ms)
        self._last_tick_start = t0
        try:
            self._step()
        except Exception as e:
            CLOG.log_error("TICK", "Tick loop error", e)
        dt_tick = (time.monotonic() - t0) * 1000.0
        self._tick_times.append(dt_tick)

        if self._running and not self._paused:
            self._schedule(self._next_delay())

    def _next_delay(self):
        if self._pet is None:
            return 1000
        now = time.monotonic()

        # 4.2 Адаптивный цикл анимаций:
        # 16 мс (60 fps) активируется строго при наличии активных динамических состояний:
        is_dynamic = (
            self._state in ("press", "drag", "pet", "fly", "walk")
            or self._hop_active
            or self._bubble_fade_in
            or self._walk_in
            or self._laser_active
            or self._platform_moving
            or abs(self._slide_v) > 0.0
            or self._shake_pending is not None
            or now < self._squash_until
            or (self._expr == "dizzy" and now < self._expr_until)
        )

        if is_dynamic:
            # При режиме энергосбережения 60 fps ограничиваются до 30 fps (33 мс)
            if self._power_save_mode:
                return 33
            return 16

        # Во время воспроизведения музыки: если питомец в idle — танец не реже 33 мс (30 fps)
        if self._media == "music" and self._state == "idle":
            return 33

        if self._state in ("hang", "peek"):
            return 33

        # В режиме сна (sleep): задержка 250 мс
        if self._state == "sleep":
            return 250

        # В состоянии покоя без музыки (idle): частота тика снижается до 8–10 тиков/с (100–125 мс)
        return 110

    def _dp(self, value):
        # 4.2 Мемоизация и кэширование AndroidUtilities.dp()
        v = self._dp_cache.get(value)
        if v is None:
            v = float(AndroidUtilities.dp(value))
            self._dp_cache[value] = v
        return v

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
                new_rot = int(display.getRotation())
                if new_rot != self._rotation:
                    self._rotation = new_rot
                    self._dp_cache.clear()
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
                self._check_telemetry_summary(now)

        if self._pet is None or self._decor is None:
            return
        if self._pos_ready:
            self._poll_media(now)
            self._poll_clipboard(now)
            # 1.3 Отказоустойчивый чекер строк (Fail-Safe Checker раз в 100 мс)
            if (self._media == "music" or self._test_karaoke_active) and self._track_is_playing and self._lyrics_timeline:
                if now - getattr(self, "_last_failsafe_check", 0.0) >= 0.10:
                    self._last_failsafe_check = now
                    t_calc_raw = self._get_current_track_pos(now)
                    t_karaoke = t_calc_raw + self._user_offset
                    expected_idx = -1
                    for idx_item, (t_sec, _) in enumerate(self._lyrics_timeline):
                        if t_sec <= t_karaoke:
                            expected_idx = idx_item
                        else:
                            break
                    if expected_idx >= 0:
                        t_curr = self._lyrics_timeline[expected_idx][0]
                        t_next = (
                            self._lyrics_timeline[expected_idx + 1][0]
                            if expected_idx + 1 < len(self._lyrics_timeline)
                            else t_curr + 5.0
                        )
                        line_dur = t_next - t_curr
                        sing_until = t_curr + min(line_dur - 0.7, 5.0) if line_dur > 5.5 else t_next
                        target_idx = expected_idx if t_karaoke <= sing_until else -2
                        if target_idx != self._current_lyric_idx:
                            self._do_karaoke_line_switch()
                    elif self._current_lyric_idx >= 0:
                        self._do_karaoke_line_switch()
            self._update_sync_debug_hud(now)
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
            if bm:
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
                elif not charging and level < 15 and random.random() < 0.2:
                    self._say("battery_low")

            # Проверка PowerManager.isPowerSaveMode()
            pm = ctx.getSystemService(Context.POWER_SERVICE)
            if pm:
                self._power_save_mode = bool(getattr(pm, "isPowerSaveMode", lambda: False)())
        except Exception:
            pass

    def _check_telemetry_summary(self, now: float):
        if now - self._last_summary_time < 60.0:
            return
        self._last_summary_time = now
        fps = 0.0
        avg_tick = 0.0
        max_tick = 0.0
        if self._tick_times:
            avg_tick = sum(self._tick_times) / len(self._tick_times)
            max_tick = max(self._tick_times)
        if self._frame_intervals:
            avg_interval = sum(self._frame_intervals) / len(self._frame_intervals)
            fps = 1000.0 / max(1.0, avg_interval)

        avg_scan = 0.0
        if self._platform_scan_times:
            avg_scan = sum(self._platform_scan_times) / len(self._platform_scan_times)

        CLOG.log_info(
            "TELEMETRY",
            f"Сводка производительности (60с): FPS={fps:.1f}, тик avg={avg_tick:.1f}мс, max={max_tick:.1f}мс, мост ping={self._bridge_last_ping_latency:.1f}мс, скан платформ={avg_scan:.1f}мс",
            fps=f"{fps:.1f}",
            avg_tick_ms=f"{avg_tick:.1f}",
            max_tick_ms=f"{max_tick:.1f}",
            bridge_latency_ms=f"{self._bridge_last_ping_latency:.1f}",
            scan_platforms_ms=f"{avg_scan:.1f}",
        )

    def _poll_clipboard(self, now):
        if not self._cfg.get("clipboard_sync", False) or now < self._clip_check_time:
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

            # Приватность: текст буфера не логируем! Реагирует ТОЛЬКО на валидные ссылки SoundCloud
            sc_match = re.search(r"https?://(?:on\.)?soundcloud\.com/\S+", clip_text)
            if sc_match:
                sc_url = sc_match.group(0)
                CLOG.log_info("CLIPBOARD", "Обнаружена SoundCloud ссылка в буфере обмена")

                def _on_resolved(res):
                    if res:
                        a, t = res
                        run_on_ui_thread(lambda: self._start_custom_song(f"{a} - {t}"))

                threading.Thread(
                    target=lambda u=sc_url: _on_resolved(self._lyrics_helper.resolve_soundcloud_url(u)),
                    daemon=True,
                ).start()
        except Exception:
            pass

    def _fat_stage(self):
        c = len(self._eaten)
        if c <= 1: return 0
        if c <= 3: return 1
        if c <= 6: return 2
        return 3

    def _step_ground(self, dt, now, gravity, min_x, max_x, min_y, max_y):
        self._min_x, self._max_x, self._min_y, self._max_y = min_x, max_x, min_y, max_y
        self._walk_in = False
        fat = self._fat_stage()
        speed_factor = [1.0, 0.85, 0.65, 0.45][fat]
        # 2. Ускорение бега на +15% при тап-побеге
        if now < getattr(self, "_flee_boost_until", 0.0):
            speed_factor *= 1.15

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
                # 2.5 Инстинкт скалолаза: если сидит на дне экрана, каждые 2-4с ищет платформы выше и прыгает вверх
                if not self._hop_active and now >= getattr(self, "_next_climb_attempt", 0.0):
                    self._next_climb_attempt = now + random.uniform(2.0, 4.0)
                    platforms_above = [p for p in self._platforms if p[4] < self._y - self._dp(35)]
                    if platforms_above:
                        self._hop(self._dp(550))
                elif random.random() < 0.015 and not self._hop_active and self._platforms:
                    self._hop(self._dp(450))
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
            # Отменяем караоке таймер при переходе в сон
            if self._handler and self._karaoke_switch_r:
                self._handler.removeCallbacks(self._karaoke_switch_r)
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

    def _scan_platforms(self, min_y, max_y):
        if not self._cfg.get("gravity", False):
            return []
        now = time.monotonic()
        # 4.3 Время жизни кэша платформ _platforms_cache: 500 мс
        if self._platforms_cache and (now - self._last_platforms_scan_time < 0.50):
            return self._platforms_cache

        # В состоянии покоя (idle) и сна (sleep) повторный обход дерева замораживается
        is_moving = self._state in ("fly", "walk") or abs(self._vy) > 0.05 or self._hop_active
        if not is_moving and self._platforms_cache:
            return self._platforms_cache

        t_scan_start = time.monotonic()
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

        scan_dur = (time.monotonic() - t_scan_start) * 1000.0
        self._platform_scan_times.append(scan_dur)
        self._platforms_cache = result
        self._last_platforms_scan_time = now
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
            if self._is_singing and self._cfg.get("singing_mouth_enabled", False):
                mouth = "open" if int(now * 7) % 2 else "chew"
            elif now < self._mouth_open_until:
                mouth = "open"
            elif now < self._chew_until and int(now * 6) % 2:
                mouth = "chew"

        hat_idx = clamp(int(self._cfg.get("hat", 0)), 0, len(HATS) - 1)
        hat = HATS[hat_idx]

        # Цветовая фаза (для Dirty Flag)
        color_idx = clamp(int(self._cfg.get("color", 0)), 0, len(PALETTES) - 1)
        color_sig = color_idx
        if color_idx == 9:
            color_sig = int((now * 0.4 % 1.0) * 30)  # 30 фаз радуги
        elif color_idx == 10:
            color_sig = Theme.getColor(Theme.key_actionBarDefault)

        music_phones = bool(self._cfg.get("dance", True) and self._media == "music" and self._track_is_playing and not self._paused and state != "sleep")
        return (eyes, look, arms, legs, squash, blush, mouth, hat, fat, color_sig, music_phones)

    def _render(self, now):
        key = self._compose(now)

        # 4.3 Dirty Flag (Флаг неизменности кадра)
        # setImageBitmap() и setTranslation*() блокируются, если с прошлого тика не изменились координаты и кадр!
        cur_x = float(self._x)
        cur_y = float(self._y + self._hop_off)

        rotation = 0.0
        if self._state == "fly":
            rotation = clamp(self._vx / self._dp(70), -25.0, 25.0)
        elif self._state == "hang":
            rotation = math.sin((now - self._hang_start) * 3.0) * 6.0
        elif self._is_singing:
            rotation = math.sin(now * 8.0) * 7.0
        elif self._media and self._state == "idle" and not self._hop_active:
            rotation = math.sin(now * math.pi * 2.0) * 6.0

        if key != self._last_rendered_frame_key:
            self._last_rendered_frame_key = key
            bmp = self._get_frame(key)
            self._last_rendered_bmp = bmp
            self._pet.setImageBitmap(bmp)

        if self._last_rendered_x != cur_x:
            self._last_rendered_x = cur_x
            self._pet.setTranslationX(cur_x)

        if self._last_rendered_y != cur_y:
            self._last_rendered_y = cur_y
            self._pet.setTranslationY(cur_y)

        if self._last_rendered_rot != rotation:
            self._last_rendered_rot = rotation
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

    def _on_touch(self, event):
        action = event.getActionMasked()
        rx, ry = float(event.getRawX()), float(event.getRawY())
        now = time.monotonic()
        pointer_count = event.getPointerCount()

        if pointer_count >= 2 and action != MotionEvent.ACTION_POINTER_UP:
            self._laser_active = True
            try:
                cur_px = self._last_rendered_x if self._last_rendered_x is not None else self._x
                cur_py = self._last_rendered_y if self._last_rendered_y is not None else (self._y + self._hop_off)
                lx = float(cur_px) + float(event.getX(1))
                ly = float(cur_py) + float(event.getY(1))
                if self._decor is not None and self._decor.getWidth() > 0:
                    lx = clamp(lx, 0.0, float(self._decor.getWidth()))
                    ly = clamp(ly, 0.0, float(self._decor.getHeight()))
            except Exception:
                lx, ly = rx, ry
            self._run_towards(lx, ly)
            self._update_laser_view(lx, ly, True)
            if random.random() < 0.15:
                self._say("laser_chase")
            return True
        else:
            if self._laser_active:
                self._laser_active = False
                self._update_laser_view(0, 0, False)

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
            self._update_laser_view(0, 0, False)
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

    def _update_laser_view(self, x: float, y: float, visible: bool):
        try:
            if not visible:
                if self._laser_view is not None:
                    self._laser_view.setVisibility(View.GONE)
                return

            size = max(4, int(self._dp(10)))
            if self._laser_view is None and self._decor is not None:
                ctx = self._decor.getContext()
                lv = View(ctx)
                gd = GradientDrawable()
                gd.setShape(GradientDrawable.OVAL)
                gd.setColor(as_java_color(0xFFFF0033))
                gd.setStroke(max(1, int(self._dp(2))), as_java_color(0x66FF0033))
                lv.setBackground(gd)
                lp = FrameLayout.LayoutParams(size, size)
                self._decor.addView(lv, lp)
                self._laser_view = lv

            if self._laser_view is not None:
                self._laser_view.setVisibility(View.VISIBLE)
                self._laser_view.setTranslationX(float(x - size / 2.0))
                self._laser_view.setTranslationY(float(y - size / 2.0))
        except Exception as e:
            CLOG.log_error("LASER", "Laser view error", e)

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
        # Тап по питомцу возвращает всё съеденное на свои места!
        if self._eaten:
            self._spit_all(now)
            return
        if now - self._last_tap < 0.32:
            self._last_tap = 0.0
            self._hop(self._dp(720))
            self._set_expr("happy", 1.3)
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
        # 2. Механика: Тап-побег (+15% скорости, прыжок наверх и реплика tap_flee)
        self._squash_until = now + 0.12
        self._set_expr("happy", 1.8)
        self._haptic(3)
        self._flee_boost_until = now + random.uniform(3.0, 4.0)

        decor_w = float(self._decor.getWidth()) if self._decor is not None and self._decor.getWidth() > 0 else (getattr(self, "_max_x", 400.0) * 1.5)
        mid_x = decor_w / 2.0
        dist = self._dp(140)

        min_x = getattr(self, "_min_x", 0.0)
        max_x = getattr(self, "_max_x", self._x + dist)

        if self._x + self._w / 2.0 >= mid_x:
            self._walk_target = max(min_x, self._x - dist)
            self._look = -1
        else:
            self._walk_target = min(max_x, self._x + dist)
            self._look = 1
        self._state = "walk"

        # Если питомец в нижней половине экрана (Y > min_y + 100 dp) — высокий прыжок вверх на 560 dp
        min_y = getattr(self, "_min_y", 0.0)
        if self._y > min_y + self._dp(100):
            self._hop(self._dp(560))
        else:
            self._hop(self._dp(340))

        self._say("tap_flee")

    def _start_pet(self, now):
        self._state = "pet"
        self._next_heart = now + 0.1
        self._haptic(0)

    def _stroke(self):
        self._spawn_particle("heart")
        self._haptic(4)

    def _end_pet(self, now):
        self._state = "idle"
        self._set_expr("happy", 2.2)
        try:
            count = int(self.get_setting("pets_count", 0) or 0) + 1
            self.set_setting("pets_count", count)
        except Exception:
            pass
        self._say("pet")

    def _on_notification(self, id, account, args):
        now = time.monotonic()
        ev_read = getattr(NotificationCenter, "messagesRead", -999)
        ev_del = getattr(NotificationCenter, "messagesDeleted", -999)

        if not self._cfg.get("tg_events", True):
            return
        scope = clamp(int(self._cfg.get("tg_chat_scope", 0) or 0), 0, 1)

        if id == ev_read:
            if scope == 0 and self._chat_dialog <= 0:
                return
            if self._state in ("idle", "walk"):
                self._hop(self._dp(380))
                self._spawn_particle("spark")
                self._say("read")
            return

        if id == ev_del:
            del_chan = 0
            try:
                if args is not None and len(args) > 1:
                    del_chan = int(args[1] or 0)
            except Exception:
                del_chan = 0
            if scope == 0 and (del_chan > 0 or self._chat_dialog <= 0):
                return
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

        # 6.1 Чат «Избранное» (dialog_id == my_uid): входящие события полностью игнорируются!
        if dialog_id == my_uid:
            return

        # По умолчанию (scope == 0) реагируем ТОЛЬКО на личные сообщения (dialog_id > 0); группы/каналы (dialog_id <= 0) игнорируются
        if scope == 0 and dialog_id <= 0:
            return

        sender_name = None
        for i in range(min(int(messages.size()), MAX_SCAN_MESSAGES)):
            message = messages.get(i)
            if message is None or message.isOut():
                continue

            from_uid = 0
            if message.messageOwner and message.messageOwner.from_id:
                from_uid = getattr(message.messageOwner.from_id, "user_id", 0)
            if from_uid == my_uid:
                continue

            incoming = True
            if sender_name is None and from_uid > 0:
                try:
                    user_obj = MessagesController.getInstance(account).getUser(from_uid)
                    if user_obj is not None:
                        sender_name = str(UserObject.getFirstName(user_obj) or "").strip() or None
                except Exception:
                    pass
            text = message.messageOwner.message if message.messageOwner is not None else None
            if text:
                t_str = str(text)
                texts.append(t_str[:MAX_KEYWORD_TEXT].lower())
                # Автозапуск SoundCloud из входящих сообщений (если включен)
                if self._cfg.get("sc_autostart_incoming", False) and "soundcloud.com/" in t_str:
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
        elif mood == "thanks":
            self._set_expr("happy", 2.0)
            self._hop(self._dp(380))
            self._say("thanks")
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

    def _on_sent(self, length, account):
        if not self._cfg.get("tg_events", True):
            return
        now = time.monotonic()
        if now < self._next_sent_react:
            return
        self._next_sent_react = now + 1.5

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

# === [SHARED_BLOCK:PLAYER_ENGINE] ===
    def _record_sync_trace(self, tag: str, msg: str):
        ts = time.strftime("%H:%M:%S")
        entry = f"{ts} | {tag:<5} | {msg}"
        self._sync_trace_log.append(entry)
        CLOG.log_debug("SYNC_TRACE", f"[{tag}] {msg}")

    def _update_sync_debug_hud(self, now: float):
        tv = self._sync_debug_tv
        if tv is None:
            return
        show_hud = bool(self._cfg.get("sync_debug_hud", False)) and (self._media == "music" or self._test_karaoke_active) and (self._bubble_mode == "karaoke")
        if not show_hud:
            if tv.getVisibility() != View.GONE:
                tv.setVisibility(View.GONE)
            return
        if now - self._last_hud_upd < 0.18:
            return
        self._last_hud_upd = now
        calc_ms = self._get_current_track_pos_ms(now)
        raw_s = float(self._last_raw_pos_ms) / 1000.0
        calc_s = calc_ms / 1000.0
        meta = self._lyrics_helper.get_lyrics_meta(self._last_active_clean_a, self._last_active_clean_t) if self._last_active_clean_t else {}
        lrc_src = meta.get("source", "NONE")
        lrc_dur = float(meta.get("duration_sec") or 0.0)
        trk_dur = float(self._active_duration_ms) / 1000.0
        tot = len(self._lyrics_timeline)
        hud_txt = (
            f"SRC:{self._last_sync_source} | raw:{raw_s:.2f}s calc:{calc_s:.2f}s Δ:{self._last_sync_delta_ms:+.0f}ms\n"
            f"off:{self._user_offset:+.2f}s | idx:{self._current_lyric_idx}/{tot} | LRC:{lrc_src}({lrc_dur:.0f}s/{trk_dur:.0f}s)"
        )
        if tv.getVisibility() != View.VISIBLE:
            tv.setVisibility(View.VISIBLE)
        if hud_txt != self._last_hud_text:
            self._last_hud_text = hud_txt
            tv.setText(hud_txt)

    def _clear_playback_anchors(self, reset_user_offset: bool = False):
        self._anchor_pos_ms = 0.0
        self._anchor_mono = 0.0
        self._anchor_speed = 1.0
        self._track_base_pos = 0.0
        self._track_base_time = 0.0
        self._track_is_playing = False
        self._playback_speed = 1.0
        self._last_sse_rx_mono = 0.0
        self._last_processed_bridge_rx_mono = 0.0
        self._last_bridge_raw_pos_ms = -1
        self._last_bridge_raw_rx_mono = 0.0
        self._last_tg_raw_pos_ms = -1
        self._bridge_back_snap_streak = 0
        self._last_sync_source = "NONE"
        self._last_sync_delta_ms = 0.0
        self._last_raw_pos_ms = 0
        self._active_duration_ms = 0
        self._current_lyric_idx = -1
        self._is_singing = False
        if reset_user_offset:
            self._sync_offset_ms = 0.0
            self._user_offset = 0.0
            self._session_offsets.clear()

    def _get_current_track_pos_ms(self, now: Optional[float] = None) -> float:
        if now is None:
            now = time.monotonic()
        if not self._track_is_playing or self._anchor_mono <= 0.0:
            return self._anchor_pos_ms
        pos = self._anchor_pos_ms + max(0.0, now - self._anchor_mono) * 1000.0 * self._anchor_speed
        if self._active_duration_ms > 1000:
            pos = min(pos, float(self._active_duration_ms) + 1500.0)
        return pos

    def _get_current_track_pos(self, now: float) -> float:
        return self._get_current_track_pos_ms(now) / 1000.0

    def _bridge_matches(self, snap, tg_a: str, tg_t: str) -> bool:
        if not snap or not snap.get("has_media"):
            return False
        ba, bt = self._lyrics_helper.clean_metadata(str(snap.get("artist") or ""), str(snap.get("title") or ""))
        ca, ct = self._lyrics_helper.clean_metadata(tg_a, tg_t)
        bt_l, ct_l = bt.lower(), ct.lower()
        ba_l, ca_l = ba.lower(), ca.lower()
        if ct_l and bt_l:
            if ct_l == bt_l or ct_l in bt_l or bt_l in ct_l:
                return True
            return False
        bp = str(snap.get("player") or "").lower()
        return ("telegram" in bp or "aprel" in bp or "gram" in bp) and (not ca_l or not ba_l or ca_l == ba_l)

    def _apply_fresh_bridge_anchor_and_jump(self, expected_track_id: str):
        """После загрузки LRC берёт живой якорь из SSE или свежего GET /now-playing (без старого пре-LRC якоря)."""
        parts = expected_track_id.split("::")
        exp_player = parts[0] if len(parts) >= 1 else ""
        exp_a = parts[1] if len(parts) >= 3 else ""
        exp_t = parts[2] if len(parts) >= 3 else (parts[1] if len(parts) == 2 else "")

        def _snap_valid(s) -> bool:
            if not s or not s.get("has_media") or not s.get("is_playing") or not bool(s.get("position_known", True)):
                return False
            if exp_player == "Telegram":
                return self._bridge_matches(s, exp_a, exp_t)
            return True

        with self._bridge_lock:
            snap = self._bridge_data
        now = time.monotonic()
        if _snap_valid(snap):
            rx_mono = float(snap.get("_received_mono") or 0.0)
            if rx_mono > 0.0 and (self._bridge_sse_connected or (now - rx_mono <= 0.45)):
                pos_ms = float(snap.get("position_ms") or 0.0)
                try:
                    spd = clamp(float(snap.get("playback_speed") or 1.0), 0.25, 4.0)
                except Exception:
                    spd = 1.0
                self._anchor_pos_ms = pos_ms
                self._anchor_mono = rx_mono
                self._anchor_speed = spd
                self._playback_speed = spd
                self._track_base_pos = pos_ms / 1000.0
                self._track_base_time = rx_mono
                self._last_processed_bridge_rx_mono = max(self._last_processed_bridge_rx_mono, rx_mono)
                self._last_bridge_raw_pos_ms = int(pos_ms)
                self._last_bridge_raw_rx_mono = rx_mono
                self._last_raw_pos_ms = int(pos_ms)
                self._bridge_back_snap_streak = 0
                self._record_sync_trace("REANC", f"post-LRC anchor pos={pos_ms:.0f}ms spd={spd:.2f}x")
                self._current_lyric_idx = -1
                self._do_karaoke_line_switch()
                return

        self._current_lyric_idx = -1
        self._do_karaoke_line_switch()

        if not self._bridge_sse_connected:
            def _fetch_now():
                ok, data, dt_ping = self._bridge_poll_once()
                if not ok or not isinstance(data, dict) or not _snap_valid(data):
                    return
                self._on_bridge_payload(data, "Polling", dt_ping)
                rx_fresh = time.monotonic()
                pos_fresh = float(data.get("position_ms") or 0.0)
                try:
                    spd_fresh = clamp(float(data.get("playback_speed") or 1.0), 0.25, 4.0)
                except Exception:
                    spd_fresh = 1.0

                def _apply_live():
                    if self._unloaded or self._current_track_id != expected_track_id:
                        return
                    self._anchor_pos_ms = pos_fresh
                    self._anchor_mono = rx_fresh
                    self._anchor_speed = spd_fresh
                    self._playback_speed = spd_fresh
                    self._track_base_pos = pos_fresh / 1000.0
                    self._track_base_time = rx_fresh
                    self._last_processed_bridge_rx_mono = max(self._last_processed_bridge_rx_mono, rx_fresh)
                    self._last_bridge_raw_pos_ms = int(pos_fresh)
                    self._last_bridge_raw_rx_mono = rx_fresh
                    self._last_raw_pos_ms = int(pos_fresh)
                    self._bridge_back_snap_streak = 0
                    self._current_lyric_idx = -1
                    self._do_karaoke_line_switch()

                run_on_ui_thread(_apply_live)

            threading.Thread(target=_fetch_now, daemon=True, name="clawd_lrc_sync_snap").start()

    def _fetch_artwork_async(self, expected_track_id: str, track_label: str):
        def _worker():
            bmp = None
            try:
                req = urllib.request.Request(
                    "http://127.0.0.1:44444/artwork",
                    headers={
                        "User-Agent": f"ClawdPet/{__version__} (Android)",
                        "Host": "127.0.0.1:44444",
                    },
                )
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    if getattr(resp, "status", 200) == 200:
                        raw = resp.read()
                        if raw:
                            jbytes = jarray(jbyte)(raw)
                            bmp = BitmapFactory.decodeByteArray(jbytes, 0, len(raw))
            except Exception:
                bmp = None

            def _apply():
                if self._unloaded or self._current_track_id != expected_track_id or self._artwork_view is None:
                    if bmp is not None:
                        try:
                            bmp.recycle()
                        except Exception:
                            pass
                    return
                old_bmp = self._artwork_bmp
                self._artwork_bmp = bmp
                if self._artwork_view is not None:
                    self._artwork_view.setImageBitmap(bmp)
                if self._artwork_title_tv is not None:
                    self._artwork_title_tv.setText(track_label)
                if self._artwork_row is not None:
                    if bmp is not None and self._bubble_mode == "karaoke":
                        self._artwork_row.setVisibility(View.VISIBLE)
                    else:
                        self._artwork_row.setVisibility(View.GONE)
                if old_bmp is not None and old_bmp != bmp:
                    try:
                        old_bmp.recycle()
                    except Exception:
                        pass

            run_on_ui_thread(_apply)

        threading.Thread(target=_worker, daemon=True, name="clawd_artwork").start()

    def _poll_media(self, now):
        if now < self._media_check:
            return
        self._media_check = now + 0.35

        kind = None
        track_title, track_artist, player_name = None, None, "telegram"
        track_position_ms = 0
        duration_ms = 0
        is_playing = False
        position_known = True
        playback_speed = 1.0
        bridge_rx_mono = 0.0
        accent_color: Optional[int] = None
        palette_3: Tuple[int, int, int] = DEFAULT_KARAOKE_PALETTE
        has_artwork = False
        sync_source = "NONE"

        # Проверка окончания тестового режима караоке и приоритета реального воспроизведения
        tg_playing_now = False
        tg_paused_music = None
        bridge_snapshot = None
        if self._cfg.get("dance", True):
            try:
                controller = MediaController.getInstance()
                playing = controller.getPlayingMessageObject()
                if playing is not None and playing.isMusic():
                    if controller.isPlayingMessage(playing) and not controller.isMessagePaused():
                        tg_playing_now = True
                        kind = "music"
                        is_playing = True
                        player_name = "Telegram"
                        track_title = str(playing.getMusicTitle() or "").strip()
                        track_artist = str(playing.getMusicAuthor() or "").strip()
                        dur_sec = float(getattr(playing, "getDuration", lambda: 0)())
                        duration_ms = int(dur_sec * 1000)
                        prog = float(getattr(playing, "audioProgress", 0.0))
                        track_position_ms = int(dur_sec * prog * 1000)
                        position_known = True
                        sync_source = "TG"
                    else:
                        tg_paused_music = playing
            except Exception as e:
                CLOG.log_error("TG_AUDIO", "Poll error", e)

            with self._bridge_lock:
                bridge_snapshot = self._bridge_data
            if bridge_snapshot and not self._bridge_sse_connected and not bridge_snapshot.get("is_fallback"):
                b_rx_chk = float(bridge_snapshot.get("_received_mono") or 0.0)
                if b_rx_chk <= 0.0 or (now - b_rx_chk) > 4.0:
                    bridge_snapshot = None

        if self._test_karaoke_active:
            test_done = False
            if not self._cfg.get("dance", True) or not self._cfg.get("karaoke", True) or tg_playing_now or (bridge_snapshot and bridge_snapshot.get("has_media") and bridge_snapshot.get("is_playing")):
                test_done = True
            elif self._lyrics_timeline and self._get_current_track_pos(now) > self._lyrics_timeline[-1][0] + 6.0:
                test_done = True
            elif not self._lyrics_timeline and self._anchor_mono > 0.0 and (now - self._anchor_mono > 10.0):
                test_done = True
            if not test_done:
                self._track_is_playing = True
                self._last_sync_source = "DEMO"
                return
            self._test_karaoke_active = False

        # 2.1 Приоритеты источников звука + обогащение треков Telegram данными из Bridge (обложка, акценты, SSE-тайминг):
        # Telegram Playing (+ Bridge sync/art/accent) -> Clawd Bridge Playing -> Telegram Paused -> Clawd Bridge Paused
        tg_playing = tg_playing_now
        used_bridge = False
        used_bridge_art = False
        if self._cfg.get("dance", True):
            if tg_playing:
                if self._bridge_matches(bridge_snapshot, track_artist or "", track_title or ""):
                    used_bridge_art = True
                    accent_color = parse_hex_color(bridge_snapshot.get("accent_color"))
                    palette_3 = derive_palette_3(bridge_snapshot.get("accent_color"), bridge_snapshot.get("accent_colors"))
                    has_artwork = bool(bridge_snapshot.get("has_artwork", False))
                    try:
                        playback_speed = clamp(float(bridge_snapshot.get("playback_speed") or 1.0), 0.25, 4.0)
                    except Exception:
                        playback_speed = 1.0
                    b_rx = float(bridge_snapshot.get("_received_mono") or 0.0)
                    b_pos_known = bool(bridge_snapshot.get("position_known", True))
                    if bridge_snapshot.get("is_playing") and b_rx > 0.0 and b_pos_known:
                        used_bridge = True
                        track_position_ms = int(bridge_snapshot.get("position_ms") or 0)
                        if int(bridge_snapshot.get("duration_ms") or 0) > 0:
                            duration_ms = int(bridge_snapshot.get("duration_ms") or 0)
                        position_known = True
                        bridge_rx_mono = b_rx
                        sync_source = "TG+SSE" if bridge_snapshot.get("_is_sse_event") else "TG+Poll"
            else:
                if bridge_snapshot and bridge_snapshot.get("has_media") and bridge_snapshot.get("is_playing"):
                    used_bridge = True
                    used_bridge_art = True
                    kind = "music"
                    is_playing = True
                    player_name = str(bridge_snapshot.get("player") or "Bridge")
                    track_artist = str(bridge_snapshot.get("artist") or "")
                    track_title = str(bridge_snapshot.get("title") or "")
                    track_position_ms = int(bridge_snapshot.get("position_ms") or 0)
                    duration_ms = int(bridge_snapshot.get("duration_ms") or 0)
                    position_known = bool(bridge_snapshot.get("position_known", True))
                    try:
                        playback_speed = clamp(float(bridge_snapshot.get("playback_speed") or 1.0), 0.25, 4.0)
                    except Exception:
                        playback_speed = 1.0
                    bridge_rx_mono = float(bridge_snapshot.get("_received_mono") or 0.0)
                    accent_color = parse_hex_color(bridge_snapshot.get("accent_color"))
                    palette_3 = derive_palette_3(bridge_snapshot.get("accent_color"), bridge_snapshot.get("accent_colors"))
                    has_artwork = bool(bridge_snapshot.get("has_artwork", False))
                    sync_source = "Bridge-SSE" if bridge_snapshot.get("_is_sse_event") else ("SyncFile" if bridge_snapshot.get("is_fallback") else "Bridge-Poll")
                elif tg_paused_music is not None:
                    kind = "music"
                    is_playing = False
                    player_name = "Telegram"
                    track_title = str(tg_paused_music.getMusicTitle() or "").strip()
                    track_artist = str(tg_paused_music.getMusicAuthor() or "").strip()
                    dur_sec = float(getattr(tg_paused_music, "getDuration", lambda: 0)())
                    duration_ms = int(dur_sec * 1000)
                    prog = float(getattr(tg_paused_music, "audioProgress", 0.0))
                    track_position_ms = int(dur_sec * prog * 1000)
                    position_known = True
                    sync_source = "TG(pause)"
                    if self._bridge_matches(bridge_snapshot, track_artist, track_title):
                        used_bridge_art = True
                        accent_color = parse_hex_color(bridge_snapshot.get("accent_color"))
                        palette_3 = derive_palette_3(bridge_snapshot.get("accent_color"), bridge_snapshot.get("accent_colors"))
                        has_artwork = bool(bridge_snapshot.get("has_artwork", False))
                        b_rx = float(bridge_snapshot.get("_received_mono") or 0.0)
                        if b_rx > 0.0 and bool(bridge_snapshot.get("position_known", True)):
                            used_bridge = True
                            track_position_ms = int(bridge_snapshot.get("position_ms") or track_position_ms)
                            bridge_rx_mono = b_rx
                elif bridge_snapshot and bridge_snapshot.get("has_media"):
                    used_bridge = True
                    used_bridge_art = True
                    kind = "music"
                    is_playing = False
                    player_name = str(bridge_snapshot.get("player") or "Bridge")
                    track_artist = str(bridge_snapshot.get("artist") or "")
                    track_title = str(bridge_snapshot.get("title") or "")
                    track_position_ms = int(bridge_snapshot.get("position_ms") or 0)
                    duration_ms = int(bridge_snapshot.get("duration_ms") or 0)
                    position_known = bool(bridge_snapshot.get("position_known", True))
                    try:
                        playback_speed = clamp(float(bridge_snapshot.get("playback_speed") or 1.0), 0.25, 4.0)
                    except Exception:
                        playback_speed = 1.0
                    bridge_rx_mono = float(bridge_snapshot.get("_received_mono") or 0.0)
                    accent_color = parse_hex_color(bridge_snapshot.get("accent_color"))
                    palette_3 = derive_palette_3(bridge_snapshot.get("accent_color"), bridge_snapshot.get("accent_colors"))
                    has_artwork = bool(bridge_snapshot.get("has_artwork", False))
                    sync_source = "Bridge(pause)"

        self._last_sync_source = sync_source
        self._last_raw_pos_ms = track_position_ms
        if duration_ms > 0:
            self._active_duration_ms = duration_ms

        if kind == "music":
            self._accent_color = accent_color
            if self._target_palette != palette_3:
                self._target_palette = palette_3
                if self._bubble_visible and self._bubble_mode == "karaoke":
                    self._apply_karaoke_bubble_style()
        else:
            self._accent_color = None
            self._target_palette = DEFAULT_KARAOKE_PALETTE

        track_changed = False
        if track_title:
            clean_a, clean_t = self._lyrics_helper.clean_metadata(track_artist, track_title)
            self._last_active_clean_a = clean_a
            self._last_active_clean_t = clean_t
            triplet_id = f"{player_name}::{clean_a}::{clean_t}"
            art_key = f"{clean_a}::{clean_t}"
            if triplet_id != self._current_track_id:
                track_changed = True
                self._current_track_id = triplet_id
                self._lyrics_timeline = []
                self._clear_playback_anchors(reset_user_offset=False)
                self._last_sync_source = sync_source
                self._last_raw_pos_ms = track_position_ms
                self._active_duration_ms = duration_ms
                self._lyrics_retry_count = 0
                self._last_lyrics_retry = 0.0
                self._clear_artwork()

                track_offset_key = f"{clean_a} - {clean_t}"
                self._user_offset = self._session_offsets.get(track_offset_key, 0.0)
                self._sync_offset_ms = self._user_offset * 1000.0

                self._record_sync_trace("TRACK", f"'{clean_a} - {clean_t}' src={sync_source} dur={duration_ms/1000:.1f}s pos={track_position_ms}ms")
                CLOG.log_info(
                    "TRACK",
                    f"Смена трека: '{clean_a}' — '{clean_t}' (player={player_name}, dur={duration_ms/1000.0:.1f}с, speed={playback_speed:.2f}x, offset={self._sync_offset_ms:.0f}мс)",
                    player=player_name,
                    artist=clean_a,
                    title=clean_t,
                    offset_ms=f"{self._sync_offset_ms:.0f}",
                )

                # Реклама: без автора и < 30 с
                is_ad = (not clean_a) and (0 < duration_ms < 30000)
                if is_ad:
                    CLOG.log_info("TRACK", "Обнаружена реклама: пропуск поиска слов")
                elif self._cfg.get("karaoke", True):
                    self._say_track_detected(clean_a, clean_t)
                    expected_track_id = triplet_id

                    def _on_lyrics_loaded(tl):
                        def _apply():
                            if self._unloaded or self._current_track_id != expected_track_id:
                                return
                            self._lyrics_timeline = tl
                            meta = self._lyrics_helper.get_lyrics_meta(clean_a, clean_t)
                            self._record_sync_trace(
                                "LRC",
                                f"{meta.get('source', 'NONE')} lines={len(tl)} lrc_dur={meta.get('duration_sec', 0):.0f}s trk_dur={self._active_duration_ms/1000:.0f}s score={meta.get('score', 0):.1f}",
                            )
                            if not tl:
                                self._say("no_lyrics")
                                return
                            self._apply_fresh_bridge_anchor_and_jump(expected_track_id)
                        run_on_ui_thread(_apply)

                    self._lyrics_helper.get_lyrics_async(clean_a, clean_t, _on_lyrics_loaded, duration_ms=duration_ms)

            elif kind == "music" and is_playing and not self._lyrics_timeline and (clean_a or clean_t):
                if self._lyrics_retry_count < 3 and (now - self._last_lyrics_retry >= 6.0):
                    self._lyrics_retry_count += 1
                    self._last_lyrics_retry = now
                    CLOG.log_info(
                        "LYRICS",
                        f"Автоповтор поиска слов ({self._lyrics_retry_count}/3): '{clean_a}' — '{clean_t}'",
                        retry=self._lyrics_retry_count,
                        artist=clean_a,
                        title=clean_t,
                    )
                    expected_track_id = triplet_id

                    def _on_retry_loaded(tl):
                        def _apply_retry():
                            if self._unloaded or self._current_track_id != expected_track_id:
                                return
                            if tl:
                                self._lyrics_timeline = tl
                                self._apply_fresh_bridge_anchor_and_jump(expected_track_id)
                            elif self._lyrics_retry_count >= 3:
                                self._say("no_lyrics")
                        run_on_ui_thread(_apply_retry)

                    self._lyrics_helper.get_lyrics_async(clean_a, clean_t, _on_retry_loaded, duration_ms=duration_ms)

            # Обложка: запрашивается ОДИН раз при смене трека ИЛИ при изменении has_artwork: False -> True (включая треки Telegram через Bridge)
            if used_bridge_art:
                should_fetch_art = has_artwork and (
                    self._artwork_track_key != art_key or not self._artwork_last_has_flag
                )
                self._artwork_last_has_flag = has_artwork
                if should_fetch_art:
                    self._artwork_track_key = art_key
                    label = f"{clean_a} — {clean_t}" if clean_a else clean_t
                    self._fetch_artwork_async(triplet_id, label)

        # Монотонный якорь + 3-уровневая анти-дрейфовая коррекция + защита от замерзших/квантованных пакетов
        self._position_known = position_known
        if kind == "music":
            was_paused = not self._track_is_playing
            resumed = is_playing and was_paused
            speed_changed = abs(playback_speed - self._anchor_speed) > 0.01

            if not is_playing:
                fresh_pause_pkt = used_bridge and bridge_rx_mono > self._last_processed_bridge_rx_mono
                if fresh_pause_pkt:
                    self._last_processed_bridge_rx_mono = bridge_rx_mono
                    self._anchor_pos_ms = float(track_position_ms)
                else:
                    self._anchor_pos_ms = self._get_current_track_pos_ms(now)
                self._anchor_mono = 0.0
                self._anchor_speed = playback_speed
                self._playback_speed = playback_speed
                self._track_base_pos = self._anchor_pos_ms / 1000.0
                self._track_base_time = 0.0
                self._track_is_playing = False
                self._is_singing = False
                self._bridge_back_snap_streak = 0
                if self._handler and self._karaoke_switch_r:
                    self._handler.removeCallbacks(self._karaoke_switch_r)
            else:
                self._track_is_playing = True
                self._playback_speed = playback_speed

                if used_bridge:
                    fresh_pkt = bridge_rx_mono > self._last_processed_bridge_rx_mono
                    if fresh_pkt or track_changed or resumed or self._anchor_mono <= 0.0:
                        if fresh_pkt:
                            self._last_processed_bridge_rx_mono = bridge_rx_mono
                        pkt_mono = bridge_rx_mono if bridge_rx_mono > 0.0 else now

                        if track_changed or resumed or self._anchor_mono <= 0.0 or speed_changed:
                            self._anchor_pos_ms = float(track_position_ms)
                            self._anchor_mono = pkt_mono
                            self._anchor_speed = playback_speed
                            self._track_base_pos = self._anchor_pos_ms / 1000.0
                            self._track_base_time = pkt_mono
                            self._last_bridge_raw_pos_ms = track_position_ms
                            self._last_bridge_raw_rx_mono = pkt_mono
                            self._bridge_back_snap_streak = 0
                            self._last_sync_delta_ms = 0.0
                            self._current_lyric_idx = -1
                            self._do_karaoke_line_switch()
                        else:
                            # Защита №1: если Bridge прислал точь-в-точь тот же position_ms < 3.5с подряд, не откатываем якорь назад!
                            is_frozen_pkt = (
                                self._last_bridge_raw_pos_ms >= 0
                                and track_position_ms == self._last_bridge_raw_pos_ms
                                and 0.0 < (pkt_mono - self._last_bridge_raw_rx_mono) < 3.5
                            )
                            if is_frozen_pkt:
                                self._last_bridge_raw_rx_mono = pkt_mono
                                self._bridge_back_snap_streak = 0
                            else:
                                local_at_rx_ms = self._anchor_pos_ms + max(0.0, pkt_mono - self._anchor_mono) * 1000.0 * self._anchor_speed
                                delta = float(track_position_ms) - local_at_rx_ms
                                self._last_sync_delta_ms = delta

                                # Защита №2: квантованный шаг MediaSession (вперёд по секундам), дающий ложный мелкий откат (-180..-1200мс)
                                is_quant_back = (
                                    -1200.0 < delta <= -180.0
                                    and self._last_bridge_raw_pos_ms >= 0
                                    and track_position_ms >= self._last_bridge_raw_pos_ms - 100
                                )
                                if is_quant_back:
                                    self._bridge_back_snap_streak += 1
                                    if self._bridge_back_snap_streak < 2:
                                        self._record_sync_trace("QHOLD", f"raw={track_position_ms} local={local_at_rx_ms:.0f} Δ={delta:+.0f}ms (фильтр пилы)")
                                        self._anchor_pos_ms += delta * 0.20
                                        self._track_base_pos = self._anchor_pos_ms / 1000.0
                                        self._reschedule_karaoke_switch()
                                    else:
                                        self._bridge_back_snap_streak = 0
                                        self._anchor_pos_ms = float(track_position_ms)
                                        self._anchor_mono = pkt_mono
                                        self._anchor_speed = playback_speed
                                        self._track_base_pos = self._anchor_pos_ms / 1000.0
                                        self._track_base_time = pkt_mono
                                        self._record_sync_trace("BSNAP", f"confirmed back Δ={delta:+.0f}ms -> {track_position_ms}ms")
                                        self._do_karaoke_line_switch()
                                elif abs(delta) >= 180.0:
                                    self._bridge_back_snap_streak = 0
                                    CLOG.log_debug(
                                        "ANTIDRIFT",
                                        f"Мгновенный снап якоря: delta={delta:+.0f}мс",
                                        delta_ms=f"{delta:.0f}",
                                    )
                                    self._record_sync_trace("SNAP", f"raw={track_position_ms} local={local_at_rx_ms:.0f} Δ={delta:+.0f}ms")
                                    self._anchor_pos_ms = float(track_position_ms)
                                    self._anchor_mono = pkt_mono
                                    self._anchor_speed = playback_speed
                                    self._track_base_pos = self._anchor_pos_ms / 1000.0
                                    self._track_base_time = pkt_mono
                                    if abs(delta) >= 1200.0:
                                        self._current_lyric_idx = -1
                                    self._do_karaoke_line_switch()
                                elif abs(delta) > 50.0:
                                    self._bridge_back_snap_streak = 0
                                    CLOG.log_debug(
                                        "ANTIDRIFT",
                                        f"Мягкая коррекция якоря: delta={delta:+.0f}мс (сдвиг {delta*0.5:+.0f}мс)",
                                        delta_ms=f"{delta:.0f}",
                                    )
                                    self._anchor_pos_ms += delta * 0.5
                                    self._track_base_pos = self._anchor_pos_ms / 1000.0
                                    self._reschedule_karaoke_switch()
                                else:
                                    self._bridge_back_snap_streak = 0
                                self._last_bridge_raw_pos_ms = track_position_ms
                                self._last_bridge_raw_rx_mono = pkt_mono
                else:
                    # Telegram MediaController без Bridge: порог перемотки 850 мс + защита от замерзшего audioProgress
                    local_ms = self._get_current_track_pos_ms(now)
                    delta = float(track_position_ms) - local_ms
                    self._last_sync_delta_ms = delta
                    is_frozen_tg = (
                        not track_changed
                        and not resumed
                        and self._anchor_mono > 0.0
                        and not speed_changed
                        and self._last_tg_raw_pos_ms >= 0
                        and track_position_ms == self._last_tg_raw_pos_ms
                        and delta < 0.0
                        and abs(delta) < 2200.0
                    )
                    self._last_tg_raw_pos_ms = track_position_ms
                    if track_changed or resumed or self._anchor_mono <= 0.0 or speed_changed or (not is_frozen_tg and abs(delta) >= 850.0):
                        if abs(delta) >= 850.0 and not track_changed and not resumed:
                            self._record_sync_trace("TGSNP", f"raw={track_position_ms} local={local_ms:.0f} Δ={delta:+.0f}ms")
                        self._anchor_pos_ms = float(track_position_ms)
                        self._anchor_mono = now
                        self._anchor_speed = playback_speed
                        self._track_base_pos = self._anchor_pos_ms / 1000.0
                        self._track_base_time = now
                        if resumed or self._bubble_mode != "karaoke" or abs(delta) >= 1200.0:
                            self._current_lyric_idx = -1
                        self._do_karaoke_line_switch()
        else:
            self._track_is_playing = False
            self._playback_speed = 1.0

        if kind == self._media:
            return
        prev = self._media
        self._media = kind
        if kind is None:
            self._current_track_id = None
            self._lyrics_timeline = []
            self._lyrics_retry_count = 0
            self._clear_playback_anchors(reset_user_offset=False)
            self._accent_color = None
            self._target_palette = DEFAULT_KARAOKE_PALETTE
            self._clear_artwork()
            self._hide_bubble()
            if self._handler and self._karaoke_switch_r:
                self._handler.removeCallbacks(self._karaoke_switch_r)
            if prev == "music" and self._state == "idle":
                self._say("music_end")
            return
        if prev is None and self._state in ("idle", "walk"):
            self._say("music" if kind == "music" else "listen")

    def _say_track_detected(self, artist: str, title: str):
        full = f"{artist} — {title}" if artist else title
        self._say(f"🎵 {full}", force=True)

    # 4.1 Декуплинг переключения строк караоке (Вариант A)
    # Переключение отвязано от _step(), вызывается через Handler.postDelayed
    def _reschedule_karaoke_switch(self):
        if self._handler is None or self._karaoke_switch_r is None:
            return
        self._handler.removeCallbacks(self._karaoke_switch_r)

        if (
            not self._cfg.get("karaoke", True)
            or not self._lyrics_timeline
            or (self._media != "music" and not self._test_karaoke_active)
            or not self._track_is_playing
            or self._state not in ("idle", "walk")
        ):
            return

        now = time.monotonic()
        t_calc_raw = self._get_current_track_pos(now)
        t_karaoke = t_calc_raw + self._user_offset

        # Находим текущую строку (последняя строка с line_time_ms <= current_pos_ms) и следующую
        cur_idx = -1
        next_idx = -1
        for i, (t_sec, _) in enumerate(self._lyrics_timeline):
            if t_sec <= t_karaoke:
                cur_idx = i
            else:
                next_idx = i
                break

        wake_at = t_karaoke + 0.35
        if cur_idx >= 0:
            t_curr = self._lyrics_timeline[cur_idx][0]
            if next_idx >= 0:
                t_next_line = self._lyrics_timeline[next_idx][0]
                line_dur = t_next_line - t_curr
                sing_until = t_curr + min(line_dur - 0.7, 5.0) if line_dur > 5.5 else t_next_line

                if t_karaoke < sing_until:
                    wake_at = sing_until
                else:
                    wake_at = t_next_line
            else:
                sing_until = t_curr + 5.0
                if t_karaoke < sing_until:
                    wake_at = sing_until
                else:
                    wake_at = t_karaoke + 4.0
        elif next_idx >= 0:
            wake_at = self._lyrics_timeline[next_idx][0]
        else:
            wake_at = t_karaoke + 4.0

        speed = max(0.25, self._anchor_speed if self._anchor_mono > 0.0 else self._playback_speed)
        delay_ms = max(20, int(math.ceil(((wake_at - t_karaoke) / speed) * 1000.0)) + 8)
        self._handler.postDelayed(self._karaoke_switch_r, delay_ms)

    def _do_karaoke_line_switch(self):
        if not self._running or self._paused:
            return
        now = time.monotonic()
        if (
            not self._cfg.get("karaoke", True)
            or not self._lyrics_timeline
            or (self._media != "music" and not self._test_karaoke_active)
            or not self._track_is_playing
        ):
            self._is_singing = False
            return

        # Защита от смерти караоке-петли при прыжке, перетаскивании или тапе
        if self._state not in ("idle", "walk"):
            self._is_singing = False
            if self._handler and self._karaoke_switch_r:
                self._handler.postDelayed(self._karaoke_switch_r, 100)
            return

        if not self._position_known:
            self._is_singing = False
            self._say("sync_unavailable")
            self._reschedule_karaoke_switch()
            return

        t_calc_raw = self._get_current_track_pos(now)
        t_karaoke = t_calc_raw + self._user_offset

        cur_idx = -1
        for i, (t_sec, _) in enumerate(self._lyrics_timeline):
            if t_sec <= t_karaoke:
                cur_idx = i
            else:
                break

        if cur_idx >= 0:
            t_curr, cur_line = self._lyrics_timeline[cur_idx]
            has_next = cur_idx + 1 < len(self._lyrics_timeline)
            t_next, next_line = self._lyrics_timeline[cur_idx + 1] if has_next else (t_curr + 5.0, "")

            line_dur = t_next - t_curr
            sing_until = t_curr + min(line_dur - 0.7, 5.0) if line_dur > 5.5 else t_next

            if t_karaoke <= sing_until:
                self._is_singing = True
                if cur_idx != self._current_lyric_idx:
                    self._current_lyric_idx = cur_idx
                    self._record_sync_trace("LINE", f"#{cur_idx}/{len(self._lyrics_timeline)} lrc={t_curr:.2f}s pos={t_karaoke:.2f}s | {cur_line[:24]}")
                    self._show_karaoke_line(cur_line, next_line, now)
            else:
                self._is_singing = False
                if self._track_is_playing and bool(self._lyrics_timeline):
                    if self._current_lyric_idx != -2:
                        self._current_lyric_idx = -2
                        self._show_karaoke_line("♪ ♪ ♪", next_line, now)
                else:
                    if self._current_lyric_idx != -2:
                        self._current_lyric_idx = -2
                        self._hide_bubble()
        else:
            self._is_singing = False
            if self._current_lyric_idx != -1:
                self._current_lyric_idx = -1
                if self._track_is_playing and self._lyrics_timeline:
                    self._show_karaoke_line("♪ ♪ ♪", self._lyrics_timeline[0][1], now)

        self._reschedule_karaoke_switch()

    def _animate_text_change(self, view: TextView, new_text: str, target_alpha: float = 1.0, animate: Optional[bool] = None):
        if view is None:
            return
        vid = id(view)
        seq = self._text_anim_seq.get(vid, 0) + 1
        self._text_anim_seq[vid] = seq

        should_animate = self._bubble_visible if animate is None else bool(animate)
        shift_dp = float(AndroidUtilities.dp(5))
        old_text = ""
        try:
            val = view.getText()
            if val is not None:
                old_text = str(val.toString() if hasattr(val, "toString") else val)
        except Exception:
            old_text = ""

        if old_text == new_text and float(view.getAlpha()) > 0.05:
            try:
                view.animate().withEndAction(None).cancel()
            except Exception:
                pass
            view.animate().alpha(target_alpha).translationY(0.0).setDuration(85).start()
            return

        if not old_text or not should_animate:
            try:
                view.animate().withEndAction(None).cancel()
            except Exception:
                pass
            view.setText(new_text)
            view.setTranslationY(0.0)
            view.setAlpha(target_alpha)
            view.forceLayout()
            view.requestLayout()
            return

        try:
            view.animate().withEndAction(None).cancel()
            gen = self._bubble_gen

            def _on_faded_out():
                try:
                    if seq != self._text_anim_seq.get(vid) or gen != self._bubble_gen or self._bubble_mode != "karaoke" or not self._bubble_visible:
                        return
                    view.setText(new_text)
                    view.setTranslationY(shift_dp)
                    view.forceLayout()
                    view.requestLayout()
                    if self._bubble is not None:
                        self._bubble.forceLayout()
                        self._bubble.requestLayout()
                    view.animate().translationY(0.0).alpha(target_alpha).setDuration(85).start()
                except Exception:
                    pass

            view.animate().translationY(-shift_dp).alpha(0.0).setDuration(65).withEndAction(R(_on_faded_out)).start()
        except Exception:
            view.setText(new_text)
            view.setTranslationY(0.0)
            view.setAlpha(target_alpha)
            view.forceLayout()
            view.requestLayout()

    def _rotate_palette(self, palette: Tuple[int, int, int], now: float) -> Tuple[int, int, int]:
        phase = (now * 0.55) % 3.0
        i0 = int(phase) % 3
        i1 = (i0 + 1) % 3
        i2 = (i0 + 2) % 3
        frac = phase - int(phase)
        return (
            mix_color(palette[i0], palette[i1], frac),
            mix_color(palette[i1], palette[i2], frac),
            mix_color(palette[i2], palette[i0], frac),
        )

    def _apply_palette_to_drawables(self, border_palette: Tuple[int, int, int], bg_palette: Optional[Tuple[int, int, int]] = None):
        if self._bubble is None:
            return
        if bg_palette is None:
            bg_palette = border_palette
        s = self._bubble_scale()
        border_cols = jarray(jint)([as_java_color((c & 0x00FFFFFF) | 0xDD000000) for c in border_palette])
        bg_cols = jarray(jint)([as_java_color((mix_color(0xFF0D0E12, c, 0.19) & 0x00FFFFFF) | 0xEA000000) for c in bg_palette])
        stroke_px = max(2, int(self._dp(1.8) * min(s, 1.5)))
        radius_px = max(4.0, float(self._dp(13) * s))

        if (
            self._karaoke_layer_drawable is not None
            and self._karaoke_border_gd is not None
            and self._karaoke_bg_gd is not None
        ):
            try:
                self._karaoke_border_gd.setColors(border_cols)
                self._karaoke_bg_gd.setColors(bg_cols)
                if self._bubble.getBackground() is not self._karaoke_layer_drawable:
                    self._bubble.setBackground(self._karaoke_layer_drawable)
                self._bubble.invalidate()
                return
            except Exception:
                pass

        border_gd = GradientDrawable(GradientDrawable.Orientation.TL_BR, border_cols)
        border_gd.setCornerRadius(radius_px)
        bg_gd = GradientDrawable(GradientDrawable.Orientation.TL_BR, bg_cols)
        bg_gd.setCornerRadius(max(1.0, radius_px - stroke_px))

        ld = LayerDrawable([border_gd, bg_gd])
        ld.setLayerInset(1, stroke_px, stroke_px, stroke_px, stroke_px)
        self._karaoke_border_gd = border_gd
        self._karaoke_bg_gd = bg_gd
        self._karaoke_layer_drawable = ld
        self._bubble.setBackground(ld)
        pad12 = max(4, int(self._dp(12) * s))
        pad7 = max(2, int(self._dp(7) * s))
        self._bubble.setPadding(pad12, pad7, pad12, pad7)

    def _step_gradient_anim(self):
        if self._unloaded or self._paused or self._bubble is None or self._bubble_mode != "karaoke":
            return
        now = time.monotonic()
        elapsed = now - self._grad_anim_start
        dur = 0.36
        t = clamp(elapsed / dur, 0.0, 1.0)
        eased = 1.0 - (1.0 - t) * (1.0 - t)
        cur = (
            mix_color(self._grad_from[0], self._grad_target[0], eased),
            mix_color(self._grad_from[1], self._grad_target[1], eased),
            mix_color(self._grad_from[2], self._grad_target[2], eased),
        )
        self._grad_curr = cur
        animated = bool(self._cfg.get("animated_gradient_border", True))
        if animated and self._bubble_visible:
            border_pal = self._rotate_palette(cur, now)
            self._apply_palette_to_drawables(border_pal, cur)
            if self._handler is not None and self._grad_anim_r is not None:
                self._handler.postDelayed(self._grad_anim_r, 33)
        else:
            self._apply_palette_to_drawables(cur, cur)
            if t < 1.0 and self._handler is not None and self._grad_anim_r is not None:
                self._handler.postDelayed(self._grad_anim_r, 16)

    def _apply_karaoke_bubble_style(self):
        if self._bubble is None:
            return
        target = self._target_palette or DEFAULT_KARAOKE_PALETTE
        self._last_bubble_palette = target
        animated = bool(self._cfg.get("animated_gradient_border", True))

        if (
            self._bubble_visible
            and self._bubble_mode == "karaoke"
            and self._karaoke_layer_drawable is not None
            and self._handler is not None
            and self._grad_anim_r is not None
            and (self._grad_curr != target or animated)
        ):
            self._handler.removeCallbacks(self._grad_anim_r)
            self._grad_from = self._grad_curr
            self._grad_target = target
            self._grad_anim_start = time.monotonic()
            self._step_gradient_anim()
        else:
            if self._handler is not None and self._grad_anim_r is not None:
                self._handler.removeCallbacks(self._grad_anim_r)
            self._grad_curr = target
            self._grad_from = target
            self._grad_target = target
            border_pal = self._rotate_palette(target, time.monotonic()) if animated else target
            self._apply_palette_to_drawables(border_pal, target)
            if animated and self._bubble_visible and self._bubble_mode == "karaoke" and self._handler is not None and self._grad_anim_r is not None:
                self._grad_anim_start = time.monotonic() - 1.0
                self._handler.postDelayed(self._grad_anim_r, 33)

    def _max_bubble_width_px(self) -> int:
        decor_w = int(self._decor.getWidth()) if self._decor is not None else 0
        if decor_w <= 0:
            try:
                decor_w = int(AndroidUtilities.displaySize.x)
            except Exception:
                decor_w = AndroidUtilities.dp(360)
        return max(AndroidUtilities.dp(120), decor_w - AndroidUtilities.dp(24))

    def _relayout_bubble(self):
        for v in (
            self._artwork_title_tv,
            self._artwork_view,
            self._artwork_row,
            self._bubble_text,
            self._bubble_subtext,
            self._media_controls_layout,
            self._sync_debug_tv,
        ):
            if v is not None:
                if isinstance(v, TextView):
                    try:
                        cur = v.getText()
                        v.setText(cur if cur is not None else "")
                    except Exception:
                        pass
                v.forceLayout()
                v.requestLayout()
        if self._bubble is not None:
            self._bubble.forceLayout()
            self._bubble.requestLayout()

    def _apply_karaoke_geometry(self, s: float):
        if self._bubble is None:
            return
        pad12 = max(4, int(self._dp(12) * s))
        pad7 = max(2, int(self._dp(7) * s))
        screen_cap = self._max_bubble_width_px()
        max_w = min(AndroidUtilities.dp(260.0 * s), max(AndroidUtilities.dp(100), screen_cap - pad12 * 2))
        base_min = 210.0 if abs(s - 1.0) < 0.01 else 110.0 * s
        min_w = min(AndroidUtilities.dp(base_min), max_w)
        self._bubble.setMinimumWidth(min_w)
        self._bubble.setLayoutParams(FrameLayout.LayoutParams(-2, -2))
        self._bubble.setPadding(pad12, pad7, pad12, pad7)

        art_sz = max(12, AndroidUtilities.dp(32.0 * s))
        if self._artwork_row is not None:
            self._artwork_row.setLayoutParams(LinearLayout.LayoutParams(-2, -2))
        if self._artwork_title_tv is not None:
            self._artwork_title_tv.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 10.5 * s)
            self._artwork_title_tv.setSingleLine(True)
            if TextUtils is not None:
                self._artwork_title_tv.setEllipsize(TextUtils.TruncateAt.END)
            self._artwork_title_tv.setMaxWidth(max(AndroidUtilities.dp(50), max_w - art_sz - AndroidUtilities.dp(10.0 * s)))
            self._artwork_title_tv.setLayoutParams(LinearLayout.LayoutParams(-2, -2))
        if self._media_controls_layout is not None:
            self._media_controls_layout.setLayoutParams(LinearLayout.LayoutParams(-2, -2))

        if self._bubble_text is not None:
            self._bubble_text.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 13.0 * s)
            self._bubble_text.setMinimumWidth(0)
            self._bubble_text.setMaxWidth(max_w)
            self._bubble_text.setGravity(Gravity.CENTER_HORIZONTAL)
            self._bubble_text.setLayoutParams(LinearLayout.LayoutParams(-2, -2))
        if self._bubble_subtext is not None:
            self._bubble_subtext.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 10.5 * s)
            self._bubble_subtext.setMinimumWidth(0)
            self._bubble_subtext.setMaxWidth(max_w)
            self._bubble_subtext.setGravity(Gravity.CENTER_HORIZONTAL)
            self._bubble_subtext.setLayoutParams(LinearLayout.LayoutParams(-2, -2))
        if self._sync_debug_tv is not None:
            self._sync_debug_tv.setTextSize(TypedValue.COMPLEX_UNIT_DIP, max(7.0, 9.0 * s))
            self._sync_debug_tv.setMaxWidth(max_w)
            self._sync_debug_tv.setLayoutParams(LinearLayout.LayoutParams(-2, -2))
        self._relayout_bubble()

    def _apply_speech_geometry(self, s: float):
        if self._bubble is None:
            return
        bg = GradientDrawable()
        bg.setCornerRadius(max(3.0, float(self._dp(12) * s)))
        bg.setColor(Theme.getColor(Theme.key_windowBackgroundWhite))
        bg.setStroke(max(1, int(self._dp(1))), Theme.getColor(Theme.key_divider))
        self._bubble.setBackground(bg)

        pad10 = max(3, int(self._dp(10) * s))
        pad6 = max(2, int(self._dp(6) * s))
        screen_cap = self._max_bubble_width_px()
        max_w = min(AndroidUtilities.dp(200.0 * s), max(AndroidUtilities.dp(90), screen_cap - pad10 * 2))

        self._bubble.setMinimumWidth(0)
        self._bubble.setLayoutParams(FrameLayout.LayoutParams(-2, -2))
        self._bubble.setPadding(pad10, pad6, pad10, pad6)

        if self._bubble_text is not None:
            self._bubble_text.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 13.0 * s)
            self._bubble_text.setMinimumWidth(0)
            self._bubble_text.setMaxWidth(max_w)
            self._bubble_text.setGravity(Gravity.NO_GRAVITY)
            self._bubble_text.setLayoutParams(LinearLayout.LayoutParams(-2, -2))
            self._bubble_text.setTextColor(Theme.getColor(Theme.key_windowBackgroundWhiteBlackText))
        if self._artwork_row is not None:
            self._artwork_row.setVisibility(View.GONE)
        if self._bubble_subtext is not None:
            self._bubble_subtext.setText("")
            self._bubble_subtext.setVisibility(View.GONE)
        if self._media_controls_layout is not None:
            self._media_controls_layout.setVisibility(View.GONE)
        if self._sync_debug_tv is not None:
            self._sync_debug_tv.setVisibility(View.GONE)
        self._relayout_bubble()

    def _show_karaoke_line(self, current_text: str, next_text: str, now: float):
        if self._bubble is None or self._bubble_text is None:
            return
        try:
            was_karaoke = (self._bubble_mode == "karaoke")
            was_visible = self._bubble_visible
            if not was_karaoke:
                self._bubble_mode = "karaoke"
                self._apply_karaoke_geometry(self._bubble_scale())
            if not was_karaoke or not was_visible or self._last_bubble_palette != self._target_palette:
                self._bubble_visible = True
                self._apply_karaoke_bubble_style()

            if self._artwork_row is not None:
                self._artwork_row.setVisibility(View.VISIBLE if self._artwork_bmp is not None else View.GONE)

            do_anim = was_visible and was_karaoke
            self._bubble_text.setTextColor(as_java_color(0xFFFFFFFF))
            self._animate_text_change(self._bubble_text, current_text, target_alpha=1.0, animate=do_anim)

            if self._bubble_subtext is not None:
                if next_text:
                    self._bubble_subtext.setVisibility(View.VISIBLE)
                    self._bubble_subtext.setTextColor(as_java_color(0x77FFFFFF))
                    self._animate_text_change(self._bubble_subtext, next_text, target_alpha=0.45, animate=do_anim)
                else:
                    self._bubble_subtext.setText("")
                    self._bubble_subtext.setVisibility(View.GONE)

            if self._media_controls_layout is not None and self._cfg.get("media_controls", True):
                self._media_controls_layout.setVisibility(View.VISIBLE)
            elif self._media_controls_layout is not None:
                self._media_controls_layout.setVisibility(View.GONE)

            self._bubble.setVisibility(View.VISIBLE)
            self._bubble.setAlpha(1.0)
            self._bubble_visible = True
            self._bubble_until = now + 9.0
            self._update_sync_debug_hud(now)
            self._bubble.forceLayout()
            self._bubble.requestLayout()
            if hasattr(self, "_on_bubble_resized"):
                self._on_bubble_resized()
        except Exception as e:
            CLOG.log_error("KARAOKE_UI", "Show line error", e)

    def _force_refetch_current_lyrics(self):
        clean_a = getattr(self, "_last_active_clean_a", "")
        clean_t = getattr(self, "_last_active_clean_t", "")
        if not clean_t:
            return
        expected_id = self._current_track_id
        self._say("Ищу свежий текст...", force=True)

        def _on_fresh(tl):
            def _apply():
                if self._unloaded or self._current_track_id != expected_id:
                    return
                self._lyrics_timeline = tl
                meta = self._lyrics_helper.get_lyrics_meta(clean_a, clean_t)
                cands = meta.get("candidates") or []
                self._record_sync_trace("REFETCH", f"src={meta.get('source')} lines={len(tl)} cands={len(cands)}")
                if len(cands) > 1:
                    self._open_lrc_candidates_dialog(clean_a, clean_t, expected_id, cands)
                elif tl:
                    self._apply_fresh_bridge_anchor_and_jump(expected_id)
                else:
                    self._say("no_lyrics", force=True)
            run_on_ui_thread(_apply)

        self._lyrics_helper.get_lyrics_async(
            clean_a, clean_t, _on_fresh, duration_ms=self._active_duration_ms, force_refresh=True
        )

    def _open_lrc_candidates_dialog(self, clean_a: str, clean_t: str, expected_id: str, cands: List[Dict[str, Any]]):
        try:
            ctx = self._get_safe_activity()
            if not ctx or not cands:
                return
            items = []
            for c in cands:
                cdur = float(c.get("duration") or 0.0)
                mm, ss = int(cdur // 60), int(cdur % 60)
                dur_str = f"{mm:02d}:{ss:02d}" if cdur > 0 else "?:??"
                items.append(f"[{c.get('source', '?')} • {dur_str}] {c.get('artist', '')} — {c.get('title', '')}")

            b = AlertDialog.Builder(ctx)
            b.setTitle("Выберите подходящий текст (LRC)")

            def _on_pick(_d, which):
                if 0 <= which < len(cands) and self._current_track_id == expected_id:
                    tl = self._lyrics_helper.apply_manual_candidate(clean_a, clean_t, cands[which])
                    if tl:
                        self._lyrics_timeline = tl
                        self._apply_fresh_bridge_anchor_and_jump(expected_id)

            b.setItems(items, DialogClickListener(_on_pick))
            b.setPositiveButton("Закрыть", None)
            b.show()
        except Exception as e:
            CLOG.log_error("LRC_PICK", "Candidates dialog error", e)

    # 2.3 Механика Tap-to-Sync (Выбор строки + сдвиг + смена LRC + HUD)
    def _open_tap_to_sync_dialog(self):
        try:
            ctx = self._get_safe_activity()
            if not ctx:
                return

            clean_a = getattr(self, "_last_active_clean_a", "")
            clean_t = getattr(self, "_last_active_clean_t", "")
            if not clean_t and self._current_track_id:
                parts = self._current_track_id.split("::")
                if len(parts) >= 3:
                    clean_a, clean_t = parts[1], parts[2]
                elif len(parts) == 2:
                    clean_t = parts[1]
            canon_key = f"{clean_a} - {clean_t}".strip(" -")

            root = LinearLayout(ctx)
            root.setOrientation(LinearLayout.VERTICAL)
            p14 = AndroidUtilities.dp(14)
            p8 = AndroidUtilities.dp(8)
            root.setPadding(p14, p8, p14, p8)

            meta = self._lyrics_helper.get_lyrics_meta(clean_a, clean_t) if clean_t else {}
            status_tv = TextView(ctx)
            status_tv.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 12.0)
            status_tv.setPadding(0, 0, 0, p8)

            def _refresh_status():
                status_tv.setText(
                    f"SRC: {self._last_sync_source} | Сдвиг: {self._user_offset:+.2f}с | Δ: {self._last_sync_delta_ms:+.0f}мс\n"
                    f"LRC: {meta.get('source', 'NONE')} ({meta.get('duration_sec', 0):.0f}с / трек {self._active_duration_ms/1000:.0f}с)"
                )

            _refresh_status()
            root.addView(status_tv, LinearLayout.LayoutParams(-1, -2))

            def _nudge(delta_sec: Optional[float]):
                now = time.monotonic()
                if delta_sec is None:
                    self._user_offset = 0.0
                else:
                    self._user_offset = round(self._user_offset + delta_sec, 2)
                self._sync_offset_ms = self._user_offset * 1000.0
                if canon_key:
                    self._session_offsets[canon_key] = self._user_offset
                self._record_sync_trace("OFFSET", f"manual offset={self._user_offset:+.2f}s")
                _refresh_status()
                self._last_hud_upd = 0.0
                self._current_lyric_idx = -1
                self._do_karaoke_line_switch()

            nudge_row = LinearLayout(ctx)
            nudge_row.setOrientation(LinearLayout.HORIZONTAL)
            nudge_row.setGravity(Gravity.CENTER)
            for lbl, dv in (("-0.5с", -0.5), ("-0.2с", -0.2), ("0с", None), ("+0.2с", 0.2), ("+0.5с", 0.5)):
                btn = TextView(ctx)
                btn.setText(lbl)
                btn.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 12.5)
                btn.setPadding(AndroidUtilities.dp(8), AndroidUtilities.dp(6), AndroidUtilities.dp(8), AndroidUtilities.dp(6))
                btn.setOnClickListener(ViewClickListener(lambda _v, d=dv: _nudge(d)))
                nudge_row.addView(btn, LinearLayout.LayoutParams(-2, -2))
            root.addView(nudge_row, LinearLayout.LayoutParams(-1, -2))

            dlg_ref = [None]
            tools_row = LinearLayout(ctx)
            tools_row.setOrientation(LinearLayout.HORIZONTAL)
            tools_row.setGravity(Gravity.CENTER)
            tools_row.setPadding(0, 0, 0, p8)

            def _toggle_hud():
                new_val = not bool(self._cfg.get("sync_debug_hud", False))
                self.set_setting("sync_debug_hud", new_val)
                self._on_cfg_change("sync_debug_hud", new_val)

            for lbl, fn in (
                ("🔄 Другой текст", lambda: (dlg_ref[0].dismiss() if dlg_ref[0] else None, self._force_refetch_current_lyrics())),
                ("🐞 HUD", _toggle_hud),
                ("📋 Отчёт", lambda: self._copy_system_report()),
            ):
                btn = TextView(ctx)
                btn.setText(lbl)
                btn.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 12.0)
                btn.setPadding(AndroidUtilities.dp(8), AndroidUtilities.dp(5), AndroidUtilities.dp(8), AndroidUtilities.dp(5))
                btn.setOnClickListener(ViewClickListener(lambda _v, f=fn: f()))
                tools_row.addView(btn, LinearLayout.LayoutParams(-2, -2))
            root.addView(tools_row, LinearLayout.LayoutParams(-1, -2))

            if self._lyrics_timeline:
                scroll = ScrollView(ctx)
                list_col = LinearLayout(ctx)
                list_col.setOrientation(LinearLayout.VERTICAL)

                def _select_line(which: int):
                    t_line, selected_text = self._lyrics_timeline[which]
                    now = time.monotonic()
                    t_calc_raw = self._get_current_track_pos(now)
                    # Формула: _user_offset = T_line - T_calc_raw
                    new_offset = t_line - t_calc_raw
                    self._user_offset = new_offset
                    self._sync_offset_ms = new_offset * 1000.0
                    if canon_key:
                        self._session_offsets[canon_key] = new_offset
                    self._record_sync_trace("TAPSYNC", f"line #{which} t={t_line:.2f}s offset={new_offset:+.3f}s")
                    CLOG.log_info(
                        "SYNC",
                        f"Калибровка Tap-to-Sync: строка #{which} '{selected_text}', new_offset={new_offset:.3f}с",
                        line_index=which,
                        offset=f"{new_offset:.3f}",
                    )
                    self._current_lyric_idx = which
                    next_txt = self._lyrics_timeline[which + 1][1] if which + 1 < len(self._lyrics_timeline) else ""
                    self._show_karaoke_line(selected_text, next_txt, now)
                    self._reschedule_karaoke_switch()
                    if dlg_ref[0] is not None:
                        dlg_ref[0].dismiss()

                for idx_l, (t_sec, text) in enumerate(self._lyrics_timeline):
                    mm = int(t_sec // 60)
                    ss = int(t_sec % 60)
                    prefix = "▶ " if idx_l == self._current_lyric_idx else ""
                    row_tv = TextView(ctx)
                    row_tv.setText(f"{prefix}[{mm:02d}:{ss:02d}] {text}")
                    row_tv.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 13.5)
                    row_tv.setPadding(AndroidUtilities.dp(4), AndroidUtilities.dp(7), AndroidUtilities.dp(4), AndroidUtilities.dp(7))
                    row_tv.setOnClickListener(ViewClickListener(lambda _v, i=idx_l: _select_line(i)))
                    list_col.addView(row_tv, LinearLayout.LayoutParams(-1, -2))

                scroll.addView(list_col)
                lp_scroll = LinearLayout.LayoutParams(-1, AndroidUtilities.dp(260))
                root.addView(scroll, lp_scroll)
            else:
                empty_tv = TextView(ctx)
                empty_tv.setText("Слова не найдены. Нажмите «🔄 Другой текст».")
                empty_tv.setPadding(0, p8, 0, p8)
                root.addView(empty_tv, LinearLayout.LayoutParams(-1, -2))

            b = AlertDialog.Builder(ctx)
            b.setTitle("Tap-to-Sync и Отладка [📋]")
            b.setView(root)
            b.setPositiveButton("Закрыть", None)
            dlg_ref[0] = b.show()
        except Exception as e:
            CLOG.log_error("SYNC_DIALOG", "Dialog error", e)

    def _start_custom_song(self, raw_input: str):
        a, t = self._lyrics_helper.clean_metadata("", raw_input)
        track_id = f"custom::{a}::{t}"
        if track_id == self._current_track_id and self._is_singing:
            return
        now = time.monotonic()
        self._current_track_id = track_id
        self._lyrics_timeline = []
        self._clear_playback_anchors(reset_user_offset=False)
        self._last_active_clean_a = a
        self._last_active_clean_t = t
        self._media = "music"
        self._track_is_playing = True
        self._anchor_pos_ms = 0.0
        self._anchor_mono = now
        self._anchor_speed = 1.0
        self._track_base_pos = 0.0
        self._track_base_time = now
        self._lyrics_retry_count = 0
        self._last_lyrics_retry = 0.0
        self._user_offset = self._session_offsets.get(f"{a} - {t}", 0.0)
        self._sync_offset_ms = self._user_offset * 1000.0

        self._say_track_detected(a, t)
        expected_track_id = track_id

        def _on_loaded(tl):
            def _apply():
                if self._unloaded or self._current_track_id != expected_track_id:
                    return
                self._lyrics_timeline = tl
                if not tl:
                    self._is_singing = False
                    self._say("no_lyrics")
                self._reschedule_karaoke_switch()
            run_on_ui_thread(_apply)

        self._lyrics_helper.get_lyrics_async(a, t, _on_loaded)
# === [/SHARED_BLOCK:PLAYER_ENGINE] ===

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
            self._bubble_gen += 1
            if self._handler is not None and self._grad_anim_r is not None:
                self._handler.removeCallbacks(self._grad_anim_r)
            self._bubble.animate().cancel()
            if self._bubble_text is not None:
                self._bubble_text.animate().withEndAction(None).cancel()
                self._bubble_text.setTranslationY(0.0)
                self._bubble_text.setAlpha(1.0)
            if self._bubble_subtext is not None:
                self._bubble_subtext.animate().withEndAction(None).cancel()
                self._bubble_subtext.setTranslationY(0.0)
                self._bubble_subtext.setText("")

            if self._bubble_mode != "speech":
                self._bubble_mode = "speech"
                self._apply_speech_geometry(self._bubble_scale())

            if self._bubble_text is not None:
                self._bubble_text.setText(text)
                self._bubble_text.forceLayout()
                self._bubble_text.requestLayout()

            self._bubble.forceLayout()
            self._bubble.requestLayout()
            self._bubble.setAlpha(0.0)
            self._bubble.setVisibility(View.VISIBLE)
            self._bubble_visible = True
            self._bubble_fade_in = True
            self._bubble_until = now + 2.0 + len(text) * 0.05
        except Exception as e:
            CLOG.log_error("BUBBLE", "Bubble text error", e)

    def _hide_bubble(self):
        if self._bubble is None or not self._bubble_visible:
            return
        if self._handler is not None and self._grad_anim_r is not None:
            self._handler.removeCallbacks(self._grad_anim_r)
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
        is_karaoke_active = (self._media == "music" or self._test_karaoke_active) and self._track_is_playing and bool(self._lyrics_timeline)
        if now >= self._bubble_until and not self._is_singing and not is_karaoke_active:
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

    # 3. «Абсолютный Обжора» 2.0 (Безопасное поедание любого View)
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
        min_side_dp = self._dp(24)  # Минимальный размер стороны: не менее 24 dp

        while stack and visited < 900:
            view = stack.pop()
            visited += 1

            if view is None or view.getVisibility() != View.VISIBLE:
                continue
            try:
                if float(view.getAlpha()) < 0.05:  # Пропускать элементы с alpha < 0.05
                    continue
            except Exception:
                pass

            # Исключение: собственные элементы плагина
            if (
                view.equals(self._pet)
                or view.equals(self._bubble)
                or (self._laser_view is not None and view.equals(self._laser_view))
            ):
                continue
            if any(view.equals(p) for p in self._poops) or any(view.equals(pt) for pt in self._particles):
                continue
            if any(item.get("view_ref") and view.equals(item["view_ref"].get()) for item in self._eaten):
                continue

            count = view.getChildCount() if isinstance(view, ViewGroup) else 0
            has_children = count > 0
            if has_children:
                for i in range(count):
                    child = view.getChildAt(i)
                    if child is not None:
                        stack.append(child)
                # Пропускать пустые контейнеры без фона/отрисовки
                if view.getBackground() is None:
                    continue

            w, h = view.getWidth(), view.getHeight()
            if w < min_side_dp or h < min_side_dp:
                continue
            if w >= width * 0.95 and h >= height * 0.95:
                continue

            view.getLocationInWindow(loc)
            x = loc[0] - dloc[0]
            y = loc[1] - dloc[1]
            if x + w <= 0 or y + h <= top or x >= width or y >= height:
                continue

            # Приоритет элементу с наименьшей площадью (W x H)
            area = float(w * h)
            is_container = isinstance(view, ViewGroup) and has_children
            candidates.append((view, x, y, w, h, area, is_container))

        if not candidates:
            return None

        # Контейнеры целиком (ViewGroup) выбираются только при отсутствии подходящих дочерних элементов
        leaf_candidates = [c for c in candidates if not c[6]]
        pool = leaf_candidates if leaf_candidates else candidates

        cx = self._x + self._w / 2.0
        cy = self._y + self._h / 2.0
        reach = self._dp(220)

        # Вес: наименьшая площадь + близость к питомцу
        def _score(item):
            _, x, y, w, h, area, _ = item
            dist = math.hypot(x + w / 2.0 - cx, y + h / 2.0 - cy)
            return (area ** 0.5) * (1.0 + dist / reach)

        pool.sort(key=_score)
        chosen = pool[0]
        return (chosen[0], chosen[1], chosen[2], chosen[3], chosen[4])

    def _try_eat(self, now, top):
        try:
            target = self._pick_target(top)
            if target is None:
                return False
            view, x, y, w, h = target

            # 3.4 Управление памятью: масштабирование снимка (длинная сторона <= 256 px)
            max_side = max(w, h)
            scale = min(1.0, 256.0 / max(1, max_side))
            bmp_w = max(1, int(w * scale))
            bmp_h = max(1, int(h * scale))

            bmp = Bitmap.createBitmap(bmp_w, bmp_h, Bitmap.Config.ARGB_8888)
            canvas = Canvas(bmp)
            if scale < 1.0:
                canvas.scale(scale, scale)
            canvas.translate(float(-view.getScrollX()), float(-view.getScrollY()))
            view.draw(canvas)

            orig_alpha = float(view.getAlpha())
            cls_name = view.getClass().getSimpleName()

            # 3.4 Ссылки хранятся строго через WeakReference!
            item = {
                "view_ref": WeakReference(view),
                "alpha": orig_alpha,
                "bmp": bmp,
                "w": w,
                "h": h,
                "cls_name": cls_name,
            }

            # 3.3 Безопасность RecyclerView: регистрируем OnChildAttachStateChangeListener
            # 6.1 Проверяем, не прикреплен ли уже слушатель от плагина к данному экземпляру RecyclerView
            parent = view.getParent()
            while parent is not None:
                if isinstance(parent, RecyclerView):
                    already = any(p is parent or (hasattr(p, "equals") and p.equals(parent)) for p, _ in self._recycler_listeners)
                    if not already:
                        listener = RecyclerAttachStateListener(self, view, orig_alpha)
                        parent.addOnChildAttachStateChangeListener(listener)
                        self._recycler_listeners.append((parent, listener))
                    break
                parent = parent.getParent()

            view.setAlpha(0.0)

            # Лимит желудка: максимум 12 элементов. При 13-м старейший автоматически выплёвывается
            if len(self._eaten) >= MAX_EATEN:
                oldest = self._eaten.pop(0)
                self._spit_one(oldest, self._x + self._w / 2.0, self._y + self._h / 2.0, 0)

            self._eaten.append(item)
            self._schedule_auto_return()

            copy = ImageView(self._pet.getContext())
            copy.setImageBitmap(bmp)
            copy.setScaleType(ImageView.ScaleType.FIT_XY)
            item["copy"] = copy
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
            anim.withEndAction(R(lambda v=copy, cn=cls_name: self._on_swallowed(v, cn)))
            anim.start()
            return True
        except Exception as e:
            CLOG.log_error("EAT", "Eat animation error", e)
            return False

    def _schedule_auto_return(self):
        # 3.5 Селектор автовозврата: 30 секунд, 2 минуты, 10 минут
        if self._handler is None or self._auto_return_r is None:
            return
        self._handler.removeCallbacks(self._auto_return_r)
        idx = clamp(int(self._cfg.get("auto_return", 1)), 0, len(AUTO_RETURN_SECONDS) - 1)
        sec = AUTO_RETURN_SECONDS[idx]
        self._handler.postDelayed(self._auto_return_r, int(sec * 1000.0))

    def _on_auto_return_triggered(self):
        CLOG.log_info("AUTO_RETURN", "Сработал таймер автовозврата: выплёвывание всего съеденного")
        self._give_back()

    def _on_recycler_cell_detached(self, view):
        # Ячейка списка откреплена при скролле
        CLOG.log_debug("RECYCLER", "Ячейка списка откреплена, alpha восстановлена")

    def _on_swallowed(self, copy, cls_name: str):
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

        try:
            self.set_setting("eaten_count", int(self.get_setting("eaten_count", 0) or 0) + 1)
        except Exception:
            pass

        # 3.6 Классификация реплик по типу съеденного View
        cn_lower = cls_name.lower()
        if "edittext" in cn_lower or "input" in cn_lower:
            self._say("eat_edittext")
        elif "message" in cn_lower or "chatmessagecell" in cn_lower or "text" in cn_lower:
            self._say("eat_message")
        elif "actionbar" in cn_lower or "toolbar" in cn_lower or "header" in cn_lower:
            self._say("eat_header")
        elif "avatar" in cn_lower or "backupimageview" in cn_lower or "round" in cn_lower:
            self._say("eat_avatar")
        else:
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
            pad = max(1, int(self._dp(6)))
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
        self._say("clean")

    def _remove_poops(self):
        for view in self._poops:
            self._remove_view(view)
        self._poops = []

    def _prune_eaten(self):
        kept = []
        for item in self._eaten:
            v = item["view_ref"].get() if item.get("view_ref") else None
            if v is not None:
                try:
                    if float(v.getAlpha()) < 0.05:
                        kept.append(item)
                    else:
                        copy_v = item.get("copy")
                        if copy_v is not None:
                            try:
                                copy_v.animate().cancel()
                                copy_v.setImageBitmap(None)
                            except Exception:
                                pass
                            item["copy"] = None
                        bmp = item.get("bmp")
                        if bmp is not None:
                            item["bmp"] = None
                            try:
                                bmp.recycle()
                            except Exception:
                                pass
                except Exception:
                    pass
            else:
                copy_v = item.get("copy")
                if copy_v is not None:
                    try:
                        copy_v.animate().cancel()
                        copy_v.setImageBitmap(None)
                    except Exception:
                        pass
                    item["copy"] = None
                bmp = item.get("bmp")
                if bmp is not None:
                    item["bmp"] = None
                    try:
                        bmp.recycle()
                    except Exception:
                        pass
        self._eaten = kept

    def _restore_all(self):
        items = self._eaten + self._spitting
        self._eaten, self._spitting = [], []
        for view in list(self._flying):
            try:
                view.animate().cancel()
                if hasattr(view, "setImageBitmap"):
                    view.setImageBitmap(None)
            except Exception:
                pass
            self._remove_view(view)
        self._flying = []

        for item in items:
            # 4. Предотвращение краша Canvas: trying to draw a recycled bitmap
            copy_v = item.get("copy")
            if copy_v is not None:
                try:
                    copy_v.animate().cancel()
                    if hasattr(copy_v, "setImageBitmap"):
                        copy_v.setImageBitmap(None)
                except Exception:
                    pass
                item["copy"] = None

            v = item["view_ref"].get() if item.get("view_ref") else None
            if v is not None:
                try:
                    v.setAlpha(float(item["alpha"]))
                except Exception:
                    pass
            bmp = item.get("bmp")
            if bmp is not None:
                item["bmp"] = None
                try:
                    bmp.recycle()
                except Exception:
                    pass

        # 6.2 Гарантированно открепляем слушателей RecyclerView
        for r_view, listener in self._recycler_listeners:
            try:
                r_view.removeOnChildAttachStateChangeListener(listener)
            except Exception:
                pass
        self._recycler_listeners = []

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
        if self._handler and self._auto_return_r:
            self._handler.removeCallbacks(self._auto_return_r)

        self._chew_until = 0.0
        self._mouth_open_until = now + 0.35 + 0.08 * len(items)
        self._set_expr("surprised", 0.9)
        self._squash_until = now + 0.12
        self._hop(self._dp(300))
        self._haptic(1)
        self._say("spit")

        mx = self._x + self._w / 2.0
        my = self._y + self._hop_off + self._unit * 8.0
        for i, item in enumerate(items):
            self._spit_one(item, mx, my, i * 70)
        self._schedule(0)

    def _spit_one(self, item, mx, my, delay):
        view = item["view_ref"].get() if item.get("view_ref") else None
        bmp = item.get("bmp")
        w, h = item["w"], item["h"]

        # Если View откреплен/переиспользован адаптером
        if view is None or not view.isAttachedToWindow() or self._decor is None:
            if view is not None:
                try:
                    view.setAlpha(float(item["alpha"]))
                except Exception:
                    pass
            if bmp is not None:
                item["bmp"] = None
                try:
                    bmp.recycle()
                except Exception:
                    pass
            return

        try:
            dloc = jarray(jint)([0, 0])
            loc = jarray(jint)([0, 0])
            self._decor.getLocationInWindow(dloc)
            view.getLocationInWindow(loc)
            x, y = loc[0] - dloc[0], loc[1] - dloc[1]

            self._spitting.append(item)
            copy = ImageView(self._pet.getContext())
            copy.setImageBitmap(bmp)
            copy.setScaleType(ImageView.ScaleType.FIT_XY)
            item["copy"] = copy
            self._decor.addView(copy, FrameLayout.LayoutParams(w, h))
            self._flying.append(copy)

            copy.setTranslationX(float(mx - w / 2.0))
            copy.setTranslationY(float(my - h / 2.0))
            copy.setScaleX(0.01)
            copy.setScaleY(0.01)

            def _done(v=copy, it=item, target=view):
                try:
                    v.animate().cancel()
                    v.setImageBitmap(None)
                except Exception:
                    pass
                self._remove_view(v)
                try:
                    self._flying.remove(v)
                except ValueError:
                    pass
                try:
                    self._spitting.remove(it)
                except ValueError:
                    pass
                it["copy"] = None
                if target is not None:
                    try:
                        target.setAlpha(float(it["alpha"]))
                    except Exception:
                        pass
                bmp_ref = it.get("bmp")
                if bmp_ref is not None:
                    it["bmp"] = None
                    try:
                        bmp_ref.recycle()
                    except Exception:
                        pass

            copy.animate().translationX(float(x)).translationY(float(y)).scaleX(1.0).scaleY(1.0).setDuration(450).setStartDelay(
                int(delay)
            ).setInterpolator(OvershootInterpolator(1.2)).withEndAction(R(_done)).start()
        except Exception as e:
            CLOG.log_error("SPIT", "Spit error", e)
            if view is not None:
                try:
                    view.setAlpha(float(item["alpha"]))
                except Exception:
                    pass
            copy_v = item.get("copy")
            if copy_v is not None:
                try:
                    copy_v.animate().cancel()
                    copy_v.setImageBitmap(None)
                except Exception:
                    pass
                item["copy"] = None
            if bmp is not None:
                item["bmp"] = None
                try:
                    bmp.recycle()
                except Exception:
                    pass

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
                        # Распознавать статус набора: печатает, typing, друкує
                        if ("печатает" in txt or "typing" in txt or "друкує" in txt) and self._state in ("idle", "walk") and now >= self._next_action:
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
