#!/usr/bin/env python3
"""
IM Deliverability — Intelligent Markets
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Anti-spam técnico + Tracking de apertura/lectura/respuesta

ESTRATEGIAS ANTI-SPAM:
  1. Calentamiento de dominio (warm-up automático)
  2. Validación de emails antes de enviar
  3. Puntuación del contenido (SpamAssassin rules)
  4. Rotación de asuntos y variantes de cuerpo
  5. Delays humanizados (no robótico)
  6. Headers técnicos correctos
  7. Texto plano + HTML balance
  8. Gestión de rebotes y unsuscribes
  9. Reputación de dominio: chequeo SPF/DKIM/DMARC
  10. Pixel de tracking + link de seguimiento

TRACKING:
  - Pixel invisible 1x1px en el email → apertura
  - Links con UTM → clicks
  - Gmail API check → respuestas
"""

import os, json, re, csv, time, random, hashlib, sqlite3, smtplib, argparse
from datetime import datetime, timedelta
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import urllib.parse

try:
    import requests
    NET = True
except ImportError:
    NET = False

# ── Cargar .env ────────────────────────────────────────────────
def _load_env():
    f = Path(__file__).parent.parent / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if k.strip() and not os.environ.get(k.strip()):
                    os.environ[k.strip()] = v.strip()
_load_env()

# ════════════════════════════════════════════════════════════════
# BASE DE DATOS DE TRACKING (SQLite local)
# ════════════════════════════════════════════════════════════════

DB_PATH = Path(__file__).parent.parent / "logs" / "tracking.db"

def init_db():
    """Inicializa la base de datos de tracking"""
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS emails_enviados (
            id          TEXT PRIMARY KEY,
            agente      TEXT,
            to_email    TEXT,
            to_nombre   TEXT,
            empresa     TEXT,
            nicho       TEXT,
            asunto      TEXT,
            tipo        INTEGER,
            enviado_at  TEXT,
            estado      TEXT DEFAULT 'enviado'
        );

        CREATE TABLE IF NOT EXISTS aperturas (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id    TEXT,
            ip          TEXT,
            user_agent  TEXT,
            abierto_at  TEXT,
            FOREIGN KEY(email_id) REFERENCES emails_enviados(id)
        );

        CREATE TABLE IF NOT EXISTS clicks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id    TEXT,
            url         TEXT,
            clicked_at  TEXT,
            FOREIGN KEY(email_id) REFERENCES emails_enviados(id)
        );

        CREATE TABLE IF NOT EXISTS respuestas (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id    TEXT,
            respondido_at TEXT,
            fragmento   TEXT,
            FOREIGN KEY(email_id) REFERENCES emails_enviados(id)
        );

        CREATE TABLE IF NOT EXISTS rebotes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id    TEXT,
            tipo        TEXT,
            razon       TEXT,
            rebotado_at TEXT
        );
    """)
    conn.commit()
    conn.close()

def registrar_envio(email_id, agente, to_email, to_nombre, empresa, nicho, asunto, tipo):
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "INSERT OR REPLACE INTO emails_enviados VALUES (?,?,?,?,?,?,?,?,?,?)",
        (email_id, agente, to_email, to_nombre, empresa, nicho, asunto, tipo,
         datetime.now().isoformat(), "enviado")
    )
    conn.commit(); conn.close()

def registrar_apertura(email_id, ip="", user_agent=""):
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "INSERT INTO aperturas VALUES (NULL,?,?,?,?)",
        (email_id, ip, user_agent, datetime.now().isoformat())
    )
    conn.execute(
        "UPDATE emails_enviados SET estado='abierto' WHERE id=? AND estado='enviado'",
        (email_id,)
    )
    conn.commit(); conn.close()

def registrar_click(email_id, url):
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("INSERT INTO clicks VALUES (NULL,?,?,?)",
                 (email_id, url, datetime.now().isoformat()))
    conn.commit(); conn.close()

def registrar_respuesta(email_id, fragmento=""):
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "UPDATE emails_enviados SET estado='respondido' WHERE id=?", (email_id,)
    )
    conn.execute(
        "INSERT INTO respuestas VALUES (NULL,?,?,?)",
        (email_id, datetime.now().isoformat(), fragmento[:500])
    )
    conn.commit(); conn.close()

def get_stats() -> dict:
    """Obtiene estadísticas completas de todos los emails"""
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM emails_enviados")
    total = c.fetchone()[0]
    
    c.execute("SELECT COUNT(DISTINCT email_id) FROM aperturas")
    abiertos = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM emails_enviados WHERE estado='respondido'")
    respondidos = c.fetchone()[0]
    
    c.execute("SELECT COUNT(DISTINCT email_id) FROM clicks")
    con_clicks = c.fetchone()[0]
    
    c.execute("""
        SELECT e.agente, e.nicho, e.estado, e.to_nombre, e.empresa, 
               e.asunto, e.enviado_at
        FROM emails_enviados e
        ORDER BY e.enviado_at DESC LIMIT 50
    """)
    recientes = c.fetchall()
    
    conn.close()
    
    return {
        "total_enviados": total,
        "abiertos": abiertos,
        "respondidos": respondidos,
        "con_clicks": con_clicks,
        "tasa_apertura": f"{(abiertos/total*100):.1f}%" if total else "0%",
        "tasa_respuesta": f"{(respondidos/total*100):.1f}%" if total else "0%",
        "recientes": recientes,
    }


# ════════════════════════════════════════════════════════════════
# SERVIDOR DE TRACKING (pixel + links)
# ════════════════════════════════════════════════════════════════

# URL base del servidor de tracking
# Por defecto usa ngrok o el IP local
TRACKING_HOST = os.environ.get("IM_TRACKING_HOST", "")

class TrackingHandler(BaseHTTPRequestHandler):
    """Servidor HTTP mínimo para recibir eventos de tracking"""
    
    def log_message(self, format, *args): pass  # silenciar logs
    
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        
        if "/pixel/" in self.path:
            # Tracking de apertura
            email_id = params.get("id", [""])[0]
            if email_id:
                ip = self.client_address[0]
                ua = self.headers.get("User-Agent", "")
                registrar_apertura(email_id, ip, ua)
            
            # Devolver imagen 1x1 transparente
            self.send_response(200)
            self.send_header("Content-Type", "image/gif")
            self.send_header("Cache-Control", "no-cache, no-store")
            self.end_headers()
            # GIF 1x1 transparente
            self.wfile.write(b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x00\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b')
        
        elif "/click/" in self.path:
            # Tracking de click
            email_id = params.get("id", [""])[0]
            url = params.get("url", [""])[0]
            if email_id and url:
                registrar_click(email_id, urllib.parse.unquote(url))
            # Redirigir al destino
            self.send_response(302)
            self.send_header("Location", urllib.parse.unquote(url) if url else "/")
            self.end_headers()
        
        else:
            self.send_response(404)
            self.end_headers()

def start_tracking_server(port=8765):
    """Inicia el servidor de tracking en background"""
    try:
        server = HTTPServer(("0.0.0.0", port), TrackingHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print(f"  📡 Servidor de tracking activo en puerto {port}")
        return server
    except Exception as e:
        print(f"  ⚠️  Servidor de tracking no pudo iniciar: {e}")
        return None

def get_tracking_url():
    """Obtiene la URL pública del servidor de tracking"""
    if TRACKING_HOST:
        return TRACKING_HOST.rstrip("/")
    # Intentar obtener IP pública
    try:
        ip = requests.get("https://api.ipify.org", timeout=3).text.strip()
        return f"http://{ip}:8765"
    except:
        return ""


# ════════════════════════════════════════════════════════════════
# VALIDACIÓN DE EMAILS (reduce rebotes = mejor reputación)
# ════════════════════════════════════════════════════════════════

DOMINIOS_TEMPORALES = {
    "mailinator.com", "guerrillamail.com", "tempmail.com", "throwaway.email",
    "yopmail.com", "sharklasers.com", "guerrillamailblock.com", "grr.la",
    "10minutemail.com", "trashmail.com", "fakeinbox.com", "dispostable.com",
    "maildrop.cc", "spam4.me", "bccto.me"
}

DOMINIOS_VALIDOS_COMUNES = {
    "gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "icloud.com",
    "live.com", "msn.com", "protonmail.com"
}

def validar_email_sintaxis(email: str) -> tuple:
    """Valida sintaxis del email. Retorna (válido, razón)"""
    email = email.strip().lower()
    
    # Sintaxis básica
    if not re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', email):
        return False, "Sintaxis inválida"
    
    domain = email.split("@")[1]
    
    # Email temporal/desechable
    if domain in DOMINIOS_TEMPORALES:
        return False, "Email temporal/desechable"
    
    # Detectar patrones de emails falsos
    local = email.split("@")[0]
    if re.match(r'^(test|spam|fake|noreply|no-reply|donotreply)', local):
        return False, "Email de prueba o no-reply"
    
    return True, "OK"

def validar_dominio_mx(email: str) -> tuple:
    """Verifica que el dominio tiene registros MX (acepta emails)"""
    if not NET: return True, "Sin verificación de red"
    
    domain = email.split("@")[1]
    
    # Dominios conocidos — siempre válidos
    if domain in DOMINIOS_VALIDOS_COMUNES:
        return True, "Dominio conocido"
    
    try:
        # Verificar con Google DNS
        r = requests.get(
            f"https://dns.google/resolve?name={domain}&type=MX",
            timeout=5
        )
        data = r.json()
        if data.get("Answer"):
            return True, "Registros MX encontrados"
        return False, "Sin registros MX"
    except:
        return True, "No se pudo verificar — se asume válido"

def validar_lista_emails(csv_path: str) -> dict:
    """Valida todos los emails de un CSV y genera reporte"""
    with open(csv_path, "r", encoding="utf-8") as f:
        leads = list(csv.DictReader(f))
    
    validos = []
    invalidos = []
    
    for lead in leads:
        email = lead.get("email", "").strip()
        if not email:
            invalidos.append({**lead, "razon": "Sin email"})
            continue
        
        ok_sint, razon_sint = validar_email_sintaxis(email)
        if not ok_sint:
            invalidos.append({**lead, "razon": razon_sint})
            continue
        
        # Solo verificar MX para dominios corporativos (no los comunes)
        domain = email.split("@")[1]
        if domain not in DOMINIOS_VALIDOS_COMUNES:
            ok_mx, razon_mx = validar_dominio_mx(email)
            if not ok_mx:
                invalidos.append({**lead, "razon": razon_mx})
                continue
        
        validos.append(lead)
    
    # Guardar lista limpia
    out_path = csv_path.replace(".csv", "_validado.csv")
    if validos:
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=validos[0].keys())
            w.writeheader()
            w.writerows(validos)
    
    return {
        "total": len(leads),
        "validos": len(validos),
        "invalidos": len(invalidos),
        "tasa_validez": f"{len(validos)/len(leads)*100:.1f}%",
        "archivo_limpio": out_path,
        "invalidos_detalle": invalidos[:20],
    }


# ════════════════════════════════════════════════════════════════
# PUNTUACIÓN ANTI-SPAM DEL CONTENIDO
# ════════════════════════════════════════════════════════════════

PALABRAS_SPAM = [
    # Ventas agresivas
    "gratis", "grATIS", "GRATIS", "free", "FREE", "oferta", "OFERTA",
    "descuento", "DESCUENTO", "promoción", "PROMOCIÓN", "urgente", "URGENTE",
    "limitado", "exclusivo", "increíble", "increible", "fantástico",
    # Dinero
    "gana dinero", "ganar dinero", "ingresos extra", "millones", "fortunas",
    "riqueza", "¡dinero!", "$$", "$$$", "€€€",
    # Spam clásico
    "haga clic aquí", "clic aquí", "click here", "haz click",
    "desuscríbete", "cancela tu suscripción",
    # Caps excesivo
    "!!!",  "??!",
]

PATRONES_SPAM = [
    r'[A-Z]{5,}',          # MUCHAS MAYÚSCULAS seguidas
    r'!{2,}',              # múltiples !!!
    r'\${2,}',             # $$$ múltiples
    r'%\s*off',            # % off
    r'100\s*%\s*(gratis|free)',
]

def puntuar_spam(asunto: str, cuerpo: str) -> dict:
    """
    Evalúa el riesgo de spam del email.
    Score: 0-10 (0=perfecto, 10=spam seguro)
    """
    texto_completo = f"{asunto} {cuerpo}".lower()
    score = 0
    problemas = []
    
    # Palabras de spam
    for palabra in PALABRAS_SPAM:
        if palabra.lower() in texto_completo:
            score += 0.5
            problemas.append(f"Palabra de spam: '{palabra}'")
    
    # Patrones regex
    texto_original = f"{asunto} {cuerpo}"
    for patron in PATRONES_SPAM:
        if re.search(patron, texto_original):
            score += 1
            problemas.append(f"Patrón sospechoso: {patron}")
    
    # Asunto todo en mayúsculas
    if asunto == asunto.upper() and len(asunto) > 5:
        score += 2
        problemas.append("Asunto todo en mayúsculas")
    
    # Demasiados links
    links = len(re.findall(r'https?://', cuerpo))
    if links > 3:
        score += links - 3
        problemas.append(f"Demasiados links ({links})")
    
    # Ratio texto/html (texto plano es mejor)
    html_tags = len(re.findall(r'<[^>]+>', cuerpo))
    if html_tags > 20:
        score += 1
        problemas.append("Demasiado HTML")
    
    # Email muy corto
    palabras = len(cuerpo.split())
    if palabras < 15:
        score += 0.5
        problemas.append(f"Cuerpo muy corto ({palabras} palabras)")
    
    # Sin nombre del destinatario (genérico)
    if not re.search(r'hola|hello|hi\b|buenos', cuerpo[:50], re.I):
        score += 0.3
        problemas.append("Sin saludo personalizado")
    
    nivel = "✅ Bajo" if score < 2 else "⚠️ Medio" if score < 5 else "❌ Alto"
    
    return {
        "score": round(score, 1),
        "nivel_riesgo": nivel,
        "problemas": problemas,
        "recomendacion": "Listo para enviar" if score < 2 else 
                        "Revisar antes de enviar" if score < 5 else
                        "NO enviar — muy alto riesgo de spam",
    }


# ════════════════════════════════════════════════════════════════
# WARMUP — CALENTAMIENTO AUTOMÁTICO DE CUENTA
# ════════════════════════════════════════════════════════════════

WARMUP_SCHEDULE = {
    # día: emails máximos ese día
    # Semana 1 (días 1-7): 20/día
    1: 20,  2: 20,  3: 20,  4: 20,  5: 20,  6: 20,  7: 20,
    # Semana 2 (días 8-14): 40/día
    8: 40,  9: 40, 10: 40, 11: 40, 12: 40, 13: 40, 14: 40,
    # Semana 3 (días 15-21): 70/día
    15: 70, 16: 70, 17: 70, 18: 70, 19: 70, 20: 70, 21: 70,
    # Semana 4-5 (días 22-30): 100/día
    22: 100, 23: 100, 24: 100, 25: 100, 26: 100, 27: 100,
    28: 100, 29: 100, 30: 100,
}
WARMUP_MAX = 150  # techo absoluto día 31+
MAX_EMAILS_POR_HORA = 20  # límite anti-spam por hora

def get_max_emails_hoy() -> tuple:
    """Calcula el máximo de emails según el día de warmup"""
    config_file = Path(__file__).parent.parent / "logs" / "warmup_config.json"
    hoy = datetime.now().strftime("%Y-%m-%d")

    if not config_file.exists():
        config = {
            "inicio_warmup": datetime.now().isoformat(),
            "emails_enviados_hoy": 0,
            "fecha_ultimo": hoy,
            "emails_esta_hora": 0,
            "hora_actual": datetime.now().strftime("%Y-%m-%d %H"),
            "pausado_por_rebotes": False,
        }
        config_file.write_text(json.dumps(config, indent=2))

    config = json.loads(config_file.read_text())
    inicio = datetime.fromisoformat(config["inicio_warmup"])
    dias = (datetime.now() - inicio).days + 1

    # Reset contador diario
    if config.get("fecha_ultimo") != hoy:
        config["emails_enviados_hoy"] = 0
        config["fecha_ultimo"] = hoy
        config["emails_esta_hora"] = 0
        config["hora_actual"] = datetime.now().strftime("%Y-%m-%d %H")
        config_file.write_text(json.dumps(config, indent=2))

    max_dia = WARMUP_SCHEDULE.get(dias, WARMUP_MAX)
    enviados_hoy = config.get("emails_enviados_hoy", 0)
    restantes = max(0, max_dia - enviados_hoy)

    return restantes, dias, max_dia, enviados_hoy


def puede_enviar_ahora() -> tuple:
    """Verifica límite por hora (máx 20/hora) y pausa por rebotes. Retorna (puede, razón)"""
    config_file = Path(__file__).parent.parent / "logs" / "warmup_config.json"
    if not config_file.exists():
        return True, "OK"

    config = json.loads(config_file.read_text())

    # Pausa por tasa de rebotes alta
    if config.get("pausado_por_rebotes"):
        return False, "Pausado por tasa de rebotes >5% — revisar lista"

    # Reset contador horario si cambió la hora
    hora_actual = datetime.now().strftime("%Y-%m-%d %H")
    if config.get("hora_actual") != hora_actual:
        config["emails_esta_hora"] = 0
        config["hora_actual"] = hora_actual
        config_file.write_text(json.dumps(config, indent=2))

    enviados_hora = config.get("emails_esta_hora", 0)
    if enviados_hora >= MAX_EMAILS_POR_HORA:
        return False, f"Límite horario alcanzado ({MAX_EMAILS_POR_HORA}/hora) — espera la próxima hora"

    return True, "OK"


def registrar_email_hora():
    """Incrementa el contador horario"""
    config_file = Path(__file__).parent.parent / "logs" / "warmup_config.json"
    if not config_file.exists():
        return
    config = json.loads(config_file.read_text())
    hora_actual = datetime.now().strftime("%Y-%m-%d %H")
    if config.get("hora_actual") != hora_actual:
        config["emails_esta_hora"] = 0
        config["hora_actual"] = hora_actual
    config["emails_esta_hora"] = config.get("emails_esta_hora", 0) + 1
    config_file.write_text(json.dumps(config, indent=2))


def check_bounce_rate() -> dict:
    """Verifica la tasa de rebotes. Auto-pausa si >5%"""
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM emails_enviados")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM rebotes WHERE tipo='hard'")
    rebotes_hard = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM rebotes")
    rebotes_total = c.fetchone()[0]
    conn.close()

    if total == 0:
        return {"tasa": 0.0, "rebotes": 0, "total": 0, "pausado": False, "accion": "OK"}

    tasa = (rebotes_hard / total) * 100
    pausado = False

    if tasa > 5.0:
        # Auto-pausa
        config_file = Path(__file__).parent.parent / "logs" / "warmup_config.json"
        if config_file.exists():
            config = json.loads(config_file.read_text())
            config["pausado_por_rebotes"] = True
            config_file.write_text(json.dumps(config, indent=2))
        pausado = True
        accion = f"⛔ AUTO-PAUSADO — tasa de rebotes {tasa:.1f}% > 5%. Limpiar lista antes de continuar."
    elif tasa > 3.0:
        accion = f"⚠️  Tasa de rebotes {tasa:.1f}% — revisar lista de emails pronto"
    else:
        accion = f"✅ Tasa de rebotes {tasa:.1f}% — dentro del rango aceptable"

    return {
        "tasa": round(tasa, 2),
        "rebotes_hard": rebotes_hard,
        "rebotes_total": rebotes_total,
        "total_enviados": total,
        "pausado": pausado,
        "accion": accion,
    }


def reset_warmup():
    """Reinicia el warmup desde el día 1"""
    config_file = Path(__file__).parent.parent / "logs" / "warmup_config.json"
    hoy = datetime.now().strftime("%Y-%m-%d")
    config = {
        "inicio_warmup": datetime.now().isoformat(),
        "emails_enviados_hoy": 0,
        "fecha_ultimo": hoy,
        "emails_esta_hora": 0,
        "hora_actual": datetime.now().strftime("%Y-%m-%d %H"),
        "pausado_por_rebotes": False,
    }
    config_file.write_text(json.dumps(config, indent=2))
    return config

def registrar_email_warmup():
    """Incrementa el contador de emails del día y horario"""
    config_file = Path(__file__).parent.parent / "logs" / "warmup_config.json"
    if not config_file.exists():
        return
    config = json.loads(config_file.read_text())
    config["emails_enviados_hoy"] = config.get("emails_enviados_hoy", 0) + 1
    # También incrementa contador horario
    hora_actual = datetime.now().strftime("%Y-%m-%d %H")
    if config.get("hora_actual") != hora_actual:
        config["emails_esta_hora"] = 0
        config["hora_actual"] = hora_actual
    config["emails_esta_hora"] = config.get("emails_esta_hora", 0) + 1
    config_file.write_text(json.dumps(config, indent=2))


# ════════════════════════════════════════════════════════════════
# CONSTRUCTOR DE EMAIL CON TRACKING + ANTI-SPAM
# ════════════════════════════════════════════════════════════════

def construir_email_profesional(
    agente_nombre: str,
    agente_email: str,
    to_email: str,
    to_nombre: str,
    asunto: str,
    cuerpo_texto: str,
    email_id: str,
    tracking_url: str = "",
    adjunto_path: str = "",
    reply_to: str = ""
) -> MIMEMultipart:
    """
    Construye el email con todos los headers anti-spam correctos
    y el pixel de tracking embebido.
    """
    msg = MIMEMultipart("alternative")
    
    # ── Headers técnicos críticos para deliverability ──────────
    msg["From"]       = f"{agente_nombre} <{agente_email}>"
    msg["To"]         = to_email
    msg["Subject"]    = asunto
    msg["Reply-To"]   = reply_to or agente_email
    msg["Message-ID"] = f"<{email_id}@intelligent-markets.co>"
    
    # Headers que mejoran deliverability
    msg["X-Mailer"]          = "IM System v3"
    msg["X-Priority"]        = "3"  # Normal (no urgente)
    msg["Importance"]        = "Normal"
    msg["X-Spam-Status"]     = "No"
    msg["List-Unsubscribe"]  = f"<mailto:{agente_email}?subject=unsubscribe>"
    msg["Precedence"]        = "bulk"
    
    # ── Versión texto plano (SIEMPRE incluir — muy importante) ──
    # Gmail y otros proveedores penalizan emails sin texto plano
    text_part = MIMEText(cuerpo_texto, "plain", "utf-8")
    msg.attach(text_part)
    
    # ── Versión HTML con pixel de tracking ─────────────────────
    cuerpo_html = texto_a_html(cuerpo_texto, agente_nombre)
    
    if tracking_url and email_id:
        # Pixel de apertura 1x1
        pixel = f'<img src="{tracking_url}/pixel/?id={email_id}" width="1" height="1" style="display:none" alt="" />'
        cuerpo_html = cuerpo_html.replace("</body>", f"{pixel}</body>")
    
    html_part = MIMEText(cuerpo_html, "html", "utf-8")
    msg.attach(html_part)
    
    # ── Adjunto (solo si se pide) ───────────────────────────────
    if adjunto_path and Path(adjunto_path).exists():
        with open(adjunto_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        fname = Path(adjunto_path).name
        part.add_header("Content-Disposition", f'attachment; filename="{fname}"')
        msg.attach(part)
    
    return msg

def texto_a_html(texto: str, firma_nombre: str) -> str:
    """Convierte texto plano a HTML limpio y profesional"""
    # Escapar HTML
    texto_esc = texto.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    
    # Convertir saltos de línea
    parrafos = texto_esc.split("\n\n")
    html_parrafos = "".join([
        f'<p style="margin:0 0 14px 0;line-height:1.6;color:#333333">{p.replace(chr(10),"<br>")}</p>'
        for p in parrafos if p.strip()
    ])
    
    # Hacer links clickeables
    html_parrafos = re.sub(
        r'(https?://[^\s<>"]+)',
        r'<a href="\1" style="color:#6200FF;text-decoration:none">\1</a>',
        html_parrafos
    )
    
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="x-apple-disable-message-reformatting">
</head>
<body style="margin:0;padding:0;background:#ffffff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#ffffff">
<tr><td align="center" style="padding:20px 10px">
<table width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;width:100%">
<tr><td style="padding:20px 30px 30px">
  {html_parrafos}
  <hr style="border:none;border-top:1px solid #eeeeee;margin:24px 0">
  <p style="margin:0;font-size:11px;color:#aaaaaa;line-height:1.4">
    Este email fue enviado por {firma_nombre} de Intelligent Markets.<br>
    Si no deseas recibir más emails, responde con "no gracias".
  </p>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


# ════════════════════════════════════════════════════════════════
# VERIFICADOR DE REPUTACIÓN DE DOMINIO
# ════════════════════════════════════════════════════════════════

def verificar_reputacion_gmail():
    """
    Guía para verificar SPF, DKIM, DMARC de Gmail
    (Gmail los maneja automáticamente para @gmail.com)
    """
    print("""
  📋 REPUTACIÓN DE DOMINIO — GMAIL (@gmail.com)
  ─────────────────────────────────────────────
  ✅ SPF:   Automático en Gmail (no requiere configuración)
  ✅ DKIM:  Automático en Gmail (no requiere configuración)
  ✅ DMARC: Automático en Gmail (no requiere configuración)
  
  ⚠️  IMPORTANTE: Gmail.com tiene buena reputación pero volumen
     limitado. Para escalar, considera:
  
  1. Google Workspace ($6/mes) — mismo @gmail pero con dominio propio
     → Permite configurar SPF/DKIM/DMARC personalizados
     → Límite de 2000 emails/día (vs 500 de Gmail gratuito)
     
  2. Dominio propio (ej: @intelligentmarkets.co)
     → Máximo control de reputación
     → Necesitas configurar SPF, DKIM, DMARC en tu DNS

  CONFIGURACIÓN RECOMENDADA para @intelligentmarkets.co:
  ─────────────────────────────────────────────────────
  SPF (TXT record):
  v=spf1 include:_spf.google.com ~all

  DKIM: Generado automáticamente en Google Workspace Admin

  DMARC (TXT record para _dmarc.intelligentmarkets.co):
  v=DMARC1; p=quarantine; rua=mailto:dmarc@intelligentmarkets.co
""")

def check_email_reputation(email: str) -> dict:
    """Verifica la reputación básica del email en listas negras públicas"""
    domain = email.split("@")[1]
    results = {"domain": domain, "checks": {}}
    
    if not NET: return results
    
    # Check MXToolbox básico (sin API key)
    try:
        r = requests.get(
            f"https://mxtoolbox.com/api/v1/lookup/blacklist/{domain}",
            timeout=8
        )
        if r.status_code == 200:
            data = r.json()
            failed = [item for item in data.get("Failed", [])]
            results["checks"]["blacklists"] = {
                "en_listas_negras": len(failed) > 0,
                "listas": [f["Name"] for f in failed[:5]] if failed else [],
            }
    except: pass
    
    # Verificar si el dominio tiene MX (acepta email)
    try:
        r = requests.get(
            f"https://dns.google/resolve?name={domain}&type=MX",
            timeout=5
        )
        data = r.json()
        results["checks"]["mx"] = {
            "tiene_mx": bool(data.get("Answer")),
        }
    except: pass
    
    return results


# ════════════════════════════════════════════════════════════════
# MONITOR DE RESPUESTAS (chequea Gmail por respuestas)
# ════════════════════════════════════════════════════════════════

def check_respuestas_gmail():
    """
    Para monitorear respuestas automáticamente necesitas Gmail API.
    Esta función guía la configuración.
    Por ahora usa el método manual de logging.
    """
    print("""
  📬 MONITOREO DE RESPUESTAS
  ─────────────────────────────────────────────────────────
  
  OPCIÓN 1 — MANUAL (ya funciona):
  Cuando alguien responde, anótalo en el dashboard:
  python im_deliverability.py --marcar-respuesta --email-id <id>
  
  OPCIÓN 2 — AUTOMÁTICO con Gmail API:
  1. Ve a: https://console.cloud.google.com
  2. Crea proyecto "IM System"
  3. Habilita Gmail API
  4. Crea OAuth 2.0 credentials
  5. Descarga credentials.json a im-system/
  6. Corre: python im_deliverability.py --setup-gmail-api
  
  OPCIÓN 3 — IMAP (más simple):
  El sistema puede revisar respuestas vía IMAP cada hora.
  Requiere activar "Acceso IMAP" en Gmail Settings.
  Configurar en .env:
  IM_CHECK_IMAP=true
  IM_IMAP_CHECK_INTERVAL=3600  # cada hora en segundos
""")

def check_imap_replies():
    """Verifica respuestas vía IMAP (método más accesible)"""
    import imaplib
    import email as email_lib
    
    email_addr = os.environ.get("IM_EMAIL", "")
    password   = os.environ.get("IM_EMAIL_PASSWORD", "")
    
    if not email_addr or not password:
        return []
    
    nuevas_respuestas = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(email_addr, password)
        mail.select("inbox")
        
        # Buscar emails de las últimas 24h
        fecha = (datetime.now() - timedelta(days=1)).strftime("%d-%b-%Y")
        _, msgs = mail.search(None, f'(SINCE "{fecha}")')
        
        for num in msgs[0].split()[-20:]:  # últimos 20
            _, data = mail.fetch(num, "(RFC822)")
            msg = email_lib.message_from_bytes(data[0][1])
            
            subject = msg.get("Subject", "")
            from_email = msg.get("From", "")
            in_reply_to = msg.get("In-Reply-To", "")
            references  = msg.get("References", "")
            
            if in_reply_to or references:
                # Es una respuesta — buscar el email original
                conn = sqlite3.connect(str(DB_PATH))
                c = conn.cursor()
                
                # Buscar por Message-ID en referencias
                for ref_id in (in_reply_to + " " + references).split():
                    ref_clean = ref_id.strip("<>")
                    c.execute(
                        "SELECT id, to_email FROM emails_enviados WHERE id LIKE ?",
                        (f"%{ref_clean[:20]}%",)
                    )
                    row = c.fetchone()
                    if row:
                        registrar_respuesta(row[0], f"Re: {subject}")
                        nuevas_respuestas.append({
                            "email_id": row[0],
                            "de": from_email,
                            "asunto": subject,
                        })
                        break
                conn.close()
        
        mail.close()
        mail.logout()
    except Exception as e:
        pass  # IMAP puede fallar — no es crítico
    
    return nuevas_respuestas


# ════════════════════════════════════════════════════════════════
# DASHBOARD DE ESTADÍSTICAS (terminal)
# ════════════════════════════════════════════════════════════════

def mostrar_stats():
    """Muestra estadísticas en terminal"""
    stats = get_stats()
    restantes, dia_warmup, max_hoy, enviados_hoy = get_max_emails_hoy()
    
    G="\033[92m"; Y="\033[93m"; B="\033[94m"; W="\033[97m"; NC="\033[0m"; D="\033[90m"
    
    print(f"""
{B}╔══════════════════════════════════════════════════════╗
║  IM DELIVERABILITY — ESTADÍSTICAS                    ║
╚══════════════════════════════════════════════════════╝{NC}

  {W}EMAILS:{NC}
    Total enviados:   {stats['total_enviados']}
    Abiertos:         {stats['abiertos']} ({stats['tasa_apertura']})
    Respondidos:      {stats['respondidos']} ({stats['tasa_respuesta']})
    Con clicks:       {stats['con_clicks']}

  {W}WARMUP (día {dia_warmup}):{NC}
    Máximo hoy:       {max_hoy}
    Enviados hoy:     {enviados_hoy}
    Restantes hoy:    {restantes}
    {'✅ En warmup activo' if dia_warmup <= 30 else '🚀 Warmup completado — 150/día'}""")

    bounce = check_bounce_rate()
    puede, razon_hora = puede_enviar_ahora()
    config_file = Path(__file__).parent.parent / "logs" / "warmup_config.json"
    enviados_hora = 0
    if config_file.exists():
        cfg = json.loads(config_file.read_text())
        enviados_hora = cfg.get("emails_esta_hora", 0)
    print(f"""
    Límite por hora:  {enviados_hora}/{MAX_EMAILS_POR_HORA}  {'✅ OK' if puede else '⛔ '+razon_hora}
    Rebotes:          {bounce['tasa']}%  {bounce['accion']}

  {W}RECIENTES:{NC}""")
    
    for row in stats["recientes"][:10]:
        agente, nicho, estado, nombre, empresa, asunto, fecha = row
        emoji = {"enviado":"📤","abierto":"👁️","respondido":"💬"}.get(estado,"📤")
        fecha_short = fecha[:10] if fecha else ""
        print(f"    {emoji} [{fecha_short}] {agente} → {empresa or nombre} | {estado.upper()}")
    
    print()


# ════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════

def main():
    init_db()
    
    p = argparse.ArgumentParser(
        description="IM Deliverability — Anti-spam + Tracking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
COMANDOS:
  # Ver estadísticas completas
  python im_deliverability.py --stats

  # Validar lista de emails antes de enviar
  python im_deliverability.py --validar --csv data/leads_odonto.csv

  # Ver límite de emails del día (warmup)
  python im_deliverability.py --warmup-status

  # Analizar riesgo de spam de un email
  python im_deliverability.py --check-spam --asunto "asunto" --cuerpo "texto del email"

  # Verificar reputación del dominio
  python im_deliverability.py --check-reputacion

  # Iniciar servidor de tracking (para pixel de apertura)
  python im_deliverability.py --start-tracking

  # Marcar respuesta manualmente
  python im_deliverability.py --marcar-respuesta --email-id "abc123"

  # Revisar respuestas por IMAP
  python im_deliverability.py --check-respuestas
        """
    )
    
    p.add_argument("--stats",            action="store_true")
    p.add_argument("--validar",          action="store_true")
    p.add_argument("--csv",              help="CSV a validar")
    p.add_argument("--warmup-status",    action="store_true")
    p.add_argument("--check-spam",       action="store_true")
    p.add_argument("--asunto",           default="")
    p.add_argument("--cuerpo",           default="")
    p.add_argument("--check-reputacion", action="store_true")
    p.add_argument("--start-tracking",   action="store_true")
    p.add_argument("--marcar-respuesta", action="store_true")
    p.add_argument("--email-id",         default="")
    p.add_argument("--check-respuestas", action="store_true")
    
    args = p.parse_args()
    
    if args.stats:
        mostrar_stats()
    
    elif args.validar and args.csv:
        print(f"\n  🔍 Validando emails en {args.csv}...\n")
        resultado = validar_lista_emails(args.csv)
        print(f"  Total:     {resultado['total']}")
        print(f"  ✅ Válidos: {resultado['validos']} ({resultado['tasa_validez']})")
        print(f"  ❌ Inválidos: {resultado['invalidos']}")
        print(f"  📁 Lista limpia: {resultado['archivo_limpio']}")
        if resultado['invalidos_detalle']:
            print(f"\n  Emails inválidos detectados:")
            for inv in resultado['invalidos_detalle'][:5]:
                print(f"    - {inv.get('email','')} → {inv.get('razon','')}")
    
    elif args.warmup_status:
        restantes, dia, max_hoy, enviados = get_max_emails_hoy()
        bounce = check_bounce_rate()
        puede, razon_hora = puede_enviar_ahora()
        print(f"\n  📊 WARMUP STATUS:")
        print(f"  Día de warmup:    {dia}/30+")
        print(f"  Máximo hoy:       {max_hoy} (techo: {WARMUP_MAX}/día)")
        print(f"  Enviados hoy:     {enviados}")
        print(f"  Restantes hoy:    {restantes}")
        print(f"  Límite horario:   {MAX_EMAILS_POR_HORA}/hora — {'✅ puede enviar' if puede else '⛔ '+razon_hora}")
        print(f"  Rebotes:          {bounce['tasa']}%  {bounce['accion']}")
        print(f"  {'✅ Dentro del límite' if enviados < max_hoy else '⛔ Límite alcanzado — espera mañana'}\n")
    
    elif args.check_spam:
        if not args.asunto and not args.cuerpo:
            print("  Usa: --asunto 'tu asunto' --cuerpo 'tu mensaje'")
            return
        resultado = puntuar_spam(args.asunto, args.cuerpo)
        print(f"\n  📊 ANÁLISIS ANTI-SPAM:")
        print(f"  Score:        {resultado['score']}/10")
        print(f"  Nivel:        {resultado['nivel_riesgo']}")
        print(f"  Resultado:    {resultado['recomendacion']}")
        if resultado['problemas']:
            print(f"  Problemas detectados:")
            for prob in resultado['problemas']:
                print(f"    ⚠️  {prob}")
        print()
    
    elif args.check_reputacion:
        verificar_reputacion_gmail()
    
    elif args.start_tracking:
        server = start_tracking_server()
        if server:
            url = get_tracking_url()
            print(f"\n  📡 Tracking activo en: {url}")
            print(f"  Agrega a .env: IM_TRACKING_HOST={url}")
            print(f"  Ctrl+C para detener\n")
            try:
                while True: time.sleep(1)
            except KeyboardInterrupt:
                server.shutdown()
                print("  Servidor detenido.")
    
    elif args.marcar_respuesta and args.email_id:
        registrar_respuesta(args.email_id, "Marcada manualmente")
        print(f"  ✅ Respuesta registrada para email {args.email_id}")
    
    elif args.check_respuestas:
        print("  📬 Revisando respuestas por IMAP...")
        nuevas = check_imap_replies()
        if nuevas:
            print(f"  ✅ {len(nuevas)} nuevas respuestas encontradas:")
            for r in nuevas:
                print(f"    - {r['de']} | {r['asunto']}")
        else:
            print("  Sin nuevas respuestas detectadas.")
    
    else:
        p.print_help()

if __name__ == "__main__":
    main()


# ════════════════════════════════════════════════════════════════
# MONITOR DE REPLIES — IMAP inbox checker + auto-respuesta
# ════════════════════════════════════════════════════════════════

import imaplib
import email as _email_lib
from email.header import decode_header as _decode_header

def _decode_str(h: str) -> str:
    if not h:
        return ""
    parts = _decode_header(h)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(str(part))
    return " ".join(result).strip()


def revisar_inbox_imap() -> list:
    """
    Conecta al inbox de Gmail via IMAP y retorna lista de replies no leidos.
    Solo procesa emails con Subject que comienza con 'Re:' o con In-Reply-To header.
    """
    em = os.environ.get("IM_EMAIL", "intelligentsmarkets@gmail.com")
    pw = os.environ.get("IM_EMAIL_PASSWORD", "")
    if not pw:
        return []

    replies = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(em, pw)
        mail.select("INBOX")

        desde = (datetime.now() - timedelta(days=3)).strftime("%d-%b-%Y")
        _, msgnums = mail.search(None, f'(UNSEEN SINCE {desde})')

        for num in (msgnums[0].split() or []):
            try:
                _, data = mail.fetch(num, "(RFC822)")
                raw = data[0][1]
                msg = _email_lib.message_from_bytes(raw)

                subject      = _decode_str(msg.get("Subject", ""))
                from_header  = _decode_str(msg.get("From", ""))
                in_reply_to  = msg.get("In-Reply-To", "")

                is_reply = subject.lower().startswith("re:") or bool(in_reply_to.strip())
                if not is_reply:
                    continue

                # Extraer cuerpo texto plano
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            payload = part.get_payload(decode=True)
                            if payload:
                                body = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                                break
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        body = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")

                # Extraer email limpio del remitente
                rem_match = re.search(r'<([^>]+@[^>]+)>', from_header)
                rem_email = rem_match.group(1).strip().lower() if rem_match else from_header.strip().lower()

                # Ignorar autorespuestas o nuestros propios emails
                if em.lower() in rem_email:
                    continue

                replies.append({
                    "from_email":   rem_email,
                    "from_display": from_header,
                    "subject":      subject,
                    "body":         body[:3000],
                    "in_reply_to":  in_reply_to,
                    "msg_num":      num,
                })
                # Marcar como leido para no procesar dos veces
                mail.store(num, "+FLAGS", "\\Seen")

            except Exception:
                continue

        mail.logout()
    except Exception as e:
        print(f"  IMAP error: {e}")

    return replies


def _buscar_contexto_lead(rem_email: str) -> dict:
    """Busca el lead y el ultimo email enviado a ese remitente en platform.db."""
    db_path = Path(__file__).parent.parent / "logs" / "platform.db"
    if not db_path.exists():
        return {}
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    log  = conn.execute(
        "SELECT * FROM emails_log WHERE LOWER(to_email)=LOWER(?) ORDER BY id DESC LIMIT 1",
        (rem_email,)).fetchone()
    lead = conn.execute(
        "SELECT * FROM leads WHERE LOWER(email)=LOWER(?) LIMIT 1",
        (rem_email,)).fetchone()
    conn.close()
    return {
        "email_log": dict(log)  if log  else {},
        "lead":      dict(lead) if lead else {},
    }


def _actualizar_db_reply(rem_email: str):
    """Marca lead como 'respondido' y actualiza emails_log en platform.db."""
    db_path = Path(__file__).parent.parent / "logs" / "platform.db"
    if not db_path.exists():
        return
    now = datetime.now().isoformat()
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE emails_log SET estado='respondido', respondido_at=? "
        "WHERE LOWER(to_email)=LOWER(?) AND estado NOT IN ('respondido','reunion','cliente')",
        (now, rem_email))
    conn.execute(
        "UPDATE leads SET status='respondido', fecha_contacto=? "
        "WHERE LOWER(email)=LOWER(?) AND status NOT IN ('reunion','cliente','cerrado')",
        (now, rem_email))
    conn.commit(); conn.close()


def _generar_auto_respuesta(reply: dict, ctx: dict) -> str:
    """Genera una respuesta automatica con Claude segun el tono del reply."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or not NET:
        return ""

    log    = ctx.get("email_log", {})
    lead   = ctx.get("lead", {})
    agente = log.get("agente", "Mateo")
    cal    = (os.environ.get("CAL_MUSIC","https://cal.com/intelligent-markets-agencia/sello-30min")
              if agente == "Jose" else
              os.environ.get("CAL_EMPRESAS","https://cal.com/intelligent-markets-agencia/30min"))
    firma  = (f"Jose Galvis\nDirector - IM Music | Intelligent Markets"
              if agente == "Jose" else
              f"Mateo Galvis\nGerente de Marketing - Intelligent Markets")

    nombre    = lead.get("nombre", "").split()[0] if lead.get("nombre") else ""
    empresa   = lead.get("empresa", log.get("empresa", ""))
    body_recv = reply.get("body", "")[:1200]

    prompt = f"""Eres {agente} de Intelligent Markets. Recibiste esta respuesta a un email de prospeccion:

DE: {reply.get('from_email')} | {empresa}
ASUNTO: {reply.get('subject')}
MENSAJE RECIBIDO:
{body_recv}

INSTRUCCIONES DE RESPUESTA:
- Si pregunta precio/costo: NO dar precio. Decir que depende del plan y proponer llamada: {cal}
- Si quiere mas informacion: Respuesta breve + proponer llamada: {cal}
- Si quiere agendar: Confirmar con entusiasmo + link: {cal}
- Si dice no interesa: Agradecer elegantemente y cerrar la puerta con dignidad
- Si es ambiguo: Una sola pregunta para entender que necesita
- Maximo 90 palabras
- Tono: calido y confiado. Nunca ansioso ni vendedor.
- NO empezar con "Hola" o "Buenos dias" — ir directo al punto
- Firma: {firma}

DEVUELVE SOLO el cuerpo del email listo para enviar (sin JSON, sin markdown)."""

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"Content-Type":"application/json","x-api-key":api_key,"anthropic-version":"2023-06-01"},
            json={"model":"claude-sonnet-4-6","max_tokens":350,
                  "messages":[{"role":"user","content":prompt}]},
            timeout=30,
        )
        d = r.json()
        return d.get("content",[{}])[0].get("text","").strip()
    except Exception:
        return ""


def _enviar_auto_respuesta(agente: str, to_email: str, subject: str, body: str) -> bool:
    """Envia la respuesta automatica via SMTP."""
    em = os.environ.get("IM_EMAIL","intelligentsmarkets@gmail.com")
    pw = os.environ.get("IM_EMAIL_PASSWORD","")
    if not pw:
        return False
    nombre_agente = "Jose Galvis" if "jose" in agente.lower() else "Mateo Galvis"
    reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = reply_subject
        msg["From"]    = f"{nombre_agente} <{em}>"
        msg["To"]      = to_email
        msg.attach(MIMEText(body, "plain", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(em, pw)
            s.sendmail(em, [to_email], msg.as_string())
        return True
    except Exception as e:
        print(f"  Error enviando auto-respuesta: {e}")
        return False


def _registrar_auto_respuesta(agente: str, to_email: str, empresa: str, nicho: str, subject: str):
    """Registra la auto-respuesta enviada en emails_log."""
    db_path = Path(__file__).parent.parent / "logs" / "platform.db"
    if not db_path.exists():
        return
    reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO emails_log (agente,to_email,empresa,nicho,asunto,tipo,estado,enviado_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (agente, to_email, empresa, nicho, reply_subject, 99, "ENVIADO", datetime.now().isoformat()))
    conn.commit(); conn.close()


def procesar_replies():
    """
    Ciclo completo:
    1. Revisa inbox IMAP buscando replies
    2. Por cada reply: actualiza DB, genera respuesta con Claude, la envia
    3. Registra la respuesta enviada
    """
    print(f"\n[{datetime.now().strftime('%H:%M')}] Revisando inbox...")
    try:
        replies = revisar_inbox_imap()
    except Exception as e:
        print(f"  Error en IMAP: {e}")
        return

    if not replies:
        print("  Sin replies nuevos")
        return

    print(f"  {len(replies)} reply(s) detectado(s)")

    for reply in replies:
        rem = reply["from_email"]
        ctx = _buscar_contexto_lead(rem)
        log = ctx.get("email_log", {})
        lead = ctx.get("lead", {})

        print(f"  Reply de {rem} -> {reply['subject'][:50]}")

        # 1. Actualizar DB: lead respondio
        _actualizar_db_reply(rem)

        # 2. Generar respuesta con Claude
        resp_body = _generar_auto_respuesta(reply, ctx)
        if not resp_body:
            print(f"    No se pudo generar respuesta automatica (sin API key o sin red)")
            continue

        # 3. Enviar respuesta
        agente  = log.get("agente", "Mateo")
        empresa = lead.get("empresa", log.get("empresa", ""))
        nicho   = lead.get("nicho",   log.get("nicho",   ""))

        ok = _enviar_auto_respuesta(agente, rem, reply["subject"], resp_body)
        if ok:
            print(f"    Auto-respuesta enviada a {rem}")
            _registrar_auto_respuesta(agente, rem, empresa, nicho, reply["subject"])
        else:
            print(f"    Error enviando auto-respuesta a {rem}")


def iniciar_monitor_inbox(intervalo_min: int = 30):
    """
    Inicia el monitor de replies en un thread de fondo.
    Revisa el inbox cada `intervalo_min` minutos.
    """
    def _loop():
        # Primera revision inmediata
        try:
            procesar_replies()
        except Exception as e:
            print(f"  Monitor inbox error: {e}")
        while True:
            time.sleep(intervalo_min * 60)
            try:
                procesar_replies()
            except Exception as e:
                print(f"  Monitor inbox error: {e}")

    t = threading.Thread(target=_loop, daemon=True, name="inbox-monitor")
    t.start()
    print(f"  Monitor de inbox activo — revisando cada {intervalo_min} min")
    return t


# ════════════════════════════════════════════════════════════════
# SISTEMA DE ALERTAS CRÍTICAS
# Detecta palabras clave en emails recibidos/enviados y dispara
# alerta a intelligentmarkets@gmail.com + escribe en logs/alertas.json
# ════════════════════════════════════════════════════════════════

ALERT_KEYWORDS = [
    "rechazado", "inhabilitado", "pago fallido", "suspendido",
    "bloqueado", "banned", "cuenta suspendida", "payment failed",
    "account disabled", "suspended", "rejected", "violation",
    "cuenta deshabilitada", "incumplimiento", "política",
]

ALERT_RECIPIENT = "intelligentmarkets@gmail.com"

_ALERTS_LOG = Path(__file__).parent.parent / "logs" / "alertas.json"


def _load_alerts_log():
    _ALERTS_LOG.parent.mkdir(parents=True, exist_ok=True)
    if _ALERTS_LOG.exists():
        try:
            return json.loads(_ALERTS_LOG.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save_alert_log(entry):
    alertas = _load_alerts_log()
    alertas.append(entry)
    # Keep last 500 entries
    if len(alertas) > 500:
        alertas = alertas[-500:]
    _ALERTS_LOG.write_text(
        json.dumps(alertas, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _detectar_keywords(texto):
    """Return list of matched alert keywords found in texto (case-insensitive)."""
    texto_lower = texto.lower()
    return [kw for kw in ALERT_KEYWORDS if kw in texto_lower]


def _enviar_alerta_email(asunto_original, keywords_encontradas, fragmento, origen):
    """Send an alert email via SMTP using existing env credentials."""
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")

    if not smtp_user or not smtp_pass:
        return False

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    body_txt = (
        f"⚠️ ALERTA CRÍTICA — IM System\n\n"
        f"Fecha: {now_str}\n"
        f"Origen: {origen}\n"
        f"Asunto original: {asunto_original}\n"
        f"Palabras clave detectadas: {', '.join(keywords_encontradas)}\n\n"
        f"Fragmento del mensaje:\n"
        f"{'─'*50}\n"
        f"{fragmento[:800]}\n"
        f"{'─'*50}\n\n"
        f"Acción requerida: Revisar de inmediato en la plataforma IM."
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"⚠️ ALERTA IM: {', '.join(keywords_encontradas[:2])}"
    msg["From"]    = smtp_user
    msg["To"]      = ALERT_RECIPIENT
    msg.attach(MIMEText(body_txt, "plain", "utf-8"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, [ALERT_RECIPIENT], msg.as_string())
        return True
    except Exception as e:
        print(f"  [ALERT] Error enviando alerta email: {e}")
        return False


def escanear_texto_alerta(texto, asunto="", origen="manual"):
    """
    Public API: scan any text for alert keywords.
    If found → log to alertas.json + attempt email alert.
    Returns dict with matches and action taken.
    """
    keywords = _detectar_keywords(texto)
    if not keywords:
        return {"alerta": False, "keywords": []}

    fragmento = texto[:1000]
    entry = {
        "timestamp": datetime.now().isoformat(),
        "origen": origen,
        "asunto": asunto,
        "keywords": keywords,
        "fragmento": fragmento[:300],
        "email_enviado": False,
    }

    print(f"  [ALERT] Palabras críticas detectadas: {keywords} — origen: {origen}")

    email_ok = _enviar_alerta_email(asunto, keywords, fragmento, origen)
    entry["email_enviado"] = email_ok

    _save_alert_log(entry)

    return {
        "alerta": True,
        "keywords": keywords,
        "email_enviado": email_ok,
        "timestamp": entry["timestamp"],
    }


def monitorear_inbox_alertas(intervalo_min=15):
    """
    Background thread: monitors SMTP inbox (IMAP) for alert keywords.
    Complements the existing procesar_replies() flow.
    Reads IMAP credentials from env: IMAP_HOST, IMAP_USER, IMAP_PASS.
    """
    import imaplib
    import email as email_lib

    imap_host = os.environ.get("IMAP_HOST", "imap.gmail.com")
    imap_user = os.environ.get("IMAP_USER", os.environ.get("SMTP_USER", ""))
    imap_pass = os.environ.get("IMAP_PASS", os.environ.get("SMTP_PASS", ""))

    if not imap_user or not imap_pass:
        print("  [ALERT] IMAP no configurado — monitor de alertas desactivado")
        return None

    def _check_inbox():
        try:
            M = imaplib.IMAP4_SSL(imap_host)
            M.login(imap_user, imap_pass)
            M.select("INBOX")
            # Search unseen messages from last 24h
            _, data = M.search(None, "UNSEEN")
            uids = data[0].split()[-50:]  # Last 50 unseen max
            for uid in uids:
                _, msg_data = M.fetch(uid, "(RFC822)")
                raw = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw)
                asunto = msg.get("Subject", "")
                cuerpo = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            try:
                                cuerpo += part.get_payload(decode=True).decode("utf-8", errors="ignore")
                            except Exception:
                                pass
                else:
                    try:
                        cuerpo = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
                    except Exception:
                        pass
                texto_completo = f"{asunto} {cuerpo}"
                escanear_texto_alerta(texto_completo, asunto=asunto, origen="imap_inbox")
            M.logout()
        except Exception as e:
            print(f"  [ALERT] Error IMAP check: {e}")

    def _loop():
        _check_inbox()
        while True:
            time.sleep(intervalo_min * 60)
            _check_inbox()

    t = threading.Thread(target=_loop, daemon=True, name="alerta-monitor")
    t.start()
    print(f"  [ALERT] Monitor de alertas activo — revisando inbox cada {intervalo_min} min")
    return t


def listar_alertas(limit=50):
    """Return recent alerts from log file."""
    alertas = _load_alerts_log()
    return alertas[-limit:]
