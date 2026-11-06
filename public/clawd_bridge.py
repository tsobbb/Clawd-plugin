#!/usr/bin/env python3
"""
Clawd Bridge Service v1.3 (Reference Python Server & Emulator)
Спецификация ТЗ v1.3:
• Порт: 44444 (URL: http://127.0.0.1:44444/now-playing)
• Безопасность: Host.split(":")[0] строго 127.0.0.1 или localhost (иначе 403 Forbidden)
• Без заголовка Access-Control-Allow-Origin
• Точный таймер позиции: дельта monotonic() прибавляется строго при is_playing=True
"""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import time

STATE = {
    "has_media": True,
    "is_playing": True,
    "player": "Spotify",
    "artist": "Kai Angel",
    "title": "andy warhol",
    "duration_ms": 142000,
    "position_known": True,
    "base_position_ms": 32500,
    "base_timestamp": time.time(),
}


def get_current_position_ms() -> int:
    if not STATE["is_playing"]:
        return int(STATE["base_position_ms"])
    delta_ms = int((time.time() - STATE["base_timestamp"]) * 1000)
    pos = int(STATE["base_position_ms"] + delta_ms)
    dur = STATE["duration_ms"]
    return min(pos, dur) if dur > 0 else pos


class BridgeRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Тихий режим логов

    def do_GET(self):
        # 1. Проверка заголовка Host
        host = self.headers.get("Host", "")
        hostname = host.split(":")[0].strip().lower()
        if hostname not in ("127.0.0.1", "localhost"):
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"403 Forbidden: Invalid Host")
            return

        if self.path == "/now-playing":
            pos_ms = get_current_position_ms()
            response_payload = {
                "has_media": bool(STATE["has_media"]),
                "is_playing": bool(STATE["is_playing"]),
                "player": str(STATE["player"]),
                "artist": str(STATE["artist"]),
                "title": str(STATE["title"]),
                "position_ms": int(pos_ms),
                "duration_ms": int(STATE["duration_ms"]),
                "position_known": bool(STATE["position_known"]),
                "timestamp": int(time.time()),
            }

            body = json.dumps(response_payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            # Access-Control-Allow-Origin удален по ТЗ v1.3
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        # Эндпоинт для управления симулятором из тестов: /set-state
        host = self.headers.get("Host", "")
        hostname = host.split(":")[0].strip().lower()
        if hostname not in ("127.0.0.1", "localhost"):
            self.send_response(403)
            self.end_headers()
            return

        if self.path == "/set-state":
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            if "is_playing" in data and not data["is_playing"]:
                STATE["base_position_ms"] = get_current_position_ms()
                STATE["base_timestamp"] = time.time()
                STATE["is_playing"] = False
            elif "is_playing" in data and data["is_playing"]:
                STATE["base_timestamp"] = time.time()
                STATE["is_playing"] = True

            for k in ("has_media", "player", "artist", "title", "duration_ms", "position_known"):
                if k in data:
                    STATE[k] = data[k]
            if "position_ms" in data:
                STATE["base_position_ms"] = int(data["position_ms"])
                STATE["base_timestamp"] = time.time()

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        else:
            self.send_response(404)
            self.end_headers()


def run_server(port=44444):
    server_address = ("127.0.0.1", port)
    httpd = HTTPServer(server_address, BridgeRequestHandler)
    print(f"[Clawd Bridge v1.3] Сервер запущен на http://127.0.0.1:{port}/now-playing")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    run_server()
