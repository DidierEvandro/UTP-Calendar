import os
_appdata = os.environ.get('LOCALAPPDATA', '')
if _appdata: os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(_appdata, "UTPCalendar", "Navegadores")
else: os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"
import logging
import json
import re
import unicodedata
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Callable, List
from zoneinfo import ZoneInfo

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from playwright.sync_api import Error as PlaywrightError

# Importaciones corregidas para el nuevo sistema
from cycle_config import format_date, calculate_extraction_window
from credential_security import get_local_credential
from peru_holidays import get_national_holidays_from
from scraper import ClassEvent


logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, str], None]


DEFAULT_LOGIN_URL = "https://sso.utp.edu.pe/auth/realms/Xpedition/protocol/openid-connect/auth?client_id=utpmas-web&redirect_uri=https%3A%2F%2Fportal.utp.edu.pe%2F&response_mode=fragment&response_type=code&scope=openid"
DEFAULT_SCHEDULE_URL = "https://portal.utp.edu.pe/calendario"
DEFAULT_BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
LIMA_TZ = ZoneInfo("America/Lima")
EXTRA_WEEK_DAYS = 7

WEEKDAY_NAME_BY_INDEX = {
    0: "lunes",
    1: "martes",
    2: "miercoles",
    3: "jueves",
    4: "viernes",
    5: "sabado",
    6: "domingo",
}

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

SPANISH_MONTH_MAP = {
        "enero": 1,
        "febrero": 2,
        "marzo": 3,
        "abril": 4,
        "mayo": 5,
        "junio": 6,
        "julio": 7,
        "agosto": 8,
        "setiembre": 9,
        "septiembre": 9,
        "octubre": 10,
        "noviembre": 11,
        "diciembre": 12,
}


def _env(name: str, required: bool = True, default: str = "") -> str:
    value = os.environ.get(name, default).strip()
    if required and not value:
        raise RuntimeError(f"Falta variable de entorno requerida: {name}")
    return value


def _emit_progress(progress_cb: ProgressCallback | None, percent: int, message: str) -> None:
    if progress_cb is None:
        return
    bounded = max(0, min(100, int(percent)))
    try:
        progress_cb(bounded, message)
    except Exception:
        pass


def _first_available(page_obj, selectors: List[str], action: str, value: str = "") -> str:
    for selector in selectors:
        loc = page_obj.locator(selector).first
        if loc.count() > 0:
            if action == "fill":
                loc.fill(value)
            elif action == "click":
                loc.click()
            return selector

    raise RuntimeError(f"No se encontro selector para {action}: {selectors}")


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


def _resolve_window() -> tuple[date, date, str]:
    today = datetime.now(LIMA_TZ).date()
    settings = _get_settings()
    window_start, window_end = calculate_extraction_window(settings, today)
    return window_start, window_end, "Ciclo Personalizado"


def _target_week_starts(window_start: date, window_end: date) -> list[date]:
    first_week = window_start - timedelta(days=window_start.weekday())
    last_week = window_end - timedelta(days=window_end.weekday())

    weeks: list[date] = []
    current = first_week
    while current <= last_week:
        weeks.append(current)
        current += timedelta(days=7)
    return weeks


def _normalize_day(day_value: str) -> str:
    return day_value.strip().lower().replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")


def _normalize_text(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()


def _extract_date_from_text(value: str, reference_year: int) -> date | None:
    normalized = _normalize_text(" ".join(value.split()))

    numeric_match = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", normalized)
    if numeric_match:
        day_text, month_text, year_text = numeric_match.groups()
        year = reference_year if not year_text else int(year_text)
        if year < 100:
            year += 2000
        try:
            return date(year, int(month_text), int(day_text))
        except ValueError:
            return None

    text_match = re.search(r"\b(\d{1,2})\s+de\s+([a-z]+)(?:\s+de\s+(\d{2,4}))?\b", normalized)
    if not text_match:
        return None

    day_text, month_text, year_text = text_match.groups()
    month = SPANISH_MONTH_MAP.get(month_text)
    if month is None:
        return None

    year = reference_year if not year_text else int(year_text)
    if year < 100:
        year += 2000

    try:
        return date(year, month, int(day_text))
    except ValueError:
        return None


def _extract_rows_from_current_week(
    page,
    row_selector: str,
    course_selector: str,
    day_selector: str,
    start_selector: str,
    end_selector: str,
    room_selector: str,
) -> list[dict]:
    try:
        page.wait_for_selector("button.cardContent.fadeTransition, table tbody tr", timeout=12000)
    except PlaywrightTimeoutError:
        logger.info("No se detectaron filas directas, continuando con extracción automática del DOM.")

    return page.evaluate(
        r"""
    ({ rowSelector, courseSelector, daySelector, startSelector, endSelector, roomSelector }) => {
      const dayRegex = /(lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingo)/i;
      const timeRegex = /\b([01]?\d|2[0-3])[:.]([0-5]\d)\b/g;

      const pick = (root, selector) => {
        if (!selector) return '';
        const el = root.querySelector(selector);
        return el ? (el.textContent || '').trim() : '';
      };

      const normalizeTime = (v) => (v || '').trim().replace('.', ':');

      const fromUtpEventCards = () => {
        const dayNameMap = {
          lun: 'lunes',
          mar: 'martes',
          mie: 'miercoles',
          mié: 'miercoles',
          jue: 'jueves',
          vie: 'viernes',
          sab: 'sabado',
          sáb: 'sabado',
          dom: 'domingo',
        };

        const dayHeaderRegex = /\b(lun(?:es)?|mar(?:tes)?|mi[eé](?:rcoles)?|jue(?:ves)?|vie(?:rnes)?|s[aá]b(?:ado)?|dom(?:ingo)?)\b/i;

        const detectDayColumns = () => {
          const all = Array.from(document.querySelectorAll('*'));
          const candidates = [];

          for (const el of all) {
            const text = (el.textContent || '').trim();
            if (!text || text.length > 16) continue;
            if (!dayHeaderRegex.test(text)) continue;

            const rect = el.getBoundingClientRect();
            if (rect.width < 12 || rect.height < 8) continue;
            if (rect.top > window.innerHeight * 0.55) continue;

            const tokenMatch = text.match(dayHeaderRegex);
            if (!tokenMatch) continue;
            const token = tokenMatch[1].slice(0, 3).toLowerCase();
            const day = dayNameMap[token];
            if (!day) continue;

            candidates.push({
              day,
              x: rect.left + rect.width / 2,
              top: rect.top,
            });
          }

          const byDay = {};
          for (const c of candidates) {
            if (!byDay[c.day] || c.top < byDay[c.day].top) {
              byDay[c.day] = c;
            }
          }

          return Object.values(byDay).sort((a, b) => a.x - b.x);
        };

        const dayColumns = detectDayColumns();
        const out = [];
        const cards = Array.from(document.querySelectorAll('button.cardContent.fadeTransition'));
        for (const card of cards) {
          const text = (card.textContent || '').trim();
          if (!text.includes('Curso:')) continue;

          let day = '';
          if (dayColumns.length > 0) {
            const rect = card.getBoundingClientRect();
            const centerX = rect.left + rect.width / 2;
            let best = dayColumns[0];
            let bestDistance = Math.abs(centerX - best.x);

            for (const col of dayColumns.slice(1)) {
              const dist = Math.abs(centerX - col.x);
              if (dist < bestDistance) {
                best = col;
                bestDistance = dist;
              }
            }
            day = best.day;
          }

          const courseMatch = text.match(/Curso:\s*(.+?)(?=([01]?\d|2[0-3])[:.][0-5]\d)/i);
          const timeMatches = Array.from(text.matchAll(/([01]?\d|2[0-3])[:.]([0-5]\d)/g));
          const times = timeMatches.map((m) => `${m[1]}:${m[2]}`);
          const roomMatch = text.match(/[A-Z]\d{3,4}/);

          out.push({
            course: courseMatch ? courseMatch[1].trim() : '',
            day,
            start: times[0] ? normalizeTime(times[0]) : '',
            end: times[1] ? normalizeTime(times[1]) : '',
            room: roomMatch ? roomMatch[0] : 'Por definir',
            raw: text,
          });
        }
        return out;
      };

      const fromConfiguredRows = () => {
        const rows = Array.from(document.querySelectorAll(rowSelector));
        return rows.map((row) => ({
          course: pick(row, courseSelector),
          day: pick(row, daySelector),
          start: normalizeTime(pick(row, startSelector)),
          end: normalizeTime(pick(row, endSelector)),
          room: pick(row, roomSelector),
        }));
      };

      const fromGenericTables = () => {
        const out = [];
        const rows = Array.from(document.querySelectorAll('table tr'));
        for (const row of rows) {
          const cols = Array.from(row.querySelectorAll('th,td')).map((c) => (c.textContent || '').trim()).filter(Boolean);
          if (cols.length < 4) continue;
          const joined = cols.join(' | ');
          const dayMatch = joined.match(dayRegex);
          const times = joined.match(/\b([01]?\d|2[0-3])[:.]([0-5]\d)\b/g) || [];
          if (!dayMatch || times.length < 2) continue;
          out.push({
            course: cols[0],
            day: dayMatch[0],
            start: normalizeTime(times[0]),
            end: normalizeTime(times[1]),
            room: cols[cols.length - 1],
          });
        }
        return out;
      };

      const utpCards = fromUtpEventCards().filter((x) => x.course && x.day && x.start && x.end);
      if (utpCards.length) return utpCards;

      const preferred = fromConfiguredRows().filter((x) => x.course && x.day && x.start && x.end);
      if (preferred.length) return preferred;

      return fromGenericTables();
    }
    """,
        {
            "rowSelector": row_selector,
            "courseSelector": course_selector,
            "daySelector": day_selector,
            "startSelector": start_selector,
            "endSelector": end_selector,
            "roomSelector": room_selector,
        },
    )


def _fetch_monthly_rows_via_graphql(
    page,
    target_weeks: list[date],
    auth_headers: dict[str, str],
    progress_cb: ProgressCallback | None = None,
) -> list[dict]:
    endpoint = "https://api-portal.utpxpedition.com/graphql"
    if not auth_headers or "authorization" not in auth_headers:
        logger.warning("No se encontraron headers de autorización para GraphQL.")
        return []

    headers = {
        "content-type": "application/json",
        "accept": "application/json",
        "authorization": auth_headers.get("authorization", ""),
        "applicationid": auth_headers.get("applicationid", "utpmas-web"),
        "isreservation": auth_headers.get("isreservation", "false"),
        "user-role": auth_headers.get("user-role", "student"),
        "user-id": auth_headers.get("user-id", ""),
        "accept-language": auth_headers.get("accept-language", "es-PE,es;q=0.9"),
        "referer": "https://portal.utp.edu.pe/calendario",
    }

    periods_query = {
        "operationName": "getPeriodsAvailable",
        "variables": {},
        "query": "query getPeriodsAvailable { academicInformationV2 { periods { period isCurrent } } }",
    }

    schedule_query = {
        "operationName": "getSchedules",
        "query": (
            "query getSchedules($date: Float!, $periods: [String!]) { "
            "scheduleByDate(filters: {date: $date, classTypes: [1, 2, 3, 4, 5, 6], periods: $periods}) { "
            "dates { date items { name startTime endTime typeSchedule { name } modality { location } "
            "class { start end type isClass name location { classRoom { id } } } } } } }"
        ),
    }

    try:
        _emit_progress(progress_cb, 42, "Preparando consulta GraphQL")
        periods_resp = page.request.post(
            endpoint,
            headers=headers,
            data=json.dumps(periods_query),
            timeout=45000,
        )
        periods_data = periods_resp.json()
        periods = (periods_data.get("data") or {}).get("academicInformationV2", {}).get("periods", [])
        current = next((p for p in periods if p.get("isCurrent")), periods[0] if periods else None)
        period = (current or {}).get("period")
        if not period:
            logger.warning("GraphQL no devolvió periodo académico vigente.")
            return []

        rows: list[dict] = []
        total_weeks = max(1, len(target_weeks))
        for index, week_start in enumerate(target_weeks, start=1):
            _emit_progress(progress_cb, 45 + int(18 * (index - 1) / total_weeks), f"Consultando semana {index} de {total_weeks}")
            dt_ref = datetime.combine(week_start, datetime.min.time(), LIMA_TZ) + timedelta(hours=12)
            payload = {
                "operationName": schedule_query["operationName"],
                "variables": {"date": float(int(dt_ref.timestamp() * 1000)), "periods": [period]},
                "query": schedule_query["query"],
            }
            response = page.request.post(
                endpoint,
                headers=headers,
                data=json.dumps(payload),
                timeout=45000,
            )
            body = response.json()
            dates = (body.get("data") or {}).get("scheduleByDate", {}).get("dates", [])

            for d in dates:
                class_date = d.get("date")
                for item in d.get("items", []):
                    cls = item.get("class") or {}
                    type_name = str((item.get("typeSchedule") or {}).get("name") or "").upper()
                    class_type = str(cls.get("type") or "").upper()
                    is_class = type_name == "CLASS" or cls.get("isClass") is True or class_type == "COURSE"
                    if not is_class:
                        continue

                    course = item.get("name") or cls.get("name") or ""
                    start_ms = int(item.get("startTime") or cls.get("start") or 0)
                    end_ms = int(item.get("endTime") or cls.get("end") or 0)
                    room = (
                        (item.get("modality") or {}).get("location")
                        or ((cls.get("location") or {}).get("classRoom") or {}).get("id")
                        or "Por definir"
                    )

                    if course and class_date and start_ms and end_ms:
                        rows.append(
                            {
                                "date": class_date,
                                "course": course,
                                "startMs": start_ms,
                                "endMs": end_ms,
                                "room": str(room).strip() or "Por definir",
                            }
                        )

            logger.info("Extracción GraphQL activa para periodo %s: %s filas.", period, len(rows))
            _emit_progress(progress_cb, 65, "GraphQL completado")
        return rows
    except Exception as exc:
        logger.warning("Extracción GraphQL no disponible: %s", exc)
        return []


def _close_overlays_if_present(page) -> None:
    close_selectors = [
        "button:has-text('No, gracias')",
        "button:has-text('Omitir')",
        "button[data-testid='cmp-close-LightBox']",
    ]
    for selector in close_selectors:
        try:
            loc = page.locator(selector).first
            if loc.count() > 0 and loc.is_visible():
                loc.click(timeout=1200)
                page.wait_for_timeout(350)
        except Exception:
            pass


def _get_week_nav_buttons(page):
    return page.locator("button.button--md.sc-cc-button")


def _go_to_week(page, current_week_start: date, target_week_start: date) -> bool:
    if current_week_start == target_week_start:
        return True

    nav_buttons = _get_week_nav_buttons(page)

    def _safe_button_count() -> int:
        try:
            return nav_buttons.count()
        except PlaywrightError:
            page.wait_for_timeout(600)
            page.wait_for_load_state("domcontentloaded", timeout=8000)
            return _get_week_nav_buttons(page).count()

    if _safe_button_count() < 2:
        for _ in range(3):
            _close_overlays_if_present(page)
            page.wait_for_timeout(500)
            nav_buttons = _get_week_nav_buttons(page)
            if _safe_button_count() >= 2:
                break

    if _safe_button_count() < 2:
        return False

    step_days = (target_week_start - current_week_start).days
    step_weeks = step_days // 7

    if step_weeks == 0:
        return True

    direction_idx = 0 if step_weeks < 0 else 1
    clicks = abs(step_weeks)

    for _ in range(clicks):
        _close_overlays_if_present(page)
        nav_buttons.nth(direction_idx).click(timeout=3000)
        page.wait_for_timeout(1500)

    return True


def scrape_with_playwright(progress_cb: ProgressCallback | None = None) -> List[ClassEvent]:
    username = get_local_credential("UNI_USERNAME")
    password = get_local_credential("UNI_PASSWORD")
    login_url = _env("UNI_LOGIN_URL", required=False, default=DEFAULT_LOGIN_URL)
    schedule_url = _env("UNI_SCHEDULE_URL", required=False, default=DEFAULT_SCHEDULE_URL)

    user_selector = _env("LOGIN_USER_SELECTOR", required=False, default="#username,input[name='username']")
    pass_selector = _env("LOGIN_PASS_SELECTOR", required=False, default="#password,input[name='password']")
    submit_selector = _env("LOGIN_SUBMIT_SELECTOR", required=False, default="#kc-login,input[type='submit'],button[type='submit']")

    row_selector = _env("SCHEDULE_ROW_SELECTOR", required=False, default="table tbody tr")
    course_selector = _env("COURSE_SELECTOR", required=False, default="td:nth-child(1)")
    day_selector = _env("DAY_SELECTOR", required=False, default="td:nth-child(2)")
    start_selector = _env("START_SELECTOR", required=False, default="td:nth-child(3)")
    end_selector = _env("END_SELECTOR", required=False, default="td:nth-child(4)")
    room_selector = _env("ROOM_SELECTOR", required=False, default="td:nth-child(5)")

    events: List[ClassEvent] = []
    event_keys: set[tuple[str, str, str, str, str, str]] = set()

    window_start, window_end, cycle_name = _resolve_window()
    target_weeks = _target_week_starts(window_start, window_end)
    try:
        national_holidays = get_national_holidays_from(window_start)
    except Exception as exc:
        logger.warning("No se pudieron cargar feriados nacionales en Playwright: %s", exc)
        national_holidays = {}

    user_selectors = [s.strip() for s in user_selector.split(",") if s.strip()]
    pass_selectors = [s.strip() for s in pass_selector.split(",") if s.strip()]
    submit_selectors = [s.strip() for s in submit_selector.split(",") if s.strip()]

    logger.info("Iniciando fallback con Playwright")
    _emit_progress(progress_cb, 32, "Iniciando navegador")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        _emit_progress(progress_cb, 36, "Configurando navegador")
        context = browser.new_context(
            locale="es-PE",
            timezone_id="America/Lima",
            user_agent=DEFAULT_BROWSER_UA,
        )
        page = context.new_page()
        _emit_progress(progress_cb, 38, "Preparando autenticacion")
        graphql_auth_headers: dict[str, str] = {}

        def _capture_graphql_request_headers(request) -> None:
            if graphql_auth_headers:
                return
            if "api-portal.utpxpedition.com/graphql" not in request.url:
                return
            headers = request.headers
            graphql_auth_headers.update(
                {
                    "authorization": headers.get("authorization", ""),
                    "applicationid": headers.get("applicationid", ""),
                    "isreservation": headers.get("isreservation", ""),
                    "user-role": headers.get("user-role", ""),
                    "user-id": headers.get("user-id", ""),
                    "accept-language": headers.get("accept-language", ""),
                }
            )

        page.on("request", _capture_graphql_request_headers)

        try:
            page.goto(login_url, wait_until="domcontentloaded", timeout=45000)
            _emit_progress(progress_cb, 40, "Login cargado")
            used_user = _first_available(page, user_selectors, "fill", username)
            used_pass = _first_available(page, pass_selectors, "fill", password)
            used_submit = _first_available(page, submit_selectors, "click")
            logger.info("Selectores login usados: user=%s pass=%s submit=%s", used_user, used_pass, used_submit)
            _emit_progress(progress_cb, 41, "Enviando credenciales")
            page.wait_for_timeout(2500)

            try:
                login_visible = (
                    page.locator("#username,input[name='username']").count() > 0
                    and page.locator("#password,input[name='password']").count() > 0
                )
            except PlaywrightError:
                login_visible = False
            if login_visible:
                raise RuntimeError("No se pudo iniciar sesion. Verifica codigo y contraseña.")

            try:
                page.wait_for_url("**portal.utp.edu.pe/**", timeout=45000)
            except PlaywrightTimeoutError:
                logger.info("No se detecto redireccion completa tras login, continuando con URL actual.")

            _emit_progress(progress_cb, 44, "Abriendo calendario")

            if "portal.utp.edu.pe" not in page.url or "calendario" not in page.url:
                page.goto(schedule_url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(8000)
            _emit_progress(progress_cb, 46, "Calendario listo")

            if not graphql_auth_headers:
                page.reload(wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(5000)

            _close_overlays_if_present(page)

            logger.info(
                "Extracción de ciclo %s en ventana %s a %s (%s semanas).",
                cycle_name,
                format_date(window_start),
                format_date(window_end),
                len(target_weeks),
            )
            
            gql_rows = _fetch_monthly_rows_via_graphql(page, target_weeks, graphql_auth_headers, progress_cb=progress_cb)
            for row in gql_rows:
                course = (row.get("course") or "").strip()
                room = (row.get("room") or "").strip() or "Por definir"
                class_date_raw = (row.get("date") or "").strip()
                start_ms = int(row.get("startMs") or 0)
                end_ms = int(row.get("endMs") or 0)

                if not (course and class_date_raw and start_ms and end_ms):
                    continue

                try:
                    class_date = datetime.strptime(class_date_raw, "%Y-%m-%d").date()
                except ValueError:
                    continue

                if class_date < window_start or class_date > window_end:
                    continue

                if class_date in national_holidays:
                    logger.info(
                        "Feriado detectado en GraphQL, evento omitido: %s | %s | %s",
                        format_date(class_date),
                        national_holidays[class_date],
                        course,
                    )
                    continue

                start_time = datetime.fromtimestamp(start_ms / 1000, tz=LIMA_TZ).strftime("%H:%M")
                end_time = datetime.fromtimestamp(end_ms / 1000, tz=LIMA_TZ).strftime("%H:%M")
                day = WEEKDAY_NAME_BY_INDEX[class_date.weekday()]

                dedupe_key = (
                    format_date(class_date),
                    course.lower(),
                    day,
                    start_time,
                    end_time,
                    room.lower(),
                )
                if dedupe_key in event_keys:
                    continue

                event_keys.add(dedupe_key)
                events.append(
                    ClassEvent(
                        course=course,
                        day=day,
                        start_time=start_time,
                        end_time=end_time,
                        room=room,
                        class_date=class_date,
                    )
                )

            if events:
                logger.info("Eventos cargados por GraphQL: %s", len(events))
                _emit_progress(progress_cb, 68, "Eventos cargados por GraphQL")
            else:
                logger.warning("GraphQL no devolvió clases; se activa respaldo por navegación DOM.")
                current_week_start = window_start - timedelta(days=window_start.weekday())
                total_weeks = max(1, len(target_weeks))

                for index, week_start in enumerate(target_weeks, start=1):
                    _emit_progress(progress_cb, 70 + int(18 * (index - 1) / total_weeks), f"Extrayendo semana DOM {index} de {total_weeks}")
                    try:
                        moved = _go_to_week(page, current_week_start, week_start)
                    except Exception as exc:
                        logger.warning("Error navegando semana %s: %s", format_date(week_start), exc)
                        moved = False
                    if not moved:
                        logger.warning(
                            "No se detectaron botones de navegación semanal; usando vista actual para semana %s.",
                            format_date(week_start),
                        )
                    else:
                        current_week_start = week_start

                    page.wait_for_timeout(2200)
                    rows_data = _extract_rows_from_current_week(
                        page,
                        row_selector=row_selector,
                        course_selector=course_selector,
                        day_selector=day_selector,
                        start_selector=start_selector,
                        end_selector=end_selector,
                        room_selector=room_selector,
                    )

                    if not rows_data:
                        logger.info("Semana %s sin eventos detectados.", format_date(week_start))
                        continue

                    for row in rows_data:
                        course = (row.get("course") or "").strip()
                        day = (row.get("day") or "").strip()
                        start_time = (row.get("start") or "").strip().replace(".", ":")
                        end_time = (row.get("end") or "").strip().replace(".", ":")
                        room = (row.get("room") or "").strip() or "Por definir"
                        raw_text = (row.get("raw") or "").strip()

                        if room == "Por definir" and raw_text:
                            room_match = re.search(r"[A-Z]\d{3,4}", raw_text)
                            if room_match:
                                room = room_match.group(0)

                        if (not start_time or not end_time) and raw_text:
                            times = re.findall(r"([01]?\d|2[0-3])[:.]([0-5]\d)", raw_text)
                            if len(times) >= 2:
                                start_time = f"{times[0][0]}:{times[0][1]}"
                                end_time = f"{times[1][0]}:{times[1][1]}"

                        if not all([course, day, start_time, end_time]):
                            continue

                        if not re.fullmatch(r"\d{1,2}:\d{2}", start_time) or not re.fullmatch(r"\d{1,2}:\d{2}", end_time):
                            continue

                        class_date = _extract_date_from_text(raw_text, week_start.year) if raw_text else None
                        if class_date is None:
                            normalized_day = _normalize_day(day)
                            weekday = WEEKDAY_MAP.get(normalized_day)
                            if weekday is None:
                                continue

                            class_date = week_start + timedelta(days=weekday)

                        if class_date < window_start or class_date > window_end:
                            continue

                        if class_date in national_holidays:
                            logger.info(
                                "Feriado detectado en DOM, evento omitido: %s | %s | %s",
                                format_date(class_date),
                                national_holidays[class_date],
                                course,
                            )
                            continue

                        dedupe_key = (
                            format_date(class_date),
                            course.lower(),
                            normalized_day,
                            start_time,
                            end_time,
                            room.lower(),
                        )
                        if dedupe_key in event_keys:
                            continue

                        event_keys.add(dedupe_key)
                        events.append(
                            ClassEvent(
                                course=course,
                                day=day,
                                start_time=start_time,
                                end_time=end_time,
                                room=room,
                                class_date=class_date,
                            )
                        )

                _emit_progress(progress_cb, 90, "Extraccion DOM completada")

        except PlaywrightTimeoutError as exc:
            logger.error("Timeout en Playwright: %s", exc)
            raise
        finally:
            context.close()
            browser.close()

    logger.info("Eventos detectados con Playwright: %s", len(events))
    _emit_progress(progress_cb, 95, "Playwright finalizado")
    return events