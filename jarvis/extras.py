"""GitHub (salt okunur) ve hava durumu (Open-Meteo, anahtarsız)."""
import json
import urllib.error
import urllib.parse
import urllib.request

GITHUB = "https://api.github.com"
GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"

WEATHER_CODES = {
    0: "açık", 1: "çoğunlukla açık", 2: "parçalı bulutlu", 3: "kapalı", 45: "sisli", 48: "kırağılı sis",
    51: "hafif çisenti", 53: "çisenti", 55: "yoğun çisenti", 61: "hafif yağmur", 63: "yağmur", 65: "şiddetli yağmur",
    71: "hafif kar", 73: "kar", 75: "yoğun kar", 80: "hafif sağanak", 81: "sağanak", 82: "şiddetli sağanak",
    95: "gök gürültülü fırtına", 96: "dolulu fırtına", 99: "şiddetli dolulu fırtına",
}


class ExtraError(Exception):
    pass


def _get_json(url: str, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "jarvis-local", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        raise ExtraError(f"HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ExtraError(f"Bağlanılamadı: {exc.reason}") from exc


# ---- GitHub -------------------------------------------------------------------

def _gh(path: str, token: str, params: dict | None = None) -> dict:
    url = GITHUB + path + ("?" + urllib.parse.urlencode(params) if params else "")
    try:
        return _get_json(url, {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                               "X-GitHub-Api-Version": "2022-11-28"})
    except ExtraError as exc:
        if "401" in str(exc):
            raise ExtraError("GitHub token geçersiz ya da süresi dolmuş.") from exc
        raise


def github_user(token: str) -> str:
    return _gh("/user", token)["login"]


def github_ozet(token: str) -> dict:
    if not token:
        raise ExtraError("GitHub token yok. Bağlantılar bölümüne ekle.")
    queries = {
        "inceleme_bekleyen_pr": "is:open is:pr review-requested:@me archived:false",
        "acik_pr_larim": "is:open is:pr author:@me archived:false",
        "bana_atanan_issue": "is:open is:issue assignee:@me archived:false",
    }
    out = {}
    for key, q in queries.items():
        data = _gh("/search/issues", token, {"q": q, "per_page": 10, "sort": "updated"})
        out[key] = [{"repo": i["repository_url"].rsplit("/repos/", 1)[-1], "no": i["number"],
                     "baslik": i["title"][:120], "guncelleme": i["updated_at"][:10]} for i in data.get("items", [])]
    return out


# ---- Hava durumu --------------------------------------------------------------

def hava_durumu(city: str) -> dict:
    if not city:
        raise ExtraError("Şehir belirtilmemiş. Bağlantılar bölümünden şehrini ayarla.")
    geo = _get_json(GEOCODE + "?" + urllib.parse.urlencode({"name": city, "count": 1, "language": "tr"}))
    if not geo.get("results"):
        raise ExtraError(f"Şehir bulunamadı: {city}")
    g = geo["results"][0]
    f = _get_json(FORECAST + "?" + urllib.parse.urlencode({
        "latitude": g["latitude"], "longitude": g["longitude"], "timezone": "auto", "forecast_days": 1,
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code"}))
    cur, day = f["current"], f["daily"]
    return {
        "sehir": g["name"],
        "su_an": f"{cur['temperature_2m']:.0f}°C (hissedilen {cur['apparent_temperature']:.0f}°C), {WEATHER_CODES.get(cur['weather_code'], '?')}",
        "bugun": f"{day['temperature_2m_min'][0]:.0f}–{day['temperature_2m_max'][0]:.0f}°C, {WEATHER_CODES.get(day['weather_code'][0], '?')}, "
                 f"yağış ihtimali %{day['precipitation_probability_max'][0]}",
    }
