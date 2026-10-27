import argparse
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from . import organize
from .db import connect
from .timeparse import parse_when

ISO = "%Y-%m-%d %H:%M"
LOG_KINDS = {
    "su": ("ml", "Su"),
    "uyku": ("saat", "Uyku"),
    "spor": ("dk", "Spor"),
    "kalori": ("kcal", "Kalori"),
    "kilo": ("kg", "Kilo"),
}


def now_s() -> str:
    return datetime.now().strftime(ISO)


# ---- komutlar ---------------------------------------------------------------

def cmd_note(a):
    db = connect()
    if a.action == "ekle":
        db.execute("INSERT INTO notes(ts, text) VALUES (?, ?)", (now_s(), " ".join(a.text)))
        db.commit()
        print("Not kaydedildi.")
    else:
        for r in db.execute("SELECT * FROM notes ORDER BY id DESC LIMIT ?", (a.limit,)):
            print(f"#{r['id']}  {r['ts']}  {r['text']}")


def cmd_remind(a):
    db = connect()
    if a.action == "ekle":
        due = parse_when(a.when)
        db.execute("INSERT INTO reminders(due, text) VALUES (?, ?)", (due.strftime(ISO), " ".join(a.text)))
        db.commit()
        print(f"Hatırlatıcı eklendi: {due.strftime(ISO)}")
    elif a.action == "bitti":
        db.execute("UPDATE reminders SET done=1 WHERE id=?", (a.id,))
        db.commit()
        print("Tamamlandı olarak işaretlendi.")
    else:
        for r in db.execute("SELECT * FROM reminders WHERE done=0 ORDER BY due"):
            print(f"#{r['id']}  {r['due']}  {r['text']}")


def cmd_expense(a):
    db = connect()
    if a.action == "ekle":
        db.execute(
            "INSERT INTO expenses(ts, amount, category, note) VALUES (?, ?, ?, ?)",
            (now_s(), a.amount, a.category.lower(), " ".join(a.note)),
        )
        db.commit()
        print(f"{a.amount:.2f} TL {a.category} olarak kaydedildi.")
    else:
        month = datetime.now().strftime("%Y-%m")
        totals = defaultdict(float)
        for r in db.execute("SELECT * FROM expenses WHERE ts LIKE ?", (month + "%",)):
            totals[r["category"]] += r["amount"]
        if not totals:
            print("Bu ay harcama yok.")
            return
        for cat, tot in sorted(totals.items(), key=lambda kv: -kv[1]):
            print(f"{cat:<15}{tot:>10.2f} TL")
        print(f"{'TOPLAM':<15}{sum(totals.values()):>10.2f} TL")


def cmd_log(a):
    db = connect()
    unit, label = LOG_KINDS[a.kind]
    db.execute(
        "INSERT INTO logs(ts, kind, value, note) VALUES (?, ?, ?, ?)",
        (now_s(), a.kind, a.value, " ".join(a.note)),
    )
    db.commit()
    print(f"{label}: {a.value:g} {unit} kaydedildi.")


def cmd_goal(a):
    db = connect()
    if a.action == "ekle":
        db.execute("INSERT INTO goals(created, text) VALUES (?, ?)", (now_s(), " ".join(a.text)))
        db.commit()
        print("Hedef eklendi.")
    elif a.action == "bitti":
        db.execute("UPDATE goals SET done=1 WHERE id=?", (a.id,))
        db.commit()
        print("Hedef tamamlandı.")
    else:
        for r in db.execute("SELECT * FROM goals ORDER BY done, id"):
            print(f"#{r['id']}  [{'x' if r['done'] else ' '}]  {r['text']}")


def _log_totals(db, since: str) -> dict:
    out = defaultdict(float)
    for r in db.execute("SELECT kind, value FROM logs WHERE ts >= ?", (since,)):
        out[r["kind"]] += r["value"] or 0
    return out


def cmd_today(_a):
    db = connect()
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    print(f"=== Bugün · {today} ===\n")

    end_of_day = now.strftime("%Y-%m-%d 23:59")
    rows = db.execute(
        "SELECT * FROM reminders WHERE done=0 AND due <= ? ORDER BY due", (end_of_day,)
    ).fetchall()
    print("Hatırlatıcılar")
    if not rows:
        print("  (yok)")
    for r in rows:
        late = " (GECİKMİŞ)" if r["due"] < now.strftime(ISO) else ""
        print(f"  #{r['id']} {r['due'][11:]}  {r['text']}{late}")

    print("\nBugünkü kayıtlar")
    totals = _log_totals(db, today)
    for kind, (unit, label) in LOG_KINDS.items():
        if kind in totals:
            print(f"  {label}: {totals[kind]:g} {unit}")
    if not totals:
        print("  (yok)")

    spent = db.execute("SELECT COALESCE(SUM(amount),0) s FROM expenses WHERE ts >= ?", (today,)).fetchone()["s"]
    print(f"\nBugünkü harcama: {spent:.2f} TL")

    goals = db.execute("SELECT * FROM goals WHERE done=0 ORDER BY id").fetchall()
    if goals:
        print("\nAçık hedefler")
        for g in goals:
            print(f"  #{g['id']} {g['text']}")


def cmd_week(_a):
    db = connect()
    since_dt = datetime.now() - timedelta(days=7)
    since = since_dt.strftime("%Y-%m-%d")
    print(f"=== Haftalık özet · {since} → bugün ===\n")

    by_kind: dict[str, list[float]] = defaultdict(list)
    for r in db.execute("SELECT substr(ts,1,10) d, kind, SUM(value) v FROM logs WHERE ts >= ? GROUP BY d, kind", (since,)):
        by_kind[r["kind"]].append(r["v"] or 0)
    for kind, (unit, label) in LOG_KINDS.items():
        vals = by_kind.get(kind)
        if vals:
            print(f"{label}: {len(vals)} gün kayıt, günlük ort. {sum(vals)/len(vals):.1f} {unit}")
    if not by_kind:
        print("Sağlık kaydı yok.")

    total = db.execute("SELECT COALESCE(SUM(amount),0) s FROM expenses WHERE ts >= ?", (since,)).fetchone()["s"]
    print(f"\nHarcama (7 gün): {total:.2f} TL")

    done = db.execute("SELECT COUNT(*) c FROM reminders WHERE done=1").fetchone()["c"]
    open_ = db.execute("SELECT COUNT(*) c FROM reminders WHERE done=0").fetchone()["c"]
    print(f"Hatırlatıcılar: {done} tamamlandı, {open_} açık")

    goals = db.execute("SELECT * FROM goals ORDER BY done, id").fetchall()
    if goals:
        n_done = sum(1 for g in goals if g["done"])
        print(f"\nHedefler: {n_done}/{len(goals)} tamamlandı")
        for g in goals:
            print(f"  [{'x' if g['done'] else ' '}] {g['text']}")


def cmd_organize(a):
    if a.undo:
        n = organize.undo()
        print("Geri alınacak kayıt yok." if n < 0 else f"{n} dosya eski yerine taşındı.")
        return
    folder = Path(a.folder) if a.folder else organize.default_downloads()
    if not folder.is_dir():
        sys.exit(f"Klasör yok: {folder}")
    moves = organize.plan(folder)
    if not moves:
        print("Taşınacak dosya yok (son 1 saatte inenler atlanır).")
        return
    print(f"{len(moves)} dosya taşınacak ({folder}):")
    for src, dest in moves:
        print(f"  {src.name}  →  {dest.parent.relative_to(folder)}")
    if not a.apply:
        print("\nKURU ÇALIŞTIRMA: hiçbir şey taşınmadı. Uygulamak için --apply ekle.")
        return
    done = organize.apply(moves)
    print(f"\n{len(done)} dosya taşındı. Geri almak için: jarvis organize --undo")


# ---- ayrıştırıcı ------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jarvis", description="Kişisel asistan")
    sub = p.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("not", help="not defteri")
    n.add_argument("action", choices=["ekle", "liste"])
    n.add_argument("text", nargs="*")
    n.add_argument("--limit", type=int, default=20)
    n.set_defaults(fn=cmd_note)

    r = sub.add_parser("hatirlat", help="hatırlatıcılar")
    r.add_argument("action", choices=["ekle", "liste", "bitti"])
    r.add_argument("text", nargs="*")
    r.add_argument("--when", "-w", default="yarın 09:00")
    r.add_argument("--id", type=int)
    r.set_defaults(fn=cmd_remind)

    e = sub.add_parser("harcama", help="harcama takibi")
    e.add_argument("action", choices=["ekle", "ozet"])
    e.add_argument("amount", type=float, nargs="?")
    e.add_argument("category", nargs="?", default="diger")
    e.add_argument("note", nargs="*")
    e.set_defaults(fn=cmd_expense)

    l = sub.add_parser("kayit", help="su / uyku / spor / kalori / kilo")
    l.add_argument("kind", choices=list(LOG_KINDS))
    l.add_argument("value", type=float)
    l.add_argument("note", nargs="*")
    l.set_defaults(fn=cmd_log)

    g = sub.add_parser("hedef", help="kariyer ve öğrenme hedefleri")
    g.add_argument("action", choices=["ekle", "liste", "bitti"])
    g.add_argument("text", nargs="*")
    g.add_argument("--id", type=int)
    g.set_defaults(fn=cmd_goal)

    sub.add_parser("bugun", help="günlük özet").set_defaults(fn=cmd_today)
    sub.add_parser("hafta", help="haftalık özet").set_defaults(fn=cmd_week)

    o = sub.add_parser("organize", help="İndirilenler düzenleyici (varsayılan kuru çalıştırma)")
    o.add_argument("--folder")
    o.add_argument("--apply", action="store_true")
    o.add_argument("--undo", action="store_true")
    o.set_defaults(fn=cmd_organize)
    return p


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    p = build_parser()
    a = p.parse_args(argv)
    if a.cmd == "harcama" and a.action == "ekle" and a.amount is None:
        p.error("harcama ekle <tutar> <kategori> [not]")
    if a.cmd in ("not", "hatirlat", "hedef") and a.action == "ekle" and not a.text:
        p.error("metin gerekli")
    if a.cmd in ("hatirlat", "hedef") and a.action == "bitti" and a.id is None:
        p.error("--id gerekli")
    try:
        a.fn(a)
    except ValueError as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
