"""
claude_tracker.py — Registra cada cambio que Claude Code hace en el proyecto.
Log: logs/claude_session_log.json
"""
import json
from datetime import datetime
from pathlib import Path

LOG = Path(__file__).parent.parent / "logs" / "claude_session_log.json"


def _load():
    if LOG.exists():
        try:
            data = json.loads(LOG.read_text(encoding="utf-8"))
            # Si el log existente es una lista (formato anterior), convertir
            if isinstance(data, list):
                return {}
            return data
        except Exception:
            return {}
    return {}


def _save(data):
    LOG.parent.mkdir(exist_ok=True)
    LOG.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def registrar(archivo: str, accion: str, resultado: str = "OK",
              bytes_antes: int = None, bytes_despues: int = None):
    data = _load()
    fecha = datetime.now().strftime("%Y-%m-%d")
    hora  = datetime.now().strftime("%H:%M:%S")

    if fecha not in data:
        data[fecha] = {"acciones": []}

    entrada = {"timestamp": hora, "archivo": archivo, "accion": accion, "resultado": resultado}
    if bytes_antes is not None:
        entrada["bytes_antes"] = bytes_antes
    if bytes_despues is not None:
        entrada["bytes_despues"] = bytes_despues
        if bytes_antes is not None:
            entrada["delta"] = bytes_despues - bytes_antes

    data[fecha]["acciones"].append(entrada)
    _save(data)


def get_resumen(fecha: str = None):
    data = _load()
    if fecha:
        return data.get(fecha, {})
    hoy = datetime.now().strftime("%Y-%m-%d")
    return data.get(hoy, {"acciones": []})


def ver_log(dias: int = 1):
    data = _load()
    fechas = sorted(data.keys())[-dias:]
    for f in fechas:
        acciones = data[f].get("acciones", [])
        print(f"\n=== {f} ({len(acciones)} cambios) ===")
        for a in acciones:
            delta = f" ({'+' if a.get('delta',0)>=0 else ''}{a.get('delta','')} bytes)" if "delta" in a else ""
            print(f"  [{a['timestamp']}] {a['archivo']} | {a['accion']} => {a['resultado']}{delta}")


if __name__ == "__main__":
    ver_log(dias=7)
