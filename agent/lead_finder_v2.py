#!/usr/bin/env python3
"""
IM Lead Finder v2 — Intelligent Markets
Scraping sin APIs + Apollo.io opcional + Artistas Independientes
"""

import os, re, csv, time, random, json, argparse, sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus, urljoin

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# ── Dependencias opcionales ──────────────────────────────────────
try:
    import requests
    from bs4 import BeautifulSoup
    SCRAPING_OK = True
except ImportError:
    SCRAPING_OK = False

# ── Flush DNS (Windows pierde caché entre procesos) ──────────────
import subprocess as _sp, platform as _plat
if _plat.system() == "Windows":
    try:
        _sp.run(["ipconfig", "/flushdns"], capture_output=True, timeout=5)
    except Exception:
        pass

# ── Cargar .env antes de leer las keys ──────────────────────────
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

APOLLO_KEY     = os.environ.get("APOLLO_API_KEY", "")
GMAPS_KEY      = os.environ.get("GOOGLE_MAPS_API_KEY", "")
SPOTIFY_CLIENT_ID     = os.environ.get("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
LASTFM_API_KEY        = os.environ.get("LASTFM_API_KEY", "")
# El scraping directo de HTML de Google/Bing/DuckDuckGo/Spotify está roto desde
# que esos sitios exigen JavaScript o bloquean bots (verificado 2026-09-17).
# Se deja apagado por defecto para no perder tiempo. GOOGLE_MAPS_API_KEY y
# SPOTIFY_CLIENT_ID/SECRET son las fuentes reales y confiables ahora mismo.
ENABLE_LEGACY_SCRAPING = os.environ.get("ENABLE_LEGACY_SCRAPING", "false").lower() == "true"

# ════════════════════════════════════════════════════════════════
# CONFIGURACIÓN DE NICHOS
# ════════════════════════════════════════════════════════════════

NICHOS = {
    # ── SALUD ────────────────────────────────────────────────────
    "odontologos": {
        "label": "🦷 Odontólogos",
        "vertical": "empresas",
        "template": "empresa_salud",
        "queries_google": [
            '"{city}" odontólogo consultorio dental contacto correo',
            '"{city}" clínica dental "agenda tu cita" email',
            '"{city}" odontología estética "@" sitio:*.com',
            'odontólogo "{city}" instagram contacto whatsapp',
            '"{city}" ortodoncia implantes dentales contacto',
        ],
        "directorios": [
            "https://www.doctoralia.com.co/odontologos/{city_slug}",
            "https://www.doctoralia.es/odontologos/{city_slug}",
            "https://www.google.com/maps/search/odontólogos+{city_encoded}",
        ],
        "apollo_titles": ["Dentist", "Odontólogo", "Dental Clinic Owner", "Director Clínica Dental"],
        "apollo_industry": "Medical Practice",
    },
    "dermatologo": {
        "label": "💆 Dermatólogos",
        "vertical": "empresas",
        "template": "empresa_salud",
        "queries_google": [
            '"{city}" dermatólogo clínica estética contacto email',
            '"{city}" dermatología cosméticos "agenda" correo',
            '"{city}" dermatólogo instagram DM contacto',
        ],
        "directorios": [
            "https://www.doctoralia.com.co/dermatologo/{city_slug}",
        ],
        "apollo_titles": ["Dermatologist", "Dermatólogo", "Clinic Director"],
        "apollo_industry": "Medical Practice",
    },
    "psicologo": {
        "label": "🧠 Psicólogos",
        "vertical": "empresas",
        "template": "empresa_salud",
        "queries_google": [
            '"{city}" psicólogo online consulta email contacto',
            '"{city}" psicología clínica "agenda cita" correo',
            '"{city}" terapeuta psicólogo instagram contacto',
        ],
        "directorios": [
            "https://www.doctoralia.com.co/psicologo/{city_slug}",
        ],
        "apollo_titles": ["Psychologist", "Psicólogo", "Therapist", "Mental Health"],
        "apollo_industry": "Mental Health Care",
    },
    "fisioterapeuta": {
        "label": "💪 Fisioterapeutas",
        "vertical": "empresas",
        "template": "empresa_salud",
        "queries_google": [
            '"{city}" fisioterapia centro rehabilitación email',
            '"{city}" fisioterapeuta contacto correo cita',
        ],
        "directorios": [
            "https://www.doctoralia.com.co/fisioterapeuta/{city_slug}",
        ],
        "apollo_titles": ["Physical Therapist", "Fisioterapeuta", "Rehab Center Owner"],
        "apollo_industry": "Health, Wellness and Fitness",
    },

    # ── EMPRESAS ────────────────────────────────────────────────
    "agencia_viajes": {
        "label": "✈️ Agencias de Viajes",
        "vertical": "empresas",
        "template": "empresa_viajes",
        "queries_google": [
            '"{city}" agencia de viajes email contacto ventas',
            '"{city}" travel agency "info@" OR "ventas@"',
            '"{city}" operadora turística contacto correo',
            'site:linkedin.com "gerente" "agencia de viajes" "{city}"',
        ],
        "directorios": [
            "https://www.cotelco.org/directorio",
            "https://www.anato.org/directorio",
        ],
        "apollo_titles": ["Travel Agency Owner", "Gerente Agencia Viajes", "CEO Travel", "Director Comercial"],
        "apollo_industry": "Leisure, Travel & Tourism",
    },
    "seguros": {
        "label": "🛡️ Seguros",
        "vertical": "empresas",
        "template": "empresa_seguros",
        "queries_google": [
            '"{city}" corredor de seguros email contacto',
            '"{city}" agencia seguros "asesor" correo',
            'site:linkedin.com "{city}" "broker seguros" OR "asesor seguros"',
            '"{city}" seguros vida salud auto contacto ejecutivo',
        ],
        "directorios": [
            "https://www.fasecolda.com/directorio",
        ],
        "apollo_titles": ["Insurance Broker", "Corredor Seguros", "Asesor Seguros", "Insurance Agent"],
        "apollo_industry": "Insurance",
    },
    "autos_alta_gama": {
        "label": "🚗 Carros Alta Gama",
        "vertical": "empresas",
        "template": "empresa_autos",
        "queries_google": [
            '"{city}" concesionario BMW Mercedes Audi contacto gerente',
            '"{city}" venta carros lujo "director comercial" email',
            '"{city}" importadora vehículos premium contacto',
            'site:linkedin.com "{city}" "gerente" "concesionario" OR "automotriz"',
        ],
        "directorios": [],
        "apollo_titles": ["Dealer Principal", "Gerente Concesionario", "Sales Director Automotive"],
        "apollo_industry": "Automotive",
    },

    # ── MÚSICA ──────────────────────────────────────────────────
    "sello_musical": {
        "label": "🎵 Sellos Musicales",
        "vertical": "music",
        "template": "music_sello",
        "queries_google": [
            '"{city}" sello discográfico indie email demos contacto',
            '"{country}" sello musical urbano reggaeton rap "contáctanos"',
            'site:linkedin.com "{country}" "sello discográfico" OR "record label" director',
            '"{country}" disquera independiente A&R email',
            '"{city}" sello musical Instagram contacto DM',
        ],
        "directorios": [
            "https://www.aei.es/directorio-sellos",  # España
            "https://www.ifpi.org/member-labels",
        ],
        "apollo_titles": ["Label Owner", "A&R Manager", "Sello Discográfico", "Record Label CEO", "Music Director"],
        "apollo_industry": "Entertainment",
    },
    "manager_musical": {
        "label": "🎤 Managers / Booking",
        "vertical": "music",
        "template": "music_manager",
        "queries_google": [
            '"{country}" manager artistas urbanos email representación',
            '"{city}" booking manager música independiente contacto',
            'site:linkedin.com "{country}" "manager artistas" OR "music manager"',
            '"{country}" management musical "contacto" OR "info@"',
        ],
        "directorios": [],
        "apollo_titles": ["Artist Manager", "Manager Musical", "Booking Agent", "Talent Manager"],
        "apollo_industry": "Entertainment",
    },
    "artista_independiente": {
        "label": "🎙️ Artistas Independientes",
        "vertical": "music",
        "template": "music_artista",
        "queries_google": [
            '"{country}" artista independiente sin sello Spotify contacto booking',
            '"{city}" cantante independiente urbano email manager',
            'site:distrokid.com OR site:tunecore.com artista "{country}"',
            '"{country}" artista urbano indie sin representación Instagram DM',
            '"{city}" productor musical independiente colaboraciones email',
            'spotify artist "{country}" "sin sello" OR "independent" contacto',
        ],
        "directorios": [
            "https://open.spotify.com/search/{query}/artists",
            "https://soundcloud.com/search/people?q={query}",
        ],
        "apollo_titles": ["Independent Artist", "Artista Musical", "Singer Songwriter", "Music Producer"],
        "apollo_industry": "Entertainment",
        "instagram_hashtags": [
            "#artista{country_tag}",
            "#musicaindependiente",
            "#sindsello",
            "#artistaurbano{country_tag}",
            "#musicacolombiana",
        ],
        "spotify_searches": [
            "{country} independent artist",
            "artista independiente {country}",
            "urbano indie {city}",
        ],
    },
    "estudio_grabacion": {
        "label": "🎚️ Estudios de Grabación",
        "vertical": "music",
        "template": "music_sello",
        "queries_google": [
            '"{city}" estudio de grabación profesional email tarifas contacto',
            '"{city}" recording studio "reservas" OR "booking" correo',
            '"{city}" estudio música Instagram contacto',
        ],
        "directorios": [],
        "apollo_titles": ["Studio Owner", "Recording Studio Manager", "Dueño Estudio Grabación"],
        "apollo_industry": "Entertainment",
    },
}

# ════════════════════════════════════════════════════════════════
# HEADERS ROTATIVOS (anti-bot)
# ════════════════════════════════════════════════════════════════

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]

EMAIL_RE = re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b')
PHONE_RE = re.compile(r'(?:\+?(?:57|52|34|1))?[\s\-\.]?(?:\d[\s\-\.]?){7,11}')

NOISE_EMAILS = {
    "example.com", "test.com", "email.com", "domain.com", "correo.com",
    "sentry.io", "wix.com", "wordpress.com", "cloudflare.com", "amazonaws.com",
    "google.com", "facebook.com", "instagram.com", "tiktok.com", "youtube.com",
    "schema.org", "w3.org", "apple.com", "microsoft.com",
}

def random_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.google.com/",
    }

def human_delay(base=2.0, spread=4.0):
    t = base + random.random() * spread
    time.sleep(t)

def clean_emails(raw):
    result = []
    for e in EMAIL_RE.findall(raw):
        domain = e.split("@")[1].lower()
        if domain not in NOISE_EMAILS and len(e) < 80:
            result.append(e.lower())
    return list(set(result))

# ════════════════════════════════════════════════════════════════
# SCRAPING — MOTOR PRINCIPAL (sin APIs)
# ════════════════════════════════════════════════════════════════

def fetch(url, timeout=12):
    if not SCRAPING_OK:
        return None
    try:
        r = requests.get(url, headers=random_headers(), timeout=timeout, allow_redirects=True)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return None

def google_search(query, lang="es", num=10):
    """Búsqueda en Google sin API — respeta delays"""
    if not SCRAPING_OK:
        return []
    url = f"https://www.google.com/search?q={quote_plus(query)}&hl={lang}&num={num}"
    html = fetch(url)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.select("a[href]"):
        href = a["href"]
        if href.startswith("/url?q="):
            href = href[7:].split("&")[0]
        if href.startswith("http") and "google" not in href and "youtube" not in href:
            links.append(href)
    return list(dict.fromkeys(links))[:num]

def bing_search(query, num=10):
    """Bing como alternativa cuando Google bloquea"""
    if not SCRAPING_OK:
        return []
    url = f"https://www.bing.com/search?q={quote_plus(query)}&count={num}"
    html = fetch(url)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.select("li.b_algo h2 a"):
        href = a.get("href", "")
        if href.startswith("http") and "bing" not in href and "microsoft" not in href:
            links.append(href)
    return list(dict.fromkeys(links))[:num]

def duckduckgo_search(query, num=10):
    """DuckDuckGo como backup adicional"""
    if not SCRAPING_OK:
        return []
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    html = fetch(url)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.select("a.result__url"):
        href = a.get("href", "")
        if href.startswith("http"):
            links.append(href)
    return list(dict.fromkeys(links))[:num]

def multi_search(query, num=10):
    """Intenta Google → Bing → DuckDuckGo en cascada"""
    results = google_search(query, num=num)
    if len(results) < 3:
        results += bing_search(query, num=num)
    if len(results) < 3:
        results += duckduckgo_search(query, num=num)
    return list(dict.fromkeys(results))[:num]

def extract_contact_from_page(url):
    """Extrae emails, teléfonos y nombre del negocio de una URL"""
    html = fetch(url)
    if not html:
        return {}

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "head", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)
    emails = clean_emails(text)

    # También buscar en atributos href mailto:
    for a in soup.find_all("a", href=True):
        if "mailto:" in a["href"].lower():
            mail = a["href"].replace("mailto:", "").strip().split("?")[0]
            if "@" in mail:
                emails.append(mail.lower())
    emails = list(set(emails))

    phones = list(set([p.strip() for p in PHONE_RE.findall(text)
                       if len(re.sub(r'\D', '', p)) >= 7]))[:3]

    # Nombre del negocio
    name = ""
    if soup.title:
        name = (soup.title.string or "").strip()[:100]
    if not name:
        h1 = soup.find("h1")
        if h1:
            name = h1.get_text(strip=True)[:100]

    # Redes sociales
    socials = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        if "instagram.com" in href:
            socials["instagram"] = a["href"]
        elif "facebook.com" in href:
            socials["facebook"] = a["href"]
        elif "linkedin.com" in href:
            socials["linkedin"] = a["href"]

    return {
        "name": name,
        "emails": emails[:5],
        "phones": phones,
        "socials": socials,
        "url": url,
    }

def enrich_email_from_web(lead, verbose=True):
    """
    Visita la web del lead (url) y subpáginas de contacto para extraer email.
    Modifica el lead in-place. Retorna True si encontró email.
    """
    url = lead.get("url", "")
    if not url or lead.get("email"):
        return bool(lead.get("email"))

    CONTACT_PATHS = ["/contacto", "/contact", "/contactenos", "/contactenos.html",
                     "/nosotros", "/about", "/quienes-somos", "/contact-us"]

    found_email = ""
    found_instagram = lead.get("instagram", "")

    for path in [""] + CONTACT_PATHS:
        target = url.rstrip("/") + path if path else url
        try:
            info = extract_contact_from_page(target)
        except Exception:
            continue

        if info.get("emails"):
            found_email = info["emails"][0]
            if not found_instagram and info.get("socials", {}).get("instagram"):
                found_instagram = info["socials"]["instagram"]
            break

        if not found_instagram and info.get("socials", {}).get("instagram"):
            found_instagram = info["socials"]["instagram"]

        if path == "":
            time.sleep(random.uniform(0.8, 1.8))

    if found_email:
        lead["email"] = found_email
        if verbose:
            empresa = lead.get("empresa", "?")[:35]
            print(f"     📧 {empresa} → {found_email}")
    if found_instagram:
        lead["instagram"] = found_instagram

    return bool(found_email)


def scrape_doctoralia(nicho_slug, city_slug, country="co"):
    """Extrae profesionales de Doctoralia"""
    leads = []
    base = f"https://www.doctoralia.com.{'co' if country=='co' else 'es'}"
    nicho_map = {
        "odontologos": "dentistas",
        "dermatologo": "dermatologo",
        "psicologo": "psicologo",
        "fisioterapeuta": "fisioterapeuta",
    }
    path = nicho_map.get(nicho_slug, nicho_slug)
    url = f"{base}/{path}/{city_slug}"

    html = fetch(url)
    if not html:
        return leads

    soup = BeautifulSoup(html, "html.parser")
    for card in soup.select("div[data-id], article.doctor-card, div.doctor-item")[:30]:
        name_el = card.select_one("h3, h2, .doctor-name, [itemprop='name']")
        name = name_el.get_text(strip=True) if name_el else ""
        profile_a = card.select_one("a[href*='/doctor/']")
        profile_url = urljoin(base, profile_a["href"]) if profile_a else ""

        if name:
            leads.append({
                "nombre": name,
                "empresa": f"Consulta {name}",
                "email": "",
                "telefono": "",
                "ciudad": city_slug.replace("-", " ").title(),
                "pais": "Colombia" if country == "co" else "España",
                "nicho": nicho_slug,
                "url": profile_url,
                "fuente": "doctoralia",
            })
    return leads

_spotify_token_cache = {"token": None, "expires": 0}

def _spotify_get_token():
    """Client Credentials flow — requiere SPOTIFY_CLIENT_ID/SECRET (gratis en developer.spotify.com)"""
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        return None
    now = time.time()
    if _spotify_token_cache["token"] and now < _spotify_token_cache["expires"]:
        return _spotify_token_cache["token"]
    try:
        r = requests.post(
            "https://accounts.spotify.com/api/token",
            data={"grant_type": "client_credentials"},
            auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET),
            timeout=10,
        )
        data = r.json()
        token = data.get("access_token")
        if token:
            _spotify_token_cache["token"] = token
            _spotify_token_cache["expires"] = now + data.get("expires_in", 3600) - 60
            return token
    except Exception:
        pass
    return None

def scrape_spotify_artists(query, country="CO", max_results=20):
    """Busca artistas vía Spotify Web API oficial (Client Credentials).
    No da email/contacto (Spotify no lo expone) — sí da nombre, género,
    popularidad y seguidores reales para priorizar a quién contactar."""
    token = _spotify_get_token()
    if not token:
        return []

    leads = []
    try:
        r = requests.get(
            "https://api.spotify.com/v1/search",
            headers={"Authorization": f"Bearer {token}"},
            params={"q": query, "type": "artist", "market": country[:2].upper(), "limit": min(max_results, 50)},
            timeout=10,
        )
        data = r.json()
        items = data.get("artists", {}).get("items", [])
        for item in items[:max_results]:
            followers = item.get("followers", {}).get("total", 0)
            leads.append({
                "nombre": item.get("name", ""),
                "empresa": f"Artista Independiente — {item.get('name', '')}",
                "email": "",
                "spotify_url": item.get("external_urls", {}).get("spotify", ""),
                "followers": followers,
                "popularity": item.get("popularity", 0),
                "generos": ", ".join(item.get("genres", [])[:3]),
                "ciudad": "",
                "pais": country,
                "nicho": "artista_independiente",
                "fuente": "spotify_api",
            })
    except Exception as e:
        print(f"  ⚠️  Spotify API error: {e}")
    return leads

# ════════════════════════════════════════════════════════════════
# LAST.FM — LEADS DE ARTISTAS CALIFICADOS (gratis, reemplaza a Spotify)
# ════════════════════════════════════════════════════════════════
# Filtra por banda de oyentes globales reales (no el conteo geo-sesgado de
# geo.gettopartists): suficiente tracción/plata para pagar, pero sin la
# maquinaria de un sello grande detrás (esos no necesitan tus servicios).
# Calibrado 2026-09-17: Bad Bunny ~2.7M oyentes (sello grande, no califica),
# Ryan Castro ~412K, Blessd ~288K, Dei V ~141K (independientes con tracción real).

LASTFM_TAGS_URBANO = [
    "reggaeton", "trap latino", "urbano", "reggaeton colombiano",
    "colombian hip hop", "musica urbana",
]

LASTFM_QUALIFY_MIN = 8000       # menos que esto = casi seguro sin presupuesto real
LASTFM_QUALIFY_MAX = 40000      # más que esto = ya tiene sello/equipo grande detrás
# Bajado de 120,000 a 40,000 el 2026-09-18: se verificó en vivo que
# "Amenazzy" con 118,617 oyentes en Last.fm es una cuenta VERIFICADA de
# Instagram con 4.4 millones de seguidores — Last.fm subregistra al público
# hispanohablante en reggaeton/trap latino, así que el techo viejo dejaba
# pasar estrellas establecidas como si fueran independientes. Aun con este
# techo mas bajo, TODO artista debe verificarse en Instagram (seguidores +
# verificado) antes de escribirle — ver verificar_artista_instagram().
                                 # (bajado de 350k — verificado 2026-09-17: Jowell&Randy con
                                 # 274k ya tenía booking agency profesional y Latin Grammy noms)

def _lastfm_get(method, **params):
    if not LASTFM_API_KEY:
        return {}
    try:
        r = requests.get(
            "https://ws.audioscrobbler.com/2.0/",
            params={"method": method, "api_key": LASTFM_API_KEY, "format": "json", **params},
            timeout=15,
        )
        return r.json()
    except Exception:
        return {}

def search_lastfm_artists(nicho_key, city, country, max_results=20, tags=None):
    """Descubre artistas con tracción real vía Last.fm (gratis, sin tarjeta).
    Recorre charts de género y filtra por oyentes globales reales para
    quedarse con el punto dulce: tiene plata, no tiene sello grande."""
    if not LASTFM_API_KEY:
        return []

    tags = tags or LASTFM_TAGS_URBANO
    candidatos = {}  # nombre -> None (dedup, preserva orden de aparición)
    for tag in tags:
        data = _lastfm_get("tag.gettopartists", tag=tag, limit=200)
        for a in data.get("topartists", {}).get("artist", []):
            name = a.get("name", "")
            if name:
                candidatos.setdefault(name, None)

    # Paginas de colaboracion ("Fulano & Mengano", "Fulano x Mengano", "feat.")
    # tienen su propio conteo de oyentes en Last.fm, separado y mucho mas bajo
    # que la fama real de cada artista involucrado -> se cuelan superestrellas
    # (ej. "J Balvin & Bad Bunny") como si fueran independientes sin sello.
    _COLAB_RE = re.compile(r"\s(&|x|vs\.?|feat\.?|featuring)\s", re.IGNORECASE)

    leads = []
    for name in candidatos:
        if len(leads) >= max_results:
            break
        if _COLAB_RE.search(name):
            continue
        info = _lastfm_get("artist.getinfo", artist=name)
        art = info.get("artist")
        if not art:
            continue
        stats = art.get("stats", {})
        try:
            listeners = int(stats.get("listeners", 0))
            playcount = int(stats.get("playcount", 0))
        except (TypeError, ValueError):
            continue
        if not (LASTFM_QUALIFY_MIN <= listeners <= LASTFM_QUALIFY_MAX):
            continue

        generos = ", ".join(t.get("name", "") for t in art.get("tags", {}).get("tag", [])[:3])
        engagement = round(playcount / listeners, 1) if listeners else 0

        leads.append({
            "nombre":      "",
            "empresa":     f"Artista Independiente — {name}",
            "email":       "",
            "telefono":    "",
            "instagram":   "",
            "linkedin":    "",
            "ciudad":      city,
            "pais":        country,
            "nicho":       nicho_key,
            "vertical":    "music",
            "url":         art.get("url", ""),
            "fuente":      "lastfm",
            "oyentes":     listeners,
            "reproducciones": playcount,
            "engagement_por_oyente": engagement,
            "generos":     generos,
            "fecha":       datetime.now().strftime("%Y-%m-%d"),
            # NUNCA "pendiente" (listo para contactar) — el numero de oyentes
            # de Last.fm por si solo NO es confiable para saber si el artista
            # ya tiene sello/equipo grande (verificado en vivo 2026-09-18:
            # "Amenazzy" y "Tomasa del Real" pasaron el filtro de oyentes y
            # resultaron ser cuentas verificadas de Instagram con 100k-4.4M
            # seguidores). Todo artista debe verificarse a mano en Instagram
            # (seguidores + verificado) antes de escribirle. Solo despues de
            # esa verificacion se cambia el status a "pendiente".
            "status":      "pendiente_verificacion_ig",
        })

    leads.sort(key=lambda l: -l["oyentes"])
    return leads

# ════════════════════════════════════════════════════════════════
# APOLLO.IO API — ENRIQUECIMIENTO OPCIONAL
# ════════════════════════════════════════════════════════════════

def apollo_search(nicho_key, city, country, max_results=50):
    """
    Búsqueda de leads vía Apollo.io API.
    Requiere: export APOLLO_API_KEY="tu-key"
    Planes: https://www.apollo.io/pricing (free: 50/mes, paid: ilimitado)
    """
    if not APOLLO_KEY:
        return [], "Apollo.io no configurado. Export APOLLO_API_KEY=tu-key"

    nicho = NICHOS.get(nicho_key, {})
    titles = nicho.get("apollo_titles", [])
    industry = nicho.get("apollo_industry", "")

    payload = {
        "per_page": min(max_results, 100),
        "page": 1,
        "person_titles": titles,
        "organization_industry_tag_values": [industry] if industry else [],
        "person_locations": [city, country],
        "contact_email_status": ["verified", "likely to engage"],
    }

    try:
        r = requests.post(
            "https://api.apollo.io/v1/mixed_people/search",
            headers={
                "Content-Type": "application/json",
                "Cache-Control": "no-cache",
                "X-Api-Key": APOLLO_KEY,
            },
            json=payload,
            timeout=15,
        )
        data = r.json()
        people = data.get("people", [])
        leads = []
        for p in people:
            leads.append({
                "nombre": f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
                "empresa": p.get("organization", {}).get("name", ""),
                "email": p.get("email", ""),
                "telefono": p.get("phone_numbers", [{}])[0].get("sanitized_number", "") if p.get("phone_numbers") else "",
                "linkedin": p.get("linkedin_url", ""),
                "titulo": p.get("title", ""),
                "ciudad": city,
                "pais": country,
                "nicho": nicho_key,
                "fuente": "apollo",
            })
        return leads, f"Apollo: {len(leads)} leads encontrados"
    except Exception as e:
        return [], f"Error Apollo: {e}"

# ════════════════════════════════════════════════════════════════
# OPENSTREETMAP — GRATIS, SIN API KEY, SIN TARJETA
# ════════════════════════════════════════════════════════════════
# Fuente de respaldo cuando no hay GOOGLE_MAPS_API_KEY. Cobertura menor
# que Google Maps pero 100% gratis y sin registro. Verificado 2026-09-17.

OSM_TAGS = {
    "odontologos":     [("amenity", "dentist")],
    "dermatologo":     [("healthcare", "dermatologist"), ("amenity", "clinic")],
    "psicologo":       [("healthcare", "psychotherapist"), ("healthcare", "psychologist")],
    "fisioterapeuta":  [("healthcare", "physiotherapist")],
    "agencia_viajes":  [("shop", "travel_agency")],
    "seguros":         [("office", "insurance")],
    "autos_alta_gama": [("shop", "car")],
}

_osm_bbox_cache = {}

def _osm_geocode_bbox(city, country):
    """Geocodifica una ciudad a bounding box vía Nominatim (gratis, sin key)."""
    cache_key = f"{city}|{country}"
    if cache_key in _osm_bbox_cache:
        return _osm_bbox_cache[cache_key]
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": f"{city}, {country}", "format": "json", "limit": 1},
            headers={"User-Agent": "IMSystem-LeadFinder/1.0"},
            timeout=20,
        )
        data = r.json()
        if not data:
            return None
        bb = data[0]["boundingbox"]  # [south, north, west, east]
        bbox = f"{bb[0]},{bb[2]},{bb[1]},{bb[3]}"
        _osm_bbox_cache[cache_key] = bbox
        return bbox
    except Exception:
        return None

def search_openstreetmap(nicho_key, city, country, max_results=30):
    """Busca negocios en OpenStreetMap (Overpass API) — gratis, sin key."""
    tags = OSM_TAGS.get(nicho_key)
    if not tags:
        return []

    bbox = _osm_geocode_bbox(city, country)
    if not bbox:
        return []

    nicho_data = NICHOS.get(nicho_key, {})
    clauses = "".join(
        f'node["{k}"="{v}"]({bbox});way["{k}"="{v}"]({bbox});'
        for k, v in tags
    )
    query = f'[out:json][timeout:25];({clauses});out center {max_results};'

    # overpass-api.de se cae seguido (servidor comunitario sobrecargado) —
    # reintenta con mirrors alternos antes de rendirse.
    mirrors = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass.openstreetmap.ru/api/interpreter",
    ]
    elements = None
    last_err = None
    for attempt in range(2):  # 2 rondas completas por si el servidor está saturado (504)
        for mirror in mirrors:
            try:
                r = requests.post(
                    mirror,
                    data={"data": query},
                    headers={"User-Agent": "IMSystem-LeadFinder/1.0"},
                    timeout=35,
                )
                if r.status_code == 200:
                    elements = r.json().get("elements", [])
                    break
                last_err = f"{mirror} -> HTTP {r.status_code}"
            except Exception as e:
                last_err = f"{mirror} -> {e}"
                continue
        if elements is not None:
            break
        if attempt == 0:
            time.sleep(8)  # da tiempo al servidor sobrecargado a liberarse
    if elements is None:
        print(f"  ⚠️  OpenStreetMap: servidor gratis saturado, no respondió. Último error: {last_err}")
        return []

    leads = []
    seen = set()
    for el in elements:
        t = el.get("tags", {})
        name = t.get("name", "")
        if not name or name in seen:
            continue
        seen.add(name)
        addr_parts = [t.get(f"addr:{p}") for p in ("street", "housenumber", "city")]
        _tel = t.get("contact:phone") or t.get("phone", "")
        leads.append({
            "nombre":    "",
            "empresa":   name,
            "email":     t.get("contact:email") or t.get("email", ""),
            "telefono":  _tel,
            "whatsapp":  telefono_a_whatsapp(_tel, country),
            "instagram": "",
            "linkedin":  "",
            "ciudad":    city,
            "pais":      country,
            "nicho":     nicho_key,
            "vertical":  nicho_data.get("vertical", "empresas"),
            "url":       t.get("contact:website") or t.get("website", ""),
            "fuente":    "openstreetmap",
            "direccion": ", ".join(p for p in addr_parts if p),
            "fecha":     datetime.now().strftime("%Y-%m-%d"),
            "status":    "pendiente",
        })
        if len(leads) >= max_results:
            break

    return leads

# ════════════════════════════════════════════════════════════════
# MOTOR PRINCIPAL DE BÚSQUEDA
# ════════════════════════════════════════════════════════════════
# GOOGLE MAPS PLACES API
# ════════════════════════════════════════════════════════════════

# Tope diario de llamadas a Google Places — protege el crédito gratis de
# Google ($200 USD/mes). Cada Text Search cuesta ~$0.032 USD; 150/día en
# días hábiles se queda muy por debajo del límite gratis todo el mes.
GMAPS_DAILY_CALL_LIMIT = 150

def _gmaps_calls_hoy():
    """Lee/actualiza el contador de llamadas a Places API del día de hoy."""
    contador_file = Path(__file__).parent.parent / "logs" / "gmaps_calls.json"
    contador_file.parent.mkdir(exist_ok=True)
    hoy = datetime.now().strftime("%Y-%m-%d")
    data = {}
    if contador_file.exists():
        try:
            data = json.loads(contador_file.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    if data.get("fecha") != hoy:
        data = {"fecha": hoy, "llamadas": 0}
    return data, contador_file

def _gmaps_registrar_llamada():
    data, contador_file = _gmaps_calls_hoy()
    data["llamadas"] += 1
    contador_file.write_text(json.dumps(data), encoding="utf-8")
    return data["llamadas"]

def search_google_maps(nicho_key, city, country, max_results=30):
    """
    Busca negocios usando Places API (New) — Text Search.
    Requiere GOOGLE_MAPS_API_KEY en .env con Places API (New) habilitada.
    Docs: https://developers.google.com/maps/documentation/places/web-service/text-search
    """
    if not GMAPS_KEY:
        return []
    if not SCRAPING_OK:
        return []

    data, _ = _gmaps_calls_hoy()
    if data["llamadas"] >= GMAPS_DAILY_CALL_LIMIT:
        print(f"  ⚠️  Tope diario de Google Places alcanzado ({GMAPS_DAILY_CALL_LIMIT}/día) — saltando para proteger el crédito gratis.")
        return []

    nicho_data = NICHOS.get(nicho_key, {})
    label_clean = (nicho_data.get("label", nicho_key)
                   .replace("🦷","").replace("🎤","").replace("🎵","")
                   .replace("🏋","").replace("✈","").strip())

    query = f"{label_clean} en {city} {country}"
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GMAPS_KEY,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.nationalPhoneNumber,places.websiteUri,places.id",
    }
    results = []
    page_token = None

    try:
        for _ in range(3):
            body = {"textQuery": query, "languageCode": "es", "maxResultCount": min(max_results, 20)}
            if page_token:
                body["pageToken"] = page_token

            r = requests.post(url, headers=headers, json=body, timeout=10)
            _gmaps_registrar_llamada()
            data = r.json()

            if "error" in data:
                print(f"  ⚠️  Google Maps error: {data['error'].get('message','')[:80]}")
                break

            for place in data.get("places", []):
                if len(results) >= max_results:
                    break
                lead = _gmaps_place_to_lead_new(place, nicho_key, city, country)
                results.append(lead)

            page_token = data.get("nextPageToken")
            if not page_token or len(results) >= max_results:
                break

    except Exception as e:
        print(f"  ⚠️  Google Maps error: {e}")

    return results


def telefono_a_whatsapp(telefono, country="Colombia"):
    """Convierte un teléfono a link directo de WhatsApp (wa.me) — solo si
    es celular (en Colombia: 10 dígitos, empieza en 3). Los fijos (604, 601...)
    no tienen WhatsApp, se dejan vacíos."""
    if not telefono:
        return ""
    digitos = re.sub(r"\D", "", telefono)
    if country.lower() in ("colombia", "co"):
        if len(digitos) == 10 and digitos.startswith("3"):
            return f"https://wa.me/57{digitos}"
        return ""  # fijo — sin WhatsApp
    # Otros países: asume que ya viene completo si tiene 11+ dígitos
    if len(digitos) >= 11:
        return f"https://wa.me/{digitos}"
    return ""

def _gmaps_place_to_lead_new(place, nicho_key, city, country):
    """Convierte resultado de Places API (New) a formato lead."""
    nicho_data = NICHOS.get(nicho_key, {})
    empresa = place.get("displayName", {}).get("text", "") if isinstance(place.get("displayName"), dict) else place.get("displayName", "")
    telefono = place.get("nationalPhoneNumber", "")
    web_url  = place.get("websiteUri", "")
    place_id = place.get("id", "")

    return {
        "nombre":    "",
        "empresa":   empresa,
        "email":     "",
        "telefono":  telefono,
        "whatsapp":  telefono_a_whatsapp(telefono, country),
        "instagram": "",
        "linkedin":  "",
        "ciudad":    city,
        "pais":      country,
        "nicho":     nicho_key,
        "vertical":  nicho_data.get("vertical", "empresas"),
        "url":       web_url,
        "fuente":    "google_maps",
        "direccion": place.get("formattedAddress", ""),
        "gmaps_id":  place_id,
    }


def _gmaps_place_to_lead(place, nicho_key, city, country):
    nicho_data = NICHOS.get(nicho_key, {})
    lead = {
        "nombre":    "",
        "empresa":   place.get("name", ""),
        "email":     "",
        "telefono":  "",
        "instagram": "",
        "linkedin":  "",
        "ciudad":    city,
        "pais":      country,
        "nicho":     nicho_key,
        "vertical":  nicho_data.get("vertical", "empresas"),
        "url":       place.get("website", ""),
        "fuente":    "google_maps",
        "fecha":     datetime.now().strftime("%Y-%m-%d"),
        "status":    "pendiente",
        "direccion": place.get("formatted_address", ""),
    }

    # Get full details for phone + website if we have place_id
    place_id = place.get("place_id")
    if place_id and GMAPS_KEY:
        try:
            det_url = "https://maps.googleapis.com/maps/api/place/details/json"
            r = requests.get(det_url, params={
                "place_id": place_id,
                "fields": "formatted_phone_number,website,url",
                "key": GMAPS_KEY,
                "language": "es",
            }, timeout=8)
            det = r.json().get("result", {})
            lead["telefono"] = det.get("formatted_phone_number", "")
            lead["url"]      = det.get("website", lead["url"])
        except Exception:
            pass

    return lead


# ════════════════════════════════════════════════════════════════

def find_leads(nicho_key, city, country, max_leads=50,
               use_apollo=False, output_file=None, verbose=True):
    """
    Motor principal — combina scraping puro + Apollo opcional
    """
    nicho = NICHOS.get(nicho_key)
    if not nicho:
        print(f"❌ Nicho '{nicho_key}' no encontrado.")
        print(f"   Disponibles: {', '.join(NICHOS.keys())}")
        return []

    if verbose:
        print(f"\n{'═'*58}")
        print(f"  {nicho['label']} — {city}, {country}")
        print(f"  Modo: {'Apollo + Scraping' if use_apollo else 'Scraping puro'}")
        print(f"  Meta: {max_leads} leads")
        print(f"{'═'*58}\n")

    all_leads = []
    seen_emails = set()
    seen_names = set()

    # ── FASE 1: Apollo.io (si está configurado y se solicita) ───
    if use_apollo and APOLLO_KEY:
        print("  ⚡ Apollo.io activado — buscando leads enriquecidos...")
        apollo_leads, msg = apollo_search(nicho_key, city, country, max_results=max_leads)
        print(f"     {msg}")
        for lead in apollo_leads:
            key = lead.get("email") or lead.get("nombre")
            if key and key not in seen_emails:
                seen_emails.add(key)
                all_leads.append(lead)
    elif use_apollo and not APOLLO_KEY:
        print("  ⚠️  Apollo.io solicitado pero APOLLO_API_KEY no configurado.")
        print("     Continúa con scraping puro...")

    # ── FASE 2: Scraping puro desde múltiples fuentes ───────────
    city_slug = city.lower().replace(" ", "-").replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u")
    city_enc = quote_plus(city)
    country_tag = country.lower()[:2]

    # 2a. Queries de búsqueda web (Google/Bing/DDG) — APAGADO por defecto:
    # estos motores bloquean scraping o exigen JS (verificado 2026-09-17),
    # así que solo desperdician tiempo. Activar con ENABLE_LEGACY_SCRAPING=true
    # en .env si algún día vuelve a funcionar.
    queries = nicho.get("queries_google", []) if ENABLE_LEGACY_SCRAPING else []
    for q_template in queries:
        if len(all_leads) >= max_leads:
            break

        q = (q_template
             .replace("{city}", city)
             .replace("{country}", country)
             .replace("{city_slug}", city_slug)
             .replace("{country_tag}", country_tag))

        if verbose:
            print(f"  🔍 {q[:65]}...")

        urls = multi_search(q, num=8)

        for url in urls:
            if len(all_leads) >= max_leads:
                break

            info = extract_contact_from_page(url)

            if info and info.get("emails"):
                for email in info["emails"]:
                    if email not in seen_emails:
                        seen_emails.add(email)
                        lead = {
                            "nombre": "",
                            "empresa": info.get("name", ""),
                            "email": email,
                            "telefono": info.get("phones", [""])[0] if info.get("phones") else "",
                            "instagram": info.get("socials", {}).get("instagram", ""),
                            "linkedin": info.get("socials", {}).get("linkedin", ""),
                            "ciudad": city,
                            "pais": country,
                            "nicho": nicho_key,
                            "vertical": nicho.get("vertical", "empresas"),
                            "url": url,
                            "fuente": "web_scraping",
                            "fecha": datetime.now().strftime("%Y-%m-%d"),
                            "status": "pendiente",
                        }
                        all_leads.append(lead)
                        if verbose:
                            print(f"     ✅ {email} — {info.get('name', '')[:40]}")

            human_delay(1.5, 3)

        human_delay(2, 5)

    # 2b. Doctoralia (nichos de salud) — APAGADO: Doctoralia se fusionó con
    # Docplanner y cambió toda su estructura de URLs (verificado 2026-09-17),
    # el dominio viejo ya no resuelve. Activar con ENABLE_LEGACY_SCRAPING=true
    # si algún día se actualiza la lógica de scraping a las nuevas URLs.
    if ENABLE_LEGACY_SCRAPING and nicho_key in ["odontologos", "dermatologo", "psicologo", "fisioterapeuta"] and len(all_leads) < max_leads:
        print(f"\n  📋 Buscando en Doctoralia...")
        ct = "es" if country.lower() in ["españa", "spain", "es"] else "co"
        doc_leads = scrape_doctoralia(nicho_key, city_slug, country=ct)
        for lead in doc_leads:
            name_key = lead.get("nombre", "").lower()
            if name_key and name_key not in seen_names and len(all_leads) < max_leads:
                seen_names.add(name_key)
                lead["vertical"] = nicho.get("vertical", "empresas")
                lead["fecha"] = datetime.now().strftime("%Y-%m-%d")
                lead["status"] = "pendiente"
                all_leads.append(lead)
                if verbose:
                    print(f"     👤 {lead['nombre']}")

    # 2c. Last.fm para artistas independientes (Spotify requiere Premium
    # en la cuenta dueña de la app — bloqueado desde 2026-09-17, ver notas)
    if nicho_key == "artista_independiente" and len(all_leads) < max_leads:
        if LASTFM_API_KEY:
            print(f"\n  🎵 Buscando artistas calificados en Last.fm...")
            lf_leads = search_lastfm_artists(nicho_key, city, country, max_results=max_leads)
            for lead in lf_leads:
                key = lead.get("empresa", "").lower()
                if key and key not in seen_names and len(all_leads) < max_leads:
                    seen_names.add(key)
                    all_leads.append(lead)
                    if verbose:
                        print(f"     🎤 {lead['empresa']} — {lead['oyentes']:,} oyentes, "
                              f"{lead['engagement_por_oyente']} plays/oyente — {lead['generos']}")
        else:
            print("  ⚠️  LASTFM_API_KEY no configurada — saltando búsqueda de artistas.")

    # ── FASE EXTRA: Google Maps Places API ──────────────────────
    if GMAPS_KEY:
        gmaps_leads = search_google_maps(nicho_key, city, country, max_results=max(max_leads, 30))
        maps_nuevos = []
        for lead in gmaps_leads:
            dedup_key = lead.get("empresa") or lead.get("gmaps_id")
            if dedup_key and dedup_key not in seen_emails:
                seen_emails.add(dedup_key)
                lead.setdefault("fecha", datetime.now().strftime("%Y-%m-%d"))
                lead.setdefault("status", "pendiente")
                maps_nuevos.append(lead)
                if verbose:
                    print(f"     🗺️  [Maps] {lead.get('empresa','?')} — {lead.get('telefono','sin tel')}")

        # Enriquecimiento: visitar web de cada lead Maps para buscar email
        if maps_nuevos and verbose:
            with_web = [l for l in maps_nuevos if l.get("url")]
            print(f"\n  📧 Enriqueciendo emails ({len(with_web)} leads con web)...")
        for lead in maps_nuevos:
            if lead.get("url") and not lead.get("email"):
                enrich_email_from_web(lead, verbose=verbose)
                human_delay(1.0, 2.0)

        all_leads.extend(maps_nuevos)

    # ── FASE EXTRA: OpenStreetMap (gratis, sin key) ──────────────
    # Se usa cuando no hay GOOGLE_MAPS_API_KEY configurada.
    elif nicho_key in OSM_TAGS:
        if verbose:
            print(f"\n  🗺️  Buscando en OpenStreetMap (gratis, sin API key)...")
        osm_leads = search_openstreetmap(nicho_key, city, country, max_results=max_leads)
        osm_nuevos = []
        for lead in osm_leads:
            dedup_key = lead.get("empresa")
            if dedup_key and dedup_key not in seen_emails and dedup_key not in seen_names:
                seen_emails.add(dedup_key)
                osm_nuevos.append(lead)
                if verbose:
                    print(f"     🗺️  [OSM] {lead.get('empresa','?')} — {lead.get('telefono') or 'sin tel'}")

        if osm_nuevos and verbose:
            with_web = [l for l in osm_nuevos if l.get("url")]
            print(f"\n  📧 Enriqueciendo emails ({len(with_web)} leads con web)...")
        for lead in osm_nuevos:
            if lead.get("url") and not lead.get("email"):
                enrich_email_from_web(lead, verbose=verbose)
                human_delay(1.0, 2.0)

        all_leads.extend(osm_nuevos)

    # ── GUARDAR CSV ──────────────────────────────────────────────
    if output_file is None:
        out_dir = Path(__file__).parent.parent / "data"
        out_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        output_file = str(out_dir / f"leads_{nicho_key}_{city_slug}_{ts}.csv")

    if all_leads:
        fieldnames = [
            "nombre", "empresa", "email", "telefono", "whatsapp", "instagram", "linkedin",
            "ciudad", "pais", "nicho", "vertical", "url", "fuente", "fecha", "status",
            "oyentes", "reproducciones", "engagement_por_oyente", "generos",
        ]
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(all_leads)

    if verbose:
        print(f"\n{'═'*58}")
        print(f"  ✅ Total leads encontrados: {len(all_leads)}")
        print(f"  📁 Guardado en: {output_file}")
        print(f"  🎯 Con email: {sum(1 for l in all_leads if l.get('email'))}")
        print(f"  👤 Sin email (solo nombre): {sum(1 for l in all_leads if not l.get('email'))}")
        print(f"{'═'*58}\n")

    return all_leads

# ════════════════════════════════════════════════════════════════
# BÚSQUEDA MULTI-NICHO / MULTI-CIUDAD
# ════════════════════════════════════════════════════════════════

def bulk_search(config_file):
    """
    Ejecuta múltiples búsquedas desde un JSON de configuración.
    Ejemplo config.json:
    [
      {"nicho": "odontologos", "city": "Medellín", "country": "Colombia", "max": 50},
      {"nicho": "sello_musical", "city": "México", "country": "México", "max": 30}
    ]
    """
    with open(config_file, "r") as f:
        configs = json.load(f)

    total = 0
    for cfg in configs:
        leads = find_leads(
            cfg["nicho"], cfg["city"], cfg["country"],
            max_leads=cfg.get("max", 50),
            use_apollo=cfg.get("apollo", False),
        )
        total += len(leads)
        print(f"  ✅ {cfg['nicho']} / {cfg['city']}: {len(leads)} leads")
        human_delay(5, 10)  # pausa entre nichos

    print(f"\n  📊 TOTAL leads recolectados: {total}")

# ════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(
        description="IM Lead Finder v2 — Scraping puro + Apollo.io opcional",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
NICHOS DISPONIBLES:
  Salud:   {', '.join([k for k in NICHOS if NICHOS[k]['vertical']=='empresas' and k not in ['agencia_viajes','seguros','autos_alta_gama']])}
  Biz:     agencia_viajes, seguros, autos_alta_gama
  Música:  sello_musical, manager_musical, artista_independiente, estudio_grabacion

EJEMPLOS:
  # Scraping puro
  python lead_finder_v2.py --nicho odontologos --city Medellín --country Colombia

  # Con Apollo.io (necesita APOLLO_API_KEY)
  python lead_finder_v2.py --nicho seguros --city Bogotá --country Colombia --apollo

  # Artistas independientes
  python lead_finder_v2.py --nicho artista_independiente --city "Puerto Rico" --country "Puerto Rico"

  # Bulk desde archivo
  python lead_finder_v2.py --bulk config.json

  # Ver nichos
  python lead_finder_v2.py --list

APOLLO.IO (opcional, mejora resultados):
  export APOLLO_API_KEY="tu-api-key"
  Plan free: 50 contactos/mes | https://www.apollo.io/pricing

INSTALAR DEPENDENCIAS:
  pip install requests beautifulsoup4
        """
    )
    p.add_argument("--nicho", help="Nicho a buscar")
    p.add_argument("--city", default="Medellín")
    p.add_argument("--country", default="Colombia")
    p.add_argument("--max", type=int, default=50)
    p.add_argument("--apollo", action="store_true", help="Usar Apollo.io API")
    p.add_argument("--output", help="Archivo CSV de salida")
    p.add_argument("--bulk", help="Archivo JSON con múltiples búsquedas")
    p.add_argument("--list", action="store_true", help="Listar nichos disponibles")

    args = p.parse_args()

    if not SCRAPING_OK:
        print("❌ Instala dependencias: pip install requests beautifulsoup4")
        sys.exit(1)

    if args.list:
        print("\n📋 NICHOS DISPONIBLES:\n")
        for key, val in NICHOS.items():
            ap = "✓ Apollo" if val.get("apollo_titles") else ""
            print(f"  {val['label']:<30} {key:<25} {ap}")
        return

    if args.bulk:
        bulk_search(args.bulk)
        return

    if not args.nicho:
        p.print_help()
        return

    find_leads(args.nicho, args.city, args.country,
               max_leads=args.max, use_apollo=args.apollo,
               output_file=args.output)

def enriquecer_lead_con_email(lead):
    try:
        import sys, os
        sys.path.insert(0, os.path.dirname(__file__))
        from email_finder import buscar_email_completo
        resultado = buscar_email_completo(
            nombre=lead.get('nombre', ''),
            empresa=lead.get('empresa', lead.get('nombre_empresa', '')),
            url=lead.get('url', lead.get('web', '')),
            ciudad=lead.get('ciudad', 'Colombia')
        )
        if resultado.get('email'):
            lead['email'] = resultado['email']
            lead['email_verificado'] = resultado.get('email_verificado', False)
            lead['score_email'] = resultado.get('score_calidad', 0)
        if resultado.get('telefono'):
            lead['telefono'] = resultado['telefono']
            lead['whatsapp'] = resultado['telefono']
        if resultado.get('linkedin'):
            lead['linkedin'] = resultado['linkedin']
        lead['fuentes_email'] = resultado.get('fuentes_consultadas', [])
    except Exception as e:
        pass
    return lead


if __name__ == "__main__":
    main()
