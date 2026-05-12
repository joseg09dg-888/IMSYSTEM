"""
session_memory.py — Registro de todo lo que hace Claude Code en cada sesión.
Guarda en logs/claude_session_log.json.
"""
import json
import os
import threading
from datetime import datetime
from pathlib import Path

_LOG_PATH = Path(__file__).parent.parent / "logs" / "claude_session_log.json"
_lock = threading.Lock()
_SESSION_DATE = datetime.now().strftime("%Y-%m-%d")


def _load():
    if _LOG_PATH.exists():
        try:
            return json.loads(_LOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save(sessions):
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _LOG_PATH.write_text(json.dumps(sessions, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_bytes(path):
    try:
        return Path(path).stat().st_size
    except Exception:
        return 0


def registrar(archivo, accion, resultado="OK", bytes_antes=None, bytes_despues=None):
    """
    Registra una acción de Claude Code.

    archivo       — ruta relativa al archivo tocado (o 'sistema' si no aplica)
    accion        — descripción de lo que se hizo
    resultado     — 'OK', 'ERROR', o descripción del resultado
    bytes_antes   — tamaño del archivo antes del cambio (opcional)
    bytes_despues — tamaño del archivo después del cambio (opcional)
    """
    entrada = {
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "archivo": str(archivo),
        "accion": str(accion),
        "resultado": str(resultado),
        "bytes_antes": bytes_antes,
        "bytes_despues": bytes_despues,
    }

    with _lock:
        sessions = _load()
        # Buscar o crear la sesión de hoy
        sesion_hoy = None
        for s in sessions:
            if s.get("sesion") == _SESSION_DATE:
                sesion_hoy = s
                break
        if sesion_hoy is None:
            sesion_hoy = {"sesion": _SESSION_DATE, "acciones": []}
            sessions.append(sesion_hoy)
        sesion_hoy["acciones"].append(entrada)
        _save(sessions)

    return entrada


def registrar_archivo(path, accion):
    """Registra un cambio de archivo midiendo bytes antes y después automáticamente."""
    antes = _get_bytes(path)
    entrada = registrar(
        archivo=path,
        accion=accion,
        resultado="OK",
        bytes_antes=antes,
        bytes_despues=antes,  # se actualiza tras la acción
    )
    return entrada


def actualizar_bytes_despues(path):
    """Llama esto después de escribir el archivo para actualizar bytes_despues."""
    despues = _get_bytes(path)
    with _lock:
        sessions = _load()
        for s in sessions:
            if s.get("sesion") == _SESSION_DATE:
                acciones = s.get("acciones", [])
                for a in reversed(acciones):
                    if a.get("archivo") == str(path):
                        a["bytes_despues"] = despues
                        break
                break
        _save(sessions)


def get_sesion_hoy():
    """Retorna todas las acciones de la sesión de hoy."""
    with _lock:
        sessions = _load()
        for s in sessions:
            if s.get("sesion") == _SESSION_DATE:
                return s
    return {"sesion": _SESSION_DATE, "acciones": []}


def get_resumen():
    """Retorna un resumen compacto de la sesión actual."""
    sesion = get_sesion_hoy()
    acciones = sesion.get("acciones", [])
    ok = sum(1 for a in acciones if a.get("resultado") == "OK")
    err = sum(1 for a in acciones if a.get("resultado") not in ("OK", ""))
    archivos = list({a["archivo"] for a in acciones})
    return {
        "sesion": _SESSION_DATE,
        "total_acciones": len(acciones),
        "ok": ok,
        "errores": err,
        "archivos_tocados": archivos,
        "ultima_accion": acciones[-1] if acciones else None,
    }


if __name__ == "__main__":
    # Test
    registrar("frontend/index.html", "reemplazó frontend completo", "OK", 240033, 95000)
    registrar("agent/session_memory.py", "creó módulo de memoria de sesión", "OK", 0, 2100)
    print(json.dumps(get_resumen(), ensure_ascii=False, indent=2))
