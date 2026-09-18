#!/usr/bin/env python3
"""
IM Daily Pipeline — busca leads nuevos y los manda, sin intervencion manual.

Cada vez que corre:
  1. Toma la siguiente combinacion nicho+ciudad de la rotacion (Mateo) que no
     se haya corrido hoy, busca leads reales (Google Places / OpenStreetMap),
     y los agrega al CSV maestro de negocios.
  2. Busca artistas calificados nuevos en Last.fm y los agrega al CSV maestro
     de musica (sin contacto todavia — eso sigue siendo manual/asistido).
  3. Llama al scheduler de Mateo y de Jose para que manden lo que tengan
     pendiente, respetando horario laboral y el copy que corresponda.

Pensado para correr una vez al dia (o via mateo_scheduler.bat / cron), no en
loop infinito — el loop de horario/pausas ya lo maneja im_scheduler.py.

Uso:
  python agent/daily_pipeline.py --linea mateo
  python agent/daily_pipeline.py --linea jose
  python agent/daily_pipeline.py --linea ambas
"""
import argparse, json, subprocess, sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from lead_finder_v2 import find_leads, search_lastfm_artists  # noqa: E402

BASE = Path(__file__).parent.parent
DATA_DIR = BASE / "data"
LOGS_DIR = BASE / "logs"
LOGS_DIR.mkdir(exist_ok=True)

MAESTRO_EMPRESAS = DATA_DIR / "MAESTRO_leads_empresas.csv"
MAESTRO_ARTISTAS = DATA_DIR / "MAESTRO_leads_artistas.csv"
ROTACION_STATE = LOGS_DIR / "rotacion_pipeline.json"

# ── Rotacion de nicho+ciudad para Mateo — se recorre una combinacion por dia ──
ROTACION_EMPRESAS = [
    ("odontologos", "Medellin", "Colombia"),
    ("dermatologo", "Medellin", "Colombia"),
    ("psicologo", "Medellin", "Colombia"),
    ("fisioterapeuta", "Medellin", "Colombia"),
    ("agencia_viajes", "Medellin", "Colombia"),
    ("seguros", "Medellin", "Colombia"),
    ("autos_alta_gama", "Medellin", "Colombia"),
    ("odontologos", "Bogota", "Colombia"),
    ("agencia_viajes", "Bogota", "Colombia"),
    ("odontologos", "Miami", "United States"),
]

# Tags de genero para descubrir artistas nuevos en Last.fm cada corrida
GENEROS_ARTISTAS = ["reggaeton", "trap latino", "urbano", "colombian hip hop"]


def _cargar_estado():
    if ROTACION_STATE.exists():
        try:
            return json.loads(ROTACION_STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"fecha": "", "indice": 0}


def _guardar_estado(estado):
    ROTACION_STATE.write_text(json.dumps(estado, ensure_ascii=False), encoding="utf-8")


def _append_csv(rows, destino: Path):
    import csv
    if not rows:
        return 0
    existe = destino.exists()
    existentes = set()
    if existe:
        with open(destino, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                existentes.add((r.get("empresa", ""), r.get("email", "")))

    nuevas = [r for r in rows if (r.get("empresa", ""), r.get("email", "")) not in existentes]
    if not nuevas:
        return 0

    fieldnames = list(rows[0].keys())
    modo = "a" if existe else "w"
    with open(destino, modo, newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if not existe:
            w.writeheader()
        w.writerows(nuevas)
    return len(nuevas)


def paso_buscar_empresas():
    """Corre la siguiente combinacion de la rotacion (una por dia)."""
    estado = _cargar_estado()
    hoy = datetime.now().strftime("%Y-%m-%d")
    if estado.get("fecha") != hoy:
        estado = {"fecha": hoy, "indice": estado.get("indice", 0)}

    idx = estado["indice"] % len(ROTACION_EMPRESAS)
    nicho, ciudad, pais = ROTACION_EMPRESAS[idx]
    print(f"[pipeline] Buscando: {nicho} en {ciudad}, {pais}")

    leads = find_leads(nicho, ciudad, pais, max_leads=30, verbose=True)
    nuevas = _append_csv(leads, MAESTRO_EMPRESAS)
    print(f"[pipeline] {nuevas} leads nuevos agregados al maestro de empresas.")

    estado["indice"] = idx + 1
    estado["fecha"] = hoy
    _guardar_estado(estado)
    return nuevas


def paso_buscar_artistas():
    print("[pipeline] Buscando artistas calificados nuevos en Last.fm...")
    todos = []
    vistos = set()
    for genero in GENEROS_ARTISTAS:
        leads = search_lastfm_artists("artista_independiente", "Medellin", "Colombia",
                                       max_results=15, tags=[genero])
        for l in leads:
            key = l.get("empresa", "")
            if key not in vistos:
                vistos.add(key)
                todos.append(l)
    nuevos = _append_csv(todos, MAESTRO_ARTISTAS)
    print(f"[pipeline] {nuevos} artistas nuevos agregados al maestro de musica "
          f"(sin contacto todavia — falta revision manual de Instagram).")
    return nuevos


def paso_enviar(agente: str, csv_path: Path, max_por_sesion: int = 15):
    """Manda UNA tanda (no loop infinito) respetando horario, via im_agents.py."""
    if not csv_path.exists():
        print(f"[pipeline] {csv_path.name} no existe todavia, nada que enviar.")
        return
    python_exe = sys.executable
    cmd = [
        python_exe, str(Path(__file__).parent / "im_agents.py"),
        "--agente", agente,
        "--csv", str(csv_path),
        "--tipo", "1",
        "--max", str(max_por_sesion),
        "--brochure",
    ]
    print(f"[pipeline] Enviando con {agente}: {' '.join(cmd[2:])}")
    subprocess.run(cmd, cwd=str(Path(__file__).parent))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--linea", choices=["mateo", "jose", "ambas"], default="ambas")
    p.add_argument("--solo-buscar", action="store_true",
                   help="Solo busca leads nuevos, no envia nada (para revisar antes).")
    args = p.parse_args()

    if args.linea in ("mateo", "ambas"):
        paso_buscar_empresas()
        if not args.solo_buscar:
            paso_enviar("mateo", MAESTRO_EMPRESAS)

    if args.linea in ("jose", "ambas"):
        paso_buscar_artistas()
        # Jose no se auto-envia: los artistas nuevos no tienen contacto todavia,
        # necesitan revision de Instagram primero (a proposito, ver notas de sesion).


if __name__ == "__main__":
    main()
