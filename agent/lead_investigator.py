#!/usr/bin/env python3
"""
IM Lead Investigator — Intelligent Markets
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Investigación profunda de prospectos usando las 7 Maletas del prospecto
+ neurociencia del consumidor, ANTES de escribir el primer email.

Las 7 Maletas del Prospecto:
  1. ¿Qué tiene?     — web, redes, ads activos, reseñas
  2. ¿Qué le falta?  — puntos de mejora evidentes
  3. ¿Qué le duele?  — dolor nuclear del nicho
  4. ¿Qué desea?     — objetivo que no está logrando
  5. ¿Qué lo frena?  — objeción principal
  6. ¿Qué lo mueve?  — motivación profunda
  7. ¿Cómo conectamos? — ángulo de entrada para el email

Uso:
  python agent/lead_investigator.py --email joseg09.dg@gmail.com
  python agent/lead_investigator.py --lead '{"nombre":"Dr. Lopez","empresa":"Clinica Lopez","email":"x@x.com","nicho":"odontologos"}'
"""

import os, json, re, sys, time, argparse
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# ── Cargar .env ────────────────────────────────────────────────
def _load_env():
    f = Path(__file__).parent.parent / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if k.strip() and not os.environ.get(k.strip()):
                    os.environ[k.strip()] = v.strip()
_load_env()

try:
    import requests
    NET = True
except ImportError:
    NET = False

BASE = Path(__file__).parent.parent
INV_DIR = BASE / "data" / "investigaciones"

# ════════════════════════════════════════════════════════════════
# SYSTEM PROMPT — mismo estilo que intelligence_engine.py
# ════════════════════════════════════════════════════════════════

SYS_INVESTIGADOR_PROSPECTO = """Eres el Analista de Inteligencia de Prospectos de Intelligent Markets.
Combinas experiencia en marketing B2B con neurociencia del consumidor (Kahneman, Cialdini, Ariely),
psicología persuasiva y la metodología de las 7 Maletas adaptada para PROSPECTOS FRÍOS.

Tu trabajo NO es investigar para vender — es investigar para CONECTAR.
El primer email nunca hace pitch. Solo hace que el prospecto quiera responder.

REGLA ABSOLUTA DE HONESTIDAD:
- SOLO incluyes hechos verificados o inferencias claramente marcadas como tal.
- Si la web NO se pudo cargar: NUNCA inventas "la página cargó lento", "el sitio tiene problemas técnicos"
  ni cualquier observación sobre la web. JAMÁS fabricas lo que no viste.
- Si no tienes datos de la web: el ángulo de entrada se basa en el nicho, ciudad e Instagram únicamente.
- Señala explícitamente cuándo algo es inferencia del sector vs dato concreto verificado.
- Una investigación honesta con pocos datos es mejor que una llena de datos fabricados.

Tus análisis son:
- Concretos y específicos para el negocio/persona investigada
- Accionables: cada insight lleva directamente a un ángulo de contacto
- Honestos: "inferencia del sector" cuando no hay dato verificado
- Basados SOLO en señales reales observadas directamente

Usas el lenguaje exacto del nicho. Nunca hablas como agencia genérica."""


# ════════════════════════════════════════════════════════════════
# LLAMADA A CLAUDE (mismo patrón que intelligence_engine.py)
# ════════════════════════════════════════════════════════════════

def call_claude(system_prompt: str, user_prompt: str, max_tokens: int = 2000) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or not NET:
        return ""
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "claude-sonnet-4-5",
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            },
            timeout=90,
        )
        data = r.json()
        if "error" in data:
            return ""
        return data.get("content", [{}])[0].get("text", "")
    except Exception:
        return ""


# ════════════════════════════════════════════════════════════════
# SCRAPING LIVIANO DEL PROSPECTO
# ════════════════════════════════════════════════════════════════

def _fetch_con_reintentos(url: str, intentos: int = 3, timeout: int = 9) -> tuple:
    """Intenta cargar URL hasta `intentos` veces. Retorna (html, cargó_ok)."""
    if not NET or not url:
        return "", False
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    ]
    for i in range(intentos):
        try:
            hdrs = {
                "User-Agent": user_agents[i % len(user_agents)],
                "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            }
            r = requests.get(url, headers=hdrs, timeout=timeout, allow_redirects=True)
            if r.status_code == 200 and len(r.text) > 200:
                return r.text, True
            if i < intentos - 1:
                time.sleep(2)
        except Exception:
            if i < intentos - 1:
                time.sleep(2)
    return "", False


def _extraer_texto_plano(html: str, max_chars: int = 3000) -> str:
    """Extrae texto legible de HTML sin dependencia de BeautifulSoup."""
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&[a-z]+;', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:max_chars]


def _detectar_senales_digitales(html: str, url: str) -> dict:
    """Detecta presencia de pixels, analytics, redes, etc."""
    h = html.lower()
    return {
        "facebook_pixel":   "fbq(" in h or "facebook.net/en_US/fbevents" in h,
        "google_analytics": "gtag(" in h or "google-analytics.com" in h or "googletagmanager" in h,
        "instagram_link":   "instagram.com/" in h,
        "facebook_link":    "facebook.com/" in h,
        "tiktok_link":      "tiktok.com/" in h,
        "whatsapp_cta":     "wa.me/" in h or "api.whatsapp.com" in h,
        "chat_widget":      any(x in h for x in ["intercom", "tidio", "crisp", "zendesk", "hubspot"]),
        "blog_section":     any(x in h for x in ["/blog", "/noticias", "/articulos", "blog."]),
        "testimonios":      any(x in h for x in ["testimonios", "opiniones", "resenas", "reseñas", "reviews"]),
        "tienda_online":    any(x in h for x in ["carrito", "agregar al", "add to cart", "shopify", "woocommerce"]),
    }


def _recopilar_datos_digitales(lead: dict) -> dict:
    """Recopila señales digitales reales del prospecto. Nunca inventa nada."""
    url       = (lead.get("url") or "").strip()
    instagram = (lead.get("instagram") or "").strip()
    datos     = {
        "url_analizada": url,
        "html_disponible": False,
        "sin_web_verificada": False,
        "intentos_realizados": 0,
        "texto_web": "",
        "senales": {},
        "instagram_analizado": bool(instagram),
    }

    if url and (url.startswith("http://") or url.startswith("https://")):
        print(f"        🌐 Intentando cargar {url[:60]}...", end="", flush=True)
        html, ok = _fetch_con_reintentos(url, intentos=3)
        datos["intentos_realizados"] = 3
        if ok:
            datos["html_disponible"] = True
            datos["texto_web"] = _extraer_texto_plano(html)
            datos["senales"] = _detectar_senales_digitales(html, url)
            print(" ✓ cargada")
        else:
            datos["sin_web_verificada"] = True
            print(" ✗ no accesible (3 intentos)")
    elif url:
        datos["sin_web_verificada"] = True

    return datos


# ════════════════════════════════════════════════════════════════
# PROMPT DE LAS 7 MALETAS DEL PROSPECTO
# ════════════════════════════════════════════════════════════════

DOLORES_POR_NICHO = {
    "odontologos":       "Agenda poco llena, dependencia del voz a voz, no saben medir qué pacientes vienen del digital",
    "restaurantes":      "Mesas vacías entre semana, no fidelizan clientes, no aparecen en Google Maps con buenas reseñas",
    "agencias_viajes":   "Compiten contra OTAs (Booking, Despegar) con menor presupuesto, leads de bajo cierre",
    "seguros":           "Cartera estancada, renovaciones perdidas, prospectos que piden cotización y desaparecen",
    "gimnasios":         "Alta rotación de miembros en enero-febrero, no retienen, pocas referencias activas",
    "educacion":         "Bajo enrollment, alto costo por lead, ciclos de decisión muy largos",
    "inmobiliarias":     "Leads fríos que nunca cierran, dependencia de portales caros, sin marca propia",
    "ecommerce":         "Carrito abandonado alto, CAC creciente, bajo retorno de clientes",
    "clinicas_salud":    "No generan confianza online, dependencia de EPS/seguros, poca diferenciación",
    "constructoras":     "Ciclos de venta muy largos, leads poco calificados, no tienen CRM",
    "music":             "Streams que no crecen, sin fanbase real, sin estrategia de lanzamiento",
    "artistas":          "Streams que no crecen, sin fanbase real, sin estrategia de lanzamiento",
    "sellos":            "Artistas con potencial sin distribución efectiva, sin presencia en DSPs clave",
}

DESEOS_POR_NICHO = {
    "odontologos":       "Tener la agenda llena de pacientes calificados de forma predecible, sin depender de referidos",
    "restaurantes":      "Llenar el restaurante entre semana y construir una comunidad de clientes fieles",
    "agencias_viajes":   "Conseguir clientes de alto valor que compren paquetes completos y repitan",
    "seguros":           "Tener un flujo constante de referidos calificados y renovaciones sin esfuerzo manual",
    "gimnasios":         "Retener miembros más de 6 meses y llenar clases en horarios valle",
    "educacion":         "Llenar los cupos de cada programa con estudiantes calificados y comprometidos",
    "inmobiliarias":     "Recibir leads de calidad que realmente quieran comprar, no solo curiosos",
    "ecommerce":         "Reducir el CAC y aumentar el LTV con clientes que recompran",
    "clinicas_salud":    "Ser la clínica de referencia en su especialidad en la ciudad",
    "constructoras":     "Proyectos vendidos antes de estar terminados, con clientes calificados",
    "music":             "Crecer en streams y fanbase de forma orgánica y sostenida",
    "artistas":          "Crecer en streams y fanbase de forma orgánica y sostenida",
    "sellos":            "Posicionar artistas del catálogo en los mercados clave de habla hispana",
}


def _construir_prompt_7_maletas(lead: dict, datos_digitales: dict) -> str:
    nombre   = lead.get("nombre", "")
    empresa  = lead.get("empresa", "")
    nicho    = lead.get("nicho", "general")
    ciudad   = lead.get("ciudad", "")
    url      = lead.get("url", "")
    instagram= lead.get("instagram", "")
    email    = lead.get("email", "")

    nicho_key = nicho.lower().replace(" ", "_")
    dolor_nicho  = DOLORES_POR_NICHO.get(nicho_key, f"Dificultad para conseguir y retener clientes en el sector {nicho}")
    deseo_nicho  = DESEOS_POR_NICHO.get(nicho_key,  f"Crecer de forma predecible y diferenciarse de la competencia")

    senales = datos_digitales.get("senales", {})
    texto_web = datos_digitales.get("texto_web", "")
    tiene_web = datos_digitales.get("html_disponible", False)

    sin_web = datos_digitales.get("sin_web_verificada", False)

    if sin_web:
        web_context = f"""
SITIO WEB ({url}): NO PUDO CARGARSE — 3 intentos fallidos.
⚠️  REGLA CRÍTICA: NO menciones la web en el análisis. NO inventes observaciones sobre ella.
⚠️  NO uses frases como "noté que su página...","vi que su web...","la página cargó lento", etc.
⚠️  Basa el análisis SOLO en el nicho, la ciudad y cualquier info de Instagram disponible.
"""
    elif url and tiene_web and senales:
        senales_txt = "\n".join([
            f"  - Facebook Pixel instalado: {'✅ SÍ' if senales.get('facebook_pixel') else '❌ NO'}",
            f"  - Google Analytics/GTM: {'✅ SÍ' if senales.get('google_analytics') else '❌ NO'}",
            f"  - Instagram enlazado en web: {'✅ SÍ' if senales.get('instagram_link') else '❌ NO'}",
            f"  - WhatsApp como CTA: {'✅ SÍ' if senales.get('whatsapp_cta') else '❌ NO'}",
            f"  - Blog / sección de contenido: {'✅ SÍ' if senales.get('blog_section') else '❌ NO'}",
            f"  - Testimonios visibles: {'✅ SÍ' if senales.get('testimonios') else '❌ NO'}",
            f"  - Chat widget activo: {'✅ SÍ' if senales.get('chat_widget') else '❌ NO'}",
        ])
        web_context = f"""
SITIO WEB VERIFICADO ({url}):
{senales_txt}

CONTENIDO WEB (extracto real):
{texto_web[:1500]}
"""
    elif url:
        web_context = f"URL proporcionada ({url}) pero no accesible al momento del análisis — no hacer referencia a ella."
    else:
        web_context = "Sin URL web — análisis basado en nicho, ciudad e Instagram únicamente."

    instagram_context = f"Instagram: {instagram}" if instagram else "Instagram: no proporcionado."

    return f"""Analiza este PROSPECTO frío para Intelligent Markets y completa las 7 Maletas del Prospecto.

DATOS DEL PROSPECTO:
- Nombre: {nombre or "No disponible"}
- Empresa / Proyecto: {empresa or "No disponible"}
- Email: {email or "No disponible"}
- Nicho: {nicho}
- Ciudad: {ciudad or "No especificada"}
- {instagram_context}

SEÑALES DIGITALES DETECTADAS:
{web_context}

CONTEXTO DEL NICHO:
- Dolor típico del nicho: {dolor_nicho}
- Deseo típico del nicho: {deseo_nicho}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INSTRUCCIONES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Basándote en los datos reales disponibles (señales web + nicho + contexto),
completa las 7 Maletas del Prospecto. Sé ESPECÍFICO: usa datos concretos cuando
los tengas, e infiere con honestidad cuando no los tengas (señala cuándo es inferencia).

Devuelve ÚNICAMENTE este JSON válido (sin texto extra, sin markdown):
{{
  "maleta_1_tiene": {{
    "resumen": "qué presencia digital tiene actualmente (web, pixel, redes, tracking)",
    "detalle": ["punto 1", "punto 2", "punto 3"]
  }},
  "maleta_2_falta": {{
    "resumen": "qué le falta de forma más evidente en digital",
    "detalle": ["carencia 1", "carencia 2", "carencia 3"]
  }},
  "maleta_3_duele": {{
    "resumen": "cuál es su dolor nuclear real como negocio (no genérico)",
    "detalle": "explicación de 2-3 líneas de por qué este dolor es relevante para este prospecto específico"
  }},
  "maleta_4_desea": {{
    "resumen": "qué resultado está intentando conseguir pero no logra",
    "detalle": "qué se imagina que cambiaría en su negocio si resolviera el problema"
  }},
  "maleta_5_frena": {{
    "resumen": "cuál es su objeción principal para contratar marketing",
    "detalle": "por qué tiene esa objeción y cómo se manifiesta en el sector"
  }},
  "maleta_6_mueve": {{
    "resumen": "qué motivación profunda lo haría actuar",
    "detalle": "principio psicológico detrás de esta motivación (Cialdini, Kahneman, etc.)"
  }},
  "maleta_7_angulo": {{
    "resumen": "cuál es el mejor ángulo de entrada para el primer email",
    "asunto_sugerido": "asunto conversacional de máximo 8 palabras sin emojis",
    "primera_linea": "primera oración del email — específica, sin pitch, genera curiosidad",
    "por_que_funciona": "por qué este ángulo va a generar respuesta en este prospecto"
  }},
  "resumen_investigacion": "3-4 líneas que resumen todo lo que necesita saber el agente antes de escribir el email",
  "nivel_confianza": "alto/medio/bajo — qué tan confiable es esta investigación dados los datos disponibles"
}}"""


# ════════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL: investigar()
# ════════════════════════════════════════════════════════════════

def investigar(lead: dict, forzar: bool = False) -> dict:
    """
    Investiga un lead con las 7 Maletas del Prospecto.

    Cachea el resultado en data/investigaciones/{email_safe}.json.
    Si ya existe y no se fuerza, devuelve el cache.

    Returns: dict con las 7 maletas + resumen
    """
    email = lead.get("email", "").strip()
    empresa = lead.get("empresa", lead.get("nombre", "sin_nombre"))

    # Clave de cache: email si existe, sino empresa sanitizada
    cache_key = re.sub(r"[^\w@.-]", "_", email or empresa)[:80]
    INV_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = INV_DIR / f"{cache_key}.json"

    # ── Cache hit ────────────────────────────────────────────────
    if cache_file.exists() and not forzar:
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            print(f"      📂 Investigación cargada desde cache ({cache_file.name})")
            return cached
        except Exception:
            pass

    t0 = time.time()
    print(f"      🔬 Recopilando señales digitales...", end="", flush=True)

    # ── Recopilación de datos digitales ─────────────────────────
    datos_digitales = _recopilar_datos_digitales(lead)
    print(f" ✓")

    print(f"      🧠 Analizando con 7 Maletas (Claude)...", end="", flush=True)

    # ── Llamada a Claude con las 7 Maletas ──────────────────────
    prompt = _construir_prompt_7_maletas(lead, datos_digitales)
    raw = call_claude(SYS_INVESTIGADOR_PROSPECTO, prompt, max_tokens=2000)

    resultado = {}
    if raw:
        # Limpiar posible markdown wrapper
        clean = re.sub(r"```json|```", "", raw).strip()
        # Extraer JSON si hay texto antes/después
        m = re.search(r'\{[\s\S]+\}', clean)
        if m:
            try:
                resultado = json.loads(m.group())
            except json.JSONDecodeError:
                pass

    elapsed = round(time.time() - t0, 1)
    print(f" ✓ ({elapsed}s)")

    # ── Fallback si Claude falló ─────────────────────────────────
    if not resultado:
        nicho_key = lead.get("nicho", "general").lower().replace(" ", "_")
        resultado = _fallback_investigacion(lead, datos_digitales, nicho_key)

    # ── Enriquecer con metadata ──────────────────────────────────
    resultado["_meta"] = {
        "lead_email":       email,
        "lead_empresa":     empresa,
        "lead_nicho":       lead.get("nicho", ""),
        "investigado_at":   datetime.now().isoformat(),
        "duracion_seg":     elapsed,
        "url_analizada":    datos_digitales.get("url_analizada", ""),
        "web_disponible":   datos_digitales.get("html_disponible", False),
        "sin_web_verificada": datos_digitales.get("sin_web_verificada", False),
        "intentos_web":     datos_digitales.get("intentos_realizados", 0),
        "senales":          datos_digitales.get("senales", {}),
    }

    # ── Guardar cache ────────────────────────────────────────────
    cache_file.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    return resultado


def _fallback_investigacion(lead: dict, datos: dict, nicho_key: str) -> dict:
    """Investigación de emergencia cuando Claude no responde."""
    empresa = lead.get("empresa", "")
    nicho   = lead.get("nicho", "empresas")
    nombre  = lead.get("nombre", "")
    senales = datos.get("senales", {})

    tiene = []
    falta = []
    if datos.get("html_disponible"):
        tiene.append(f"Sitio web activo: {datos.get('url_analizada','')}")
    if senales.get("facebook_pixel"):  tiene.append("Facebook Pixel instalado")
    else:                              falta.append("Sin Facebook Pixel — no pueden hacer remarketing")
    if senales.get("google_analytics"): tiene.append("Google Analytics/GTM activo")
    else:                               falta.append("Sin tracking web — no miden el origen de visitas")
    if senales.get("instagram_link"):  tiene.append("Instagram enlazado en la web")
    else:                              falta.append("Sin Instagram enlazado")
    if senales.get("testimonios"):     tiene.append("Testimonios visibles")
    else:                              falta.append("Sin testimonios ni prueba social visible")

    if not tiene:
        tiene = ["Presencia digital básica aún por detectar"]
    if not falta:
        falta = ["No se detectaron carencias — analizar manualmente"]

    dolor  = DOLORES_POR_NICHO.get(nicho_key, f"Dificultad para conseguir clientes en {nicho} de forma predecible")
    deseo  = DESEOS_POR_NICHO.get(nicho_key, f"Crecer y diferenciarse de la competencia en {nicho}")

    return {
        "maleta_1_tiene":   {"resumen": f"{empresa} tiene presencia digital parcial.", "detalle": tiene},
        "maleta_2_falta":   {"resumen": "Carencias detectadas en tracking y conversión.", "detalle": falta},
        "maleta_3_duele":   {"resumen": dolor, "detalle": f"En el sector {nicho}, el principal dolor operativo es {dolor}."},
        "maleta_4_desea":   {"resumen": deseo, "detalle": deseo},
        "maleta_5_frena":   {"resumen": "Creen que ya lo están haciendo bien o que el marketing es caro.", "detalle": "Objeción clásica en negocios con tracción inicial por referidos."},
        "maleta_6_mueve":   {"resumen": "El miedo a quedarse atrás de la competencia que sí está invirtiendo.", "detalle": "Principio de aversión a la pérdida (Kahneman): perder posición duele más que ganar."},
        "maleta_7_angulo":  {
            "resumen": f"Señalar algo concreto y real que notaste en su presencia digital de {empresa}.",
            "asunto_sugerido": f"algo que noté en {empresa[:25]}",
            "primera_linea": f"Revisé {empresa} antes de escribirte y hay algo que me llamó la atención.",
            "por_que_funciona": "La especificidad demuestra que no es spam y activa la curiosidad."
        },
        "resumen_investigacion": (
            f"{nombre or empresa} está en el sector {nicho} en {lead.get('ciudad','')}. "
            f"Su dolor principal es: {dolor}. "
            f"Le falta: {', '.join(falta[:2])}. "
            f"El mejor ángulo: señalar algo concreto de su presencia digital."
        ),
        "nivel_confianza": "bajo" if not datos.get("html_disponible") else "medio",
    }


def formatear_resumen(inv: dict) -> str:
    """Formatea la investigación como texto conciso para usar en prompts."""
    lines = []

    m1 = inv.get("maleta_1_tiene", {})
    m2 = inv.get("maleta_2_falta", {})
    m3 = inv.get("maleta_3_duele", {})
    m4 = inv.get("maleta_4_desea", {})
    m5 = inv.get("maleta_5_frena", {})
    m6 = inv.get("maleta_6_mueve", {})
    m7 = inv.get("maleta_7_angulo", {})

    lines.append(f"MALETA 1 — QUÉ TIENE: {m1.get('resumen','')}")
    if m1.get("detalle"):
        for d in (m1["detalle"] if isinstance(m1["detalle"], list) else [m1["detalle"]])[:3]:
            lines.append(f"  • {d}")

    lines.append(f"\nMALETA 2 — QUÉ LE FALTA: {m2.get('resumen','')}")
    if m2.get("detalle"):
        for d in (m2["detalle"] if isinstance(m2["detalle"], list) else [m2["detalle"]])[:3]:
            lines.append(f"  • {d}")

    lines.append(f"\nMALETA 3 — QUÉ LE DUELE: {m3.get('resumen','')}")
    lines.append(f"  → {m3.get('detalle','')[:200]}")

    lines.append(f"\nMALETA 4 — QUÉ DESEA: {m4.get('resumen','')}")

    lines.append(f"\nMALETA 5 — QUÉ LO FRENA: {m5.get('resumen','')}")

    lines.append(f"\nMALETA 6 — QUÉ LO MUEVE: {m6.get('resumen','')}")
    lines.append(f"  → {m6.get('detalle','')[:200]}")

    lines.append(f"\nMALETA 7 — ÁNGULO DE ENTRADA:")
    lines.append(f"  Asunto sugerido: \"{m7.get('asunto_sugerido','')}\"")
    lines.append(f"  Primera línea: \"{m7.get('primera_linea','')}\"")
    lines.append(f"  Por qué funciona: {m7.get('por_que_funciona','')}")

    lines.append(f"\nRESUMEN: {inv.get('resumen_investigacion','')}")
    lines.append(f"Confianza: {inv.get('nivel_confianza','medio').upper()}")

    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(
        description="IM Lead Investigator — 7 Maletas del Prospecto",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EJEMPLOS:
  # Investigar por email (busca en leads DB o CSV)
  python agent/lead_investigator.py --email joseg09.dg@gmail.com

  # Investigar con datos directos
  python agent/lead_investigator.py --lead '{"nombre":"Dr. Lopez","empresa":"Clinica Lopez","email":"x@x.com","nicho":"odontologos","ciudad":"Medellin","url":"https://clinicalopez.com"}'

  # Forzar re-investigación (ignorar cache)
  python agent/lead_investigator.py --email x@x.com --forzar
        """
    )
    p.add_argument("--email",   help="Email del lead a investigar")
    p.add_argument("--lead",    help="JSON string con datos del lead")
    p.add_argument("--forzar",  action="store_true", help="Re-investigar aunque exista cache")
    p.add_argument("--json",    action="store_true", help="Mostrar JSON completo en lugar del resumen")
    args = p.parse_args()

    lead_data = {}

    if args.lead:
        try:
            lead_data = json.loads(args.lead)
        except json.JSONDecodeError as e:
            print(f"Error parseando --lead JSON: {e}")
            sys.exit(1)

    elif args.email:
        # Buscar en platform.db primero
        db_path = BASE / "logs" / "platform.db"
        if db_path.exists():
            try:
                import sqlite3
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM leads WHERE email=? LIMIT 1", (args.email,)
                ).fetchone()
                conn.close()
                if row:
                    lead_data = dict(row)
            except Exception:
                pass

        # Si no está en DB, crear con solo el email
        if not lead_data:
            lead_data = {"email": args.email, "nombre": "", "empresa": "", "nicho": "general"}
            print(f"  ⚠  Lead no encontrado en DB. Investigando con datos mínimos.")

    else:
        p.print_help()
        sys.exit(0)

    print(f"\n{'═'*56}")
    print(f"  IM LEAD INVESTIGATOR — 7 Maletas del Prospecto")
    print(f"  Lead:  {lead_data.get('nombre','') or lead_data.get('email','')}")
    print(f"  Empresa: {lead_data.get('empresa','N/A')}")
    print(f"  Nicho:   {lead_data.get('nicho','N/A')}")
    print(f"{'═'*56}\n")

    t_total = time.time()
    resultado = investigar(lead_data, forzar=args.forzar)
    elapsed = round(time.time() - t_total, 1)

    print()
    if args.json:
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
    else:
        print(formatear_resumen(resultado))

    print(f"\n  Tiempo total: {elapsed}s")
    cache_key = re.sub(r"[^\w@.-]", "_", lead_data.get("email","") or lead_data.get("empresa",""))[:80]
    print(f"  Cache: {INV_DIR / (cache_key + '.json')}")
    print()


if __name__ == "__main__":
    main()
