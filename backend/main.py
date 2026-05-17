import sys
import os
# Redirigir cualquier error fatal a la nada para que nunca salga una ventana emergente
sys.stderr = open(os.devnull, 'w')

# --- CONFIGURACIÓN CRÍTICA GLOBAL: RUTA ABSOLUTA ---
_appdata = os.environ.get('LOCALAPPDATA', '')
if _appdata:
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(_appdata, "UTPCalendar", "Navegadores")
else:
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"
# ---------------------------------------------------

import argparse
import json
import traceback
import datetime
import time
import subprocess
from pathlib import Path

try:
    from pipeline import run_pipeline
    from profile_scraper import scrape_personal_data
    from nextcloud_uploader import test_nextcloud_connection
    from peru_holidays import refresh_national_holidays_cache
    from datetime import date
    from cycle_config import calculate_extraction_window, format_date
    # ELIMINAMOS AUTOSTART_MANAGER AQUÍ
except ImportError:
    pass

try:
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
except Exception:
    pass

def send_to_csharp(data):
    print(json.dumps(data), flush=True)

def progress_adapter(percent, message):
    send_to_csharp({"method": "progress", "params": {"percent": percent, "message": message}})

def _get_profiles_path() -> Path:
    local_app_data = os.environ.get('LOCALAPPDATA', '')
    if local_app_data:
        packages_path = Path(local_app_data) / "Packages"
        if packages_path.exists():
            matches = list(packages_path.glob("*/LocalCache/Local/UTPCalendar/local_profiles.json"))
            if matches: return matches[0]
        path = Path(local_app_data) / "UTPCalendar" / "local_profiles.json"
        if path.exists(): return path
    return Path(__file__).resolve().parent / "local_profiles.json"

def log_autorun(msg: str):
    try:
        log_file = _get_profiles_path().parent / "autorun_log.txt"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass

def _get_settings_from_profiles():
    try:
        path = _get_profiles_path()
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
            return data.get("settings", data.get("Settings", {}))
    except Exception: return {}

def run_rpc_server():
    try:
        print("Motor Python conectado y listo en modo RPC.", flush=True)
        for line in sys.stdin:
            line = line.strip()
            if not line: continue
            try:
                req = json.loads(line)
                req_id = req.get("id")
                method = req.get("method")
                params = req.get("params", {})
                
                if method == "ping":
                    send_to_csharp({"id": req_id, "result": "pong"})
                
                elif method == "run_pipeline":
                    os.environ["UNI_USERNAME"] = params.get("username", "")
                    os.environ["UNI_PASSWORD"] = params.get("password", "")
                    
                    settings = _get_settings_from_profiles()
                    start_d, end_d = calculate_extraction_window(settings, date.today())
                    os.environ["UTP_RANGE_START"] = format_date(start_d)
                    os.environ["UTP_RANGE_END"] = format_date(end_d)
                    
                    nc_enabled = settings.get("nextcloud_upload_enabled", settings.get("NextcloudUploadEnabled", False))
                    os.environ["NEXTCLOUD_UPLOAD_ENABLED"] = "true" if nc_enabled else "false"
                    os.environ["NEXTCLOUD_SERVER_URL"] = settings.get("nextcloud_server_url", "")
                    os.environ["NEXTCLOUD_BEARER_TOKEN"] = settings.get("nextcloud_bearer_token", "")
                    os.environ["NEXTCLOUD_REMOTE_PATH"] = settings.get("nextcloud_remote_path", "")
                    
                    code = run_pipeline(progress_cb=progress_adapter)
                    send_to_csharp({"id": req_id, "result": {"code": code, "message": "Proceso finalizado"}})

                elif method == "update_metadata":
                    sent_early = [False]
                    def early_cb(d):
                        send_to_csharp({"id": req_id, "result": d})
                        sent_early[0] = True
                        
                    data = scrape_personal_data(params.get("username", ""), params.get("password", ""), progress_cb=progress_adapter, early_result_cb=early_cb)
                    if not sent_early[0]: send_to_csharp({"id": req_id, "result": data})

                elif method == "test_nextcloud":
                    success, message = test_nextcloud_connection(params.get("serverUrl", ""), params.get("bearerToken", ""), params.get("remotePath", ""), progress_cb=progress_adapter)
                    send_to_csharp({"id": req_id, "result": {"success": success, "message": message}})

                elif method == "refresh_holidays":
                    refresh_national_holidays_cache(progress_cb=progress_adapter)
                    send_to_csharp({"id": req_id, "result": {"success": True, "message": "Feriados actualizados"}})

                elif method == "shutdown":
                    sys.exit(0)
            except Exception as e:
                print(f"[ERROR CRITICO] {traceback.format_exc()}", file=sys.stderr, flush=True)
                try:
                    send_to_csharp({"id": req_id, "error": str(e)})
                except: pass
                
    except OSError:
        # ¡EL ESCUDO MAGICO! Si C# cierra la app y rompe la tubería, Python se despide en total silencio.
        sys.exit(0)
    except Exception:
        # Previene cualquier otro popup de PyInstaller
        sys.exit(1)
def main(argv: list[str] | None = None) -> int:
    os.chdir(Path(__file__).resolve().parent)
    parser = argparse.ArgumentParser()
    parser.add_argument("--rpc", action="store_true")
    parser.add_argument("--autorun", action="store_true")
    parser.add_argument("--install-browsers", action="store_true")
    args = parser.parse_args(argv)
    
    if args.install_browsers:
        try:
            import re
            from playwright._impl._driver import compute_driver_executable, get_driver_env
            
            progress_adapter(10, "Preparando entorno seguro de Windows...")
            
            driver_executable, driver_cli = compute_driver_executable()
            cli_args = driver_cli if isinstance(driver_cli, list) else [driver_cli]
            cmd = [driver_executable] + cli_args + ["install", "chromium"]
            
            env = os.environ.copy()
            env.update(get_driver_env())
            
            creation_flags = 0x08000000 if sys.platform == "win32" else 0
            
            process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                creationflags=creation_flags
            )
            
            base_pct = 15
            max_pct = 50
            stage_name = "Iniciando motor..."

            # LECTOR CARÁCTER POR CARÁCTER (El antídoto para el salto de línea \r)
            if process.stdout:
                buffer = []
                while True:
                    char = process.stdout.read(1)
                    if not char and process.poll() is not None:
                        break
                    
                    if char == '\r' or char == '\n':
                        line = "".join(buffer).strip()
                        buffer.clear()
                        if not line: continue

                        if "Downloading Chrome for Testing" in line:
                            base_pct = 15; max_pct = 50; stage_name = "Navegador base"
                        elif "Downloading FFmpeg" in line:
                            base_pct = 50; max_pct = 55; stage_name = "Librerías multimedia"
                        elif "Downloading Chrome Headless Shell" in line:
                            base_pct = 55; max_pct = 95; stage_name = "Motor silencioso"
                        elif "Downloading Winldd" in line:
                            base_pct = 95; max_pct = 98; stage_name = "Dependencias Windows"

                        match = re.search(r'(\d{1,3})%', line)
                        if match:
                            local_pct = int(match.group(1))
                            real_pct = base_pct + int((local_pct / 100.0) * (max_pct - base_pct))
                            progress_adapter(real_pct, f"Descargando {stage_name}... {local_pct}%")
                        elif "Downloaded to" in line or "downloaded to" in line:
                            progress_adapter(max_pct, f"{stage_name} completado.")
                    else:
                        buffer.append(char)

            process.wait()
            if process.returncode == 0:
                progress_adapter(100, "¡Configuración completada con éxito!")
                return 0
            else:
                return 1
                
        except Exception as e:
            progress_adapter(0, f"Error: {str(e)}")
            return 1

    if args.rpc: return run_rpc_server() or 0
    
    if args.autorun: 
        import time
        time.sleep(20) # Espera 20 segundos para que el Wi-Fi o Red se conecte
        
        log_autorun("\n" + "="*40)
        log_autorun("=== INICIANDO EXTRACCIÓN EN SEGUNDO PLANO ===")
        path = _get_profiles_path()
        lock_file = path.parent / "autorun.lock"
        if lock_file.exists():
            if time.time() - lock_file.stat().st_mtime < 120: return 0
        try:
            with open(lock_file, "w") as f: f.write("bloqueado")
        except: pass
        class AutorunLogger:
            def write(self, msg):
                if msg.strip(): log_autorun(f"  > {msg.strip()}")
            def flush(self): pass
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = AutorunLogger(), AutorunLogger()
        try:
            with open(path, "r", encoding="utf-8-sig") as f: data = json.load(f)
            settings = data.get("Settings", data.get("settings", {}))
            def get_val(d, target_key):
                target = target_key.lower().replace("_", "")
                for k, v in d.items():
                    if k.lower().replace("_", "") == target: return v
                return None
            default_user = get_val(settings, "defaultusername")
            if not default_user: return 1
            users = data.get("Users", data.get("users", []))
            user_pass = next((get_val(u, "password") for u in users if get_val(u, "username") == default_user), "")
            nc_enabled = str(get_val(settings, "NextcloudUploadEnabled")).strip().lower() in {"1", "true", "yes", "on"}
            os.environ["UNI_USERNAME"] = default_user
            os.environ["UNI_PASSWORD"] = user_pass
            os.environ["NEXTCLOUD_UPLOAD_ENABLED"] = "true" if nc_enabled else "false"
            os.environ["NEXTCLOUD_SERVER_URL"] = str(get_val(settings, "NextcloudServerUrl") or "")
            os.environ["NEXTCLOUD_BEARER_TOKEN"] = str(get_val(settings, "NextcloudBearerToken") or "")
            os.environ["NEXTCLOUD_REMOTE_PATH"] = str(get_val(settings, "NextcloudRemotePath") or "")
            try:
                start_d, end_d = calculate_extraction_window(settings, date.today())
                os.environ["UTP_RANGE_START"] = format_date(start_d)
                os.environ["UTP_RANGE_END"] = format_date(end_d)
            except: pass
            code = run_pipeline()
            if code in [0, 2]: 
                now_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M") + " (auto)"
                def set_val(d, target_key, new_value):
                    target = target_key.lower().replace("_", "")
                    for k in d.keys():
                        if k.lower().replace("_", "") == target:
                            d[k] = new_value
                            return
                    d[target_key] = new_value
                set_val(settings, "LastIcsGenerated", now_str)
                if code == 0 and nc_enabled: set_val(settings, "LastNextcloudUpload", now_str)
                try:
                    with open(path, "w", encoding="utf-8") as f: json.dump(data, f, indent=2)
                except: pass
            return code
        except Exception: return 1
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr
            if lock_file.exists(): 
                try: lock_file.unlink()
                except: pass
    return 0

if __name__ == "__main__":
    sys.exit(main())