import logging
import os
import time
from urllib.parse import urlparse, unquote
import requests

DEFAULT_TIMEOUT_SECONDS = 10

def _parse_timeout(raw_value: str) -> int:
    try: return max(1, int(raw_value))
    except: return DEFAULT_TIMEOUT_SECONDS

def _clean_server_url(url: str) -> str:
    parsed = urlparse(url.strip())
    path = parsed.path
    for ui_path in ["/apps/files", "/settings/", "/index.php"]:
        if ui_path in path: path = path.split(ui_path)[0]
    if "/remote.php/" in path: path = path.split("/remote.php/")[0]
    return f"{parsed.scheme}://{parsed.netloc}{path}".rstrip("/")

def get_or_create_public_share(remote_file_path: str) -> str:
    server_url = _clean_server_url(os.environ.get("NEXTCLOUD_SERVER_URL", ""))
    token = os.environ.get("NEXTCLOUD_BEARER_TOKEN", "")
    share_api_url = f"{server_url}/ocs/v2.php/apps/files_sharing/api/v1/shares"
    
    # Decodificar espacios (ej. "/UTP%20Calendar/x.ics" -> "/UTP Calendar/x.ics")
    clean_path = unquote(remote_file_path)
    
    headers = {
        "Authorization": f"Bearer {token}", 
        "OCS-APIRequest": "true", 
        "Accept": "application/json"
    }
    
    try:
        # Intentar crear el enlace
        payload = {"path": clean_path, "shareType": 3}
        resp = requests.post(share_api_url, data=payload, headers=headers, timeout=10)
        
        if resp.status_code in [200, 201]: 
            return resp.json()['ocs']['data']['url']
            
        # Si ya existe o falló la creación, intentar obtener el enlace listando los compartidos
        list_resp = requests.get(share_api_url, params={"path": clean_path}, headers=headers, timeout=10)
        shares = list_resp.json()['ocs']['data']
        if isinstance(shares, list) and len(shares) > 0: 
            return shares[0]['url']
            
    except Exception as e: 
        print(f"[Nextcloud] Error al generar enlace publico: {e}", flush=True)
        pass
    return ""

def upload_file_to_nextcloud(local_file_path: str) -> tuple[bool, str]:
    server_url = _clean_server_url(os.environ.get("NEXTCLOUD_SERVER_URL", "").strip())
    bearer_token = os.environ.get("NEXTCLOUD_BEARER_TOKEN", "").strip()
    remote_path_raw = os.environ.get("NEXTCLOUD_REMOTE_PATH", "").strip().replace(" ", "%20")
    timeout_s = _parse_timeout(os.environ.get("NEXTCLOUD_TIMEOUT_SECONDS", ""))
    
    if not server_url or not bearer_token: return False, "Faltan credenciales."

    if remote_path_raw.startswith("http"):
        base_target = remote_path_raw.rstrip('/')
    else:
        if not remote_path_raw.startswith("/"): remote_path_raw = f"/{remote_path_raw}"
        base_target = f"{server_url}/remote.php/webdav{remote_path_raw}"

    filename = os.path.basename(local_file_path)
    target_url = f"{base_target}/{filename}" if not base_target.lower().endswith(".ics") else base_target
    
    parsed_url = urlparse(target_url)
    full_remote_path = parsed_url.path.split("/remote.php/webdav")[-1] if "/remote.php/webdav" in parsed_url.path else parsed_url.path

    last_error = ""
    for intento in range(3):
        try:
            with open(local_file_path, "rb") as f:
                resp = requests.put(target_url, data=f, headers={"Authorization": f"Bearer {bearer_token}", "Content-Type": "text/calendar"}, timeout=timeout_s)
            
            if 200 <= resp.status_code < 300:
                public_url = get_or_create_public_share(full_remote_path)
                return True, public_url if public_url else target_url
                
            last_error = f"Error HTTP {resp.status_code}"
        except Exception as e:
            last_error = str(e)
            
        time.sleep(5)
        
    return False, f"Fallo tras 3 intentos: {last_error}"

def test_nextcloud_connection(server_url: str, bearer_token: str, remote_path: str, progress_cb=None) -> tuple[bool, str]:
    def _report(p, m):
        if progress_cb: progress_cb(p, m)
        print(f"[Nextcloud] {m}", flush=True)

    try:
        _report(10, "Iniciando prueba de conexión con Nextcloud...")
        clean_url = _clean_server_url(server_url)
        _report(30, f"Servidor detectado: {clean_url}")
        
        if not remote_path.startswith("/"): remote_path = f"/{remote_path}"
        test_url = f"{clean_url}/remote.php/webdav{remote_path}"
        
        _report(50, "Enviando petición PROPFIND para verificar permisos...")
        headers = {"Authorization": f"Bearer {bearer_token}", "OCS-APIRequest": "true"}
        resp = requests.request("PROPFIND", test_url, headers=headers, timeout=10)
        
        if 200 <= resp.status_code < 300:
            _report(100, "Conexión y permisos verificados correctamente.")
            return True, "Conexión exitosa"
        
        _report(100, f"Error de conexión: Código {resp.status_code}")
        return False, f"Error {resp.status_code}"
    except Exception as e:
        _report(100, f"Error crítico: {str(e)}")
        return False, str(e)