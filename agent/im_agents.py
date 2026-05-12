#!/usr/bin/env python3
"""
IM Agents v3 — Intelligent Markets
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Mateo Galvis  → Intelligent Markets (empresas)
José Galvis   → IM Music (sello / artistas)

Flujo:
  1. Investigación profunda (web + redes + ads + contenido + mejoras)
  2. Informe pre-reunión completo
  3. Copy humanizado sin venta directa
  4. Ciclo de ventas por vertical
  5. Envío + log
"""

import os, json, time, random, csv, smtplib, argparse, re, sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from datetime import datetime
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from urllib.parse import urljoin, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
    NET = True
except ImportError:
    NET = False

# ── Lead Investigator (7 Maletas del Prospecto) ────────────────
try:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent))
    import lead_investigator as _lead_inv
    _INV_OK = True
except Exception:
    _INV_OK = False

# ── Cargar .env si existe ──────────────────────────────────────
def _load_env():
    env = Path(__file__).parent.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if k.strip() and not os.environ.get(k.strip()):
                    os.environ[k.strip()] = v.strip()
_load_env()

# ════════════════════════════════════════════════════════════════
# AGENTES
# ════════════════════════════════════════════════════════════════

AGENTES = {

    "mateo": {
        "nombre_completo": "Mateo Galvis",
        "nombre":          "Mateo",
        "rol":             "Gerente de Marketing",
        "empresa":         "Intelligent Markets",
        "firma":           "Mateo Galvis\nGerente de Marketing — Intelligent Markets",
        "email":           os.environ.get("IM_EMAIL", "intelligentsmarkets@gmail.com"),
        "vertical":        "empresas",
        "cal_link":        os.environ.get("CAL_EMPRESAS", "https://cal.com/intelligent-markets-agencia/30min"),
        "brochure":        "brochures/deck_im_empresas.pdf",

        "personalidad": """
Eres Mateo Galvis, Gerente de Marketing de Intelligent Markets. Medellín, Colombia.
Intelligent Markets es una agencia de marketing que aplica neurociencia y psicología del
consumidor para generar resultados reales — más clientes, más ventas, de forma medible.

CÓMO TE PRESENTAS:
- Tu nombre es Mateo Galvis. Firmas como "Mateo Galvis — Intelligent Markets".
- En el primer email no explicas todos los servicios. Solo conectas con algo relevante para ellos.
- Si preguntan qué es IM: "Somos una agencia de marketing en Medellín. Usamos neurociencia del
  consumidor y publicidad digital para conseguir más clientes de forma predecible. Trabajamos con
  clínicas de salud, agencias de viajes, seguros y más."

VOZ Y TONO:
- Directo, cercano, profesional sin ser rígido.
- Colombiano auténtico. Como habla un profesional serio pero accesible.
- Frases cortas. Sin rodeos. Sin jerga de agencia.
- Demuestras que investigaste a la persona antes de escribir.
- Una sola pregunta al final que invite a conversar, no a comprar.
- Máximo 130 palabras en el primer email.

PROHIBIDO:
- "potenciar", "escalar", "sinergia", "360°", "KPI", "ROI" en el primer email
- "agenda una llamada sin compromiso"
- "somos la agencia perfecta"
- Más de un CTA
- Sonar como plantilla corporativa
""",

        # CICLO DE VENTAS — EMPRESAS
        "ciclo_ventas": {
            "etapas": ["Atracción", "Presentación", "Evaluación", "Conversión", "Ascensión"],
            "descripcion": {
                "Atracción":    "Primera impresión. Generar curiosidad sin vender. El prospecto no sabe quién eres aún.",
                "Presentación": "Ya hay conexión. Presentar IM con evidencia real. Mostrar que entiendes su negocio.",
                "Evaluación":   "Están comparando. Mostrar diferenciadores. Manejar objeciones con neurociencia.",
                "Conversión":   "Listos para decidir. Eliminar fricción. Hacer el proceso de cierre fácil.",
                "Ascensión":    "Ya son clientes. Aumentar valor. Referidos. Servicios adicionales.",
            },
            "mensaje_por_etapa": {
                "Atracción":    "tipo_1",  # primer contacto
                "Presentación": "tipo_2",  # follow-up con más contexto
                "Evaluación":   "tipo_3",  # respuesta a interés + objeciones
                "Conversión":   "tipo_4",  # cierre
                "Ascensión":    "tipo_5",  # expansión
            },
        },
    },

    "jose": {
        "nombre_completo": "José Galvis",
        "nombre":          "José",
        "rol":             "Director — IM Music",
        "empresa":         "IM Music | Intelligent Markets",
        "firma":           "José Galvis\nDirector — IM Music | Intelligent Markets",
        "email":           os.environ.get("IM_EMAIL", "intelligentsmarkets@gmail.com"),
        "vertical":        "music",
        "cal_link":        os.environ.get("CAL_MUSIC", "https://cal.com/intelligent-markets-agencia/sello-30min"),
        "brochure":        "brochures/im_music_2026.pdf",

        "personalidad": """
Eres José Galvis, Director de IM Music — el sello y agencia musical de Intelligent Markets.
Medellín, Colombia. IM Music trabaja con artistas independientes, sellos y managers en
Colombia, México, España, Puerto Rico y República Dominicana.

CÓMO TE PRESENTAS:
- Tu nombre es José Galvis. Firmas como "José Galvis — IM Music | Intelligent Markets".
- IM Music: sello + agencia que usa neurociencia del consumidor aplicada a la industria musical.
- En el primer email no hablas de todos los servicios. Hablas desde el sector.
- Si preguntan qué es IM Music: "Es el sello y agencia de Intelligent Markets. Trabajamos con
  artistas y sellos independientes aplicando estrategia real — no solo publicidad. Desde Medellín
  con presencia en Colombia, México, España, Puerto Rico y República Dominicana."

VOZ Y TONO:
- Hablas desde adentro de la industria. No como agencia externa.
- Vocabulario real del sector: streams, DSPs, fanbase, booking, master, publishing, lanzamiento.
- Muy conciso. WhatsApp energy. Máximo 120 palabras en primer contacto.
- Demuestras que conoces su música o su trabajo específico.
- Una pregunta genuina al final.

PROHIBIDO:
- "maximizar tus streams"
- "llevar tu carrera al siguiente nivel"
- Hablar de precios o servicios en el primer email
- Sonar como agencia de marketing genérica
- Más de 130 palabras en el primer contacto
""",

        # CICLO DE VENTAS — MÚSICA
        "ciclo_ventas": {
            "etapas": ["Atracción", "Presentación", "Evaluación", "Validación", "Conversión", "Ascensión"],
            "descripcion": {
                "Atracción":    "Primer contacto desde el sector. Demostrar que conoces su trabajo.",
                "Presentación": "Presentar IM Music con casos reales. Mostrar que entiendes la industria.",
                "Evaluación":   "Están analizando. Mostrar diferenciadores vs otras agencias/sellos.",
                "Validación":   "Necesitan prueba social. Testimonios, resultados, artistas que confían en IM.",
                "Conversión":   "Listos para firmar. Propuesta clara. Sin presión.",
                "Ascensión":    "Ya son clientes. Más servicios. Colaboraciones. Referidos en la industria.",
            },
            "mensaje_por_etapa": {
                "Atracción":    "tipo_1",
                "Presentación": "tipo_2",
                "Evaluación":   "tipo_3",
                "Validación":   "tipo_4",
                "Conversión":   "tipo_5",
                "Ascensión":    "tipo_6",
            },
        },
    },
}

# ════════════════════════════════════════════════════════════════
# INVESTIGACIÓN PROFUNDA (el corazón del sistema)
# ════════════════════════════════════════════════════════════════

HEADERS = [
    {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36", "Accept-Language": "es-CO,es;q=0.9"},
    {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36", "Accept-Language": "es-MX,es;q=0.9"},
    {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/118.0.0.0 Safari/537.36"},
]

def fetch(url, timeout=12):
    if not NET: return None
    try:
        r = requests.get(url, headers=random.choice(HEADERS), timeout=timeout, allow_redirects=True)
        return r.text if r.status_code == 200 else None
    except: return None

def find_social_links(soup, base_url=""):
    """Extrae todos los links a redes sociales de una página"""
    socials = {}
    patterns = {
        "instagram": r"instagram\.com/([A-Za-z0-9._]+)",
        "facebook":  r"facebook\.com/([A-Za-z0-9./_-]+)",
        "tiktok":    r"tiktok\.com/@([A-Za-z0-9._]+)",
        "youtube":   r"youtube\.com/(?:channel/|@|c/)([A-Za-z0-9._-]+)",
        "linkedin":  r"linkedin\.com/(?:in|company)/([A-Za-z0-9._-]+)",
        "twitter":   r"(?:twitter|x)\.com/([A-Za-z0-9._]+)",
        "spotify":   r"open\.spotify\.com/artist/([A-Za-z0-9]+)",
        "whatsapp":  r"(?:wa\.me|whatsapp\.com)/([0-9+]+)",
    }
    page_text = str(soup)
    for net, pattern in patterns.items():
        match = re.search(pattern, page_text, re.IGNORECASE)
        if match:
            full_match = re.search(r'https?://[^\s"\'<>]*' + net.replace("twitter", "(?:twitter|x)") + r'[^\s"\'<>]*', page_text, re.IGNORECASE)
            socials[net] = full_match.group(0).rstrip("/?") if full_match else f"@{match.group(1)}"
    return socials

def analyze_web_content(html, url=""):
    """Análisis profundo del contenido web"""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "head"]): tag.decompose()

    text = soup.get_text(separator=" ", strip=True)

    # Estructura
    h1s = [h.get_text(strip=True) for h in soup.find_all("h1")][:5]
    h2s = [h.get_text(strip=True) for h in soup.find_all("h2")][:8]
    h3s = [h.get_text(strip=True) for h in soup.find_all("h3")][:5]

    # Servicios / productos
    services = []
    for tag in soup.find_all(["li", "p", "div"], class_=re.compile(r"service|producto|servicio|ofert|precio", re.I)):
        t = tag.get_text(strip=True)
        if 10 < len(t) < 200: services.append(t)

    # CTAs y botones
    ctas = [b.get_text(strip=True) for b in soup.find_all(["button", "a"], class_=re.compile(r"btn|cta|button", re.I)) if b.get_text(strip=True)][:10]

    # Testimonios
    testimonios = []
    for tag in soup.find_all(attrs={"class": re.compile(r"testim|review|opini|comment", re.I)}):
        t = tag.get_text(strip=True)
        if 20 < len(t) < 300: testimonios.append(t[:200])

    # Imágenes (alt text)
    img_alts = [img.get("alt", "") for img in soup.find_all("img") if img.get("alt")][:10]

    # Blog / artículos
    blog_posts = []
    for tag in soup.find_all(["article", "div"], class_=re.compile(r"post|blog|article|news", re.I)):
        title = tag.find(["h1", "h2", "h3"])
        if title: blog_posts.append(title.get_text(strip=True))
    blog_posts = blog_posts[:5]

    # Contacto
    emails = list(set(re.findall(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b', text)))
    phones = list(set(re.findall(r'(?:\+?57|\+?52|\+?34)?[\s\-]?\d[\d\s\-]{6,12}', text)))[:3]

    # Redes sociales
    socials = find_social_links(soup, url)

    # Pixel / analytics / ads
    ads_signals = {
        "facebook_pixel": bool(re.search(r'fbq\(|facebook\.net/en_US/fbevents|connect\.facebook\.net', html, re.I)),
        "google_ads":     bool(re.search(r'googletagmanager|gtag\(|google-analytics|UA-|G-[A-Z0-9]', html, re.I)),
        "tiktok_pixel":   bool(re.search(r'tiktok|ttq\.|analytics\.tiktok', html, re.I)),
        "hotjar":         bool(re.search(r'hotjar|hjSiteSettings', html, re.I)),
        "hubspot":        bool(re.search(r'hubspot|hs-analytics', html, re.I)),
        "meta_ads":       bool(re.search(r'fbads|facebook.*ads|meta.*pixel', html, re.I)),
    }

    # Tecnología del sitio
    tech = {
        "wordpress":  bool(re.search(r'wp-content|wp-includes|wordpress', html, re.I)),
        "wix":        bool(re.search(r'wix\.com|wixsite', html, re.I)),
        "shopify":    bool(re.search(r'shopify|myshopify', html, re.I)),
        "webflow":    bool(re.search(r'webflow', html, re.I)),
        "squarespace":bool(re.search(r'squarespace', html, re.I)),
    }
    plataforma = next((k for k, v in tech.items() if v), "personalizado/desconocido")

    # Velocidad visual (básico)
    img_count = len(soup.find_all("img"))
    video_count = len(soup.find_all(["video", "iframe"]))

    return {
        "titulo": soup.title.string.strip() if soup.title else "",
        "h1": h1s,
        "h2": h2s,
        "h3": h3s,
        "servicios_detectados": services[:8],
        "ctas": ctas,
        "testimonios": testimonios[:4],
        "imagenes_alt": img_alts,
        "blog_posts": blog_posts,
        "emails": emails[:5],
        "telefonos": phones,
        "redes_sociales": socials,
        "ads_signals": ads_signals,
        "plataforma_web": plataforma,
        "num_imagenes": img_count,
        "num_videos": video_count,
        "tiene_blog": len(blog_posts) > 0,
        "texto_muestra": text[:2000],
    }

def scrape_social_profile(url, red):
    """Intenta obtener métricas básicas de un perfil social"""
    if not url or not NET: return {}
    html = fetch(url)
    if not html: return {}
    soup = BeautifulSoup(html, "html.parser")
    data = {"url": url, "red": red}

    if red == "instagram":
        # Buscar datos en meta tags
        for meta in soup.find_all("meta"):
            content = meta.get("content", "")
            name = meta.get("name", meta.get("property", ""))
            if "description" in name.lower() and content:
                data["descripcion"] = content[:200]
            if "title" in name.lower() and content:
                data["titulo"] = content[:100]
        # Buscar seguidores en el texto
        text = soup.get_text()
        followers = re.search(r'([\d,.KMk]+)\s*(?:seguidores|followers)', text, re.I)
        if followers: data["seguidores"] = followers.group(1)

    elif red == "facebook":
        for meta in soup.find_all("meta"):
            content = meta.get("content", "")
            name = meta.get("property", meta.get("name", ""))
            if "description" in name: data["descripcion"] = content[:200]
            if "title" in name: data["titulo"] = content[:100]

    # Posts recientes (texto)
    posts = []
    for tag in soup.find_all(["article", "div"], class_=re.compile(r"post|content|feed", re.I))[:3]:
        t = tag.get_text(strip=True)
        if 20 < len(t) < 300: posts.append(t[:200])
    if posts: data["posts_recientes"] = posts

    return data

def check_facebook_ads(empresa):
    """Busca anuncios activos en Facebook Ads Library"""
    if not NET: return {}
    try:
        # Búsqueda en la biblioteca de anuncios
        search_url = f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=CO&q={requests.utils.quote(empresa)}&search_type=keyword_unordered"
        html = fetch(search_url)
        if not html: return {"tiene_ads": False, "nota": "No se pudo acceder"}

        tiene_ads = bool(re.search(r'result|ad-card|_7pfu|ad_creative', html, re.I))
        num_ads = len(re.findall(r'ad.card|result.item', html, re.I))
        return {
            "tiene_ads_activos": tiene_ads,
            "estimado_anuncios": num_ads if tiene_ads else 0,
            "url_biblioteca": search_url,
        }
    except: return {"tiene_ads": False}

def google_search_empresa(empresa, ciudad, nicho):
    """Busca menciones y reseñas de la empresa en Google"""
    if not NET: return {}
    results = {}
    try:
        q = f'"{empresa}" {ciudad} reseñas OR reviews OR opiniones'
        html = fetch(f"https://www.google.com/search?q={requests.utils.quote(q)}&num=5")
        if html:
            soup = BeautifulSoup(html, "html.parser")
            snippets = [d.get_text(strip=True) for d in soup.select("div.VwiC3b, div.s3v9rd")][:5]
            results["menciones_google"] = snippets
            # Buscar rating
            rating = re.search(r'(\d+[.,]\d+)\s*(?:★|estrellas|stars|de 5)', " ".join(snippets))
            if rating: results["rating_encontrado"] = rating.group(1)
    except: pass
    return results

def investigacion_profunda(lead: dict) -> dict:
    """
    Investigación completa del prospecto:
    - Web: estructura, contenido, tecnología, CTA, testimonios
    - Redes sociales: presencia, contenido, engagement
    - Ads: si tienen campañas activas (Facebook Ads Library)
    - Menciones en Google
    - Puntos de mejora detectados
    - Contexto para la reunión
    """
    empresa  = lead.get("empresa", "")
    nombre   = lead.get("nombre", "")
    nicho    = lead.get("nicho", "")
    ciudad   = lead.get("ciudad", "")
    url      = lead.get("url", "").strip()
    instagram= lead.get("instagram", "").strip()

    informe = {
        "empresa": empresa,
        "nombre": nombre,
        "nicho": nicho,
        "ciudad": ciudad,
        "fecha_investigacion": datetime.now().isoformat(),
        "web": {},
        "redes_sociales": {},
        "ads": {},
        "menciones": {},
        "puntos_mejora": [],
        "oportunidades_im": [],
        "contexto_reunion": {},
        "resumen_ejecutivo": "",
    }

    # ── 1. ANÁLISIS WEB ──────────────────────────────────────────
    if url and url.startswith("http"):
        print(f"      🌐 Analizando web: {url[:50]}...")
        html = fetch(url)
        if html:
            web_data = analyze_web_content(html, url)
            informe["web"] = web_data

            # Detectar redes desde la web si no venían en el CSV
            for red, link in web_data["redes_sociales"].items():
                if red not in informe["redes_sociales"]:
                    informe["redes_sociales"][red] = {"url": link}

            # ── Detectar puntos de mejora ────────────────────────
            mejoras = []

            if not web_data["ads_signals"]["facebook_pixel"]:
                mejoras.append({
                    "area": "Tracking",
                    "problema": "Sin Facebook Pixel instalado",
                    "impacto": "No pueden hacer remarketing ni medir conversiones de Meta Ads",
                    "solucion_im": "Instalación de píxeles y configuración de eventos de conversión",
                })
            if not web_data["ads_signals"]["google_ads"]:
                mejoras.append({
                    "area": "Analytics",
                    "problema": "Sin Google Tag Manager / Analytics detectado",
                    "impacto": "Sin medición del tráfico web ni origen de visitas",
                    "solucion_im": "Setup de GTM + GA4 + conversiones",
                })
            if not web_data["redes_sociales"].get("instagram"):
                mejoras.append({
                    "area": "Redes Sociales",
                    "problema": "Sin Instagram enlazado desde la web",
                    "impacto": "Pierden tráfico cruzado entre canales",
                    "solucion_im": "Estrategia de integración digital omnicanal",
                })
            if not web_data["testimonios"]:
                mejoras.append({
                    "area": "Prueba Social",
                    "problema": "Sin testimonios visibles en el sitio",
                    "impacto": "Baja conversión — los visitantes no ven evidencia de resultados",
                    "solucion_im": "Sección de casos de éxito y testimonios con neurociencia de prueba social",
                })
            if not web_data["tiene_blog"]:
                mejoras.append({
                    "area": "Contenido / SEO",
                    "problema": "Sin blog o contenido educativo",
                    "impacto": "Baja visibilidad orgánica en Google",
                    "solucion_im": "Estrategia de contenido + SEO para el nicho",
                })
            if not web_data["ctas"]:
                mejoras.append({
                    "area": "Conversión",
                    "problema": "Sin llamados a la acción (CTA) claros detectados",
                    "impacto": "Los visitantes no saben qué hacer — se van sin convertir",
                    "solucion_im": "Optimización de CTA + embudo de conversión con psicología persuasiva",
                })
            if web_data["plataforma_web"] in ["wix", "wordpress"]:
                mejoras.append({
                    "area": "Tecnología Web",
                    "problema": f"Sitio en {web_data['plataforma_web'].capitalize()} — posiblemente lento",
                    "impacto": "Velocidad afecta SEO y tasa de rebote",
                    "solucion_im": "Auditoría de velocidad + optimización técnica",
                })

            informe["puntos_mejora"] = mejoras

    # ── 2. REDES SOCIALES ────────────────────────────────────────
    redes_a_revisar = {}
    if instagram: redes_a_revisar["instagram"] = instagram
    for red, data in informe["redes_sociales"].items():
        link = data.get("url", "") if isinstance(data, dict) else data
        if link and link.startswith("http"):
            redes_a_revisar[red] = link

    for red, link in redes_a_revisar.items():
        print(f"      📱 Revisando {red}: {link[:50]}...")
        social_data = scrape_social_profile(link, red)
        informe["redes_sociales"][red] = social_data
        time.sleep(random.uniform(1, 2))

    # Evaluar presencia en redes
    redes_presentes = list(informe["redes_sociales"].keys())
    if not redes_presentes:
        informe["puntos_mejora"].append({
            "area": "Redes Sociales",
            "problema": "Sin presencia detectada en redes sociales",
            "impacto": "Perdiendo audiencia digital completamente",
            "solucion_im": "Estrategia de presencia en redes + contenido viral",
        })
    elif len(redes_presentes) < 2:
        informe["puntos_mejora"].append({
            "area": "Redes Sociales",
            "problema": f"Presencia solo en {redes_presentes[0]} — muy limitada",
            "impacto": "No están donde están todos sus clientes potenciales",
            "solucion_im": "Expansión de presencia digital multicanal",
        })

    # ── 3. ADS ACTIVOS ───────────────────────────────────────────
    if empresa:
        print(f"      📢 Verificando ads activos...")
        ads_data = check_facebook_ads(empresa)
        informe["ads"] = ads_data
        if not ads_data.get("tiene_ads_activos"):
            informe["puntos_mejora"].append({
                "area": "Publicidad Pagada",
                "problema": "Sin campañas de paid media activas detectadas",
                "impacto": "Dependen 100% del orgánico — crecimiento muy limitado",
                "solucion_im": "Campañas de Meta Ads + Google Ads con segmentación de neurociencia",
            })

    # ── 4. MENCIONES GOOGLE ──────────────────────────────────────
    if empresa and ciudad:
        print(f"      🔍 Buscando menciones en Google...")
        menciones = google_search_empresa(empresa, ciudad, nicho)
        informe["menciones"] = menciones

    # ── 5. OPORTUNIDADES PARA IM ─────────────────────────────────
    oportunidades = []
    mejoras_areas = [m["area"] for m in informe["puntos_mejora"]]

    if "Publicidad Pagada" in mejoras_areas:
        oportunidades.append("Campañas de Meta Ads + Google Ads — están dejando dinero sobre la mesa")
    if "Prueba Social" in mejoras_areas:
        oportunidades.append("Estrategia de testimonios y casos de éxito con neurociencia de prueba social")
    if "Contenido / SEO" in mejoras_areas:
        oportunidades.append("Plan de contenido + SEO para posicionamiento orgánico en el nicho")
    if "Tracking" in mejoras_areas:
        oportunidades.append("Setup completo de tracking — no pueden medir lo que no se puede medir")
    if "Redes Sociales" in mejoras_areas:
        oportunidades.append("Estrategia de redes sociales con contenido viral basado en psicología")

    # Oportunidades basadas en nicho
    nicho_oportunidades = {
        "odontologos": "Campañas de captación de pacientes segmentadas por tipo de tratamiento y NSE",
        "dermatologo":  "Contenido educativo + ads para procedimientos cosméticos de alto ticket",
        "psicologo":    "Estrategia de visibilidad digital sensible al sector — sin estigmatizar",
        "agencia_viajes": "Captación de viajeros premium con ads de alta segmentación",
        "seguros":      "Lead generation cualificado con funnel de nurturing automático",
        "autos_alta_gama": "Branding de exclusividad + captación de compradores de alto NSE",
        "sello_musical": "Visibilización de catálogo + estrategia de playlisting y DSPs",
        "artista_independiente": "Construcción de fanbase real con estrategia de contenido + ads",
        "manager_musical": "Posicionamiento de artistas con métricas que importen al booking",
    }
    if nicho in nicho_oportunidades:
        oportunidades.insert(0, nicho_oportunidades[nicho])

    informe["oportunidades_im"] = oportunidades[:5]

    # ── 6. CONTEXTO PARA LA REUNIÓN ──────────────────────────────
    web_info = informe.get("web", {})
    informe["contexto_reunion"] = {
        "etapa_ciclo_venta": detectar_etapa_ciclo(lead),
        "dolor_principal":   inferir_dolor_principal(informe, nicho),
        "argumento_apertura": generar_argumento_apertura(informe, nicho, empresa, nombre),
        "preguntas_clave": generar_preguntas_clave(nicho, informe),
        "objeciones_esperadas": objeciones_por_nicho(nicho),
        "propuesta_valor_personalizada": generar_propuesta_valor(informe, nicho),
    }

    # ── 7. RESUMEN EJECUTIVO ─────────────────────────────────────
    num_mejoras = len(informe["puntos_mejora"])
    tiene_web = bool(web_info)
    tiene_redes = len(informe["redes_sociales"]) > 0
    tiene_ads = informe["ads"].get("tiene_ads_activos", False)

    informe["resumen_ejecutivo"] = f"""
PROSPECTO: {empresa} | {nombre} | {nicho} | {ciudad}
─────────────────────────────────────────────────
WEB:    {"✅ Sí" if tiene_web else "❌ No detectada"} | Plataforma: {web_info.get("plataforma_web","—")}
REDES:  {"✅ " + ", ".join(informe["redes_sociales"].keys()) if tiene_redes else "❌ Sin presencia detectada"}
ADS:    {"✅ Campañas activas" if tiene_ads else "❌ Sin campañas activas"}
PIXEL:  {"✅ Instalado" if web_info.get("ads_signals",{}).get("facebook_pixel") else "❌ Sin pixel"}
BLOG:   {"✅ Sí" if web_info.get("tiene_blog") else "❌ No"}
─────────────────────────────────────────────────
PUNTOS DE MEJORA DETECTADOS: {num_mejoras}
OPORTUNIDADES PARA IM: {len(informe["oportunidades_im"])}
─────────────────────────────────────────────────
ETAPA EN EL CICLO: {informe["contexto_reunion"]["etapa_ciclo_venta"]}
""".strip()

    return informe


def detectar_etapa_ciclo(lead: dict) -> str:
    status = lead.get("status", "pendiente").lower()
    mapa = {
        "pendiente": "Atracción",
        "enviado": "Atracción",
        "abierto": "Presentación",
        "respondio": "Evaluación",
        "reunion": "Conversión",
        "cliente": "Ascensión",
    }
    return mapa.get(status, "Atracción")

def inferir_dolor_principal(informe: dict, nicho: str) -> str:
    mejoras = [m["problema"] for m in informe.get("puntos_mejora", [])]
    dolores_nicho = {
        "odontologos": "Agenda vacía — dependencia total del voz a voz",
        "dermatologo":  "Competencia de spas y estética no médica que les quita pacientes",
        "psicologo":    "Dificultad para conseguir pacientes nuevos de forma consistente",
        "agencia_viajes": "Competencia de OTAs (Booking, Airbnb) que les quita las reservas",
        "seguros":      "Leads de baja calidad — mucho esfuerzo, pocas conversiones",
        "autos_alta_gama": "Ciclos de compra largos — difícil capturar al comprador en el momento correcto",
        "sello_musical": "Poca visibilidad del catálogo fuera del círculo conocido",
        "artista_independiente": "Buena música que no llega a quien debería escucharla",
        "manager_musical": "Artistas con talento pero sin métricas que convenzan al booking",
    }
    base = dolores_nicho.get(nicho, "Falta de presencia digital estructurada")
    if mejoras:
        base += f". También: {mejoras[0].lower()}"
    return base

def generar_argumento_apertura(informe, nicho, empresa, nombre):
    web = informe.get("web", {})
    mejoras = informe.get("puntos_mejora", [])
    ads = informe.get("ads", {})

    if not ads.get("tiene_ads_activos") and mejoras:
        return f"Revisé {empresa} y vi que no están corriendo campañas de paid media — están dejando pacientes/clientes que buscan activamente sin poder llegar a ellos."
    if web and not web.get("ads_signals", {}).get("facebook_pixel"):
        return f"Revisé el sitio de {empresa} — no tienen el pixel instalado, lo que significa que no pueden retargear a nadie que los haya visitado."
    if not informe.get("redes_sociales"):
        return f"Busqué {empresa} en redes sociales y la presencia digital es muy limitada para lo que están haciendo."
    return f"Revisé {empresa} antes de escribirte y hay algunas cosas que creo que podríamos mejorar juntos."

def generar_preguntas_clave(nicho: str, informe: dict) -> list:
    preguntas_base = {
        "odontologos": [
            "¿Cómo está viniendo la mayoría de sus pacientes nuevos hoy?",
            "¿Han intentado publicidad digital antes? ¿Qué pasó?",
            "¿Cuál es el tratamiento de mayor ticket que más quieren mover?",
            "¿Cuántos pacientes nuevos necesitarían al mes para sentirse bien?",
        ],
        "dermatologo": [
            "¿Qué procedimientos cosméticos quieren posicionar más?",
            "¿Cómo diferencias la clínica de los centros de estética no médicos?",
            "¿Han tenido experiencias con publicidad digital antes?",
        ],
        "agencia_viajes": [
            "¿Qué porcentaje de sus reservas vienen directo vs por OTAs?",
            "¿Cuál es su destino o paquete estrella?",
            "¿A qué perfil de viajero quieren apuntar?",
        ],
        "seguros": [
            "¿Qué tipo de seguro mueve más volumen en su portafolio?",
            "¿Cómo están generando leads ahora mismo?",
            "¿Cuánto tiempo tarda en promedio un lead en convertirse?",
        ],
        "sello_musical": [
            "¿Cuántos artistas tiene el catálogo activo?",
            "¿Cuál es el mayor reto de visibilización que tienen ahora?",
            "¿Están distribuyendo en todas las plataformas de streaming?",
        ],
        "artista_independiente": [
            "¿Cuándo es tu próximo lanzamiento?",
            "¿Tienes claro quién es tu oyente ideal?",
            "¿Estás trabajando la presencia en DSPs de forma estratégica?",
        ],
    }
    base = preguntas_base.get(nicho, [
        "¿Cómo están llegando sus clientes actuales?",
        "¿Han probado publicidad digital antes?",
        "¿Cuál es su mayor reto de crecimiento hoy?",
    ])

    # Agregar preguntas basadas en lo encontrado
    if not informe.get("ads", {}).get("tiene_ads_activos"):
        base.append("¿Han pensado en publicidad digital pero no han dado el paso? ¿Qué los ha frenado?")
    return base[:5]

def objeciones_por_nicho(nicho: str) -> list:
    objeciones = {
        "odontologos": [
            ("Ya tenemos suficientes pacientes", "Perfecto. ¿Y si pudieran elegir qué tipo de pacientes y tratamientos reciben?"),
            ("Ya probé publicidad y no funcionó", "Cuéntame qué hicieron — casi siempre es un problema de segmentación o de embudo, no de la publicidad en sí."),
            ("Es muy caro", "Depende de cuánto vale para ustedes un paciente de implantes. Generalmente un solo caso paga la campaña del mes."),
        ],
        "agencia_viajes": [
            ("Booking nos trae suficiente volumen", "Sí, pero a qué costo — las comisiones de las OTAs son enormes. ¿Cuánto sería diferente con reservas directas?"),
            ("Ya tenemos redes sociales", "Tener redes no es lo mismo que tener una estrategia. ¿Cuántas reservas generan directamente las redes hoy?"),
        ],
        "seguros": [
            ("Ya tenemos equipo comercial", "El equipo comercial es mejor cuando tiene leads cualificados. ¿Cuánto tiempo pierden en prospectos que no van a comprar?"),
            ("El sector no funciona en digital", "Cada vez más personas investigan seguros online antes de comprar. ¿Están ahí cuando los buscan?"),
        ],
        "sello_musical": [
            ("Tenemos presupuesto limitado", "Entiendo. ¿Cuál sería el ROI si uno de sus artistas pega en una playlist editorial?"),
            ("Ya trabajamos con otra agencia", "¿Qué tan medibles son los resultados de lo que hacen? ¿Tienen reportes claros?"),
        ],
    }
    return objeciones.get(nicho, [
        ("No tenemos presupuesto ahora", "¿Qué necesitaría pasar para que el presupuesto estuviera disponible?"),
        ("Necesito pensarlo", "Por supuesto. ¿Qué información adicional necesitarías para tomar la decisión?"),
    ])

def generar_propuesta_valor(informe: dict, nicho: str) -> str:
    mejoras = informe.get("puntos_mejora", [])
    opor = informe.get("oportunidades_im", [])

    base = {
        "odontologos": "Conseguir pacientes nuevos de manera predecible — sin depender del voz a voz ni de referencias",
        "dermatologo": "Llenar la agenda con pacientes de procedimientos cosméticos de alto ticket",
        "psicologo":   "Conseguir consultas nuevas de forma consistente reduciendo el estigma como barrera",
        "agencia_viajes": "Aumentar reservas directas reduciendo dependencia de OTAs",
        "seguros":     "Generar leads de seguros cualificados con intención real de compra",
        "sello_musical": "Visibilizar el catálogo y construir audiencias reales en todas las plataformas",
        "artista_independiente": "Construir fanbase real y llegar al oyente correcto con estrategia, no solo con dinero",
    }.get(nicho, "Crecer de forma medible y predecible con marketing basado en neurociencia")

    if len(mejoras) >= 2:
        base += f". Además, detectamos {len(mejoras)} áreas de mejora inmediata en su presencia digital actual."
    return base


# ════════════════════════════════════════════════════════════════
# GENERADOR DE COPY HUMANIZADO CON CLAUDE
# ════════════════════════════════════════════════════════════════

def generar_copy(agente_key: str, lead: dict, informe: dict, tipo: int,
                 investigacion_7m: dict = None) -> dict:
    """Genera el email personalizado usando Claude + investigación base + 7 Maletas."""
    agente = AGENTES[agente_key]
    nombre  = lead.get("nombre", "")
    empresa = lead.get("empresa", "")
    ciudad  = lead.get("ciudad", "")
    nicho   = lead.get("nicho", "")
    vertical = agente.get("vertical", "empresas")

    ctx_reunion = informe.get("contexto_reunion", {})
    argumento   = ctx_reunion.get("argumento_apertura", "")
    dolor       = ctx_reunion.get("dolor_principal", "")
    web         = informe.get("web", {})
    ads         = informe.get("ads", {})
    mejoras     = informe.get("puntos_mejora", [])

    tipos_desc = {
        1: "PRIMER CONTACTO — objetivo: generar curiosidad y una respuesta. No vender nada todavía.",
        2: "FOLLOW-UP (sin respuesta en 5 días) — ángulo completamente diferente al primer email.",
        3: "RESPONDIÓ CON INTERÉS — ya se puede hablar más de IM, mostrar evidencia, proponer reunión.",
        4: "PRE-REUNIÓN — confirmación de reunión + resumen de lo que se va a hablar.",
        5: "POST-REUNIÓN — seguimiento después de la llamada con la propuesta.",
    }

    # ── Bloque de 7 Maletas (si está disponible) ─────────────────
    bloque_7m = ""
    if investigacion_7m:
        if _INV_OK:
            resumen_7m = _lead_inv.formatear_resumen(investigacion_7m)
        else:
            resumen_7m = investigacion_7m.get("resumen_investigacion", "")
        m7 = investigacion_7m.get("maleta_7_angulo", {})
        angulo_sugerido = m7.get("primera_linea", "")
        asunto_sugerido = m7.get("asunto_sugerido", "")
        bloque_7m = f"""
INVESTIGACIÓN PROFUNDA — 7 MALETAS DEL PROSPECTO:
{resumen_7m}

ÁNGULO SUGERIDO POR LA INVESTIGACIÓN:
- Primera línea sugerida: "{angulo_sugerido}"
- Asunto sugerido: "{asunto_sugerido}"
(Puedes usarlos tal cual o adaptarlos — siempre que sean más específicos y naturales)
"""

    # ── Bloque de estructura para tipo 1 ─────────────────────────
    cal_link = agente["cal_link"]

    if vertical == "music":
        estructura_tipo1 = f"""
ESTRUCTURA OBLIGATORIA TIPO 1 (primer contacto — música):
Línea 1: Observación real y específica del artista/sello — algo concreto de su música, su mercado o su presencia. NO menciones la web si no fue verificada.
Línea 2: Dato o insight del mercado musical que demuestra que entiendes el sector mejor que ellos mismos (DSPs, algoritmos, fanbase, distribución).
Línea 3: Resultado concreto que IM Music logró con un artista/sello similar (sin nombrar nombres si no los tienes — puedes decir "con un artista en tu mismo nicho").
Línea 4 (CTA): "¿Tienes 20 minutos esta semana?" + enlace: {cal_link}
Línea 5: "Te adjunto cómo trabajamos con artistas en tu posición."

DINÁMICA DE PODER:
- Somos expertos del sector que NOTAMOS algo en tu trabajo — no una agencia que pide trabajo
- El insight que compartimos vale más que el email — ellos son los afortunados de recibirlo
- NUNCA preguntar sobre ellos (cuántos streams tienen, cuál es su objetivo, qué necesitan)
- SÍ compartir datos del sector que probablemente no conocen
- Prohibido: "maximizar tus streams", "llevar al siguiente nivel", sonar como agencia genérica
- Máximo 120 palabras — WhatsApp energy, no email corporativo"""

        reglas_vertical = f"""
{estructura_tipo1}

TIPO 2+: ángulo completamente diferente, mismo tono de experto, propón: {cal_link}
TIPO 3+: menciona que adjuntas info de IM Music"""
    else:
        estructura_tipo1 = f"""
ESTRUCTURA OBLIGATORIA TIPO 1 (primer contacto — empresas):
Línea 1: Observación real y específica de SU negocio — algo verificado de la investigación. Si la web no cargó, NO la menciones. Usa datos del nicho, ciudad o Instagram.
Línea 2: Dato o insight del mercado que demuestra que sabes más de su sector que ellos mismos (tendencias, benchmark del nicho, comportamiento del consumidor).
Línea 3: Resultado concreto que IM logró con un negocio similar al de ellos (puedes decir "con una clínica en Medellín" sin dar nombres).
Línea 4 (CTA): "¿Tienes 20 minutos esta semana?" + enlace: {cal_link}
Línea 5: "Te adjunto cómo trabajamos."

DINÁMICA DE PODER:
- Somos expertos que NOTAMOS algo en su negocio — venimos a aportar, no a pedir
- El poder lo tenemos nosotros — el prospecto es afortunado de recibir este email
- NUNCA preguntar sobre ELLOS (cuántos pacientes tienen, cuál es su presupuesto, qué necesitan)
- SÍ compartir un insight específico que ellos probablemente no tienen
- Prohibido: "potenciar", "escalar", "sinergia", "KPIs", "ROI"
- Máximo 130 palabras — directo, sin rodeos"""

        reglas_vertical = f"""
{estructura_tipo1}

TIPO 2: ángulo completamente diferente, mismo tono de experto
TIPO 3+: propón reunión: {cal_link} y menciona que adjuntas el brochure de IM"""

    prompt = f"""
{agente["personalidad"]}

TIPO DE MENSAJE: {tipos_desc.get(tipo, "Primer contacto")}

DATOS DEL PROSPECTO:
- Nombre: {nombre or "No disponible"}
- Empresa/Proyecto: {empresa}
- Nicho: {nicho}
- Ciudad: {ciudad}

SEÑALES DE LA INVESTIGACIÓN TÉCNICA:
- Argumento de apertura detectado: {argumento or "No disponible"}
- Dolor principal del nicho: {dolor or "No disponible"}
- Tiene ads activos: {"Sí" if ads.get("tiene_ads_activos") else "No"}
- Tiene pixel instalado: {"Sí" if web.get("ads_signals",{}).get("facebook_pixel") else "No"}
- Redes detectadas: {", ".join(informe.get("redes_sociales",{}).keys()) or "No detectadas"}
- Puntos de mejora: {", ".join([m["problema"] for m in mejoras[:3]]) or "No detectados"}
{bloque_7m}
{reglas_vertical}

REGLAS ABSOLUTAS (sin excepciones):
1. El email abre con LA OBSERVACIÓN — nunca con presentación de quién eres.
2. UNA sola pregunta al final ("¿Tienes 20 minutos esta semana?") — nunca más de una.
3. NUNCA inventar observaciones sobre la web si no fue verificada.
4. Si hay investigación de 7 Maletas disponible, ÚSALA — referencia datos concretos.
5. Test final: ¿suena como un experto del sector que notó algo, o como vendedor? Si lo segundo — reescribir.

Escribe el email como {agente["nombre"]} ({agente["nombre_completo"]}).
Firma siempre: {agente["firma"]}

Devuelve SOLO este JSON limpio (sin markdown, sin texto extra):
{{
  "asunto": "asunto conversacional máx 8 palabras sin emojis",
  "cuerpo": "cuerpo completo del email con saltos de línea naturales\\n\\nIncluye el link {cal_link} en el CTA de tipo 1.",
  "asunto_alt_1": "segunda opción de asunto",
  "asunto_alt_2": "tercera opción de asunto",
  "por_que_funciona": "una línea de por qué este email debería generar respuesta"
}}
"""

    # Load env / API key
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if k.strip() and not os.environ.get(k.strip()):
                    os.environ[k.strip()] = v.strip()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return _fallback_copy(agente, lead, informe, tipo)

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        data = resp.json()
        if "error" in data:
            print(f"    ⚠️  Claude API error: {data['error'].get('message','')[:80]}")
            return _fallback_copy(agente, lead, informe, tipo)
        texto = data.get("content", [{}])[0].get("text", "{}")
        texto = re.sub(r"```json|```", "", texto).strip()
        return json.loads(texto)
    except Exception as e:
        print(f"    ⚠️  generar_copy error: {e}")
        return _fallback_copy(agente, lead, informe, tipo)

# Banco de asuntos por nicho — 6 variaciones para rotar y evitar filtros de spam
ASUNTOS_POOL = {
    "odontologos": [
        "algo que vi en {empresa}",
        "una pregunta sobre sus pacientes nuevos",
        "¿cómo llegan los pacientes a {empresa}?",
        "revisé su clínica en Google",
        "algo sobre {empresa} y marketing dental",
        "{nombre}, una observación rápida",
    ],
    "agencias_viaje": [
        "algo que noté en {empresa}",
        "¿cómo están llegando viajeros nuevos?",
        "revisé {empresa} antes de escribir",
        "una pregunta sobre reservas directas",
        "turismo y publicidad — algo para {empresa}",
        "{nombre}, vi algo interesante",
    ],
    "restaurantes": [
        "algo sobre {empresa} que vi hoy",
        "¿cómo llegan comensales nuevos a {empresa}?",
        "revisé su presencia digital",
        "una observación sobre {empresa}",
        "mesas vacías y publicidad — algo para conversar",
        "{nombre}, rápida pregunta",
    ],
    "seguros": [
        "algo sobre {empresa} que noté",
        "¿cómo están consiguiendo asegurados nuevos?",
        "revisé {empresa} esta semana",
        "pólizas y marketing — una observación",
        "{nombre}, una pregunta rápida",
        "algo en la presencia digital de {empresa}",
    ],
    "ecommerce": [
        "algo que vi en {empresa}",
        "¿cómo están con el tráfico a la tienda?",
        "revisé {empresa} en Google",
        "una observación sobre ventas online",
        "{nombre}, algo sobre {empresa}",
        "conversión y publicidad — pregunta rápida",
    ],
    "_default": [
        "algo que vi en {empresa}",
        "una pregunta rápida",
        "revisé {empresa} antes de escribir",
        "{nombre}, ¿5 minutos?",
        "una observación sobre {empresa}",
        "algo sobre clientes nuevos en {empresa}",
    ],
}

_asunto_counters: dict = {}  # contador por nicho para rotar sin repetir


def get_asunto_rotado(nicho: str, nombre: str, empresa: str) -> str:
    """Retorna el siguiente asunto en rotación para el nicho dado."""
    key = nicho.lower().replace(" ", "_")
    pool = ASUNTOS_POOL.get(key, ASUNTOS_POOL["_default"])
    idx = _asunto_counters.get(key, 0) % len(pool)
    _asunto_counters[key] = idx + 1
    tpl = pool[idx]
    nombre_corto = nombre.split()[0] if nombre else "hola"
    empresa_corta = empresa[:30] if empresa else "su negocio"
    return tpl.format(nombre=nombre_corto, empresa=empresa_corta)


def _fallback_copy(agente, lead, informe, tipo):
    """Copy de emergencia cuando la API no responde"""
    nombre  = lead.get("nombre","").split()[0] if lead.get("nombre") else ""
    empresa = lead.get("empresa","")
    ciudad  = lead.get("ciudad","")
    nicho   = lead.get("nicho","")
    ads     = informe.get("ads",{})
    n       = agente["nombre"]
    firma   = agente["firma"]

    if tipo == 1:
        if not ads.get("tiene_ads_activos"):
            cuerpo = f"""{"Hola " + nombre + "," if nombre else ""}

Revisé {empresa or "su negocio"} antes de escribirte.

Una cosa que noté: no tienen campañas de publicidad digital activas. En {nicho.replace("_"," ")} en {ciudad}, eso significa que probablemente están dejando pasar clientes que los están buscando activamente en Google e Instagram.

¿Cómo están consiguiendo clientes nuevos hoy?

{firma}"""
        else:
            cuerpo = f"""{"Hola " + nombre + "," if nombre else ""}

Vi {empresa or "lo que están haciendo"} y quería conectar brevemente.

Trabajo con negocios similares en {ciudad} y hay algo en su presencia digital que creo que podría mejorar bastante.

¿Cómo están con la parte de conseguir clientes nuevos?

{firma}"""
    else:
        cuerpo = f"""{"Hola " + nombre + "," if nombre else ""}

Retomo por aquí. Entiendo que el tiempo es escaso.

Solo quería saber: ¿están satisfechos con cómo están llegando clientes nuevos ahora?

Si tiene sentido conversar 30 minutos, aquí está el link:
{agente["cal_link"]}

{firma}"""

    asunto_rotado = get_asunto_rotado(nicho, nombre, empresa)
    pool = ASUNTOS_POOL.get(nicho.lower().replace(" ", "_"), ASUNTOS_POOL["_default"])
    alts = [get_asunto_rotado(nicho, nombre, empresa) for _ in range(2)]

    return {
        "asunto": asunto_rotado,
        "cuerpo": cuerpo,
        "asunto_alt_1": alts[0],
        "asunto_alt_2": alts[1],
        "por_que_funciona": "Específico y basado en investigación real"
    }


# ════════════════════════════════════════════════════════════════
# GENERADOR DE INFORME PRE-REUNIÓN HTML
# ════════════════════════════════════════════════════════════════

def generar_informe_html(lead: dict, informe: dict, agente_key: str) -> str:
    """Genera el informe completo HTML para preparar la reunión"""
    agente  = AGENTES[agente_key]
    empresa = lead.get("empresa", "Prospecto")
    nicho   = lead.get("nicho", "")
    ciudad  = lead.get("ciudad", "")
    fecha   = datetime.now().strftime("%d/%m/%Y")
    slug    = re.sub(r"[^\w]","_", empresa.lower())[:20]

    web     = informe.get("web", {})
    redes   = informe.get("redes_sociales", {})
    ads     = informe.get("ads", {})
    mejoras = informe.get("puntos_mejora", [])
    opors   = informe.get("oportunidades_im", [])
    ctx     = informe.get("contexto_reunion", {})

    # Ciclo de ventas
    ciclo     = agente["ciclo_ventas"]
    etapa_act = ctx.get("etapa_ciclo_venta", ciclo["etapas"][0])

    # Helper: badge de estado
    def chk(val, yes="✅", no="❌"): return yes if val else no

    # Ads signals
    adss = web.get("ads_signals", {})

    ciclo_html = ""
    for etapa in ciclo["etapas"]:
        activa = "border:2px solid #6200FF;background:rgba(98,0,255,.15);" if etapa == etapa_act else ""
        ciclo_html += f"""
        <div style="flex:1;background:#131313;{activa}border-radius:8px;padding:12px 8px;text-align:center;">
          <div style="font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:{'#a97bff' if etapa==etapa_act else '#555'};margin-bottom:4px">{etapa}</div>
          <div style="font-size:11px;color:#888;line-height:1.4">{ciclo['descripcion'].get(etapa,'')[:60]}</div>
        </div>"""

    mejoras_html = ""
    for m in mejoras:
        mejoras_html += f"""
        <div style="background:#0a0a0a;border-left:3px solid #FF4444;border-radius:0 8px 8px 0;padding:14px 16px;margin-bottom:10px;">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px">
            <span style="font-size:10px;background:rgba(255,68,68,.15);color:#ff9090;padding:2px 8px;border-radius:10px;border:1px solid rgba(255,68,68,.2)">{m['area']}</span>
          </div>
          <div style="font-size:13px;font-weight:600;color:#eee;margin-bottom:4px">{m['problema']}</div>
          <div style="font-size:12px;color:#888;margin-bottom:6px">{m['impacto']}</div>
          <div style="font-size:11px;color:#6eb5ff">💡 IM puede: {m['solucion_im']}</div>
        </div>"""

    preguntas_html = "".join([f'<li style="margin-bottom:8px;color:#ccc;font-size:13px">{p}</li>' for p in ctx.get("preguntas_clave",[])])
    objeciones_html = "".join([f'<div style="background:#0a0a0a;border-radius:8px;padding:12px 14px;margin-bottom:8px"><div style="font-size:12px;color:#ff9090;margin-bottom:4px">❓ "{o[0]}"</div><div style="font-size:12px;color:#a3e6b0">✅ {o[1]}</div></div>' for o in ctx.get("objeciones_esperadas",[])])
    redes_html = "".join([f'<div style="display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid rgba(255,255,255,.04)"><span style="font-size:14px">{"📸" if r=="instagram" else "👍" if r=="facebook" else "🎵" if r=="tiktok" else "▶" if r=="youtube" else "💼" if r=="linkedin" else "🐦"}</span><span style="font-size:12px;color:#aaa">{r.capitalize()}</span><a href="{d.get("url","") if isinstance(d,dict) else d}" target="_blank" style="font-size:11px;color:#6200FF;margin-left:auto">Ver →</a></div>' for r, d in redes.items()])

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Informe Pre-Reunión — {empresa}</title>
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@300;400;500;600&family=DM+Mono&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:#060606;color:#e8e8e8;font-family:'DM Sans',sans-serif;padding:0 0 60px;}}
.header{{background:linear-gradient(135deg,#0d0d0d,#1a0033);padding:40px;border-bottom:1px solid rgba(98,0,255,.3);}}
.wm{{font-family:'Bebas Neue',cursive;font-size:36px;color:#fff;letter-spacing:3px;}}
.wbar{{display:inline-block;width:3px;height:32px;background:#6200FF;margin-left:2px;vertical-align:bottom;}}
.badge{{display:inline-block;padding:3px 12px;border-radius:12px;font-size:10px;font-weight:600;}}
.container{{max-width:900px;margin:0 auto;padding:32px 20px;}}
.card{{background:#131313;border:1px solid rgba(255,255,255,.06);border-radius:12px;padding:24px;margin-bottom:18px;}}
.card-t{{font-family:'Bebas Neue',cursive;font-size:16px;letter-spacing:2px;color:#6200FF;margin-bottom:16px;}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:14px;}}
.grid3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;}}
.metric{{background:#0a0a0a;border:1px solid rgba(255,255,255,.05);border-radius:10px;padding:16px;text-align:center;}}
.mv{{font-family:'Bebas Neue',cursive;font-size:32px;color:#fff;}}
.ml{{font-size:9px;letter-spacing:2px;text-transform:uppercase;color:#555;margin-top:4px;}}
.ok{{color:#00F5A0;}} .no{{color:#FF4444;}} .warn{{color:#F5C518;}}
@media print{{body{{background:#fff;color:#000}}}}
</style>
</head>
<body>

<div class="header">
  <div class="wm">IM<span class="wbar"></span></div>
  <div style="font-size:10px;letter-spacing:3px;color:#6200FF;margin-top:3px">INFORME PRE-REUNIÓN</div>
  <div style="margin-top:24px">
    <div style="font-family:'Bebas Neue',cursive;font-size:32px;color:#fff;letter-spacing:2px">{empresa.upper()}</div>
    <div style="font-size:12px;color:#888;margin-top:4px">{nicho.replace("_"," ").title()} · {ciudad} · Generado: {fecha}</div>
    <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">
      <span class="badge" style="background:rgba(98,0,255,.2);color:#a97bff;border:1px solid rgba(98,0,255,.3)">Agente: {agente["nombre_completo"]}</span>
      <span class="badge" style="background:rgba(98,0,255,.2);color:#a97bff;border:1px solid rgba(98,0,255,.3)">{agente["empresa"]}</span>
      <span class="badge" style="background:rgba(255,214,0,.1);color:#F5C518;border:1px solid rgba(255,214,0,.2)">Etapa: {etapa_act}</span>
    </div>
  </div>
</div>

<div class="container">

  <!-- RESUMEN RÁPIDO -->
  <div class="card">
    <div class="card-t">📊 DIAGNÓSTICO DIGITAL</div>
    <div class="grid3">
      <div class="metric"><div class="mv {'ok' if web else 'no'}">{chk(web)}</div><div class="ml">Sitio Web</div></div>
      <div class="metric"><div class="mv {'ok' if redes else 'no'}">{chk(redes)}</div><div class="ml">Redes Sociales</div></div>
      <div class="metric"><div class="mv {'ok' if ads.get('tiene_ads_activos') else 'no'}">{chk(ads.get('tiene_ads_activos'))}</div><div class="ml">Ads Activos</div></div>
      <div class="metric"><div class="mv {'ok' if adss.get('facebook_pixel') else 'no'}">{chk(adss.get('facebook_pixel'))}</div><div class="ml">Facebook Pixel</div></div>
      <div class="metric"><div class="mv {'ok' if adss.get('google_ads') else 'no'}">{chk(adss.get('google_ads'))}</div><div class="ml">Google Analytics</div></div>
      <div class="metric"><div class="mv {'ok' if web.get('tiene_blog') else 'no'}">{chk(web.get('tiene_blog'))}</div><div class="ml">Blog / SEO</div></div>
    </div>
    <div style="margin-top:16px;padding:14px;background:#0a0a0a;border-radius:8px;font-family:'DM Mono',monospace;font-size:11px;color:#888;white-space:pre-line">{informe.get("resumen_ejecutivo","")}</div>
  </div>

  <!-- CICLO DE VENTAS -->
  <div class="card">
    <div class="card-t">🔄 CICLO DE VENTA — ETAPA ACTUAL</div>
    <div style="display:flex;gap:6px;flex-wrap:wrap">{ciclo_html}</div>
    <div style="margin-top:14px;padding:12px;background:#0a0a0a;border-radius:8px">
      <div style="font-size:11px;color:#6200FF;margin-bottom:4px">EN ESTA ETAPA ({etapa_act}):</div>
      <div style="font-size:12px;color:#aaa">{ciclo['descripcion'].get(etapa_act,'')}</div>
    </div>
  </div>

  <!-- PUNTOS DE MEJORA -->
  {"<div class='card'><div class='card-t'>⚠️ PUNTOS DE MEJORA DETECTADOS</div>" + mejoras_html + "</div>" if mejoras else ""}

  <!-- OPORTUNIDADES PARA IM -->
  <div class="card">
    <div class="card-t">🎯 OPORTUNIDADES PARA IM</div>
    {"".join([f'<div style="display:flex;align-items:flex-start;gap:10px;padding:10px 0;border-bottom:1px solid rgba(255,255,255,.04)"><span style="color:#00F5A0;font-size:14px">→</span><span style="font-size:13px;color:#ccc">{o}</span></div>' for o in opors])}
    <div style="margin-top:14px;padding:12px;background:rgba(98,0,255,.08);border:1px solid rgba(98,0,255,.2);border-radius:8px">
      <div style="font-size:11px;color:#a97bff;margin-bottom:4px">PROPUESTA DE VALOR PERSONALIZADA:</div>
      <div style="font-size:13px;color:#ddd">{ctx.get("propuesta_valor_personalizada","")}</div>
    </div>
  </div>

  <div class="grid2">
    <!-- PREGUNTAS CLAVE -->
    <div class="card">
      <div class="card-t">❓ PREGUNTAS PARA LA REUNIÓN</div>
      <ul style="padding-left:16px">{preguntas_html}</ul>
    </div>

    <!-- REDES SOCIALES -->
    <div class="card">
      <div class="card-t">📱 REDES DETECTADAS</div>
      {redes_html if redes_html else '<div style="color:#555;font-size:12px">No se detectó presencia en redes sociales</div>'}
      {"<div style='margin-top:12px;padding:10px;background:rgba(255,68,68,.06);border-radius:8px;border:1px solid rgba(255,68,68,.15)'><div style='font-size:11px;color:#ff9090'>⚠️ " + ("Sin presencia en redes — gran oportunidad" if not redes else f"Presente en {len(redes)} red{'es' if len(redes)>1 else ''}") + "</div></div>"}
    </div>
  </div>

  <!-- MANEJO DE OBJECIONES -->
  <div class="card">
    <div class="card-t">🛡️ OBJECIONES ESPERADAS + CÓMO MANEJARLAS</div>
    {objeciones_html}
  </div>

  <!-- WEB TECH -->
  {"<div class='card'><div class='card-t'>🌐 ANÁLISIS WEB</div><div class='grid2'><div><div style='font-size:11px;color:#555;margin-bottom:6px'>TECNOLOGÍA</div><div style='font-size:13px;color:#ccc'>Plataforma: <strong style='color:#a97bff'>" + web.get('plataforma_web','—').capitalize() + "</strong></div><div style='font-size:13px;color:#ccc;margin-top:4px'>Imágenes: " + str(web.get('num_imagenes',0)) + " | Videos: " + str(web.get('num_videos',0)) + "</div></div><div><div style='font-size:11px;color:#555;margin-bottom:6px'>PIXELS Y TRACKING</div>" + "".join([f"<div style='font-size:12px;color:{'#00F5A0' if v else '#555'};margin-bottom:3px'>{'✅' if v else '❌'} {k.replace('_',' ').title()}</div>" for k,v in adss.items()]) + "</div></div>" + ("<div style='margin-top:14px'><div style='font-size:11px;color:#555;margin-bottom:8px'>SERVICIOS DETECTADOS EN WEB</div>" + "".join([f"<div style='font-size:12px;color:#aaa;padding:4px 0;border-bottom:1px solid rgba(255,255,255,.03)'>{s[:100]}</div>" for s in web.get('servicios_detectados',[])[:5]]) + "</div>" if web.get('servicios_detectados') else "") + "</div>" if web else ""}

</div>

<div style="text-align:center;padding:30px;color:#333;font-size:10px;border-top:1px solid rgba(255,255,255,.04);margin-top:20px">
  Intelligent Markets · intelligentmarkets@gmail.com · Generado: {fecha}<br>
  {agente["nombre_completo"]} — {agente["empresa"]}
</div>

</body>
</html>"""

    out = Path(__file__).parent.parent / "reports"
    out.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    path = out / f"informe_{slug}_{ts}.html"
    path.write_text(html, encoding="utf-8")
    return str(path)


# ════════════════════════════════════════════════════════════════
# ENVÍO DE EMAIL
# ════════════════════════════════════════════════════════════════

def enviar_email(agente_key, to_email, asunto, cuerpo, adjuntar=False):
    agente = AGENTES[agente_key]
    pwd = os.environ.get("IM_EMAIL_PASSWORD", "")
    if not pwd:
        print(f"    ⚠️  Sin contraseña — simulando envío a {to_email}")
        return True
    try:
        msg = MIMEMultipart()
        msg["From"] = f"{agente['nombre_completo']} <{agente['email']}>"
        msg["To"]   = to_email
        msg["Subject"] = asunto
        msg.attach(MIMEText(cuerpo, "plain", "utf-8"))
        if adjuntar:
            bp = Path(__file__).parent.parent / agente["brochure"]
            MAX_ATTACH_BYTES = 20 * 1024 * 1024  # 20 MB — Gmail límite real ~25MB
            if bp.exists() and bp.stat().st_size <= MAX_ATTACH_BYTES:
                with open(bp, "rb") as f:
                    part = MIMEBase("application","octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f"attachment; filename={bp.name}")
                msg.attach(part)
            elif bp.exists():
                # Brochure demasiado grande — incluir enlace de descarga en el cuerpo
                drive_key = "BROCHURE_LINK_" + agente.get("vertical","empresas").upper()
                drive_url = os.environ.get(drive_key, "")
                if drive_url:
                    cuerpo_actual = msg.get_payload(0)
                    if hasattr(cuerpo_actual, 'get_payload'):
                        texto = cuerpo_actual.get_payload(decode=True).decode('utf-8', errors='ignore')
                        texto += f"\n\n[Descarga el brochure aquí: {drive_url}]"
                        msg.get_payload()[0] = MIMEText(texto, "plain", "utf-8")
                    print(f"    Brochure grande — link Drive incluido en cuerpo")
                else:
                    print(f"    Brochure {bp.name} ({bp.stat().st_size//1024//1024}MB) grande — agrega BROCHURE_LINK_EMPRESAS al .env para incluir link")
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls()
            s.login(agente["email"], pwd)
            s.sendmail(agente["email"], to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"    ❌ Error: {e}")
        return False

def log_actividad(lead, agente, tipo, asunto, cuerpo, status, informe_path=""):
    # 1. CSV local
    log = Path(__file__).parent.parent / "logs" / "actividad_agentes.csv"
    log.parent.mkdir(exist_ok=True)
    nuevo = not log.exists()
    with open(log, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if nuevo:
            w.writerow(["timestamp","agente","tipo","nombre","empresa","email","nicho","ciudad","asunto","palabras","status","informe"])
        w.writerow([datetime.now().isoformat(), agente, tipo, lead.get("nombre",""), lead.get("empresa",""),
                    lead.get("email",""), lead.get("nicho",""), lead.get("ciudad",""),
                    asunto, len(cuerpo.split()), status, informe_path])

    # 2. platform.db emails_log + actualizar status del lead
    try:
        import sqlite3 as _sqlite3
        db_path = Path(__file__).parent.parent / "logs" / "platform.db"
        if db_path.exists():
            conn = _sqlite3.connect(str(db_path))
            conn.execute(
                "INSERT INTO emails_log (agente, to_email, to_nombre, empresa, nicho, asunto, tipo, estado, enviado_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (agente, lead.get("email",""), lead.get("nombre",""), lead.get("empresa",""),
                 lead.get("nicho",""), asunto, tipo, status, datetime.now().isoformat())
            )
            # Actualizar status del lead en la DB si fue enviado
            if status == "ENVIADO":
                conn.execute(
                    "UPDATE leads SET status='enviado', fecha_contacto=? WHERE LOWER(email)=LOWER(?)",
                    (datetime.now().isoformat(), lead.get("email",""))
                )
            conn.commit(); conn.close()
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════
# FLUJO PRINCIPAL
# ════════════════════════════════════════════════════════════════

def procesar_leads(csv_path, agente_key, tipo=1, dry_run=False,
                   max_envios=50, adjuntar=False, generar_informe=True):
    agente = AGENTES[agente_key]
    with open(csv_path, "r", encoding="utf-8") as f:
        leads = list(csv.DictReader(f))

    tipos_label = {1:"PRIMER CONTACTO",2:"FOLLOW-UP",3:"RESPONDIÓ CON INTERÉS",4:"PRE-REUNIÓN",5:"CIERRE"}

    print(f"\n{'═'*62}")
    print(f"  AGENTE:  {agente['nombre_completo']} — {agente['empresa']}")
    print(f"  TIPO:    {tipos_label.get(tipo, str(tipo))}")
    print(f"  LEADS:   {len(leads)} | MAX: {max_envios}")
    print(f"  MODO:    {'🔍 DRY RUN' if dry_run else '🚀 ENVÍO REAL'}")
    print(f"  INFORME: {'Sí' if generar_informe else 'No'}")
    print(f"{'═'*62}\n")

    # Cargar deliverability para rate-limit y dedup
    try:
        import sys as _sys2
        _sys2.path.insert(0, str(Path(__file__).parent))
        import im_deliverability as _deliv
        _DELIV_OK = True
    except Exception:
        _DELIV_OK = False

    # Dedup de dominios — no enviar dos veces al mismo dominio en una misma campaña
    dominios_enviados: set = set()

    enviados = 0
    for i, lead in enumerate(leads[:max_envios], 1):
        email = lead.get("email","").strip()
        if not email or "@" not in email:
            continue

        # Rate-limit horario
        if _DELIV_OK and not dry_run:
            puede, razon = _deliv.puede_enviar_ahora()
            if not puede:
                print(f"\n  ⛔ {razon} — pausando campaña. Reintenta más tarde.")
                break

        # Dedup de dominio
        dominio = email.split("@")[1].lower()
        if dominio not in {"gmail.com","hotmail.com","outlook.com","yahoo.com"} and dominio in dominios_enviados:
            print(f"  [{i}] ⚠️  Dominio {dominio} ya contactado — omitiendo {email}")
            continue
        dominios_enviados.add(dominio)

        nombre  = lead.get("nombre","") or lead.get("empresa","")
        empresa = lead.get("empresa","")

        print(f"  [{i}/{min(len(leads),max_envios)}] {nombre or email}")

        # INVESTIGACIÓN TÉCNICA (web, ads, redes)
        print(f"    🔍 Investigando...", end="", flush=True)
        informe = investigacion_profunda(lead)
        print(f" ✓ ({len(informe.get('puntos_mejora',[]))} mejoras detectadas)")

        # INVESTIGACIÓN 7 MALETAS (neurociencia + ángulo de entrada)
        inv_7m = None
        if _INV_OK:
            print(f"    🧠 7 Maletas...", end="", flush=True)
            try:
                inv_7m = _lead_inv.investigar(lead)
                print(f" ✓ (confianza: {inv_7m.get('nivel_confianza','?')})")
            except Exception as _e:
                print(f" ⚠ ({_e})")

        # INFORME HTML
        informe_path = ""
        if generar_informe:
            print(f"    📄 Generando informe pre-reunión...", end="", flush=True)
            informe_path = generar_informe_html(lead, informe, agente_key)
            print(f" ✓ {Path(informe_path).name}")

        # COPY — tipo >= 3 adjunta brochure automáticamente
        adjuntar_este = adjuntar or (tipo >= 3)
        print(f"    ✍️  Generando copy...", end="", flush=True)
        copy = generar_copy(agente_key, lead, informe, tipo, inv_7m)
        print(f" ✓")
        print(f"    📬 Asunto: {copy.get('asunto','')}")
        print(f"    💬 {copy.get('por_que_funciona','')}")
        print(f"    📝 {len(copy.get('cuerpo','').split())} palabras\n")

        asunto = copy.get("asunto","")
        cuerpo = copy.get("cuerpo","")

        if dry_run:
            print(f"    ── EMAIL ────────────────────────────────────")
            print(cuerpo)
            print(f"    ──────────────────────────────────────────────\n")
            log_actividad(lead, agente["nombre"], tipos_label.get(tipo,""), asunto, cuerpo, "DRY_RUN", informe_path)
            enviados += 1
        else:
            print(f"    📤 Enviando...", end="", flush=True)
            ok = enviar_email(agente_key, email, asunto, cuerpo, adjuntar_este)
            status = "ENVIADO" if ok else "ERROR"
            print(f" {'✅' if ok else '❌'}")
            log_actividad(lead, agente["nombre"], tipos_label.get(tipo,""), asunto, cuerpo, status, informe_path)
            if ok:
                enviados += 1
                if _DELIV_OK:
                    _deliv.registrar_email_warmup()
            if i < min(len(leads), max_envios):
                delay = random.uniform(60, 120)
                print(f"    ⏳ {delay:.0f}s...\n")
                time.sleep(delay)

    print(f"\n{'═'*62}")
    print(f"  ✅ Procesados: {enviados}")
    print(f"  📁 Informes:  reports/")
    print(f"  📊 Log:       logs/actividad_agentes.csv")
    print(f"{'═'*62}\n")

def modo_interactivo(agente_key):
    print(f"\n🧪 MODO INTERACTIVO — {AGENTES[agente_key]['nombre_completo']}\n")
    lead = {
        "nombre":  input("  Nombre del contacto: ").strip(),
        "empresa": input("  Empresa/Negocio: ").strip(),
        "email":   input("  Email: ").strip(),
        "ciudad":  input("  Ciudad: ").strip() or "Medellín",
        "nicho":   input("  Nicho: ").strip() or "odontologos",
        "url":     input("  URL web (Enter para omitir): ").strip(),
        "instagram":input("  Instagram URL (Enter para omitir): ").strip(),
    }
    tipo = int(input("  Tipo (1=primero, 2=follow-up, 3=interés): ") or "1")
    gen_inf = input("  ¿Generar informe pre-reunión? (S/n): ").strip().lower() != "n"

    print(f"\n  🔍 Investigando {lead['empresa'] or lead['nombre']}...")
    informe = investigacion_profunda(lead)
    print(f"  ✓ {len(informe.get('puntos_mejora',[]))} puntos de mejora | {len(informe.get('redes_sociales',{}))} redes")

    inv_7m = None
    if _INV_OK:
        print(f"  🧠 Analizando con 7 Maletas...")
        try:
            inv_7m = _lead_inv.investigar(lead)
            print(f"  ✓ Ángulo: {inv_7m.get('maleta_7_angulo',{}).get('resumen','')}")
        except Exception as e:
            print(f"  ⚠ 7 Maletas falló: {e}")

    if gen_inf:
        path = generar_informe_html(lead, informe, agente_key)
        print(f"  📄 Informe: {path}")
        try: os.system(f"open '{path}' 2>/dev/null || xdg-open '{path}' 2>/dev/null")
        except: pass

    print(f"\n  ✍️  Generando copy...\n")
    copy = generar_copy(agente_key, lead, informe, tipo, inv_7m)

    print(f"  {'─'*55}")
    print(f"  ASUNTO:  {copy['asunto']}")
    print(f"  ALT 1:   {copy.get('asunto_alt_1','')}")
    print(f"  ALT 2:   {copy.get('asunto_alt_2','')}")
    print(f"  {'─'*55}")
    print(copy["cuerpo"])
    print(f"  {'─'*55}")
    print(f"  POR QUÉ: {copy.get('por_que_funciona','')}")
    print()

    if lead["email"] and input("  ¿Enviar? (s/N): ").strip().lower() == "s":
        ok = enviar_email(agente_key, lead["email"], copy["asunto"], copy["cuerpo"])
        print(f"  {'✅ Enviado' if ok else '❌ Error'}")

# ════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(
        description="IM Agents v3 — Mateo (empresas) + José (música)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
AGENTES:
  mateo  → Intelligent Markets (salud, viajes, seguros, autos)
  jose   → IM Music (sellos, managers, artistas independientes)

TIPOS DE MENSAJE:
  1 = Primer contacto    4 = Pre-reunión
  2 = Follow-up          5 = Post-reunión / cierre
  3 = Respondió con interés

EJEMPLOS:
  # Modo interactivo (siempre empieza aquí para probar)
  python im_agents.py --agente mateo --interactivo
  python im_agents.py --agente jose --interactivo

  # Procesar CSV con investigación completa + informe
  python im_agents.py --agente mateo --csv data/leads_odontologos_*.csv --dry-run
  python im_agents.py --agente jose  --csv data/leads_sello_*.csv --dry-run

  # Envío real
  python im_agents.py --agente mateo --csv data/leads.csv --tipo 1 --max 40
  python im_agents.py --agente jose  --csv data/leads.csv --tipo 1 --max 30

  # Follow-up con brochure
  python im_agents.py --agente mateo --csv data/leads.csv --tipo 3 --brochure
        """
    )
    p.add_argument("--agente", choices=["mateo","jose"], required=True)
    p.add_argument("--csv", help="Archivo CSV de leads")
    p.add_argument("--tipo", type=int, default=1, choices=range(1,6))
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--max", type=int, default=50)
    p.add_argument("--brochure", action="store_true")
    p.add_argument("--sin-informe", action="store_true", help="No generar informe HTML")
    p.add_argument("--interactivo", action="store_true")
    args = p.parse_args()

    if args.interactivo:
        modo_interactivo(args.agente)
        return
    if not args.csv:
        p.print_help()
        return

    import glob
    archivos = glob.glob(args.csv)
    if not archivos:
        print(f"❌ No se encontraron archivos: {args.csv}")
        return
    for f in archivos:
        procesar_leads(f, args.agente, args.tipo, args.dry_run,
                       args.max, args.brochure, not args.sin_informe)

if __name__ == "__main__":
    main()
