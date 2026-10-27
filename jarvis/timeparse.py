import re
from datetime import datetime, timedelta

DAY_WORDS = {"bugün": 0, "bugun": 0, "yarın": 1, "yarin": 1, "öbür gün": 2, "obur gun": 2}
DEFAULT_HOUR = 9


def parse_when(text: str, now: datetime | None = None) -> datetime:
    """'yarın 09:30', 'bugün 18:00', '2026-11-01 08:00', '2026-11-01', '+3g' biçimlerini çözer."""
    now = now or datetime.now()
    s = text.strip().lower()

    m = re.fullmatch(r"\+(\d+)\s*(g|gün|gun|s|saat|d|dk)", s)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        if unit in ("g", "gün", "gun"):
            return now + timedelta(days=n)
        if unit in ("s", "saat"):
            return now + timedelta(hours=n)
        return now + timedelta(minutes=n)

    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt if fmt.endswith("%M") else dt.replace(hour=DEFAULT_HOUR)
        except ValueError:
            pass

    for word, days in sorted(DAY_WORDS.items(), key=lambda kv: -len(kv[0])):
        if s.startswith(word):
            rest = s[len(word):].strip()
            hour, minute = DEFAULT_HOUR, 0
            if rest:
                m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?", rest)
                if not m:
                    break
                hour, minute = int(m.group(1)), int(m.group(2) or 0)
            base = (now + timedelta(days=days)).replace(second=0, microsecond=0)
            return base.replace(hour=hour, minute=minute)

    raise ValueError(f"Zamanı anlayamadım: {text!r}. Örnek: 'yarın 09:30', '2026-11-01 08:00', '+3g'")
