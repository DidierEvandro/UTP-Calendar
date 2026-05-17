import os
# --- DEBE IR AQUÍ ---
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"
# --------------------

import logging
import socket
import json
from pathlib import Path
from datetime import date
from typing import Callable
from ics_generator import write_calendar
from nextcloud_uploader import upload_file_to_nextcloud
from peru_holidays import get_holiday_cache_updated_at, get_national_holidays_from
from scraper import ClassEvent, SpaPageDetectedError, scrape_with_requests

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[int, str], None]

def _emit_progress(progress_cb: ProgressCallback | None, percent: int, message: str) -> None:
    if progress_cb is None: return
    progress_cb(max(0, min(100, int(percent))), message)

def _log_and_emit(progress_cb: ProgressCallback | None, percent: int, message: str):
    logger.info(message)
    print(f"[Python] {message}", flush=True) 
    if progress_cb: _emit_progress(progress_cb, percent, message)

def _has_internet() -> bool:
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        return False

def _deep_find(data, target_key):
    target = target_key.lower().replace("_", "")
    if isinstance(data, dict):
        for k, v in data.items():
            if k.lower().replace("_", "") == target:
                return v
        for v in data.values():
            res = _deep_find(v, target_key)
            if res is not None: return res
    elif isinstance(data, list):
        for item in data:
            res = _deep_find(item, target_key)
            if res is not None: return res
    return None

def _get_global_data() -> dict:
    local_app_data = os.environ.get('LOCALAPPDATA')
    if not local_app_data: return {}
    
    candidates = []
    candidates.append(Path(local_app_data) / "UTPCalendar" / "local_profiles.json")
    
    packages_path = Path(local_app_data) / "Packages"
    if packages_path.exists():
        for match in packages_path.glob("*/LocalCache/Local/UTPCalendar/local_profiles.json"):
            candidates.append(match)
            
    base_dir = Path(__file__).parent
    candidates.append(base_dir / "local_profiles.json")
    candidates.append(base_dir.parent / "local_profiles.json")

    files_checked = []
    for path in candidates:
        files_checked.append(str(path))
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                    if _deep_find(data, "nextcloudserverurl") is not None or _deep_find(data, "searchrangemonths") is not None:
                        print(f"[Debug] Archivo de configuración encontrado exitosamente en la bóveda de Windows: {path}", flush=True)
                        return data
            except Exception:
                pass
                
    print(f"[Debug] Python no encontró configuraciones válidas. Rutas buscadas: {files_checked}", flush=True)
    return {}

def _get_setting_bool(data: dict, key: str) -> bool:
    v = _deep_find(data, key)
    if v is None: return False
    if isinstance(v, bool): return v
    return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}

def _get_setting_str(data: dict, key: str) -> str:
    v = _deep_find(data, key)
    if v is None: return ""
    return str(v).strip()

def run_pipeline(progress_cb: ProgressCallback | None = None) -> int:
    _log_and_emit(progress_cb, 5, "--- Iniciando motor de extracción UTP Calendar ---")
    
    if not _has_internet():
        _log_and_emit(progress_cb, 100, "[ERROR CRÍTICO] No hay conexión a internet. Abortando extracción.")
        return 1

    today = date.today()
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    _log_and_emit(progress_cb, 6, f"Fecha de sistema: {today.day} de {meses[today.month - 1]} de {today.year}")
    
    app_data = _get_global_data()
    
    use_custom = _get_setting_bool(app_data, "usecustomdaterange")
    if use_custom:
        start_str = _get_setting_str(app_data, "customstartdate")[:10]
        end_str = _get_setting_str(app_data, "customenddate")[:10]
        modo = "fechas personalizadas"
    else:
        months = _get_setting_str(app_data, "searchrangemonths")
        if not months: months = "2"
        start_str = "mes actual"
        end_str = f"+{months} meses"
        modo = "rango dinámico por meses"
        
    _log_and_emit(progress_cb, 8, f"Configuración: {modo}")
    _log_and_emit(progress_cb, 9, f"Buscando clases: {start_str} -> {end_str}")

    _log_and_emit(progress_cb, 12, "Verificando feriados nacionales...")
    try:
        national_holidays = get_national_holidays_from(today)
        _log_and_emit(progress_cb, 15, f"Feriados listos (caché: {get_holiday_cache_updated_at()})")
    except Exception as exc:
        logger.warning("No se pudo preparar la caché de feriados.")

    events = []

    _log_and_emit(progress_cb, 20, "Modo de extracción: Intentando API directa (rápido)...")

    try:
        events = scrape_with_requests()
        if events: _log_and_emit(progress_cb, 50, f"Lectura exitosa: se encontraron {len(events)} eventos rápidos.")
    except SpaPageDetectedError:
        _log_and_emit(progress_cb, 25, "El portal requiere renderizado. Cambiando de motor...")
    except Exception as exc:
        _log_and_emit(progress_cb, 25, f"Error en API directa: {str(exc)[:50]}...")

    if not events:
        _log_and_emit(progress_cb, 30, "Lanzando motor de navegador oculto. Esto tomará unos segundos...")
        try:
            # AQUÍ ES DONDE LLAMA A TU ARCHIVO FANTASMA
            from fallback_playwright import scrape_with_playwright
            events = scrape_with_playwright(progress_cb=progress_cb)
        except Exception as exc:
            _log_and_emit(progress_cb, 100, f"Error crítico durante la extracción profunda: {str(exc)}")
            return 1

    if not events:
        _log_and_emit(progress_cb, 100, "Finalizado: No se encontraron clases programadas para este periodo.")
        return 1

    unique_courses = set(e.course for e in events)
    unique_days = set(e.day.capitalize() for e in events)
    
    _log_and_emit(progress_cb, 82, f"Resumen final: {len(events)} clases totales guardadas.")
    _log_and_emit(progress_cb, 83, f"Cursos extraídos ({len(unique_courses)}):")
    for idx, c in enumerate(unique_courses, 1):
        _log_and_emit(progress_cb, 83, f"  - {c}")
    _log_and_emit(progress_cb, 84, f"Días de clase: {', '.join(unique_days)}")

    _log_and_emit(progress_cb, 88, "Generando archivo de calendario (.ics)...")
    output_file = write_calendar(events)
    
    _log_and_emit(progress_cb, 92, "Evaluando estado de la nube...")
    
    nc_enabled = _get_setting_bool(app_data, "nextclouduploadenabled")
    nc_url = _get_setting_str(app_data, "nextcloudserverurl")
    nc_token = _get_setting_str(app_data, "nextcloudbearertoken")

    if not nc_enabled and not nc_url:
        _log_and_emit(progress_cb, 100, "Horario guardado localmente (sincronización apagada).")
        return 0

    if not nc_enabled and nc_url:
        _log_and_emit(progress_cb, 93, "Aviso: Sincronización apagada pero hay credenciales guardadas. Forzando subida...")
        nc_enabled = True

    os.environ["NEXTCLOUD_SERVER_URL"] = nc_url
    os.environ["NEXTCLOUD_BEARER_TOKEN"] = nc_token
    os.environ["NEXTCLOUD_REMOTE_PATH"] = _get_setting_str(app_data, "nextcloudremotepath")

    _log_and_emit(progress_cb, 94, "Conectando con el servidor WebDAV...")
    try:
        ok, result_url = upload_file_to_nextcloud(output_file)
        
        if ok:
            _log_and_emit(progress_cb, 100, "Sincronización exitosa. Enlace público generado.")
            print(f"RESULT_URL:{result_url}", flush=True) 
            return 0
        else:
            _log_and_emit(progress_cb, 100, f"Error en la subida remota: {result_url}")
            return 2
    except Exception as e:
        _log_and_emit(progress_cb, 100, f"Excepción al subir a Nextcloud: {str(e)}")
        return 2