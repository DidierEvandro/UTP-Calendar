"""
Gestión de autoinicio usando el Registro de Windows.
Método no intrusivo, sin elevación requerida.
"""

import os
from typing import Optional

if os.name == "nt":
    import winreg


class RegistryAutostart:
    """Maneja el autoinicio mediante el Registro de Windows."""

    RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
    VALUE_NAME = "UTPCalendarAutoRun"

    @staticmethod
    def is_active() -> bool:
        """
        Verifica si hay una entrada de autoinicio en el Registro.
        
        Retorna:
            True si existe la entrada, False si no.
        """
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RegistryAutostart.RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
                winreg.QueryValueEx(key, RegistryAutostart.VALUE_NAME)
                return True
        except FileNotFoundError:
            return False
        except Exception:
            return False

    @staticmethod
    def get_command() -> Optional[str]:
        """
        Lee el comando actual del Registro.
        
        Retorna:
            El comando como string, o None si no existe.
        """
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RegistryAutostart.RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, RegistryAutostart.VALUE_NAME)
                return str(value)
        except (FileNotFoundError, OSError):
            return None

    @staticmethod
    def install(command: str) -> tuple[bool, str]:
        """
        Instala una entrada de autoinicio en el Registro.
        
        Args:
            command: Comando completo a ejecutar al inicio
        
        Retorna:
            (éxito: bool, mensaje: str)
        """
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RegistryAutostart.RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, RegistryAutostart.VALUE_NAME, 0, winreg.REG_SZ, command)
            return True, "Autoinicio activado por Registro"
        except PermissionError:
            return False, "Permisos insuficientes para acceder al Registro"
        except Exception as e:
            return False, f"Error al instalar en Registro: {e}"

    @staticmethod
    def uninstall() -> tuple[bool, str]:
        """
        Elimina la entrada de autoinicio del Registro.
        
        Retorna:
            (éxito: bool, mensaje: str)
        """
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RegistryAutostart.RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, RegistryAutostart.VALUE_NAME)
            return True, "Entrada del Registro eliminada"
        except FileNotFoundError:
            # Clave o valor no existe, no es error
            return True, "No había entrada en el Registro"
        except PermissionError:
            return False, "Permisos insuficientes para eliminar del Registro"
        except Exception as e:
            return False, f"Error al eliminar del Registro: {e}"
