"""Yapay zekanın çağırabildiği araçlar.

Güvenlik: buradaki araçların hiçbiri dosya taşımaz, silmez, mail göndermez.
İndirilenler için yalnızca önizleme vardır; taşıma sadece arayüzdeki onay
düğmesiyle (server.py) yapılır.
"""
import contextlib
import io
from collections import defaultdict
from datetime import datetime

from . import cli, extras, google, organize
from .db import connect
from .timeparse import parse_when

ISO = cli.ISO
LOG_KINDS = list(cli.LOG_KINDS)

DECLARATIONS = [
    {"name": "not_ekle", "description": "Not defterine not ekler.",
     "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "not_listele", "description": "Son notları listeler.",
     "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}}},
    {"name": "hatirlatici_ekle",
     "description": "Hatırlatıcı ekler. 'when' biçimleri: 'yarın 09:30', 'bugün 18:00', '2026-11-01 08:00', '+3g', '+2s'. "
                    "Kullanıcı göreli zaman söylediyse (örn. 'pazartesi') bunu tarihe çevirip '2026-11-02 09:00' biçiminde ver.",
     "parameters": {"type": "object", "properties": {"text": {"type": "string"}, "when": {"type": "string"}},
                    "required": ["text", "when"]}},
    {"name": "hatirlatici_listele", "description": "Açık hatırlatıcıları listeler."},
    {"name": "hatirlatici_tamamla", "description": "Hatırlatıcıyı id ile tamamlandı işaretler.",
     "parameters": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]}},
    {"name": "harcama_ekle", "description": "Harcama kaydeder (TL). Kategori küçük harfli tek kelime: market, ulasim, yemek, fatura, eglence, saglik, giyim, diger.",
     "parameters": {"type": "object", "properties": {
         "amount": {"type": "number"}, "category": {"type": "string"}, "note": {"type": "string"}},
         "required": ["amount", "category"]}},
    {"name": "harcama_ozet", "description": "Bu ayın harcamalarını kategoriye göre özetler."},
    {"name": "saglik_kaydet",
     "description": "Sağlık kaydı ekler. kind: su (ml), uyku (saat), spor (dk), kalori (kcal), kilo (kg). "
                    "Kalori kaydını yalnızca kullanıcı onayladıktan sonra yap.",
     "parameters": {"type": "object", "properties": {
         "kind": {"type": "string", "enum": LOG_KINDS}, "value": {"type": "number"}, "note": {"type": "string"}},
         "required": ["kind", "value"]}},
    {"name": "hedef_ekle", "description": "Kariyer/öğrenme hedefi ekler.",
     "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "hedef_listele", "description": "Hedefleri listeler."},
    {"name": "hedef_tamamla", "description": "Hedefi id ile tamamlandı işaretler.",
     "parameters": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]}},
    {"name": "bugun_ozet", "description": "Günün özetini verir: hatırlatıcılar, kayıtlar, harcama, açık hedefler."},
    {"name": "hafta_ozet", "description": "Son 7 günün özetini verir."},
    {"name": "mail_ozet",
     "description": "Gmail'den mail özeti (gönderen, konu, kısa önizleme). SALT OKUNUR. Varsayılan: son 3 günün okunmamış, promosyon olmayan mailleri. "
                    "query Gmail arama sözdizimidir (ör. 'is:unread is:important', 'from:biri@x.com newer_than:7d').",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer"}}}},
    {"name": "takvim_listele",
     "description": "Google Takvim etkinliklerini listeler (bugünden itibaren 'days' gün). SALT OKUNUR.",
     "parameters": {"type": "object", "properties": {"days": {"type": "integer"}}}},
    {"name": "github_ozet",
     "description": "GitHub: inceleme bekleyen PR'lar, açık PR'larım, bana atanan issue'lar. SALT OKUNUR."},
    {"name": "hava_durumu",
     "description": "Bugünkü hava durumu. city verilmezse ayarlardaki şehir kullanılır.",
     "parameters": {"type": "object", "properties": {"city": {"type": "string"}}}},
    {"name": "indirilenler_onizle",
     "description": "İndirilenler klasörünü düzenleme ÖNİZLEMESİ. Hiçbir dosyayı taşımaz. Taşımayı kullanıcı arayüzdeki düğmeyle yapar.",
     },
]


def _capture(fn) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(None)
    return buf.getvalue().strip()


def run(name: str, args: dict) -> dict:
    """Aracı çalıştırır, modele dönecek sözlüğü verir. Hata fırlatmaz."""
    try:
        return {"result": _dispatch(name, args or {})}
    except Exception as exc:  # modele hatayı anlat, sunucuyu düşürme
        return {"error": f"{type(exc).__name__}: {exc}"}


def _dispatch(name: str, a: dict):
    db = connect()
    now = datetime.now().strftime(ISO)

    if name == "not_ekle":
        db.execute("INSERT INTO notes(ts, text) VALUES (?, ?)", (now, str(a["text"])))
        db.commit()
        return "Not kaydedildi."
    if name == "not_listele":
        rows = db.execute("SELECT * FROM notes ORDER BY id DESC LIMIT ?", (int(a.get("limit") or 10),)).fetchall()
        return [f"#{r['id']} {r['ts']} {r['text']}" for r in rows] or "Not yok."

    if name == "hatirlatici_ekle":
        due = parse_when(str(a["when"]))
        db.execute("INSERT INTO reminders(due, text) VALUES (?, ?)", (due.strftime(ISO), str(a["text"])))
        db.commit()
        return f"Hatırlatıcı eklendi: {due.strftime(ISO)}"
    if name == "hatirlatici_listele":
        rows = db.execute("SELECT * FROM reminders WHERE done=0 ORDER BY due").fetchall()
        return [f"#{r['id']} {r['due']} {r['text']}" for r in rows] or "Açık hatırlatıcı yok."
    if name == "hatirlatici_tamamla":
        cur = db.execute("UPDATE reminders SET done=1 WHERE id=?", (int(a["id"]),))
        db.commit()
        return "Tamamlandı." if cur.rowcount else "Böyle bir hatırlatıcı yok."

    if name == "harcama_ekle":
        amount = float(a["amount"])
        if amount <= 0:
            raise ValueError("tutar pozitif olmalı")
        db.execute("INSERT INTO expenses(ts, amount, category, note) VALUES (?, ?, ?, ?)",
                   (now, amount, str(a["category"]).lower(), str(a.get("note") or "")))
        db.commit()
        return f"{amount:.2f} TL {a['category']} kaydedildi."
    if name == "harcama_ozet":
        totals = defaultdict(float)
        for r in db.execute("SELECT category, amount FROM expenses WHERE ts LIKE ?", (now[:7] + "%",)):
            totals[r["category"]] += r["amount"]
        if not totals:
            return "Bu ay harcama yok."
        out = {k: round(v, 2) for k, v in sorted(totals.items(), key=lambda kv: -kv[1])}
        out["TOPLAM"] = round(sum(totals.values()), 2)
        return out

    if name == "saglik_kaydet":
        kind = str(a["kind"])
        if kind not in cli.LOG_KINDS:
            raise ValueError(f"bilinmeyen tür: {kind}")
        db.execute("INSERT INTO logs(ts, kind, value, note) VALUES (?, ?, ?, ?)",
                   (now, kind, float(a["value"]), str(a.get("note") or "")))
        db.commit()
        unit, label = cli.LOG_KINDS[kind]
        return f"{label}: {float(a['value']):g} {unit} kaydedildi."

    if name == "hedef_ekle":
        db.execute("INSERT INTO goals(created, text) VALUES (?, ?)", (now, str(a["text"])))
        db.commit()
        return "Hedef eklendi."
    if name == "hedef_listele":
        rows = db.execute("SELECT * FROM goals ORDER BY done, id").fetchall()
        return [f"#{r['id']} [{'x' if r['done'] else ' '}] {r['text']}" for r in rows] or "Hedef yok."
    if name == "hedef_tamamla":
        cur = db.execute("UPDATE goals SET done=1 WHERE id=?", (int(a["id"]),))
        db.commit()
        return "Hedef tamamlandı." if cur.rowcount else "Böyle bir hedef yok."

    if name == "bugun_ozet":
        return _capture(cli.cmd_today)
    if name == "hafta_ozet":
        return _capture(cli.cmd_week)

    if name == "indirilenler_onizle":
        return preview_organize()["text"]

    if name == "mail_ozet":
        return google.mail_ozet(str(a.get("query") or ""), int(a.get("max_results") or 15)) or "Eşleşen mail yok."
    if name == "takvim_listele":
        return google.takvim_listele(int(a.get("days") or 1)) or "Bu aralıkta etkinlik yok."
    if name == "github_ozet":
        from . import ai
        return extras.github_ozet(ai.setting("GITHUB_TOKEN"))
    if name == "hava_durumu":
        from . import ai
        return extras.hava_durumu(str(a.get("city") or "") or ai.setting("JARVIS_CITY"))

    raise ValueError(f"bilinmeyen araç: {name}")


def preview_organize() -> dict:
    folder = organize.default_downloads()
    if not folder.is_dir():
        return {"count": 0, "text": f"Klasör bulunamadı: {folder}"}
    moves = organize.plan(folder)
    if not moves:
        return {"count": 0, "text": "Taşınacak dosya yok (son 1 saatte inenler atlanır)."}
    lines = [f"{len(moves)} dosya taşınacak. Henüz hiçbir şey taşınmadı."]
    lines += [f"{src.name} → {dest.parent.name}" for src, dest in moves[:40]]
    if len(moves) > 40:
        lines.append(f"... ve {len(moves) - 40} dosya daha")
    return {"count": len(moves), "text": "\n".join(lines)}
