#!/usr/bin/env python3
"""
Синхронизация общих модулей плеера (Bridge SSE/Polling, LyricsHelper, анти-дрейф,
градиентная рамка, Tap-to-Sync, масштабирование 0.4x–2.0x) между:
  - public/clawd_v3_4.py (полный плагин с питомцем)
  - public/clawd_lyrics_player.py (отдельный плагин только с текстовиком-плеером)

Использование:
  python3 scripts/sync_plugins.py              # копирует общие блоки из clawd_v3_4.py -> clawd_lyrics_player.py
  python3 scripts/sync_plugins.py --from-lyrics # копирует общие блоки из clawd_lyrics_player.py -> clawd_v3_4.py
  python3 scripts/sync_plugins.py --check       # проверяет идентичность общих блоков (exit 1 при расхождении)
"""

import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PET_PATH = os.path.join(ROOT, "public", "clawd_v3_4.py")
LYRICS_PATH = os.path.join(ROOT, "public", "clawd_lyrics_player.py")

BLOCK_NAMES = [
    "COLOR_LOGGER_PROXIES",
    "LYRICS_HELPER",
    "BRIDGE_DAEMON",
    "MEDIA_KEYS",
    "BUBBLE_SCALE_UI",
    "PLAYER_ENGINE",
]


def extract_block(text: str, name: str) -> str:
    start_tag = f"# === [SHARED_BLOCK:{name}] ==="
    end_tag = f"# === [/SHARED_BLOCK:{name}] ==="
    pattern = re.compile(re.escape(start_tag) + r"(.*?)" + re.escape(end_tag), re.DOTALL)
    m = pattern.search(text)
    if not m:
        raise RuntimeError(f"Shared block '{name}' not found")
    return m.group(1)


def replace_block(text: str, name: str, body: str) -> str:
    start_tag = f"# === [SHARED_BLOCK:{name}] ==="
    end_tag = f"# === [/SHARED_BLOCK:{name}] ==="
    pattern = re.compile(re.escape(start_tag) + r".*?" + re.escape(end_tag), re.DOTALL)
    if not pattern.search(text):
        raise RuntimeError(f"Target shared block '{name}' not found")
    return pattern.sub(lambda _m: f"{start_tag}{body}{end_tag}", text, count=1)


def main():
    parser = argparse.ArgumentParser(description="Sync shared player blocks between Clawd plugins.")
    parser.add_argument("--from-lyrics", action="store_true", help="Sync from clawd_lyrics_player.py to clawd_v3_4.py")
    parser.add_argument("--check", action="store_true", help="Check whether shared blocks match without writing")
    args = parser.parse_args()

    with open(PET_PATH, "r", encoding="utf-8") as f:
        pet_text = f.read()
    with open(LYRICS_PATH, "r", encoding="utf-8") as f:
        lyrics_text = f.read()

    if args.check:
        mismatches = []
        for name in BLOCK_NAMES:
            b_pet = extract_block(pet_text, name)
            b_lyr = extract_block(lyrics_text, name)
            if b_pet != b_lyr:
                mismatches.append(name)
        if mismatches:
            print(f"OUT OF SYNC: {', '.join(mismatches)}", file=sys.stderr)
            sys.exit(1)
        print(f"IN SYNC: {len(BLOCK_NAMES)} shared blocks match identically.")
        return

    src_text, dst_text, dst_path, direction = (
        (lyrics_text, pet_text, PET_PATH, "clawd_lyrics_player.py -> clawd_v3_4.py")
        if args.from_lyrics
        else (pet_text, lyrics_text, LYRICS_PATH, "clawd_v3_4.py -> clawd_lyrics_player.py")
    )

    updated = dst_text
    for name in BLOCK_NAMES:
        body = extract_block(src_text, name)
        updated = replace_block(updated, name, body)

    if updated != dst_text:
        with open(dst_path, "w", encoding="utf-8") as f:
            f.write(updated)
        print(f"Synced {len(BLOCK_NAMES)} shared blocks ({direction}).")
    else:
        print(f"Already up to date ({direction}).")


if __name__ == "__main__":
    main()
