"""Yerel web arayüzü. Yalnızca 127.0.0.1'e bağlanır."""
import base64
import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import ai, extras, google, organize, tools

HOST, PORT = "127.0.0.1", 8765
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
MAX_BODY = 8 * 1024 * 1024
STATIC = Path(__file__).resolve().parent / "static"
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
SETTABLE = {"GITHUB_TOKEN", "JARVIS_CITY"}

chat = ai.Chat()
lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    server_version = "Jarvis"

    def log_message(self, *args):  # sessiz
        pass

    # -- yardımcılar --
    def _host_ok(self) -> bool:
        return self.headers.get("Host", "") in ALLOWED_HOSTS

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        return origin is None or origin in {f"http://{h}" for h in ALLOWED_HOSTS}

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self' data: blob:")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: dict):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("İstek çok büyük.")
        return json.loads(self.rfile.read(n) or b"{}")

    # -- yollar --
    def do_GET(self):
        if not self._host_ok():
            return self._json(403, {"error": "yasak"})
        if self.path in ("/", "/index.html"):
            return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if self.path == "/api/status":
            return self._json(200, {
                "key_set": bool(ai.load_key()), "model": ai.model_name(),
                "google": {"credentials": google.find_client_file() is not None,
                           "connected": google.connected(), **google.flow},
                "github": bool(ai.setting("GITHUB_TOKEN")),
                "city": ai.setting("JARVIS_CITY"),
            })
        self._json(404, {"error": "yok"})

    def do_POST(self):
        if not (self._host_ok() and self._origin_ok()):
            return self._json(403, {"error": "yasak"})
        try:
            data = self._body()
        except (ValueError, json.JSONDecodeError) as exc:
            return self._json(400, {"error": str(exc)})

        try:
            if self.path == "/api/chat":
                return self._chat(data)
            if self.path == "/api/reset":
                with lock:
                    chat.reset()
                return self._json(200, {"ok": True})
            if self.path == "/api/setkey":
                return self._setkey(data)
            if self.path == "/api/google/connect":
                google.open_auth()
                return self._json(200, {"ok": True})
            if self.path == "/api/google/disconnect":
                google.disconnect()
                return self._json(200, {"ok": True})
            if self.path == "/api/setting":
                return self._setting(data)
            if self.path == "/api/organize/preview":
                return self._json(200, tools.preview_organize())
            if self.path == "/api/organize/apply":
                return self._organize_apply()
            if self.path == "/api/organize/undo":
                n = organize.undo()
                return self._json(200, {"text": "Geri alınacak kayıt yok." if n < 0 else f"{n} dosya eski yerine taşındı."})
        except (ai.AIError, google.GoogleError, extras.ExtraError) as exc:
            return self._json(200, {"error": str(exc)})
        except Exception as exc:
            return self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
        self._json(404, {"error": "yok"})

    def _chat(self, data: dict):
        text = str(data.get("message") or "").strip()
        image = None
        if data.get("image"):
            mime = data["image"].get("mime")
            raw = data["image"].get("data", "")
            if mime not in ALLOWED_MIME:
                raise ai.AIError("Yalnızca JPEG, PNG veya WebP resim gönderilebilir.")
            base64.b64decode(raw, validate=True)
            image = {"mime": mime, "data": raw}
        if not text and not image:
            raise ai.AIError("Boş mesaj.")
        with lock:
            answer = chat.send(text, image)
        self._json(200, {"answer": answer})

    def _setkey(self, data: dict):
        key = str(data.get("key") or "").strip()
        if not (20 <= len(key) <= 200) or any(c.isspace() for c in key):
            raise ai.AIError("Anahtar biçimi geçersiz görünüyor.")
        ai.verify_key(key)  # kaydetmeden önce gerçekten çalıştığını doğrula
        ai.save_key(key)
        self._json(200, {"ok": True})

    def _setting(self, data: dict):
        name, value = str(data.get("name") or ""), str(data.get("value") or "").strip()
        if name not in SETTABLE:
            raise ai.AIError("Bu ayar değiştirilemez.")
        if not value or len(value) > 200 or any(c in value for c in "\r\n"):
            raise ai.AIError("Değer geçersiz.")
        if name == "GITHUB_TOKEN":
            user = extras.github_user(value)  # kaydetmeden önce doğrula
            ai.save_setting(name, value)
            return self._json(200, {"ok": True, "info": f"GitHub: {user}"})
        if name == "JARVIS_CITY":
            extras.hava_durumu(value)  # şehir gerçekten bulunuyor mu
        ai.save_setting(name, value)
        self._json(200, {"ok": True})

    def _organize_apply(self):
        folder = organize.default_downloads()
        moves = organize.plan(folder)
        done = organize.apply(moves) if moves else []
        self._json(200, {"text": f"{len(done)} dosya taşındı. Geri almak için 'Geri al' düğmesini kullan."})


class ExclusiveServer(ThreadingHTTPServer):
    allow_reuse_address = False  # Windows'ta aynı porta ikinci sunucunun sessizce bağlanmasını engeller


def main():
    try:
        srv = ExclusiveServer((HOST, PORT), Handler)
    except OSError:
        raise SystemExit(f"Port {PORT} zaten kullanımda. Jarvis başka bir pencerede açık olabilir: onu kapatıp yeniden başlat.")
    url = f"http://localhost:{PORT}"
    print(f"Jarvis çalışıyor: {url}  (durdurmak için Ctrl+C)")
    try:
        if not os.environ.get("JARVIS_NO_BROWSER"):
            webbrowser.open(url)
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
