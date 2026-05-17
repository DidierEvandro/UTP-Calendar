import json
import logging
import re
import unicodedata
from datetime import date, datetime, timedelta
from cycle_config import parse_date, format_date, format_datetime
from pathlib import Path
from typing import Dict

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

FERIADOS_URL = "https://www.gob.pe/feriados"
CACHE_PATH = Path(__file__).with_name("peru_holidays_cache.json")
MONTH_MAP = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "setiembre": 9, "septiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

def _normalize_ascii(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")

def _extract_year(page_text: str, default_year: int) -> int:
    match = re.search(r"Feriados\s+(\d{4})", page_text, flags=re.IGNORECASE)
    if not match:
        return default_year
    return int(match.group(1))

def _extract_dates_from_text(value: str, year: int) -> list[date]:
    normalized = _normalize_ascii(" ".join(value.split()).lower())
    pairs = re.findall(r"(\d{1,2})\s+de\s+([a-z]+)", normalized)
    if not pairs: return []

    points: list[date] = []
    for day_text, month_text in pairs:
        month = MONTH_MAP.get(month_text)
        if month is None: continue
        points.append(date(year, month, int(day_text)))

    if not points: return []
    if len(points) == 1: return points

    start = min(points)
    end = max(points)
    total_days = (end - start).days
    if total_days <= 0: return [start]
    return [start + timedelta(days=offset) for offset in range(total_days + 1)]

def _extract_next_holiday_block(html: str, year: int) -> Dict[date, str]:
    flat_text = " ".join(BeautifulSoup(html, "html.parser").get_text(" ", strip=True).split())
    match = re.search(
        r"El siguiente feriado nacional es\s+([A-Za-zÁÉÍÓÚáéíóú]+\s+\d{1,2}\s+de\s+[a-záéíóú]+)\s+(.+?)\s+Feriado nacional",
        flat_text, flags=re.IGNORECASE,
    )
    if not match: return {}

    date_text = match.group(1)
    holiday_name = match.group(2).strip()
    holiday_name = re.split(r"\s+Tipo\s+Fecha\s+Motivo\b", holiday_name, flags=re.IGNORECASE)[0].strip()
    dates = _extract_dates_from_text(date_text, year)
    return {day: holiday_name for day in dates}

def _load_cache() -> dict:
    if not CACHE_PATH.exists(): return {"updated_at": None, "years": {}}
    try: return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception: return {"updated_at": None, "years": {}}

def _save_cache(cache: dict) -> None:
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

def _load_year_from_cache(year: int) -> Dict[date, str]:
    cache = _load_cache()
    years = cache.get("years", {})
    cached_year = years.get(str(year), {})
    
    result: Dict[date, str] = {}
    for day_text, holiday_name in cached_year.items():
        try: result[parse_date(day_text)] = holiday_name
        except Exception: continue
    return result

def _store_year_to_cache(year: int, holidays: Dict[date, str]) -> None:
    cache = _load_cache()
    years = cache.get("years", {})
    years[str(year)] = {format_date(day): name for day, name in sorted(holidays.items())}
    cache["years"] = years
    cache["updated_at"] = format_datetime(datetime.now())
    _save_cache(cache)

def _fetch_national_holidays_for_year(year: int, progress_cb=None) -> Dict[date, str]:
    msg = f"Descargando feriados desde gob.pe para {year}..."
    if progress_cb: progress_cb(30, msg)
    print(f"[Feriados] {msg}", flush=True)
    
    response = requests.get(FERIADOS_URL, timeout=10, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "es-PE,es;q=0.9"})
    response.raise_for_status()

    if progress_cb: progress_cb(60, "Analizando portal del gobierno...")
    print("[Feriados] Analizando portal del gobierno...", flush=True)
    html = response.text
    detected_year = _extract_year(html, year)
    soup = BeautifulSoup(html, "html.parser")

    result: Dict[date, str] = _extract_next_holiday_block(html, detected_year)
    for row in soup.select("tr"):
        cols = [col.get_text(" ", strip=True) for col in row.select("td")]
        if len(cols) < 3: continue
        holiday_type, date_text, holiday_name = cols[0], cols[1], cols[2]
        if "feriado nacional" not in holiday_type.lower(): continue
        for day in _extract_dates_from_text(date_text, detected_year):
            result[day] = holiday_name

    msg_done = f"Se encontraron {len(result)} feriados."
    if progress_cb: progress_cb(90, msg_done)
    print(f"[Feriados] {msg_done}", flush=True)
    return result

def _get_year_holidays(year: int, force_refresh: bool = False, progress_cb=None) -> Dict[date, str]:
    if not force_refresh:
        cached = _load_year_from_cache(year)
        if cached:
            if progress_cb: progress_cb(100, "Feriados cargados desde caché local")
            print("[Feriados] Feriados cargados desde caché local.", flush=True)
            return cached

    try:
        holidays = _fetch_national_holidays_for_year(year, progress_cb)
    except Exception as exc:
        cached = _load_year_from_cache(year)
        if cached:
            if progress_cb: progress_cb(100, "Error de red. Usando caché.")
            print(f"[Feriados] Error de red. Usando caché. Detalles: {exc}", flush=True)
            return cached
        return {}

    if holidays:
        _store_year_to_cache(year, holidays)
        if progress_cb: progress_cb(100, "Feriados actualizados correctamente.")
        print("[Feriados] Caché de feriados actualizada y guardada.", flush=True)

    return holidays

def get_national_holidays_from(date_from: date, force_refresh: bool = False) -> Dict[date, str]:
    holidays = _get_year_holidays(date_from.year, force_refresh=force_refresh)
    return {day: name for day, name in holidays.items() if day >= date_from}

def refresh_national_holidays_cache(reference_day: date | None = None, progress_cb=None) -> Dict[date, str]:
    if progress_cb: progress_cb(10, "Iniciando actualización de feriados...")
    print("[Feriados] Iniciando actualización de feriados...", flush=True)
    target_day = reference_day or date.today()
    return _get_year_holidays(target_day.year, force_refresh=True, progress_cb=progress_cb)

def get_holiday_cache_updated_at() -> str:
    cache = _load_cache()
    updated_at = cache.get("updated_at")
    if isinstance(updated_at, str) and updated_at.strip(): return updated_at
    return "Nunca"