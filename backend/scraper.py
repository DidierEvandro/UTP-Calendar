import os
_appdata = os.environ.get('LOCALAPPDATA', '')
if _appdata: os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(_appdata, "UTPCalendar", "Navegadores")
else: os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"
import logging
import os
import re
from datetime import date
from dataclasses import dataclass
from html import unescape
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from credential_security import get_local_credential

logger = logging.getLogger(__name__)

try:
    import lxml
    DEFAULT_PARSER = "lxml"
except ImportError:
    DEFAULT_PARSER = "html.parser"

WEEKDAY_MAP = {
    "lunes": 0,
    "martes": 1,
    "miercoles": 2,
    "miércoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sabado": 5,
    "sábado": 5,
    "domingo": 6,
}

DEFAULT_LOGIN_URL = "https://sso.utp.edu.pe/auth/realms/Xpedition/protocol/openid-connect/auth?client_id=utpmas-web&redirect_uri=https%3A%2F%2Fportal.utp.edu.pe%2F&response_mode=fragment&response_type=code&scope=openid"
DEFAULT_SCHEDULE_URL = "https://portal.utp.edu.pe/calendario"


@dataclass
class ClassEvent:
    course: str
    day: str
    start_time: str
    end_time: str
    room: str
    class_date: Optional[date] = None

    def __post_init__(self) -> None:
        self.course = self.course.strip().lower().title()
        self.day = self.day.strip()
        self.start_time = self.start_time.strip()
        self.end_time = self.end_time.strip()
        self.room = self.room.strip() or "Por definir"

    def weekday(self) -> int:
        normalized = self.day.strip().lower()
        if normalized not in WEEKDAY_MAP:
            raise ValueError(f"Día no reconocido: {self.day}")
        return WEEKDAY_MAP[normalized]


class SpaPageDetectedError(RuntimeError):
    pass


def _env(name: str, required: bool = True, default: str = "") -> str:
    value = os.environ.get(name, default).strip()
    if required and not value:
        raise RuntimeError(f"Falta variable de entorno requerida: {name}")
    return value


def _extract_csrf(html: str) -> Dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    csrf_candidates = ["csrf", "csrf_token", "_csrf", "_token", "authenticity_token"]

    payload = {}
    for name in csrf_candidates:
        token_input = soup.select_one(f"input[name='{name}']")
        if token_input and token_input.get("value"):
            payload[name] = token_input.get("value")
            break

    return payload


def _extract_login_form(html: str) -> tuple[str, Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    form = soup.select_one("form")
    if form is None:
        raise RuntimeError("No se encontró formulario de login SSO.")

    action = (form.get("action") or "").strip()
    if not action:
        raise RuntimeError("No se encontró action en formulario SSO.")

    fields: Dict[str, str] = {}
    for input_el in form.select("input[name]"):
        name = (input_el.get("name") or "").strip()
        if not name:
            continue
        value = input_el.get("value")
        fields[name] = value if isinstance(value, str) else ""

    return unescape(action), fields


def _normalize_time(value: str) -> str:
    value = value.strip().replace(".", ":")
    if re.fullmatch(r"\d{1,2}:\d{2}", value):
        return value
    if re.fullmatch(r"\d{3,4}", value):
        if len(value) == 3:
            return f"0{value[0]}:{value[1:]}"
        return f"{value[:2]}:{value[2:]}"
    raise ValueError(f"Formato de hora no reconocido: {value}")


def _create_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _looks_like_login_page(html: str) -> bool:
    markers = ("Inicia Sesión", "Ingresa tus datos para iniciar sesión", "Usuario: código de alumno UTP")
    return any(marker in html for marker in markers)


def _looks_like_spa_shell(html: str) -> bool:
    shell_markers = ('<div id="root"></div>', "static/js/main", "webpackJsonp")
    return all(marker in html for marker in shell_markers)


def _parse_rows(html: str) -> List[ClassEvent]:
    row_selector = _env("SCHEDULE_ROW_SELECTOR", required=False, default="table tbody tr")
    course_selector = _env("COURSE_SELECTOR", required=False, default="td:nth-child(1)")
    day_selector = _env("DAY_SELECTOR", required=False, default="td:nth-child(2)")
    start_selector = _env("START_SELECTOR", required=False, default="td:nth-child(3)")
    end_selector = _env("END_SELECTOR", required=False, default="td:nth-child(4)")
    room_selector = _env("ROOM_SELECTOR", required=False, default="td:nth-child(5)")

    soup = BeautifulSoup(html, DEFAULT_PARSER)
    rows = soup.select(row_selector)

    events: List[ClassEvent] = []
    for row in rows:
        course_el = row.select_one(course_selector)
        day_el = row.select_one(day_selector)
        start_el = row.select_one(start_selector)
        end_el = row.select_one(end_selector)
        room_el = row.select_one(room_selector)

        if not all([course_el, day_el, start_el, end_el]):
            continue

        try:
            event = ClassEvent(
                course=course_el.get_text(strip=True),
                day=day_el.get_text(strip=True),
                start_time=_normalize_time(start_el.get_text(strip=True)),
                end_time=_normalize_time(end_el.get_text(strip=True)),
                room=(room_el.get_text(strip=True) if room_el else "Por definir"),
            )
            _ = event.weekday()
            events.append(event)
            # LOG EN VIVO DE CURSOS
            print(f"[Python] Curso detectado: {event.course} ({event.day.capitalize()})", flush=True)
        except Exception as exc:
            pass

    return events


def scrape_with_requests() -> List[ClassEvent]:
    username = get_local_credential("UNI_USERNAME")
    password = get_local_credential("UNI_PASSWORD")
    login_url = _env("UNI_LOGIN_URL", required=False, default=DEFAULT_LOGIN_URL)
    schedule_url = _env("UNI_SCHEDULE_URL", required=False, default=DEFAULT_SCHEDULE_URL)
    user_agent = _env("HTTP_USER_AGENT", required=False, default="Mozilla/5.0")

    session = _create_session()
    headers = {"User-Agent": user_agent, "Accept-Language": "es-PE,es;q=0.9"}

    logger.info("Iniciando sesión SSO con requests")
    entry_page = session.get(login_url, headers=headers, timeout=30)
    entry_page.raise_for_status()

    action_url, form_fields = _extract_login_form(entry_page.text)
    if not action_url.startswith(("http://", "https://")):
        action_url = requests.compat.urljoin(login_url, action_url)

    form_fields.update({"username": username, "password": password})

    if not any(k in form_fields for k in ("_token", "csrf", "csrf_token", "_csrf")):
        form_fields.update(_extract_csrf(entry_page.text))

    login_response = session.post(action_url, data=form_fields, headers=headers, timeout=30, allow_redirects=True)
    login_response.raise_for_status()

    schedule_response = session.get(schedule_url, headers=headers, timeout=30)
    schedule_response.raise_for_status()

    if _looks_like_login_page(schedule_response.text):
        raise RuntimeError("La sesión no quedó autenticada. Revisa tus credenciales.")

    events = _parse_rows(schedule_response.text)
    if not events and _looks_like_spa_shell(schedule_response.text):
        raise SpaPageDetectedError("La página de calendario está cifrada. Cambiando de motor...")

    return events