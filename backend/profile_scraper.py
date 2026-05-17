import os
# --- RUTA ABSOLUTA ---
_appdata = os.environ.get('LOCALAPPDATA', '')
if _appdata: os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(_appdata, "UTPCalendar", "Navegadores")
else: os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"
# ---------------------

import base64
import time  
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

def cerrar_ventanas_emergentes(page, progress_cb=None):
    if progress_cb: progress_cb(40, "Buscando ventanas emergentes...")
    try:
        selector_cerrar = "button[data-testid='utp-close-lightbox']"
        if page.locator(selector_cerrar).first.is_visible(timeout=3000):
            if progress_cb: progress_cb(45, "Cerrando modal con la 'X'...")
            page.locator(selector_cerrar).first.click()
            page.wait_for_timeout(1000)
    except Exception: pass

    try:
        btn_omitir = page.locator("button", has_text="Omitir")
        if btn_omitir.first.is_visible(timeout=2000):
            if progress_cb: progress_cb(50, "Cerrando encuesta con el boton 'Omitir'...")
            btn_omitir.first.click()
            page.wait_for_timeout(1000)
    except Exception: pass

def guardar_foto_perfil(base64_string, codigo_alumno):
    try:
        local_app_data = os.getenv('LOCALAPPDATA')
        img_dir = Path(local_app_data) / "UTPCalendar" / "profiles" if local_app_data else Path("datos_extraidos")
        img_dir.mkdir(parents=True, exist_ok=True)
        if "," in base64_string: base64_string = base64_string.split(",")[1]
        img_data = base64.b64decode(base64_string)
        ruta_archivo = img_dir / f"foto_{codigo_alumno}.jpg"
        with open(ruta_archivo, "wb") as f: f.write(img_data)
        return str(ruta_archivo)
    except Exception: return ""

def scrape_personal_data(username, password, progress_cb=None, early_result_cb=None):
    tiempo_inicio = time.time() 
    with sync_playwright() as p:
        # Lanzamiento directo y limpio
        browser = p.chromium.launch(headless=True, slow_mo=50)

        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()

        if progress_cb: progress_cb(10, "Iniciando sesion en portal UTP...")
        page.goto("https://sso.utp.edu.pe/auth/realms/Xpedition/protocol/openid-connect/auth?client_id=utpmas-web&redirect_uri=https%3A%2F%2Fportal.utp.edu.pe%2F&state=47e142f6-c2cf-4146-8394-5746166e3089&response_mode=fragment&response_type=code&scope=openid&nonce=ee972707-01a2-4d5c-a9cd-0d10540c23e0")
        
        page.fill("#username", username)
        page.fill("#password", password)
        page.click("#kc-login")

        if progress_cb: progress_cb(30, "Esperando carga de portal...")
        page.wait_for_url("**/portal.utp.edu.pe/**", timeout=60000)
        page.wait_for_load_state("networkidle")
        cerrar_ventanas_emergentes(page, progress_cb)
        
        if progress_cb: progress_cb(60, "Navegando a seccion Perfil...")
        page.goto("https://portal.utp.edu.pe/perfil")
        
        page.wait_for_timeout(3000) 
        page.wait_for_load_state("networkidle")
        cerrar_ventanas_emergentes(page, progress_cb)
        
        if progress_cb: progress_cb(70, "Extrayendo informacion personal...")
        
        try:
            nombre = "No encontrado"
            for h1 in page.locator("h1").all():
                if h1.inner_text().strip(): 
                    nombre = h1.inner_text().strip()
                    break

            def obtener_valor(etiqueta):
                try: return page.locator(f"xpath=//h4[text()='{etiqueta}']/following-sibling::span").inner_text(timeout=5000).strip()
                except: return "Dato no disponible"

            carrera = obtener_valor("Carrera")
            modalidad = obtener_valor("Modalidad de carrera")
            campus = obtener_valor("Campus")
            correo = obtener_valor("Correo UTP")

            foto_element = page.locator("img[src^='data:image']")
            if foto_element.count() > 0:
                ruta_foto = guardar_foto_perfil(foto_element.first.get_attribute("src"), username)
            else:
                ruta_foto = ""

            if progress_cb: progress_cb(100, "Extraccion exitosa.")

            datos_finales = {
                "FullName": nombre.title() if nombre != "No encontrado" else nombre,
                "Career": carrera,
                "Modality": modalidad,
                "Campus": campus,
                "Email": correo,
                "ProfilePicturePath": ruta_foto if "No se" not in ruta_foto else ""
            }

            if early_result_cb: early_result_cb(datos_finales)
            return datos_finales
        except Exception as e:
            if progress_cb: progress_cb(100, f"Error: {str(e)}")
            return None
        finally:
            page.wait_for_timeout(2000)
            browser.close()