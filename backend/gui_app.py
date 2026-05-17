import json
import logging
import os
import queue
import threading
import tkinter as tk
from dataclasses import dataclass
from calendar import monthrange
from datetime import date, datetime, time, timedelta
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk
from urllib.parse import urlparse

from icalendar import Calendar as ICalendar

from autostart_manager import (
    get_autorun,
    set_autorun,
    repair_autorun,
)
from cycle_config import (
    CYCLE_LABELS,
    clamp_window,
    cycle_bounds,
    default_selection_window,
    detect_cycle_for_date,
    format_date,
    normalize_cycle_name,
    parse_date,
    format_datetime,
)
from credential_security import clear_active_credentials, set_active_credentials
from peru_holidays import get_holiday_cache_updated_at, refresh_national_holidays_cache
from nextcloud_uploader import test_nextcloud_connection
from pipeline import run_pipeline
from scraper import DEFAULT_LOGIN_URL, DEFAULT_SCHEDULE_URL


DATA_FILE = Path(__file__).with_name("local_profiles.json")
DEFAULT_FIRST_EVENT_REMINDER_MINUTES = 120
DEFAULT_OTHER_EVENTS_REMINDER_MINUTES = 5
DEFAULT_NEXTCLOUD_TIMEOUT_SECONDS = 10
DATE_INPUT_MODE_TEXT = "text"
DATE_INPUT_MODE_DROPDOWN = "dropdown"
SPANISH_MONTHS = (
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
)
MONTH_TO_NUMBER = {name: index + 1 for index, name in enumerate(SPANISH_MONTHS)}
MONTHS_BY_CYCLE = {
    "Verano": (1, 2),
    "Marzo": (3, 4, 5, 6, 7),
    "Agosto": (8, 9, 10, 11, 12),
}

CALENDAR_MONTH_NAMES = (
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
)


@dataclass(frozen=True)
class CalendarEventItem:
    event_date: date
    start_dt: datetime
    end_dt: datetime
    summary: str
    location: str
    description: str


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


class QueueLogHandler(logging.Handler):
    def __init__(self, log_queue: queue.Queue[str]) -> None:
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.log_queue.put_nowait(msg)
        except Exception:
            self.handleError(record)


def _default_data() -> dict:
    return {
        "users": [],
        "settings": {
            "login_url": DEFAULT_LOGIN_URL,
            "schedule_url": DEFAULT_SCHEDULE_URL,
            "cycle_lock_enabled": True,
            "reminders_enabled": True,
            "first_event_reminder_minutes": DEFAULT_FIRST_EVENT_REMINDER_MINUTES,
            "other_events_reminder_minutes": DEFAULT_OTHER_EVENTS_REMINDER_MINUTES,
            "nextcloud_upload_enabled": False,
            "nextcloud_server_url": "",
            "nextcloud_bearer_token": "",
            "nextcloud_remote_path": "",
            "nextcloud_timeout_seconds": DEFAULT_NEXTCLOUD_TIMEOUT_SECONDS,
            "subscription_ics_url": "",
            "default_username": "",
            "autostart_enabled": False,
            "selected_cycle": "",
            "date_input_mode": DATE_INPUT_MODE_DROPDOWN,
            "last_ics_generated": "Nunca",
            "last_nextcloud_upload": "Nunca",
        },
    }


def _load_data() -> dict:
    if not DATA_FILE.exists():
        return _default_data()

    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return _default_data()

    if not isinstance(data, dict):
        return _default_data()

    users = data.get("users", [])
    settings = data.get("settings", {})

    if not isinstance(users, list):
        users = []
    if not isinstance(settings, dict):
        settings = {}

    return {
        "users": [u for u in users if isinstance(u, dict)],
        "settings": {
            "login_url": str(settings.get("login_url") or DEFAULT_LOGIN_URL),
            "schedule_url": str(settings.get("schedule_url") or DEFAULT_SCHEDULE_URL),
            "cycle_lock_enabled": bool(settings.get("cycle_lock_enabled", True)),
            "reminders_enabled": bool(settings.get("reminders_enabled", True)),
            "first_event_reminder_minutes": _safe_non_negative_int(
                settings.get("first_event_reminder_minutes"),
                DEFAULT_FIRST_EVENT_REMINDER_MINUTES,
            ),
            "other_events_reminder_minutes": _safe_non_negative_int(
                settings.get("other_events_reminder_minutes"),
                DEFAULT_OTHER_EVENTS_REMINDER_MINUTES,
            ),
            "nextcloud_upload_enabled": bool(settings.get("nextcloud_upload_enabled", False)),
            "nextcloud_server_url": str(settings.get("nextcloud_server_url") or ""),
            "nextcloud_bearer_token": str(settings.get("nextcloud_bearer_token") or ""),
            "nextcloud_remote_path": str(settings.get("nextcloud_remote_path") or ""),
            "nextcloud_timeout_seconds": max(
                1,
                _safe_non_negative_int(
                    settings.get("nextcloud_timeout_seconds"),
                    DEFAULT_NEXTCLOUD_TIMEOUT_SECONDS,
                ),
            ),
            "subscription_ics_url": str(settings.get("subscription_ics_url") or ""),
            "default_username": str(settings.get("default_username") or ""),
            "autostart_enabled": bool(settings.get("autostart_enabled", False)),
            "selected_cycle": str(settings.get("selected_cycle") or ""),
            "date_input_mode": str(settings.get("date_input_mode") or DATE_INPUT_MODE_DROPDOWN),
            "last_ics_generated": str(settings.get("last_ics_generated") or "Nunca"),
            "last_nextcloud_upload": str(settings.get("last_nextcloud_upload") or "Nunca"),
        },
    }


def _safe_non_negative_int(value, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, parsed)


def _save_data(data: dict) -> None:
    DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


class UtpCalendarApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("UTP Calendar - Gestor de Usuarios")
        self.root.geometry("980x720")
        self.root.minsize(860, 620)

        self.data = _load_data()
        self.status_var = tk.StringVar(value="Listo")
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_pct_var = tk.StringVar(value="0%")
        self.is_running = False
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.log_handler = self._setup_log_handler()
        self.cycle_var = tk.StringVar()
        self.start_date_var = tk.StringVar()
        self.end_date_var = tk.StringVar()
        self.date_input_mode_var = tk.StringVar(value=str(self.data["settings"].get("date_input_mode", DATE_INPUT_MODE_DROPDOWN)))
        self.start_day_var = tk.StringVar()
        self.start_month_var = tk.StringVar()
        self.start_year_var = tk.StringVar()
        self.end_day_var = tk.StringVar()
        self.end_month_var = tk.StringVar()
        self.end_year_var = tk.StringVar()
        self.year_options = [str(year) for year in range(date.today().year - 5, date.today().year + 6)]
        self.lock_cycle_var = tk.BooleanVar(value=bool(self.data["settings"].get("cycle_lock_enabled", True)))
        self.reminders_enabled_var = tk.BooleanVar(value=bool(self.data["settings"].get("reminders_enabled", True)))
        self.first_event_reminder_var = tk.StringVar(
            value=str(
                _safe_non_negative_int(
                    self.data["settings"].get("first_event_reminder_minutes"),
                    DEFAULT_FIRST_EVENT_REMINDER_MINUTES,
                )
            )
        )
        self.other_events_reminder_var = tk.StringVar(
            value=str(
                _safe_non_negative_int(
                    self.data["settings"].get("other_events_reminder_minutes"),
                    DEFAULT_OTHER_EVENTS_REMINDER_MINUTES,
                )
            )
        )
        self.nextcloud_enabled_var = tk.BooleanVar(
            value=bool(self.data["settings"].get("nextcloud_upload_enabled", False))
        )
        self.nextcloud_server_url_var = tk.StringVar(
            value=str(self.data["settings"].get("nextcloud_server_url", ""))
        )
        self.nextcloud_bearer_token_var = tk.StringVar(
            value=str(self.data["settings"].get("nextcloud_bearer_token", ""))
        )
        self.nextcloud_remote_path_var = tk.StringVar(
            value=str(self.data["settings"].get("nextcloud_remote_path", ""))
        )
        self.subscription_url_var = tk.StringVar(
            value=str(self.data["settings"].get("subscription_ics_url", ""))
        )
        self.nextcloud_timeout_var = tk.StringVar(
            value=str(
                max(
                    1,
                    _safe_non_negative_int(
                        self.data["settings"].get("nextcloud_timeout_seconds"),
                        DEFAULT_NEXTCLOUD_TIMEOUT_SECONDS,
                    ),
                )
            )
        )
        self.default_user_var = tk.StringVar(
            value=str(self.data["settings"].get("default_username", ""))
        )
        self.default_user_status_var = tk.StringVar(value=self._default_user_status_text())
        self.user_selected_info_var = tk.StringVar(value="Selecciona un usuario para ver sus datos")
        self.user_selected_meta_var = tk.StringVar(value="")
        # Variables de autoinicio
        self.autostart_enabled_var = tk.BooleanVar(
            value=bool(self.data["settings"].get("autostart_enabled", False))
        )
        self.autostart_status_var = tk.StringVar(value="Autoinicio: verificando...")
        # Últimas acciones
        self.last_ics_gen_var = tk.StringVar(value=str(self.data.get("settings", {}).get("last_ics_generated", "Nunca")))
        self.last_nextcloud_upload_var = tk.StringVar(value=str(self.data.get("settings", {}).get("last_nextcloud_upload", "Nunca")))
        self.autostart_details_var = tk.StringVar(value="")
        self.holidays_updated_var = tk.StringVar(value="Actualizado a: verificando...")
        self.window_hint_var = tk.StringVar(value="")
        self.calendar_status_var = tk.StringVar(value="Cargando calendario...")
        self.calendar_month_var = tk.StringVar(value="")
        self.calendar_selected_day_var = tk.StringVar(value="")
        self.calendar_events: list[CalendarEventItem] = []
        self.calendar_events_by_date: dict[date, list[CalendarEventItem]] = {}
        self.calendar_visible_year = date.today().year
        self.calendar_visible_month = date.today().month
        self.calendar_selected_date = date.today()

        self._build_modern_ui()
        self._initialize_cycle_controls()
        self._sync_date_input_mode_ui()
        self._load_users_into_tree()
        self._refresh_holidays_status()
        self._refresh_autostart_status()
        self._poll_logs()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_log_handler(self) -> logging.Handler:
        handler = QueueLogHandler(self.log_queue)
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logging.getLogger().addHandler(handler)
        return handler

    def _build_modern_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=0)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=0, column=0, sticky="nsew")

        self.user_tab = ttk.Frame(self.notebook)
        self.reminders_tab = ttk.Frame(self.notebook)
        self.nextcloud_tab = ttk.Frame(self.notebook)
        self.terminal_tab = ttk.Frame(self.notebook)
        self.calendar_tab = ttk.Frame(self.notebook)
        self.help_tab = ttk.Frame(self.notebook)
        self.advanced_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.user_tab, text="Usuarios")
        self.notebook.add(self.reminders_tab, text="Recordatorios")
        self.notebook.add(self.nextcloud_tab, text="Nextcloud")
        self.notebook.add(self.terminal_tab, text="Terminal")
        self.notebook.add(self.calendar_tab, text="Calendario")
        self.notebook.add(self.help_tab, text="Como usar")
        self.notebook.add(self.advanced_tab, text="Ajustes avanzados")

        self._build_user_tab()
        self._build_reminders_tab()
        self._build_nextcloud_tab()
        self._build_terminal_tab()
        self._build_calendar_tab()
        self._build_help_tab()
        self._build_advanced_tab()

        footer = ttk.Frame(self.root, padding=(12, 0, 12, 10))
        footer.grid(row=1, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)

        actions_row = ttk.Frame(footer)
        actions_row.pack(fill=tk.X, pady=(0, 6))

        progress_row = ttk.Frame(footer)
        progress_row.pack(fill=tk.X)

        self.progress_bar = ttk.Progressbar(
            progress_row,
            orient=tk.HORIZONTAL,
            mode="determinate",
            maximum=100,
            variable=self.progress_var,
        )
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(progress_row, textvariable=self.progress_pct_var, width=6, anchor="e").pack(side=tk.RIGHT, padx=(8, 0))

        ttk.Label(footer, textvariable=self.status_var).pack(anchor="w", pady=(4, 0))

        info_row = ttk.Frame(footer)
        info_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(info_row, text="Ultima generacion .ics:", width=20, anchor="w").pack(side=tk.LEFT)
        ttk.Label(info_row, textvariable=self.last_ics_gen_var, width=24, anchor="w").pack(side=tk.LEFT)
        ttk.Label(info_row, text="Ultima subida Nextcloud:", width=22, anchor="w").pack(side=tk.LEFT, padx=(12, 0))
        ttk.Label(info_row, textvariable=self.last_nextcloud_upload_var, width=24, anchor="w").pack(side=tk.LEFT)

        self._reload_calendar_from_disk()

    def _build_user_tab(self) -> None:
        outer = ttk.Frame(self.user_tab, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(outer, highlightthickness=0)
        self.v_scroll = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.v_scroll.set)
        self.v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        frame = ttk.Frame(self.canvas, padding=12)
        self.canvas_window_id = self.canvas.create_window((0, 0), window=frame, anchor="nw")
        frame.bind("<Configure>", self._on_content_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        ttk.Label(frame, text="Usuarios registrados", font=("TkDefaultFont", 11, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(frame, text="Administrar cuentas, revisar informacion y generar el ultimo .ics.", foreground="gray").grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 10))

        self.tree = ttk.Treeview(frame, columns=("username",), show="headings", height=10)
        self.tree.heading("username", text="Codigo de alumno")
        self.tree.column("username", width=260)
        self.tree.grid(row=2, column=0, columnspan=3, sticky="nsew", pady=(0, 8))
        self.tree.bind("<<TreeviewSelect>>", self._on_select_user)

        ttk.Label(frame, textvariable=self.user_selected_info_var, wraplength=760, justify=tk.LEFT).grid(row=3, column=0, columnspan=3, sticky="w")
        ttk.Label(frame, textvariable=self.user_selected_meta_var, foreground="gray", wraplength=760, justify=tk.LEFT).grid(row=4, column=0, columnspan=3, sticky="w", pady=(2, 10))

        ttk.Label(frame, text="Codigo").grid(row=5, column=0, sticky="w")
        self.username_entry = ttk.Entry(frame)
        self.username_entry.grid(row=6, column=0, sticky="ew", padx=(0, 8))

        ttk.Label(frame, text="Contrasena").grid(row=5, column=1, sticky="w")
        self.password_entry = ttk.Entry(frame, show="*")
        self.password_entry.grid(row=6, column=1, sticky="ew", padx=(0, 8))

        add_btn = ttk.Button(frame, text="Agregar / Actualizar", command=self._add_or_update_user)
        add_btn.grid(row=6, column=2, sticky="ew")

        action_row = ttk.Frame(frame)
        action_row.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        action_row.columnconfigure(0, weight=1)
        action_row.columnconfigure(1, weight=1)
        action_row.columnconfigure(2, weight=1)

        self.set_default_user_btn = ttk.Button(action_row, text="Establecer como predeterminado", command=self._set_selected_as_default, state=tk.DISABLED)
        self.set_default_user_btn.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        del_btn = ttk.Button(action_row, text="Eliminar seleccionado", command=self._delete_selected_user)
        del_btn.grid(row=0, column=1, sticky="ew", padx=(0, 8))

        self.run_btn = ttk.Button(action_row, text="Generar ICS con usuario seleccionado", command=self._run_selected_user)
        self.run_btn.grid(row=0, column=2, sticky="ew")

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=1)
        frame.rowconfigure(2, weight=1)

    def _build_reminders_tab(self) -> None:
        frame = ttk.Frame(self.reminders_tab, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(0, weight=1)

        ttk.Label(frame, text="Recordatorios", font=("TkDefaultFont", 11, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text="Personaliza el tiempo de alerta para el primer evento y los siguientes eventos.", foreground="gray", wraplength=760, justify=tk.LEFT).grid(row=1, column=0, sticky="w", pady=(2, 14))

        self.reminders_enabled_check = ttk.Checkbutton(frame, text="Activar recordatorios", variable=self.reminders_enabled_var, command=self._on_reminders_toggled)
        self.reminders_enabled_check.grid(row=2, column=0, sticky="w", pady=(0, 10))

        ttk.Label(frame, text="Recordatorio del primer evento (minutos antes)").grid(row=3, column=0, sticky="w")
        self.first_event_reminder_entry = ttk.Entry(frame, textvariable=self.first_event_reminder_var)
        self.first_event_reminder_entry.grid(row=4, column=0, sticky="ew", pady=(0, 10))

        ttk.Label(frame, text="Recordatorio de los siguientes eventos (minutos antes)").grid(row=5, column=0, sticky="w")
        self.other_events_reminder_entry = ttk.Entry(frame, textvariable=self.other_events_reminder_var)
        self.other_events_reminder_entry.grid(row=6, column=0, sticky="ew", pady=(0, 12))

        button_row = ttk.Frame(frame)
        button_row.grid(row=7, column=0, sticky="w")
        self.save_reminders_btn = ttk.Button(button_row, text="Guardar recordatorios", command=self._save_reminders_settings)
        self.save_reminders_btn.pack(side=tk.LEFT)

        self._on_reminders_toggled()

    def _build_nextcloud_tab(self) -> None:
        frame = ttk.Frame(self.nextcloud_tab, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(0, weight=1)

        ttk.Label(frame, text="Nextcloud", font=("TkDefaultFont", 11, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text="Configura la subida, el enlace publico y la verificacion de conexion.", foreground="gray", wraplength=760, justify=tk.LEFT).grid(row=1, column=0, sticky="w", pady=(2, 14))

        self.nextcloud_enabled_check = ttk.Checkbutton(frame, text="Subir .ics a Nextcloud al finalizar", variable=self.nextcloud_enabled_var, command=self._on_nextcloud_toggled)
        self.nextcloud_enabled_check.grid(row=2, column=0, sticky="w")

        ttk.Label(frame, text="URL del servidor Nextcloud").grid(row=3, column=0, sticky="w", pady=(10, 0))
        self.nextcloud_server_entry = ttk.Entry(frame, textvariable=self.nextcloud_server_url_var)
        self.nextcloud_server_entry.grid(row=4, column=0, sticky="ew")

        ttk.Label(frame, text="Token Bearer").grid(row=5, column=0, sticky="w", pady=(10, 0))
        self.nextcloud_token_entry = ttk.Entry(frame, textvariable=self.nextcloud_bearer_token_var, show="*")
        self.nextcloud_token_entry.grid(row=6, column=0, sticky="ew")

        ttk.Label(frame, text="Ruta remota completa").grid(row=7, column=0, sticky="w", pady=(10, 0))
        self.nextcloud_path_entry = ttk.Entry(frame, textvariable=self.nextcloud_remote_path_var)
        self.nextcloud_path_entry.grid(row=8, column=0, sticky="ew")

        ttk.Label(frame, text="Timeout de subida (segundos)").grid(row=9, column=0, sticky="w", pady=(10, 0))
        self.nextcloud_timeout_entry = ttk.Entry(frame, textvariable=self.nextcloud_timeout_var)
        self.nextcloud_timeout_entry.grid(row=10, column=0, sticky="ew")

        self.nextcloud_test_btn = ttk.Button(frame, text="Probar conexion Nextcloud", command=self._test_nextcloud_connection)
        self.nextcloud_test_btn.grid(row=11, column=0, sticky="w", pady=(12, 0))

        ttk.Separator(frame).grid(row=12, column=0, sticky="ew", pady=14)

        ttk.Label(frame, text="URL publica de suscripcion ICS").grid(row=13, column=0, sticky="w")
        self.subscription_url_entry = ttk.Entry(frame, textvariable=self.subscription_url_var)
        self.subscription_url_entry.grid(row=14, column=0, sticky="ew")

        button_row = ttk.Frame(frame)
        button_row.grid(row=15, column=0, sticky="ew", pady=(10, 0))
        self.copy_subscription_btn = ttk.Button(button_row, text="Copiar enlace ICS", command=self._copy_subscription_link)
        self.copy_subscription_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.save_nextcloud_btn = ttk.Button(button_row, text="Guardar configuración Nextcloud", command=self._save_nextcloud_settings)
        self.save_nextcloud_btn.pack(side=tk.LEFT)

        ttk.Label(frame, textvariable=self.last_nextcloud_upload_var).grid(row=16, column=0, sticky="w", pady=(12, 0))

    def _build_terminal_tab(self) -> None:
        frame = ttk.Frame(self.terminal_tab, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)

        header = ttk.Frame(frame)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(header, text="Terminal de logs", font=("TkDefaultFont", 11, "bold")).pack(side=tk.LEFT)
        ttk.Button(header, text="Limpiar consola", command=self._clear_console).pack(side=tk.RIGHT)

        self.console_text = scrolledtext.ScrolledText(frame, height=14, wrap=tk.WORD, state=tk.DISABLED)
        self.console_text.grid(row=1, column=0, sticky="nsew")

    def _build_help_tab(self) -> None:
        frame = ttk.Frame(self.help_tab, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="Como usar", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text=(
                "Esta seccion quedara como guia paso a paso para el usuario. "
                "Por ahora solo queda reservada para documentacion y ayudas de uso."
            ),
            foreground="gray",
            wraplength=760,
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(6, 0))

    def _build_advanced_tab(self) -> None:
        frame = ttk.Frame(self.advanced_tab, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        general = ttk.Labelframe(frame, text="Generacion y ciclo", padding=10)
        general.grid(row=0, column=0, columnspan=2, sticky="ew")
        general.columnconfigure(0, weight=1)
        general.columnconfigure(1, weight=1)
        general.columnconfigure(2, weight=1)

        ttk.Label(general, text="URL Login").grid(row=0, column=0, sticky="w")
        self.login_url_entry = ttk.Entry(general)
        self.login_url_entry.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        self.login_url_entry.insert(0, self.data["settings"]["login_url"])

        ttk.Label(general, text="URL Calendario").grid(row=2, column=0, sticky="w")
        self.schedule_url_entry = ttk.Entry(general)
        self.schedule_url_entry.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        self.schedule_url_entry.insert(0, self.data["settings"]["schedule_url"])

        self.lock_cycle_check = ttk.Checkbutton(
            general,
            text="Bloquear ciclo segun la fecha de consulta",
            variable=self.lock_cycle_var,
            command=self._on_cycle_lock_toggled,
        )
        self.lock_cycle_check.grid(row=4, column=0, columnspan=3, sticky="w")

        ttk.Label(general, text="Ciclo academico").grid(row=5, column=0, sticky="w", pady=(10, 0))
        self.cycle_combo = ttk.Combobox(general, values=CYCLE_LABELS, textvariable=self.cycle_var, state="readonly")
        self.cycle_combo.grid(row=6, column=0, sticky="ew", padx=(0, 8))
        self.cycle_combo.bind("<<ComboboxSelected>>", self._on_cycle_changed)

        ttk.Label(general, text="Modo de fecha").grid(row=5, column=1, sticky="w", pady=(10, 0))
        date_mode_frame = ttk.Frame(general)
        date_mode_frame.grid(row=6, column=1, columnspan=2, sticky="w")
        self.date_mode_text_radio = ttk.Radiobutton(date_mode_frame, text="Texto manual", value=DATE_INPUT_MODE_TEXT, variable=self.date_input_mode_var, command=self._on_date_input_mode_changed)
        self.date_mode_text_radio.pack(side=tk.LEFT, padx=(0, 12))
        self.date_mode_dropdown_radio = ttk.Radiobutton(date_mode_frame, text="Desplegable", value=DATE_INPUT_MODE_DROPDOWN, variable=self.date_input_mode_var, command=self._on_date_input_mode_changed)
        self.date_mode_dropdown_radio.pack(side=tk.LEFT)

        ttk.Label(general, text="Desde (DD-MM-YYYY)").grid(row=7, column=0, sticky="w", pady=(10, 0))
        self.start_date_container = ttk.Frame(general)
        self.start_date_container.grid(row=8, column=0, sticky="ew", padx=(0, 8))
        self.start_date_container.columnconfigure(0, weight=1)
        self.start_date_container.columnconfigure(1, weight=1)
        self.start_date_text_frame = ttk.Frame(self.start_date_container)
        self.start_date_text_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.start_date_text_frame.columnconfigure(0, weight=1)
        self.start_date_text_entry = ttk.Entry(self.start_date_text_frame, textvariable=self.start_date_var)
        self.start_date_text_entry.grid(row=0, column=0, sticky="ew")
        self.start_date_text_entry.bind("<FocusOut>", lambda _event: self._on_text_date_focus_out("start"))
        self.start_date_dropdown_frame = ttk.Frame(self.start_date_container)
        self.start_date_dropdown_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.start_date_dropdown_frame.columnconfigure(0, weight=1)
        self.start_date_dropdown_frame.columnconfigure(1, weight=2)
        self.start_date_dropdown_frame.columnconfigure(2, weight=1)
        self.start_day_combo = ttk.Combobox(self.start_date_dropdown_frame, textvariable=self.start_day_var, values=[], state="readonly", width=5)
        self.start_day_combo.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.start_month_combo = ttk.Combobox(self.start_date_dropdown_frame, textvariable=self.start_month_var, values=SPANISH_MONTHS, state="readonly", width=12)
        self.start_month_combo.grid(row=0, column=1, sticky="ew", padx=(0, 4))
        self.start_year_combo = ttk.Combobox(self.start_date_dropdown_frame, textvariable=self.start_year_var, values=self.year_options, state="readonly", width=7)
        self.start_year_combo.grid(row=0, column=2, sticky="ew")
        self.start_day_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_date_picker_changed("start"))
        self.start_month_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_date_picker_changed("start"))
        self.start_year_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_date_picker_changed("start"))

        ttk.Label(general, text="Hasta (DD-MM-YYYY)").grid(row=7, column=1, sticky="w", pady=(10, 0))
        self.end_date_container = ttk.Frame(general)
        self.end_date_container.grid(row=8, column=1, columnspan=2, sticky="ew")
        self.end_date_container.columnconfigure(0, weight=1)
        self.end_date_container.columnconfigure(1, weight=1)
        self.end_date_text_frame = ttk.Frame(self.end_date_container)
        self.end_date_text_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.end_date_text_frame.columnconfigure(0, weight=1)
        self.end_date_text_entry = ttk.Entry(self.end_date_text_frame, textvariable=self.end_date_var)
        self.end_date_text_entry.grid(row=0, column=0, sticky="ew")
        self.end_date_text_entry.bind("<FocusOut>", lambda _event: self._on_text_date_focus_out("end"))
        self.end_date_dropdown_frame = ttk.Frame(self.end_date_container)
        self.end_date_dropdown_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.end_date_dropdown_frame.columnconfigure(0, weight=1)
        self.end_date_dropdown_frame.columnconfigure(1, weight=2)
        self.end_date_dropdown_frame.columnconfigure(2, weight=1)
        self.end_day_combo = ttk.Combobox(self.end_date_dropdown_frame, textvariable=self.end_day_var, values=[], state="readonly", width=5)
        self.end_day_combo.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.end_month_combo = ttk.Combobox(self.end_date_dropdown_frame, textvariable=self.end_month_var, values=SPANISH_MONTHS, state="readonly", width=12)
        self.end_month_combo.grid(row=0, column=1, sticky="ew", padx=(0, 4))
        self.end_year_combo = ttk.Combobox(self.end_date_dropdown_frame, textvariable=self.end_year_var, values=self.year_options, state="readonly", width=7)
        self.end_year_combo.grid(row=0, column=2, sticky="ew")
        self.end_day_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_date_picker_changed("end"))
        self.end_month_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_date_picker_changed("end"))
        self.end_year_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_date_picker_changed("end"))

        ttk.Label(general, textvariable=self.window_hint_var, foreground="gray", wraplength=760, justify=tk.LEFT).grid(row=9, column=0, columnspan=3, sticky="w", pady=(10, 0))

        system = ttk.Labelframe(frame, text="Sistema y mantenimiento", padding=10)
        system.grid(row=1, column=0, sticky="nsew", pady=(12, 0), padx=(0, 6))
        system.columnconfigure(0, weight=1)

        ttk.Label(system, text="Usuario predeterminado", font=("TkDefaultFont", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(system, textvariable=self.default_user_status_var).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(system, text="Autoinicio").grid(row=2, column=0, sticky="w", pady=(10, 0))
        self.autostart_check = ttk.Checkbutton(system, text="Iniciar con Windows", variable=self.autostart_enabled_var, command=self._on_autostart_toggled)
        self.autostart_check.grid(row=3, column=0, sticky="w", pady=(4, 0))
        ttk.Label(system, textvariable=self.autostart_status_var, font=("TkDefaultFont", 9, "bold")).grid(row=4, column=0, sticky="w", pady=(8, 0))
        ttk.Label(system, textvariable=self.autostart_details_var, foreground="gray", wraplength=360, justify=tk.LEFT).grid(row=5, column=0, sticky="w")
        self.repair_autostart_btn = ttk.Button(system, text="Reparar inicio", command=self._repair_autostart)
        self.repair_autostart_btn.grid(row=6, column=0, sticky="w", pady=(8, 0))

        maintenance = ttk.Labelframe(frame, text="Mantenimiento", padding=10)
        maintenance.grid(row=1, column=1, sticky="nsew", pady=(12, 0), padx=(6, 0))
        maintenance.columnconfigure(0, weight=1)
        self.refresh_holidays_btn = ttk.Button(maintenance, text="Forzar actualizacion de feriados", command=self._refresh_holidays_button_clicked)
        self.refresh_holidays_btn.grid(row=0, column=0, sticky="w")
        ttk.Label(maintenance, textvariable=self.holidays_updated_var, foreground="gray").grid(row=1, column=0, sticky="w", pady=(6, 0))

        buttons_row = ttk.Frame(frame)
        buttons_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self.save_advanced_btn = ttk.Button(buttons_row, text="Guardar configuración avanzada", command=self._save_advanced_settings)
        self.save_advanced_btn.pack(side=tk.LEFT)


    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=0, column=0, sticky="nsew")

        self.config_tab = ttk.Frame(self.notebook)
        self.calendar_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.config_tab, text="Configuración")
        self.notebook.add(self.calendar_tab, text="Calendario")

        outer = ttk.Frame(self.config_tab)
        outer.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(outer, highlightthickness=0)
        self.v_scroll = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.v_scroll.set)
        self.v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        frame = ttk.Frame(self.canvas, padding=12)
        self.canvas_window_id = self.canvas.create_window((0, 0), window=frame, anchor="nw")

        frame.bind("<Configure>", self._on_content_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        users_label = ttk.Label(frame, text="Usuarios")
        users_label.grid(row=0, column=0, sticky="w")

        self.tree = ttk.Treeview(frame, columns=("username",), show="headings", height=10)
        self.tree.heading("username", text="Codigo de alumno")
        self.tree.column("username", width=220)
        self.tree.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(4, 8))
        self.tree.bind("<<TreeviewSelect>>", self._on_select_user)

        ttk.Label(frame, text="Codigo").grid(row=2, column=0, sticky="w")
        self.username_entry = ttk.Entry(frame)
        self.username_entry.grid(row=3, column=0, sticky="ew", padx=(0, 8))

        ttk.Label(frame, text="Contraseña").grid(row=2, column=1, sticky="w")
        self.password_entry = ttk.Entry(frame, show="*")
        self.password_entry.grid(row=3, column=1, sticky="ew", padx=(0, 8))

        add_btn = ttk.Button(frame, text="Agregar / Actualizar", command=self._add_or_update_user)
        add_btn.grid(row=3, column=2, sticky="ew")

        del_btn = ttk.Button(frame, text="Eliminar seleccionado", command=self._delete_selected_user)
        del_btn.grid(row=4, column=2, sticky="ew", pady=(8, 0))

        self.set_default_user_btn = ttk.Button(
            frame,
            text="Establecer como predeterminado",
            command=self._set_selected_as_default,
            state=tk.DISABLED,
        )
        self.set_default_user_btn.grid(row=4, column=0, sticky="ew", pady=(8, 0), padx=(0, 8))

        ttk.Label(frame, textvariable=self.default_user_status_var).grid(
            row=4,
            column=1,
            sticky="w",
            pady=(12, 0),
        )

        ttk.Separator(frame).grid(row=5, column=0, columnspan=3, sticky="ew", pady=12)

        ttk.Label(frame, text="URL Login").grid(row=6, column=0, sticky="w")
        self.login_url_entry = ttk.Entry(frame)
        self.login_url_entry.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        self.login_url_entry.insert(0, self.data["settings"]["login_url"])

        ttk.Label(frame, text="URL Calendario").grid(row=8, column=0, sticky="w")
        self.schedule_url_entry = ttk.Entry(frame)
        self.schedule_url_entry.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        self.schedule_url_entry.insert(0, self.data["settings"]["schedule_url"])

        ttk.Label(frame, text="Ciclo academico").grid(row=10, column=0, sticky="w")
        self.cycle_combo = ttk.Combobox(frame, values=CYCLE_LABELS, textvariable=self.cycle_var, state="readonly")
        self.cycle_combo.grid(row=11, column=0, sticky="ew", padx=(0, 8))
        self.cycle_combo.bind("<<ComboboxSelected>>", self._on_cycle_changed)

        ttk.Label(frame, text="Desde (DD-MM-YYYY)").grid(row=10, column=1, sticky="w")
        self.start_date_container = ttk.Frame(frame)
        self.start_date_container.grid(row=11, column=1, sticky="ew", padx=(0, 8))
        self.start_date_container.columnconfigure(0, weight=1)
        self.start_date_container.columnconfigure(1, weight=1)
        self.start_date_text_frame = ttk.Frame(self.start_date_container)
        self.start_date_text_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.start_date_text_frame.columnconfigure(0, weight=1)
        self.start_date_text_entry = ttk.Entry(self.start_date_text_frame, textvariable=self.start_date_var)
        self.start_date_text_entry.grid(row=0, column=0, sticky="ew")
        self.start_date_text_entry.bind("<FocusOut>", lambda _event: self._on_text_date_focus_out("start"))
        self.start_date_dropdown_frame = ttk.Frame(self.start_date_container)
        self.start_date_dropdown_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.start_date_dropdown_frame.columnconfigure(0, weight=1)
        self.start_date_dropdown_frame.columnconfigure(1, weight=2)
        self.start_date_dropdown_frame.columnconfigure(2, weight=1)
        self.start_day_combo = ttk.Combobox(self.start_date_dropdown_frame, textvariable=self.start_day_var, values=[], state="readonly", width=5)
        self.start_day_combo.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.start_month_combo = ttk.Combobox(self.start_date_dropdown_frame, textvariable=self.start_month_var, values=SPANISH_MONTHS, state="readonly", width=12)
        self.start_month_combo.grid(row=0, column=1, sticky="ew", padx=(0, 4))
        self.start_year_combo = ttk.Combobox(self.start_date_dropdown_frame, textvariable=self.start_year_var, values=self.year_options, state="readonly", width=7)
        self.start_year_combo.grid(row=0, column=2, sticky="ew")
        self.start_day_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_date_picker_changed("start"))
        self.start_month_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_date_picker_changed("start"))
        self.start_year_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_date_picker_changed("start"))

        ttk.Label(frame, text="Hasta (DD-MM-YYYY)").grid(row=10, column=2, sticky="w")
        self.end_date_container = ttk.Frame(frame)
        self.end_date_container.grid(row=11, column=2, sticky="ew")
        self.end_date_container.columnconfigure(0, weight=1)
        self.end_date_container.columnconfigure(1, weight=1)
        self.end_date_text_frame = ttk.Frame(self.end_date_container)
        self.end_date_text_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.end_date_text_frame.columnconfigure(0, weight=1)
        self.end_date_text_entry = ttk.Entry(self.end_date_text_frame, textvariable=self.end_date_var)
        self.end_date_text_entry.grid(row=0, column=0, sticky="ew")
        self.end_date_text_entry.bind("<FocusOut>", lambda _event: self._on_text_date_focus_out("end"))
        self.end_date_dropdown_frame = ttk.Frame(self.end_date_container)
        self.end_date_dropdown_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.end_date_dropdown_frame.columnconfigure(0, weight=1)
        self.end_date_dropdown_frame.columnconfigure(1, weight=2)
        self.end_date_dropdown_frame.columnconfigure(2, weight=1)
        self.end_day_combo = ttk.Combobox(self.end_date_dropdown_frame, textvariable=self.end_day_var, values=[], state="readonly", width=5)
        self.end_day_combo.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.end_month_combo = ttk.Combobox(self.end_date_dropdown_frame, textvariable=self.end_month_var, values=SPANISH_MONTHS, state="readonly", width=12)
        self.end_month_combo.grid(row=0, column=1, sticky="ew", padx=(0, 4))
        self.end_year_combo = ttk.Combobox(self.end_date_dropdown_frame, textvariable=self.end_year_var, values=self.year_options, state="readonly", width=7)
        self.end_year_combo.grid(row=0, column=2, sticky="ew")
        self.end_day_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_date_picker_changed("end"))
        self.end_month_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_date_picker_changed("end"))
        self.end_year_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_date_picker_changed("end"))

        ttk.Label(frame, textvariable=self.window_hint_var).grid(row=12, column=0, columnspan=3, sticky="w", pady=(4, 8))

        advanced = ttk.Labelframe(frame, text="Ajustes avanzados", padding=8)
        advanced.grid(row=13, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        self.lock_cycle_check = ttk.Checkbutton(
            advanced,
            text="Bloquear ciclo segun la fecha de consulta",
            variable=self.lock_cycle_var,
            command=self._on_cycle_lock_toggled,
        )
        self.lock_cycle_check.grid(row=0, column=0, sticky="w")

        ttk.Label(advanced, text="Modo de fecha").grid(row=1, column=0, sticky="w", pady=(8, 0))
        date_mode_frame = ttk.Frame(advanced)
        date_mode_frame.grid(row=2, column=0, sticky="w")
        self.date_mode_text_radio = ttk.Radiobutton(
            date_mode_frame,
            text="Texto manual",
            value=DATE_INPUT_MODE_TEXT,
            variable=self.date_input_mode_var,
            command=self._on_date_input_mode_changed,
        )
        self.date_mode_text_radio.grid(row=0, column=0, sticky="w", padx=(0, 12))
        self.date_mode_dropdown_radio = ttk.Radiobutton(
            date_mode_frame,
            text="Desplegable por dia, mes y anio",
            value=DATE_INPUT_MODE_DROPDOWN,
            variable=self.date_input_mode_var,
            command=self._on_date_input_mode_changed,
        )
        self.date_mode_dropdown_radio.grid(row=0, column=1, sticky="w")
        ttk.Label(
            advanced,
            text="El desplegable oculta meses fuera del ciclo activo cuando el bloqueo por ciclo está activado.",
            foreground="gray",
            wraplength=320,
            justify=tk.LEFT,
        ).grid(row=3, column=0, sticky="w", pady=(4, 0))

        ttk.Label(advanced, text="Recordatorio primer evento (minutos antes)").grid(row=4, column=0, sticky="w", pady=(10, 0))
        self.first_event_reminder_entry = ttk.Entry(advanced, textvariable=self.first_event_reminder_var)
        self.first_event_reminder_entry.grid(row=5, column=0, sticky="ew")

        ttk.Label(advanced, text="Recordatorio siguientes eventos (minutos antes)").grid(row=6, column=0, sticky="w", pady=(8, 0))
        self.other_events_reminder_entry = ttk.Entry(advanced, textvariable=self.other_events_reminder_var)
        self.other_events_reminder_entry.grid(row=7, column=0, sticky="ew")

        ttk.Separator(advanced).grid(row=8, column=0, sticky="ew", pady=(10, 8))

        self.nextcloud_check = ttk.Checkbutton(
            advanced,
            text="Subir .ics a Nextcloud al finalizar",
            variable=self.nextcloud_enabled_var,
            command=self._on_nextcloud_toggled,
        )
        self.nextcloud_check.grid(row=9, column=0, sticky="w")

        ttk.Label(advanced, text="URL servidor Nextcloud").grid(row=10, column=0, sticky="w", pady=(8, 0))
        self.nextcloud_server_entry = ttk.Entry(advanced, textvariable=self.nextcloud_server_url_var)
        self.nextcloud_server_entry.grid(row=11, column=0, sticky="ew")

        ttk.Label(advanced, text="Token Bearer").grid(row=12, column=0, sticky="w", pady=(8, 0))
        self.nextcloud_token_entry = ttk.Entry(advanced, textvariable=self.nextcloud_bearer_token_var, show="*")
        self.nextcloud_token_entry.grid(row=13, column=0, sticky="ew")

        ttk.Label(advanced, text="Ruta remota completa").grid(row=14, column=0, sticky="w", pady=(8, 0))
        self.nextcloud_path_entry = ttk.Entry(advanced, textvariable=self.nextcloud_remote_path_var)
        self.nextcloud_path_entry.grid(row=15, column=0, sticky="ew")

        ttk.Label(advanced, text="Timeout subida (segundos)").grid(row=16, column=0, sticky="w", pady=(8, 0))
        self.nextcloud_timeout_entry = ttk.Entry(advanced, textvariable=self.nextcloud_timeout_var)
        self.nextcloud_timeout_entry.grid(row=17, column=0, sticky="ew")

        self.nextcloud_test_btn = ttk.Button(
            advanced,
            text="Probar conexion Nextcloud",
            command=self._test_nextcloud_connection,
        )
        self.nextcloud_test_btn.grid(row=18, column=0, sticky="w", pady=(8, 0))

        ttk.Label(advanced, text="URL publica de suscripcion ICS").grid(row=19, column=0, sticky="w", pady=(8, 0))
        self.subscription_url_entry = ttk.Entry(advanced, textvariable=self.subscription_url_var)
        self.subscription_url_entry.grid(row=20, column=0, sticky="ew")

        self.refresh_holidays_btn = ttk.Button(
            advanced,
            text="Forzar actualizacion de feriados",
            command=self._refresh_holidays_button_clicked,
        )
        self.refresh_holidays_btn.grid(row=21, column=0, sticky="w", pady=(8, 0))

        ttk.Label(advanced, textvariable=self.holidays_updated_var).grid(row=22, column=0, sticky="w", pady=(6, 0))

        ttk.Separator(advanced).grid(row=23, column=0, sticky="ew", pady=(10, 8))

        ttk.Label(advanced, text="Usuario predeterminado para autoinicio").grid(row=24, column=0, sticky="w")
        ttk.Label(advanced, textvariable=self.default_user_status_var).grid(row=25, column=0, sticky="w", pady=(4, 0))

        # Checkbox para activar/desactivar autoinicio
        self.autostart_check = ttk.Checkbutton(
            advanced,
            text="Iniciar con Windows",
            variable=self.autostart_enabled_var,
            command=self._on_autostart_toggled,
        )
        self.autostart_check.grid(row=26, column=0, sticky="w", pady=(12, 4))

        # Botón de acciones de autoinicio
        autostart_actions = ttk.Frame(advanced)
        autostart_actions.grid(row=27, column=0, sticky="ew", pady=(8, 0))
        autostart_actions.columnconfigure(0, weight=1)

        self.repair_autostart_btn = ttk.Button(
            autostart_actions,
            text="Reparar inicio",
            command=self._repair_autostart,
        )
        self.repair_autostart_btn.grid(row=0, column=0, sticky="ew")

        # Estado y detalles del autoinicio
        ttk.Label(advanced, textvariable=self.autostart_status_var, font=("TkDefaultFont", 9, "bold")).grid(row=28, column=0, sticky="w", pady=(8, 2))
        ttk.Label(advanced, textvariable=self.autostart_details_var, justify=tk.LEFT, foreground="gray").grid(row=29, column=0, sticky="ew", pady=(0, 8))

        advanced.columnconfigure(0, weight=1)
        self._on_nextcloud_toggled()

        self.copy_subscription_btn = ttk.Button(frame, text="Copiar enlace ICS", command=self._copy_subscription_link)
        self.copy_subscription_btn.grid(row=14, column=1, sticky="e")

        self.run_btn = ttk.Button(frame, text="Generar ICS con usuario seleccionado", command=self._run_selected_user)
        self.run_btn.grid(row=14, column=2, sticky="e")

        status = ttk.Label(frame, textvariable=self.status_var)
        status.grid(row=15, column=0, columnspan=3, sticky="w", pady=(12, 0))

        ttk.Label(frame, text="Consola en tiempo real").grid(row=15, column=0, sticky="w", pady=(10, 4))
        clear_btn = ttk.Button(frame, text="Limpiar consola", command=self._clear_console)
        clear_btn.grid(row=15, column=2, sticky="e", pady=(10, 4))

        self.console_text = scrolledtext.ScrolledText(frame, height=10, wrap=tk.WORD, state=tk.DISABLED)
        self.console_text.grid(row=16, column=0, columnspan=3, sticky="nsew")

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=1)
        frame.rowconfigure(1, weight=1)
        frame.rowconfigure(16, weight=1)

        footer = ttk.Frame(self.root, padding=(12, 0, 12, 10))
        footer.grid(row=1, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)

        actions_row = ttk.Frame(footer)
        actions_row.pack(fill=tk.X, pady=(0, 6))
        self.save_settings_btn = ttk.Button(actions_row, text="Guardar configuracion", command=self._save_settings)
        self.save_settings_btn.pack(side=tk.LEFT)

        progress_row = ttk.Frame(footer)
        progress_row.pack(fill=tk.X)

        self.progress_bar = ttk.Progressbar(
            progress_row,
            orient=tk.HORIZONTAL,
            mode="determinate",
            maximum=100,
            variable=self.progress_var,
        )
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(progress_row, textvariable=self.progress_pct_var, width=6, anchor="e").pack(side=tk.RIGHT, padx=(8, 0))

        ttk.Label(footer, textvariable=self.status_var).pack(anchor="w", pady=(4, 0))

        info_row = ttk.Frame(footer)
        info_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(info_row, text="Última generación .ics:", width=20, anchor="w").pack(side=tk.LEFT)
        ttk.Label(info_row, textvariable=self.last_ics_gen_var, width=24, anchor="w").pack(side=tk.LEFT)
        ttk.Label(info_row, text="Última subida Nextcloud:", width=22, anchor="w").pack(side=tk.LEFT, padx=(12, 0))
        ttk.Label(info_row, textvariable=self.last_nextcloud_upload_var, width=24, anchor="w").pack(side=tk.LEFT)

        self._build_calendar_tab()
        self._reload_calendar_from_disk()

    def _build_calendar_tab(self) -> None:
        container = ttk.Frame(self.calendar_tab, padding=12)
        container.pack(fill=tk.BOTH, expand=True)

        toolbar = ttk.Frame(container)
        toolbar.pack(fill=tk.X)

        month_nav = ttk.Frame(toolbar)
        month_nav.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.prev_month_btn = ttk.Button(month_nav, text="< Mes", command=lambda: self._move_calendar_month(-1))
        self.prev_month_btn.pack(side=tk.LEFT)
        self.month_label = ttk.Label(month_nav, textvariable=self.calendar_month_var, anchor="center", font=("TkDefaultFont", 11, "bold"))
        self.month_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        self.next_month_btn = ttk.Button(month_nav, text="Mes >", command=lambda: self._move_calendar_month(1))
        self.next_month_btn.pack(side=tk.LEFT)

        day_nav = ttk.Frame(toolbar)
        day_nav.pack(side=tk.RIGHT)
        ttk.Button(day_nav, text="< Día", command=lambda: self._move_calendar_day(-1)).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(day_nav, text="Hoy", command=self._jump_to_today).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(day_nav, text="Día >", command=lambda: self._move_calendar_day(1)).pack(side=tk.LEFT)

        ttk.Label(container, textvariable=self.calendar_status_var, foreground="gray").pack(anchor="w", pady=(8, 10))

        self.calendar_grid_frame = ttk.Frame(container)
        self.calendar_grid_frame.pack(fill=tk.BOTH, expand=False)

        agenda_frame = ttk.Labelframe(container, text="Eventos del día", padding=10)
        agenda_frame.pack(fill=tk.BOTH, expand=True, pady=(12, 0))

        agenda_header = ttk.Frame(agenda_frame)
        agenda_header.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(agenda_header, textvariable=self.calendar_selected_day_var, font=("TkDefaultFont", 10, "bold")).pack(side=tk.LEFT)
        ttk.Button(agenda_header, text="Actualizar desde ICS", command=self._reload_calendar_from_disk).pack(side=tk.RIGHT)

        tree_frame = ttk.Frame(agenda_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self.calendar_tree = ttk.Treeview(tree_frame, columns=("hora", "curso", "aula"), show="headings", height=10)
        self.calendar_tree.heading("hora", text="Hora")
        self.calendar_tree.heading("curso", text="Curso")
        self.calendar_tree.heading("aula", text="Aula")
        self.calendar_tree.column("hora", width=110, anchor="center")
        self.calendar_tree.column("curso", width=340, anchor="w")
        self.calendar_tree.column("aula", width=140, anchor="w")
        self.calendar_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tree_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.calendar_tree.yview)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.calendar_tree.configure(yscrollcommand=tree_scroll.set)

    def _calendar_ics_path(self) -> Path:
        base_dir = Path(__file__).resolve().parent
        output_dir_raw = os.environ.get("OUTPUT_DIR", "public").strip()
        output_dir_path = Path(output_dir_raw or "public")
        if not output_dir_path.is_absolute():
            output_dir_path = base_dir / output_dir_path

        output_filename = os.environ.get("OUTPUT_FILENAME", "horario.ics").strip() or "horario.ics"
        return output_dir_path / output_filename

    def _coerce_calendar_datetime(self, value) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, time.min)
        return None

    def _load_calendar_events(self) -> list[CalendarEventItem]:
        ics_path = self._calendar_ics_path()
        if not ics_path.exists():
            self.calendar_status_var.set(f"No existe el ICS generado en {ics_path.name}")
            return []

        try:
            calendar = ICalendar.from_ical(ics_path.read_bytes())
        except Exception as exc:
            logger.warning("No se pudo leer el ICS para el calendario: %s", exc)
            self.calendar_status_var.set("No se pudo leer el último ICS generado")
            return []

        events: list[CalendarEventItem] = []
        for component in calendar.walk("VEVENT"):
            try:
                dtstart_raw = component.decoded("dtstart")
            except Exception:
                continue

            dtend_raw = component.decoded("dtend") if component.get("dtend") else dtstart_raw
            dtstart = self._coerce_calendar_datetime(dtstart_raw)
            dtend = self._coerce_calendar_datetime(dtend_raw) or dtstart
            if dtstart is None or dtend is None:
                continue

            summary = str(component.get("summary") or "Clase").strip() or "Clase"
            location = str(component.get("location") or "").strip()
            description = str(component.get("description") or "").strip()
            events.append(
                CalendarEventItem(
                    event_date=dtstart.date(),
                    start_dt=dtstart,
                    end_dt=dtend,
                    summary=summary,
                    location=location,
                    description=description,
                )
            )

        events.sort(key=lambda item: (item.event_date, item.start_dt, item.summary.lower(), item.location.lower()))
        self.calendar_status_var.set(f"{len(events)} eventos cargados desde {ics_path.name}")
        return events

    def _reload_calendar_from_disk(self) -> None:
        self.calendar_events = self._load_calendar_events()
        self.calendar_events_by_date = {}
        for event in self.calendar_events:
            self.calendar_events_by_date.setdefault(event.event_date, []).append(event)

        if self.calendar_events:
            if self.calendar_selected_date not in self.calendar_events_by_date:
                self.calendar_selected_date = self.calendar_events[0].event_date
            self.calendar_visible_year = self.calendar_selected_date.year
            self.calendar_visible_month = self.calendar_selected_date.month
        else:
            today = date.today()
            self.calendar_selected_date = today
            self.calendar_visible_year = today.year
            self.calendar_visible_month = today.month

        self._render_calendar_month()
        self._render_calendar_agenda()

    def _render_calendar_month(self) -> None:
        if not hasattr(self, "calendar_grid_frame"):
            return

        for child in self.calendar_grid_frame.winfo_children():
            child.destroy()

        month_date = date(self.calendar_visible_year, self.calendar_visible_month, 1)
        self.calendar_month_var.set(f"{CALENDAR_MONTH_NAMES[self.calendar_visible_month - 1]} {self.calendar_visible_year}")

        day_names = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
        for column, label_text in enumerate(day_names):
            header = ttk.Label(self.calendar_grid_frame, text=label_text, anchor="center")
            header.grid(row=0, column=column, sticky="ew", padx=2, pady=(0, 4))

        start_grid = month_date - timedelta(days=month_date.weekday())
        for row in range(1, 7):
            self.calendar_grid_frame.rowconfigure(row, weight=1)
        for column in range(7):
            self.calendar_grid_frame.columnconfigure(column, weight=1)

        for index in range(42):
            cell_date = start_grid + timedelta(days=index)
            row = index // 7 + 1
            column = index % 7
            events = self.calendar_events_by_date.get(cell_date, [])
            is_current_month = cell_date.month == self.calendar_visible_month
            is_selected = cell_date == self.calendar_selected_date
            is_today = cell_date == date.today()

            if is_selected:
                bg = "#1f6feb"
                fg = "white"
            elif is_today:
                bg = "#dff3ff"
                fg = "#0f172a"
            elif not is_current_month:
                bg = "#f4f4f4"
                fg = "#8a8a8a"
            else:
                bg = "white"
                fg = "#111111"

            cell_text = [str(cell_date.day)]
            for event in events[:2]:
                summary = event.summary if len(event.summary) <= 22 else f"{event.summary[:21]}…"
                cell_text.append(f"{event.start_dt.strftime('%H:%M')} {summary}")
            if len(events) > 2:
                cell_text.append(f"+{len(events) - 2} más")

            button = tk.Button(
                self.calendar_grid_frame,
                text="\n".join(cell_text),
                command=lambda day=cell_date: self._select_calendar_date(day),
                wraplength=130,
                justify=tk.LEFT,
                anchor="nw",
                bg=bg,
                fg=fg,
                activebackground=bg,
                activeforeground=fg,
                relief="solid",
                borderwidth=1,
                font=("Segoe UI", 9),
                padx=6,
                pady=6,
            )
            button.grid(row=row, column=column, sticky="nsew", padx=2, pady=2)

    def _render_calendar_agenda(self) -> None:
        if not hasattr(self, "calendar_tree"):
            return

        for item in self.calendar_tree.get_children():
            self.calendar_tree.delete(item)

        selected_events = self.calendar_events_by_date.get(self.calendar_selected_date, [])
        self.calendar_selected_day_var.set(format_date(self.calendar_selected_date))

        if not selected_events:
            self.calendar_tree.insert("", tk.END, values=("", "Sin eventos", ""))
            return

        for event in selected_events:
            time_range = f"{event.start_dt.strftime('%H:%M')} - {event.end_dt.strftime('%H:%M')}"
            room = event.location or "Por definir"
            self.calendar_tree.insert("", tk.END, values=(time_range, event.summary, room))

    def _select_calendar_date(self, selected_date: date) -> None:
        self.calendar_selected_date = selected_date
        self.calendar_visible_year = selected_date.year
        self.calendar_visible_month = selected_date.month
        self._render_calendar_month()
        self._render_calendar_agenda()

    def _move_calendar_month(self, delta: int) -> None:
        current_year = self.calendar_visible_year
        current_month = self.calendar_visible_month
        month_index = (current_year * 12 + (current_month - 1)) + delta
        new_year, zero_based_month = divmod(month_index, 12)
        new_month = zero_based_month + 1
        day = min(self.calendar_selected_date.day, monthrange(new_year, new_month)[1])
        self._select_calendar_date(date(new_year, new_month, day))

    def _move_calendar_day(self, delta: int) -> None:
        self._select_calendar_date(self.calendar_selected_date + timedelta(days=delta))

    def _jump_to_today(self) -> None:
        self._select_calendar_date(date.today())

    def _on_content_configure(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self.canvas_window_id, width=event.width)

    def _on_mousewheel(self, event) -> None:
        if not self.canvas.winfo_exists():
            return
        if hasattr(self, "notebook") and hasattr(self, "user_tab"):
            try:
                if self.notebook.index(self.notebook.select()) != self.notebook.index(self.user_tab):
                    return
            except Exception:
                return
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _set_progress(self, percent: int, message: str | None = None) -> None:
        bounded = max(0, min(100, int(percent)))
        self.progress_var.set(bounded)
        self.progress_pct_var.set(f"{bounded}%")
        if message:
            self.status_var.set(message)

    def _progress_from_pipeline(self, percent: int, message: str) -> None:
        self.root.after(0, lambda: self._set_progress(percent, message))

    def _initialize_cycle_controls(self) -> None:
        today = date.today()
        detected_cycle = detect_cycle_for_date(today)
        saved_cycle = normalize_cycle_name(str(self.data["settings"].get("selected_cycle", "")))
        selected_cycle = detected_cycle if self.lock_cycle_var.get() or not saved_cycle else saved_cycle
        self.cycle_var.set(selected_cycle or detected_cycle)

        start_date, end_date = default_selection_window(today)
        self._set_date_range(start_date, end_date)
        self._apply_cycle_constraints(force_update=True)

    def _set_date_range(self, start_date: date, end_date: date) -> None:
        self.start_date_var.set(format_date(start_date))
        self.end_date_var.set(format_date(end_date))
        self._set_date_picker("start", start_date)
        self._set_date_picker("end", end_date)

    def _parse_date_range(self) -> tuple[date, date]:
        start_date = parse_date(self.start_date_var.get())
        end_date = parse_date(self.end_date_var.get())
        if end_date < start_date:
            end_date = start_date
        return start_date, end_date

    def _set_date_picker(self, prefix: str, value: date) -> None:
        day_var = getattr(self, f"{prefix}_day_var")
        month_var = getattr(self, f"{prefix}_month_var")
        year_var = getattr(self, f"{prefix}_year_var")

        year_var.set(str(value.year))
        month_var.set(SPANISH_MONTHS[value.month - 1])
        self._refresh_date_day_options(prefix, preferred_day=value.day)
        day_var.set(str(value.day))

    def _refresh_date_day_options(self, prefix: str, preferred_day: int | None = None) -> None:
        day_var = getattr(self, f"{prefix}_day_var")
        month_var = getattr(self, f"{prefix}_month_var")
        year_var = getattr(self, f"{prefix}_year_var")
        day_combo = getattr(self, f"{prefix}_day_combo")

        month = MONTH_TO_NUMBER.get(month_var.get(), date.today().month)
        try:
            year = int(year_var.get())
        except ValueError:
            year = date.today().year

        max_day = monthrange(year, month)[1]
        day_combo.configure(values=[str(day) for day in range(1, max_day + 1)])

        try:
            current_day = int(preferred_day if preferred_day is not None else day_var.get())
        except Exception:
            current_day = 1

        day_var.set(str(max(1, min(current_day, max_day))))

    def _read_date_picker(self, prefix: str) -> date:
        day_var = getattr(self, f"{prefix}_day_var")
        month_var = getattr(self, f"{prefix}_month_var")
        year_var = getattr(self, f"{prefix}_year_var")

        try:
            day = int(day_var.get())
            month = MONTH_TO_NUMBER[month_var.get()]
            year = int(year_var.get())
        except Exception as exc:
            raise ValueError("Fecha invalida") from exc

        max_day = monthrange(year, month)[1]
        if day < 1 or day > max_day:
            raise ValueError("Fecha invalida")
        return date(year, month, day)

    def _on_date_picker_changed(self, prefix: str) -> None:
        self._refresh_date_day_options(prefix)
        try:
            selected_date = self._read_date_picker(prefix)
        except Exception:
            return

        if prefix == "start":
            self.start_date_var.set(format_date(selected_date))
        else:
            self.end_date_var.set(format_date(selected_date))

    def _selected_cycle_bounds(self) -> tuple[date, date]:
        cycle_name = normalize_cycle_name(self.cycle_var.get()) or detect_cycle_for_date(date.today())
        return cycle_bounds(cycle_name, date.today().year)

    def _normalize_date_input_mode(self, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized == DATE_INPUT_MODE_TEXT:
            return DATE_INPUT_MODE_TEXT
        return DATE_INPUT_MODE_DROPDOWN

    def _is_dropdown_date_mode(self) -> bool:
        return self._normalize_date_input_mode(self.date_input_mode_var.get()) == DATE_INPUT_MODE_DROPDOWN

    def _allowed_month_numbers(self) -> list[int]:
        if not self.lock_cycle_var.get():
            return list(range(1, 13))

        cycle_name = normalize_cycle_name(self.cycle_var.get()) or detect_cycle_for_date(date.today())
        return list(MONTHS_BY_CYCLE.get(cycle_name, range(1, 13)))

    def _allowed_month_names(self) -> list[str]:
        return [SPANISH_MONTHS[month - 1] for month in self._allowed_month_numbers()]

    def _sync_date_input_mode_ui(self) -> None:
        self.date_input_mode_var.set(self._normalize_date_input_mode(self.date_input_mode_var.get()))

        if self._is_dropdown_date_mode():
            self.start_date_text_frame.grid_remove()
            self.end_date_text_frame.grid_remove()
            self.start_date_dropdown_frame.grid()
            self.end_date_dropdown_frame.grid()
        else:
            self.start_date_dropdown_frame.grid_remove()
            self.end_date_dropdown_frame.grid_remove()
            self.start_date_text_frame.grid()
            self.end_date_text_frame.grid()

        self._refresh_date_picker_options()

    def _refresh_date_picker_options(self) -> None:
        allowed_month_names = self._allowed_month_names()
        month_values = allowed_month_names if self._is_dropdown_date_mode() else SPANISH_MONTHS

        self.start_month_combo.configure(values=month_values)
        self.end_month_combo.configure(values=month_values)
        self.start_year_combo.configure(values=self.year_options)
        self.end_year_combo.configure(values=self.year_options)

        self._refresh_date_day_options("start")
        self._refresh_date_day_options("end")

        if self._is_dropdown_date_mode():
            self._normalize_dropdown_selection("start", allowed_month_names)
            self._normalize_dropdown_selection("end", allowed_month_names)
        elif self.lock_cycle_var.get():
            self._clamp_text_dates_to_cycle()

    def _clamp_text_dates_to_cycle(self) -> None:
        try:
            start_date = parse_date(self.start_date_var.get())
            end_date = parse_date(self.end_date_var.get())
        except Exception:
            return

        cycle_start, cycle_end = self._selected_cycle_bounds()
        start_date, end_date = clamp_window(start_date, end_date, cycle_start, cycle_end)
        self.start_date_var.set(format_date(start_date))
        self.end_date_var.set(format_date(end_date))

    def _on_text_date_focus_out(self, prefix: str) -> None:
        if self._is_dropdown_date_mode():
            return

        try:
            selected_date = parse_date(self.start_date_var.get() if prefix == "start" else self.end_date_var.get())
        except Exception:
            return

        if self.lock_cycle_var.get():
            cycle_start, cycle_end = self._selected_cycle_bounds()
            selected_date = min(max(selected_date, cycle_start), cycle_end)

        if prefix == "start":
            self.start_date_var.set(format_date(selected_date))
        else:
            self.end_date_var.set(format_date(selected_date))

    def _normalize_dropdown_selection(self, prefix: str, allowed_month_names: list[str]) -> None:
        month_var = getattr(self, f"{prefix}_month_var")
        if month_var.get() not in allowed_month_names:
            fallback_month = allowed_month_names[0] if allowed_month_names else SPANISH_MONTHS[0]
            month_var.set(fallback_month)

        self._refresh_date_day_options(prefix)

        try:
            selected_date = self._read_date_picker(prefix)
        except Exception:
            return

        if prefix == "start":
            self.start_date_var.set(format_date(selected_date))
        else:
            self.end_date_var.set(format_date(selected_date))

    def _apply_cycle_constraints(self, force_update: bool = False) -> None:
        today = date.today()
        detected_cycle = detect_cycle_for_date(today)

        if self.lock_cycle_var.get():
            self.cycle_var.set(detected_cycle)
            self.cycle_combo.config(state="disabled")
            selected_cycle = detected_cycle
        else:
            self.cycle_combo.config(state="readonly")
            selected_cycle = normalize_cycle_name(self.cycle_var.get()) or detected_cycle
            self.cycle_var.set(selected_cycle)

        cycle_start, cycle_end = cycle_bounds(selected_cycle, today.year)
        self._refresh_date_picker_options()

        try:
            current_start, current_end = self._parse_date_range()
        except Exception:
            current_start, current_end = default_selection_window(today)

        if force_update or self.lock_cycle_var.get():
            current_start, current_end = default_selection_window(today)

        if current_end < cycle_start or current_start > cycle_end:
            current_start = cycle_start
            current_end = min(cycle_start + timedelta(days=37), cycle_end)
        else:
            current_start, current_end = clamp_window(current_start, current_end, cycle_start, cycle_end)

        self._set_date_range(current_start, current_end)
        self.window_hint_var.set(
            f"Ventana permitida: {format_date(cycle_start)} a {format_date(cycle_end)} | Ciclo activo: {selected_cycle}"
        )
        self._refresh_date_picker_options()

    def _on_date_input_mode_changed(self) -> None:
        self.date_input_mode_var.set(self._normalize_date_input_mode(self.date_input_mode_var.get()))

        try:
            start_date, end_date = self._parse_date_range()
        except Exception:
            start_date, end_date = default_selection_window(date.today())

        self._set_date_range(start_date, end_date)
        self._sync_date_input_mode_ui()

    def _on_cycle_changed(self, _event=None) -> None:
        if self.lock_cycle_var.get():
            self.cycle_var.set(detect_cycle_for_date(date.today()))
        self._apply_cycle_constraints()

    def _on_cycle_lock_toggled(self) -> None:
        self._apply_cycle_constraints(force_update=True)
        self._sync_date_input_mode_ui()

    def _on_nextcloud_toggled(self) -> None:
        state = tk.NORMAL if self.nextcloud_enabled_var.get() else tk.DISABLED
        self.nextcloud_server_entry.config(state=state)
        self.nextcloud_token_entry.config(state=state)
        self.nextcloud_path_entry.config(state=state)
        self.nextcloud_timeout_entry.config(state=state)
        self.nextcloud_test_btn.config(state=state)

    def _on_reminders_toggled(self) -> None:
        state = tk.NORMAL if self.reminders_enabled_var.get() else tk.DISABLED
        self.first_event_reminder_entry.config(state=state)
        self.other_events_reminder_entry.config(state=state)

    def _refresh_holidays_status(self) -> None:
        self.holidays_updated_var.set(f"Actualizado a: {get_holiday_cache_updated_at()}")

    def _resolve_subscription_link(self) -> str:
        link = self.subscription_url_var.get().strip()
        if link:
            return link

        remote_path = self.nextcloud_remote_path_var.get().strip()
        if _is_http_url(remote_path):
            return remote_path

        return ""

    def _copy_subscription_link(self) -> None:
        if self.is_running:
            messagebox.showinfo("En progreso", "Espera a que termine la ejecucion para copiar el enlace")
            return

        link = self._resolve_subscription_link()
        if not link:
            messagebox.showerror(
                "Enlace faltante",
                "Define la URL publica de suscripcion ICS en Ajustes avanzados.",
            )
            return

        self.root.clipboard_clear()
        self.root.clipboard_append(link)
        self.root.update_idletasks()
        self.status_var.set("Enlace ICS copiado al portapapeles")
        self._append_console(f"[ICS] Enlace copiado: {link}")

    def _refresh_holidays_button_clicked(self) -> None:
        if self.is_running:
            messagebox.showinfo("En progreso", "No puedes actualizar feriados mientras se genera el ICS")
            return

        self.refresh_holidays_btn.config(state=tk.DISABLED)
        self.status_var.set("Actualizando feriados nacionales...")

        def task() -> None:
            try:
                refresh_national_holidays_cache()
                detail = f"Actualizado a: {get_holiday_cache_updated_at()}"
                ok = True
            except Exception as exc:
                detail = f"Error al actualizar feriados: {exc}"
                ok = False

            def finish() -> None:
                self.refresh_holidays_btn.config(state=tk.NORMAL)
                self._refresh_holidays_status()
                self.status_var.set(detail)
                self._append_console(f"[Feriados] {detail}")
                if not ok:
                    messagebox.showwarning("Feriados", detail)

            self.root.after(0, finish)

        threading.Thread(target=task, daemon=True).start()

    def _refresh_default_user_options(self) -> None:
        current_default = self.default_user_var.get().strip()
        usernames = {(user.get("username") or "").strip() for user in self.data["users"]}
        usernames.discard("")

        if current_default and current_default not in usernames:
            self.default_user_var.set("")

        self.default_user_status_var.set(self._default_user_status_text())

    def _default_user_status_text(self) -> str:
        default_username = self.default_user_var.get().strip()
        if default_username:
            return f"Usuario predeterminado: {default_username}"
        return "Usuario predeterminado: ninguno"

    def _update_default_user_button_state(self) -> None:
        if not hasattr(self, "set_default_user_btn"):
            return
        self.set_default_user_btn.config(state=tk.NORMAL if self.tree.selection() else tk.DISABLED)

    def _set_selected_as_default(self) -> None:
        selected = self.tree.selection()
        if not selected:
            self._update_default_user_button_state()
            return

        idx = int(selected[0])
        if idx < 0 or idx >= len(self.data["users"]):
            return

        username = (self.data["users"][idx].get("username") or "").strip()
        if not username:
            messagebox.showerror("Dato invalido", "El usuario seleccionado no tiene codigo valido")
            return

        self.default_user_var.set(username)
        self.data["settings"]["default_username"] = username
        _save_data(self.data)
        self._load_users_into_tree()
        self.status_var.set(f"{username} establecido como predeterminado")

    def _refresh_autostart_status(self) -> None:
        """Actualiza el estado del autoinicio desde el SO y la UI."""
        try:
            status = get_autorun()
        except Exception as exc:
            self.autostart_status_var.set(f"✗ Error al consultar: {exc}")
            self.autostart_details_var.set("")
            self.autostart_enabled_var.set(False)
            return

        if status.enabled:
            # Autoinicio está activo
            self.autostart_enabled_var.set(True)
            self.autostart_status_var.set("✓ Activo por Registro")
            self.autostart_details_var.set(status.details)
        else:
            # Autoinicio no está activo
            self.autostart_enabled_var.set(False)
            self.autostart_status_var.set("○ Autoinicio desactivado")
            self.autostart_details_var.set("")

        self._update_autostart_ui_state()

    def _update_autostart_ui_state(self) -> None:
        """Actualiza el estado habilitado/deshabilitado de los controles de autoinicio."""
        self.repair_autostart_btn.config(state=tk.NORMAL)

    def _on_autostart_toggled(self) -> None:
        """Controlador cuando el usuario marca/desmarca el checkbox de autoinicio."""
        enabled = self.autostart_enabled_var.get()
        
        if not enabled:
            # Desactivar autoinicio
            ok, message = set_autorun(enabled=False)
            self._refresh_autostart_status()
            self.data["settings"]["autostart_enabled"] = False
            
            if ok:
                self.status_var.set("Autoinicio desactivado")
                self.autostart_details_var.set("")
            else:
                messagebox.showerror("Error", f"No se pudo desactivar el autoinicio:\n{message}")
                self._refresh_autostart_status()
            return
        
        # Activar autoinicio
        default_username = self.default_user_var.get().strip()
        if not default_username:
            messagebox.showerror(
                "Autoinicio",
                "Debes definir un usuario predeterminado antes de activar autoinicio",
            )
            self.autostart_enabled_var.set(False)
            return

        self.data["settings"]["autostart_enabled"] = True

        ok, message = set_autorun(enabled=True)
        self._refresh_autostart_status()

        if ok:
            self.status_var.set("Autoinicio activado")
            messagebox.showinfo("Éxito", f"Autoinicio activado:\n{message}")
        else:
            messagebox.showerror("Error", f"No se pudo activar el autoinicio:\n{message}")
            self.autostart_enabled_var.set(False)
            self.data["settings"]["autostart_enabled"] = False

    def _repair_autostart(self) -> None:
        """Repara el autoinicio eliminando todos los rastros y reconstruyendo."""
        default_username = self.default_user_var.get().strip()
        if not default_username:
            messagebox.showerror(
                "Autoinicio",
                "Debes definir un usuario predeterminado para reparar",
            )
            return

        if not messagebox.askyesno(
            "Reparar inicio",
            "Esta acción puede requerir permisos de administrador si hay restos heredados. ¿Deseas continuar?",
        ):
            return

        enabled = bool(self.autostart_enabled_var.get())

        self.repair_autostart_btn.config(state=tk.DISABLED)
        self.status_var.set("Reparando autoinicio...")

        ok, message = repair_autorun(enabled=enabled)
        self._refresh_autostart_status()
        self.repair_autostart_btn.config(state=tk.NORMAL)

        if ok:
            self.status_var.set("✓ Autoinicio reparado exitosamente")
            messagebox.showinfo(
                "Reparación Exitosa",
                f"✓ {message}\n\nEl programa se ejecutará automáticamente al reiniciar Windows.",
            )
        else:
            self.status_var.set("✗ Error al reparar autoinicio")
            messagebox.showerror(
                "Error en Reparación",
                f"✗ {message}\n\nRevisa los permisos y vuelve a intentar.",
            )

    def _test_nextcloud_connection(self) -> None:
        server_url = self.nextcloud_server_url_var.get().strip()
        bearer_token = self.nextcloud_bearer_token_var.get().strip()
        remote_path = self.nextcloud_remote_path_var.get().strip()
        timeout_raw = self.nextcloud_timeout_var.get().strip()

        try:
            timeout_seconds = max(1, int(timeout_raw))
        except Exception:
            messagebox.showerror("Dato invalido", "El timeout de Nextcloud debe ser un numero entero mayor o igual a 1")
            return

        if not _is_http_url(server_url):
            messagebox.showerror("Dato invalido", "La URL de Nextcloud debe iniciar con http:// o https://")
            return
        if not bearer_token:
            messagebox.showerror("Dato faltante", "Debes ingresar el token Bearer de Nextcloud")
            return
        if not remote_path:
            messagebox.showerror("Dato faltante", "Debes ingresar la ruta remota completa de Nextcloud")
            return

        self.nextcloud_test_btn.config(state=tk.DISABLED)
        self.status_var.set("Probando conexion con Nextcloud...")

        def task() -> None:
            ok, detail = test_nextcloud_connection(
                server_url=server_url,
                bearer_token=bearer_token,
                remote_path=remote_path,
                timeout_seconds=timeout_seconds,
            )

            def finish() -> None:
                if self.nextcloud_enabled_var.get():
                    self.nextcloud_test_btn.config(state=tk.NORMAL)
                if ok:
                    self.status_var.set("Conexion Nextcloud verificada")
                    self._append_console(f"[Nextcloud] {detail}")
                    messagebox.showinfo("Nextcloud", detail)
                else:
                    self.status_var.set("No se pudo validar Nextcloud")
                    self._append_console(f"[Nextcloud] {detail}")
                    messagebox.showwarning("Nextcloud", detail)

            self.root.after(0, finish)

        threading.Thread(target=task, daemon=True).start()

    def _load_users_into_tree(self) -> None:
        for row_id in self.tree.get_children():
            self.tree.delete(row_id)

        default_username = self.default_user_var.get().strip()
        for idx, user in enumerate(self.data["users"]):
            username = (user.get("username") or "").strip()
            display_username = username
            if username and username == default_username:
                display_username = f"{username} / predeterminado"
            self.tree.insert("", tk.END, iid=str(idx), values=(display_username,))

        self._refresh_default_user_options()
        self._update_default_user_button_state()
        self._update_selected_user_details()

    def _on_select_user(self, _event=None) -> None:
        self._update_selected_user_details()
        self._update_default_user_button_state()

    def _update_selected_user_details(self) -> None:
        selected = self.tree.selection()
        if not selected:
            self.user_selected_info_var.set("Selecciona un usuario para ver sus datos")
            self.user_selected_meta_var.set("")
            return

        idx = int(selected[0])
        if idx < 0 or idx >= len(self.data["users"]):
            self.user_selected_info_var.set("Seleccion invalida")
            self.user_selected_meta_var.set("")
            return

        user = self.data["users"][idx]
        username = (user.get("username") or "").strip()
        password = user.get("password") or ""
        is_default = username and username == self.default_user_var.get().strip()

        self.username_entry.delete(0, tk.END)
        self.username_entry.insert(0, username)
        self.password_entry.delete(0, tk.END)
        self.password_entry.insert(0, password)

        self.user_selected_info_var.set(f"Usuario seleccionado: {username or 'sin codigo'}")
        self.user_selected_meta_var.set(
            f"Contrasena: {'*' * min(len(password), 12) if password else 'vacía'} | Longitud: {len(password)} caracteres | Estado: {'predeterminado' if is_default else 'normal'}"
        )

    def _add_or_update_user(self) -> None:
        username = self.username_entry.get().strip()
        password = self.password_entry.get()

        if not username or not password:
            messagebox.showerror("Dato faltante", "Debes ingresar codigo y contraseña")
            return

        updated = False
        for user in self.data["users"]:
            if user.get("username") == username:
                user["password"] = password
                updated = True
                break

        if not updated:
            self.data["users"].append({"username": username, "password": password})

        _save_data(self.data)
        self._load_users_into_tree()
        self.status_var.set("Usuario guardado")

    def _delete_selected_user(self) -> None:
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Seleccion requerida", "Selecciona un usuario para eliminar")
            return

        idx = int(selected[0])
        removed_username = (self.data["users"][idx].get("username") or "").strip()
        del self.data["users"][idx]

        if self.default_user_var.get().strip() == removed_username:
            self.default_user_var.set("")
            self.data["settings"]["default_username"] = ""

        _save_data(self.data)
        self._load_users_into_tree()
        self.username_entry.delete(0, tk.END)
        self.password_entry.delete(0, tk.END)
        self.status_var.set("Usuario eliminado")

    def _save_settings(self) -> bool:
        login_url = self.login_url_entry.get().strip()
        schedule_url = self.schedule_url_entry.get().strip()
        first_event_reminder_raw = self.first_event_reminder_var.get().strip()
        other_events_reminder_raw = self.other_events_reminder_var.get().strip()
        nextcloud_enabled = bool(self.nextcloud_enabled_var.get())
        nextcloud_server_url = self.nextcloud_server_url_var.get().strip()
        nextcloud_bearer_token = self.nextcloud_bearer_token_var.get().strip()
        nextcloud_remote_path = self.nextcloud_remote_path_var.get().strip()
        nextcloud_timeout_raw = self.nextcloud_timeout_var.get().strip()

        if not login_url or not schedule_url:
            messagebox.showerror("Dato faltante", "Debes ingresar ambas URLs")
            return False

        try:
            first_event_reminder_minutes = int(first_event_reminder_raw)
            other_events_reminder_minutes = int(other_events_reminder_raw)
            if first_event_reminder_minutes < 0 or other_events_reminder_minutes < 0:
                raise ValueError
        except Exception:
            messagebox.showerror("Dato invalido", "Los recordatorios deben ser numeros enteros mayores o iguales a 0")
            return False

        try:
            nextcloud_timeout_seconds = max(1, int(nextcloud_timeout_raw))
        except Exception:
            messagebox.showerror("Dato invalido", "El timeout de Nextcloud debe ser un numero entero mayor o igual a 1")
            return False

        if nextcloud_enabled:
            if not _is_http_url(nextcloud_server_url):
                messagebox.showerror("Dato invalido", "La URL de Nextcloud debe iniciar con http:// o https://")
                return False
            if not nextcloud_bearer_token:
                messagebox.showerror("Dato faltante", "Debes ingresar el token Bearer de Nextcloud")
                return False
            if not nextcloud_remote_path:
                messagebox.showerror("Dato faltante", "Debes ingresar la ruta remota completa de Nextcloud")
                return False

        self.data["settings"]["login_url"] = login_url
        self.data["settings"]["schedule_url"] = schedule_url
        self.data["settings"]["cycle_lock_enabled"] = bool(self.lock_cycle_var.get())
        self.data["settings"]["selected_cycle"] = normalize_cycle_name(self.cycle_var.get())
        self.data["settings"]["first_event_reminder_minutes"] = first_event_reminder_minutes
        self.data["settings"]["other_events_reminder_minutes"] = other_events_reminder_minutes
        self.data["settings"]["nextcloud_upload_enabled"] = nextcloud_enabled
        self.data["settings"]["nextcloud_server_url"] = nextcloud_server_url
        self.data["settings"]["nextcloud_bearer_token"] = nextcloud_bearer_token
        self.data["settings"]["nextcloud_remote_path"] = nextcloud_remote_path
        self.data["settings"]["nextcloud_timeout_seconds"] = nextcloud_timeout_seconds
        self.data["settings"]["subscription_ics_url"] = self.subscription_url_var.get().strip()
        self.data["settings"]["default_username"] = self.default_user_var.get().strip()
        self.data["settings"]["autostart_enabled"] = bool(self.autostart_enabled_var.get())
        self.data["settings"].pop("autostart_method", None)
        self.data["settings"]["date_input_mode"] = self._normalize_date_input_mode(self.date_input_mode_var.get())
        _save_data(self.data)
        self.status_var.set("Configuracion guardada")
        return True

    def _save_reminders_settings(self) -> bool:
        first_event_reminder_raw = self.first_event_reminder_var.get().strip()
        other_events_reminder_raw = self.other_events_reminder_var.get().strip()

        try:
            first_event_reminder_minutes = int(first_event_reminder_raw)
            other_events_reminder_minutes = int(other_events_reminder_raw)
            if first_event_reminder_minutes < 0 or other_events_reminder_minutes < 0:
                raise ValueError
        except Exception:
            messagebox.showerror("Dato invalido", "Los recordatorios deben ser numeros enteros mayores o iguales a 0")
            return False

        self.data["settings"]["reminders_enabled"] = bool(self.reminders_enabled_var.get())
        self.data["settings"]["first_event_reminder_minutes"] = first_event_reminder_minutes
        self.data["settings"]["other_events_reminder_minutes"] = other_events_reminder_minutes
        _save_data(self.data)
        self.status_var.set("Configuración de recordatorios guardada")
        messagebox.showinfo("Éxito", "Recordatorios guardados correctamente")
        return True

    def _save_nextcloud_settings(self) -> bool:
        nextcloud_enabled = bool(self.nextcloud_enabled_var.get())
        nextcloud_server_url = self.nextcloud_server_url_var.get().strip()
        nextcloud_bearer_token = self.nextcloud_bearer_token_var.get().strip()
        nextcloud_remote_path = self.nextcloud_remote_path_var.get().strip()
        nextcloud_timeout_raw = self.nextcloud_timeout_var.get().strip()

        try:
            nextcloud_timeout_seconds = max(1, int(nextcloud_timeout_raw))
        except Exception:
            messagebox.showerror("Dato invalido", "El timeout de Nextcloud debe ser un numero entero mayor o igual a 1")
            return False

        if nextcloud_enabled:
            if not _is_http_url(nextcloud_server_url):
                messagebox.showerror("Dato invalido", "La URL de Nextcloud debe iniciar con http:// o https://")
                return False
            if not nextcloud_bearer_token:
                messagebox.showerror("Dato faltante", "Debes ingresar el token Bearer de Nextcloud")
                return False
            if not nextcloud_remote_path:
                messagebox.showerror("Dato faltante", "Debes ingresar la ruta remota completa de Nextcloud")
                return False

        self.data["settings"]["nextcloud_upload_enabled"] = nextcloud_enabled
        self.data["settings"]["nextcloud_server_url"] = nextcloud_server_url
        self.data["settings"]["nextcloud_bearer_token"] = nextcloud_bearer_token
        self.data["settings"]["nextcloud_remote_path"] = nextcloud_remote_path
        self.data["settings"]["nextcloud_timeout_seconds"] = nextcloud_timeout_seconds
        self.data["settings"]["subscription_ics_url"] = self.subscription_url_var.get().strip()
        _save_data(self.data)
        self.status_var.set("Configuración de Nextcloud guardada")
        messagebox.showinfo("Éxito", "Configuración de Nextcloud guardada correctamente")
        return True

    def _save_advanced_settings(self) -> bool:
        login_url = self.login_url_entry.get().strip()
        schedule_url = self.schedule_url_entry.get().strip()

        if not login_url or not schedule_url:
            messagebox.showerror("Dato faltante", "Debes ingresar ambas URLs")
            return False

        try:
            start_date, end_date = self._parse_date_range()
        except Exception:
            messagebox.showerror("Dato invalido", "El rango de fechas no es valido")
            return False

        self.data["settings"]["login_url"] = login_url
        self.data["settings"]["schedule_url"] = schedule_url
        self.data["settings"]["cycle_lock_enabled"] = bool(self.lock_cycle_var.get())
        self.data["settings"]["selected_cycle"] = normalize_cycle_name(self.cycle_var.get())
        self.data["settings"]["date_input_mode"] = self._normalize_date_input_mode(self.date_input_mode_var.get())
        _save_data(self.data)
        self.status_var.set("Configuración avanzada guardada")
        messagebox.showinfo("Éxito", "Configuración avanzada guardada correctamente")
        return True

    def _run_selected_user(self) -> None:
        if self.is_running:
            messagebox.showinfo("En progreso", "Ya hay una ejecución en curso")
            return

        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Seleccion requerida", "Selecciona un usuario")
            return

        idx = int(selected[0])
        user = self.data["users"][idx]

        username = (user.get("username") or "").strip()
        password = user.get("password") or ""
        login_url = self.login_url_entry.get().strip()
        schedule_url = self.schedule_url_entry.get().strip()
        first_event_reminder_raw = self.first_event_reminder_var.get().strip()
        other_events_reminder_raw = self.other_events_reminder_var.get().strip()
        nextcloud_enabled = bool(self.nextcloud_enabled_var.get())
        nextcloud_server_url = self.nextcloud_server_url_var.get().strip()
        nextcloud_bearer_token = self.nextcloud_bearer_token_var.get().strip()
        nextcloud_remote_path = self.nextcloud_remote_path_var.get().strip()
        nextcloud_timeout_raw = self.nextcloud_timeout_var.get().strip()

        if not username or not password:
            messagebox.showerror("Dato faltante", "Usuario seleccionado sin credenciales completas")
            return

        if not login_url or not schedule_url:
            messagebox.showerror("Dato faltante", "Debes definir URLs de login y calendario")
            return

        try:
            first_event_reminder_minutes = int(first_event_reminder_raw)
            other_events_reminder_minutes = int(other_events_reminder_raw)
            if first_event_reminder_minutes < 0 or other_events_reminder_minutes < 0:
                raise ValueError
        except Exception:
            messagebox.showerror("Dato invalido", "Los recordatorios deben ser numeros enteros mayores o iguales a 0")
            return

        try:
            nextcloud_timeout_seconds = max(1, int(nextcloud_timeout_raw))
        except Exception:
            messagebox.showerror("Dato invalido", "El timeout de Nextcloud debe ser un numero entero mayor o igual a 1")
            return

        if nextcloud_enabled:
            if not _is_http_url(nextcloud_server_url):
                messagebox.showerror("Dato invalido", "La URL de Nextcloud debe iniciar con http:// o https://")
                return
            if not nextcloud_bearer_token:
                messagebox.showerror("Dato faltante", "Debes ingresar el token Bearer de Nextcloud")
                return
            if not nextcloud_remote_path:
                messagebox.showerror("Dato faltante", "Debes ingresar la ruta remota completa de Nextcloud")
                return

        try:
            start_date, end_date = self._parse_date_range()
        except Exception:
            messagebox.showerror("Dato faltante", "Debes definir un rango de fechas valido")
            return

        cycle_name = normalize_cycle_name(self.cycle_var.get())
        if not cycle_name:
            messagebox.showerror("Dato faltante", "Debes seleccionar un ciclo academico valido")
            return

        cycle_start, cycle_end = cycle_bounds(cycle_name, date.today().year)
        start_date, end_date = clamp_window(start_date, end_date, cycle_start, cycle_end)
        self._set_date_range(start_date, end_date)

        self.is_running = True
        self.run_btn.config(state=tk.DISABLED)
        self.refresh_holidays_btn.config(state=tk.DISABLED)
        self._set_progress(0, "Iniciando ejecucion")
        self.status_var.set(f"Ejecutando scraper con {username} en ciclo {cycle_name}...")
        self._append_console(f"[Run] Usuario: {username}")
        self._append_console(f"[Run] Ciclo: {cycle_name} | Rango: {format_date(start_date)} -> {format_date(end_date)}")
        reminders_enabled = bool(self.reminders_enabled_var.get())
        if reminders_enabled:
            self._append_console(
                f"[Run] Recordatorios: HABILITADOS | Primer evento {first_event_reminder_minutes} min | Siguientes {other_events_reminder_minutes} min"
            )
        else:
            self._append_console("[Run] Recordatorios: DESHABILITADOS")
        self._append_console(
            f"[Run] Nextcloud: {'habilitado' if nextcloud_enabled else 'deshabilitado'} | Upload timeout: {nextcloud_timeout_seconds}s"
        )

        def task() -> None:
            try:
                set_active_credentials(username, password)
                os.environ["UNI_LOGIN_URL"] = login_url
                os.environ["UNI_SCHEDULE_URL"] = schedule_url
                os.environ["UTP_CYCLE_NAME"] = cycle_name
                os.environ["UTP_RANGE_START"] = format_date(start_date)
                os.environ["UTP_RANGE_END"] = format_date(end_date)
                os.environ["UTP_CYCLE_LOCKED"] = "true" if self.lock_cycle_var.get() else "false"
                os.environ["UTP_REMINDERS_ENABLED"] = "true" if reminders_enabled else "false"
                os.environ["UTP_REMINDER_FIRST_MINUTES"] = str(first_event_reminder_minutes)
                os.environ["UTP_REMINDER_NEXT_MINUTES"] = str(other_events_reminder_minutes)
                os.environ["FORCE_PLAYWRIGHT"] = "true"
                os.environ["ENABLE_PLAYWRIGHT_FALLBACK"] = "true"
                os.environ["NEXTCLOUD_UPLOAD_ENABLED"] = "true" if nextcloud_enabled else "false"
                os.environ["NEXTCLOUD_SERVER_URL"] = nextcloud_server_url
                os.environ["NEXTCLOUD_BEARER_TOKEN"] = nextcloud_bearer_token
                os.environ["NEXTCLOUD_REMOTE_PATH"] = nextcloud_remote_path
                os.environ["NEXTCLOUD_TIMEOUT_SECONDS"] = str(nextcloud_timeout_seconds)

                code = run_pipeline(progress_cb=self._progress_from_pipeline)
                if code == 0:
                    upload_result = os.environ.get("NEXTCLOUD_UPLOAD_RESULT", "disabled").strip().lower()
                    if upload_result == "success":
                        msg = "ICS generado y subido a Nextcloud"
                    elif upload_result == "failed":
                        msg = "ICS generado, pero la subida a Nextcloud fallo"
                    else:
                        msg = "ICS generado correctamente"
                else:
                    msg = f"El scraper terminó con código {code}"
                success = code == 0
                # actualizar timestamps y persistir
                if success:
                    now_str = format_datetime(datetime.now())
                    # última generación
                    try:
                        self.data.setdefault("settings", {})["last_ics_generated"] = now_str
                        self.last_ics_gen_var.set(now_str)
                    except Exception:
                        pass
                    # última subida nextcloud
                    if upload_result == "success":
                        try:
                            self.data.setdefault("settings", {})["last_nextcloud_upload"] = now_str
                            self.last_nextcloud_upload_var.set(now_str)
                        except Exception:
                            pass
                    try:
                        _save_data(self.data)
                    except Exception:
                        pass
            except Exception as exc:
                msg = f"Error: {exc}"
                success = False
            finally:
                clear_active_credentials()
                self.root.after(0, lambda: self._finish_run(msg, success))

        threading.Thread(target=task, daemon=True).start()

    def _finish_run(self, msg: str, success: bool) -> None:
        self.is_running = False
        self.run_btn.config(state=tk.NORMAL)
        self.refresh_holidays_btn.config(state=tk.NORMAL)
        if success:
            self._set_progress(100)
            self._reload_calendar_from_disk()
        self.status_var.set(msg)

    def _append_console(self, line: str) -> None:
        self.console_text.config(state=tk.NORMAL)
        self.console_text.insert(tk.END, f"{line}\n")
        self.console_text.see(tk.END)
        self.console_text.config(state=tk.DISABLED)

    def _clear_console(self) -> None:
        self.console_text.config(state=tk.NORMAL)
        self.console_text.delete("1.0", tk.END)
        self.console_text.config(state=tk.DISABLED)

    def _poll_logs(self) -> None:
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self._append_console(msg)
        except queue.Empty:
            pass
        self.root.after(120, self._poll_logs)

    def _on_close(self) -> None:
        if hasattr(self, "canvas"):
            self.canvas.unbind_all("<MouseWheel>")
        logging.getLogger().removeHandler(self.log_handler)
        self.root.destroy()


def start_gui() -> None:
    root = tk.Tk()
    UtpCalendarApp(root)
    root.mainloop()
