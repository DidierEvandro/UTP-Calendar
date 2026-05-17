"""Gestor local de credenciales para ejecucion privada."""

import os


_ACTIVE_CREDENTIALS: dict[str, str] = {}


def set_active_credentials(username: str, password: str) -> None:
    _ACTIVE_CREDENTIALS["UNI_USERNAME"] = username.strip()
    _ACTIVE_CREDENTIALS["UNI_PASSWORD"] = password


def clear_active_credentials() -> None:
    _ACTIVE_CREDENTIALS.clear()


def get_local_credential(name: str, required: bool = True, default: str = "") -> str:
    local_value = _ACTIVE_CREDENTIALS.get(name, "")
    if local_value:
        return local_value

    env_value = os.environ.get(name, "").strip()
    if env_value:
        return env_value

    if required and not default:
        raise RuntimeError(f"Falta valor requerido: {name}.")
    return default
