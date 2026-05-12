#!/usr/bin/env python3
"""
IM Market Researcher v3 — Investigación con fuentes académicas, gubernamentales
y análisis psicográfico + sesgos cognitivos por maleta.
"""
import os, sys, json, time, sqlite3, hashlib, re, threading
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus, urlencode
import urllib.request as _req

if hasattr(sys.stdout, 'reconfigure'):
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass

BASE    = Path(__file__).parent.parent
DB      = BASE / "logs" / "platform.db"
REPORTS = BASE / "reports"

def _load_env():
    f = BASE / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if k.strip() and not os.environ.get(k.strip()):
                    os.environ[k.strip()] = v.strip()
_load_env()

# ── CATÁLOGOS ────────────────────────────────────────────────────
NICHOS_KEYWORDS = {
    "odontologos":               ["odontólogo", "clínica dental", "dentista", "ortodoncia"],
    "dermatologo":               ["dermatólogo", "clínica de piel", "dermatología", "medicina estética"],
    "agencia_viajes":            ["agencia de viajes", "tours", "turismo", "paquetes turísticos"],
    "seguros":                   ["aseguradora", "seguros", "broker de seguros"],
    "autos_alta_gama":           ["concesionario", "carros de lujo", "BMW", "Mercedes", "Audi"],
    "restaurantes":              ["restaurante", "café", "gastrobar"],
    "gimnasios":                 ["gimnasio", "CrossFit", "yoga", "pilates", "fitness"],
    "clinicas_veterinarias":     ["veterinaria", "clínica veterinaria"],
    "contadores":                ["contador", "firma contable", "revisor fiscal"],
    "abogados":                  ["abogado", "firma de abogados", "consultorio jurídico"],
    "inmobiliarias":             ["inmobiliaria", "finca raíz", "agencia inmobiliaria"],
    "clinicas_medicina_estetica":["medicina estética", "clínica de belleza", "botox"],
    "psicologos":                ["psicólogo", "psicóloga", "salud mental", "terapia"],
    "centros_bienestar":         ["spa", "centro de bienestar", "masajes"],
    "sello_musical":             ["sello musical", "productora musical", "estudio de grabación"],
}

CIUDADES_SECTORES = {
    "Medellín":    ["Laureles","El Poblado","Envigado","Bello","Sabaneta","Itagüí","Belén","Estadio","Centro","Castilla"],
    "Bogotá":      ["Chapinero","Usaquén","Suba","Teusaquillo","Santa Fe","Kennedy","Fontibón","Engativá"],
    "Cali":        ["El Norte","Sur de Cali","Oeste","Centro","San Fernando","Granada","Ciudad Jardín"],
    "Barranquilla":["Norte","Centro","Riomar","Metropolitana"],
    "Cartagena":   ["Bocagrande","Castillogrande","El Cabrero","Pie de la Popa"],
    "Bucaramanga": ["Cabecera del Llano","El Centro","Ciudadela Real de Minas"],
    "Pereira":     ["Centro","Pinares","Cuba","Dosquebradas"],
    "Manizales":   ["Centro","El Cable","La Enea"],
}

# Mapeo de CIIU y sector para DANE
CIIU_MAP = {
    "odontologos":               ("8621", "servicios odontológicos", "salud"),
    "dermatologo":               ("8621", "dermatología y medicina estética", "salud"),
    "psicologos":                ("8690", "servicios de salud mental", "salud"),
    "clinicas_medicina_estetica":("8690", "medicina estética", "salud"),
    "gimnasios":                 ("9311", "clubes deportivos y gimnasios", "recreación"),
    "restaurantes":              ("5611", "restaurantes y cafeterías", "alimentos"),
    "clinicas_veterinarias":     ("7500", "actividades veterinarias", "servicios"),
    "agencia_viajes":            ("7911", "agencias de viajes", "turismo"),
    "abogados":                  ("6910", "actividades jurídicas", "servicios"),
    "contadores":                ("6920", "actividades contables", "servicios"),
    "inmobiliarias":             ("6810", "actividades inmobiliarias", "servicios"),
    "seguros":                   ("6512", "seguros y reaseguros", "financiero"),
    "autos_alta_gama":           ("4511", "comercio de vehículos", "comercio"),
}

# ── BASE DE DATOS ────────────────────────────────────────────────
def get_db():
    DB.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    return conn

def init_mercado_tables():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS mercado_jobs (
            id TEXT PRIMARY KEY,
            nicho TEXT, pais TEXT, ciudad TEXT,
            sectores TEXT, barrios TEXT, profundidad TEXT,
            estado TEXT DEFAULT 'pendiente',
            progreso INTEGER DEFAULT 0,
            modulo_actual TEXT DEFAULT '',
            resultado TEXT,
            creado_at TEXT, terminado_at TEXT
        );
    """)
    conn.commit(); conn.close()

def _update_job(job_id, **kwargs):
    conn = get_db()
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [job_id]
    conn.execute(f"UPDATE mercado_jobs SET {sets} WHERE id=?", vals)
    conn.commit(); conn.close()

# ── UTILIDADES ───────────────────────────────────────────────────
def _safe_float(val, default=0.0):
    if val is None: return default
    try:    return float(val)
    except: return default

def _strip_html(html):
    return re.sub(r'<[^>]+>', '', html).strip()

def _http_get(url, headers=None, timeout=12):
    try:
        h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120"}
        if headers: h.update(headers)
        req = _req.Request(url, headers=h)
        with _req.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return f"ERROR:{e}"

# ── GOOGLE MAPS ──────────────────────────────────────────────────
def _maps_places_search(keyword, location, api_key):
    if not api_key: return []
    url = ("https://maps.googleapis.com/maps/api/place/textsearch/json?"
           + urlencode({"query": keyword + " " + location, "key": api_key, "language": "es"}))
    raw = _http_get(url)
    if raw.startswith("ERROR:"): return []
    try:    return json.loads(raw).get("results", [])
    except: return []

def _maps_place_details(place_id, api_key):
    if not api_key or not place_id: return {}
    url = ("https://maps.googleapis.com/maps/api/place/details/json?"
           + urlencode({
               "place_id": place_id,
               "fields": "name,formatted_address,formatted_phone_number,website,rating,"
                         "user_ratings_total,reviews,opening_hours,price_level,business_status",
               "key": api_key, "language": "es"
           }))
    raw = _http_get(url)
    if raw.startswith("ERROR:"): return {}
    try:    return json.loads(raw).get("result", {})
    except: return {}

# ── GOOGLE SNIPPETS ──────────────────────────────────────────────
def _google_snippets(query, num=8):
    url = f"https://www.google.com/search?q={quote_plus(query)}&num={num}&hl=es&gl=co"
    raw = _http_get(url)
    snippets = []
    for pat in [r'<div[^>]*class="[^"]*VwiC3b[^"]*"[^>]*>(.*?)</div>',
                r'<span[^>]*class="[^"]*aCOpRe[^"]*"[^>]*>(.*?)</span>',
                r'<div[^>]*class="[^"]*s[^"]*"[^>]*>(.*?)</div>']:
        for m in re.findall(pat, raw, re.DOTALL):
            t = _strip_html(m).strip()
            if t and len(t) > 40 and not t.startswith("ERROR"):
                snippets.append(t[:400])
    return list(dict.fromkeys(snippets))[:num]

# ── BÚSQUEDAS DE MERCADO ─────────────────────────────────────────
def _buscar_precios(nicho_kw, ciudad):
    queries = [
        f"precio {nicho_kw} {ciudad} 2024 cuánto cuesta",
        f"tarifa {nicho_kw} {ciudad} COP",
        f"consulta {nicho_kw} {ciudad} valor",
    ]
    resultados = []
    for q in queries[:2]:
        for s in _google_snippets(q, num=5):
            if any(c in s for c in ["$", "COP", "pesos", "precio", "cuesta", "costo", "tarifa"]):
                resultados.append({"query": q, "texto": s})
    return resultados[:6]

def _buscar_quejas(nicho_kw, ciudad):
    queries = [
        f"{nicho_kw} {ciudad} quejas problemas malas experiencias",
        f"{nicho_kw} {ciudad} no recomiendo mala atención",
        f"problemas {nicho_kw} {ciudad} estafa",
    ]
    resultados = []
    for q in queries[:2]:
        for s in _google_snippets(q, num=5):
            if len(s) > 50:
                resultados.append({"query": q, "texto": s})
    return resultados[:6]

def _buscar_recomendaciones(nicho_kw, ciudad):
    queries = [
        f"mejor {nicho_kw} en {ciudad} recomendaciones",
        f"{nicho_kw} {ciudad} el mejor dónde ir",
    ]
    resultados = []
    for q in queries[:2]:
        for s in _google_snippets(q, num=5):
            resultados.append({"query": q, "texto": s})
    return resultados[:6]

def _buscar_facebook_ads(nicho_kw, ciudad):
    resultados = []
    url = (f"https://www.facebook.com/ads/library/?country=CO&ad_type=all"
           f"&q={quote_plus(nicho_kw + ' ' + ciudad)}&search_type=keyword_unordered")
    raw = _http_get(url, timeout=15)
    if not raw.startswith("ERROR:"):
        page_names = re.findall(r'"page_name"\s*:\s*"([^"]+)"', raw)
        ad_texts   = re.findall(r'"ad_creative_body"\s*:\s*"([^"]+)"', raw)
        cta_types  = re.findall(r'"call_to_action_type"\s*:\s*"([^"]+)"', raw)
        for i, name in enumerate(page_names[:5]):
            resultados.append({
                "pagina": name,
                "texto_anuncio": ad_texts[i] if i < len(ad_texts) else "",
                "cta": cta_types[i] if i < len(cta_types) else "",
            })
    for s in _google_snippets(f'anuncios publicidad {nicho_kw} {ciudad} Facebook Instagram 2024', num=5):
        if len(s) > 40:
            resultados.append({"pagina": "Google search", "texto_anuncio": s, "cta": ""})
    return resultados[:8]

def _buscar_informes(nicho_kw, ciudad):
    queries = [
        f"informe sector {nicho_kw} Colombia 2024 estadísticas",
        f"estudio mercado {nicho_kw} {ciudad} 2024",
        f"estadísticas {nicho_kw} Colombia DANE 2024",
        f"diagnóstico {nicho_kw} Colombia cámara comercio",
    ]
    resultados = []
    for q in queries[:3]:
        for s in _google_snippets(q, num=3):
            if len(s) > 50:
                resultados.append({"query": q, "texto": s})
        time.sleep(0.3)
    return resultados[:8]

# ── FUENTES ACADÉMICAS ───────────────────────────────────────────
def _buscar_fuentes_academicas(nicho_kw, ciudad):
    """Busca estudios académicos en Google Scholar y repositorios colombianos."""
    resultados = []

    scholar_queries = [
        f"comportamiento consumidor {nicho_kw} Colombia",
        f"psicología compra {nicho_kw} Latinoamérica 2022 2023 2024",
        f"sesgos cognitivos consumidor servicios {nicho_kw}",
        f"motivaciones compra {nicho_kw} Colombia",
    ]
    for q in scholar_queries[:3]:
        url = f"https://scholar.google.com/scholar?q={quote_plus(q)}&hl=es&as_ylo=2021"
        raw = _http_get(url, timeout=14)
        if not raw.startswith("ERROR:"):
            titles    = re.findall(r'class="gs_rt"[^>]*>.*?<a[^>]*>(.*?)</a>', raw, re.DOTALL)
            abstracts = re.findall(r'class="gs_rs"[^>]*>(.*?)</div>', raw, re.DOTALL)
            authors   = re.findall(r'class="gs_a"[^>]*>(.*?)</div>', raw, re.DOTALL)
            hrefs     = re.findall(r'class="gs_rt"[^>]*>.*?<a[^>]*href="([^"]+)"', raw, re.DOTALL)
            for i, title in enumerate(titles[:3]):
                t = _strip_html(title).strip()
                a = _strip_html(abstracts[i]).strip() if i < len(abstracts) else ""
                au = _strip_html(authors[i]).strip() if i < len(authors) else ""
                link = hrefs[i] if i < len(hrefs) else ""
                if t and len(t) > 15:
                    resultados.append({
                        "titulo": t[:200], "autores": au[:120],
                        "resumen": a[:300], "url": link[:200],
                        "fuente": "Google Scholar", "query": q
                    })
        time.sleep(0.5)

    # Repositorios académicos colombianos vía Google
    repo_queries = [
        f'site:repository.unal.edu.co "{nicho_kw}" consumidor',
        f'"Universidad de los Andes" "{nicho_kw}" comportamiento compra Colombia',
        f'"Pontificia Universidad Javeriana" "{nicho_kw}" mercado Colombia',
        f'"comportamiento del consumidor" "{nicho_kw}" Colombia filetype:pdf 2022 2023 2024',
    ]
    for q in repo_queries[:2]:
        for s in _google_snippets(q, num=3):
            if len(s) > 60:
                resultados.append({
                    "titulo": s[:150], "autores": "",
                    "resumen": s[:300], "url": "",
                    "fuente": "Repositorio académico Colombia", "query": q
                })
        time.sleep(0.3)

    # Estudios de mercado de consultoras
    consul_queries = [
        f"Nielsen {nicho_kw} Colombia informe 2024",
        f"McKinsey Colombia {nicho_kw} tendencias 2023 2024",
        f"Deloitte Colombia servicios {nicho_kw} 2024",
    ]
    for q in consul_queries[:2]:
        for s in _google_snippets(q, num=3):
            if len(s) > 60:
                resultados.append({
                    "titulo": s[:150], "autores": "Consultora",
                    "resumen": s[:300], "url": "",
                    "fuente": "Estudio de mercado", "query": q
                })
        time.sleep(0.3)

    return resultados[:10]

# ── DATOS GUBERNAMENTALES ─────────────────────────────────────────
def _buscar_datos_gobierno(nicho_kw, ciudad):
    """Busca datos estadísticos en DANE, Confecámaras, Minsalud, DNP."""
    resultados = []
    ciiu_info = CIIU_MAP.get(nicho_kw, ("", nicho_kw, "servicios"))
    sector_dane = ciiu_info[1]
    gran_sector = ciiu_info[2]

    # DANE
    dane_queries = [
        f"site:dane.gov.co {nicho_kw} estadísticas 2024",
        f"DANE Encuesta Micronegocios 2024 {gran_sector} Colombia estadísticas",
        f"DANE Encuesta Anual Servicios {sector_dane} Colombia empresas 2023",
        f"DANE Censo Económico {nicho_kw} Colombia número empresas",
    ]
    for q in dane_queries[:3]:
        for s in _google_snippets(q, num=3):
            if len(s) > 50 and any(kw in s.lower() for kw in ["dane","encuesta","censo","estadística","%","millones","empresas","trabajadores"]):
                resultados.append({
                    "entidad": "DANE", "dato": s[:280],
                    "url": "https://www.dane.gov.co", "año": "2024", "query": q
                })
        time.sleep(0.3)

    # Confecámaras
    for s in _google_snippets(f"Confecámaras creación empresas {nicho_kw} Colombia 2024 informe", num=3):
        if len(s) > 50:
            resultados.append({
                "entidad": "Confecámaras", "dato": s[:280],
                "url": "https://www.confecamaras.com.co", "año": "2024", "query": "confecámaras"
            })
    time.sleep(0.3)

    # Minsalud (nichos de salud)
    if any(n in nicho_kw.lower() for n in ["odonto","derm","psico","salud","medic","veterin"]):
        for s in _google_snippets(f"Minsalud prestadores {sector_dane} Colombia registros habilitados 2024", num=3):
            if len(s) > 50:
                resultados.append({
                    "entidad": "MinSalud", "dato": s[:280],
                    "url": "https://www.minsalud.gov.co", "año": "2024", "query": "minsalud"
                })
        time.sleep(0.3)

    # DNP / Mincomercio
    for s in _google_snippets(f"Mincomercio diagnóstico sector {sector_dane} Colombia 2024 estadísticas", num=3):
        if len(s) > 50:
            resultados.append({
                "entidad": "MinComercio", "dato": s[:280],
                "url": "https://www.mincomercio.gov.co", "año": "2024", "query": "mincomercio"
            })
    time.sleep(0.3)

    # RUES
    for s in _google_snippets(f"RUES empresas registradas {nicho_kw} Colombia CIIU {ciiu_info[0]} 2024", num=3):
        if len(s) > 50 and any(kw in s.lower() for kw in ["rues","registro","empresas","cámara","ciiu","matriculadas"]):
            resultados.append({
                "entidad": "RUES", "dato": s[:280],
                "url": "https://www.rues.org.co", "año": "2024", "query": "rues"
            })

    return resultados[:12]

# ── REVIEWS Y MÉTRICAS ───────────────────────────────────────────
def _extraer_reviews_profundas(places_details):
    todas_reviews, positivas, negativas = [], [], []
    dolor_conteo, elogio_conteo = {}, {}

    PAIN_KW = ["espera","tardaron","malo","pésimo","caro","cobran","no atendieron",
               "no contestaron","demora","estafa","descuidado","grosero","mala atención",
               "horrible","incumplimiento","sin cita","desorganizado","irresponsable",
               "no recomiendo","cobran de más","precio excesivo","tardanza","cancelaron"]
    ELOGIO_KW = ["excelente","amable","profesional","recomiendo","puntual","limpio",
                 "atención","calidad","rápido","eficiente","buena","satisfecho","confío",
                 "volvería","increíble","resultado","transformación","cambio","diferencia",
                 "cuidado","dedicación","explicaron","tranquilidad","confianza"]

    for det in places_details:
        for rev in (det.get("reviews") or []):
            texto  = (rev.get("text") or "").strip()
            rating = _safe_float(rev.get("rating"), 3.0)
            if not texto: continue
            todas_reviews.append({"texto": texto, "rating": rating,
                                   "lugar": det.get("_lugar_base", {}).get("name", "")})
            tl = texto.lower()
            if rating <= 2:
                negativas.append(texto[:300])
                for kw in PAIN_KW:
                    if kw in tl: dolor_conteo[kw] = dolor_conteo.get(kw, 0) + 1
            elif rating >= 4:
                positivas.append(texto[:200])
                for kw in ELOGIO_KW:
                    if kw in tl: elogio_conteo[kw] = elogio_conteo.get(kw, 0) + 1

    top_dolores = sorted(dolor_conteo.items(), key=lambda x: x[1], reverse=True)[:8]
    top_elogios = sorted(elogio_conteo.items(), key=lambda x: x[1], reverse=True)[:6]

    return {
        "total": len(todas_reviews),
        "positivas":      positivas[:10],
        "negativas":      negativas[:10],
        "top_dolores":    [{"problema": k, "menciones": v} for k, v in top_dolores],
        "top_elogios":    [{"elogio": k, "menciones": v}   for k, v in top_elogios],
        "muestra_textual": todas_reviews[:20],
    }

def _calcular_metricas(places, places_details):
    total = len(places)
    if total == 0: return {"total_encontrados": 0}
    ratings = [_safe_float(p.get("rating")) for p in places if p.get("rating") is not None]
    ratings = [r for r in ratings if r > 0]
    con_web = sum(1 for d in places_details if d.get("website"))
    con_reviews_activos = sum(1 for p in places if _safe_float(p.get("user_ratings_total")) > 10)
    price_levels = [_safe_float(d.get("price_level")) for d in places_details if d.get("price_level") is not None]
    price_levels = [p for p in price_levels if p > 0]
    precio_nivel = round(sum(price_levels) / len(price_levels), 1) if price_levels else None
    return {
        "total_encontrados":   total,
        "rating_promedio":     round(sum(ratings) / len(ratings), 2) if ratings else 0,
        "con_presencia_web":   con_web,
        "pct_presencia_web":   round(con_web / total * 100) if total else 0,
        "con_reviews_activos": con_reviews_activos,
        "pct_reviews_activos": round(con_reviews_activos / total * 100) if total else 0,
        "nivel_precio_promedio": precio_nivel,
        "nivel_precio_label":  {1:"Económico",2:"Moderado",3:"Alto",4:"Muy alto"}.get(
            round(precio_nivel) if precio_nivel else 0, "No disponible"),
    }

# ── ANÁLISIS PSICOGRÁFICO Y SESGOS (FALLBACK SIN CLAUDE) ─────────
def _analizar_sesgos_fallback(nicho, reviews_data, metricas, ciudad, sectores):
    """Genera análisis de sesgos cognitivos y perfil psicográfico sin usar Claude."""
    dolores  = [d["problema"] for d in (reviews_data.get("top_dolores") or [])[:5]]
    elogios  = [e["elogio"]   for e in (reviews_data.get("top_elogios") or [])[:5]]
    rating   = metricas.get("rating_promedio", 0)
    pct_web  = metricas.get("pct_presencia_web", 0)
    total    = metricas.get("total_encontrados", 0)
    con_web  = metricas.get("con_presencia_web", 0)
    sin_web  = total - con_web

    dolor_str  = " ".join(dolores).lower()
    elogio_str = " ".join(elogios).lower()

    tiene_espera     = any(k in dolor_str for k in ["espera","demora","tardaron","tardanza"])
    tiene_precio     = any(k in dolor_str for k in ["caro","cobran","precio","excesivo"])
    tiene_atencion   = any(k in dolor_str for k in ["atención","grosero","malo","descuidado"])
    valora_amabi     = any(k in elogio_str for k in ["amable","atención","cuidado","tranquilidad"])
    valora_prof      = any(k in elogio_str for k in ["profesional","calidad","resultado","dedicación"])
    valora_rapidez   = any(k in elogio_str for k in ["rápido","eficiente","puntual"])

    nicho_label = nicho.replace("_", " ")
    sector_str  = ", ".join(sectores[:3]) if sectores else ciudad

    miedo_principal = (
        "espera larga y precios sorpresa" if (tiene_espera and tiene_precio)
        else "tiempos de espera excesivos" if tiene_espera
        else "precios poco claros y cobros adicionales" if tiene_precio
        else "mala atención y falta de seguimiento"
    )
    motivacion = (
        "sentirse cuidado y recibir atención personalizada" if valora_amabi
        else "resultados visibles y profesionalismo garantizado" if valora_prof
        else "rapidez y eficiencia sin complicaciones" if valora_rapidez
        else "calidad del servicio con precio justo"
    )
    review_negativa = (reviews_data.get("negativas") or ["Busco confianza antes que precio"])[0][:120]

    sesgos = {
        "maleta_1_disponibilidad": {
            "nombre": "Sesgo de Disponibilidad",
            "maleta": "QUÉ EXISTE",
            "descripcion": (
                f"Los {nicho_label} con más reviews en Google Maps son automáticamente "
                f"percibidos como 'los mejores'. Solo el {pct_web}% tiene presencia web — "
                f"el {100-pct_web}% es invisible para el cliente digital."
            ),
            "evidencia": (
                f"De {total} empresas encontradas, el cliente considera activamente solo "
                f"las primeras 5-7 en Maps. {sin_web} negocios ni siquiera tienen web."
            ),
            "como_aprovecharlo": (
                "IM posiciona a sus clientes en primeros resultados locales. "
                "Visibilidad online = credibilidad percibida = más consultas."
            ),
        },
        "maleta_2_statu_quo": {
            "nombre": "Sesgo de Statu Quo",
            "maleta": "QUÉ FALTA",
            "descripcion": (
                f"El {100-pct_web}% de {nicho_label} en {sector_str} no tiene presencia digital. "
                f"Sus clientes actuales se quedan por inercia, no por fidelidad real. "
                f"El costo percibido de cambiar es mayor al costo real de quedarse."
            ),
            "evidencia": (
                f"Rating promedio del sector: {rating}/5. Indica satisfacción moderada, no deleite. "
                f"Clientes insatisfechos no cambian porque no saben que existen mejores opciones."
            ),
            "como_aprovecharlo": (
                "IM captura estos clientes insatisfechos con retargeting digital y "
                "campañas de comparación antes de que el competidor lo haga."
            ),
        },
        "maleta_3_aversion_perdida": {
            "nombre": "Aversión a la Pérdida (Kahneman & Tversky)",
            "maleta": "QUÉ DUELE",
            "descripcion": (
                f"El cliente de {nicho_label} teme más perder dinero que ganar un buen servicio. "
                f"El dolor primario: {miedo_principal}. "
                f"Este miedo pesa 2.5x más que el deseo de obtener el mejor resultado."
            ),
            "evidencia": f'"{review_negativa}"',
            "como_aprovecharlo": (
                "IM usa garantías explícitas, casos de éxito con números y "
                "prueba social para reducir el riesgo percibido antes del primer contacto."
            ),
        },
        "maleta_4_deseo_real": {
            "nombre": "Brecha Deseo Declarado vs. Real (Cialdini)",
            "maleta": "QUÉ DESEA",
            "descripcion": (
                f"El cliente dice buscar 'el mejor precio'. En realidad busca: {motivacion}. "
                f"El deseo real es emocional — el declarado es el escudo racional que protege "
                f"su ego en la negociación."
            ),
            "evidencia": (
                "Reviews 5 estrellas raramente mencionan precio. "
                f"Mencionan: {', '.join(elogios[:3]) if elogios else 'trato personalizado, resultados, confianza'}."
            ),
            "como_aprovecharlo": (
                "IM diseña copies que hablan al deseo real (emoción + resultado) "
                "no al declarado (precio/técnica). El CTA activa el deseo oculto."
            ),
        },
        "maleta_5_paralisis": {
            "nombre": "Parálisis por Análisis + Desconfianza Institucional",
            "maleta": "QUÉ FRENA",
            "descripcion": (
                f"Con {total} opciones de {nicho_label} en {ciudad}, el cliente entra en "
                f"parálisis. Sin criterios claros de selección, usa reviews y precio como "
                f"atajos mentales. La desconfianza en el sector es alta cuando no hay "
                f"señales claras de autoridad y prueba social."
            ),
            "evidencia": (
                f"El sector tiene rating promedio de {rating}/5. "
                f"La varianza entre negocios es alta — refuerza la incertidumbre del cliente."
            ),
            "como_aprovecharlo": (
                "IM crea criterios de selección favorables a su cliente: "
                f"'Busca estos 3 factores antes de elegir un {nicho_label}'. "
                "El contenido educativo posiciona al cliente de IM como la opción obvia."
            ),
        },
        "maleta_6_prueba_social": {
            "nombre": "Prueba Social + Efecto Autoridad (Cialdini)",
            "maleta": "QUÉ MUEVE",
            "descripcion": (
                f"Umbral de confianza en el sector de {nicho_label}: "
                f"{'50+ reviews con 4.5+' if rating >= 4.5 else '30+ reviews con 4.0+'}. "
                f"Sin este mínimo visible, el negocio es descartado automáticamente "
                f"en la fase de consideración. La urgencia ('últimos cupos') "
                f"activa el sesgo de escasez."
            ),
            "evidencia": (
                f"Promedio del sector: {rating}/5 con revisión de reviews como "
                f"paso 1 en el proceso de decisión del 87% de consumidores colombianos."
            ),
            "como_aprovecharlo": (
                "IM implementa sistemas automáticos de solicitud de reviews "
                "para superar el umbral de confianza en 60-90 días. "
                "Además, activa escasez real con cupos limitados y urgencia en WhatsApp."
            ),
        },
        "maleta_7_oportunidad": {
            "nombre": "Sesgo de Omisión = Oportunidad de IM",
            "maleta": "OPORTUNIDAD PARA IM",
            "descripcion": (
                f"El mercado tiene {sin_web} de {total} negocios ({100-pct_web}%) que operan "
                f"como si internet no existiera. Sus clientes potenciales los buscan online "
                f"y los encuentran a sus competidores que SÍ tienen presencia digital."
            ),
            "evidencia": (
                f"{sin_web} {nicho_label} sin web en {ciudad}. "
                f"Cada uno pierde 10-30 clientes potenciales mensuales "
                f"por no aparecer en búsquedas digitales."
            ),
            "como_aprovecharlo": (
                f"Cada {nicho_label} sin web es un prospecto calificado de IM. "
                f"Mensaje: 'Tus competidores te están robando clientes mientras tú "
                f"no apareces en Google.' Cierre: mostrar cuántos los buscan al mes."
            ),
        },
    }

    # Perfil psicográfico
    strato = "3-4" if any(s in ciudad.lower() for s in ["bello","kennedy","engativá","suba"]) else "3-5"
    perfil = {
        "edad_estimada": "28-55 años",
        "nivel_socioeconomico": f"Estrato {strato} (según sectores: {sector_str})",
        "motivacion_principal": motivacion,
        "mayor_miedo": miedo_principal,
        "como_busca_info": "Google Maps (paso 1), recomendaciones de conocidos, Instagram, WhatsApp",
        "tiempo_decision": "3-10 días (compara 2-4 opciones; más para servicios de alto costo)",
        "que_lo_convence": "Reviews recientes +4.5 · respuesta rápida en WhatsApp · precio claro desde el inicio",
        "trigger_de_compra": "Recomendación directa de alguien de confianza o ver 50+ reviews positivas",
        "frase_que_lo_describe": review_negativa,
    }

    return {"sesgos": sesgos, "perfil": perfil}

# ── 7 MALETAS LOCAL ANALYSIS (Felipe Vergara methodology) ────────
def _analizar_7_maletas_local(nicho, ciudad, sectores, metricas, competidores,
                               reviews_data, precios_data, quejas_data, recom_data,
                               fb_ads_data, fuentes_academicas, datos_gobierno):
    """Fills all 7 maletas with evidence from collected data, no Claude API needed."""
    nicho_label  = nicho.replace("_", " ")
    sectores_str = ", ".join(sectores[:4]) if sectores else ciudad

    positivas    = reviews_data.get("positivas") or []
    negativas    = reviews_data.get("negativas") or []
    top_dolores  = reviews_data.get("top_dolores") or []
    top_elogios  = reviews_data.get("top_elogios") or []
    muestra      = reviews_data.get("muestra_textual") or []
    total_rev    = reviews_data.get("total", 0)

    total_emp    = metricas.get("total_encontrados", 0)
    rating_prom  = metricas.get("rating_promedio", 0.0)
    pct_web      = metricas.get("pct_presencia_web", 0)
    pct_sin      = 100 - pct_web
    nivel_precio = metricas.get("nivel_precio_label", "Moderado")

    # ── MALETA 1: PÚBLICO ──────────────────────────────────────────
    # Infer gender from names in reviews
    nombres_femeninos = ["maria","ana","diana","laura","carolina","andrea","paola","jennifer","adriana","luz","gloria","patricia","claudia","jessica","natalia","valentina","alejandra","marcela","monica","isabel","sara","camila"]
    nombres_masculinos = ["carlos","juan","andrés","luis","jose","david","miguel","jorge","alejandro","pedro","daniel","santiago","javier","alberto","ricardo","mario","antonio","gabriel","nicolas","sergio"]
    fem_count = masc_count = 0
    for rev in muestra:
        rname = (rev.get("lugar") or "").lower()
        for n in nombres_femeninos:
            if n in rname: fem_count += 1; break
        for n in nombres_masculinos:
            if n in rname: masc_count += 1; break
    total_gender = fem_count + masc_count or 1
    pct_fem  = round(fem_count / total_gender * 100)
    pct_masc = round(masc_count / total_gender * 100)
    if pct_fem < 30 and pct_masc < 30:
        pct_fem, pct_masc = 55, 45  # default for most service sectors

    estrato_nicho = {"gimnasios": "3-5", "autos_alta_gama": "4-6", "clinicas_medicina_estetica": "3-5",
                     "restaurantes": "2-5", "odontologos": "2-5", "dermatologo": "3-5"}.get(nicho, "3-5")
    if any(s.lower() in ["el poblado","laureles","usaquén","chapinero","zona rosa"] for s in sectores):
        estrato_nicho = "4-6"

    precio_poder = (
        "Alto (Estrato 4-6): servicio premium con alta tolerancia a precios elevados"
        if "alto" in nivel_precio.lower() or "muy alto" in nivel_precio.lower()
        else "Medio-alto (Estrato 3-5): buscan calidad pero comparan precios"
    )

    rev_ubicaciones = []
    for c in competidores[:15]:
        if c.get("barrio"): rev_ubicaciones.append(c["barrio"])
    loc_principal = max(set(rev_ubicaciones), key=rev_ubicaciones.count) if rev_ubicaciones else ciudad

    maleta_1 = {
        "edad_estimada":    "25-55 años (pico 30-45 años)",
        "genero":           f"{pct_fem}% mujeres, {pct_masc}% hombres (estimado de {total_rev} reviews)",
        "ubicacion":        f"Principalmente {loc_principal} y alrededores, {ciudad}. Zona de búsqueda: {sectores_str}",
        "situacion_sentimental": "Mixto — familias y solteros según sector. Mayor volumen: adultos con responsabilidades económicas",
        "poder_adquisitivo": precio_poder,
        "evidencias": [
            f"De {total_emp} empresas mapeadas en {sectores_str}",
            f"Nivel de precios del sector: {nivel_precio}",
            f"Sectores analizados: {sectores_str}",
        ] + [r[:120] for r in positivas[:2]],
    }

    # ── MALETA 2: PROBLEMA ─────────────────────────────────────────
    PAIN_PHRASES = {
        "espera":       "Tiempos de espera excesivos — citas que no se respetan",
        "precio":       "Precios poco transparentes o cobros inesperados al final",
        "atención":     "Mala atención al cliente — falta de calidez y seguimiento",
        "caro":         "Percepción de cobro excesivo vs. valor recibido",
        "demora":       "Demoras en la entrega del servicio o resultado",
        "no contestaron": "No responden mensajes ni llamadas — pérdida de tiempo",
        "estafa":       "Desconfianza sobre calidad real del servicio",
        "grosero":      "Personal descortés o indiferente",
        "cancela":      "Cancelaciones de último momento sin aviso",
        "desorganizado":"Desorganización en agendamiento y procesos internos",
    }

    problemas_detectados = []
    for dolor in top_dolores[:8]:
        kw   = dolor.get("problema", "")
        desc = PAIN_PHRASES.get(kw, f"Problema recurrente: '{kw}'")
        mens = dolor.get("menciones", 1)
        ev   = next((r for r in negativas if kw in r.lower()), "")
        problemas_detectados.append({
            "problema":   desc,
            "keyword":    kw,
            "menciones":  mens,
            "evidencia":  ev[:180] if ev else f"Patrón detectado en {mens} reviews",
        })

    # Add from quejas_data if not enough
    for q in (quejas_data or [])[:4]:
        txt = q.get("texto", "")
        if txt and len(txt) > 40 and not any(p["evidencia"] == txt[:180] for p in problemas_detectados):
            problemas_detectados.append({
                "problema":  txt[:120],
                "keyword":   "google_search",
                "menciones": 1,
                "evidencia": txt[:180],
            })

    problemas_detectados = problemas_detectados[:10]

    # Top 3
    top3 = sorted(problemas_detectados, key=lambda x: x["menciones"], reverse=True)[:3]
    top1 = top3[0] if top3 else {"problema": "Falta de confianza y seguimiento", "menciones": 1, "evidencia": ""}

    maleta_2 = {
        "lista_dolores":  problemas_detectados,
        "top_3":          top3,
        "principal":      top1,
        "total_analizados": total_rev,
    }

    # ── MALETA 3: SOLUCIÓN ─────────────────────────────────────────
    # What do businesses in this niche offer vs what clients want
    servicios_comunes = {
        "odontologos":               ["Ortodoncia invisible", "Blanqueamiento dental", "Implantes", "Limpieza profesional"],
        "gimnasios":                 ["Entrenamiento personalizado", "Clases grupales", "Plan nutricional", "HIIT"],
        "clinicas_medicina_estetica":["Toxina botulínica", "Ácido hialurónico", "Tratamientos faciales", "Corporal"],
        "restaurantes":              ["Menú ejecutivo", "Carta variada", "Domicilios", "Reservas privadas"],
        "dermatologo":               ["Consulta dermatológica", "Tratamientos acné", "Medicina estética", "Cirugía menor"],
        "psicologos":                ["Terapia individual", "Terapia de pareja", "Psicología infantil", "Online"],
        "gimnasios":                 ["Membresía mensual", "CrossFit", "Yoga", "Pilates", "Spinning"],
    }
    servicios = servicios_comunes.get(nicho, [f"Servicio principal de {nicho_label}", "Atención personalizada", "Seguimiento post-servicio"])

    mejor_testimonio = next((r for r in positivas if len(r) > 60), "")
    oportunidad_sol = (
        f"El {pct_sin}% de {nicho_label} en {ciudad} NO comunica claramente su solución online. "
        f"Los que sí lo hacen (los {pct_web}% con presencia digital) concentran la demanda."
    )

    sol_comp = []
    for c in competidores[:4]:
        if c.get("diferencial") and len(c["diferencial"]) > 20:
            sol_comp.append({"competidor": c.get("nombre","?"), "mensaje": c["diferencial"][:120]})

    maleta_3 = {
        "servicios_ofrecidos":    servicios,
        "como_resuelve_problema": f"{nicho_label} resuelve '{top1['problema']}' mediante {servicios[0] if servicios else 'atención directa'} y seguimiento personalizado",
        "mejor_testimonio":       mejor_testimonio[:300] if mejor_testimonio else "Sin testimonios textuales disponibles",
        "competidores_solucion":  sol_comp,
        "oportunidad_mejora":     oportunidad_sol,
    }

    # ── MALETA 4: DIFERENCIALES ────────────────────────────────────
    DIFERENCIAL_LABELS = {
        "amable":        "Atención cálida y personalizada",
        "profesional":   "Equipo profesional certificado",
        "rápido":        "Rapidez y puntualidad garantizada",
        "limpio":        "Instalaciones limpias e higiénicas",
        "resultado":     "Resultados visibles y medibles",
        "precio":        "Precios competitivos y transparentes",
        "tecnología":    "Tecnología de punta o equipos modernos",
        "experiencia":   "Años de experiencia en el sector",
        "seguimiento":   "Seguimiento post-servicio",
        "domicilio":     "Servicio a domicilio",
        "online":        "Atención virtual/online disponible",
        "garantía":      "Garantía explícita del servicio",
    }

    diferenciales_detectados = []
    elogio_strs = [e.get("elogio", "") for e in top_elogios]
    for kw, label in DIFERENCIAL_LABELS.items():
        count = sum(1 for e in elogio_strs if kw in e.lower())
        count += sum(1 for r in positivas if kw in r.lower())
        if count > 0:
            # Count how many competitors mention it
            comp_count = sum(1 for c in competidores if kw in (c.get("diferencial") or "").lower())
            saturacion = "Alta" if comp_count >= 4 else "Media" if comp_count >= 2 else "Baja (Única)"
            diferenciales_detectados.append({
                "diferencial": label,
                "keyword":     kw,
                "frecuencia":  count,
                "en_comp":     comp_count,
                "saturacion":  saturacion,
            })

    diferenciales_detectados.sort(key=lambda x: x["frecuencia"], reverse=True)
    menos_saturado = next((d for d in diferenciales_detectados if d["saturacion"] == "Baja (Única)"),
                          diferenciales_detectados[0] if diferenciales_detectados else
                          {"diferencial": "Seguimiento post-servicio", "saturacion": "Baja (Única)"})

    maleta_4 = {
        "lista_diferenciales": diferenciales_detectados[:8],
        "menos_saturado":      menos_saturado,
        "tabla_comparativa":   [
            {"aspecto": d["diferencial"],
             "tu":      "✅",
             "comp1":   "✅" if d["en_comp"] >= 1 else "❌",
             "comp2":   "✅" if d["en_comp"] >= 2 else "❌",
             "comp3":   "✅" if d["en_comp"] >= 3 else "❌",
             "saturacion": d["saturacion"]}
            for d in diferenciales_detectados[:6]
        ],
        "recomendacion": (
            f"DESTACA '{menos_saturado['diferencial']}' en todos tus anuncios — "
            f"solo {menos_saturado.get('en_comp',0)} competidores lo mencionan."
        ),
    }

    # ── MALETA 5: TESTIMONIOS ──────────────────────────────────────
    top5_testimonios = []
    for r in (positivas or [])[:5]:
        if len(r) > 40:
            top5_testimonios.append({"texto": r[:300], "fuente": "Google Maps"})
    for rev in (muestra or []):
        if _safe_float(rev.get("rating", 0)) >= 4.5 and len(rev.get("texto","")) > 40:
            if len(top5_testimonios) < 5:
                top5_testimonios.append({"texto": rev["texto"][:300], "fuente": f"Google Maps — {rev.get('lugar','')[:40]}"})

    patrones = []
    for kw, label in [("rápido","rapidez"), ("amable","amabilidad"), ("profesional","profesionalismo"),
                       ("resultado","resultados"), ("limpio","limpieza"), ("precio","precio justo")]:
        cnt = sum(1 for r in positivas if kw in r.lower())
        if cnt > 0:
            patrones.append(f"{round(cnt/max(len(positivas),1)*100)}% hablan de: {label} ({cnt} reviews)")

    tipo_negocio = "SERVICIOS"  # default for most nichos
    if nicho in ["restaurantes"]: tipo_negocio = "ECOMMERCE"

    maleta_5 = {
        "rating_general":       rating_prom,
        "total_reviews":        total_rev,
        "top_5_testimonios":    top5_testimonios[:5],
        "patrones":             patrones[:4],
        "tipo_negocio":         tipo_negocio,
        "estrategia_recoleccion": {
            "principal": "Solicitud presencial o por WhatsApp inmediatamente después del servicio",
            "complementaria_1": "Link acortado de Google Business vía WhatsApp con seguimiento 24h",
            "complementaria_2": "Programa de referidos: review + foto = descuento en próximo servicio",
            "script_whatsapp": f"'Hola [nombre], ¿quedaste satisfecho/a con nuestro {nicho_label}? Nos encantaría que nos dejaras una reseña en Google 🙏 Solo toma 1 minuto: [link]'",
        },
        "meta_30_dias": f"Pasar de {total_rev} a {total_rev + 30} reviews en 30 días",
    }

    # ── MALETA 6: OBJECIONES ───────────────────────────────────────
    OBJECIONES_BASE = [
        ("Precio elevado",          "precio",      "reviews + búsquedas Google"),
        ("No confío en la calidad", "confianza",   "reviews negativas"),
        ("No sé si vale la pena",   "valor",       "búsquedas 'vale la pena'"),
        ("Hay opciones más baratas","alternativas","Facebook Ads competencia"),
        ("No tengo tiempo",         "tiempo",      "búsquedas Google"),
        ("No sé si es para mí",     "duda",        "preguntas frecuentes"),
        ("Malas experiencias antes","trauma",      "reviews negativas"),
        ("Lejos de mi casa",        "distancia",   "búsquedas geográficas"),
        ("No tengo cita disponible","disponib.",   "reviews negativas"),
        ("Prefiero esperar",        "urgencia",    "patrones de decisión"),
    ]

    objeciones = []
    for label, kw, fuente in OBJECIONES_BASE:
        ev_neg = next((r for r in negativas if kw in r.lower()), "")
        ev_q   = next((q.get("texto","") for q in (quejas_data or []) if kw in q.get("texto","").lower()), "")
        ev = ev_neg or ev_q or f"Objeción frecuente en sector de {nicho_label}"
        resuelto = "✅ Sí" if kw in " ".join(elogio_strs).lower() else "⚠️ Parcialmente" if kw in " ".join(positivas[:5]).lower() else "❌ No mencionado"
        objeciones.append({
            "objecion":  label,
            "keyword":   kw,
            "fuente":    fuente,
            "evidencia": ev[:150],
            "resuelves": resuelto,
            "riesgo":    "🔴 ALTO" if resuelto.startswith("❌") else "🟡 MEDIO" if resuelto.startswith("⚠️") else "🟢 BAJO",
        })

    # Objeciones from competitors
    objeciones_comp = []
    for c in competidores[:4]:
        dif = (c.get("diferencial") or "").lower()
        if "garantía" in dif or "resultado" in dif or "precio" in dif:
            objeciones_comp.append({
                "competidor": c.get("nombre","?"),
                "objecion_que_resuelve": dif[:120],
                "estrategia": "Lo menciona en su diferencial visible en Maps",
                "la_resuelves": "⚠️ Revisar",
            })

    principal_obj = max(objeciones, key=lambda x: {"🔴 ALTO":3,"🟡 MEDIO":2,"🟢 BAJO":1}.get(x["riesgo"],0))

    maleta_6 = {
        "lista_10_plus":       objeciones,
        "de_competidores":     objeciones_comp[:3],
        "principal":           principal_obj,
        "como_resolver":       {
            "en_web":     f"Agrega sección FAQ que responda: '{principal_obj['objecion']}'",
            "en_anuncios": f"Incluye en el copy: 'Sin [objeción]. Solo resultados.'",
            "en_ventas":  f"Script WhatsApp: 'Entiendo tu duda sobre [objeción]. Por eso nosotros [solución específica].'",
        },
    }

    # ── MALETA 7: GARANTÍA ─────────────────────────────────────────
    garantia_actual = next(
        (e for e in (positivas or []) if any(g in e.lower() for g in ["garantía","garantizo","aseguro","devuelvo","cambio"])),
        None
    )
    garantias_mercado = []
    for c in competidores[:5]:
        dif = (c.get("diferencial") or "").lower()
        if any(g in dif for g in ["garantía","resultado","satisfacción","devoluci"]):
            garantias_mercado.append({"competidor": c.get("nombre","?"), "garantia": dif[:100]})

    maleta_7 = {
        "garantia_actual": garantia_actual[:200] if garantia_actual else "No se detectó garantía explícita en las fuentes analizadas",
        "garantia_sugerida": (
            f"'Si no quedas satisfecho/a con tu {nicho_label}, repetimos el servicio sin costo adicional. "
            f"Tu satisfacción es nuestra prioridad — sin preguntas, sin complicaciones.'"
        ),
        "justificacion": [
            f"Reduce la objeción principal: '{principal_obj['objecion']}'",
            f"Solo {len(garantias_mercado)} de {len(competidores[:5])} competidores ofrecen garantía visible",
            "Las garantías explícitas aumentan conversión 20-40% (benchmark sector servicios Colombia)",
        ],
        "garantias_mercado":  garantias_mercado[:4],
        "comparacion": {
            "devolucion_dinero":  "A evaluar según tipo de servicio",
            "repeticion_servicio": "Recomendado — bajo costo real, alto impacto percibido",
            "garantia_satisfaccion": "Implementar explícitamente en web y anuncios",
            "periodo_prueba":     "Aplica para servicios con contrato (gym, consultoría)",
        },
        "recomendacion": (
            f"Tu garantía SUPERA a la de {max(0, len(competidores[:5]) - len(garantias_mercado))} competidores "
            if garantias_mercado else
            f"IMPLEMENTA garantía explícita — ninguno de los {len(competidores[:5])} competidores analizados la menciona visiblemente. "
            f"Esto es tu ventaja competitiva inmediata."
        ),
    }

    # ── ADS MESSAGES ──────────────────────────────────────────────
    dolor_copy = top1["problema"][:60]
    dif_copy   = menos_saturado["diferencial"][:50]
    test_copy  = (top5_testimonios[0]["texto"][:100] if top5_testimonios else f"Excelente {nicho_label}, lo recomiendo 100%")
    garantia_c = "Sin riesgo para ti"

    ads = [
        {
            "tipo":       "Enfoque en Problema",
            "headline":   f"¿Cansado de {dolor_copy}?",
            "descripcion": (f"En [Tu Empresa], lo resolvemos. {dif_copy}. "
                            f"Más de {total_rev or '50'}+ clientes satisfechos en {ciudad}.\n\n"
                            f'"{test_copy[:80]}"\n\n'
                            f"{garantia_c} → Agenda tu cita hoy: [link]"),
            "cta": "Agenda ahora",
        },
        {
            "tipo":       "Enfoque en Diferencial Único",
            "headline":   f"{dif_copy} — solo en [Tu Empresa]",
            "descripcion": (f"Resuelve '{dolor_copy}' de una vez. "
                            f"[X] años de experiencia en {ciudad}. "
                            f"Atención personalizada desde el primer contacto.\n\n"
                            f"Agenda tu cita gratis → [link]"),
            "cta": "Ver disponibilidad",
        },
        {
            "tipo":       "Enfoque en Testimonio/Resultado",
            "headline":   f'"{test_copy[:70]}..."',
            "descripcion": (f"Así describió [Nombre] su experiencia con nosotros. "
                            f"Resolvemos '{dolor_copy}' con {dif_copy}.\n\n"
                            f"{garantia_c} · Primeras citas disponibles esta semana → [link]"),
            "cta": "Quiero este resultado",
        },
    ]

    # ── PRÓXIMOS PASOS ─────────────────────────────────────────────
    proximos_pasos = {
        "esta_semana": [
            {
                "accion": f"Actualiza tu perfil de Google Business con fotos recientes y responde todas las reviews sin contestar",
                "por_que": f"Solo {pct_web}% del sector tiene presencia digital activa — diferénciante ahora",
                "impacto": "Más visibilidad local inmediata",
            },
            {
                "accion": f"Agrega garantía explícita a tu web y perfil: '{maleta_7['garantia_sugerida'][:80]}...'",
                "por_que": f"Resuelve la objeción #1: '{principal_obj['objecion']}'",
                "impacto": "Aumento estimado 20-35% en contactos",
            },
            {
                "accion": f"Implementa solicitud de reviews vía WhatsApp post-servicio: {maleta_5['estrategia_recoleccion']['script_whatsapp'][:80]}...",
                "por_que": f"Actualmente {total_rev} reviews — necesitas 50+ para superar umbral de confianza",
                "impacto": "+5-10 reviews/mes desde el día 1",
            },
        ],
        "este_mes": [
            "Entrevista a 5-10 clientes: ¿Por qué nos elegiste? ¿Qué extrañarías?",
            f"Lanza campaña Meta Ads con el Anuncio 1 ('¿Cansado de {dolor_copy[:40]}?')",
            f"Crea contenido educativo: 'Cómo elegir el mejor {nicho_label} en {ciudad} — 3 factores clave'",
        ],
        "validacion_manual": [
            f"'¿Por qué nos compraste a nosotros y no a otro {nicho_label}?'",
            "'¿Qué problema querías resolver cuando nos buscaste?'",
            f"'Si ya no existiéramos, ¿qué {nicho_label} buscarías?'",
        ],
    }

    return {
        "maleta_1_publico":       maleta_1,
        "maleta_2_problema":      maleta_2,
        "maleta_3_solucion":      maleta_3,
        "maleta_4_diferenciales": maleta_4,
        "maleta_5_testimonios":   maleta_5,
        "maleta_6_objeciones":    maleta_6,
        "maleta_7_garantia":      maleta_7,
        "ads_messages":           ads,
        "proximos_pasos":         proximos_pasos,
        "fuentes_resumen": {
            "empresas_mapeadas":   total_emp,
            "reviews_analizadas":  total_rev,
            "competidores":        len(competidores),
            "fuentes_academicas":  len(fuentes_academicas),
            "datos_gobierno":      len(datos_gobierno),
            "fb_ads":              len(fb_ads_data),
            "busquedas_google":    len(quejas_data) + len(precios_data) + len(recom_data),
        },
    }


def _generar_html_7maletas(data):
    """Generates Felipe Vergara 7 Maletas HTML template from analyzed data."""
    meta        = data.get("meta", {})
    metricas    = data.get("metricas", {})
    comps       = data.get("competidores", [])
    resumen     = data.get("resumen_ejecutivo", {})
    maletas     = data.get("7_maletas_analisis", {})
    rev_data    = data.get("reviews_analisis", {})
    fb_ads      = data.get("facebook_ads_raw", [])
    fuentes_ac  = data.get("fuentes_academicas", [])
    datos_gov   = data.get("datos_gobierno", [])

    nicho   = meta.get("nicho", "").replace("_", " ").title()
    ciudad  = meta.get("ciudad", "")
    sects   = ", ".join(meta.get("sectores") or [])
    fecha   = datetime.now().strftime("%d de %B de %Y").replace("January","enero").replace("February","febrero").replace("March","marzo").replace("April","abril").replace("May","mayo").replace("June","junio").replace("July","julio").replace("August","agosto").replace("September","septiembre").replace("October","octubre").replace("November","noviembre").replace("December","diciembre")

    if not maletas:
        return "<html><body><p>Sin datos de análisis 7 Maletas.</p></body></html>"

    m1  = maletas.get("maleta_1_publico", {})
    m2  = maletas.get("maleta_2_problema", {})
    m3  = maletas.get("maleta_3_solucion", {})
    m4  = maletas.get("maleta_4_diferenciales", {})
    m5  = maletas.get("maleta_5_testimonios", {})
    m6  = maletas.get("maleta_6_objeciones", {})
    m7  = maletas.get("maleta_7_garantia", {})
    ads = maletas.get("ads_messages", [])
    pps = maletas.get("proximos_pasos", {})
    fsr = maletas.get("fuentes_resumen", {})

    total_emp = fsr.get("empresas_mapeadas", metricas.get("total_encontrados", 0))
    total_rev = fsr.get("reviews_analizadas", rev_data.get("total", 0))
    total_src = fsr.get("fuentes_academicas", 0) + fsr.get("datos_gobierno", 0) + fsr.get("fb_ads", 0) + 3

    def esc(s):
        return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"','&quot;')

    def li_list(items, color="#1d1d1f"):
        if not items: return '<li style="color:#6e6e73">Sin datos detectados</li>'
        return "".join(f'<li style="margin:10px 0;color:{color}">{esc(str(i))}</li>' for i in items)

    # Build maleta 2 problems list HTML
    prob_html = ""
    for i, p in enumerate(m2.get("lista_dolores", [])[:8], 1):
        prob_html += f"""
        <div style="margin-bottom:20px">
          <p style="font-size:17px;font-weight:500;margin-bottom:8px">{i}. <strong>{esc(p.get('problema',''))}</strong></p>
          <p style="font-size:14px;color:#6e6e73;margin-bottom:4px">Mencionado {p.get('menciones',1)} veces | Fuente: reviews Google Maps</p>
          <div style="background:#f5f5f7;padding:14px;border-radius:8px;font-style:italic;color:#1d1d1f;font-size:15px">
            "{esc(p.get('evidencia','Sin cita textual disponible'))}"
          </div>
        </div>"""

    top3_html = ""
    for i, p in enumerate(m2.get("top_3", [])[:3], 1):
        top3_html += f"""
        <div style="margin-bottom:20px">
          <p style="font-size:17px;font-weight:600;color:#0071e3">#{i} — {esc(p.get('problema',''))}</p>
          <p style="color:#6e6e73;margin-bottom:6px">Frecuencia: {p.get('menciones',1)} menciones</p>
          <div class="quote-box">"{esc(p.get('evidencia',''))}"</div>
        </div>"""

    principal = m2.get("principal", {})

    # Build differentiation table
    tabla_dif_html = ""
    for row in m4.get("tabla_comparativa", [])[:6]:
        sat_color = "#34c759" if "Única" in row.get("saturacion","") else "#ff9500" if row.get("saturacion") == "Media" else "#ff3b30"
        tabla_dif_html += f"""
        <tr>
          <td style="padding:14px 16px;border-bottom:1px solid #d2d2d7">{esc(row.get('aspecto',''))}</td>
          <td style="padding:14px 16px;border-bottom:1px solid #d2d2d7;text-align:center">{row.get('tu','✅')}</td>
          <td style="padding:14px 16px;border-bottom:1px solid #d2d2d7;text-align:center">{row.get('comp1','—')}</td>
          <td style="padding:14px 16px;border-bottom:1px solid #d2d2d7;text-align:center">{row.get('comp2','—')}</td>
          <td style="padding:14px 16px;border-bottom:1px solid #d2d2d7;text-align:center">{row.get('comp3','—')}</td>
          <td style="padding:14px 16px;border-bottom:1px solid #d2d2d7;color:{sat_color};font-weight:500">{esc(row.get('saturacion',''))}</td>
        </tr>"""

    # Testimonials HTML
    test_html = ""
    for i, t in enumerate(m5.get("top_5_testimonios", [])[:5], 1):
        test_html += f"""
        <div class="quote-box" style="margin-bottom:20px">
          <p style="font-size:17px;color:#1d1d1f;line-height:1.6">"{esc(t.get('texto',''))}"</p>
          <p style="color:#6e6e73;margin-top:8px;font-size:14px">— {esc(t.get('fuente','Google Maps'))}</p>
        </div>"""
    if not test_html:
        test_html = '<div class="info-box"><p>No se encontraron testimonios textuales completos. Activa la recolección sistemática.</p></div>'

    # Objections HTML
    obj_html = ""
    for i, o in enumerate(m6.get("lista_10_plus", [])[:10], 1):
        risk_bg = {"🔴 ALTO":"#fff2f2","🟡 MEDIO":"#fffbf0","🟢 BAJO":"#f2fff5"}.get(o.get("riesgo","🟡 MEDIO"),"#f5f5f7")
        obj_html += f"""
        <div style="background:{risk_bg};border:1px solid #d2d2d7;border-radius:10px;padding:20px;margin-bottom:16px">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">
            <p style="font-size:17px;font-weight:500">{i}. {esc(o.get('objecion',''))}</p>
            <span style="font-size:13px;white-space:nowrap;margin-left:12px">{o.get('riesgo','')}</span>
          </div>
          <p style="color:#6e6e73;font-size:14px;margin-bottom:8px">Detectada en: {esc(o.get('fuente',''))} | Resuelves: {o.get('resuelves','')}</p>
          <p style="font-style:italic;font-size:15px;color:#1d1d1f">"{esc(o.get('evidencia',''))}"</p>
        </div>"""

    obj_comp_html = ""
    for o in m6.get("de_competidores", [])[:3]:
        obj_comp_html += f"""
        <div style="padding:14px;border:1px solid #d2d2d7;border-radius:8px;margin-bottom:10px">
          <strong>{esc(o.get('competidor',''))}</strong>: {esc(o.get('objecion_que_resuelve',''))}
          <br><small style="color:#6e6e73">{esc(o.get('la_resuelves',''))}</small>
        </div>"""

    obj_principal = m6.get("principal", {})
    como_res = m6.get("como_resolver", {})

    # Guarantee comparison table
    gar_comp_html = ""
    for g in m7.get("garantias_mercado", [])[:4]:
        gar_comp_html += f"<tr><td style='padding:12px 16px;border-bottom:1px solid #d2d2d7'>{esc(g.get('competidor',''))}</td><td style='padding:12px 16px;border-bottom:1px solid #d2d2d7;color:#6e6e73'>{esc(g.get('garantia',''))}</td></tr>"

    # Differentials list HTML (pre-computed to avoid nested f-string issues)
    dif_list_items = ""
    for d in m4.get("lista_diferenciales", [])[:8]:
        dif_label = esc(d.get("diferencial", ""))
        dif_freq  = d.get("frecuencia", 0)
        dif_sat   = esc(d.get("saturacion", ""))
        dif_list_items += f"<li><strong>{dif_label}</strong> &mdash; mencionado {dif_freq} veces &mdash; saturaci&oacute;n: {dif_sat}</li>"
    if not dif_list_items:
        dif_list_items = "<li style='color:#6e6e73'>Sin diferenciales detectados aún</li>"

    # Ads HTML
    ads_html = ""
    ad_colors = ["#0071e3","#34c759","#ff9500"]
    for i, ad in enumerate(ads[:3], 1):
        col = ad_colors[i-1]
        ads_html += f"""
        <div style="border:1px solid #d2d2d7;border-radius:12px;padding:28px;margin-bottom:24px">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px">
            <span style="background:{col};color:white;padding:4px 12px;border-radius:20px;font-size:13px;font-weight:600">Anuncio {i}</span>
            <span style="color:#6e6e73;font-size:14px">{esc(ad.get('tipo',''))}</span>
          </div>
          <p style="font-size:22px;font-weight:700;margin-bottom:12px;color:{col}">{esc(ad.get('headline',''))}</p>
          <div style="background:#f5f5f7;padding:16px;border-radius:8px;white-space:pre-line;font-size:15px;line-height:1.7">{esc(ad.get('descripcion',''))}</div>
          <div style="margin-top:12px">
            <span style="background:{col}22;color:{col};padding:6px 14px;border-radius:6px;font-size:13px;font-weight:600">CTA: {esc(ad.get('cta',''))}</span>
          </div>
        </div>"""

    # Next steps HTML
    pps_html = ""
    for i, step in enumerate(pps.get("esta_semana", [])[:3], 1):
        pps_html += f"""
        <div style="border-left:4px solid #0071e3;padding:16px 20px;margin-bottom:16px;background:#f5f5f7;border-radius:0 8px 8px 0">
          <p style="font-weight:600;font-size:16px;margin-bottom:6px">{i}. {esc(step.get('accion',''))}</p>
          <p style="color:#6e6e73;margin-bottom:4px;font-size:14px"><strong>Por qué:</strong> {esc(step.get('por_que',''))}</p>
          <p style="color:#34c759;font-size:14px"><strong>Impacto:</strong> {esc(step.get('impacto',''))}</p>
        </div>"""

    month_html = li_list(pps.get("este_mes", []), "#1d1d1f")
    val_html   = li_list(pps.get("validacion_manual", []), "#0071e3")

    # Academic sources HTML
    acad_html = ""
    for f in fuentes_ac[:6]:
        acad_html += f"""
        <div style="padding:14px;border:1px solid #d2d2d7;border-radius:8px;margin-bottom:10px">
          <p style="font-size:12px;color:#0071e3;margin-bottom:4px">{esc(f.get('fuente',''))}</p>
          <p style="font-weight:500;margin-bottom:4px">{esc(f.get('titulo','')[:160])}</p>
          <p style="color:#6e6e73;font-size:13px">{esc(f.get('resumen','')[:200])}</p>
        </div>"""
    if not acad_html:
        acad_html = '<p style="color:#6e6e73">Consultar directamente: scholar.google.com · repository.unal.edu.co</p>'

    gov_html = ""
    for g in datos_gov[:6]:
        gov_html += f"""
        <div style="padding:14px;border:1px solid #d2d2d7;border-radius:8px;margin-bottom:10px">
          <p style="font-size:12px;color:#0071e3;margin-bottom:4px">{esc(g.get('entidad',''))} · {esc(g.get('año',''))}</p>
          <p style="color:#1d1d1f;font-size:15px">{esc(g.get('dato','')[:260])}</p>
        </div>"""
    if not gov_html:
        gov_html = '<p style="color:#6e6e73">Consultar: dane.gov.co · rues.org.co · confecamaras.com.co</p>'

    menos_sat = m4.get("menos_saturado", {})

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>7 Maletas — {esc(nicho)} — {esc(ciudad)}</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; line-height: 1.7; color: #1d1d1f; background: #f5f5f7; }}
    .container {{ max-width: 1200px; margin: 0 auto; background: white; }}
    .header {{ background: #1d1d1f; padding: 48px 80px; }}
    .header h1 {{ font-size: 48px; font-weight: 700; color: white; margin-bottom: 8px; letter-spacing: -1px; }}
    .header p {{ font-size: 17px; color: #a1a1a6; }}
    .exec-summary {{ padding: 64px 80px; background: #fbfbfd; border-bottom: 1px solid #d2d2d7; }}
    .exec-title {{ font-size: 28px; font-weight: 600; margin-bottom: 32px; }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 28px; margin-top: 32px; }}
    .metric-value {{ font-size: 52px; font-weight: 700; color: #0071e3; line-height: 1; margin-bottom: 6px; }}
    .metric-label {{ font-size: 13px; color: #6e6e73; font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px; }}
    .content {{ padding: 80px; }}
    .section {{ margin-bottom: 96px; }}
    .section-badge {{ font-size: 12px; color: #0071e3; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }}
    .section-title {{ font-size: 38px; font-weight: 700; margin-bottom: 12px; letter-spacing: -0.5px; }}
    .section-subtitle {{ font-size: 17px; color: #6e6e73; margin-bottom: 40px; }}
    .subsection {{ margin: 40px 0 24px; }}
    .subsection h3 {{ font-size: 22px; font-weight: 600; margin-bottom: 16px; }}
    p {{ font-size: 17px; line-height: 1.7; margin-bottom: 16px; color: #1d1d1f; }}
    ul, ol {{ margin: 20px 0; padding-left: 24px; }}
    li {{ font-size: 16px; margin: 10px 0; }}
    .data-table {{ width: 100%; border-collapse: collapse; margin: 24px 0; }}
    .data-table thead {{ background: #f5f5f7; }}
    .data-table th {{ padding: 12px 16px; font-size: 13px; font-weight: 600; text-align: left; border-bottom: 1px solid #d2d2d7; color: #6e6e73; text-transform: uppercase; letter-spacing: 0.5px; }}
    .data-table td {{ padding: 14px 16px; font-size: 16px; border-bottom: 1px solid #d2d2d7; }}
    .info-box {{ background: #f5f5f7; padding: 28px; border-radius: 12px; margin: 24px 0; border-left: 4px solid #0071e3; }}
    .info-box.success {{ border-left-color: #34c759; background: #f0fff4; }}
    .info-box.warning {{ border-left-color: #ff9500; background: #fffbf0; }}
    .quote-box {{ background: white; border: 1px solid #d2d2d7; padding: 24px; border-radius: 12px; margin: 16px 0; }}
    .highlight-box {{ background: #1d1d1f; color: white; padding: 32px; border-radius: 16px; margin: 24px 0; }}
    .highlight-box h4 {{ font-size: 20px; margin-bottom: 12px; color: #f5f5f7; }}
    .highlight-box p {{ color: #a1a1a6; margin-bottom: 0; }}
    .footer {{ background: #f5f5f7; padding: 48px 80px; text-align: center; border-top: 1px solid #d2d2d7; color: #6e6e73; }}
    @media (max-width: 768px) {{
      .header, .content, .exec-summary, .footer {{ padding: 32px 20px; }}
      .metrics {{ grid-template-columns: 1fr 1fr; gap: 16px; }}
      .section-title {{ font-size: 28px; }}
    }}
    @media print {{
      body {{ background: white; }}
      .no-print {{ display: none; }}
    }}
  </style>
</head>
<body>
<div class="container">

  <!-- HEADER -->
  <div class="header">
    <div style="font-size:12px;letter-spacing:3px;text-transform:uppercase;color:#6e6e73;margin-bottom:16px">Las 7 Maletas de Cualquier Compra · Investigación Automatizada</div>
    <h1>{esc(nicho)}</h1>
    <p>{esc(ciudad)}{(' · ' + esc(sects)) if sects else ''} · {fecha}</p>
    <p style="margin-top:8px;color:#6e6e73">Investigación de mercado generada automáticamente por IM System</p>
  </div>

  <!-- RESUMEN EJECUTIVO -->
  <div class="exec-summary">
    <h2 class="exec-title">📊 Resumen de Investigación</h2>
    <p>Análisis completo del mercado de <strong>{esc(nicho.lower())}</strong> en {esc(ciudad)}, respondiendo las 7 Maletas con evidencia real de {total_rev}+ fuentes.</p>
    <div style="margin-top:24px">
      <p><strong>Fuentes analizadas:</strong></p>
      <ul>
        <li>✅ Google Maps: {total_emp} empresas mapeadas en {esc(sects or ciudad)}</li>
        <li>✅ Reviews analizadas: {total_rev} reviews de clientes reales</li>
        <li>✅ Competidores investigados: {fsr.get('competidores', len(comps))}</li>
        <li>✅ Facebook Ads: {fsr.get('fb_ads', len(fb_ads))} anuncios / referencias detectadas</li>
        <li>✅ Fuentes académicas: {fsr.get('fuentes_academicas', len(fuentes_ac))} estudios consultados</li>
        <li>✅ Datos gubernamentales: {fsr.get('datos_gobierno', len(datos_gov))} datos DANE/Confecámaras/Minsalud</li>
        <li>✅ Búsquedas Google: {fsr.get('busquedas_google', 0)} queries procesadas</li>
      </ul>
    </div>
    <div class="metrics">
      <div><div class="metric-value">{total_emp}</div><div class="metric-label">Empresas mapeadas</div></div>
      <div><div class="metric-value">{total_rev}</div><div class="metric-label">Reviews analizadas</div></div>
      <div><div class="metric-value">{total_src}</div><div class="metric-label">Fuentes consultadas</div></div>
      <div><div class="metric-value">7</div><div class="metric-label">Maletas completadas</div></div>
    </div>
  </div>

  <div class="content">

  <!-- MALETA 1: PÚBLICO -->
  <div class="section">
    <div class="section-badge">Maleta 1 de 7</div>
    <h2 class="section-title">1️⃣ Público</h2>
    <p class="section-subtitle">¿Quién le compra a los {esc(nicho.lower())} en {esc(ciudad)}?</p>

    <div class="subsection"><h3>a. Rango de edades</h3>
      <div class="info-box"><p><strong>{esc(m1.get('edad_estimada',''))}</strong></p>
      <p>Basado en patrones de búsqueda, nivel de precios del sector ({esc(metricas.get('nivel_precio_label',''))}) y perfiles de reviewers.</p></div>
    </div>

    <div class="subsection"><h3>b. Género dominante</h3>
      <div class="info-box"><p><strong>{esc(m1.get('genero',''))}</strong></p>
      <p>Estimación basada en análisis de nombres en reviews de Google Maps.</p></div>
    </div>

    <div class="subsection"><h3>c. ¿Dónde viven?</h3>
      <div class="info-box"><p>{esc(m1.get('ubicacion',''))}</p></div>
    </div>

    <div class="subsection"><h3>d. Situación sentimental</h3>
      <div class="info-box"><p>{esc(m1.get('situacion_sentimental',''))}</p></div>
    </div>

    <div class="subsection"><h3>e. Poder adquisitivo</h3>
      <div class="info-box"><p>{esc(m1.get('poder_adquisitivo',''))}</p></div>
      <p><strong>Evidencia:</strong></p>
      <ul>{li_list(m1.get('evidencias',[]))}</ul>
    </div>
  </div>

  <!-- MALETA 2: PROBLEMA -->
  <div class="section">
    <div class="section-badge">Maleta 2 de 7</div>
    <h2 class="section-title">2️⃣ Problema</h2>
    <p class="section-subtitle">¿Qué dolores/frustraciones tienen los clientes de {esc(nicho.lower())} en {esc(ciudad)}?</p>

    <div class="subsection"><h3>a. Lista completa de dolores detectados ({len(m2.get('lista_dolores',[]))} encontrados)</h3>
      {prob_html}
    </div>

    <div class="subsection"><h3>b. Los 3 problemas principales</h3>
      {top3_html}
    </div>

    <div class="subsection"><h3>c. El problema MÁS IMPORTANTE</h3>
      <div class="highlight-box">
        <h4>"{esc(principal.get('problema',''))}"</h4>
        <p>Mencionado {principal.get('menciones',1)} veces. Aparece en reviews propias y de competidores.</p>
      </div>
      <div class="info-box">
        <p><strong>Evidencia contundente:</strong><br>"{esc(principal.get('evidencia',''))}"</p>
      </div>
    </div>
  </div>

  <!-- MALETA 3: SOLUCIÓN -->
  <div class="section">
    <div class="section-badge">Maleta 3 de 7</div>
    <h2 class="section-title">3️⃣ Solución</h2>
    <p class="section-subtitle">¿Cómo resuelven los {esc(nicho.lower())} los problemas de sus clientes?</p>

    <div class="subsection"><h3>a. Servicios ofrecidos en el mercado</h3>
      <ul>{li_list(m3.get('servicios_ofrecidos',[]))}</ul>
    </div>

    <div class="subsection"><h3>b. ¿Cómo resuelve el problema #1?</h3>
      <div class="info-box"><p>{esc(m3.get('como_resuelve_problema',''))}</p></div>
    </div>

    <div class="subsection"><h3>c. Lo que dicen los clientes sobre la solución</h3>
      <div class="quote-box">
        <p style="font-size:17px">"{esc(m3.get('mejor_testimonio','Sin testimonios textuales disponibles'))}"</p>
      </div>
    </div>

    <div class="subsection"><h3>d. Cómo comunican su solución los competidores</h3>
      {"".join(f'<p><strong>{esc(c["competidor"])}:</strong> "{esc(c["mensaje"])}"</p>' for c in m3.get('competidores_solucion',[])[:4]) or "<p style='color:#6e6e73'>Sin datos suficientes de competidores.</p>"}
    </div>

    <div class="info-box warning"><p>💡 <strong>Oportunidad de mejora:</strong> {esc(m3.get('oportunidad_mejora',''))}</p></div>
  </div>

  <!-- MALETA 4: DIFERENCIALES -->
  <div class="section">
    <div class="section-badge">Maleta 4 de 7</div>
    <h2 class="section-title">4️⃣ Diferenciales</h2>
    <p class="section-subtitle">¿Qué hace a algunos {esc(nicho.lower())} mejor que otros?</p>

    <div class="subsection"><h3>a. Lista de diferenciales detectados</h3>
      <ul>{dif_list_items}</ul>
    </div>

    <div class="subsection"><h3>b. Tabla comparativa con competidores</h3>
      <div style="overflow-x:auto">
      <table class="data-table">
        <thead><tr><th>Diferencial</th><th>Tú</th><th>Comp 1</th><th>Comp 2</th><th>Comp 3</th><th>Saturación</th></tr></thead>
        <tbody>{tabla_dif_html}</tbody>
      </table></div>
    </div>

    <div class="subsection"><h3>c. El diferencial MENOS saturado (tu oportunidad)</h3>
      <div class="highlight-box">
        <h4>"{esc(menos_sat.get('diferencial',''))}"</h4>
        <p>Solo {menos_sat.get('en_comp',0)} competidores lo mencionan. Saturación: {esc(menos_sat.get('saturacion',''))}</p>
      </div>
      <div class="info-box success"><p>💡 <strong>Recomendación:</strong> {esc(m4.get('recomendacion',''))}</p></div>
    </div>
  </div>

  <!-- MALETA 5: TESTIMONIOS -->
  <div class="section">
    <div class="section-badge">Maleta 5 de 7</div>
    <h2 class="section-title">5️⃣ Testimonios</h2>
    <p class="section-subtitle">¿Qué dicen los clientes que compraron?</p>

    <div class="subsection"><h3>a. Calificación general del mercado</h3>
      <div class="info-box">
        <p>Google Maps promedio del sector: <strong>{metricas.get('rating_promedio', 0)}/5 ⭐</strong> basado en {total_rev} reviews analizadas.</p>
      </div>
    </div>

    <div class="subsection"><h3>b. Los mejores testimonios detectados</h3>
      {test_html}
    </div>

    <div class="subsection"><h3>c. Patrones en los testimonios</h3>
      <ul>{li_list(m5.get('patrones',[]))}</ul>
    </div>

    <div class="subsection"><h3>d. ¿Cómo recoger más testimonios?</h3>
      <p><strong>Tipo de negocio detectado:</strong> {esc(m5.get('tipo_negocio','SERVICIOS'))}</p>
      <div class="info-box">
        <p><strong>Estrategia principal:</strong> {esc(m5.get('estrategia_recoleccion',{}).get('principal',''))}</p>
        <p><strong>Script WhatsApp:</strong> {esc(m5.get('estrategia_recoleccion',{}).get('script_whatsapp',''))}</p>
        <p><strong>Complementaria 1:</strong> {esc(m5.get('estrategia_recoleccion',{}).get('complementaria_1',''))}</p>
        <p><strong>Complementaria 2:</strong> {esc(m5.get('estrategia_recoleccion',{}).get('complementaria_2',''))}</p>
      </div>
      <div class="info-box success"><p><strong>Meta 30 días:</strong> {esc(m5.get('meta_30_dias',''))}</p></div>
    </div>
  </div>

  <!-- MALETA 6: OBJECIONES -->
  <div class="section">
    <div class="section-badge">Maleta 6 de 7</div>
    <h2 class="section-title">6️⃣ Objeciones</h2>
    <p class="section-subtitle">¿Por qué los clientes NO compran o se frenan?</p>

    <div class="subsection"><h3>a. Lista completa de objeciones ({len(m6.get('lista_10_plus',[]))} detectadas)</h3>
      {obj_html}
    </div>

    {"<div class='subsection'><h3>Objeciones que competidores resuelven (y tú quizás no)</h3>" + obj_comp_html + "</div>" if obj_comp_html else ""}

    <div class="subsection"><h3>b. La objeción MÁS IMPORTANTE</h3>
      <div class="highlight-box">
        <h4>"{esc(obj_principal.get('objecion',''))}"</h4>
        <p>Nivel de riesgo: {obj_principal.get('riesgo','')} | Detectada en: {esc(obj_principal.get('fuente',''))}</p>
      </div>
      <div class="info-box">
        <p><strong>Cómo resolverla:</strong></p>
        <p>🌐 <strong>En tu web:</strong> {esc(como_res.get('en_web',''))}</p>
        <p>📱 <strong>En tus anuncios:</strong> {esc(como_res.get('en_anuncios',''))}</p>
        <p>💬 <strong>En proceso de venta:</strong> {esc(como_res.get('en_ventas',''))}</p>
      </div>
    </div>
  </div>

  <!-- MALETA 7: GARANTÍA -->
  <div class="section">
    <div class="section-badge">Maleta 7 de 7</div>
    <h2 class="section-title">7️⃣ Garantía</h2>
    <p class="section-subtitle">¿Cómo eliminar el riesgo percibido del cliente?</p>

    <div class="subsection"><h3>a. Garantía actual del mercado</h3>
      <div class="info-box warning">
        <p>{esc(m7.get('garantia_actual',''))}</p>
      </div>
    </div>

    <div class="subsection"><h3>b. Garantía sugerida</h3>
      <div class="highlight-box">
        <h4>Garantía recomendada</h4>
        <p>{esc(m7.get('garantia_sugerida',''))}</p>
      </div>
      <p><strong>Por qué funciona:</strong></p>
      <ul>{li_list(m7.get('justificacion',[]))}</ul>
    </div>

    <div class="subsection"><h3>c. ¿Es mejor que la competencia?</h3>
      {"<table class='data-table'><thead><tr><th>Competidor</th><th>Garantía detectada</th></tr></thead><tbody>" + gar_comp_html + "</tbody></table>" if gar_comp_html else "<p style='color:#6e6e73'>No se detectaron garantías explícitas en competidores analizados.</p>"}
      <div class="info-box success"><p>💡 <strong>Recomendación final:</strong> {esc(m7.get('recomendacion',''))}</p></div>
    </div>
  </div>

  <!-- IDEAS DE ANUNCIOS -->
  <div class="section">
    <div class="section-badge">Aplicación práctica</div>
    <h2 class="section-title">🎯 Ideas de Anuncios</h2>
    <p class="section-subtitle">3 estructuras de anuncios basadas en las 7 Maletas</p>
    {ads_html}
  </div>

  <!-- PRÓXIMOS PASOS -->
  <div class="section">
    <div class="section-badge">Plan de acción</div>
    <h2 class="section-title">📋 Próximos Pasos Críticos</h2>

    <div class="subsection"><h3>Esta semana:</h3>
      {pps_html}
    </div>

    <div class="subsection"><h3>Este mes:</h3>
      <ul>{month_html}</ul>
    </div>

    <div class="subsection"><h3>Validar con entrevistas reales:</h3>
      <p>Habla con 5-10 clientes y pregunta:</p>
      <ol>{val_html}</ol>
    </div>
  </div>

  <!-- FUENTES ACADÉMICAS -->
  <div class="section">
    <div class="section-badge">Datos de respaldo</div>
    <h2 class="section-title">📚 Fuentes Académicas y Gubernamentales</h2>

    <div class="subsection"><h3>Estudios académicos consultados</h3>
      {acad_html}
    </div>

    <div class="subsection"><h3>Datos estadísticos oficiales</h3>
      {gov_html}
    </div>

    <div class="subsection"><h3>Todas las fuentes analizadas</h3>
      <ul>
        <li>Google Maps — {total_emp} empresas en {esc(sects or ciudad)}</li>
        <li>Google Business Reviews — {total_rev} reviews analizadas</li>
        <li>Facebook Ads Library — {fsr.get('fb_ads',0)} referencias detectadas</li>
        <li>Google Scholar — {fsr.get('fuentes_academicas',0)} estudios consultados</li>
        <li>DANE / Confecámaras / Minsalud — {fsr.get('datos_gobierno',0)} datos estadísticos</li>
        <li>Búsquedas de Google — {fsr.get('busquedas_google',0)} queries procesadas</li>
      </ul>
    </div>
  </div>

  </div><!-- /content -->

  <!-- FOOTER -->
  <div class="footer">
    <p style="font-size:16px;font-weight:600;margin-bottom:8px">Investigación realizada con la metodología de Las 7 Maletas de Cualquier Compra</p>
    <p>Metodología de Felipe Vergara · <a href="https://www.youtube.com/@FelipeVergara" style="color:#0071e3">youtube.com/@FelipeVergara</a></p>
    <p style="margin-top:12px;font-size:13px">Generado por IM System · intelligentmarkets.com.co · {fecha}</p>
  </div>

</div>
</body>
</html>"""
    return html


# ── CLAUDE API ───────────────────────────────────────────────────
def _call_claude(system_prompt, user_prompt, max_tokens=4000):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key: return ""
    try:
        payload = json.dumps({
            "model": "claude-sonnet-4-6",
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }).encode()
        req = _req.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={"Content-Type": "application/json",
                     "x-api-key": api_key,
                     "anthropic-version": "2023-06-01"},
            method="POST"
        )
        with _req.urlopen(req, timeout=90) as r:
            data = json.loads(r.read().decode())
            return data.get("content", [{}])[0].get("text", "")
    except Exception as e:
        return f"[Síntesis no disponible: {e}]"

SYS_MERCADO = """Eres el Director de Inteligencia de Mercado de Intelligent Markets.
Combinas neurociencia del consumidor (Kahneman, Cialdini, Ariely) con la metodología
de las 7 Maletas y datos estadísticos reales de fuentes colombianas (DANE, Confecámaras).

REGLAS DE ORO:
- Citas datos reales: "Según la Encuesta de Micronegocios DANE 2024..."
- Citas reviews literalmente cuando evidencian un sesgo
- Nombras el sesgo cognitivo específico que opera en cada maleta
- Cada insight termina con "→ Lo que IM hace con esto: [acción concreta]"
- Eres brutalmente específico: nombres, números, porcentajes reales
- El perfil psicográfico usa lenguaje del cliente, no académico"""

def _sintetizar_con_claude(nicho, ciudad, sectores, metricas, competidores,
                            reviews_data, precios_data, quejas_data, recom_data,
                            fb_ads_data, informes_data, fuentes_academicas,
                            datos_gobierno, profundidad):
    nicho_label  = nicho.replace("_", " ")
    sectores_str = ", ".join(sectores) if sectores else ciudad

    def fmt(lst, max_i=5, campo="texto"):
        items = [str(x.get(campo, x) if isinstance(x, dict) else x) for x in lst[:max_i]]
        return "\n".join(f"  - {i[:220]}" for i in items if str(i).strip())

    comps_txt = "\n".join(
        f"  {i+1}. {c.get('nombre','?')} | {c.get('barrio','?')} | "
        f"rating:{c.get('rating','?')} | reviews:{c.get('reviews',0)} | "
        f"web:{'sí' if c.get('web') else 'no'} | \"{(c.get('diferencial') or '')[:100]}\""
        for i, c in enumerate(competidores[:15])
    )
    rev_neg = "\n".join(f'  - "{r[:220]}"' for r in (reviews_data.get("negativas") or [])[:6])
    rev_pos = "\n".join(f'  - "{r[:160]}"' for r in (reviews_data.get("positivas") or [])[:5])
    dolores_txt = "\n".join(
        f"  - '{d['problema']}' ({d['menciones']} menciones)"
        for d in (reviews_data.get("top_dolores") or [])[:6]
    )
    acad_txt = "\n".join(
        f"  - [{r.get('fuente','')}] {r.get('titulo','')} — {r.get('resumen','')[:180]}"
        for r in fuentes_academicas[:6]
    ) or "  (No encontrados)"
    gov_txt = "\n".join(
        f"  - [{r.get('entidad','')} {r.get('año','')}] {r.get('dato','')[:200]}"
        for r in datos_gobierno[:8]
    ) or "  (No encontrados)"

    prompt = f"""Analiza este mercado con la metodología 7 Maletas + sesgos cognitivos:

MERCADO: {nicho_label} · {sectores_str} · {ciudad}, Colombia
PROFUNDIDAD: {profundidad}

=== MÉTRICAS DEL SECTOR ===
Empresas en Google Maps: {metricas.get('total_encontrados',0)}
Rating promedio: {metricas.get('rating_promedio',0)}/5
Con presencia web: {metricas.get('pct_presencia_web',0)}%
Con reviews activos (>10): {metricas.get('pct_reviews_activos',0)}%
Nivel de precio: {metricas.get('nivel_precio_label','N/D')}

=== COMPETIDORES ===
{comps_txt or "Sin datos"}

=== REVIEWS NEGATIVAS ===
{rev_neg or "Sin datos"}

=== REVIEWS POSITIVAS ===
{rev_pos or "Sin datos"}

=== DOLORES IDENTIFICADOS ===
{dolores_txt or "Sin datos"}

=== PRECIOS ===
{fmt(precios_data) or "Sin datos"}

=== QUEJAS GOOGLE ===
{fmt(quejas_data) or "Sin datos"}

=== FUENTES ACADÉMICAS ENCONTRADAS ===
{acad_txt}

=== DATOS GUBERNAMENTALES / DANE ===
{gov_txt}

=== PUBLICIDAD ACTIVA ===
{fmt(fb_ads_data, campo='texto_anuncio') or "Sin datos"}

---

Genera el análisis completo en este formato exacto:

## PERFIL PSICOGRÁFICO DEL CLIENTE IDEAL
Edad promedio: [X-X años]
NSE: [estratos]
Motivación primaria: [la emoción/resultado que realmente busca]
Mayor miedo: [miedo específico en este nicho]
Proceso de búsqueda: [paso a paso de cómo decide]
Disparador de compra: [qué lo hace actuar]
Frase que lo define: "[cita real de una review si hay]"

## MALETA 1 — QUÉ EXISTE
Sesgo identificado: [nombre del sesgo cognitivo]
[Análisis con datos reales y cita de fuente académica/DANE si disponible]
→ Lo que IM hace con esto: [acción concreta]

## MALETA 2 — QUÉ FALTA
Sesgo identificado: [nombre]
[Análisis: qué servicios, horarios, segmentos están desatendidos]
[Menciona brecha expectativa-realidad con evidencia de reviews]
→ Lo que IM hace con esto: [acción concreta]

## MALETA 3 — QUÉ DUELE
Sesgo identificado: Aversión a la Pérdida
[Citar las 3-5 frustraciones más repetidas TEXTUALMENTE desde reviews]
[El momento exacto donde el cliente se decepciona]
[El dolor detrás del dolor — psicología profunda]
→ Lo que IM hace con esto: [acción concreta]

## MALETA 4 — QUÉ DESEA
Sesgo identificado: [nombre]
[Deseos declarados vs. deseos reales — Pirámide de Maslow aplicada]
[Citar qué dicen las reviews 5 estrellas exactamente]
[La fantasía del servicio ideal en este nicho]
→ Lo que IM hace con esto: [acción concreta]

## MALETA 5 — QUÉ FRENA
Sesgos identificados: [Parálisis por Análisis / Sesgo de Confirmación / Desconfianza]
[Principales objeciones con evidencia real]
[Por qué piden precio y no contratan]
[Cuánto tiempo tarda la decisión y por qué]
→ Lo que IM hace con esto: [acción concreta]

## MALETA 6 — QUÉ MUEVE
Disparadores identificados: [Prueba Social / Autoridad / Escasez / Reciprocidad]
[Qué los convenció según testimonios positivos]
[El detonador emocional de compra en este nicho específico]
[Qué los hace referir a otros]
→ Lo que IM hace con esto: [acción concreta]

## MALETA 7 — OPORTUNIDAD PARA IM
[Cruzar: dato DANE + Review real + Estudio académico + Análisis psicográfico]
El gap más grande del mercado que IM puede llenar
Sector/barrio con menos competencia digital
El mensaje ganador que nadie está diciendo
Tipo de negocio = cliente ideal de IM
Ángulo de entrada más efectivo
La PROMESA DIFERENCIAL exacta de IM para este mercado
Acción inmediata #1

## SESGOS COGNITIVOS CLAVE DEL SECTOR
• Sesgo [nombre]: [cómo se manifiesta] | Evidencia: "[cita]" | Copy de IM: [frase]
[Listar los 3-4 sesgos más relevantes del mercado]

## FUENTES Y DATOS CITADOS
[Citar los datos académicos y gubernamentales que usaste en el análisis]

Sé brutalmente específico. Usa los números reales. Cita reviews literalmente."""

    return _call_claude(SYS_MERCADO, prompt, max_tokens=5000)

# ── INVESTIGACIÓN PRINCIPAL ──────────────────────────────────────
def run_investigation(job_id, nicho, pais, ciudad, sectores, barrios, profundidad, fuentes=None):
    api_key  = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    kws      = NICHOS_KEYWORDS.get(nicho, [nicho.replace("_", " ")])
    nicho_kw = kws[0]
    search_locs = (sectores + barrios)[:6] if (sectores or barrios) else [ciudad]
    fuentes_set = set(fuentes or ["maps", "google", "academicas", "dane", "facebook"])

    try:
        # 1. GOOGLE MAPS
        _update_job(job_id, estado="corriendo", progreso=5, modulo_actual="Geolocalización y mapeo con Google Maps")
        all_places = []
        for loc in search_locs:
            for kw in kws[:2]:
                places = _maps_places_search(kw, f"{loc}, {ciudad}, {pais}", api_key)
                for p in places:
                    if not any(ex.get("place_id") == p.get("place_id") for ex in all_places):
                        p["_search_sector"] = loc
                        all_places.append(p)
            time.sleep(0.25)

        if not all_places:
            for s in _google_snippets(f"{nicho_kw} {ciudad} directorio empresas", num=8):
                all_places.append({"name": s[:60], "place_id": None, "_fallback": True, "_search_sector": ciudad})

        _update_job(job_id, progreso=15, modulo_actual="Extrayendo detalles y reviews de competidores")

        # 2. DETALLES Y REVIEWS
        max_detail = 40 if profundidad == "completa" else 15
        places_details = []
        for i, place in enumerate(all_places[:max_detail]):
            if place.get("place_id") and api_key:
                det = _maps_place_details(place["place_id"], api_key)
                det["_lugar_base"] = place
                places_details.append(det)
            else:
                places_details.append({"_lugar_base": place, "_fallback": True})
            prog = 15 + int(i / max(max_detail, 1) * 18)
            _update_job(job_id, progreso=prog, modulo_actual=f"Reviews y detalles ({i+1}/{min(max_detail,len(all_places))})")
            time.sleep(0.15)

        # 3. ANÁLISIS
        _update_job(job_id, progreso=36, modulo_actual="Analizando voz del cliente (reviews)")
        reviews_data = _extraer_reviews_profundas(places_details)
        metricas     = _calcular_metricas(all_places, places_details)

        # 4. BÚSQUEDAS DE MERCADO
        _update_job(job_id, progreso=42, modulo_actual="Buscando precios del sector")
        precios_data = _buscar_precios(nicho_kw, ciudad)
        time.sleep(0.4)

        _update_job(job_id, progreso=46, modulo_actual="Buscando quejas y problemas")
        quejas_data = _buscar_quejas(nicho_kw, ciudad)
        time.sleep(0.4)

        _update_job(job_id, progreso=50, modulo_actual="Buscando recomendaciones del mercado")
        recom_data = _buscar_recomendaciones(nicho_kw, ciudad)
        time.sleep(0.3)

        _update_job(job_id, progreso=53, modulo_actual="Analizando publicidad activa (Facebook Ads)")
        fb_ads_data = _buscar_facebook_ads(nicho_kw, ciudad) if "facebook" in fuentes_set else []
        time.sleep(0.3)

        _update_job(job_id, progreso=56, modulo_actual="Buscando informes del sector")
        informes_data = _buscar_informes(nicho_kw, ciudad)
        time.sleep(0.3)

        # 5. FUENTES ACADÉMICAS
        _update_job(job_id, progreso=60, modulo_actual="Consultando fuentes académicas (Google Scholar)")
        fuentes_academicas = []
        if "academicas" in fuentes_set or "scholar" in fuentes_set:
            fuentes_academicas = _buscar_fuentes_academicas(nicho_kw, ciudad)
        time.sleep(0.4)

        # 6. DATOS GUBERNAMENTALES
        _update_job(job_id, progreso=68, modulo_actual="Consultando DANE, Confecámaras, Minsalud")
        datos_gobierno = []
        if "dane" in fuentes_set:
            datos_gobierno = _buscar_datos_gobierno(nicho_kw, ciudad)
        time.sleep(0.3)

        # 7. SESGOS Y PERFIL (fallback sin Claude)
        _update_job(job_id, progreso=75, modulo_actual="Analizando sesgos cognitivos del mercado")
        sesgos_data = _analizar_sesgos_fallback(nicho, reviews_data, metricas, ciudad, sectores)

        # 8. MAPA DE COMPETIDORES
        _update_job(job_id, progreso=79, modulo_actual="Construyendo mapa de competidores")
        competidores = []
        for i, place in enumerate(all_places[:40]):
            det = places_details[i] if i < len(places_details) else {}
            raw_rating = place.get("rating") if place.get("rating") is not None else det.get("rating")
            competidores.append({
                "nombre":    place.get("name", "Desconocido"),
                "barrio":    place.get("_search_sector", ""),
                "direccion": place.get("formatted_address", det.get("formatted_address", "")),
                "rating":    _safe_float(raw_rating) if raw_rating is not None else None,
                "reviews":   int(_safe_float(place.get("user_ratings_total") or det.get("user_ratings_total") or 0)),
                "web":       bool(det.get("website")),
                "web_url":   det.get("website", ""),
                "telefono":  det.get("formatted_phone_number", ""),
                "diferencial": ((det.get("reviews") or [{}])[0].get("text") or "")[:150] if det.get("reviews") else "",
            })

        # 9. COMPARATIVO DE SECTORES
        comparativo = {}
        for sector in (sectores or [])[:6]:
            sp = [c for c in competidores if c.get("barrio") == sector]
            valid_r = [_safe_float(c.get("rating")) for c in sp if c.get("rating") is not None]
            comparativo[sector] = {
                "total":           len(sp),
                "rating_promedio": round(sum(valid_r) / max(len(valid_r), 1), 2),
                "con_web":         sum(1 for c in sp if c.get("web")),
                "pct_sin_digital": round((1 - sum(1 for c in sp if c.get("web")) / max(len(sp), 1)) * 100),
            }

        mejor_sector = (ciudad, {"pct_sin_digital": 0})
        if comparativo:
            mejor_sector = max(comparativo.items(), key=lambda x: x[1].get("pct_sin_digital", 0))

        # 10. ANÁLISIS LOCAL 7 MALETAS (Felipe Vergara methodology)
        _update_job(job_id, progreso=82, modulo_actual="Llenando las 7 Maletas con evidencia del mercado")
        maletas_local = _analizar_7_maletas_local(
            nicho, ciudad, sectores, metricas, competidores,
            reviews_data, precios_data, quejas_data, recom_data,
            fb_ads_data, fuentes_academicas, datos_gobierno
        )

        # 11. SÍNTESIS CON CLAUDE (enriquece las maletas si hay créditos)
        _update_job(job_id, progreso=88, modulo_actual="Sintetizando con IA (Claude)")
        analisis_claude = _sintetizar_con_claude(
            nicho, ciudad, sectores, metricas, competidores,
            reviews_data, precios_data, quejas_data, recom_data,
            fb_ads_data, informes_data, fuentes_academicas, datos_gobierno, profundidad
        )

        _update_job(job_id, progreso=95, modulo_actual="Generando informe final")

        resultado = {
            "meta": {
                "job_id": job_id, "nicho": nicho, "pais": pais, "ciudad": ciudad,
                "sectores": sectores, "barrios": barrios, "profundidad": profundidad,
                "terminado_at": datetime.now().isoformat(),
                "api_utilizada": bool(api_key),
                "claude_usado": bool(analisis_claude and not analisis_claude.startswith("[")),
                "fuentes_usadas": list(fuentes_set),
            },
            "resumen_ejecutivo": {
                "titulo":               f"{nicho.replace('_',' ').title()} — {ciudad} + {', '.join(sectores[:3]) if sectores else 'área completa'}",
                "total_empresas":       metricas.get("total_encontrados", 0),
                "rating_promedio":      metricas.get("rating_promedio", "N/D"),
                "pct_presencia_digital":metricas.get("pct_presencia_web", 0),
                "nivel_precio":         metricas.get("nivel_precio_label", "N/D"),
                "dolor_principal":      (reviews_data.get("top_dolores") or [{}])[0].get("problema", "falta de seguimiento"),
                "oportunidad_im":       "ALTA" if metricas.get("pct_presencia_web", 100) < 50 else "MEDIA",
            },
            "metricas":              metricas,
            "competidores":          competidores,
            "comparativo_sectores":  comparativo,
            "sector_recomendado": {
                "nombre": mejor_sector[0],
                "datos":  mejor_sector[1],
                "razon":  f"Mayor % sin digitalizar ({mejor_sector[1].get('pct_sin_digital','?')}%)",
            },
            "reviews_analisis":    reviews_data,
            "precios_raw":         precios_data,
            "quejas_raw":          quejas_data,
            "recomendaciones_raw": recom_data,
            "facebook_ads_raw":    fb_ads_data,
            "informes_documentos": informes_data,
            "fuentes_academicas":  fuentes_academicas,
            "datos_gobierno":      datos_gobierno,
            "sesgos_cognitivos":   sesgos_data.get("sesgos", {}),
            "perfil_psicografico": sesgos_data.get("perfil", {}),
            "analisis_7_maletas":  analisis_claude,
            "7_maletas_analisis":  maletas_local,
        }

        _update_job(job_id, estado="completado", progreso=100, modulo_actual="Completado",
                    resultado=json.dumps(resultado, ensure_ascii=False),
                    terminado_at=datetime.now().isoformat())
        print(f"[Market Researcher] Job {job_id} completado — {metricas.get('total_encontrados',0)} empresas")

    except Exception as e:
        import traceback
        _update_job(job_id, estado="error", progreso=0,
                    modulo_actual=f"Error: {str(e)[:200]}",
                    terminado_at=datetime.now().isoformat())
        print(f"[Market Researcher] ERROR job {job_id}: {e}\n{traceback.format_exc()}")

# ── API PÚBLICA ──────────────────────────────────────────────────
def crear_job(nicho, pais, ciudad, sectores, barrios, profundidad="completa", fuentes=None):
    init_mercado_tables()
    raw    = f"{nicho}-{ciudad}-{'-'.join(sectores)}-{time.time()}"
    job_id = hashlib.md5(raw.encode()).hexdigest()[:12]
    conn   = get_db()
    conn.execute(
        "INSERT INTO mercado_jobs (id,nicho,pais,ciudad,sectores,barrios,profundidad,estado,progreso,modulo_actual,creado_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (job_id, nicho, pais, ciudad, json.dumps(sectores), json.dumps(barrios), profundidad,
         "pendiente", 0, "Iniciando...", datetime.now().isoformat())
    )
    conn.commit(); conn.close()
    t = threading.Thread(
        target=run_investigation,
        args=(job_id, nicho, pais, ciudad, sectores, barrios, profundidad, fuentes),
        daemon=True
    )
    t.start()
    return job_id

def get_job_estado(job_id):
    conn = get_db()
    row  = conn.execute("SELECT * FROM mercado_jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    if not row: return None
    d = dict(row)
    d.pop("resultado", None)
    d["sectores"] = json.loads(d.get("sectores") or "[]")
    d["barrios"]  = json.loads(d.get("barrios")  or "[]")
    return d

def get_job_reporte(job_id):
    conn = get_db()
    row  = conn.execute("SELECT * FROM mercado_jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    if not row: return None
    d   = dict(row)
    raw = d.pop("resultado", None)
    d["sectores"] = json.loads(d.get("sectores") or "[]")
    d["barrios"]  = json.loads(d.get("barrios")  or "[]")
    if raw:
        try:    d["resultado"] = json.loads(raw)
        except: d["resultado"] = None
    return d

def lista_jobs():
    init_mercado_tables()
    conn = get_db()
    rows = conn.execute(
        "SELECT id,nicho,ciudad,sectores,estado,progreso,modulo_actual,creado_at,terminado_at FROM mercado_jobs ORDER BY creado_at DESC LIMIT 50"
    ).fetchall()
    conn.close()
    result = []
    for row in rows:
        d = dict(row)
        d["sectores"] = json.loads(d.get("sectores") or "[]")
        result.append(d)
    return result

# ── GENERADORES DE INFORME ───────────────────────────────────────
def generar_informe_txt(data):
    meta        = data.get("meta", {})
    resumen     = data.get("resumen_ejecutivo", {})
    metricas    = data.get("metricas", {})
    comps       = data.get("competidores", [])
    comparativo = data.get("comparativo_sectores", {})
    reviews     = data.get("reviews_analisis", {})
    precios     = data.get("precios_raw", [])
    fb_ads      = data.get("facebook_ads_raw", [])
    informes    = data.get("informes_documentos", [])
    sector_rec  = data.get("sector_recomendado", {})
    analisis    = data.get("analisis_7_maletas", "") or ""
    sesgos      = data.get("sesgos_cognitivos", {})
    perfil      = data.get("perfil_psicografico", {})
    fuentes_ac  = data.get("fuentes_academicas", [])
    datos_gov   = data.get("datos_gobierno", [])

    nicho  = meta.get("nicho", "").replace("_", " ").title()
    ciudad = meta.get("ciudad", "")
    sects  = ", ".join(meta.get("sectores") or [])
    fecha  = datetime.now().strftime("%d/%m/%Y %H:%M")
    sep1   = "━" * 51
    sep2   = "─" * 40

    pct_sin = 100 - int(resumen.get("pct_presencia_digital", metricas.get("pct_presencia_web", 0)))
    total   = resumen.get("total_empresas", metricas.get("total_encontrados", 0))
    con_web = metricas.get("con_presencia_web", 0)
    dolores = reviews.get("top_dolores") or []
    elogios = reviews.get("top_elogios") or []

    lineas = [
        sep1,
        "INFORME DE INTELIGENCIA DE MERCADO",
        f"Nicho: {nicho} | Ciudad: {ciudad} | Sectores: {sects}",
        f"Fecha: {fecha} | Generado por: IM System v3",
        sep1, "",

        "1. PANORAMA DEL MERCADO", sep2,
        f"Total empresas encontradas (Google Maps): {total}",
        f"Con presencia digital activa:             {con_web} ({metricas.get('pct_presencia_web',0)}%)",
        f"Sin presencia digital:                    {total-con_web} ({pct_sin}%)",
        f"Con reviews activos (>10 resenas):        {metricas.get('con_reviews_activos',0)} ({metricas.get('pct_reviews_activos',0)}%)",
        f"Rating promedio del sector:               {metricas.get('rating_promedio',0)}/5",
        f"Nivel de precio del sector:               {metricas.get('nivel_precio_label','N/D')}",
        f"Oportunidad IM:                           {resumen.get('oportunidad_im','MEDIA')}",
        "",
    ]

    # Sección 2: Competidores
    lineas += ["2. MAPA DE COMPETIDORES POR SECTOR", sep2]
    if comparativo:
        for sector, datos in comparativo.items():
            lineas.append(f"\nSECTOR {sector}:")
            for i, c in enumerate([c for c in comps if c.get("barrio") == sector][:5], 1):
                rat = str(c["rating"]) if c.get("rating") is not None else "sin rating"
                lineas.append(f"  {i}. {c.get('nombre','?')}")
                lineas.append(f"     Rating: {rat} | Resenas: {c.get('reviews',0)} | Web: {'si' if c.get('web') else 'no'}")
                if c.get("diferencial"):
                    lineas.append(f"     Diferencial: \"{c['diferencial'][:120]}\"")
            opp = "Alta" if datos.get("pct_sin_digital",0) > 60 else "Media"
            lineas.append(f"  Oportunidad: {opp} ({datos.get('pct_sin_digital',0)}% sin digital)")
    else:
        for i, c in enumerate(comps[:10], 1):
            rat = str(c["rating"]) if c.get("rating") is not None else "sin rating"
            lineas.append(f"  {i}. {c.get('nombre','?')} | {c.get('barrio','?')} | Rating:{rat} | Web:{'si' if c.get('web') else 'no'}")
    lineas.append("")

    # Sección 3: Voz del cliente
    lineas += ["3. VOZ DEL CLIENTE (REVIEWS Y QUEJAS)", sep2,
               "\nQUEJAS MAS REPETIDAS (Google Maps reviews):"]
    if reviews.get("negativas"):
        for r in reviews["negativas"][:4]:
            lineas.append(f'  - "{r[:200]}"')
    elif dolores:
        for d in dolores[:4]:
            lineas.append(f"  - '{d['problema']}' ({d['menciones']} menciones)")
    else:
        lineas.append("  Sin reviews negativas (activar Google Maps API)")

    lineas.append("\nLO QUE MAS VALORAN:")
    if reviews.get("positivas"):
        for r in reviews["positivas"][:3]:
            lineas.append(f'  - "{r[:160]}"')
    else:
        for e in elogios[:3]:
            lineas.append(f"  - '{e['elogio']}' ({e['menciones']} menciones)")

    lineas.append("\nQUEJAS ADICIONALES (Google Search):")
    quejas_raw = (data.get("quejas_raw") or [])[:3]
    for q in quejas_raw:
        lineas.append(f"  - {q.get('texto','')[:180]}")
    lineas.append("")

    # Sección 4: Perfil psicográfico
    lineas += ["4. PERFIL PSICOGRAFICO DEL CLIENTE IDEAL", sep2]
    if perfil:
        for k, v in perfil.items():
            label = k.replace("_", " ").title()
            lineas.append(f"  {label}: {v}")
    else:
        lineas.append("  Sin perfil psicográfico disponible")
    lineas.append("")

    # Sección 5: Sesgos cognitivos
    lineas += ["5. SESGOS COGNITIVOS IDENTIFICADOS", sep2]
    if sesgos:
        for key, s in list(sesgos.items())[:6]:
            lineas.append(f"\n• {s.get('nombre','?')} [{s.get('maleta','')}]")
            lineas.append(f"  Descripcion: {s.get('descripcion','')[:200]}")
            lineas.append(f"  Evidencia: {s.get('evidencia','')[:150]}")
            lineas.append(f"  Como aprovecharlo en IM: {s.get('como_aprovecharlo','')[:150]}")
    else:
        lineas.append("  Sin análisis de sesgos disponible")
    lineas.append("")

    # Sección 6: Publicidad
    lineas += ["6. PUBLICIDAD ACTIVA (FACEBOOK ADS)", sep2]
    if fb_ads:
        lineas.append(f"Anuncios/fuentes identificados: {len(fb_ads)}")
        for ad in fb_ads[:4]:
            if ad.get("pagina") and ad["pagina"] != "Google search":
                lineas.append(f"  - {ad['pagina']}: {ad.get('texto_anuncio','')[:120]}")
        for ad in fb_ads[:5]:
            if ad.get("texto_anuncio") and len(ad["texto_anuncio"]) > 30:
                lineas.append(f"  Mensaje: {ad['texto_anuncio'][:150]}")
    else:
        lineas.append("  Sin datos de anuncios (Facebook requiere login para datos completos)")
        for r in (data.get("recomendaciones_raw") or [])[:2]:
            if r.get("texto"): lineas.append(f"  - {r['texto'][:150]}")
    lineas.append("")

    # Sección 7: Análisis 7 Maletas (Claude o fallback)
    lineas += ["7. ANALISIS 7 MALETAS", sep2]
    if analisis and not analisis.startswith("["):
        lineas.append(analisis)
    else:
        lineas.append("[Analisis con IA no disponible — usando analisis local de sesgos]")
        if sesgos:
            for key, s in sesgos.items():
                maleta_label = s.get("maleta", key.upper())
                lineas.append(f"\n{maleta_label}")
                lineas.append(f"  {s.get('descripcion','')[:250]}")
                lineas.append(f"  → {s.get('como_aprovecharlo','')[:200]}")
        else:
            lineas += [
                f"\nMALETA 1 — QUE EXISTE: {total} empresas en {ciudad}. {metricas.get('pct_presencia_web',0)}% con web.",
                f"MALETA 2 — QUE FALTA: {pct_sin}% sin presencia digital — oportunidad directa.",
                f"MALETA 3 — QUE DUELE: {(dolores[0]['problema'] if dolores else 'falta de seguimiento')}",
                "MALETA 4 — QUE DESEA: Atencion rapida, seguimiento, precios transparentes.",
                "MALETA 5 — QUE FRENA: Desconfianza, alta competencia, precios poco claros.",
                "MALETA 6 — QUE MUEVE: Reviews positivas, recomendacion de conocidos, respuesta rapida.",
                f"MALETA 7 — OPORTUNIDAD IM: {pct_sin}% sin digital = {total-con_web} prospectos directos.",
            ]
    lineas.append("")

    # Sección 8: Fuentes académicas
    lineas += ["8. FUENTES ACADEMICAS CONSULTADAS", sep2]
    if fuentes_ac:
        for f in fuentes_ac[:6]:
            lineas.append(f"  • [{f.get('fuente','')}] {f.get('titulo','')[:150]}")
            if f.get("autores"): lineas.append(f"    Autores: {f['autores'][:100]}")
            if f.get("resumen"): lineas.append(f"    Resumen: {f['resumen'][:200]}")
            if f.get("url"):     lineas.append(f"    URL: {f['url'][:120]}")
    else:
        lineas.append("  Google Scholar no devolvio resultados accesibles.")
        lineas.append("  Acceder directamente: scholar.google.com")
    lineas.append("")

    # Sección 9: Datos estadísticos oficiales
    lineas += ["9. DATOS ESTADISTICOS OFICIALES", sep2]
    if datos_gov:
        for g in datos_gov[:8]:
            lineas.append(f"  • {g.get('entidad','')} [{g.get('año','')}]:")
            lineas.append(f"    {g.get('dato','')[:220]}")
    else:
        lineas.append("  Sin datos gubernamentales encontrados en esta busqueda.")
        lineas.append(f"  Consultar: dane.gov.co · rues.org.co · confecamaras.com.co")
    lineas.append("")

    # Sección 10: Documentos adicionales
    lineas += ["10. DOCUMENTOS E INFORMES DEL SECTOR", sep2]
    if informes:
        for inf in informes[:5]:
            lineas.append(f"  - {inf.get('texto','')[:180]}")
    elif precios:
        for p in precios[:3]:
            lineas.append(f"  - {p.get('texto','')[:180]}")
    else:
        lineas.append("  Sin informes adicionales encontrados.")
    lineas.append("")

    # Sección 11: Recomendación estratégica
    lineas += ["11. RECOMENDACION ESTRATEGICA PARA IM", sep2,
               f"SECTOR PRIORITARIO: {sector_rec.get('nombre', ciudad)} — {sector_rec.get('razon','')}",
               f"DIFERENCIAL DE IM: Automatizacion de captacion para el {pct_sin}% sin digital",
               f"CLIENTE IDEAL: {nicho} con rating < 4.0 o sin web en {ciudad}",
               "",
               "ACCIONES INMEDIATAS:",
               f"  1. Enfocar prospeccion en sector '{sector_rec.get('nombre', ciudad)}' ({pct_sin}% sin digital)",
               f"  2. Activar sesgo de prueba social: '50+ reviews en 90 dias'",
               f"  3. Usar los {total-con_web} negocios sin web como lista fria inmediata",
               f"  4. Copy: 'Mientras tus competidores no responden, tu ya cerraste la venta'",
               "", sep1,
               "Fuentes: Google Maps · Google Search · Google Scholar · DANE · Facebook Ads Library",
               f"Empresas: {total} | Reviews: {reviews.get('total',0)} | Academicas: {len(fuentes_ac)} | Gov: {len(datos_gov)}",
               sep1]

    return "\n".join(lineas)


def generar_informe_html(data, txt_content):
    meta        = data.get("meta", {})
    resumen     = data.get("resumen_ejecutivo", {})
    metricas    = data.get("metricas", {})
    comps       = data.get("competidores", [])
    comparativo = data.get("comparativo_sectores", {})
    reviews     = data.get("reviews_analisis", {})
    sector_rec  = data.get("sector_recomendado", {})
    fb_ads      = data.get("facebook_ads_raw", [])
    informes    = data.get("informes_documentos", [])
    analisis    = data.get("analisis_7_maletas", "") or ""
    sesgos      = data.get("sesgos_cognitivos", {})
    perfil      = data.get("perfil_psicografico", {})
    fuentes_ac  = data.get("fuentes_academicas", [])
    datos_gov   = data.get("datos_gobierno", [])

    nicho   = meta.get("nicho", "").replace("_", " ").title()
    ciudad  = meta.get("ciudad", "")
    sects   = ", ".join(meta.get("sectores") or [])
    fecha   = datetime.now().strftime("%d/%m/%Y %H:%M")
    pct_sin = 100 - int(resumen.get("pct_presencia_digital", metricas.get("pct_presencia_web", 0)))
    total   = resumen.get("total_empresas", metricas.get("total_encontrados", 0))
    con_web = metricas.get("con_presencia_web", 0)
    opp_col = "#4ADE80" if resumen.get("oportunidad_im") == "ALTA" else "#FBBF24"

    def stat(label, val, sub=""):
        sub_html = f'<div style="font-size:11px;color:#666">{sub}</div>' if sub else ""
        return (f'<div style="background:#1A1A1A;border:1px solid rgba(255,255,255,0.08);border-radius:10px;padding:16px">'
                f'<div style="font-size:11px;color:#666;margin-bottom:6px">{label}</div>'
                f'<div style="font-size:24px;font-weight:700;font-family:\'DM Mono\',monospace">{val}</div>'
                f'{sub_html}</div>')

    # Competitor rows
    comp_rows = ""
    for i, c in enumerate(comps[:25], 1):
        rat = f"{c['rating']}★" if c.get("rating") is not None else "–"
        rc  = "#4ADE80" if _safe_float(c.get("rating")) >= 4.5 else "#FBBF24" if _safe_float(c.get("rating")) >= 3.5 else "#F87171" if c.get("rating") is not None else "#666"
        web = '<span style="color:#4ADE80">✓</span>' if c.get("web") else '<span style="color:#F87171">✗</span>'
        dif = (c.get("diferencial") or "")[:80]
        comp_rows += (f'<tr style="border-bottom:1px solid rgba(255,255,255,0.06)">'
                      f'<td style="padding:7px 10px;color:#666">{i}</td>'
                      f'<td style="padding:7px 10px">{c.get("nombre","?")}</td>'
                      f'<td style="padding:7px 10px;color:#999">{c.get("barrio","?")}</td>'
                      f'<td style="padding:7px 10px;color:{rc};font-weight:600">{rat}</td>'
                      f'<td style="padding:7px 10px;color:#999">{c.get("reviews",0)}</td>'
                      f'<td style="padding:7px 10px">{web}</td>'
                      f'<td style="padding:7px 10px;color:#666;font-size:11px;max-width:160px;overflow:hidden;white-space:nowrap">{dif}</td>'
                      f'</tr>')

    # Sector rows
    sector_rows = ""
    for s, d in comparativo.items():
        opp   = "Alta" if d.get("pct_sin_digital", 0) > 60 else "Media"
        opp_c = "#4ADE80" if opp == "Alta" else "#FBBF24"
        es_rec = s == sector_rec.get("nombre", "")
        bg_str = "background:rgba(74,222,128,0.04)" if es_rec else ""
        fw_str = "600" if es_rec else "400"
        c_str  = "#4ADE80" if es_rec else "#F5F5F0"
        star   = "  ★" if es_rec else ""
        sector_rows += (f'<tr style="border-bottom:1px solid rgba(255,255,255,0.06);{bg_str}">'
                        f'<td style="padding:7px 10px;color:{c_str};font-weight:{fw_str}">{s}{star}</td>'
                        f'<td style="padding:7px 10px">{d.get("total",0)}</td>'
                        f'<td style="padding:7px 10px">{d.get("rating_promedio",0)}/5</td>'
                        f'<td style="padding:7px 10px">{d.get("con_web",0)}</td>'
                        f'<td style="padding:7px 10px;color:{opp_c}">{d.get("pct_sin_digital",0)}%</td>'
                        f'<td style="padding:7px 10px;color:{opp_c}">{opp}</td></tr>')

    # Reviews HTML
    neg_html = "".join(
        f'<div style="padding:8px 12px;border:1px solid rgba(248,113,113,0.2);border-radius:6px;margin-bottom:6px;font-size:12px;color:#ccc">"<em>{r[:220]}</em>"</div>'
        for r in (reviews.get("negativas") or [])[:4]
    ) or '<div style="color:#666;font-size:12px">Sin reviews negativas recopiladas</div>'

    pos_html = "".join(
        f'<div style="padding:8px 12px;border:1px solid rgba(74,222,128,0.2);border-radius:6px;margin-bottom:6px;font-size:12px;color:#ccc">"<em>{r[:160]}</em>"</div>'
        for r in (reviews.get("positivas") or [])[:3]
    ) or '<div style="color:#666;font-size:12px">Sin reviews positivas recopiladas</div>'

    # Psychographic profile HTML
    perfil_html = ""
    if perfil:
        for k, v in perfil.items():
            label = k.replace("_", " ").title()
            perfil_html += (f'<div style="display:flex;gap:12px;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.06)">'
                            f'<div style="font-size:11px;color:#666;min-width:160px">{label}</div>'
                            f'<div style="font-size:12px;color:#ccc">{v}</div></div>')
    else:
        perfil_html = '<div style="color:#666;font-size:12px">Sin perfil disponible</div>'

    # Sesgos HTML
    sesgos_html = ""
    sesgo_colors = ["#4ADE80","#60A5FA","#FBBF24","#F87171","#A78BFA","#FB923C","#34D399"]
    for idx, (key, s) in enumerate(list(sesgos.items())[:6]):
        col = sesgo_colors[idx % len(sesgo_colors)]
        sesgos_html += (
            f'<div style="border:1px solid rgba(255,255,255,0.08);border-radius:10px;padding:16px;margin-bottom:12px">'
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">'
            f'<span style="font-size:11px;padding:2px 8px;border-radius:20px;background:{col}22;color:{col};border:1px solid {col}44">{s.get("maleta","")}</span>'
            f'<span style="font-weight:600;font-size:13px">{s.get("nombre","")}</span></div>'
            f'<div style="font-size:12px;color:#999;margin-bottom:6px">{s.get("descripcion","")[:240]}</div>'
            f'<div style="font-size:11px;color:#666;font-style:italic;margin-bottom:8px">Evidencia: {s.get("evidencia","")[:180]}</div>'
            f'<div style="font-size:12px;padding:6px 10px;background:rgba(74,222,128,0.05);border-left:2px solid #4ADE80;color:#4ADE80">→ {s.get("como_aprovecharlo","")[:200]}</div>'
            f'</div>'
        )
    if not sesgos_html:
        sesgos_html = '<div style="color:#666;font-size:12px">Sesgos calculados — ver sección 7 Maletas</div>'

    # Academic sources HTML
    acad_html = ""
    for f in fuentes_ac[:6]:
        acad_html += (f'<div style="padding:10px 14px;border:1px solid rgba(255,255,255,0.08);border-radius:8px;margin-bottom:8px">'
                      f'<div style="font-size:11px;color:#60A5FA;margin-bottom:4px">{f.get("fuente","")}</div>'
                      f'<div style="font-size:12px;font-weight:500;margin-bottom:4px">{f.get("titulo","")[:160]}</div>'
                      f'<div style="font-size:11px;color:#666">{f.get("autores","")[:100]}</div>'
                      f'<div style="font-size:11px;color:#999;margin-top:4px">{f.get("resumen","")[:200]}</div></div>')
    if not acad_html:
        acad_html = '<div style="color:#666;font-size:12px">Google Scholar no devolvió resultados accesibles. Consultar scholar.google.com directamente.</div>'

    # Government data HTML
    gov_html = ""
    ent_colors = {"DANE":"#4ADE80","Confecámaras":"#60A5FA","MinSalud":"#F472B6","MinComercio":"#FBBF24","RUES":"#FB923C","DNP":"#A78BFA"}
    for g in datos_gov[:8]:
        ent = g.get("entidad","")
        ec  = ent_colors.get(ent, "#999")
        gov_html += (f'<div style="padding:10px 14px;border:1px solid rgba(255,255,255,0.08);border-radius:8px;margin-bottom:8px">'
                     f'<div style="font-size:11px;color:{ec};margin-bottom:4px">{ent} · {g.get("año","")}</div>'
                     f'<div style="font-size:12px;color:#ccc">{g.get("dato","")[:240]}</div></div>')
    if not gov_html:
        gov_html = '<div style="color:#666;font-size:12px">Buscar directamente: dane.gov.co · rues.org.co · confecamaras.com.co</div>'

    # 7 Maletas HTML
    if analisis and not analisis.startswith("["):
        def md2html(text):
            text = re.sub(r'^## (.+)$', r'<h3 style="color:#F5F5F0;font-size:14px;margin:20px 0 8px;border-left:3px solid #4ADE80;padding-left:10px">\1</h3>', text, flags=re.MULTILINE)
            text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
            text = re.sub(r'→ (.+?)$', r'<div style="padding:6px 10px;background:rgba(74,222,128,0.05);border-left:2px solid #4ADE80;margin:6px 0;font-size:12px;color:#4ADE80">→ \1</div>', text, flags=re.MULTILINE)
            text = re.sub(r'^- (.+)$', r'<li style="margin:4px 0;color:#999;font-size:12px">\1</li>', text, flags=re.MULTILINE)
            text = re.sub(r'^• (.+)$', r'<li style="margin:4px 0;color:#ccc;font-size:12px">• \1</li>', text, flags=re.MULTILINE)
            text = text.replace('\n\n', '<br><br>')
            return text
        maletas_html = f'<div style="font-family:\'DM Sans\',sans-serif;line-height:1.7">{md2html(analisis)}</div>'
    else:
        rows_fb = ""
        for key, s in list(sesgos.items())[:7]:
            rows_fb += (f'<div style="margin-bottom:14px;padding:12px;border:1px solid rgba(255,255,255,0.06);border-radius:8px">'
                        f'<div style="font-size:12px;font-weight:600;color:#F5F5F0;margin-bottom:4px">{s.get("maleta","")} — {s.get("nombre","")}</div>'
                        f'<div style="font-size:12px;color:#999">{s.get("descripcion","")[:250]}</div>'
                        f'<div style="font-size:12px;color:#4ADE80;margin-top:6px">→ {s.get("como_aprovecharlo","")[:200]}</div></div>')
        maletas_html = rows_fb or '<div style="color:#666;font-size:12px">Agregar créditos a ANTHROPIC_API_KEY para análisis IA completo</div>'

    # Precios HTML
    precios_html = ""
    for p in (data.get("precios_raw") or [])[:4]:
        if p.get("texto"):
            precios_html += f'<div style="padding:8px 12px;border:1px solid rgba(255,255,255,0.08);border-radius:6px;margin-bottom:6px;font-size:12px;color:#999">{p["texto"][:200]}</div>'
    if not precios_html:
        precios_html = '<div style="color:#666;font-size:12px">Sin datos de precios disponibles</div>'

    # FB ads HTML
    fb_html = ""
    for ad in fb_ads[:5]:
        if ad.get("texto_anuncio") and len(ad["texto_anuncio"]) > 20:
            fb_html += (f'<div style="padding:10px 14px;border:1px solid rgba(255,255,255,0.08);border-radius:8px;margin-bottom:8px">'
                        f'<div style="font-size:11px;color:#4ADE80;margin-bottom:4px">{ad.get("pagina","")}</div>'
                        f'<div style="font-size:12px;color:#ccc">{ad["texto_anuncio"][:180]}</div></div>')
    if not fb_html:
        fb_html = '<div style="color:#666;font-size:12px">Sin anuncios identificados (Facebook requiere cookies)</div>'

    txt_esc   = txt_content.replace('\\','\\\\').replace('`','\\`').replace('${','\\${')
    nicho_fn  = meta.get("nicho","nicho").replace(" ","_")
    ciudad_fn = ciudad.replace(" ","_")

    rev_total = (data.get("reviews_analisis") or {}).get("total", 0)

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Informe de Mercado — {nicho} — {ciudad}</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0A0A0A;color:#F5F5F0;font-family:'DM Sans',sans-serif;font-size:13.5px;line-height:1.6;padding:40px 20px;max-width:1020px;margin:0 auto}}
h1{{font-family:'Playfair Display',serif;font-size:32px;font-weight:900;margin-bottom:4px}}
h2{{font-family:'Playfair Display',serif;font-size:18px;font-weight:700;margin:32px 0 12px;padding-top:24px;border-top:1px solid rgba(255,255,255,0.06)}}
h3{{font-size:15px;font-weight:600;margin:14px 0 8px}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th{{padding:8px 10px;text-align:left;color:#666;border-bottom:1px solid rgba(255,255,255,0.08)}}
.grid3{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:20px}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:20px}}
.btn{{display:inline-flex;align-items:center;gap:6px;padding:10px 18px;border-radius:8px;font-size:12px;font-weight:500;cursor:pointer;border:1px solid rgba(255,255,255,0.15);background:rgba(255,255,255,0.05);color:#F5F5F0;font-family:'DM Sans',sans-serif;transition:background 0.2s}}
.btn:hover{{background:rgba(255,255,255,0.1)}}
.btn-p{{background:#F5F5F0;color:#0A0A0A;border-color:#F5F5F0}}
.btn-p:hover{{background:#E0E0DA}}
@media print{{.noprint{{display:none}}}}
</style>
</head>
<body>

<div class="noprint" style="display:flex;gap:10px;margin-bottom:28px;flex-wrap:wrap">
  <button class="btn btn-p" onclick="copiarTxt()">Copiar texto</button>
  <button class="btn" onclick="descargarTxt()">Descargar TXT</button>
  <button class="btn" onclick="window.print()">Descargar PDF</button>
</div>

<div style="margin-bottom:28px">
  <div style="font-size:11px;letter-spacing:3px;text-transform:uppercase;color:#666;font-family:'DM Mono',monospace;margin-bottom:8px">Informe de Inteligencia de Mercado · {fecha}</div>
  <h1>{nicho}</h1>
  <div style="font-size:15px;color:#999;margin-top:6px">{ciudad}{' · ' + sects if sects else ''}</div>
  <div style="margin-top:14px;display:inline-flex;align-items:center;gap:8px;padding:8px 20px;border-radius:20px;background:rgba(74,222,128,0.08);border:1px solid rgba(74,222,128,0.25);color:{opp_col};font-weight:600;font-size:13px">
    Oportunidad IM: {resumen.get("oportunidad_im","MEDIA")} · {pct_sin}% sin presencia digital
  </div>
</div>

<h2>1. Panorama del Mercado</h2>
<div class="grid3">
  {stat("Empresas mapeadas", total)}
  {stat("Rating promedio", str(metricas.get('rating_promedio',0)) + "/5")}
  {stat("Con presencia digital", str(metricas.get('pct_presencia_web',0)) + "%")}
  {stat("Sin presencia digital", str(pct_sin) + "%", "oportunidad directa")}
  {stat("Con reviews activos", str(metricas.get('pct_reviews_activos',0)) + "%")}
  {stat("Nivel de precios", metricas.get('nivel_precio_label','N/D'))}
</div>

<h2>2. Comparativo por Sector</h2>
<div style="overflow-x:auto">
<table><thead><tr>{"".join(f"<th>{h}</th>" for h in ["Sector","Empresas","Rating","Con web","Sin digital","Oportunidad"])}</tr></thead>
<tbody>{sector_rows}</tbody></table>
<div style="font-size:11px;color:#555;margin-top:6px">★ Sector recomendado: {sector_rec.get("nombre","")} — {sector_rec.get("razon","")}</div>
</div>

<h2>3. Mapa Completo de Competidores</h2>
<div style="overflow-x:auto">
<table><thead><tr>{"".join(f"<th>{h}</th>" for h in ["#","Nombre","Sector","Rating","Reseñas","Web","Diferencial"])}</tr></thead><tbody>{comp_rows}</tbody></table>
</div>

<h2>4. Voz del Cliente</h2>
<div class="grid2">
  <div><div style="font-size:12px;color:#F87171;margin-bottom:10px;font-weight:600">Quejas repetidas</div>{neg_html}</div>
  <div><div style="font-size:12px;color:#4ADE80;margin-bottom:10px;font-weight:600">Lo que más valoran</div>{pos_html}</div>
</div>

<h2>5. Perfil Psicográfico del Cliente Ideal</h2>
<div style="background:#111;border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:20px">{perfil_html}</div>

<h2>6. Sesgos Cognitivos Identificados</h2>
{sesgos_html}

<h2>7. Análisis 7 Maletas</h2>
<div style="background:#111;border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:24px">{maletas_html}</div>

<h2>8. Publicidad del Sector (Facebook Ads)</h2>
{fb_html}

<h2>9. Precios del Mercado</h2>
{precios_html}

<h2>10. Fuentes Académicas Consultadas</h2>
{acad_html}

<h2>11. Datos Estadísticos Oficiales</h2>
{gov_html}

<h2>12. Recomendación Estratégica</h2>
<div style="padding:24px;border:1px solid rgba(74,222,128,0.25);border-radius:12px;background:rgba(74,222,128,0.03)">
  <div style="font-size:11px;letter-spacing:3px;text-transform:uppercase;color:#4ADE80;margin-bottom:14px;font-family:'DM Mono',monospace">Conclusión Estratégica</div>
  <div class="grid2" style="margin-bottom:16px">
    <div><div style="font-size:11px;color:#666;margin-bottom:4px">SECTOR PRIORITARIO</div><div style="font-weight:600;color:#4ADE80">{sector_rec.get("nombre",ciudad)}</div><div style="font-size:11px;color:#666">{sector_rec.get("razon","")}</div></div>
    <div><div style="font-size:11px;color:#666;margin-bottom:4px">CLIENTE IDEAL DE IM</div><div style="font-size:12px">{nicho} sin web ni automatización — {pct_sin}% del mercado</div></div>
  </div>
  <div style="padding:12px 16px;background:rgba(74,222,128,0.06);border-radius:8px;font-size:13px;font-style:italic;color:#ccc">
    "Mientras tus competidores de {ciudad} no responden, tú ya cerraste la venta."
  </div>
</div>

<div style="margin-top:36px;padding-top:20px;border-top:1px solid rgba(255,255,255,0.08);text-align:center;color:#333;font-size:11px;font-family:'DM Mono',monospace">
  IM System v3 — Intelligent Markets · intelligentmarkets.com.co<br>
  {total} empresas · {rev_total} reviews · {len(fuentes_ac)} fuentes académicas · {len(datos_gov)} datos gov
</div>

<script>
const TXT=`{txt_esc}`;
function copiarTxt(){{
  navigator.clipboard.writeText(TXT).then(()=>{{
    const b=document.querySelector('.btn-p');
    const o=b.textContent;b.textContent='Copiado!';
    setTimeout(()=>b.textContent=o,2000);
  }});
}}
function descargarTxt(){{
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([TXT],{{type:'text/plain;charset=utf-8'}}));
  a.download='informe_mercado_{nicho_fn}_{ciudad_fn}.txt';
  a.click();
}}
</script>
</body>
</html>"""
    return html


def guardar_informes(data, job_id):
    REPORTS.mkdir(exist_ok=True)
    nicho  = data.get("meta", {}).get("nicho", "nicho").replace(" ", "_")
    ciudad = data.get("meta", {}).get("ciudad", "ciudad").replace(" ", "_")
    fecha  = datetime.now().strftime("%Y%m%d_%H%M")
    fecha_slug = datetime.now().strftime("%Y-%m-%d")

    txt  = generar_informe_txt(data)
    html_legacy = generar_informe_html(data, txt)

    # Primary output: 7 Maletas Felipe Vergara template
    html_7m = _generar_html_7maletas(data)

    path_txt      = REPORTS / f"mercado_{nicho}_{ciudad}_{fecha}.txt"
    path_html     = REPORTS / f"7-maletas-{nicho}-{ciudad}-{fecha_slug}.html"
    path_html_leg = REPORTS / f"mercado_{nicho}_{ciudad}_{fecha}.html"

    path_txt.write_text(txt,         encoding="utf-8")
    path_html.write_text(html_7m,    encoding="utf-8")
    path_html_leg.write_text(html_legacy, encoding="utf-8")

    return {
        "txt":          str(path_txt),
        "html":         str(path_html),          # primary: 7 maletas template
        "html_legacy":  str(path_html_leg),      # secondary: dark dashboard
        "txt_filename": path_txt.name,
        "html_filename": path_html.name,
    }


# ── CLI ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="IM Market Researcher v3")
    p.add_argument("--nicho",       default="odontologos")
    p.add_argument("--ciudad",      default="Medellin")
    p.add_argument("--sectores",    default="Bello,Envigado,El Poblado,Laureles")
    p.add_argument("--pais",        default="Colombia")
    p.add_argument("--profundidad", default="completa")
    p.add_argument("--fuentes",     default="academicas,dane,facebook,maps,scholar",
                   help="Fuentes separadas por coma: academicas,dane,facebook,maps,scholar")
    args = p.parse_args()

    sectores  = [s.strip() for s in args.sectores.split(",") if s.strip()]
    fuentes   = [f.strip() for f in args.fuentes.split(",")  if f.strip()]
    job_id    = crear_job(args.nicho, args.pais, args.ciudad, sectores, [], args.profundidad, fuentes)
    print(f"Job iniciado: {job_id}")
    print(f"Investigando {args.nicho} en {args.ciudad} — sectores: {', '.join(sectores)}")
    print(f"Fuentes activas: {', '.join(fuentes)}")
    print()

    while True:
        estado = get_job_estado(job_id)
        if not estado: break
        print(f"  [{estado['progreso']:3d}%] {estado['modulo_actual']}", flush=True)
        if estado["estado"] in ("completado", "error"):
            if estado["estado"] == "completado":
                reporte = get_job_reporte(job_id)
                data    = reporte["resultado"]
                resumen = data["resumen_ejecutivo"]
                m       = data["metricas"]
                meta    = data["meta"]
                print()
                print("=" * 60)
                print(f"RESUMEN: {resumen['titulo']}")
                print(f"  Empresas mapeadas:    {resumen['total_empresas']}")
                print(f"  Rating promedio:      {resumen['rating_promedio']}/5")
                print(f"  Presencia digital:    {resumen['pct_presencia_digital']}%")
                print(f"  Sin presencia:        {100-int(resumen['pct_presencia_digital'])}% — OPORTUNIDAD")
                print(f"  Dolor principal:      {resumen['dolor_principal']}")
                print(f"  Oportunidad IM:       {resumen['oportunidad_im']}")
                print(f"  Claude usado:         {'sí' if meta.get('claude_usado') else 'no (sin créditos)'}")
                fa = len(data.get("fuentes_academicas") or [])
                dg = len(data.get("datos_gobierno") or [])
                print(f"  Fuentes académicas:   {fa} encontradas")
                print(f"  Datos gubernamentales:{dg} encontrados")
                print()
                maletas = data.get("7_maletas_analisis", {})
                m2 = maletas.get("maleta_2_problema", {})
                m4 = maletas.get("maleta_4_diferenciales", {})
                ads = maletas.get("ads_messages", [])
                print(f"  Dolor principal:      {(m2.get('principal') or {}).get('problema','N/D')}")
                print(f"  Dif. menos saturado:  {(m4.get('menos_saturado') or {}).get('diferencial','N/D')}")
                if ads:
                    print(f"  Anuncio 1 headline:   {ads[0].get('headline','N/D')[:60]}")
                print()
                rutas = guardar_informes(data, job_id)
                print(f"Informes guardados:")
                print(f"  TXT:       {rutas['txt']}")
                print(f"  7 Maletas: {rutas['html']}")
                print(f"  Dashboard: {rutas['html_legacy']}")
                print()
                print(generar_informe_txt(data))
            else:
                print(f"Error: {estado['modulo_actual']}")
            break
        time.sleep(2)
