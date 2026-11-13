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

from android.content import ClipData, ClipboardManager, Context, DialogInterface
from android.graphics import BitmapFactory
from android.graphics.drawable import GradientDrawable, LayerDrawable
from android.os import Environment, Handler, Looper
from android.util import TypedValue
from android.view import Gravity, KeyEvent, MotionEvent, View
from android.widget import FrameLayout, ImageView, LinearLayout, ScrollView, SeekBar, TextView
from java import dynamic_proxy, jarray, jbyte, jint
from org.telegram.messenger import AndroidUtilities, MediaController
from org.telegram.ui import LaunchActivity
from org.telegram.ui.ActionBar import AlertDialog, Theme

from android_utils import R, log, run_on_ui_thread
from base_plugin import AppEvent, BasePlugin, MenuItemData, MenuItemType
from client_utils import get_last_fragment
from ui.settings import Divider, Header, Selector, Switch, Text

try:
    from android.text import TextUtils
except Exception:
    TextUtils = None

__id__ = "clawd_lyrics_player"
__name__ = "Clawd Lyrics"
__description__ = (
    "Автономный музыкальный текстовик (караоке-оверлей) без питомца v3.5.\n\n"
    "• Синхронный 2-строчный текст песен (LRCLIB + NetEase + архив Lyrics/) с Tap-to-Sync [📋].\n"
    "• Интеграция с Clawd Bridge (SSE /events + обложки + анимированный 3-цветный градиент).\n"
    "• Свободное перемещение рамки пальцем по экрану, пресеты позиции и точная настройка X/Y.\n"
    "• Динамический масштаб рамки и текста от 0.40x до 2.00x."
)
__author__ = "@tsobbb"
__version__ = "3.5"
__icon__ = "msg_round_play"

POS_V_ITEMS = [
    "Сверху (под шапкой)",
    "По центру экрана",
    "Снизу (над панелью)",
    "Пользовательская (перетаскиванием)",
]
POS_H_ITEMS = [
    "По центру",
    "Слева",
    "Справа",
    "Пользовательская (X%)",
]

MAX_LOG_FILE_SIZE = 512 * 1024  # строго 512 КБ
MAX_LYRICS_FILES = 200

STATUS_PHRASES = {
    "no_lyrics": "Слов не нашёл :(",
    "sync_unavailable": "Синхронизация недоступна",
}


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


class LyricsBubbleTouchListener(dynamic_proxy(View.OnTouchListener)):
    """Перетаскивание текстовой рамки пальцем по экрану (если позиция не закреплена)."""

    def __init__(self, plugin):
        super().__init__()
        self.plugin = plugin
        self._down_rx = 0.0
        self._down_ry = 0.0
        self._start_x = 0.0
        self._start_y = 0.0
        self._dragging = False

    def onTouch(self, view, event):
        try:
            if self.plugin is None or self.plugin._cfg.get("lock_position", False):
                return False
            action = int(event.getActionMasked())
            rx = float(event.getRawX())
            ry = float(event.getRawY())
            if action == MotionEvent.ACTION_DOWN:
                self._down_rx = rx
                self._down_ry = ry
                self._start_x = float(view.getTranslationX())
                self._start_y = float(view.getTranslationY())
                self._dragging = False
                return True
            if action == MotionEvent.ACTION_MOVE:
                dx = rx - self._down_rx
                dy = ry - self._down_ry
                if not self._dragging:
                    slop = float(AndroidUtilities.dp(6))
                    if (dx * dx + dy * dy) < (slop * slop):
                        return True
                    self._dragging = True
                self.plugin._apply_drag_xy(self._start_x + dx, self._start_y + dy)
                return True
            if action in (MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL):
                if self._dragging:
                    self.plugin._commit_drag_position()
                    self._dragging = False
                    return True
                return False
        except Exception as e:
            CLOG.log_error("DRAG", "Bubble drag error", e)
        return False


class ClawdLyricsPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        self._handler = None
        self._tick_r = None
        self._karaoke_switch_r = None
        self._grad_anim_r = None
        self._running = False
        self._paused = False
        self._unloaded = False
        self._cfg: Dict[str, Any] = {}

        self._decor = None
        self._pet = None  # Совместимость с общими методами плеера (питомца нет)
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
        self._bubble_touch_listener = None

        self._dp_cache: Dict[Any, float] = {}
        self._state = "idle"
        self._pos_ready = True
        self._bubble_visible = False
        self._bubble_gen = 0
        self._bubble_until = 0.0
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

        self._media = None
        self._media_check = 0.0
        self._last_checked_clip = ""
        self._clip_check_time = 0.0

        self._bridge_thread = None
        self._bridge_stop_event = threading.Event()
        self._bridge_consecutive_errors = 0
        self._bridge_interval = 1.6
        self._bridge_last_ping_latency = 0.0
        self._bridge_data: Optional[Dict[str, Any]] = None
        self._bridge_lock = threading.Lock()
        self._bridge_mode = "INIT"
        self._bridge_sse_resp = None
        self._bridge_sse_connected = False
        self._bridge_push_pending = False
        self._last_sse_rx_mono = 0.0
        self._last_processed_bridge_rx_mono = 0.0

        self._dragging_now = False

    def _add_debug_log(self, msg: str):
        CLOG.log_info("APP", msg)

    def _dp(self, value) -> float:
        cached = self._dp_cache.get(value)
        if cached is not None:
            return cached
        res = float(AndroidUtilities.dp(value))
        self._dp_cache[value] = res
        return res

    def _hop(self, *_args, **_kwargs):
        pass

    def on_plugin_load(self):
        CLOG.ensure_started()
        CLOG.log_info("LOAD", f"Загрузка Clawd Lyrics v{__version__} by {__author__}...")
        with self._bridge_lock:
            self._bridge_data = None
        self._clear_playback_anchors(reset_user_offset=True)
        self._reload_cfg()
        self._handler = Handler(Looper.getMainLooper())
        self._tick_r = R(self._tick)
        self._karaoke_switch_r = R(self._do_karaoke_line_switch)
        self._grad_anim_r = R(self._step_gradient_anim)

        self.add_menu_item(
            MenuItemData(
                menu_type=MenuItemType.DRAWER_MENU,
                text="Текстовик Clawd",
                on_click=self._on_menu_toggle,
                item_id="clawd_lyrics_toggle",
                icon="msg_round_play",
            )
        )
        self._start_bridge_daemon()
        run_on_ui_thread(self._start)

    def on_plugin_unload(self):
        CLOG.log_info("UNLOAD", f"Выгрузка Clawd Lyrics v{__version__}...")
        self._unloaded = True
        self._running = False
        if self._handler is not None:
            for r in (self._tick_r, self._karaoke_switch_r, self._grad_anim_r):
                if r is not None:
                    self._handler.removeCallbacks(r)
        self._stop_bridge_daemon()
        with self._bridge_lock:
            self._bridge_data = None
        self._clear_playback_anchors(reset_user_offset=True)
        run_on_ui_thread(self._detach_views)
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

    def on_app_event(self, event_type):
        if event_type == AppEvent.PAUSE:
            self._paused = True
            if self._handler is not None:
                for r in (self._tick_r, self._karaoke_switch_r, self._grad_anim_r):
                    if r is not None:
                        self._handler.removeCallbacks(r)
        elif event_type == AppEvent.RESUME:
            self._paused = False
            run_on_ui_thread(self._start)

    def create_settings(self) -> List[Any]:
        scale_cur = clamp(float(self.get_setting("bubble_scale", 1.0) or 1.0), 0.4, 2.0)
        x_pct = int(round(clamp(float(self.get_setting("pos_x_pct", 0.5) if self.get_setting("pos_x_pct", None) is not None else 0.5), 0.0, 1.0) * 100))
        y_pct = int(round(clamp(float(self.get_setting("pos_y_pct", 0.12) if self.get_setting("pos_y_pct", None) is not None else 0.12), 0.0, 1.0) * 100))
        return [
            Header(text=f"Clawd Lyrics v{__version__} (Только плеер)"),
            Switch(
                key="show",
                text="Показывать текстовик",
                default=True,
                subtext="Также включается в боковом меню Telegram",
                icon="msg_round_play",
                on_change=lambda v: self._on_cfg_change("show", v),
            ),
            Header(text="Размер и расположение рамки"),
            Text(
                text="Размер рамки текста (0.4x – 2.0x)",
                subtext=f"Текущий масштаб: {scale_cur:.2f}x",
                icon="msg_customize",
                on_click=lambda _v=None: run_on_ui_thread(self._open_bubble_scale_dialog),
            ),
            Selector(
                key="pos_v_preset",
                text="Позиция по вертикали",
                default=0,
                items=POS_V_ITEMS,
                icon="msg_photo_settings",
                on_change=lambda v: self._on_cfg_change("pos_v_preset", v),
            ),
            Selector(
                key="pos_h_preset",
                text="Выравнивание по горизонтали",
                default=0,
                items=POS_H_ITEMS,
                icon="msg_photo_settings",
                on_change=lambda v: self._on_cfg_change("pos_h_preset", v),
            ),
            Text(
                text="Настроить позицию рамки (X / Y)",
                subtext=f"Текущая точка: X={x_pct}%, Y={y_pct}% (или тяните пальцем)",
                icon="msg_location",
                on_click=lambda _v=None: run_on_ui_thread(self._open_position_dialog),
            ),
            Switch(
                key="lock_position",
                text="Зафиксировать рамку",
                default=False,
                subtext="Отключает перетаскивание рамки пальцем по экрану",
                icon="msg_pin",
                on_change=lambda v: self._on_cfg_change("lock_position", v),
            ),
            Header(text="Караоке и Clawd Bridge 🎵"),
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
                text="Пульт управления в рамке",
                default=True,
                subtext="Кнопки [⏮], [⏯], [⏭] и [📋] для выбора строки",
                icon="msg_round_play",
                on_change=lambda v: self._on_cfg_change("media_controls", v),
            ),
            Switch(
                key="show_on_pause",
                text="Показывать рамку на паузе",
                default=False,
                subtext="Если выкл — рамка плавно скрывается, когда трек на паузе",
                icon="msg_pause",
                on_change=lambda v: self._on_cfg_change("show_on_pause", v),
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
                subtext="Открывает текст скопированных ссылок SoundCloud",
                icon="msg_copy",
                on_change=lambda v: self._on_cfg_change("clipboard_sync", v),
            ),
            Header(text="🧪 Тест и Диагностика"),
            Text(
                text="🧪 Тест караоке (Демо-трек)",
                subtext="Проверить рамку, градиент, размер и расположение без музыки",
                icon="msg_diagnostic",
                accent=True,
                on_click=lambda _v=None: run_on_ui_thread(self._run_demo_test),
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
            Divider(),
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

    def _run_demo_test(self):
        self._test_karaoke_active = True
        self._start_custom_song("Kai Angel - andy warhol")

    def _show_logs_dialog(self):
        try:
            ctx = self._get_safe_activity()
            if not ctx:
                return
            lines = list(CLOG.ring_buffer)[-50:]
            content = "=== КОЛЬЦЕВОЙ БУФЕР В ПАМЯТИ (500 строк) ===\n" + "\n".join(lines)
            b = AlertDialog.Builder(ctx)
            b.setTitle("Журнал Clawd Lyrics")
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
                f"=== ДАМП CLAWD LYRICS v{__version__} ===\n"
                f"Время: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Статус моста: mode={self._bridge_mode}, errors={self._bridge_consecutive_errors}, latency={self._bridge_last_ping_latency:.1f}ms\n"
                f"Текущий трек: {self._current_track_id} (dur={self._active_duration_ms/1000.0:.1f}s, speed={self._playback_speed:.2f}x, src={self._last_sync_source})\n"
                f"Якорь: raw={self._last_raw_pos_ms}ms, calc={self._get_current_track_pos_ms():.0f}ms, Δ={self._last_sync_delta_ms:+.0f}ms, idx={self._current_lyric_idx}/{len(self._lyrics_timeline)}\n"
                f"LRC совпадение: src={lrc_meta.get('source', 'NONE')}, '{lrc_meta.get('matched_artist', '')} - {lrc_meta.get('matched_title', '')}', lrc_dur={lrc_meta.get('duration_sec', 0):.1f}s, score={lrc_meta.get('score', 0):.1f}\n"
                f"Смещение _user_offset: {self._user_offset:.3f} с\n"
                f"Масштаб: {self._bubble_scale():.2f}x, X={self._cfg.get('pos_x_pct', 0.5):.2f}, Y={self._cfg.get('pos_y_pct', 0.12):.2f}\n"
                f"\n=== ТРАССИРОВКА СИНХРОНИЗАЦИИ (ПОСЛЕДНИЕ {len(sync_trace_lines)} СОБЫТИЙ) ===\n"
                + ("\n".join(sync_trace_lines) if sync_trace_lines else "(пусто)")
                + f"\n\n=== ПОСЛЕДНИЕ 200 СТРОК ЛОГА ===\n"
                + "\n".join(last_lines)
            )
            cm.setPrimaryClip(ClipData.newPlainText("Clawd Lyrics Diagnostics", report))
            self._say("Отчёт скопирован в буфер! 📋", force=True)
        except Exception as e:
            CLOG.log_error("REPORT", "Report copy error", e)

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
        def _f(key, default, lo, hi):
            try:
                v = self.get_setting(key, default)
                return clamp(float(default if v is None else v), lo, hi)
            except Exception:
                return default

        self._cfg = {
            "show": bool(self.get_setting("show", True)),
            "dance": True,
            "karaoke": True,
            "bubble_scale": _f("bubble_scale", 1.0, 0.4, 2.0),
            "pos_v_preset": clamp(int(self.get_setting("pos_v_preset", 0) or 0), 0, len(POS_V_ITEMS) - 1),
            "pos_h_preset": clamp(int(self.get_setting("pos_h_preset", 0) or 0), 0, len(POS_H_ITEMS) - 1),
            "pos_x_pct": _f("pos_x_pct", 0.5, 0.0, 1.0),
            "pos_y_pct": _f("pos_y_pct", 0.12, 0.0, 1.0),
            "lock_position": bool(self.get_setting("lock_position", False)),
            "animated_gradient_border": bool(self.get_setting("animated_gradient_border", True)),
            "media_controls": bool(self.get_setting("media_controls", True)),
            "show_on_pause": bool(self.get_setting("show_on_pause", False)),
            "sync_debug_hud": bool(self.get_setting("sync_debug_hud", False)),
            "clipboard_sync": bool(self.get_setting("clipboard_sync", False)),
        }
        self._sync_offset_ms = 0.0
        self._user_offset = 0.0

    def _on_cfg_change(self, key, value):
        self._cfg[key] = value
        if key == "show":
            run_on_ui_thread(lambda: self._apply_show(bool(value)))
        elif key == "animated_gradient_border":
            run_on_ui_thread(self._apply_karaoke_bubble_style)
        elif key == "bubble_scale":
            run_on_ui_thread(self._refresh_bubble_scale)
        elif key in ("pos_v_preset", "pos_h_preset", "pos_x_pct", "pos_y_pct"):
            run_on_ui_thread(self._position_lyrics_bubble)
        elif key == "media_controls":
            run_on_ui_thread(self._apply_controls_visibility)
        elif key == "sync_debug_hud":
            run_on_ui_thread(lambda: (setattr(self, "_last_hud_upd", 0.0), self._update_sync_debug_hud(time.monotonic()), self._relayout_bubble(), self._position_lyrics_bubble()))

    def _apply_controls_visibility(self):
        if self._media_controls_layout is not None:
            show_ctrl = bool(self._cfg.get("media_controls", True)) and self._bubble_mode == "karaoke"
            self._media_controls_layout.setVisibility(View.VISIBLE if show_ctrl else View.GONE)
            self._relayout_bubble()
            self._position_lyrics_bubble()

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

    def _open_position_dialog(self):
        try:
            ctx = self._get_safe_activity()
            if not ctx:
                return
            orig_x = clamp(float(self._cfg.get("pos_x_pct", 0.5)), 0.0, 1.0)
            orig_y = clamp(float(self._cfg.get("pos_y_pct", 0.12)), 0.0, 1.0)
            orig_vp = int(self._cfg.get("pos_v_preset", 0))
            orig_hp = int(self._cfg.get("pos_h_preset", 0))
            cur_xy = [orig_x, orig_y]

            root = LinearLayout(ctx)
            root.setOrientation(LinearLayout.VERTICAL)
            p20 = AndroidUtilities.dp(20)
            p10 = AndroidUtilities.dp(10)
            root.setPadding(p20, p10, p20, p10)

            lbl_x = TextView(ctx)
            lbl_x.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 14.0)
            lbl_x.setText(f"По горизонтали (X): {int(round(orig_x * 100))}%")
            root.addView(lbl_x, LinearLayout.LayoutParams(-1, -2))

            seek_x = SeekBar(ctx)
            seek_x.setMax(100)
            seek_x.setProgress(int(round(orig_x * 100)))
            root.addView(seek_x, LinearLayout.LayoutParams(-1, -2))

            lbl_y = TextView(ctx)
            lbl_y.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 14.0)
            lbl_y.setPadding(0, p10, 0, 0)
            lbl_y.setText(f"По вертикали (Y): {int(round(orig_y * 100))}%")
            root.addView(lbl_y, LinearLayout.LayoutParams(-1, -2))

            seek_y = SeekBar(ctx)
            seek_y.setMax(100)
            seek_y.setProgress(int(round(orig_y * 100)))
            root.addView(seek_y, LinearLayout.LayoutParams(-1, -2))

            def _preview(px: float, py: float):
                cur_xy[0] = clamp(px, 0.0, 1.0)
                cur_xy[1] = clamp(py, 0.0, 1.0)
                lbl_x.setText(f"По горизонтали (X): {int(round(cur_xy[0] * 100))}%")
                lbl_y.setText(f"По вертикали (Y): {int(round(cur_xy[1] * 100))}%")
                self._cfg["pos_h_preset"] = 3
                self._cfg["pos_v_preset"] = 3
                self._cfg["pos_x_pct"] = cur_xy[0]
                self._cfg["pos_y_pct"] = cur_xy[1]
                self._position_lyrics_bubble()

            seek_x.setOnSeekBarChangeListener(BubbleScaleSeekListener(lambda prog: _preview(prog / 100.0, cur_xy[1])))
            seek_y.setOnSeekBarChangeListener(BubbleScaleSeekListener(lambda prog: _preview(cur_xy[0], prog / 100.0)))

            def _save(_d, _w):
                self._cfg["pos_h_preset"] = 3
                self._cfg["pos_v_preset"] = 3
                self._cfg["pos_x_pct"] = cur_xy[0]
                self._cfg["pos_y_pct"] = cur_xy[1]
                self.set_setting("pos_h_preset", 3)
                self.set_setting("pos_v_preset", 3)
                self.set_setting("pos_x_pct", float(cur_xy[0]))
                self.set_setting("pos_y_pct", float(cur_xy[1]))
                self._position_lyrics_bubble()
                self._say("Позиция сохранена", force=True)

            def _reset(_d, _w):
                self._cfg["pos_h_preset"] = 0
                self._cfg["pos_v_preset"] = 0
                self._cfg["pos_x_pct"] = 0.5
                self._cfg["pos_y_pct"] = 0.12
                self.set_setting("pos_h_preset", 0)
                self.set_setting("pos_v_preset", 0)
                self.set_setting("pos_x_pct", 0.5)
                self.set_setting("pos_y_pct", 0.12)
                self._position_lyrics_bubble()

            def _cancel(_d, _w):
                self._cfg["pos_h_preset"] = orig_hp
                self._cfg["pos_v_preset"] = orig_vp
                self._cfg["pos_x_pct"] = orig_x
                self._cfg["pos_y_pct"] = orig_y
                self._position_lyrics_bubble()

            b = AlertDialog.Builder(ctx)
            b.setTitle("Позиция рамки на экране")
            b.setView(root)
            b.setPositiveButton("Сохранить", TGDialogClickListener(_save))
            b.setNeutralButton("Сверху по центру", TGDialogClickListener(_reset))
            b.setNegativeButton("Отмена", TGDialogClickListener(_cancel))
            b.show()
        except Exception as e:
            CLOG.log_error("POS_DIALOG", "Position dialog error", e)

    def _on_menu_toggle(self, context=None):
        show = not self._cfg.get("show", True)
        self._cfg["show"] = show
        self.set_setting("show", show)
        run_on_ui_thread(lambda: self._apply_show(show))

    def _apply_show(self, show: bool):
        if show:
            self._start()
        else:
            self._running = False
            if self._handler is not None and self._tick_r is not None:
                self._handler.removeCallbacks(self._tick_r)
            self._detach_views()

    def _start(self):
        if self._unloaded or self._paused or not self._cfg.get("show", True):
            return
        try:
            self._ensure_attached()
        except Exception as e:
            CLOG.log_error("START", "Attach error", e)
        if self._bubble is None:
            run_on_ui_thread(self._start, 700)
            return
        self._running = True
        self._schedule(100)

    def _schedule(self, delay_ms: int = 100):
        if self._handler is not None and self._tick_r is not None and self._running and not self._paused:
            self._handler.removeCallbacks(self._tick_r)
            self._handler.postDelayed(self._tick_r, max(16, int(delay_ms)))

    def _ensure_attached(self):
        act = self._get_safe_activity()
        if act is None:
            return
        window = act.getWindow()
        decor = window.getDecorView() if window is not None else None
        if decor is None:
            return
        if self._decor is decor and self._bubble is not None and self._bubble.getParent() is decor:
            return
        self._detach_views()
        self._decor = decor
        self._build_views(act)

    def _build_views(self, context):
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
        self._bubble_touch_listener = LyricsBubbleTouchListener(self)
        bubble_layout.setOnTouchListener(self._bubble_touch_listener)

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
            btn.setClickable(True)
            btn.setOnClickListener(ViewClickListener(lambda _v: cb()))
            self._media_ctrl_btns.append(btn)
            return btn

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
        self._clear_artwork()
        if self._handler is not None and self._grad_anim_r is not None:
            self._handler.removeCallbacks(self._grad_anim_r)
        if self._bubble is not None:
            try:
                self._bubble.animate().cancel()
                parent = self._bubble.getParent()
                if parent is not None:
                    parent.removeView(self._bubble)
            except Exception:
                pass
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
        self._bubble_touch_listener = None
        self._decor = None
        self._bubble_mode = None
        self._last_bubble_palette = None
        self._karaoke_border_gd = None
        self._karaoke_bg_gd = None
        self._karaoke_layer_drawable = None
        self._bubble_visible = False

    def _safe_xy_bounds(self, bw: int, bh: int) -> Tuple[float, float, float, float]:
        decor_w = int(self._decor.getWidth()) if self._decor is not None else 0
        decor_h = int(self._decor.getHeight()) if self._decor is not None else 0
        if decor_w <= 0:
            decor_w = int(getattr(AndroidUtilities.displaySize, "x", 1080))
        if decor_h <= 0:
            decor_h = int(getattr(AndroidUtilities.displaySize, "y", 2200))
        margin = float(self._dp(8))
        sb_h = float(getattr(AndroidUtilities, "statusBarHeight", 0) or 0)
        nb_h = float(getattr(AndroidUtilities, "navigationBarHeight", 0) or 0)
        min_x = margin
        max_x = max(min_x, float(decor_w - bw) - margin)
        min_y = sb_h + float(self._dp(8))
        max_y = max(min_y, float(decor_h - bh) - nb_h - float(self._dp(8)))
        return (min_x, max_x, min_y, max_y)

    def _apply_drag_xy(self, x: float, y: float):
        if self._bubble is None:
            return
        bw = max(1, int(self._bubble.getWidth()))
        bh = max(1, int(self._bubble.getHeight()))
        min_x, max_x, min_y, max_y = self._safe_xy_bounds(bw, bh)
        self._bubble.setTranslationX(float(clamp(x, min_x, max_x)))
        self._bubble.setTranslationY(float(clamp(y, min_y, max_y)))

    def _commit_drag_position(self):
        if self._bubble is None:
            return
        bw = max(1, int(self._bubble.getWidth()))
        bh = max(1, int(self._bubble.getHeight()))
        min_x, max_x, min_y, max_y = self._safe_xy_bounds(bw, bh)
        tx = clamp(float(self._bubble.getTranslationX()), min_x, max_x)
        ty = clamp(float(self._bubble.getTranslationY()), min_y, max_y)
        px = (tx - min_x) / (max_x - min_x) if max_x > min_x else 0.5
        py = (ty - min_y) / (max_y - min_y) if max_y > min_y else 0.12
        px = round(clamp(px, 0.0, 1.0), 3)
        py = round(clamp(py, 0.0, 1.0), 3)
        self._cfg["pos_h_preset"] = 3
        self._cfg["pos_v_preset"] = 3
        self._cfg["pos_x_pct"] = px
        self._cfg["pos_y_pct"] = py
        self.set_setting("pos_h_preset", 3)
        self.set_setting("pos_v_preset", 3)
        self.set_setting("pos_x_pct", px)
        self.set_setting("pos_y_pct", py)

    def _position_lyrics_bubble(self):
        if self._bubble is None or not self._bubble_visible:
            return
        bw = int(self._bubble.getWidth())
        bh = int(self._bubble.getHeight())
        if bw <= 0 or bh <= 0:
            self._bubble.post(R(self._position_lyrics_bubble))
            return
        min_x, max_x, min_y, max_y = self._safe_xy_bounds(bw, bh)

        hp = int(self._cfg.get("pos_h_preset", 0))
        if hp == 0:
            bx = (min_x + max_x) / 2.0
        elif hp == 1:
            bx = min_x
        elif hp == 2:
            bx = max_x
        else:
            bx = min_x + (max_x - min_x) * clamp(float(self._cfg.get("pos_x_pct", 0.5)), 0.0, 1.0)

        vp = int(self._cfg.get("pos_v_preset", 0))
        if vp == 0:
            by = min(max_y, min_y + float(self._dp(52)))
        elif vp == 1:
            by = (min_y + max_y) / 2.0
        elif vp == 2:
            by = max(min_y, max_y - float(self._dp(56)))
        else:
            by = min_y + (max_y - min_y) * clamp(float(self._cfg.get("pos_y_pct", 0.12)), 0.0, 1.0)

        self._bubble.setTranslationX(float(clamp(bx, min_x, max_x)))
        self._bubble.setTranslationY(float(clamp(by, min_y, max_y)))

    def _on_bubble_resized(self):
        if self._bubble is not None and self._bubble_visible:
            self._bubble.post(R(self._position_lyrics_bubble))

    def _poll_clipboard(self, now: float):
        if now < self._clip_check_time or not self._cfg.get("clipboard_sync", False):
            return
        self._clip_check_time = now + 2.0
        try:
            ctx = self._bubble.getContext() if self._bubble is not None else LaunchActivity.instance
            if not ctx:
                return
            cm = ctx.getSystemService(Context.CLIPBOARD_SERVICE)
            if cm and cm.hasPrimaryClip():
                clip = cm.getPrimaryClip()
                if clip and clip.getItemCount() > 0:
                    text = str(clip.getItemAt(0).coerceToText(ctx) or "").strip()
                    if text and text != self._last_checked_clip:
                        self._last_checked_clip = text
                        if "soundcloud.com/" in text:
                            m = re.search(r"https?://(?:on\.)?soundcloud\.com/\S+", text)
                            if m:
                                url = m.group(0)
                                threading.Thread(target=lambda u=url: self._resolve_sc(u), daemon=True).start()
        except Exception:
            pass

    def _resolve_sc(self, url: str):
        res = self._lyrics_helper.resolve_soundcloud_url(url)
        if res:
            a, t = res
            run_on_ui_thread(lambda: self._start_custom_song(f"{a} - {t}"))

    def _tick(self):
        if not self._running or self._paused or self._unloaded:
            return
        try:
            self._ensure_attached()
            if self._bubble is None or self._decor is None:
                self._schedule(200)
                return
            now = time.monotonic()
            self._poll_media(now)
            self._poll_clipboard(now)

            if (self._media == "music" or self._test_karaoke_active) and self._track_is_playing and self._lyrics_timeline:
                if now - self._last_failsafe_check >= 0.10:
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

            if self._bubble_visible:
                self._update_sync_debug_hud(now)
                if not self._track_is_playing and not self._cfg.get("show_on_pause", False):
                    if self._media == "music" and self._bubble_mode == "karaoke":
                        self._bubble_until = min(self._bubble_until, now + 1.2)
                    if now >= self._bubble_until:
                        self._hide_bubble()
                    else:
                        self._position_lyrics_bubble()
                else:
                    self._position_lyrics_bubble()
        except Exception as e:
            CLOG.log_error("TICK", "Lyrics tick error", e)
        self._schedule(100)

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

    def _say(self, category, force=False, name=None):
        if self._is_singing or self._bubble is None:
            return
        if not force and category not in STATUS_PHRASES:
            return
        text = STATUS_PHRASES.get(category, str(category))
        now = time.monotonic()
        try:
            self._bubble_gen += 1
            if self._bubble_mode != "karaoke":
                self._bubble_mode = "karaoke"
                self._apply_karaoke_geometry(self._bubble_scale())
            self._bubble_visible = True
            self._apply_karaoke_bubble_style()
            if self._artwork_row is not None:
                self._artwork_row.setVisibility(View.VISIBLE if self._artwork_bmp is not None else View.GONE)
            if self._bubble_text is not None:
                self._bubble_text.animate().withEndAction(None).cancel()
                self._bubble_text.setTextColor(as_java_color(0xFFFFFFFF))
                self._bubble_text.setText(text)
                self._bubble_text.setAlpha(1.0)
                self._bubble_text.setTranslationY(0.0)
                self._bubble_text.forceLayout()
                self._bubble_text.requestLayout()
            if self._bubble_subtext is not None:
                self._bubble_subtext.animate().withEndAction(None).cancel()
                self._bubble_subtext.setText("")
                self._bubble_subtext.setVisibility(View.GONE)
            if self._media_controls_layout is not None:
                show_ctrl = bool(self._cfg.get("media_controls", True)) and self._media == "music"
                self._media_controls_layout.setVisibility(View.VISIBLE if show_ctrl else View.GONE)
            self._bubble.forceLayout()
            self._bubble.requestLayout()
            self._bubble.setAlpha(1.0)
            self._bubble.setVisibility(View.VISIBLE)
            self._bubble_until = now + 2.8
            self._on_bubble_resized()
        except Exception as e:
            CLOG.log_error("STATUS", "Status bubble error", e)

    def _hide_bubble(self):
        if self._bubble is None or not self._bubble_visible:
            return
        if self._handler is not None and self._grad_anim_r is not None:
            self._handler.removeCallbacks(self._grad_anim_r)
        self._bubble_visible = False
        self._bubble_gen += 1
        gen = self._bubble_gen
        bubble = self._bubble

        def _gone():
            if gen == self._bubble_gen and bubble is not None:
                bubble.setVisibility(View.GONE)

        anim = bubble.animate().alpha(0.0).setDuration(180)
        anim.withEndAction(R(_gone))
        anim.start()
