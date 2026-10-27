"""Google OAuth (yalnızca okuma) + Gmail + Takvim. Yalnızca standart kütüphane.

İzinler salt okunurdur: mail göndermek, silmek ya da takvime yazmak mümkün değildir.
Yetki dosyası: credentials.json (ya da Google'ın verdiği client_secret*.json) proje klasöründe.
Token: data/google_token.json (gitignore içinde).
"""
import base64
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

from .db import ROOT

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.events.readonly",
]
TOKEN_FILE = ROOT / "data" / "google_token.json"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
CALENDAR = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
FLOW_TIMEOUT = 180

flow = {"state": "idle", "msg": ""}  # idle | waiting | done | error
_flow_lock = threading.Lock()


class GoogleError(Exception):
    pass


def find_client_file():
    for pattern in ("credentials*.json", "client_secret*.json"):
        found = sorted(ROOT.glob(pattern))
        if found:
            return found[0]
    return None


def _client() -> dict:
    path = find_client_file()
    if not path:
        raise GoogleError("credentials.json bulunamadı. Google Cloud'dan indirdiğin JSON dosyasını proje klasörüne koy.")
    data = json.loads(path.read_text(encoding="utf-8"))
    c = data.get("installed") or data.get("web")
    if not c or "client_id" not in c:
        raise GoogleError("credentials.json biçimi geçersiz. 'Masaüstü uygulaması' (Desktop app) türünde bir istemci oluştur.")
    return c


def connected() -> bool:
    return TOKEN_FILE.exists()


def _save_token(tok: dict, old_refresh: str | None = None):
    data = {
        "access_token": tok["access_token"],
        "refresh_token": tok.get("refresh_token") or old_refresh,
        "expires_at": time.time() + int(tok.get("expires_in", 3600)) - 60,
        "scope": tok.get("scope", ""),
    }
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(data), encoding="utf-8")
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass


def _form_post(url: str, form: dict) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(form).encode(), method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        try:
            err = json.loads(exc.read().decode())
        except Exception:
            err = {}
        if err.get("error") == "invalid_grant":
            raise GoogleError("Google bağlantının süresi dolmuş ya da iptal edilmiş. Bağlantılar'dan Google'ı yeniden bağla.") from exc
        raise GoogleError(f"Google yetkilendirme hatası: {err.get('error_description') or err.get('error') or exc.code}") from exc
    except urllib.error.URLError as exc:
        raise GoogleError(f"Google'a bağlanılamadı: {exc.reason}") from exc


def _access_token() -> str:
    if not TOKEN_FILE.exists():
        raise GoogleError("Google bağlı değil. Bağlantılar bölümünden bağla.")
    tok = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    if time.time() < tok["expires_at"]:
        return tok["access_token"]
    if not tok.get("refresh_token"):
        raise GoogleError("Yenileme anahtarı yok. Google'ı yeniden bağla.")
    c = _client()
    new = _form_post(c.get("token_uri", "https://oauth2.googleapis.com/token"), {
        "client_id": c["client_id"], "client_secret": c.get("client_secret", ""),
        "refresh_token": tok["refresh_token"], "grant_type": "refresh_token"})
    _save_token(new, tok["refresh_token"])
    return new["access_token"]


def _get(url: str, params: dict | None = None) -> dict:
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {_access_token()}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise GoogleError("Google erişimi reddetti. İzin vermediysen ya da API kapalıysa (Gmail API / Calendar API) bu hata çıkar.") from exc
        raise GoogleError(f"Google hatası ({exc.code})") from exc
    except urllib.error.URLError as exc:
        raise GoogleError(f"Google'a bağlanılamadı: {exc.reason}") from exc


# ---- OAuth akışı (PKCE, 127.0.0.1 geri dönüşü) ---------------------------------

def start_auth() -> str:
    """Tarayıcıda açılacak izin adresini döndürür; geri dönüşü arka planda bekler."""
    c = _client()
    with _flow_lock:
        if flow["state"] == "waiting":
            raise GoogleError("Bağlantı zaten bekleniyor. Açılan Google sekmesini tamamla.")
        flow.update(state="waiting", msg="")

    verifier = base64.urlsafe_b64encode(os.urandom(48)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    result = {}

    class CB(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" not in q and "error" not in q:
                self.send_response(404); self.end_headers(); return
            result.update({k: v[0] for k, v in q.items()})
            body = "<meta charset=utf-8><body style='font-family:system-ui;padding:2rem'><h2>Tamam</h2><p>Bu sekmeyi kapatıp Jarvis'e dönebilirsin.</p>".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    httpd = HTTPServer(("127.0.0.1", 0), CB)
    httpd.timeout = FLOW_TIMEOUT
    redirect = f"http://127.0.0.1:{httpd.server_port}"
    url = c.get("auth_uri", "https://accounts.google.com/o/oauth2/v2/auth") + "?" + urllib.parse.urlencode({
        "client_id": c["client_id"], "redirect_uri": redirect, "response_type": "code",
        "scope": " ".join(SCOPES), "code_challenge": challenge, "code_challenge_method": "S256",
        "state": state, "access_type": "offline", "prompt": "consent"})

    def finish():
        try:
            deadline = time.time() + FLOW_TIMEOUT
            while not result and time.time() < deadline:
                httpd.handle_request()
            if not result:
                raise GoogleError("Zaman aşımı: izin verilmedi.")
            if result.get("error"):
                raise GoogleError(f"İzin verilmedi ({result['error']}).")
            if not secrets.compare_digest(result.get("state", ""), state):
                raise GoogleError("Güvenlik doğrulaması (state) uyuşmadı, işlem iptal edildi.")
            tok = _form_post(c.get("token_uri", "https://oauth2.googleapis.com/token"), {
                "code": result["code"], "client_id": c["client_id"], "client_secret": c.get("client_secret", ""),
                "redirect_uri": redirect, "grant_type": "authorization_code", "code_verifier": verifier})
            granted = tok.get("scope", "")
            missing = [s.rsplit("/", 1)[-1] for s in SCOPES if s not in granted]
            if missing:
                raise GoogleError("Şu izinler verilmedi: " + ", ".join(missing) + ". İzin ekranında hepsini işaretle.")
            _save_token(tok)
            flow.update(state="done", msg="")
        except GoogleError as exc:
            flow.update(state="error", msg=str(exc))
        except Exception as exc:
            flow.update(state="error", msg=f"{type(exc).__name__}: {exc}")
        finally:
            httpd.server_close()

    threading.Thread(target=finish, daemon=True).start()
    return url


def open_auth() -> str:
    url = start_auth()
    webbrowser.open(url)
    return url


def disconnect():
    TOKEN_FILE.unlink(missing_ok=True)
    flow.update(state="idle", msg="")


# ---- Gmail --------------------------------------------------------------------

DEFAULT_MAIL_QUERY = "is:unread newer_than:3d -category:promotions -category:social"


def _header(msg: dict, name: str) -> str:
    for h in msg.get("payload", {}).get("headers", []):
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def mail_ozet(query: str = "", max_results: int = 15) -> list[dict]:
    max_results = max(1, min(int(max_results or 15), 30))
    listing = _get(f"{GMAIL}/messages", {"q": query or DEFAULT_MAIL_QUERY, "maxResults": max_results})
    snippets = os.environ.get("JARVIS_MAIL_SNIPPETS", "1") != "0"
    out = []
    for m in listing.get("messages", []):
        full = _get(f"{GMAIL}/messages/{m['id']}", {"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]})
        item = {
            "from": _header(full, "From")[:120],
            "subject": _header(full, "Subject")[:150],
            "date": _header(full, "Date"),
            "important": "IMPORTANT" in full.get("labelIds", []),
        }
        if snippets:
            item["snippet"] = (full.get("snippet") or "")[:120]
        out.append(item)
    return out


# ---- Takvim -------------------------------------------------------------------

def takvim_listele(days: int = 1) -> list[dict]:
    days = max(1, min(int(days or 1), 14))
    now = datetime.now().astimezone()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    data = _get(CALENDAR, {
        "timeMin": start.isoformat(), "timeMax": (start + timedelta(days=days)).isoformat(),
        "singleEvents": "true", "orderBy": "startTime", "maxResults": 30})
    out = []
    for e in data.get("items", []):
        s, en = e.get("start", {}), e.get("end", {})
        out.append({
            "title": (e.get("summary") or "(başlıksız)")[:120],
            "start": s.get("dateTime") or s.get("date"),
            "end": en.get("dateTime") or en.get("date"),
            "all_day": "date" in s,
            "location": (e.get("location") or "")[:100],
        })
    return out
