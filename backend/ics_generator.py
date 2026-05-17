import logging
import os
import json
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from icalendar import Alarm, Calendar, Event
from cycle_config import calculate_extraction_window
from peru_holidays import get_national_holidays_from
from scraper import ClassEvent
from credential_security import get_local_credential

TZ = ZoneInfo("America/Lima")
logger = logging.getLogger(__name__)

def _next_weekday(start: date, weekday: int) -> date:
    days_ahead = (weekday - start.weekday()) % 7
    return start + timedelta(days=days_ahead)

def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(hour=int(hour), minute=int(minute))

def _sanitize_filename_part(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return safe.strip("._-") or "alumno"

def _resolve_output_filename() -> str:
    username = get_local_credential("UNI_USERNAME", required=False, default="").strip()
    if not username:
        return "horario.ics"
    return f"horario_{_sanitize_filename_part(username)}.ics"

def _get_settings() -> dict:
    try:
        local_app_data = os.getenv('LOCALAPPDATA')
        if not local_app_data: return {}
        profiles_path = Path(local_app_data) / "UTPCalendar" / "local_profiles.json"
        with open(profiles_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("Settings", data.get("settings", {}))
    except Exception:
        return {}

def _resolve_window() -> tuple[date, date]:
    today = datetime.now(TZ).date()
    settings = _get_settings()
    return calculate_extraction_window(settings, today)

def build_calendar(events: list[ClassEvent], window_start: date, window_end: date) -> Calendar:
    cal = Calendar()
    cal.add("prodid", "-//UTP Calendar Scraper//ES")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", "Horario UTP")
    
    try:
        national_holidays = get_national_holidays_from(window_start)
    except Exception:
        national_holidays = {}

    for item in events:
        class_day = item.class_date or _next_weekday(window_start, item.weekday())
        if class_day < window_start or class_day > window_end or class_day in national_holidays:
            continue

        start_dt = datetime.combine(class_day, _parse_hhmm(item.start_time), TZ)
        end_dt = datetime.combine(class_day, _parse_hhmm(item.end_time), TZ)
        if end_dt <= start_dt: end_dt += timedelta(days=1)

        event = Event()
        event.add("summary", item.course)
        event.add("location", item.room)
        event.add("dtstart", start_dt)
        event.add("dtend", end_dt)
        cal.add_component(event)

    return cal

def write_calendar(events: list[ClassEvent]) -> str:
    app_data = os.getenv('LOCALAPPDATA')
    output_dir_path = Path(app_data) / "UTPCalendar" / "data"
    output_dir_path.mkdir(parents=True, exist_ok=True)
    
    output_path = output_dir_path / _resolve_output_filename()
    
    window_start, window_end = _resolve_window()
    calendar = build_calendar(events, window_start, window_end)
    
    with open(output_path, "wb") as f:
        f.write(calendar.to_ical())

    print(f"[Python] Archivo generado en: {output_path}", flush=True)
    return str(output_path)