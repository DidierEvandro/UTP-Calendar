import os
import sys
import winreg
from pathlib import Path

def get_run_cmd():
    """Construye el comando exacto para ejecutar Python en modo silencioso absoluto."""
    python_exe = sys.executable
    
    # MAGIA SILENCIOSA: Cambiamos python.exe por pythonw.exe para evitar la consola negra
    if python_exe.lower().endswith("python.exe"):
        pythonw_exe = python_exe.lower().replace("python.exe", "pythonw.exe")
        if os.path.exists(pythonw_exe):
            python_exe = pythonw_exe

    main_py = Path(__file__).parent / "main.py"
    
    # El comando le dice a pythonw: ejecuta main.py con el argumento --autorun
    return f'"{python_exe}" "{main_py}" --autorun'

def set_autorun(enabled=True):
    """Agrega o quita la entrada en el Registro de Windows."""
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "UTPCalendar"
    
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        if enabled:
            cmd = get_run_cmd()
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
            return True, "Inicio automático habilitado (Modo Silencioso)."
        else:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
            return True, "Inicio automático deshabilitado."
    except Exception as e:
        return False, f"Error accediendo al registro: {e}"

def repair_autorun(enabled=True):
    """Limpia y vuelve a registrar las rutas actuales del proyecto."""
    set_autorun(enabled=False)
    return set_autorun(enabled=enabled)