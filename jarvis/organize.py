"""İndirilenler klasörünü kategorilere ayırır. Hiçbir şey silmez, sadece taşır.

Varsayılan kuru çalıştırmadır; --apply verilmeden dosyaya dokunulmaz.
Her uygulama bir geri alma kaydı yazar (jarvis organize --undo).
"""
import json
import shutil
import time
from datetime import datetime
from pathlib import Path

from .db import ROOT

CATEGORIES = {
    "Belgeler": {".pdf", ".doc", ".docx", ".txt", ".odt", ".rtf", ".md", ".epub"},
    "Tablolar": {".xls", ".xlsx", ".csv", ".ods"},
    "Sunumlar": {".ppt", ".pptx", ".key", ".odp"},
    "Resimler": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".heic"},
    "Videolar": {".mp4", ".mkv", ".mov", ".avi", ".webm"},
    "Muzik": {".mp3", ".wav", ".flac", ".m4a", ".ogg"},
    "Arsivler": {".zip", ".rar", ".7z", ".tar", ".gz"},
    "Kurulumlar": {".exe", ".msi", ".msix", ".dmg", ".apk"},
    "Kod": {".py", ".js", ".ts", ".json", ".html", ".css", ".ipynb", ".sql"},
}
TARGET = "_Duzenli"
SKIP_SUFFIXES = {".crdownload", ".part", ".tmp", ".partial", ".download"}
MIN_AGE_SECONDS = 3600  # yeni inen / hâlâ inen dosyalara dokunma
UNDO_LOG = ROOT / "data" / "organize_undo.json"


def default_downloads() -> Path:
    return Path.home() / "Downloads"


def category_of(path: Path) -> str:
    ext = path.suffix.lower()
    for name, exts in CATEGORIES.items():
        if ext in exts:
            return name
    return "Diger"


def plan(folder: Path) -> list[tuple[Path, Path]]:
    moves = []
    now = time.time()
    for item in sorted(folder.iterdir()):
        if not item.is_file() or item.name.startswith(".") or item.name == "desktop.ini":
            continue
        if item.suffix.lower() in SKIP_SUFFIXES:
            continue
        if now - item.stat().st_mtime < MIN_AGE_SECONDS:
            continue
        dest = folder / TARGET / category_of(item) / item.name
        moves.append((item, dest))
    return moves


def _free_name(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem, suffix, n = dest.stem, dest.suffix, 1
    while True:
        candidate = dest.with_name(f"{stem} ({n}){suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def apply(moves: list[tuple[Path, Path]]) -> list[dict]:
    done = []
    for src, dest in moves:
        dest.parent.mkdir(parents=True, exist_ok=True)
        final = _free_name(dest)
        shutil.move(str(src), str(final))
        done.append({"from": str(src), "to": str(final)})
    UNDO_LOG.parent.mkdir(parents=True, exist_ok=True)
    UNDO_LOG.write_text(
        json.dumps({"at": datetime.now().isoformat(timespec="seconds"), "moves": done},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return done


def undo() -> int:
    if not UNDO_LOG.exists():
        return -1
    data = json.loads(UNDO_LOG.read_text(encoding="utf-8"))
    restored = 0
    for mv in reversed(data["moves"]):
        src, dst = Path(mv["to"]), Path(mv["from"])
        if src.exists() and not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            restored += 1
    UNDO_LOG.unlink()
    return restored
