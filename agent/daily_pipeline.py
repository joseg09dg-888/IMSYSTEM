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

# ── Rotacion de nicho+ciudad para Mateo — busqueda mundial ──
# Ciudades en orden intercalado por continente: cada dia el pipeline avanza
# por esta lista, así que desde el primer dia ya toca Norte, Centro y Sur
# America, y Europa (no un solo pais).
CIUDADES_MUNDO = [
    ("Medellin", "Colombia"),
    ("Miami", "United States"),
    ("Ciudad de Mexico", "Mexico"),
    ("Toronto", "Canada"),
    ("Buenos Aires", "Argentina"),
    ("Madrid", "Spain"),
    ("Bogota", "Colombia"),
    ("New York", "United States"),
    ("Guadalajara", "Mexico"),
    ("Santiago", "Chile"),
    ("Barcelona", "Spain"),
    ("Lima", "Peru"),
    ("Cali", "Colombia"),
    ("Los Angeles", "United States"),
    ("Monterrey", "Mexico"),
    ("Vancouver", "Canada"),
    ("Quito", "Ecuador"),
    ("Barranquilla", "Colombia"),
    ("Houston", "United States"),
    ("Ciudad de Panama", "Panama"),
    ("San Jose", "Costa Rica"),
    ("Chicago", "United States"),
]

# Nichos que ya existen en NICHOS (lead_finder_v2.py) y sirven para cualquier pais
NICHOS_ROTACION = [
    "odontologos", "dermatologo", "psicologo", "fisioterapeuta",
    "agencia_viajes", "seguros", "autos_alta_gama",
]

# Producto nicho x ciudad, en orden: primero recorre TODAS las ciudades del
# mundo con un nicho antes de pasar al siguiente, para maximizar diversidad
# geografica desde el dia 1.
ROTACION_EMPRESAS = [
    (nicho, ciudad, pais)
    for nicho in NICHOS_ROTACION
    for ciudad, pais in CIUDADES_MUNDO
]

# Cuantas combinaciones nicho+ciudad se procesan CADA VEZ que corre el
# pipeline (antes era 1 -> muy poco volumen). Con 150 llamadas/dia de
# margen en Google Places y ~2-3 llamadas por combinacion, 10 combinaciones
# usan ~20-30 llamadas, muy por debajo del limite.
N_COMBOS_POR_CORRIDA = 10
LEADS_POR_COMBO = 50

# Tags de genero para descubrir artistas nuevos en Last.fm cada corrida.
# Last.fm reporta oyentes GLOBALES por tag (no filtra por pais), asi que esta
# lista ya cubre artistas de todo el mundo dentro de estos generos.
# IMPORTANTE 1: se evitan tags masivos genericos ("pop", "hip hop", "r&b",
# "electronic") porque sus top-artists son casi todos superestrellas muy por
# encima del rango de oyentes que califica — desperdician cientos de
# llamadas a la API sin producir leads.
# IMPORTANTE 2 (2026-09-18): se quitaron tags de mercados donde IM Music no
# tiene alcance de negocio real (amapiano = Sudafrica, afrobeats = Nigeria,
# drill = EEUU/UK, hyperpop = escena US/Europa) — aunque algunos SI eran
# artistas de nivel independiente por oyentes, no son prospectos viables:
# IM opera en español, mercado latino, sin conexiones en esas industrias.
# Solo se usan generos del ecosistema latino/urbano donde IM si puede vender.
GENEROS_ARTISTAS = [
    "reggaeton", "trap latino", "urbano", "colombian hip hop",
    "latin pop", "musica urbana", "regional mexicano",
    "corridos tumbados", "dembow", "latin trap",
    "musica popular mexicana", "rkt", "cumbia 420", "trap argentino",
]
ARTISTAS_POR_GENERO = 30

# Nombres que NUNCA se deben agregar/contactar — ya son clientes, o sellos que
# no se prospectan. Match por substring, sin distinguir mayus/minus/acentos.
EXCLUIDOS = [
    "hidental",       # ya es cliente
    "vion music",     # sello excluido
    "kapital music",  # sello excluido
]


def _excluido(nombre: str) -> bool:
    n = (nombre or "").lower()
    return any(ex in n for ex in EXCLUIDOS)


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

    nuevas = [
        r for r in rows
        if (r.get("empresa", ""), r.get("email", "")) not in existentes
        and not _excluido(r.get("empresa", ""))
    ]
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


def paso_buscar_empresas(n_combos: int = N_COMBOS_POR_CORRIDA):
    """Corre varias combinaciones nicho+ciudad de la rotacion mundial en cada
    llamada (antes era solo 1/dia -> muy poco volumen para la meta de
    800-1000 contactos/mes)."""
    estado = _cargar_estado()
    hoy = datetime.now().strftime("%Y-%m-%d")

    total_nuevas = 0
    for _ in range(n_combos):
        idx = estado["indice"] % len(ROTACION_EMPRESAS)
        nicho, ciudad, pais = ROTACION_EMPRESAS[idx]
        print(f"[pipeline] Buscando: {nicho} en {ciudad}, {pais}")

        leads = find_leads(nicho, ciudad, pais, max_leads=LEADS_POR_COMBO, verbose=True)
        nuevas = _append_csv(leads, MAESTRO_EMPRESAS)
        print(f"[pipeline] {nuevas} leads nuevos agregados al maestro de empresas "
              f"({nicho}/{ciudad}).")
        total_nuevas += nuevas

        estado["indice"] = idx + 1
        estado["fecha"] = hoy
        _guardar_estado(estado)

    print(f"[pipeline] TOTAL leads nuevos en esta corrida: {total_nuevas}")
    return total_nuevas


def paso_buscar_artistas():
    print("[pipeline] Buscando artistas calificados nuevos en Last.fm...")
    todos = []
    vistos = set()
    for genero in GENEROS_ARTISTAS:
        leads = search_lastfm_artists("artista_independiente", "Medellin", "Colombia",
                                       max_results=ARTISTAS_POR_GENERO, tags=[genero])
        for l in leads:
            key = l.get("empresa", "")
            if key not in vistos:
                vistos.add(key)
                todos.append(l)
    nuevos = _append_csv(todos, MAESTRO_ARTISTAS)
    print(f"[pipeline] {nuevos} artistas nuevos agregados al maestro de musica "
          f"(sin contacto todavia — falta revision manual de Instagram).")
    return nuevos


CIUDADES_MUSICA = [
    ("Medellin", "Colombia"), ("Bogota", "Colombia"), ("Cali", "Colombia"),
    ("Miami", "United States"), ("Ciudad de Mexico", "Mexico"), ("Los Angeles", "United States"),
    ("Buenos Aires", "Argentina"), ("Madrid", "Spain"), ("Santiago", "Chile"),
    ("Lima", "Peru"), ("San Juan", "Puerto Rico"), ("Panama", "Panama"),
]
NICHOS_MUSICA = ["sello_musical", "manager_musical", "estudio_grabacion"]
ROTACION_MUSICA = [(n, c, p) for n in NICHOS_MUSICA for c, p in CIUDADES_MUSICA]
MAESTRO_MUSICA = DATA_DIR / "MAESTRO_leads_musica.csv"
ROTACION_MUSICA_STATE = LOGS_DIR / "rotacion_musica.json"


def paso_buscar_musica(n_combos: int = 6):
    """Sellos, managers y estudios (empresas con web y correo): se envian solos con José."""
    estado = {"indice": 0}
    if ROTACION_MUSICA_STATE.exists():
        estado = json.loads(ROTACION_MUSICA_STATE.read_text(encoding="utf-8"))
    total = 0
    for _ in range(n_combos):
        idx = estado["indice"] % len(ROTACION_MUSICA)
        nicho, ciudad, pais = ROTACION_MUSICA[idx]
        print(f"[pipeline] Musica: {nicho} en {ciudad}, {pais}")
        leads = find_leads(nicho, ciudad, pais, max_leads=LEADS_POR_COMBO, verbose=True)
        total += _append_csv(leads, MAESTRO_MUSICA)
        estado["indice"] = idx + 1
        ROTACION_MUSICA_STATE.write_text(json.dumps(estado), encoding="utf-8")
    print(f"[pipeline] {total} leads de musica nuevos (sellos/managers/estudios)")
    return total


def paso_enviar(agente: str, csv_path: Path, max_por_sesion: int = 40):
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
    p.add_argument("--combos", type=int, default=N_COMBOS_POR_CORRIDA,
                   help="Cuantas combinaciones nicho+ciudad buscar en esta corrida.")
    args = p.parse_args()

    if args.linea in ("mateo", "ambas"):
        paso_buscar_empresas(n_combos=args.combos)
        if not args.solo_buscar:
            paso_enviar("mateo", MAESTRO_EMPRESAS)

    if args.linea in ("jose", "ambas"):
        paso_buscar_musica(n_combos=6)
        if not args.solo_buscar:
            paso_enviar("jose", MAESTRO_MUSICA, max_por_sesion=20)
        paso_buscar_artistas()
        # Jose no se auto-envia: los artistas nuevos no tienen contacto todavia,
        # necesitan revision de Instagram primero (a proposito, ver notas de sesion).


if __name__ == "__main__":
    main()
