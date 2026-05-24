#!/usr/bin/env python3
"""
IM Deep Researcher — Investigación profunda de UN negocio específico.
Metodología: 7 Maletas de Felipe Vergara.
Diferencia vs market_researcher.py: este analiza un negocio CLIENTE real
(con su URL, Instagram, nombre exacto) más sus competidores directos.
"""
import os, sys, json, time, sqlite3, hashlib, re, threading
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus, urlencode
import urllib.request as _req
import datetime as _dt

# ── FECHAS DINÁMICAS ──────────────────────────────────────────
_HOY = _dt.datetime.now()
AÑO_ACTUAL   = _HOY.year
AÑO_ANTERIOR = AÑO_ACTUAL - 1
AÑO_SIGUIENTE = AÑO_ACTUAL + 1
FECHA_HOY    = _HOY.strftime('%d de %B de %Y')
RANGO_AÑOS   = f"{AÑO_ANTERIOR} {AÑO_ACTUAL} {AÑO_SIGUIENTE}"

if hasattr(sys.stdout, 'reconfigure'):
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass

BASE    = Path(__file__).parent.parent
DB      = BASE / "logs" / "platform.db"
REPORTS = BASE / "reports"
UPLOADS = BASE / "uploads"

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

UPLOADS.mkdir(exist_ok=True)
REPORTS.mkdir(exist_ok=True)

# ── NICHOS (mirror from market_researcher) ───────────────────
NICHOS_KEYWORDS = {
    "odontologos":               ["odontólogo", "clínica dental", "dentista"],
    "dermatologo":               ["dermatólogo", "clínica de piel", "medicina estética"],
    "agencia_viajes":            ["agencia de viajes", "tours", "turismo"],
    "seguros":                   ["aseguradora", "seguros"],
    "autos_alta_gama":           ["concesionario", "carros de lujo"],
    "restaurantes":              ["restaurante", "café", "gastrobar"],
    "gimnasios":                 ["gimnasio", "CrossFit", "yoga", "fitness"],
    "clinicas_veterinarias":     ["veterinaria", "clínica veterinaria"],
    "contadores":                ["contador", "firma contable"],
    "abogados":                  ["abogado", "firma de abogados"],
    "inmobiliarias":             ["inmobiliaria", "finca raíz"],
    "clinicas_medicina_estetica":["medicina estética", "clínica de belleza", "botox"],
    "psicologos":                ["psicólogo", "salud mental", "terapia"],
    "centros_bienestar":         ["spa", "centro de bienestar", "masajes"],
}

# ── DB ────────────────────────────────────────────────────────
def get_db():
    DB.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    return conn

def init_investigacion_tables():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS investigacion_jobs (
            id TEXT PRIMARY KEY,
            nombre TEXT, url TEXT, instagram TEXT,
            ciudad TEXT, nicho TEXT, tamanio TEXT,
            estado TEXT DEFAULT 'pendiente',
            progreso INTEGER DEFAULT 0,
            modulo_actual TEXT DEFAULT '',
            modulos_detalle TEXT DEFAULT '{}',
            resultado TEXT,
            creado_at TEXT, terminado_at TEXT
        );
        CREATE TABLE IF NOT EXISTS proyectos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT, nicho TEXT, ciudad TEXT,
            url TEXT, instagram TEXT, tamanio TEXT,
            ultimo_job_id TEXT,
            branding_path TEXT,
            notas TEXT,
            creado_at TEXT
        );
    """)
    conn.commit(); conn.close()

def _update_job(job_id, **kwargs):
    conn = get_db()
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [job_id]
    conn.execute(f"UPDATE investigacion_jobs SET {sets} WHERE id=?", vals)
    conn.commit(); conn.close()

def _update_modulo(job_id, modulo, pct):
    conn = get_db()
    row = conn.execute("SELECT modulos_detalle FROM investigacion_jobs WHERE id=?", (job_id,)).fetchone()
    md = {}
    if row:
        try: md = json.loads(row["modulos_detalle"] or "{}")
        except: md = {}
    md[modulo] = pct
    conn.execute("UPDATE investigacion_jobs SET modulos_detalle=? WHERE id=?", (json.dumps(md), job_id))
    conn.commit(); conn.close()

# ── HTTP UTILS ────────────────────────────────────────────────
def _safe_float(val, default=0.0):
    if val is None: return default
    try:    return float(val)
    except: return default

_BS4_OK = False
try:
    from bs4 import BeautifulSoup as _BS, XMLParsedAsHTMLWarning
    import warnings as _warnings
    _warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
    _BS4_OK = True
except ImportError:
    pass

_JS_PATRONES = re.compile(
    r"type=['\"]?text/(css|javascript)|window\.bt_cc|"
    r"media=['\"]?all|dns-prefetch|stylesheet|application/rss|"
    r"function\s*\(|var\s+\w|const\s+\w|window\.|document\.|"
    r"translate\[|'prev'\s*=|'next'\s*=",
    re.IGNORECASE
)

def _limpiar_html(html_text):
    """Extrae texto limpio de HTML usando BeautifulSoup (o regex como fallback)."""
    if not html_text:
        return ''
    if _BS4_OK:
        soup = _BS(html_text, 'html.parser')
        for tag in soup(['script', 'style', 'noscript', 'iframe',
                         'link', 'meta', 'head', 'nav', 'footer',
                         'header', 'aside']):
            tag.decompose()
        texto = soup.get_text(separator=' ', strip=True)
    else:
        # Regex fallback
        texto = re.sub(r'<(script|style|noscript|iframe|svg|head)[^>]*>.*?</\1>',
                       '', html_text, flags=re.DOTALL | re.IGNORECASE)
        texto = re.sub(r'<[^>]+>', ' ', texto)
    # Colapsar espacios
    texto = re.sub(r'\s+', ' ', texto)
    # Filtrar fragmentos de código JS/CSS
    lineas = texto.split('.')
    limpias = []
    for l in lineas:
        l = l.strip()
        if not l or len(l) < 20:
            continue
        if _JS_PATRONES.search(l):
            continue
        spec = sum(1 for c in l if c in '{}();=><[]')
        if spec > 4 and spec / max(len(l), 1) > 0.15:
            continue
        limpias.append(l)
    return '. '.join(limpias[:300])

def _strip_html(html):
    """Alias rápido para compatibilidad interna."""
    if not html:
        return ''
    html = re.sub(r'<(script|style|noscript|iframe|svg|head)[^>]*>.*?</\1>',
                  '', html, flags=re.DOTALL | re.IGNORECASE)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html)).strip()

def _limpiar_texto(texto):
    """Limpia texto plano de fragmentos JS/CSS residuales."""
    if not texto:
        return ''
    limpias = []
    for l in texto.split('\n'):
        l = l.strip()
        if not l or len(l) < 5:
            continue
        if _JS_PATRONES.search(l):
            continue
        spec = sum(1 for c in l if c in '{}();=><[]')
        if spec > 4 and spec / max(len(l), 1) > 0.15:
            continue
        limpias.append(l)
    return ' '.join(limpias)

def _filtrar_reciente(texto, años_validos=None):
    """Descarta fragmentos con años anteriores a AÑO_ANTERIOR."""
    if años_validos is None:
        años_validos = {AÑO_ANTERIOR, AÑO_ACTUAL, AÑO_SIGUIENTE}
    if not texto:
        return texto
    parrafos = str(texto).split('.')
    relevantes = []
    for p in parrafos:
        años_en_texto = [int(a) for a in re.findall(r'20\d\d', p)]
        if not años_en_texto:
            relevantes.append(p)
            continue
        if any(a in años_validos for a in años_en_texto) or all(a >= AÑO_ANTERIOR for a in años_en_texto):
            relevantes.append(p)
    return '.'.join(relevantes)

def _validar_url(url):
    """Valida que la URL sea segura antes de hacer request."""
    if not url or not isinstance(url, str):
        return False, "URL vacía"
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return False, "URL debe comenzar con http:// o https://"
    # Bloquear IPs privadas y localhost
    import re as _re
    privados = r'(localhost|127\.|192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)'
    if _re.search(privados, url, _re.IGNORECASE):
        return False, "URL apunta a red privada — no permitido"
    if len(url) > 2048:
        return False, "URL demasiado larga"
    return True, "OK"

def _sanitizar_input(texto, max_len=500):
    """Limpia inputs de texto antes de usarlos en queries o logs."""
    if not isinstance(texto, str):
        texto = str(texto)
    # Eliminar caracteres de control y null bytes
    texto = re.sub(r'[\x00-\x1f\x7f]', ' ', texto)
    return texto[:max_len].strip()

def _http_get(url, headers=None, timeout=15, max_reintentos=3):
    """HTTP GET con validación de URL, timeout fijo y reintentos."""
    ok, motivo = _validar_url(url)
    if not ok:
        return f"ERROR:URL_INVALIDA:{motivo}"
    # Timeout máximo 15 segundos — nunca más
    timeout = min(timeout, 15)
    h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120"}
    if headers: h.update(headers)
    for intento in range(max_reintentos):
        try:
            req = _req.Request(url, headers=h)
            with _req.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="ignore")
        except Exception as e:
            if intento == max_reintentos - 1:
                return f"ERROR:{e}"
            time.sleep(1)
    return "ERROR:MAX_REINTENTOS"

def _google_snippets(query, num=8):
    url = f"https://www.google.com/search?q={quote_plus(query)}&num={num}&hl=es&gl=co"
    raw = _http_get(url)
    snippets = []
    for pat in [r'<div[^>]*class="[^"]*VwiC3b[^"]*"[^>]*>(.*?)</div>',
                r'<span[^>]*class="[^"]*aCOpRe[^"]*"[^>]*>(.*?)</span>']:
        for m in re.findall(pat, raw, re.DOTALL):
            t = _strip_html(m).strip()
            if t and len(t) > 40:
                snippets.append(t[:400])
    return list(dict.fromkeys(snippets))[:num]

# ── MÓDULO 1: SCRAPE WEB OFICIAL ──────────────────────────────
def _scrape_web(url):
    if not url or not url.startswith("http"):
        return {"ok": False, "razon": "URL no válida o no proporcionada"}
    raw = _http_get(url, timeout=18)
    if raw.startswith("ERROR:"):
        return {"ok": False, "razon": raw}

    result = {
        "ok": True, "url": url,
        "titulo": "",
        "meta_descripcion": "",
        "servicios": [],
        "beneficios": [],
        "problemas_mencionados": [],
        "diferenciales": [],
        "garantias": [],
        "testimonios_web": [],
        "cta_principal": "",
        "tiene_blog": False,
        "tiene_testimonios": False,
        "raw_length": len(raw),
    }

    # Título
    m = re.search(r'<title[^>]*>(.*?)</title>', raw, re.DOTALL | re.IGNORECASE)
    if m: result["titulo"] = _strip_html(m.group(1))[:120]

    # Meta descripción
    m = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']{10,})["\']', raw, re.IGNORECASE)
    if m: result["meta_descripcion"] = m.group(1)[:300]

    # Detectar elementos clave — todo sobre texto LIMPIO (sin HTML, sin JS, sin CSS)
    texto_limpio = _limpiar_html(raw)
    texto = texto_limpio.lower()
    # Dividir en oraciones para extraer snippets sin código
    oraciones = [s.strip() for s in re.split(r'[.!?]', texto_limpio) if len(s.strip()) > 20]

    def _snippet_limpio(marker, oraciones, max_len=200):
        """Extrae la oración del texto limpio que contiene el marcador."""
        marker_l = marker.lower()
        for s in oraciones:
            if marker_l in s.lower():
                return s[:max_len]
        return ""

    PAIN_MARKERS = ["¿cansado","problema","dificultad","sin resultados","frustra","preocupa",
                    "dolor","pérdida","dejas de","pierdes","no puedes","te cuesta"]
    DIFER_MARKERS = ["únicos","única","solo nosotros","garantizamos","más de ",
                     "años de experiencia","certificados","avalados","especializados"]
    GARANTIA_MARKERS = ["garantía","garantizamos","devolvemos","sin riesgo","satisfacción garantizada",
                        "100%","gratis si","riesgo cero"]

    for marker in PAIN_MARKERS:
        if marker in texto:
            clean = _snippet_limpio(marker, oraciones)
            if clean and clean not in result["problemas_mencionados"]:
                result["problemas_mencionados"].append(clean)
    result["problemas_mencionados"] = result["problemas_mencionados"][:5]

    for marker in DIFER_MARKERS:
        if marker in texto:
            clean = _snippet_limpio(marker, oraciones, max_len=150)
            if clean and clean not in result["diferenciales"]:
                result["diferenciales"].append(clean)
    result["diferenciales"] = result["diferenciales"][:5]

    for marker in GARANTIA_MARKERS:
        if marker in texto:
            clean = _snippet_limpio(marker, oraciones)
            if clean and clean not in result["garantias"]:
                result["garantias"].append(clean)
    result["garantias"] = result["garantias"][:3]

    # CTA principal
    cta_patterns = [r'<a[^>]*class="[^"]*btn[^"]*"[^>]*>(.*?)</a>',
                    r'<button[^>]*>(.*?)</button>',
                    r'<a[^>]*href="[^"]*contacto[^"]*"[^>]*>(.*?)</a>']
    for pat in cta_patterns:
        matches = re.findall(pat, raw, re.DOTALL | re.IGNORECASE)
        for m in matches[:3]:
            clean = _strip_html(m).strip()
            if clean and len(clean) > 3 and len(clean) < 60:
                result["cta_principal"] = clean
                break
        if result["cta_principal"]: break

    result["tiene_blog"]        = "/blog" in url or "blog" in texto[:3000]
    result["tiene_testimonios"] = any(w in texto for w in ["reseña","testimonio","opinión","review","★","⭐"])
    result["texto_limpio_resumen"] = texto_limpio[:800]  # guardamos resumen del texto limpio

    return result

# ── MÓDULO 2: GOOGLE MAPS ─────────────────────────────────────
def _maps_search(keyword, location, api_key):
    if not api_key: return []
    url = ("https://maps.googleapis.com/maps/api/place/textsearch/json?"
           + urlencode({"query": keyword + " " + location, "key": api_key, "language": "es"}))
    raw = _http_get(url)
    if raw.startswith("ERROR:"): return []
    try:    return json.loads(raw).get("results", [])
    except: return []

def _maps_details(place_id, api_key):
    if not api_key or not place_id: return {}
    url = ("https://maps.googleapis.com/maps/api/place/details/json?"
           + urlencode({
               "place_id": place_id,
               "fields": "name,formatted_address,formatted_phone_number,website,rating,"
                         "user_ratings_total,reviews,opening_hours,price_level",
               "key": api_key, "language": "es"
           }))
    raw = _http_get(url)
    if raw.startswith("ERROR:"): return {}
    try:    return json.loads(raw).get("result", {})
    except: return {}

def _buscar_negocio_en_maps(nombre, ciudad, api_key):
    """Busca el negocio específico del cliente en Maps."""
    if not api_key:
        return {"ok": False, "razon": "Sin Google Maps API key"}
    places = _maps_search(nombre, ciudad, api_key)
    if not places:
        places = _maps_search(nombre.split()[0] if nombre else "", ciudad, api_key)
    if not places:
        return {"ok": False, "razon": "No encontrado en Maps", "nombre": nombre}

    place = places[0]
    det = _maps_details(place.get("place_id"), api_key)

    reviews_raw = det.get("reviews") or []
    positivas, negativas = [], []
    for rev in reviews_raw:
        txt = (rev.get("text") or "").strip()
        rat = _safe_float(rev.get("rating"), 3.0)
        if not txt: continue
        if rat >= 4: positivas.append(txt[:300])
        elif rat <= 2: negativas.append(txt[:300])

    return {
        "ok": True,
        "nombre": det.get("name") or place.get("name","?"),
        "direccion": det.get("formatted_address",""),
        "rating": _safe_float(det.get("rating") or place.get("rating")),
        "total_reviews": int(_safe_float(det.get("user_ratings_total") or place.get("user_ratings_total") or 0)),
        "website": det.get("website",""),
        "telefono": det.get("formatted_phone_number",""),
        "reviews_positivas": positivas,
        "reviews_negativas": negativas,
        "reviews_raw": reviews_raw[:5],
        "place_id": place.get("place_id",""),
    }

def _buscar_competidores_maps(nicho, ciudad, api_key, excluir_nombre="", max_comp=5):
    """Busca los top competidores del nicho."""
    if not api_key: return []
    kws = NICHOS_KEYWORDS.get(nicho, [nicho.replace("_"," ")])
    all_places = []
    for kw in kws[:2]:
        places = _maps_search(kw, ciudad, api_key)
        for p in places:
            if not any(ex.get("place_id") == p.get("place_id") for ex in all_places):
                if excluir_nombre.lower() not in (p.get("name","")).lower():
                    all_places.append(p)
        time.sleep(0.2)

    competidores = []
    for place in all_places[:max_comp+3]:
        det = _maps_details(place.get("place_id"), api_key)
        reviews_raw = det.get("reviews") or []
        reviews_txt = [r.get("text","")[:250] for r in reviews_raw if r.get("text")]
        positivas = [t for t, r in zip(reviews_txt, reviews_raw) if _safe_float(r.get("rating",3)) >= 4]
        negativas = [t for t, r in zip(reviews_txt, reviews_raw) if _safe_float(r.get("rating",3)) <= 2]
        competidores.append({
            "nombre":    place.get("name","?"),
            "rating":    _safe_float(place.get("rating")),
            "reviews":   int(_safe_float(place.get("user_ratings_total") or 0)),
            "website":   bool(det.get("website")),
            "web_url":   det.get("website",""),
            "diferencial": (reviews_txt[0] if reviews_txt else "")[:150],
            "reviews_positivas": positivas[:3],
            "reviews_negativas": negativas[:3],
        })
        if len(competidores) >= max_comp: break
        time.sleep(0.2)

    return competidores

# ── MÓDULO 3: FACEBOOK ADS LIBRARY ───────────────────────────
def _buscar_facebook_ads(nombre, nicho_kw, ciudad):
    """
    Accede a Facebook Ads Library pública.
    URL pública: facebook.com/ads/library/?country=CO&q=...
    Solo extrae datos públicos disponibles sin autenticación.
    """
    resultados = []

    # Intento 1: Ads Library URL pública
    url = (f"https://www.facebook.com/ads/library/?country=CO&ad_type=all"
           f"&q={quote_plus(nombre)}&search_type=keyword_unordered")
    raw = _http_get(url, timeout=18)
    if not raw.startswith("ERROR:"):
        page_names = re.findall(r'"page_name"\s*:\s*"([^"]{3,80})"', raw)
        ad_texts   = re.findall(r'"ad_creative_body"\s*:\s*"([^"]{10,})"', raw)
        cta_types  = re.findall(r'"call_to_action_type"\s*:\s*"([^"]{3,40})"', raw)
        for i, name in enumerate(page_names[:6]):
            resultados.append({
                "pagina":        name,
                "texto_anuncio": ad_texts[i] if i < len(ad_texts) else "",
                "cta":           cta_types[i] if i < len(cta_types) else "",
                "fuente":        "Facebook Ads Library",
            })

    # Intento 2: Búsqueda por nicho en la ciudad
    if len(resultados) < 3:
        url2 = (f"https://www.facebook.com/ads/library/?country=CO&ad_type=all"
                f"&q={quote_plus(nicho_kw + ' ' + ciudad)}&search_type=keyword_unordered")
        raw2 = _http_get(url2, timeout=15)
        if not raw2.startswith("ERROR:"):
            page_names2 = re.findall(r'"page_name"\s*:\s*"([^"]{3,80})"', raw2)
            ad_texts2   = re.findall(r'"ad_creative_body"\s*:\s*"([^"]{10,})"', raw2)
            for i, name in enumerate(page_names2[:4]):
                if not any(r["pagina"] == name for r in resultados):
                    resultados.append({
                        "pagina":        name,
                        "texto_anuncio": ad_texts2[i] if i < len(ad_texts2) else "",
                        "cta":           "",
                        "fuente":        "Facebook Ads Library (nicho)",
                    })

    # Fallback: Google snippets sobre anuncios activos del sector
    if len(resultados) < 2:
        for s in _google_snippets(f'anuncios publicidad {nicho_kw} {ciudad} 2024 2025 site:facebook.com OR "Facebook Ads"', num=4):
            if len(s) > 40:
                resultados.append({"pagina": "Referencia web", "texto_anuncio": s, "cta": "", "fuente": "Google"})

    return resultados[:10]

# ── MÓDULO 4: INSTAGRAM (posts públicos) ─────────────────────
def _buscar_instagram(instagram_handle, nombre_negocio=""):
    """
    Extrae información de cuenta Instagram pública.
    Si no hay handle, intenta DESCUBRIRLO buscando en Google.
    """
    result = {"ok": False, "handle": "", "url": "", "posts_analizados": [], "comentarios": []}

    # ── Paso 1: Descubrir handle si no se provee ──────────────
    if not instagram_handle and nombre_negocio:
        # Variaciones del nombre para buscar
        nombre_slug = nombre_negocio.lower().replace(" ", "").replace("-", "")
        queries_discovery = [
            f"site:instagram.com {nombre_negocio}",
            f"instagram.com/{nombre_slug}",
            f"{nombre_negocio} instagram perfil oficial",
            f"@{nombre_slug} instagram",
        ]
        for q in queries_discovery:
            raw_g = _http_get(
                f"https://www.google.com/search?q={quote_plus(q)}&num=5&hl=es&gl=co",
                timeout=10
            )
            handles_encontrados = re.findall(
                r'instagram\.com/([\w.]{2,40})(?:/|"|\?|&)', raw_g, re.IGNORECASE
            )
            for h in handles_encontrados:
                if h.lower() not in ("p", "reel", "explore", "accounts", "login", "stories"):
                    instagram_handle = h
                    break
            if instagram_handle:
                break
            time.sleep(0.3)

    if not instagram_handle:
        result["razon"] = "No encontrado en búsqueda de Google"
        # Aun así, buscamos menciones por nombre
        if nombre_negocio:
            for s in _google_snippets(f'{nombre_negocio} instagram seguidores publicaciones', num=4):
                if s and len(s) > 30:
                    result["comentarios"].append(s[:200])
        return result

    handle = instagram_handle.lstrip("@").strip()
    result["handle"] = handle
    result["url"] = f"https://www.instagram.com/{handle}/"

    # ── Paso 2: Scrape básico del perfil público ──────────────
    raw = _http_get(f"https://www.instagram.com/{handle}/", timeout=15)
    if not raw.startswith("ERROR:") and len(raw) > 500:
        follower_m = re.search(r'"edge_followed_by":\{"count":(\d+)\}', raw)
        bio_m      = re.search(r'"biography":"([^"]{5,})"', raw)
        posts_m    = re.search(r'"edge_owner_to_timeline_media":\{"count":(\d+)\}', raw)
        if follower_m:
            result["seguidores"] = int(follower_m.group(1))
            result["ok"] = True
        if bio_m:
            result["bio"] = bio_m.group(1)[:300]
        if posts_m:
            result["total_posts"] = int(posts_m.group(1))

    # ── Paso 3: Menciones públicas vía Google ────────────────
    for s in _google_snippets(f'site:instagram.com "@{handle}"', num=5):
        if s and len(s) > 30:
            result["comentarios"].append(s[:200])
    for s in _google_snippets(f'instagram "{handle}" opiniones clientes', num=4):
        if s and len(s) > 30 and s not in result["comentarios"]:
            result["comentarios"].append(s[:200])

    result["ok"] = True
    return result

# ── MÓDULO 5: FUENTES ACADÉMICAS ─────────────────────────────
def _buscar_academico(nicho_kw, ciudad):
    """Reutiliza la lógica de market_researcher."""
    resultados = []
    queries = [
        f"comportamiento consumidor {nicho_kw} Colombia 2023 2024 2025",
        f"psicología compra {nicho_kw} Latinoamérica 2024",
        f"sesgos cognitivos consumidor servicios {nicho_kw}",
    ]
    for q in queries[:2]:
        url = f"https://scholar.google.com/scholar?q={quote_plus(q)}&hl=es&as_ylo=2022"
        raw = _http_get(url, timeout=14)
        if not raw.startswith("ERROR:"):
            titles    = re.findall(r'class="gs_rt"[^>]*>.*?<a[^>]*>(.*?)</a>', raw, re.DOTALL)
            abstracts = re.findall(r'class="gs_rs"[^>]*>(.*?)</div>', raw, re.DOTALL)
            authors   = re.findall(r'class="gs_a"[^>]*>(.*?)</div>', raw, re.DOTALL)
            for i, title in enumerate(titles[:3]):
                t  = _strip_html(title).strip()
                a  = _strip_html(abstracts[i]).strip()[:250] if i < len(abstracts) else ""
                au = _strip_html(authors[i]).strip()[:100]   if i < len(authors)   else ""
                if t and len(t) > 15:
                    resultados.append({"titulo": t[:200], "autores": au, "resumen": a, "fuente": "Google Scholar"})
        time.sleep(0.5)

    # Repositorios colombianos
    for s in _google_snippets(f'"comportamiento del consumidor" "{nicho_kw}" Colombia filetype:pdf 2023 2024', num=3):
        if len(s) > 60:
            resultados.append({"titulo": s[:150], "autores": "", "resumen": s[:250], "fuente": "Repositorio académico"})

    return resultados[:8]

# ── MÓDULO 6: DANE ───────────────────────────────────────────
def _buscar_dane(nicho_kw):
    """
    Busca datos estadísticos del NICHO (no de la empresa).
    Siempre usa nicho_kw, nunca el nombre de la empresa.
    """
    resultados = []
    queries = [
        f"site:dane.gov.co {nicho_kw} estadisticas",
        f"dane.gov.co encuesta {nicho_kw} colombia {AÑO_ACTUAL}",
        f"confecamaras {nicho_kw} colombia {AÑO_ACTUAL} estadisticas empresas",
        f"minsalud {nicho_kw} colombia informe {AÑO_ACTUAL}",
        f"dane micronegocios {nicho_kw} colombia {AÑO_ANTERIOR} {AÑO_ACTUAL}",
        f"estadisticas {nicho_kw} colombia gobierno {AÑO_ACTUAL} {AÑO_SIGUIENTE}",
    ]
    for q in queries:
        for s in _google_snippets(q, num=3):
            if len(s) > 60:
                resultados.append({"entidad": "DANE/Gremio", "dato": s[:280], "año": str(AÑO_ACTUAL)})
        time.sleep(0.3)
    return resultados[:10]

# ── MÓDULO 7B: RESEÑAS EXTERNAS (Judge.me / Trustpilot / Amazon) ─
NICHOS_ECOMMERCE = {"ecommerce", "restaurante", "sello_musical", "artista_independiente"}

def _buscar_reviews_externas(nombre, url, nicho):
    """Busca reseñas en Judge.me, Trustpilot y Amazon vía Google snippets.
    Solo relevante para nichos e-commerce o si hay URL con esas plataformas."""
    resultados = {"judge_me": [], "trustpilot": [], "amazon": [], "fuente": []}
    nombre_q = quote_plus(nombre)

    # Judge.me — tiendas Shopify
    for s in _google_snippets(f'site:judge.me "{nombre}" reviews', num=5):
        if len(s) > 40:
            resultados["judge_me"].append(s[:300])
            resultados["fuente"].append("Judge.me")
    time.sleep(0.3)

    # Trustpilot — cualquier empresa
    for s in _google_snippets(f'site:trustpilot.com "{nombre}"', num=5):
        if len(s) > 40:
            resultados["trustpilot"].append(s[:300])
            resultados["fuente"].append("Trustpilot")
    time.sleep(0.3)

    # Amazon — solo si el nicho lo justifica
    if nicho in NICHOS_ECOMMERCE:
        for s in _google_snippets(f'site:amazon.com.co "{nombre}" opiniones', num=4):
            if len(s) > 40:
                resultados["amazon"].append(s[:300])
                resultados["fuente"].append("Amazon")
        time.sleep(0.3)

    total = len(resultados["judge_me"]) + len(resultados["trustpilot"]) + len(resultados["amazon"])
    resultados["total"] = total
    resultados["ok"] = total > 0
    return resultados

# ── MÓDULO 0: NIVEL MACRO — INVESTIGACIÓN DEL SECTOR ─────────
def _investigar_sector(nicho_kw, ciudad):
    """
    NIVEL MACRO: investiga el sector/industria en 3 capas.
    NUNCA busca la empresa específica — busca comportamiento del mercado.

    Capa A — Psicología y neurociencia del consumidor
    Capa B — Datos económicos y estadísticos del nicho
    Capa C — Estudios académicos (Scholar, repositorios)
    """
    resultado = {
        "psicologia_consumidor": [],
        "neurociencia_marketing": [],
        "sesgos_cognitivos": [],
        "miedos_motivaciones": [],
        "comportamiento_consumidor": [],
        "datos_economicos": [],
        "precios_sector": [],
        "barreras_acceso": [],
        "tendencias": [],
        "estudios_academicos": [],
        "noticias": [],
    }

    # ── CAPA A: PSICOLOGÍA Y NEUROCIENCIA ─────────────────────
    queries_psico = [
        ("psicologia_consumidor",  f"psicologia paciente {nicho_kw} Colombia decision compra {AÑO_ACTUAL}"),
        ("neurociencia_marketing", f"neurociencia marketing {nicho_kw} servicios Colombia {AÑO_ACTUAL}"),
        ("sesgos_cognitivos",      f"sesgos cognitivos consumidor {nicho_kw} latinoamerica {AÑO_ACTUAL}"),
        ("psicologia_consumidor",  f"por que pacientes eligen {nicho_kw} Colombia estudio"),
        ("miedos_motivaciones",    f"miedos paciente {nicho_kw} Colombia psicologia decision"),
        ("miedos_motivaciones",    f"motivaciones cliente {nicho_kw} Colombia neurociencia {AÑO_ACTUAL}"),
        ("sesgos_cognitivos",      f"factores decision compra {nicho_kw} Colombia investigacion"),
        ("psicologia_consumidor",  f"influencia familiar decision {nicho_kw} Colombia"),
        ("psicologia_consumidor",  f"tiempo decision compra {nicho_kw} servicios Colombia"),
    ]

    # ── CAPA B: DATOS ECONÓMICOS ──────────────────────────────
    queries_economico = [
        ("datos_economicos",   f"dane encuesta {nicho_kw} colombia {AÑO_ACTUAL} {AÑO_ANTERIOR}"),
        ("datos_economicos",   f"estadisticas {nicho_kw} colombia dane {AÑO_ACTUAL}"),
        ("tendencias",         f"mercado {nicho_kw} colombia crecimiento {AÑO_ACTUAL} {AÑO_SIGUIENTE}"),
        ("datos_economicos",   f"confecamaras empresas {nicho_kw} colombia {AÑO_ACTUAL}"),
        ("precios_sector",     f"precio promedio {nicho_kw} {ciudad} {AÑO_ACTUAL} {AÑO_SIGUIENTE}"),
        ("datos_economicos",   f"informe sector {nicho_kw} colombia ministerio salud {AÑO_ACTUAL}"),
        ("barreras_acceso",    f"objeciones barreras cliente {nicho_kw} Colombia {AÑO_ACTUAL}"),
    ]

    # ── CAPA C: ESTUDIOS ACADÉMICOS ───────────────────────────
    queries_scholar = [
        ("estudios_academicos", f'"{nicho_kw}" Colombia "comportamiento del consumidor" {AÑO_ACTUAL}'),
        ("estudios_academicos", f'"{nicho_kw}" Colombia "toma de decisiones" paciente {AÑO_ANTERIOR} {AÑO_ACTUAL}'),
        ("estudios_academicos", f'neurociencia "{nicho_kw}" marketing latinoamerica {AÑO_ACTUAL}'),
        ("estudios_academicos", f'"{nicho_kw}" Colombia satisfaccion cliente encuesta {AÑO_ACTUAL}'),
        ("sesgos_cognitivos",   f'sesgos cognitivos "{nicho_kw}" servicios Colombia'),
    ]

    # Ejecutar capa A
    for categoria, q in queries_psico[:6]:   # máx 6 para no ser bloqueados
        snippets = _google_snippets(q, num=4)
        resultado[categoria].extend(s for s in snippets if s and len(s) > 50)
        resultado[categoria] = list(dict.fromkeys(resultado[categoria]))[:6]
        time.sleep(0.3)

    # Ejecutar capa B
    for categoria, q in queries_economico[:5]:
        snippets = _google_snippets(q, num=4)
        resultado[categoria].extend(s for s in snippets if s and len(s) > 50)
        resultado[categoria] = list(dict.fromkeys(resultado[categoria]))[:6]
        time.sleep(0.3)

    # Ejecutar capa C — Scholar directo + fallback Google
    for categoria, q in queries_scholar[:3]:
        scholar_url = f"https://scholar.google.com/scholar?q={quote_plus(q)}&hl=es&as_ylo={AÑO_ANTERIOR}"
        raw = _http_get(scholar_url, timeout=14)
        if not raw.startswith("ERROR:"):
            titles    = re.findall(r'class="gs_rt"[^>]*>.*?<a[^>]*>(.*?)</a>', raw, re.DOTALL)
            abstracts = re.findall(r'class="gs_rs"[^>]*>(.*?)</div>', raw, re.DOTALL)
            for i, title in enumerate(titles[:3]):
                t = _strip_html(title).strip()
                a = _strip_html(abstracts[i]).strip()[:250] if i < len(abstracts) else ""
                if t and len(t) > 15:
                    resultado[categoria].append(f"{t}: {a}")
        else:
            # Fallback: Google normal
            for s in _google_snippets(q, num=3):
                if len(s) > 60:
                    resultado[categoria].append(s)
        time.sleep(0.5)

    # Noticias recientes
    for s in _google_snippets(f"{nicho_kw} {ciudad} {AÑO_ACTUAL} tendencias noticias", num=4):
        if len(s) > 50:
            resultado["noticias"].append(s)

    return resultado


def _descubrir_redes_sociales(nombre, dominio=""):
    """Busca en Google los perfiles de redes sociales del negocio."""
    redes = {"instagram": "", "facebook": "", "tiktok": "", "youtube": ""}
    busquedas = {
        "instagram": f"site:instagram.com {nombre}",
        "facebook":  f"site:facebook.com {nombre}",
        "tiktok":    f"site:tiktok.com {nombre}",
        "youtube":   f"site:youtube.com {nombre}",
    }
    for red, q in busquedas.items():
        raw = _http_get(
            f"https://www.google.com/search?q={quote_plus(q)}&num=3&hl=es&gl=co",
            timeout=8
        )
        if raw.startswith("ERROR:"):
            continue
        urls = re.findall(r'href="(https?://' + red + r'\.com/[^"&]{3,60})"', raw, re.IGNORECASE)
        for u in urls:
            if dominio and dominio in u:
                continue
            if any(kw in u.lower() for kw in ['login','signup','search','explore','reels','stories']):
                continue
            redes[red] = u
            break
        time.sleep(0.2)
    return redes


# ── MÓDULO 8: CRAWL SITIO COMPLETO ───────────────────────────
def _crawl_sitio_completo(url_base, max_paginas=6):
    """
    Sigue los links internos del sitio para extraer texto de páginas clave.
    Prioriza páginas de servicios, precios, testimonios, FAQ, nosotros.
    """
    if not url_base:
        return {}
    PRIORITY = ["precio","servicio","tratamiento","testimonio","nosotros","faq",
                "contacto","equipo","proceso","garantia","resultado","antes","despues"]
    raw_home = _http_get(url_base, timeout=18)
    if raw_home.startswith("ERROR:"):
        return {}

    from urllib.parse import urljoin, urlparse
    base_domain = urlparse(url_base).netloc
    # Find all internal links
    links = re.findall(r'href=["\']([^"\'#?]{4,})["\']', raw_home, re.IGNORECASE)
    internal = []
    for link in links:
        full = urljoin(url_base, link)
        if urlparse(full).netloc == base_domain and full != url_base:
            internal.append(full)
    internal = list(dict.fromkeys(internal))  # dedup

    # Sort by priority keywords
    def priority_score(u):
        u_low = u.lower()
        return sum(1 for kw in PRIORITY if kw in u_low)
    internal.sort(key=priority_score, reverse=True)

    paginas = {}
    for link in internal[:max_paginas]:
        raw = _http_get(link, timeout=14)
        if not raw.startswith("ERROR:"):
            texto = _limpiar_html(raw)
            if len(texto) > 100:
                key = urlparse(link).path.strip("/") or "home"
                paginas[key] = {"url": link, "texto": texto[:1500]}
        time.sleep(0.4)
    return paginas


# ── MÓDULO 9: BÚSQUEDA MULTICAPA GOOGLE ──────────────────────
def _busqueda_multicapa(nombre, ciudad, nicho_kw, url=""):
    """
    Ejecuta múltiples queries de Google para encontrar lo que la web oficial oculta:
    quejas, precios, comparativas, menciones externas.
    """
    resultados = {
        "reviews_google": [],
        "quejas": [],
        "precios": [],
        "vs_competidor": [],
        "menciones_externas": [],
        "noticias": [],
    }

    from urllib.parse import urlparse as _urlparse
    _domain = _urlparse(url).netloc if url else "example.com"
    queries = {
        "reviews_google":    f'"{nombre}" {ciudad} reseñas opiniones clientes',
        "quejas":            f'"{nombre}" {ciudad} quejas problemas malo experiencia',
        "precios":           f'"{nombre}" {ciudad} precio costo cuánto vale',
        "vs_competidor":     f'{nicho_kw} {ciudad} mejor alternativa opciones comparar',
        "menciones_externas":f'"{nombre}" -site:{_domain}',
        "noticias":          f'"{nombre}" {ciudad} 2024 2025',
    }

    for key, q in queries.items():
        snippets = _google_snippets(q, num=6)
        resultados[key] = snippets
        time.sleep(0.4)

    return resultados


# ── MÓDULO 10: WAYBACK MACHINE ────────────────────────────────
def _buscar_wayback(url):
    """Consulta Wayback Machine CDX API para obtener snapshots del sitio."""
    if not url:
        return []
    from urllib.parse import urlparse as _urlparse2
    domain = _urlparse2(url).netloc
    cdx = (f"http://web.archive.org/cdx/search/cdx?url={quote_plus(domain)}"
           f"&output=json&limit=5&fl=timestamp,statuscode&from=20230101&to=20260101&filter=statuscode:200")
    raw = _http_get(cdx, timeout=12)
    if raw.startswith("ERROR:"):
        return []
    try:
        rows = json.loads(raw)
        return [{"fecha": r[0][:8], "status": r[1]} for r in rows[1:6]]
    except Exception:
        return []


# ── MÓDULO 7: ANÁLISIS 7 MALETAS LOCAL ───────────────────────
def _analizar_7_maletas(nombre, nicho, ciudad, tamanio,
                        web_data, negocio_maps, competidores,
                        fb_ads, instagram_data, academico, dane):
    """Produce el análisis completo de las 7 Maletas para un negocio específico."""
    nicho_label = nicho.replace("_"," ")

    # Consolidar todas las reviews
    reviews_pos = list(negocio_maps.get("reviews_positivas", []))
    reviews_neg = list(negocio_maps.get("reviews_negativas", []))
    for comp in competidores:
        reviews_pos.extend(comp.get("reviews_positivas", [])[:2])
        reviews_neg.extend(comp.get("reviews_negativas", [])[:2])

    total_reviews = (negocio_maps.get("total_reviews", 0) +
                     sum(c.get("reviews", 0) for c in competidores))

    # Detectar dolores desde reviews negativas
    PAIN_KW = {
        "espera":         "Tiempos de espera excesivos — citas no respetadas",
        "precio":         "Precios poco transparentes o cobros inesperados",
        "atención":       "Mala atención al cliente — falta de calidez",
        "caro":           "Percepción de cobro excesivo vs valor recibido",
        "demora":         "Demoras en entrega del servicio/resultado",
        "no contest":     "No responden mensajes ni llamadas",
        "garantía":       "No cumplen con la garantía ofrecida",
        "grosero":        "Personal descortés o indiferente",
        "cancelar":       "Cancelaciones de último momento",
        "desorganiz":     "Desorganización en agendamiento",
    }
    ELOGIO_KW = {
        "excelente":      "Excelencia general del servicio",
        "amable":         "Trato amable y personalizado",
        "profesional":    "Profesionalismo del equipo",
        "rápido":         "Rapidez y puntualidad",
        "limpio":         "Instalaciones limpias",
        "resultado":      "Resultados visibles y medibles",
        "recomiendo":     "Alta tasa de recomendación espontánea",
        "calidad":        "Calidad percibida del servicio",
    }

    dolor_conteo, elogio_conteo = {}, {}
    for rev in reviews_neg:
        rl = rev.lower()
        for kw, label in PAIN_KW.items():
            if kw in rl: dolor_conteo[label] = dolor_conteo.get(label, 0) + 1
    for rev in reviews_pos:
        rl = rev.lower()
        for kw, label in ELOGIO_KW.items():
            if kw in rl: elogio_conteo[label] = elogio_conteo.get(label, 0) + 1

    # Añadir dolores de web_data
    for prob in web_data.get("problemas_mencionados", []):
        dolor_conteo[prob[:80]] = dolor_conteo.get(prob[:80], 0) + 1

    top_dolores = sorted(dolor_conteo.items(), key=lambda x: x[1], reverse=True)[:8]
    top_elogios = sorted(elogio_conteo.items(), key=lambda x: x[1], reverse=True)[:6]

    principal_dolor = {"problema": top_dolores[0][0] if top_dolores else "Falta de confianza y seguimiento", "menciones": top_dolores[0][1] if top_dolores else 1, "evidencia": reviews_neg[0][:200] if reviews_neg else ""}

    # Diferenciales del negocio vs competidores
    difs_negocio = web_data.get("diferenciales", [])
    difs_comp = set()
    for comp in competidores:
        difs_comp.add(comp.get("diferencial","")[:60].lower())

    mejor_diferencial = difs_negocio[0][:80] if difs_negocio else "Sin diferencial claro detectado en web"
    menos_saturado = mejor_diferencial

    # Garantía
    garantias = web_data.get("garantias", [])
    garantia_actual = garantias[0][:200] if garantias else "No se detectó garantía explícita en la web"

    # Top testimonios
    top_testimonios = []
    for r in reviews_pos[:5]:
        if len(r) > 40:
            top_testimonios.append({"texto": r[:280], "fuente": f"Google Maps — {nombre}"})

    # Objeciones detectadas
    OBJECIONES = [
        ("Precio elevado",          "precio",       reviews_neg),
        ("No confío en la calidad", "calidad",      reviews_neg),
        ("No sé si vale la pena",   "vale",         []),
        ("Hay opciones más baratas","alternativa",  []),
        ("No tengo tiempo",         "tiempo",       []),
        ("No sé si es para mí",     "para mí",      []),
        ("Malas experiencias",      "mala",         reviews_neg),
        ("Lejos de mi casa",        "distancia",    []),
        ("Sin cita disponible",     "cita",         reviews_neg),
        ("Prefiero esperar",        "esperar",      []),
    ]
    objeciones_lista = []
    for label, kw, source in OBJECIONES:
        ev = next((r for r in source if kw in r.lower()), "")
        objeciones_lista.append({
            "objecion":  label,
            "evidencia": ev[:150] if ev else f"Objeción frecuente en {nicho_label}",
            "riesgo":    "🔴 ALTO" if ev else "🟡 MEDIO",
        })

    # Ads basados en el análisis
    dolor_copy = principal_dolor["problema"][:60]
    test_copy  = top_testimonios[0]["texto"][:80] if top_testimonios else f"Excelente {nicho_label}"
    ads = [
        {
            "tipo":       "Enfoque en Problema",
            "headline":   f"¿Cansado de {dolor_copy}?",
            "descripcion": (f"En {nombre}, lo resolvemos. {mejor_diferencial[:60]}.\n\n"
                            f'"{test_copy[:80]}"\n\n'
                            f"{garantia_actual[:80] if 'garantía' in garantia_actual.lower() else 'Sin riesgo para ti'} → Agenda ahora"),
            "cta": "Agendar cita",
        },
        {
            "tipo":       "Diferencial único",
            "headline":   f"{mejor_diferencial[:60]} — solo en {nombre}",
            "descripcion": (f"Resolvemos '{dolor_copy}' de una vez. "
                            f"Atención personalizada en {ciudad}.\n\nPrimeras citas disponibles esta semana."),
            "cta": "Ver disponibilidad",
        },
        {
            "tipo":       "Testimonio/Resultado",
            "headline":   f'"{test_copy[:70]}..."',
            "descripcion": (f"Así describió un cliente su experiencia en {nombre}.\n"
                            f"¿Listo para el mismo resultado?\n\n{garantia_actual[:60]} → Contáctanos"),
            "cta": "Quiero este resultado",
        },
    ]

    # Estrategia de testimonios según tamaño
    meta_reviews = {"pequeña": 30, "mediana": 75, "grande": 150}.get(tamanio.lower(), 50)
    current_reviews = negocio_maps.get("total_reviews", 0)

    return {
        "maleta_1_publico": {
            "edad_estimada":    "25-55 años (pico 30-45)",
            "genero":           "Mixto — analizar con Meta Audience Insights para datos exactos",
            "ubicacion":        ciudad,
            "poder_adquisitivo": {"pequeña": "NSE 2-4", "mediana": "NSE 3-5", "grande": "NSE 4-6"}.get(tamanio.lower(), "NSE 3-5"),
            "evidencias":       [r[:120] for r in reviews_pos[:3]],
        },
        "maleta_2_problema": {
            "lista_dolores":  [{"problema": k, "menciones": v, "evidencia": next((r for r in reviews_neg if any(w in r.lower() for w in k.lower().split()[:2])), "")[:150]} for k,v in top_dolores[:8]],
            "top_3":          [{"problema": k, "menciones": v} for k,v in top_dolores[:3]],
            "principal":      principal_dolor,
        },
        "maleta_3_solucion": {
            "servicios":         web_data.get("servicios",[]) or [f"Servicio principal de {nicho_label}"],
            "como_resuelve":     f"{nombre} resuelve '{principal_dolor['problema']}' mediante {mejor_diferencial[:60]} y atención personalizada",
            "mejor_testimonio":  top_testimonios[0]["texto"][:300] if top_testimonios else "Sin testimonios textuales disponibles",
            "competidores_sol":  [{"competidor": c["nombre"], "mensaje": c.get("diferencial","")[:100]} for c in competidores[:3]],
            "oportunidad":       f"De {len(competidores)} competidores, {sum(1 for c in competidores if not c.get('website'))} no tienen web activa.",
        },
        "maleta_4_diferenciales": {
            "lista":         [{"diferencial": e, "frecuencia": v} for e,v in top_elogios[:6]],
            "menos_saturado": {"diferencial": menos_saturado, "en_comp": 1},
            "recomendacion": f"DESTACA '{menos_saturado}' — diferencial con menor saturación detectada en competidores.",
        },
        "maleta_5_testimonios": {
            "rating":          negocio_maps.get("rating", 0),
            "total_reviews":   current_reviews,
            "top_5":           top_testimonios[:5],
            "patrones":        [f"{round(v/max(len(reviews_pos),1)*100)}% menciona: {k}" for k,v in list(elogio_conteo.items())[:4]],
            "meta_30_dias":    f"Pasar de {current_reviews} a {current_reviews + meta_reviews} reviews en 30 días",
            "script_review":   f"'Hola [nombre], ¿quedaste satisfecho/a? Nos dejarías una reseña en Google? 🙏 [link]'",
        },
        "maleta_6_objeciones": {
            "lista_10_plus": objeciones_lista,
            "principal":     objeciones_lista[0] if objeciones_lista else {},
            "como_resolver": {
                "en_web":     f"FAQ que responda: '{objeciones_lista[0]['objecion'] if objeciones_lista else ''}'",
                "en_anuncios": "Incluye garantía explícita en el copy del anuncio",
                "en_ventas":  "Script: 'Entiendo tu duda. Por eso en [nombre] ofrecemos [solución].'",
            },
        },
        "maleta_7_garantia": {
            "garantia_actual":  garantia_actual,
            "garantia_sugerida": f"'Si no quedas satisfecho/a con tu {nicho_label} en {nombre}, repetimos el servicio sin costo. Sin preguntas.'",
            "justificacion":    [
                f"Resuelve la objeción #1: '{objeciones_lista[0]['objecion'] if objeciones_lista else ''}'",
                f"Solo {sum(1 for c in competidores if 'garantía' in str(c.get('diferencial','')).lower())} competidores ofrecen garantía visible",
                "Garantías aumentan conversión 20-40% en sector servicios",
            ],
            "recomendacion": "IMPLEMENTA garantía explícita en web y anuncios — diferencial de bajo costo con alto impacto.",
        },
        "ads_messages":     ads,
        "proximos_pasos": {
            "esta_semana": [
                {"accion": "Actualiza Google Business con fotos recientes y responde todas las reviews", "impacto": "Más visibilidad local inmediata"},
                {"accion": f"Agrega garantía explícita a tu web", "impacto": "Reduce objeción principal"},
                {"accion": "Implementa solicitud de reviews vía WhatsApp post-servicio", "impacto": "+5-10 reviews/mes"},
            ],
            "este_mes": [
                "Entrevista 5-10 clientes: ¿Por qué nos elegiste?",
                f"Lanza campaña Meta Ads con Anuncio 1 (dolor: {dolor_copy[:40]})",
                f"Crea contenido: 'Cómo elegir el mejor {nicho_label} en {ciudad} — 3 factores clave'",
            ],
        },
        "fuentes_resumen": {
            "reviews_negocio":  current_reviews,
            "reviews_comp":     sum(c.get("reviews",0) for c in competidores),
            "total_reviews":    total_reviews,
            "competidores":     len(competidores),
            "fb_ads":           len(fb_ads),
            "academicas":       len(academico),
            "dane":             len(dane),
            "web_ok":           web_data.get("ok", False),
            "instagram_ok":     instagram_data.get("ok", False),
        },
    }

# ── MÓDULO 8: CLAUDE SYNTHESIS ────────────────────────────────
def _call_claude(prompt, max_tokens=3000):
    api_key = os.environ.get("ANTHROPIC_API_KEY","")
    if not api_key: return ""
    try:
        payload = json.dumps({
            "model": "claude-sonnet-4-5",
            "max_tokens": max_tokens,
            "system": ("Eres un investigador de mercado experto en la metodología 7 Maletas de Felipe Vergara. "
                       "Analiza datos reales y genera insights accionables para estrategias de marketing digital en Colombia."),
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        req = _req.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={"Content-Type":"application/json","x-api-key":api_key,"anthropic-version":"2023-06-01"},
            method="POST"
        )
        with _req.urlopen(req, timeout=300) as r:
            data = json.loads(r.read().decode())
            return data.get("content",[{}])[0].get("text","")
    except Exception as e:
        return f"[Claude no disponible: {e}]"

# ── INFORME FORMATEADO COMPLETO ───────────────────────────────
def _generar_informe_formateado(nombre, nicho, nicho_kw, ciudad, tamanio,
                                 url, instagram, web_data, negocio_maps,
                                 competidores, fb_ads, instagram_data,
                                 academico, dane, maletas,
                                 datos_macro=None):
    """
    Genera el informe de inteligencia completo como texto formateado.
    Si hay ANTHROPIC_API_KEY, usa Claude para generar el informe completo.
    Si no hay key, genera el informe desde los datos locales.
    """
    if datos_macro is None:
        datos_macro = {}
    fecha = FECHA_HOY

    # ── Preparar datos consolidados ────────────────────────────
    rev_pos  = negocio_maps.get("reviews_positivas", [])
    rev_neg  = negocio_maps.get("reviews_negativas", [])
    rating   = negocio_maps.get("rating", 0)
    n_reviews = negocio_maps.get("total_reviews", 0)

    # Reviews de competidores
    comp_rev_pos, comp_rev_neg = [], []
    for c in competidores:
        comp_rev_pos.extend(c.get("reviews_positivas", [])[:2])
        comp_rev_neg.extend(c.get("reviews_negativas", [])[:2])

    todas_pos = rev_pos + comp_rev_pos
    todas_neg = rev_neg + comp_rev_neg

    m1  = maletas.get("maleta_1_publico", {})
    m2  = maletas.get("maleta_2_problema", {})
    m3  = maletas.get("maleta_3_solucion", {})
    m4  = maletas.get("maleta_4_diferenciales", {})
    m5  = maletas.get("maleta_5_testimonios", {})
    m6  = maletas.get("maleta_6_objeciones", {})
    m7  = maletas.get("maleta_7_garantia", {})
    ads = maletas.get("ads_messages", [])
    pps = maletas.get("proximos_pasos", {})

    principal_dolor = m2.get("principal", {}).get("problema", "No identificado")
    mejor_dif = m4.get("menos_saturado", {}).get("diferencial", "Sin diferencial claro")
    garantia  = m7.get("garantia_actual", "No detectada")
    garantia_sug = m7.get("garantia_sugerida", "")

    tamanio_presupuesto = {
        "micro": "$500K–$1M COP/mes", "pequeña": "$1.5M COP/mes",
        "mediana": "$5M COP/mes", "grande": "$15M+ COP/mes",
    }.get(tamanio.lower(), "$3M COP/mes")

    # ── Intentar con Claude API (informe completo) ────────────
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        # Preparar contexto compacto para el prompt
        rev_pos_txt = "\n".join(f'"{r[:180]}"' for r in rev_pos[:8])
        rev_neg_txt = "\n".join(f'"{r[:180]}"' for r in rev_neg[:8])
        comp_txt = "\n".join(
            f"- {c.get('nombre','?')}: {c.get('rating',0)}/5 ({c.get('reviews',0)} reviews) | "
            f"Dif: {c.get('diferencial','?')[:80]} | Web: {'sí' if c.get('website') else 'no'}"
            for c in competidores[:5]
        )
        ads_txt = "\n".join(
            f"- [{a.get('tipo','?')}] {a.get('texto_anuncio','')[:150]}"
            for a in fb_ads[:5]
        ) or "Sin anuncios detectados"
        servicios_txt = "; ".join(web_data.get("servicios", [])[:8]) or "No detectados en web"
        dolores_txt = "\n".join(
            f"- {d.get('problema','?')} ({d.get('menciones',0)} menciones)"
            for d in m2.get("lista_dolores", [])[:8]
        )
        # Multicapa data
        mc = web_data.get("busqueda_multicapa", {})
        quejas_txt  = "\n".join(f'- "{s[:220]}"' for s in mc.get("quejas", [])[:6]) or "Sin quejas encontradas en Google"
        precios_txt = "\n".join(f'- "{s[:220]}"' for s in mc.get("precios", [])[:5]) or "Sin precios encontrados"
        menciones_txt = "\n".join(f'- "{s[:220]}"' for s in mc.get("menciones_externas", [])[:5]) or "Sin menciones externas"
        vs_txt      = "\n".join(f'- "{s[:220]}"' for s in mc.get("vs_competidor", [])[:5]) or "Sin comparativas encontradas"
        noticias_txt = "\n".join(f'- "{s[:220]}"' for s in mc.get("noticias", [])[:4]) or "Sin noticias recientes"
        # Pages crawled
        paginas_internas = web_data.get("paginas_internas", {})
        paginas_txt = "\n".join(
            f"[/{k}] {v.get('texto','')[:350]}"
            for k, v in list(paginas_internas.items())[:5]
        ) or "Solo se analizó la página principal"
        # Redes sociales descubiertas
        redes = web_data.get("redes_descubiertas", {})
        redes_txt = (
            f"Instagram: {redes.get('instagram','no encontrado')} | "
            f"Facebook: {redes.get('facebook','no encontrado')} | "
            f"TikTok: {redes.get('tiktok','no encontrado')} | "
            f"YouTube: {redes.get('youtube','no encontrado')}"
        )
        # NIVEL MACRO: datos del sector (nueva estructura con psicología)
        macro = datos_macro or {}

        def _join_macro(keys, limit=5, max_len=250):
            items = []
            for k in (keys if isinstance(keys, list) else [keys]):
                items.extend(macro.get(k, []))
            items = list(dict.fromkeys(items))
            return "\n".join(f'- "{s[:max_len]}"' for s in items[:limit]) or "Sin datos encontrados"

        macro_psico      = _join_macro(["psicologia_consumidor", "comportamiento_consumidor"])
        macro_neuro      = _join_macro(["neurociencia_marketing"])
        macro_sesgos     = _join_macro(["sesgos_cognitivos"])
        macro_miedos     = _join_macro(["miedos_motivaciones"])
        macro_economico  = _join_macro(["datos_economicos"])
        macro_precios    = _join_macro(["precios_sector"])
        macro_barreras   = _join_macro(["barreras_acceso"])
        macro_tendencias = _join_macro(["tendencias"])
        macro_scholar    = _join_macro(["estudios_academicos"])
        macro_noticias   = _join_macro(["noticias"])

        # Instagram descubierto
        ig_data  = instagram_data if isinstance(instagram_data, dict) else {}
        ig_handle = ig_data.get("handle", "") or instagram or "no encontrado"
        ig_url    = ig_data.get("url", "")
        ig_seg    = ig_data.get("seguidores", "?")
        ig_coments = "\n".join(f'- "{c[:200]}"' for c in ig_data.get("comentarios", [])[:5]) or "Sin comentarios encontrados"

        SEP = "━" * 42

        prompt = f"""Eres el psicólogo y estratega de marketing de Intelligent Markets. Fecha: {FECHA_HOY}.

Tienes datos de investigación en 3 niveles.
Analiza TODO y genera el informe completo con análisis psicológico profundo.

REGLAS ABSOLUTAS:
- NADA de JSON. NADA de código. Solo texto formateado con separadores ━.
- Cada insight CON evidencia real (cita textual de review o dato).
- Si no hay dato → "no encontrado". NUNCA inventar.
- Usar solo fechas {AÑO_ANTERIOR}-{AÑO_ACTUAL}-{AÑO_SIGUIENTE}.

━━━ NIVEL 1: PSICOLOGÍA DEL NICHO {nicho_kw.upper()} EN COLOMBIA ━━━

PSICOLOGÍA DEL CONSUMIDOR:
{macro_psico}

NEUROCIENCIA Y MARKETING:
{macro_neuro}

SESGOS COGNITIVOS IDENTIFICADOS EN EL SECTOR:
{macro_sesgos}

MIEDOS Y MOTIVACIONES DEL PACIENTE/CLIENTE:
{macro_miedos}

DATOS ECONÓMICOS DEL SECTOR:
{macro_economico}

PRECIOS PROMEDIO DEL SECTOR {AÑO_ACTUAL}:
{macro_precios}

BARRERAS DE ACCESO / OBJECIONES COMUNES:
{macro_barreras}

TENDENCIAS {AÑO_ACTUAL}-{AÑO_SIGUIENTE}:
{macro_tendencias}

ESTUDIOS ACADÉMICOS (Scholar/repositorios {AÑO_ANTERIOR}-{AÑO_ACTUAL}):
{macro_scholar}

━━━ NIVEL 2: COMPETENCIA EN {ciudad.upper()} ━━━

COMPETIDORES PRINCIPALES:
{comp_txt or 'Sin competidores mapeados'}

ANUNCIOS ACTIVOS EN EL SECTOR (Facebook Ads Library):
{ads_txt}

━━━ NIVEL 3: {nombre.upper()} — EMPRESA ESPECÍFICA ━━━

PERFIL: {nombre} | {ciudad} | {nicho_kw} | Tamaño: {tamanio}
Web: {url or 'No disponible'} | Rating: {rating}/5 ({n_reviews} reseñas)
Servicios: {servicios_txt}
Instagram descubierto: @{ig_handle} ({ig_seg} seguidores) | {ig_url}
Facebook: {redes.get('facebook','no encontrado')} | TikTok: {redes.get('tiktok','no encontrado')}
Pauta Meta activa: {'Sí — ' + str(len(fb_ads)) + ' anuncios detectados' if fb_ads else 'No detectada'}

RESEÑAS POSITIVAS REALES:
{rev_pos_txt or '(Sin reseñas encontradas)'}

RESEÑAS NEGATIVAS REALES:
{rev_neg_txt or '(Sin quejas en Maps)'}

QUEJAS ENCONTRADAS EN GOOGLE:
{quejas_txt}

PRECIOS ENCONTRADOS:
{precios_txt}

MENCIONES EXTERNAS:
{menciones_txt}

COMPARATIVAS CON COMPETIDORES:
{vs_txt}

NOTICIAS RECIENTES:
{noticias_txt}

PÁGINAS INTERNAS DEL SITIO:
{paginas_txt}

COMENTARIOS INSTAGRAM:
{ig_coments}

DOLORES DETECTADOS:
{dolores_txt or 'Sin dolores detectados'}

GARANTÍA ACTUAL: {garantia}

═══════════════════════════════════════════════
GENERA EL ANÁLISIS COMPLETO EN ESTE FORMATO:
═══════════════════════════════════════════════

{SEP}
INFORME DE INTELIGENCIA — {nombre.upper()}
{ciudad} | {nicho_kw.title()} | {FECHA_HOY}
Intelligent Markets — Investigación {AÑO_ACTUAL}
{SEP}

FUENTES CONSULTADAS:
✓ Web oficial: {url or 'No disponible'} ({len(paginas_internas)} páginas)
✓ Google Maps: {n_reviews} reseñas analizadas
✓ Facebook Ads Library: {len(fb_ads)} anuncios
✓ Instagram: @{ig_handle}
✓ TikTok: {redes.get('tiktok','no encontrado')}
✓ Competidores: {len(competidores)} analizados
✓ Estudios académicos: {len(academico)}
✓ Datos DANE/gremios: {'disponibles' if dane else 'no encontrado'}
✓ Psicología del nicho: datos recopilados

{SEP}
1. PERFIL DEL NEGOCIO
{SEP}
[Completa con datos reales encontrados]

{SEP}
2. VOZ DEL CLIENTE — REVIEWS REALES
{SEP}
[MÍNIMO 10 citas textuales de las reseñas — positivas, negativas, preguntas frecuentes]

{SEP}
3. ANÁLISIS DE COMPETIDORES ({AÑO_ACTUAL})
{SEP}
[Para cada competidor: nombre, rating, reviews, punto fuerte, punto débil, ads activos]

{SEP}
4. PUBLICIDAD ACTIVA — META ADS
{SEP}
[Analiza los anuncios detectados. Si no hay de {nombre}: analiza los del sector]
[Identifica el ángulo NO explotado por nadie]

{SEP}
5. ANÁLISIS PSICOLÓGICO PROFUNDO
{SEP}

SESGOS COGNITIVOS IDENTIFICADOS:
Para cada sesgo encontrado en los datos:
- Nombre del sesgo
- Cómo se manifiesta en {nicho_kw} específicamente
- Evidencia: [cita real de review o dato del sector]
- Cómo aprovecharlo en los ADS de {nombre}

Sesgos a identificar obligatoriamente:
→ Aversión a la pérdida: qué pierden si no actúan (evidencia real)
→ Sesgo de autoridad: quién influencia la decisión (dato del sector)
→ Prueba social: cuántas reseñas necesitan ver antes de comprar
→ Sesgo de anclaje: cómo perciben el precio (dato de precios del sector)
→ Efecto halo: qué primera impresión los convence
→ Sesgo de statu quo: por qué no cambian de proveedor
→ Miedo a ser engañados: qué los hace desconfiar (evidencia de quejas)

INFLUENCIADORES DE LA DECISIÓN:
→ ¿Quién influye? ¿La pareja? ¿Los hijos? ¿Los padres? ¿Amigos?
→ Evidencia de los datos recopilados
→ Cómo adaptar el mensaje a cada influenciador

PROCESO DE DECISIÓN (customer journey):
→ ¿Cuánto tiempo demoran en decidir?
→ ¿Qué buscan en Google antes de llamar?
→ ¿Cuántas opciones comparan?
→ ¿Qué los hace llamar vs seguir buscando?
→ Mapa del journey completo

MOTIVACIONES PROFUNDAS:
→ Motivación declarada: lo que dicen querer
→ Motivación real: lo que realmente los mueve
→ Miedo primario: qué es lo que más temen
→ Deseo profundo: el resultado emocional que buscan
→ Identidad: cómo quieren verse ante otros

{SEP}
6. ANÁLISIS 7 MALETAS (con evidencia real)
{SEP}

MALETA 1 — QUÉ TIENE:
→ Sector {nicho_kw}: [recursos comunes del nicho]
→ {nombre} específico: [basado en web, maps, páginas internas]
Evidencia: "[cita real]"

MALETA 2 — QUÉ LE FALTA:
→ Gap del sector {AÑO_ACTUAL}: [qué no tiene nadie]
→ Gap de {nombre}: [comparado con mejores competidores]
Evidencia: "[dato real]"

MALETA 3 — QUÉ DUELE AL CLIENTE (mínimo 5 dolores con citas):
- Dolor 1: "[cita textual real de reviews/quejas]" — X menciones
- Dolor 2: "[cita textual real]"
- Dolor 3: "[cita textual real]"
- Dolor 4: "[cita]"
- Dolor 5: "[cita]"
→ Sesgo activo: [nombre del sesgo y cómo se manifiesta]

MALETA 4 — QUÉ DESEA:
- Deseo declarado: "[cita review positiva real]"
- Deseo profundo: [análisis psicológico con evidencia macro]
→ Lo que buscan en Google antes de comprar

MALETA 5 — QUÉ LO FRENA:
- Objeción 1: "[evidencia real]"
- Objeción 2: "[evidencia real]"
- Objeción 3: "[evidencia real]"
→ Barreras del sector {AÑO_ACTUAL}: [datos macro]

MALETA 6 — QUÉ LO MUEVE A COMPRAR:
- Disparador 1: "[cita review positiva real]"
- Disparador 2: "[evidencia real]"
→ Prueba social necesaria: [cuántas reviews, qué tipo]

MALETA 7 — OPORTUNIDAD PARA IM:
→ Gap del sector que {nombre} no cubre: [específico]
→ Mensaje ganador basado en datos reales: [texto exacto]
→ Diferencial menos saturado: [basado en análisis de competidores]
→ Ángulo de entrada óptimo: [específico]

{SEP}
7. PERFIL PSICOGRÁFICO DEL CLIENTE IDEAL
{SEP}
[Basado en datos reales — edad, NSE, motivación, miedo, journey, qué lo convence]
Frase que lo representa: "[cita real de review]"

{SEP}
8. ESTRATEGIA ADS BASADA EN PSICOLOGÍA ({AÑO_ACTUAL})
{SEP}
Presupuesto sugerido: {tamanio_presupuesto}

[Para cada campaña: qué sesgo activa, copy basado en miedo/deseo profundo]

CAMPAÑA 1 (dolor primario + aversión a la pérdida):
Copy A — Hook: "[frase que usa palabras REALES de reviews]"
Copy B — Hook: "[variación con ángulo diferente]"
Copy C — Hook: "[ángulo de autoridad/prueba social]"

CAMPAÑA 2 (retargeting — statu quo):
[Copy específico para quien ya visitó pero no convirtió]

ÁNGULO NO EXPLOTADO (oportunidad):
→ [Lo que nadie dice en el sector — basado en análisis de ads y reviews]

{SEP}
9. PLAN DE CONTENIDO — 18 GUIONES
{SEP}
[6 fases × 3 videos. Hooks basados en sesgos cognitivos reales del sector]

FASE 1 — ATRACCIÓN (Aversión a la pérdida) — 3 videos:
Basado en: [dolor real más mencionado]
VIDEO 1.1: Hook + Escena + Guión completo 8-12 líneas + CTA + Sesgo activado
VIDEO 1.2: [ídem]
VIDEO 1.3: [ídem]

FASE 2 — EDUCATIVO/FAKE PODCAST (Authority Bias) — 3 videos:
Pregunta real del nicho: [detectada en reviews/búsquedas]
VIDEO 2.1-2.3: [guiones completos]

FASE 3 — DOCUMENTACIÓN/PROCESO (Prueba social) — 3 videos:
VIDEO 3.1-3.3: [guiones completos]

FASE 4 — VALIDACIÓN (Evidencia concreta) — 3 videos:
Basado en: [dato real de la investigación]
VIDEO 4.1-4.3: [guiones completos]

FASE 5 — STORYTELLING (Conexión emocional) — 3 videos:
Verdad incómoda del sector: [basada en datos reales]
VIDEO 5.1-5.3: [guiones completos]

FASE 6 — CIERRE/MANIFIESTO (Risk Reversal) — 3 videos:
VIDEO 6.1-6.3: [guiones con garantía explícita y urgencia real]

{SEP}
10. RECOMENDACIÓN ESTRATÉGICA FINAL
{SEP}
[Cruce de NIVEL MACRO psicología + NIVEL MICRO datos empresa]

Semana 1: [acción concreta #1]
Semana 2-4: [acción concreta #2]
Mes 2-3: [acción concreta #3]

ROAS esperado: [X]:1 en [X] meses
Inversión mínima: {tamanio_presupuesto}
Retorno estimado: [basado en sector y datos]"""

        resultado = _call_claude(prompt, max_tokens=4000)
        if resultado and not resultado.startswith("[Claude"):
            return resultado

    # ── Fallback: informe desde datos locales (sin Claude) ────
    SEP = "━" * 50
    # Use discovered handle if available, otherwise fall back to provided handle
    _ig_data_fb = instagram_data if isinstance(instagram_data, dict) else {}
    _ig_handle_fb = _ig_data_fb.get("handle", "") or instagram or "No proporcionado"
    lineas = [
        SEP,
        f"INFORME DE INTELIGENCIA — {nombre.upper()}",
        f"{ciudad} | {nicho_kw.title()} | {FECHA_HOY}",
        f"Intelligent Markets — Investigación {AÑO_ACTUAL}",
        "(Nota: activa ANTHROPIC_API_KEY para informe completo con IA — 18 guiones y análisis psicológico)",
        SEP,
        "",
        "FUENTES CONSULTADAS:",
        f"✓ Web oficial: {url or 'No disponible'}",
        f"✓ Páginas internas crawleadas: {len(web_data.get('paginas_internas', {}))}",
        f"✓ Google Maps: {n_reviews} reseñas analizadas",
        f"✓ Google Search multicapa: quejas, precios, comparativas, menciones externas",
        f"✓ Facebook Ads: {len(fb_ads)} anuncios",
        f"✓ Instagram: @{_ig_handle_fb}",
        f"✓ Competidores: {len(competidores)} en {ciudad}",
        f"✓ Wayback Machine: historial consultado",
        f"✓ Fuentes académicas: {len(academico)}",
        "",
        SEP,
        "1. PERFIL DEL NEGOCIO",
        SEP,
        f"Nombre: {nombre}",
        f"Ciudad: {ciudad} | Nicho: {nicho_kw.title()}",
        f"Tamaño: {tamanio.title()}",
        f"Web: {url or 'No disponible'}",
        f"Instagram: @{_ig_handle_fb}",
        f"Rating Google: {rating}/5 ({n_reviews} reseñas)",
        f"Tiene pauta activa: {'Sí — ' + str(len(fb_ads)) + ' anuncios' if fb_ads else 'No detectada'}",
        f"Servicios: {'; '.join(web_data.get('servicios',[])[:5]) or 'No detectados'}",
        "",
        SEP,
        "2. VOZ DEL CLIENTE",
        SEP,
        "",
        "RESEÑAS POSITIVAS:",
    ]
    for r in rev_pos[:6]:
        if len(r) > 30:
            lineas.append(f'⭐ "{r[:200]}"')
    # Include multicapa quejas in fallback
    _mc_quejas = web_data.get("busqueda_multicapa", {}).get("quejas", [])
    lineas += ["", "QUEJAS Y DOLORES:"]
    for r in (_mc_quejas[:3] + rev_neg[:5]):
        if len(r) > 20:
            lineas.append(f'⚠ "{r[:200]}"')
    lineas += [
        "",
        SEP,
        "3. COMPETIDORES",
        SEP,
    ]
    for i, c in enumerate(competidores[:5], 1):
        lineas += [
            f"COMPETIDOR {i}: {c.get('nombre','?')}",
            f"Rating: {c.get('rating',0)}/5 | Reviews: {c.get('reviews',0)} | Web: {'sí' if c.get('website') else 'no'}",
            f"Diferencial: {c.get('diferencial','No detectado')[:100]}",
            "",
        ]
    lineas += [
        SEP,
        "4. FACEBOOK ADS ACTIVOS",
        SEP,
    ]
    if fb_ads:
        for a in fb_ads[:5]:
            lineas.append(f"→ {a.get('texto_anuncio','')[:200]}")
        lineas.append(f"\nOPORTUNIDAD: Lo que nadie dice → {mejor_dif}")
    else:
        lineas.append("No se detectaron anuncios activos.")
    lineas += [
        "",
        SEP,
        "5. ANÁLISIS 7 MALETAS",
        SEP,
        "",
        "MALETA 3 — QUÉ DUELE AL CLIENTE:",
    ]
    for d in m2.get("lista_dolores", [])[:6]:
        lineas.append(f"• {d.get('problema','?')} ({d.get('menciones',0)} menciones)")
        ev = d.get("evidencia","")
        if ev:
            lineas.append(f'  Evidencia: "{ev[:150]}"')
    lineas += [
        "",
        "MALETA 4 — QUÉ DESEA EL CLIENTE:",
    ]
    for e in m4.get("lista", [])[:5]:
        lineas.append(f"• {e.get('diferencial','?')} ({e.get('frecuencia',0)} menciones)")
    lineas += [
        "",
        "MALETA 5 — QUÉ LO FRENA (objeciones):",
    ]
    for o in m6.get("lista_10_plus", [])[:5]:
        lineas.append(f"• {o.get('objecion','?')} [{o.get('riesgo','?')}]")
    lineas += [
        "",
        "MALETA 7 — OPORTUNIDAD:",
        f"→ Diferencial menos saturado: {mejor_dif}",
        f"→ Garantía recomendada: {garantia_sug[:150] if garantia_sug else 'Define garantía explícita'}",
        "",
        SEP,
        f"5B. CONTEXTO DEL SECTOR {nicho_kw.upper()} EN {AÑO_ACTUAL}",
        SEP,
        "COMPORTAMIENTO DEL CONSUMIDOR (estudios recientes):",
    ]
    for s in (datos_macro or {}).get("comportamiento_consumidor", [])[:4]:
        lineas.append(f"• {s[:250]}")
    lineas += [
        "",
        f"TENDENCIAS {AÑO_ACTUAL}:",
    ]
    for s in (datos_macro or {}).get("tendencias", [])[:4]:
        lineas.append(f"• {s[:250]}")
    lineas += [
        "",
        "BARRERAS Y OBJECIONES DEL SECTOR:",
    ]
    for s in (datos_macro or {}).get("barreras_acceso", [])[:3]:
        lineas.append(f"• {s[:200]}")
    lineas += [
        "",
        SEP,
        "7. ESTRATEGIA ADS RECOMENDADA",
        SEP,
        f"Presupuesto sugerido: {tamanio_presupuesto}",
        "",
    ]
    for i, ad in enumerate(ads[:3], 1):
        lineas += [
            f"COPY VARIACIÓN {['A','B','C'][i-1]} — {ad.get('tipo','?')}:",
            f"Headline: {ad.get('headline','?')}",
            f"Texto: {ad.get('descripcion','')[:200]}",
            f"CTA: {ad.get('cta','?')}",
            "",
        ]
    lineas += [
        SEP,
        "9. RECOMENDACIÓN FINAL",
        SEP,
        "",
        "Esta semana:",
    ]
    for paso in pps.get("esta_semana", [])[:3]:
        if isinstance(paso, dict):
            lineas.append(f"→ {paso.get('accion','?')}")
        else:
            lineas.append(f"→ {paso}")
    lineas += [
        "",
        "Este mes:",
    ]
    for paso in pps.get("este_mes", [])[:3]:
        lineas.append(f"→ {paso}")
    lineas += [
        "",
        SEP,
        "FUENTES:",
        f"• Web: {url or 'No disponible'}",
        f"• Google Maps: {n_reviews} reseñas",
        f"• FB Ads: {len(fb_ads)} anuncios | Competidores: {len(competidores)}",
        SEP,
    ]
    return "\n".join(lineas)


# ── INVESTIGACIÓN PRINCIPAL ────────────────────────────────────
def run_deep_investigation(job_id, nombre, url, instagram, ciudad, nicho, tamanio):
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY","")
    nicho_kw = NICHOS_KEYWORDS.get(nicho, [nicho.replace("_"," ")])[0]
    from urllib.parse import urlparse as _urlp
    dominio = _urlp(url).netloc if url else ""

    MODULOS = ["macro","web","maps_negocio","maps_competidores","facebook_ads","instagram","academico","dane","analisis","claude","reporte"]
    modulos_pct = {m: 0 for m in MODULOS}

    def upd(modulo, pct, msg=""):
        modulos_pct[modulo] = pct
        total = round(sum(modulos_pct.values()) / len(MODULOS))
        _update_job(job_id, progreso=total, modulo_actual=msg or modulo,
                    modulos_detalle=json.dumps(modulos_pct))

    try:
        _update_job(job_id, estado="corriendo")

        # 0. NIVEL MACRO — SECTOR (se ejecuta primero, en paralelo implícito)
        upd("macro", 20, f"Investigando sector {nicho_kw} en Colombia {AÑO_ACTUAL}...")
        datos_macro = _investigar_sector(nicho_kw, ciudad)
        upd("macro", 100)
        time.sleep(0.2)

        # 1. NIVEL MICRO — WEB OFICIAL + CRAWL + MULTICAPA
        upd("web", 10, f"Analizando web oficial: {url or 'no proporcionada'}")
        web_data = _scrape_web(url) if url else {"ok": False, "razon": "No proporcionada"}
        upd("web", 30, "Rastreando páginas internas (precios, servicios, testimonios)...")
        paginas_sitio = _crawl_sitio_completo(url) if url else {}
        web_data["paginas_internas"] = paginas_sitio
        upd("web", 55, "Búsqueda multicapa Google (quejas, precios, comparativas)...")
        busqueda_mc = _busqueda_multicapa(nombre, ciudad, nicho_kw, url)
        web_data["busqueda_multicapa"] = busqueda_mc
        upd("web", 75, "Descubriendo perfiles sociales (Instagram, Facebook, TikTok)...")
        redes_descubiertas = _descubrir_redes_sociales(nombre, dominio)
        web_data["redes_descubiertas"] = redes_descubiertas
        upd("web", 90, "Consultando historial Wayback Machine...")
        web_data["wayback"] = _buscar_wayback(url)
        upd("web", 100)
        time.sleep(0.3)

        # 2. GOOGLE MAPS — NEGOCIO PROPIO
        upd("maps_negocio", 20, f"Buscando '{nombre}' en Google Maps...")
        negocio_maps = _buscar_negocio_en_maps(nombre, ciudad, api_key)
        upd("maps_negocio", 100)
        time.sleep(0.3)

        # 3. GOOGLE MAPS — COMPETIDORES
        upd("maps_competidores", 20, "Mapeando top 5 competidores...")
        competidores = _buscar_competidores_maps(nicho, ciudad, api_key, excluir_nombre=nombre, max_comp=5)
        upd("maps_competidores", 100)
        time.sleep(0.3)

        # 4. FACEBOOK ADS LIBRARY
        upd("facebook_ads", 20, "Consultando Facebook Ads Library (pública)...")
        fb_ads = _buscar_facebook_ads(nombre, nicho_kw, ciudad)
        upd("facebook_ads", 100)
        time.sleep(0.3)

        # 5. INSTAGRAM
        upd("instagram", 20, f"Analizando/descubriendo Instagram de {nombre}...")
        instagram_data = _buscar_instagram(instagram, nombre_negocio=nombre)
        upd("instagram", 100)
        time.sleep(0.3)

        # 6. ACADÉMICO
        upd("academico", 20, "Consultando Google Scholar y repositorios colombianos...")
        academico = _buscar_academico(nicho_kw, ciudad)
        upd("academico", 100)
        time.sleep(0.3)

        # 7. DANE
        upd("dane", 20, "Consultando DANE y Confecámaras...")
        dane = _buscar_dane(nicho_kw)
        upd("dane", 100)
        time.sleep(0.2)

        # 7B. REVIEWS EXTERNAS (Judge.me / Trustpilot / Amazon)
        upd("analisis", 5, "Buscando reseñas en Judge.me / Trustpilot / Amazon...")
        reviews_externas = _buscar_reviews_externas(nombre, url, nicho)
        time.sleep(0.2)

        # 8. ANÁLISIS 7 MALETAS LOCAL
        upd("analisis", 20, "Aplicando análisis 7 Maletas...")
        maletas = _analizar_7_maletas(
            nombre, nicho, ciudad, tamanio,
            web_data, negocio_maps, competidores,
            fb_ads, instagram_data, academico, dane
        )
        upd("analisis", 100)

        # 9. CLAUDE — INFORME COMPLETO FORMATEADO
        upd("claude", 20, f"Generando informe completo con IA (Claude) — {FECHA_HOY}...")
        informe_formateado = _generar_informe_formateado(
            nombre=nombre, nicho=nicho, nicho_kw=nicho_kw, ciudad=ciudad,
            tamanio=tamanio, url=url, instagram=instagram,
            web_data=web_data, negocio_maps=negocio_maps,
            competidores=competidores, fb_ads=fb_ads,
            instagram_data=instagram_data, academico=academico,
            dane=dane, maletas=maletas,
            datos_macro=datos_macro,
        )
        # Mantener insight_claude corto para compatibilidad
        insight_claude = informe_formateado if informe_formateado else ""
        upd("claude", 100)

        # 10. GENERAR HTML
        upd("reporte", 20, "Generando informe HTML 7 Maletas...")
        resultado = {
            "meta": {
                "job_id": job_id, "nombre": nombre, "url": url or "",
                "instagram": instagram or "", "ciudad": ciudad,
                "nicho": nicho, "tamanio": tamanio,
                "terminado_at": datetime.now().isoformat(),
                "api_maps_usada": bool(api_key),
                "claude_usado":   bool(insight_claude and not insight_claude.startswith("[")),
            },
            "web":              web_data,
            "negocio_maps":     negocio_maps,
            "competidores":     competidores,
            "facebook_ads":     fb_ads,
            "instagram":        instagram_data,
            "academico":        academico,
            "dane":             dane,
            "reviews_externas": reviews_externas,
            "datos_macro":      datos_macro,
            "7_maletas":        maletas,
            "insight_claude":   insight_claude,
            "informe_formateado": informe_formateado,
        }

        html = _generar_html_reporte(resultado)
        REPORTS.mkdir(exist_ok=True)
        slug  = re.sub(r'[^a-z0-9]', '-', nombre.lower())[:30]
        fecha = datetime.now().strftime("%Y-%m-%d")
        path_html = REPORTS / f"7m-{slug}-{fecha}.html"
        path_html.write_text(html, encoding="utf-8")
        resultado["meta"]["html_path"] = str(path_html)
        resultado["meta"]["html_filename"] = path_html.name

        upd("reporte", 100)
        _update_job(job_id, estado="completado", progreso=100,
                    modulo_actual="Completado",
                    resultado=json.dumps(resultado, ensure_ascii=False),
                    terminado_at=datetime.now().isoformat())

        # Guardar en memoria persistente para no repetir en 30 días
        try:
            from session_memory import MemoriaAgentes
            resumen = str(resultado.get("insight_claude") or resultado.get("7_maletas") or "")[:2000]
            MemoriaAgentes().guardar_investigacion(nombre, url or "", job_id, resumen)
        except Exception:
            pass

    except Exception as e:
        import traceback
        _update_job(job_id, estado="error", progreso=0,
                    modulo_actual=f"Error: {str(e)[:200]}",
                    terminado_at=datetime.now().isoformat())
        print(f"[Deep Researcher] ERROR {job_id}: {e}\n{traceback.format_exc()}")

# ── HTML REPORT ───────────────────────────────────────────────
def _generar_html_reporte(data):
    """Genera el HTML 7 Maletas para el negocio investigado."""
    meta    = data.get("meta", {})
    maletas = data.get("7_maletas", {})
    neg_m   = data.get("negocio_maps", {})
    comps   = data.get("competidores", [])
    fb_ads  = data.get("facebook_ads", [])
    acad    = data.get("academico", [])
    dane    = data.get("dane", [])
    insight = data.get("insight_claude","")
    web     = data.get("web", {})

    nombre  = meta.get("nombre","")
    ciudad  = meta.get("ciudad","")
    nicho   = meta.get("nicho","").replace("_"," ").title()
    fecha   = datetime.now().strftime("%d/%m/%Y")

    def esc(s): return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

    m2 = maletas.get("maleta_2_problema",{})
    m4 = maletas.get("maleta_4_diferenciales",{})
    m5 = maletas.get("maleta_5_testimonios",{})
    m6 = maletas.get("maleta_6_objeciones",{})
    m7 = maletas.get("maleta_7_garantia",{})
    ads = maletas.get("ads_messages",[])
    pps = maletas.get("proximos_pasos",{})
    fsr = maletas.get("fuentes_resumen",{})

    principal = m2.get("principal",{})
    menos_sat = m4.get("menos_saturado",{})
    obj_prin  = m6.get("principal",{})

    # Competidores table
    comp_rows = "".join(
        f"<tr><td style='padding:10px 14px;border-bottom:1px solid #d2d2d7'>{esc(c.get('nombre',''))}</td>"
        f"<td style='padding:10px 14px;border-bottom:1px solid #d2d2d7;text-align:center'>{c.get('rating',0)}⭐</td>"
        f"<td style='padding:10px 14px;border-bottom:1px solid #d2d2d7;text-align:center'>{c.get('reviews',0)}</td>"
        f"<td style='padding:10px 14px;border-bottom:1px solid #d2d2d7;text-align:center'>{'✅' if c.get('website') else '❌'}</td>"
        f"<td style='padding:10px 14px;border-bottom:1px solid #d2d2d7;color:#6e6e73;font-size:13px'>{esc(c.get('diferencial','')[:60])}</td></tr>"
        for c in comps[:5]
    )

    # Ads HTML
    ads_html = ""
    ad_colors = ["#0071e3","#34c759","#ff9500"]
    for i, ad in enumerate(ads[:3],1):
        col = ad_colors[i-1]
        ads_html += f"""
        <div style="border:1px solid #d2d2d7;border-radius:12px;padding:24px;margin-bottom:20px">
          <div style="display:flex;gap:10px;align-items:center;margin-bottom:12px">
            <span style="background:{col};color:white;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600">Anuncio {i}</span>
            <span style="color:#6e6e73;font-size:13px">{esc(ad.get('tipo',''))}</span>
          </div>
          <p style="font-size:20px;font-weight:700;color:{col};margin-bottom:10px">{esc(ad.get('headline',''))}</p>
          <div style="background:#f5f5f7;padding:14px;border-radius:8px;white-space:pre-line;font-size:14px;line-height:1.7">{esc(ad.get('descripcion',''))}</div>
          <div style="margin-top:10px"><span style="background:{col}22;color:{col};padding:5px 12px;border-radius:6px;font-size:12px;font-weight:600">CTA: {esc(ad.get('cta',''))}</span></div>
        </div>"""

    # Insight Claude — texto completo con formato preservado
    insight_html = ""
    if insight and not insight.startswith("["):
        insight_escaped = esc(insight)
        insight_html = (
            f"<pre style='white-space:pre-wrap;font-family:-apple-system,BlinkMacSystemFont,"
            f"\"Segoe UI\",sans-serif;font-size:14px;line-height:1.8;background:#f5f5f7;"
            f"padding:24px;border-radius:12px;overflow-x:auto;color:#1d1d1f'>"
            f"{insight_escaped}</pre>"
        )
    else:
        insight_html = "<p style='color:#6e6e73'>Activar ANTHROPIC_API_KEY para sintesis IA completa.</p>"

    # Problems list
    prob_html = ""
    for i, p in enumerate(m2.get("lista_dolores",[])[:6], 1):
        _ev = p.get("evidencia","")
        _ev_html = f'<p style="font-style:italic;font-size:14px;margin-top:6px">"{esc(_ev)}"</p>' if _ev else ""
        prob_html += f"""
        <div style="margin-bottom:16px;padding:16px;background:#f5f5f7;border-radius:10px;border-left:4px solid #ff3b30">
          <p style="font-weight:600">{i}. {esc(p.get('problema',''))}</p>
          <p style="color:#6e6e73;font-size:14px;margin-top:6px">Menciones: {p.get('menciones',1)}</p>
          {_ev_html}
        </div>"""

    # Testimonios
    test_html = "".join(
        f'<div style="border:1px solid #d2d2d7;border-radius:10px;padding:18px;margin-bottom:14px">'
        f'<p style="font-size:16px">"{esc(t.get("texto",""))}"</p>'
        f'<p style="color:#6e6e73;font-size:13px;margin-top:8px">— {esc(t.get("fuente","Google Maps"))}</p></div>'
        for t in m5.get("top_5",[])[:4]
    ) or '<p style="color:#6e6e73">No se encontraron testimonios textuales. Activar Google Maps API.</p>'

    # FB ads
    fb_html = "".join(
        f'<div style="padding:12px;border:1px solid #d2d2d7;border-radius:8px;margin-bottom:10px">'
        f'<p style="font-size:12px;color:#0071e3;margin-bottom:4px">{esc(a.get("pagina",""))}</p>'
        f'<p style="color:#1d1d1f">{esc(a.get("texto_anuncio","")[:200])}</p></div>'
        for a in fb_ads[:4] if a.get("texto_anuncio")
    ) or '<p style="color:#6e6e73">Sin anuncios detectados (Facebook Ads Library limitada sin autenticación)</p>'

    # Acad
    acad_html = "".join(
        f'<div style="padding:12px;border:1px solid #d2d2d7;border-radius:8px;margin-bottom:10px">'
        f'<p style="font-size:12px;color:#0071e3">{esc(a.get("fuente",""))}</p>'
        f'<p style="font-weight:500">{esc(a.get("titulo","")[:160])}</p>'
        f'<p style="color:#6e6e73;font-size:13px">{esc(a.get("resumen","")[:200])}</p></div>'
        for a in acad[:4]
    ) or '<p style="color:#6e6e73">Consultar: scholar.google.com</p>'

    # Pasos
    pps_html = "".join(
        f'<div style="border-left:4px solid #0071e3;padding:12px 16px;margin-bottom:12px;background:#f5f5f7;border-radius:0 8px 8px 0">'
        f'<p style="font-weight:600">{esc(s.get("accion",""))}</p>'
        f'<p style="color:#34c759;font-size:13px;margin-top:4px">Impacto: {esc(s.get("impacto",""))}</p></div>'
        for s in pps.get("esta_semana",[])[:3]
    )

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>7 Maletas — {esc(nombre)} — {esc(ciudad)}</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{font-family:'Inter',-apple-system,sans-serif;line-height:1.7;color:#1d1d1f;background:#f5f5f7}}
    .container{{max-width:1100px;margin:0 auto;background:white}}
    .header{{background:#1d1d1f;padding:40px 64px}}
    .header h1{{font-size:42px;font-weight:700;color:white;margin-bottom:6px;letter-spacing:-1px}}
    .header p{{color:#a1a1a6;font-size:16px}}
    .exec{{padding:48px 64px;background:#fbfbfd;border-bottom:1px solid #d2d2d7}}
    .metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:24px;margin-top:24px}}
    .mval{{font-size:44px;font-weight:700;color:#0071e3;line-height:1;margin-bottom:4px}}
    .mlbl{{font-size:12px;color:#6e6e73;text-transform:uppercase;letter-spacing:.5px}}
    .content{{padding:64px}}
    .section{{margin-bottom:72px}}
    .badge{{font-size:11px;color:#0071e3;font-weight:600;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}}
    h2{{font-size:34px;font-weight:700;margin-bottom:8px;letter-spacing:-.5px}}
    .sub{{color:#6e6e73;font-size:16px;margin-bottom:32px}}
    h3{{font-size:20px;font-weight:600;margin:32px 0 14px}}
    p{{font-size:16px;line-height:1.7;margin-bottom:14px}}
    table{{width:100%;border-collapse:collapse}}
    th{{padding:10px 14px;font-size:12px;font-weight:600;text-align:left;border-bottom:1px solid #d2d2d7;color:#6e6e73;text-transform:uppercase}}
    .info-box{{background:#f5f5f7;padding:24px;border-radius:12px;margin:16px 0;border-left:4px solid #0071e3}}
    .info-box.success{{border-left-color:#34c759}}
    .info-box.warning{{border-left-color:#ff9500}}
    .hl{{background:#1d1d1f;color:white;padding:28px;border-radius:14px;margin:16px 0}}
    .hl h4{{font-size:18px;margin-bottom:8px;color:#f5f5f7}}
    .hl p{{color:#a1a1a6;margin:0}}
    .footer{{background:#f5f5f7;padding:40px 64px;text-align:center;border-top:1px solid #d2d2d7;color:#6e6e73}}
    @media(max-width:768px){{.header,.content,.exec,.footer{{padding:24px 20px}}.metrics{{grid-template-columns:1fr 1fr}}h2{{font-size:26px}}}}
  </style>
</head>
<body>
<div class="container">
  <div class="header">
    <div style="font-size:11px;letter-spacing:3px;text-transform:uppercase;color:#6e6e73;margin-bottom:12px">Las 7 Maletas de Cualquier Compra · {esc(nombre)}</div>
    <h1>{esc(nombre)}</h1>
    <p>{esc(nicho)} · {esc(ciudad)} · {fecha} · Investigación profunda automatizada por IM System</p>
  </div>

  <div class="exec">
    <h2 style="font-size:26px;margin-bottom:12px">Resumen de la Investigación</h2>
    <p>Análisis completo de <strong>{esc(nombre)}</strong> con {fsr.get('total_reviews',0)} reviews y {len(comps)} competidores directos.</p>
    <ul style="margin:12px 0 0 20px">
      <li>{"✅" if web.get("ok") else "⚠️"} Web oficial: {esc(web.get("titulo","") or web.get("razon","No analizada"))}</li>
      <li>{"✅" if neg_m.get("ok") else "⚠️"} Google Maps: {neg_m.get("rating",0)}⭐ · {neg_m.get("total_reviews",0)} reviews</li>
      <li>✅ Competidores: {len(comps)} mapeados en {esc(ciudad)}</li>
      <li>✅ Facebook Ads Library: {len(fb_ads)} referencias</li>
      <li>{"✅" if data.get("instagram",{}).get("ok") else "⚠️"} Instagram: {"analizado" if data.get("instagram",{}).get("ok") else "no proporcionado"}</li>
      <li>✅ Fuentes académicas: {len(acad)} estudios</li>
      <li>✅ DANE/Confecámaras: {len(dane)} datos</li>
    </ul>
    <div class="metrics">
      <div><div class="mval">{fsr.get('total_reviews',0)}</div><div class="mlbl">Reviews analizadas</div></div>
      <div><div class="mval">{len(comps)}</div><div class="mlbl">Competidores</div></div>
      <div><div class="mval">{len(acad)+len(dane)}</div><div class="mlbl">Fuentes externas</div></div>
      <div><div class="mval">7</div><div class="mlbl">Maletas completadas</div></div>
    </div>
  </div>

  <div class="content">

    <!-- MALETA 1 -->
    <div class="section">
      <div class="badge">Maleta 1 de 7</div>
      <h2>1 — Público</h2>
      <p class="sub">¿Quién compra {esc(nicho.lower())} en {esc(ciudad)}?</p>
      <div class="info-box">
        <p><strong>Edad:</strong> {esc(maletas.get("maleta_1_publico",{}).get("edad_estimada",""))}</p>
        <p><strong>Poder adquisitivo:</strong> {esc(maletas.get("maleta_1_publico",{}).get("poder_adquisitivo",""))}</p>
        <p><strong>Ubicación principal:</strong> {esc(maletas.get("maleta_1_publico",{}).get("ubicacion",""))}</p>
        <p><strong>Tamaño de empresa:</strong> {esc(meta.get("tamanio",""))}</p>
      </div>
    </div>

    <!-- MALETA 2 -->
    <div class="section">
      <div class="badge">Maleta 2 de 7</div>
      <h2>2 — Problema</h2>
      <p class="sub">Los dolores reales de los clientes de {esc(nombre)}</p>
      <h3>Dolores detectados en reviews:</h3>
      {prob_html}
      <div class="hl">
        <h4>Dolor principal: "{esc(principal.get('problema',''))}"</h4>
        <p>{esc(principal.get('evidencia',''))}</p>
      </div>
    </div>

    <!-- MALETA 3 -->
    <div class="section">
      <div class="badge">Maleta 3 de 7</div>
      <h2>3 — Solución</h2>
      <p class="sub">Cómo resuelve {esc(nombre)} los problemas de sus clientes</p>
      <div class="info-box">
        <p>{esc(maletas.get("maleta_3_solucion",{}).get("como_resuelve",""))}</p>
      </div>
      <h3>Competidores — cómo comunican su solución:</h3>
      <table><thead><tr><th>Empresa</th><th>Rating</th><th>Reviews</th><th>Web</th><th>Diferencial detectado</th></tr></thead>
      <tbody>{comp_rows}</tbody></table>
    </div>

    <!-- MALETA 4 -->
    <div class="section">
      <div class="badge">Maleta 4 de 7</div>
      <h2>4 — Diferenciales</h2>
      <p class="sub">Lo que hace único a {esc(nombre)}</p>
      <div class="info-box success">
        <p><strong>Diferencial menos saturado:</strong> {esc(menos_sat.get("diferencial",""))}</p>
        <p>{esc(m4.get("recomendacion",""))}</p>
      </div>
      <h3>Web oficial — diferenciales detectados:</h3>
      {'<ul style="padding-left:20px">' + "".join(f"<li style='margin:8px 0'>{esc(d)}</li>" for d in web.get("diferenciales",[])[:5]) + '</ul>' if web.get("diferenciales") else '<p style="color:#6e6e73">Sin diferenciales claros detectados en la web.</p>'}
    </div>

    <!-- MALETA 5 -->
    <div class="section">
      <div class="badge">Maleta 5 de 7</div>
      <h2>5 — Testimonios</h2>
      <p class="sub">{neg_m.get("rating",0)}/5 ⭐ · {neg_m.get("total_reviews",0)} reviews en Google Maps</p>
      {test_html}
      <div class="info-box">
        <p><strong>Meta 30 días:</strong> {esc(m5.get("meta_30_dias",""))}</p>
        <p><strong>Script WhatsApp:</strong> {esc(m5.get("script_review",""))}</p>
      </div>
    </div>

    <!-- MALETA 6 -->
    <div class="section">
      <div class="badge">Maleta 6 de 7</div>
      <h2>6 — Objeciones</h2>
      <p class="sub">¿Por qué no te compran hoy?</p>
      <div class="hl">
        <h4>Objeción principal: "{esc(obj_prin.get('objecion',''))}"</h4>
        <p>{esc(obj_prin.get('evidencia',''))}</p>
      </div>
      <div class="info-box warning">
        <p><strong>En web:</strong> {esc(m6.get("como_resolver",{}).get("en_web",""))}</p>
        <p><strong>En anuncios:</strong> {esc(m6.get("como_resolver",{}).get("en_anuncios",""))}</p>
        <p><strong>En ventas:</strong> {esc(m6.get("como_resolver",{}).get("en_ventas",""))}</p>
      </div>
    </div>

    <!-- MALETA 7 -->
    <div class="section">
      <div class="badge">Maleta 7 de 7</div>
      <h2>7 — Garantía</h2>
      <p class="sub">Elimina el riesgo percibido del cliente</p>
      <div class="info-box warning"><p><strong>Garantía actual detectada:</strong> {esc(m7.get("garantia_actual",""))}</p></div>
      <div class="hl"><h4>Garantía sugerida:</h4><p>{esc(m7.get("garantia_sugerida",""))}</p></div>
      <div class="info-box success"><p>{esc(m7.get("recomendacion",""))}</p></div>
    </div>

    <!-- IA INSIGHT -->
    {"<div class='section'><div class='badge'>Síntesis IA</div><h2>Mensaje Ganador (Claude)</h2><div style='background:#f5f5f7;padding:24px;border-radius:12px'>" + insight_html + "</div></div>" if insight and not insight.startswith("[") else ""}

    <!-- ADS -->
    <div class="section">
      <div class="badge">Campañas sugeridas</div>
      <h2>Ideas de Anuncios</h2>
      <p class="sub">3 estructuras basadas en las 7 Maletas de {esc(nombre)}</p>
      {ads_html}
    </div>

    <!-- PRÓXIMOS PASOS -->
    <div class="section">
      <div class="badge">Plan de acción</div>
      <h2>Próximos Pasos</h2>
      {pps_html}
      <h3 style="margin-top:24px">Este mes:</h3>
      <ul style="padding-left:20px">{"".join(f'<li style="margin:8px 0">{esc(s)}</li>' for s in pps.get("este_mes",[]))}</ul>
    </div>

    <!-- FACEBOOK ADS -->
    <div class="section">
      <div class="badge">Publicidad activa</div>
      <h2>Facebook Ads Library</h2>
      {fb_html}
    </div>

    <!-- ACADÉMICO -->
    <div class="section">
      <div class="badge">Respaldo académico</div>
      <h2>Fuentes Académicas</h2>
      {acad_html}
    </div>

  </div>

  <div class="footer">
    <p style="font-weight:600">Metodología: Las 7 Maletas de Cualquier Compra — Felipe Vergara</p>
    <p style="margin-top:6px;font-size:13px">IM System · intelligentmarkets.com.co · {fecha}</p>
    <div style="margin-top:20px;display:flex;gap:12px;justify-content:center;flex-wrap:wrap" class="no-print">
      <button onclick="window.print()" style="background:#1d1d1f;color:#fff;border:none;padding:12px 28px;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer">⬇ Descargar PDF</button>
      <button onclick="navigator.clipboard.writeText(document.body.innerText).then(()=>alert('Copiado al portapapeles'))" style="background:#f5f5f7;color:#1d1d1f;border:none;padding:12px 28px;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer">📋 Copiar texto</button>
    </div>
  </div>
</div>
<style>
@media print {{
  .no-print {{ display:none !important; }}
  body {{ -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
  .container {{ max-width:100%; padding:0; }}
  .section {{ break-inside:avoid; page-break-inside:avoid; }}
  .header {{ page-break-after:avoid; }}
  pre {{ white-space:pre-wrap !important; page-break-inside:avoid; }}
  @page {{ margin:15mm; size:A4; }}
}}
</style>
</body>
</html>"""

# ── API PÚBLICA ────────────────────────────────────────────────
def crear_job(nombre, url, instagram, ciudad, nicho, tamanio="mediana"):
    init_investigacion_tables()

    # Memoria: si ya investigamos este negocio en menos de 30 días, reusar
    try:
        sys.path.insert(0, str(BASE / "agent"))
        from session_memory import MemoriaAgentes
        cached = MemoriaAgentes().get_investigacion(nombre)
        if cached:
            print(f"[DeepResearcher] Cache hit — {nombre} investigado el {cached['fecha_investigacion'][:10]}")
            return cached["job_id"]
    except Exception:
        pass

    raw    = f"{nombre}-{ciudad}-{nicho}-{time.time()}"
    job_id = hashlib.md5(raw.encode()).hexdigest()[:12]
    conn   = get_db()
    conn.execute(
        "INSERT INTO investigacion_jobs (id,nombre,url,instagram,ciudad,nicho,tamanio,estado,progreso,modulo_actual,modulos_detalle,creado_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (job_id, nombre, url or "", instagram or "", ciudad, nicho, tamanio,
         "pendiente", 0, "Iniciando...",
         json.dumps({"web":0,"maps_negocio":0,"maps_competidores":0,"facebook_ads":0,"instagram":0,"academico":0,"dane":0,"analisis":0,"claude":0,"reporte":0}),
         datetime.now().isoformat())
    )
    conn.commit(); conn.close()
    t = threading.Thread(
        target=run_deep_investigation,
        args=(job_id, nombre, url, instagram, ciudad, nicho, tamanio),
        daemon=True
    )
    t.start()
    return job_id

def get_job_estado(job_id):
    conn = get_db()
    row  = conn.execute("SELECT id,nombre,nicho,ciudad,tamanio,estado,progreso,modulo_actual,modulos_detalle,creado_at,terminado_at FROM investigacion_jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    if not row: return None
    d = dict(row)
    try: d["modulos_detalle"] = json.loads(d.get("modulos_detalle") or "{}")
    except: d["modulos_detalle"] = {}
    return d

def get_job_reporte(job_id):
    conn = get_db()
    row  = conn.execute("SELECT * FROM investigacion_jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    if not row: return None
    d   = dict(row)
    raw = d.pop("resultado", None)
    try: d["modulos_detalle"] = json.loads(d.get("modulos_detalle") or "{}")
    except: d["modulos_detalle"] = {}
    if raw:
        try:    d["resultado"] = json.loads(raw)
        except: d["resultado"] = None
    return d

def lista_jobs(limit=20):
    init_investigacion_tables()
    conn = get_db()
    rows = conn.execute(
        "SELECT id,nombre,nicho,ciudad,tamanio,estado,progreso,modulo_actual,creado_at,terminado_at FROM investigacion_jobs ORDER BY creado_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def guardar_proyecto(nombre, nicho, ciudad, url="", instagram="", tamanio="mediana",
                     job_id="", branding_path="", proyecto_id=None):
    init_investigacion_tables()
    conn = get_db()
    if proyecto_id:
        # UPDATE existing project (e.g. upload branding)
        sets, vals = [], []
        if branding_path:
            sets.append("branding_path=?"); vals.append(branding_path)
        if job_id:
            sets.append("ultimo_job_id=?"); vals.append(job_id)
        if sets:
            vals.append(proyecto_id)
            conn.execute(f"UPDATE proyectos SET {', '.join(sets)} WHERE id=?", vals)
    else:
        conn.execute(
            "INSERT INTO proyectos (nombre,nicho,ciudad,url,instagram,tamanio,"
            "ultimo_job_id,branding_path,creado_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (nombre, nicho, ciudad, url, instagram, tamanio,
             job_id, branding_path, datetime.now().isoformat())
        )
    conn.commit(); conn.close()

def lista_proyectos():
    init_investigacion_tables()
    conn = get_db()
    rows = conn.execute("SELECT * FROM proyectos ORDER BY creado_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]
