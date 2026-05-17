import os
import sys
import json
import time
import socket
import traceback
from pathlib import Path
from datetime import date, datetime

def _get_absolute_json_path() -> Path:
    user_profile = os.environ.get('USERPROFILE')
    if user_profile:
        target_path = Path(user_profile) / "AppData" / "Local" / "UTPCalendar" / "local_profiles.json"
        if target_path.exists(): return target_path
    base_path = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    return base_path / "local_profiles.json"

def _log_debug(msg: str):
    try:
        user_profile = os.environ.get('USERPROFILE', '')
        log_dir = Path(user_profile) / "AppData" / "Local" / "UTPCalendar" if user_profile else Path(__file__).resolve().parent
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / "autostart_debug.txt", "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
    except: pass

def _wait_for_internet(timeout_seconds=90) -> bool:
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        try:
            socket.create_connection(("www.google.com", 443), timeout=2)
            _log_debug("Red detectada. Estabilizando (10s)...")
            time.sleep(10)
            return True
        except: time.sleep(5)
    return False

def run_default_profile_pipeline() -> int:
    lock_file = Path(os.getenv('TEMP', '/tmp')) / "utp_autostart.lock"
    if lock_file.exists() and (time.time() - lock_file.stat().st_mtime < 300): return 0
    
    try:
        lock_file.touch()
        if not _wait_for_internet(90):
            if lock_file.exists(): lock_file.unlink()
            return 1
            
        path = _get_absolute_json_path()
        if not path.exists():
            if lock_file.exists(): lock_file.unlink()
            return 0
            
        with open(path, "r", encoding="utf-8") as f: data = json.load(f)
            
        settings = data.get("settings", data.get("Settings", {}))
        default_user = settings.get("default_username", settings.get("DefaultUsername", ""))
        users = data.get("users", data.get("Users", []))
        user_data = next((u for u in users if u.get("username", u.get("Username")) == default_user), None)
        
        if not user_data:
            if lock_file.exists(): lock_file.unlink()
            return 0

        os.environ["UNI_USERNAME"] = user_data.get("username", "")
        os.environ["UNI_PASSWORD"] = user_data.get("password", "")
        
        from pipeline import run_pipeline
        from cycle_config import calculate_extraction_window, format_date
        
        start_d, end_d = calculate_extraction_window(settings, date.today())
        os.environ["UTP_RANGE_START"] = format_date(start_d)
        os.environ["UTP_RANGE_END"] = format_date(end_d)
        os.environ["UTP_CYCLE_NAME"] = "Personalizado"
        os.environ["UTP_CYCLE_LOCKED"] = "false"
        
        nc_enabled = settings.get("nextcloud_upload_enabled", settings.get("NextcloudUploadEnabled", False))
        os.environ["NEXTCLOUD_UPLOAD_ENABLED"] = "true" if nc_enabled else "false"
        os.environ["NEXTCLOUD_SERVER_URL"] = settings.get("nextcloud_server_url", "")
        os.environ["NEXTCLOUD_BEARER_TOKEN"] = settings.get("nextcloud_bearer_token", "")
        os.environ["NEXTCLOUD_REMOTE_PATH"] = settings.get("nextcloud_remote_path", "")
        os.environ["NEXTCLOUD_TIMEOUT_SECONDS"] = str(settings.get("nextcloud_timeout_seconds", 10))

        result = run_pipeline()
        
        if result in [0, 2]:
            now_str = f"{datetime.now().strftime('%d/%m/%Y %H:%M')} (Autostart)"
            if "settings" not in data: data["settings"] = {}
            data["settings"]["last_ics_generated"] = now_str
            if result == 0: data["settings"]["last_nextcloud_upload"] = now_str
            with open(path, "w", encoding="utf-8") as f: json.dump(data, f, indent=4)

        if lock_file.exists(): lock_file.unlink()
        return result
    except Exception:
        _log_debug(f"ERROR: {traceback.format_exc()}")
        if lock_file.exists(): lock_file.unlink()
        return 1