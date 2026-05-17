"""
Detección y migración de configuraciones de autoinicio antiguas o heredadas.
"""

import os
from pathlib import Path


def migrate_legacy_autostart() -> bool:
    """
    Detecta y migra métodos heredados de autoinicio.
    
    Casos que maneja:
    1. Acceso directo .lnk en la carpeta Startup de Windows
    2. Entradas antiguas con nombres distintos en el Registro
    3. Tareas programadas antiguas con nombres distintos
    
    Retorna:
        True si se migró algo, False si no había nada para migrar.
    """
    migrated = False
    
    # Caso 1: Acceso directo heredado en carpeta Startup
    migrated = migrated or _migrate_startup_shortcut()
    
    # Caso 2: Entradas antiguas en Registro con nombres distintos
    migrated = migrated or _migrate_legacy_registry_entries()
    
    # Caso 3: Tareas programadas antiguas
    migrated = migrated or _migrate_legacy_task_scheduler_tasks()
    
    return migrated


def _migrate_startup_shortcut() -> bool:
    r"""
    Detecta y elimina accesos directos heredados en la carpeta Startup.
    
    Ubicación: C:\Users\<user>\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup
    
    Retorna:
        True si se encontró y eliminó algo.
    """
    try:
        startup_folder = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        
        if not startup_folder.exists():
            return False
        
        migrated = False
        
        # Patrones de nombres heredados
        patterns = [
            "UTPCalendar*.lnk",
            "UTP*Calendar*.lnk",
            "calendar*.lnk",
        ]
        
        for pattern in patterns:
            for shortcut_file in startup_folder.glob(pattern):
                try:
                    shortcut_file.unlink()
                    migrated = True
                except Exception:
                    pass
        
        return migrated
        
    except Exception:
        return False


def _migrate_legacy_registry_entries() -> bool:
    """
    Detecta y elimina entradas antiguas en el Registro.
    
    Retorna:
        True si se encontró y eliminó algo.
    """
    if os.name != "nt":
        return False
    
    try:
        import winreg
        
        migrated = False
        run_key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        
        legacy_names = [
            "UTPCalendar",
            "UTPCalendarAutoRun_Old",
            "UTPCalendarAutoRun_Legacy",
            "CalendarAutoRun",
        ]
        
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key_path, 0, winreg.KEY_SET_VALUE) as key:
                for legacy_name in legacy_names:
                    try:
                        winreg.DeleteValue(key, legacy_name)
                        migrated = True
                    except (FileNotFoundError, OSError):
                        pass
        except Exception:
            pass
        
        return migrated
        
    except Exception:
        return False


def _migrate_legacy_task_scheduler_tasks() -> bool:
    """
    Detecta y elimina tareas programadas antiguas.
    
    Retorna:
        True si se encontró y eliminó algo.
    """
    try:
        import subprocess
        
        legacy_task_names = [
            r"\UTPCalendar\UTPCalendarAutoRun_Old",
            r"\UTPCalendarAutoRun_Legacy",
            r"\CalendarAutoRun",
        ]
        
        migrated = False
        
        for task_name in legacy_task_names:
            try:
                cmd = [
                    "schtasks.exe",
                    "/delete",
                    "/tn", task_name,
                    "/f",
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                
                if result.returncode == 0:
                    migrated = True
            except Exception:
                pass
        
        return migrated
        
    except Exception:
        return False


def clean_all_legacy_entries() -> tuple[bool, str]:
    """
    Limpia agresivamente todos los métodos de autoinicio heredados.
    Útil como opción de "limpiar todo" en la UI.
    
    Retorna:
        (éxito: bool, mensaje: str)
    """
    try:
        results = []
        
        if _migrate_startup_shortcut():
            results.append("Accesos directos heredados eliminados")
        
        if _migrate_legacy_registry_entries():
            results.append("Entradas antiguas del Registro eliminadas")
        
        if _migrate_legacy_task_scheduler_tasks():
            results.append("Tareas programadas antiguas eliminadas")
        
        if results:
            msg = "Limpieza completada:\n" + "\n".join(results)
            return True, msg
        else:
            return True, "No había configuraciones heredadas"
        
    except Exception as e:
        return False, f"Error durante la limpieza: {e}"
