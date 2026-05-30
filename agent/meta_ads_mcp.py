"""
meta_ads_mcp.py — Wrapper de la Marketing API de Meta (Facebook Ads).
Requiere: META_ACCESS_TOKEN y META_AD_ACCOUNT_ID en .env

Docs: https://developers.facebook.com/docs/marketing-api/
"""
import os
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    import subprocess, sys
    subprocess.run([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

BASE = Path(__file__).parent.parent
API_VER = "v19.0"
GRAPH = f"https://graph.facebook.com/{API_VER}"

# ═══════════════════════════════════════════════════════════════
# POLÍTICAS META MARKETING API
# Cumplimiento obligatorio según:
# https://developers.facebook.com/policy/
# https://www.facebook.com/policies/ads/
# ═══════════════════════════════════════════════════════════════
import logging as _logging

# Crear directorio de logs si no existe
(BASE / "logs").mkdir(exist_ok=True)

_meta_log = _logging.getLogger("meta_ads")
if not _meta_log.handlers:
    _meta_log.setLevel(_logging.INFO)
    _handler = _logging.FileHandler(str(BASE / "logs" / "meta_audit.log"), encoding="utf-8")
    _handler.setFormatter(_logging.Formatter("%(asctime)s %(message)s"))
    _meta_log.addHandler(_handler)

# ═══════════════════════════════════════════════════
# REGLAS ANTI-BAN META ADS API
# Fuente: políticas oficiales Meta + Felipe Vergara
# Score máximo: 60 puntos / 300 segundos
# Lectura = 1 punto | Escritura = 3 puntos
# ═══════════════════════════════════════════════════

POLITICAS_META = {
    "score_maximo_por_ventana": 60,       # Meta: 60 pts / 5 min
    "ventana_segundos": 300,              # 5 minutos = 300 segundos
    "puntos_lectura": 1,                  # GET call = 1 punto
    "puntos_escritura": 3,                # POST/PUT call = 3 puntos
    "delay_entre_llamadas": 3.0,          # mínimo 3s entre llamadas (Felipe Vergara)
    "delay_entre_campanas": 60,           # 60s entre crear campañas
    "max_campanas_por_dia": 5,            # límite voluntario IM
    "max_cambios_presupuesto_hora": 4,    # límite oficial Meta por ad set
    "requiere_aprobacion_humana": {
        "crear_campana", "cambiar_presupuesto",
        "pausar_campana", "activar_campana",
    },
    "contenido_prohibido": [
        "garantizado", "garantia", "gratis", "sin costo",
        "gana dinero", "ingresos pasivos", "antes y despues",
        "cura", "elimina", "urgente", "ultima oportunidad",
        "solo hoy", "clickbait", "resultados garantizados",
    ],
}

_LLAMADAS_META: list = []       # [(timestamp, puntos)]
_CAMBIOS_PRESUPUESTO: dict = {} # {ad_set_id: [timestamps]}
_CAMPANAS_HOY: int = 0
_ULTIMO_TIMESTAMP = 0.0

_ACCIONES_PERMITIDAS = {
    "get_campaigns", "get_metrics", "get_insights", "get_account_info",
    "get_ad_insights", "get_resumen", "pause_campaign", "activate_campaign",
    "set_budget", "create_campaign",
}

_META_ERRORES = {
    17:  "Rate limit de Meta alcanzado — esperando 60s y reintentando",
    100: "Parámetro inválido en la solicitud a Meta API",
    190: "Token de Meta expirado — genera uno nuevo en developers.facebook.com",
    200: "Permisos insuficientes — verifica ads_read y ads_management",
    368: "ALERTA: Cuenta publicitaria suspendida por Meta",
}


def _verificar_rate_limit(es_escritura: bool = False):
    """Sistema de score Meta: 60 puntos cada 300 segundos. Lectura=1pt, Escritura=3pts."""
    global _LLAMADAS_META, _ULTIMO_TIMESTAMP
    ahora = time.time()
    ventana = POLITICAS_META["ventana_segundos"]
    puntos = POLITICAS_META["puntos_escritura"] if es_escritura else POLITICAS_META["puntos_lectura"]

    # Limpiar entradas fuera de la ventana
    _LLAMADAS_META = [(t, p) for (t, p) in _LLAMADAS_META if ahora - t < ventana]

    # Calcular score actual
    score_actual = sum(p for _, p in _LLAMADAS_META)
    score_nuevo = score_actual + puntos

    if score_nuevo > POLITICAS_META["score_maximo_por_ventana"]:
        mas_antigua = _LLAMADAS_META[0][0] if _LLAMADAS_META else ahora
        espera = ventana - (ahora - mas_antigua) + 5
        _meta_log.warning(f"RATE_LIMIT score={score_actual}/{POLITICAS_META['score_maximo_por_ventana']} — esperando {espera:.0f}s")
        time.sleep(max(espera, 5))
        _LLAMADAS_META = []

    # Delay mínimo entre llamadas (3s según Felipe Vergara y políticas Meta)
    delay_min = POLITICAS_META["delay_entre_llamadas"]
    transcurrido = ahora - _ULTIMO_TIMESTAMP
    if transcurrido < delay_min:
        time.sleep(delay_min - transcurrido)

    _LLAMADAS_META.append((time.time(), puntos))
    _ULTIMO_TIMESTAMP = time.time()
    _meta_log.info(f"API_CALL tipo={'escritura' if es_escritura else 'lectura'} puntos={puntos} score_total={score_actual + puntos}")


def _verificar_cambio_presupuesto(entity_id: str):
    """Máximo 4 cambios de presupuesto por hora por entidad (ad set o campaña)."""
    global _CAMBIOS_PRESUPUESTO
    ahora = time.time()
    if entity_id not in _CAMBIOS_PRESUPUESTO:
        _CAMBIOS_PRESUPUESTO[entity_id] = []
    _CAMBIOS_PRESUPUESTO[entity_id] = [t for t in _CAMBIOS_PRESUPUESTO[entity_id] if ahora - t < 3600]
    if len(_CAMBIOS_PRESUPUESTO[entity_id]) >= POLITICAS_META["max_cambios_presupuesto_hora"]:
        raise MetaAdsError(f"Límite de cambios de presupuesto alcanzado para {entity_id}: máximo {POLITICAS_META['max_cambios_presupuesto_hora']} por hora. Intenta en la próxima hora.")
    _CAMBIOS_PRESUPUESTO[entity_id].append(ahora)


def _verificar_contenido(texto: str):
    """Verifica que el contenido no infrinja políticas de publicidad de Meta."""
    if not texto:
        return
    texto_lower = texto.lower()
    for palabra in POLITICAS_META["contenido_prohibido"]:
        if palabra in texto_lower:
            raise MetaAdsError(f"Contenido prohibido detectado: '{palabra}'. Meta puede banear la cuenta. Revisa las políticas de publicidad.")


def _log_accion(accion: str, campana: str, resultado: str):
    _meta_log.info(f"ACCION={accion} | CAMPANA={campana} | RESULTADO={resultado}")


def _verificar_politicas(accion: str):
    if accion not in _ACCIONES_PERMITIDAS:
        raise ValueError(f"Acción no permitida por políticas Meta: {accion}")


def _token_seguro(token: str) -> str:
    """Nunca mostrar el token completo — solo los primeros 10 caracteres."""
    return token[:10] + "..." if token else "(no configurado)"


def _manejar_error_meta(data: dict):
    """Interpreta códigos de error de Meta API y lanza excepción descriptiva."""
    err = data.get("error", {})
    code = err.get("code", 0)
    msg_original = err.get("message", "Error Meta API")
    msg_amigable = _META_ERRORES.get(code, msg_original)
    _meta_log.error(f"ERROR_META code={code} | {msg_original}")
    if code == 17:
        time.sleep(60)
    raise MetaAdsError(f"[Error {code}] {msg_amigable}")


def _load_env():
    env = BASE / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if k.strip() and not os.environ.get(k.strip()):
                    os.environ[k.strip()] = v.strip()

_load_env()


def _token():
    return os.environ.get("META_ACCESS_TOKEN", "")

def _account():
    return os.environ.get("META_AD_ACCOUNT_ID", "")

def _fmt_cop(n):
    try:
        return f"${int(float(n)):,} COP".replace(",", ".")
    except Exception:
        return str(n)

def _fmt_pct(n):
    try:
        return f"{float(n):.2f}%"
    except Exception:
        return str(n)


class MetaAdsError(Exception):
    pass


class MetaAdsMCP:
    """
    Interfaz completa con Meta Marketing API.
    Todas las operaciones de lectura y escritura de campañas.
    """

    def __init__(self):
        self.token = _token()
        self.account = _account()

    def _ok(self):
        return bool(self.token and self.account)

    def _verificar_token(self) -> float:
        """
        Consulta debug_token de Meta para saber cuántos días faltan para expirar.
        Si quedan < 7 días envía alerta por Telegram.
        Retorna días restantes, o -1 si el token no expira (token de sistema).
        """
        if not self.token:
            return 0
        try:
            r = requests.get(
                f"{GRAPH}/debug_token",
                params={"input_token": self.token, "access_token": self.token},
                timeout=10,
            )
            d = r.json().get("data", {})
            expira_ts = d.get("expires_at", 0)
            if not expira_ts:
                return -1  # token de sistema / no expira
            dias = (expira_ts - time.time()) / 86400
            if dias < 7:
                aviso = (
                    f"⚠️ *Token Meta Ads expira en {dias:.0f} días*\n\n"
                    f"Renueva en:\n"
                    f"developers.facebook.com/tools/explorer\n\n"
                    f"1. Selecciona tu app\n"
                    f"2. Agrega permisos: ads\\_read, ads\\_management\n"
                    f"3. Genera token → copia en .env como META\\_ACCESS\\_TOKEN"
                )
                try:
                    import sys as _s
                    _s.path.insert(0, str(BASE / "agent"))
                    from telegram_agent import send
                    send(aviso)
                except Exception:
                    pass
                _meta_log.warning(f"Token expira en {dias:.1f} días")
            return dias
        except Exception:
            return -1

    def _get(self, path, params=None):
        if not self._ok():
            raise MetaAdsError("META_ACCESS_TOKEN o META_AD_ACCOUNT_ID no configurados en .env")
        _verificar_rate_limit()
        p = {"access_token": self.token, **(params or {})}
        r = requests.get(f"{GRAPH}/{path}", params=p, timeout=20)
        data = r.json()
        if "error" in data:
            _manejar_error_meta(data)
        return data

    def _post(self, path, payload=None):
        if not self._ok():
            raise MetaAdsError("META_ACCESS_TOKEN o META_AD_ACCOUNT_ID no configurados en .env")
        _verificar_rate_limit()
        payload = {**(payload or {}), "access_token": self.token}
        r = requests.post(f"{GRAPH}/{path}", data=payload, timeout=20)
        data = r.json()
        if "error" in data:
            _manejar_error_meta(data)
        return data

    # ── CUENTAS ───────────────────────────────────────────────

    def get_account_info(self):
        """Info básica de la cuenta publicitaria."""
        return self._get(
            self.account,
            {"fields": "name,account_status,currency,timezone_name,spend_cap,amount_spent"}
        )

    # ── CAMPAÑAS ──────────────────────────────────────────────

    def get_campaigns(self, status="ACTIVE"):
        """
        Lista campañas de la cuenta.
        status: 'ACTIVE' | 'PAUSED' | 'ALL'
        """
        params = {
            "fields": "id,name,status,objective,daily_budget,lifetime_budget,created_time",
            "limit": 50,
        }
        if status != "ALL":
            params["effective_status"] = json.dumps([status, "PAUSED"] if status == "ALL" else [status])
        data = self._get(f"{self.account}/campaigns", params)
        return data.get("data", [])

    def get_campaign_by_name(self, nombre):
        """Busca una campaña por nombre (case-insensitive, partial match)."""
        campanas = self.get_campaigns(status="ALL")
        nombre_lower = nombre.lower()
        for c in campanas:
            if nombre_lower in c.get("name", "").lower():
                return c
        # También buscar en pausadas
        pausadas = self._get(
            f"{self.account}/campaigns",
            {"fields": "id,name,status", "effective_status": '["PAUSED"]', "limit": 50}
        ).get("data", [])
        for c in pausadas:
            if nombre_lower in c.get("name", "").lower():
                return c
        return None

    # ── MÉTRICAS / INSIGHTS ───────────────────────────────────

    def get_metrics(self, campaign_id, days=7):
        """
        Métricas completas de una campaña para los últimos N días.
        Retorna: spend, impressions, clicks, ctr, cpm, cpp, actions, roas
        """
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        until = datetime.now().strftime("%Y-%m-%d")
        data = self._get(
            f"{campaign_id}/insights",
            {
                "fields": (
                    "spend,impressions,clicks,ctr,cpm,cpp,reach,"
                    "actions,action_values,cost_per_action_type,"
                    "purchase_roas,frequency,date_start,date_stop"
                ),
                "time_range": json.dumps({"since": since, "until": until}),
                "level": "campaign",
            }
        )
        rows = data.get("data", [])
        return rows[0] if rows else {}

    def get_ad_insights(self, days=30):
        """Insights globales de la cuenta para el período."""
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        until = datetime.now().strftime("%Y-%m-%d")
        data = self._get(
            f"{self.account}/insights",
            {
                "fields": (
                    "spend,impressions,clicks,ctr,cpm,reach,"
                    "actions,action_values,purchase_roas,frequency"
                ),
                "time_range": json.dumps({"since": since, "until": until}),
                "level": "account",
            }
        )
        rows = data.get("data", [])
        return rows[0] if rows else {}

    # ── RESUMEN GENERAL ───────────────────────────────────────

    def get_resumen_general(self):
        """
        Resumen formateado para Telegram con todas las campañas activas
        y métricas clave del período.
        """
        self._verificar_token()
        try:
            cuenta = self.get_account_info()
            nombre_cuenta = cuenta.get("name", "Cuenta")
            gasto_total = _fmt_cop(float(cuenta.get("amount_spent", 0)) / 100)

            campanas = self.get_campaigns(status="ACTIVE")
            if not campanas:
                return f"*{nombre_cuenta}*\nGasto total: {gasto_total}\n\nNo hay campañas activas."

            lineas = [f"*📊 Meta Ads — {nombre_cuenta}*", f"Gasto acumulado: {gasto_total}", ""]

            for c in campanas[:8]:
                try:
                    m = self.get_metrics(c["id"], days=7)
                    gasto = _fmt_cop(float(m.get("spend", 0)))
                    ctr = _fmt_pct(m.get("ctr", 0))
                    imp = f"{int(float(m.get('impressions', 0))):,}".replace(",", ".")
                    roas_data = m.get("purchase_roas", [])
                    roas = round(float(roas_data[0]["value"]), 2) if roas_data else 0

                    # Leads / Compras
                    actions = m.get("actions", [])
                    leads = next((int(float(a["value"])) for a in actions if a["action_type"] in ("lead", "offsite_conversion.fb_pixel_lead")), 0)
                    compras = next((int(float(a["value"])) for a in actions if a["action_type"] == "offsite_conversion.fb_pixel_purchase"), 0)

                    estado_ico = "🟢" if c.get("status") == "ACTIVE" else "⏸"
                    lineas.append(
                        f"{estado_ico} *{c['name'][:30]}*\n"
                        f"   Gasto 7d: {gasto} · CTR: {ctr}\n"
                        f"   Impresiones: {imp}" +
                        (f" · ROAS: {roas}x" if roas else "") +
                        (f"\n   Leads: {leads}" if leads else "") +
                        (f" · Ventas: {compras}" if compras else "")
                    )
                except Exception:
                    lineas.append(f"⚪ *{c['name'][:30]}* — sin datos")

            return "\n".join(lineas)

        except MetaAdsError as e:
            return f"❌ Error Meta Ads: {e}"
        except Exception as e:
            return f"❌ Error inesperado: {e}"

    # ── ANÁLISIS DE CAMPAÑA ────────────────────────────────────

    def analizar_campana(self, nombre):
        """Análisis completo con benchmarks y recomendaciones."""
        c = self.get_campaign_by_name(nombre)
        if not c:
            return f"No encontré campaña con nombre '{nombre}'"

        try:
            m7  = self.get_metrics(c["id"], days=7)
            m30 = self.get_metrics(c["id"], days=30)

            gasto7  = float(m7.get("spend", 0))
            gasto30 = float(m30.get("spend", 0))
            ctr7    = float(m7.get("ctr", 0))
            cpm7    = float(m7.get("cpm", 0))
            freq7   = float(m7.get("frequency", 0))
            imp7    = int(float(m7.get("impressions", 0)))

            roas_data = m7.get("purchase_roas", [])
            roas = float(roas_data[0]["value"]) if roas_data else 0

            actions = m7.get("actions", [])
            leads = next((int(float(a["value"])) for a in actions if "lead" in a["action_type"]), 0)

            # Alertas
            alertas = []
            if ctr7 < 1.0:
                alertas.append("⚠️ CTR bajo (<1%) — revisa creativos y hook")
            if freq7 > 3.5:
                alertas.append("⚠️ Frecuencia alta (>3.5) — audiencia saturada, amplía o rota creativos")
            if cpm7 > 15:
                alertas.append("⚠️ CPM alto (>$15 USD) — revisar segmentación")
            if roas > 0 and roas < 1.5:
                alertas.append("⚠️ ROAS bajo (<1.5x) — considera pausar y revisar oferta")
            if not alertas:
                alertas.append("✅ Métricas dentro de benchmarks")

            daily_budget = c.get("daily_budget", 0)
            pres_dia = _fmt_cop(float(daily_budget) / 100) if daily_budget else "—"

            lineas = [
                f"*🔍 Análisis — {c['name']}*",
                f"Estado: {c.get('status','—')} · Objetivo: {c.get('objective','—')}",
                f"Presupuesto/día: {pres_dia}",
                "",
                f"*Últimos 7 días:*",
                f"Gasto: {_fmt_cop(gasto7)} · Impresiones: {imp7:,}".replace(",", "."),
                f"CTR: {_fmt_pct(ctr7)} · CPM: {_fmt_cop(cpm7 * 100)}",
                f"Frecuencia: {freq7:.1f}x" + (f" · ROAS: {roas:.2f}x" if roas else ""),
            ]
            if leads:
                cpl = gasto7 / leads if leads else 0
                lineas.append(f"Leads: {leads} · CPL: {_fmt_cop(cpl)}")

            if gasto30:
                lineas += ["", f"*Últimos 30 días:* Gasto {_fmt_cop(gasto30)}"]

            lineas += ["", "*Diagnóstico:*"] + alertas

            return "\n".join(lineas)

        except MetaAdsError as e:
            return f"❌ Error: {e}"

    # ── ACCIONES ──────────────────────────────────────────────

    def pause_campaign(self, nombre_o_id):
        """Pausa una campaña por nombre o ID."""
        _verificar_politicas("pause_campaign")
        if nombre_o_id.startswith("act_") or nombre_o_id.isdigit():
            camp_id = nombre_o_id
            nombre_log = camp_id
        else:
            c = self.get_campaign_by_name(nombre_o_id)
            if not c:
                _log_accion("pause_campaign", nombre_o_id, "ERROR: no encontrada")
                return f"No encontré campaña '{nombre_o_id}'"
            camp_id = c["id"]
            nombre_log = c.get("name", nombre_o_id)

        _verificar_rate_limit(es_escritura=True)
        self._post(camp_id, {"status": "PAUSED"})
        _log_accion("pause_campaign", nombre_log, "OK")
        return f"✅ Campaña pausada correctamente."

    def activate_campaign(self, nombre_o_id):
        """Activa una campaña pausada."""
        _verificar_politicas("activate_campaign")
        if nombre_o_id.startswith("act_") or nombre_o_id.isdigit():
            camp_id = nombre_o_id
            nombre_log = camp_id
        else:
            c = self.get_campaign_by_name(nombre_o_id)
            if not c:
                _log_accion("activate_campaign", nombre_o_id, "ERROR: no encontrada")
                return f"No encontré campaña '{nombre_o_id}'"
            camp_id = c["id"]
            nombre_log = c.get("name", nombre_o_id)

        _verificar_rate_limit(es_escritura=True)
        self._post(camp_id, {"status": "ACTIVE"})
        _log_accion("activate_campaign", nombre_log, "OK")
        return f"✅ Campaña activada correctamente."

    def set_budget(self, nombre, monto_cop):
        """
        Cambia el presupuesto diario de una campaña.
        monto_cop: valor en COP (se convierte a centavos para Meta)
        Límite Meta: máximo 4 cambios por hora por entidad.
        """
        _verificar_politicas("set_budget")
        c = self.get_campaign_by_name(nombre)
        if not c:
            _log_accion("set_budget", nombre, "ERROR: no encontrada")
            return f"No encontré campaña '{nombre}'"

        # Verificar límite de cambios de presupuesto (4 por hora por entidad)
        _verificar_cambio_presupuesto(c["id"])

        try:
            monto = float(str(monto_cop).replace(".", "").replace(",", "").replace("$", "").strip())
        except ValueError:
            return f"Monto inválido: '{monto_cop}'. Usa solo números (ej: 50000)"

        # Meta usa centavos de la moneda de la cuenta
        centavos = int(monto * 100)
        _verificar_rate_limit(es_escritura=True)
        self._post(c["id"], {"daily_budget": centavos})
        _log_accion("set_budget", c.get("name", nombre), f"OK monto={_fmt_cop(monto)}")
        return f"✅ Presupuesto actualizado a {_fmt_cop(monto)}/día"

    def create_campaign(self, nombre, objetivo="LEAD_GENERATION", presupuesto_dia_cop=50000):  # noqa: E501
        """
        Crea una campaña nueva.
        objetivo: LEAD_GENERATION | CONVERSIONS | TRAFFIC | BRAND_AWARENESS | REACH
        """
        OBJETIVOS_VALIDOS = {
            "leads": "LEAD_GENERATION",
            "conversiones": "CONVERSIONS",
            "trafico": "TRAFFIC",
            "reconocimiento": "BRAND_AWARENESS",
            "alcance": "REACH",
            "ventas": "CONVERSIONS",
        }
        _verificar_politicas("create_campaign")
        # Verificar contenido del nombre
        _verificar_contenido(nombre)
        # Verificar límite de campañas creadas hoy
        global _CAMPANAS_HOY
        if _CAMPANAS_HOY >= POLITICAS_META["max_campanas_por_dia"]:
            raise MetaAdsError(f"Límite diario alcanzado: máximo {POLITICAS_META['max_campanas_por_dia']} campañas por día. Inténtalo mañana.")
        obj = OBJETIVOS_VALIDOS.get(str(objetivo).lower(), objetivo.upper())

        try:
            presupuesto = float(str(presupuesto_dia_cop).replace(".", "").replace(",", "").strip())
        except ValueError:
            presupuesto = 50000

        centavos = int(presupuesto * 100)
        _verificar_rate_limit(es_escritura=True)
        # Delay adicional entre creación de campañas
        time.sleep(POLITICAS_META["delay_entre_campanas"])
        result = self._post(
            f"{self.account}/campaigns",
            {
                "name": nombre,
                "objective": obj,
                "status": "PAUSED",
                "daily_budget": centavos,
                "special_ad_categories": "[]",
            }
        )
        camp_id = result.get("id", "")
        _CAMPANAS_HOY += 1
        _log_accion("create_campaign", nombre, f"OK id={camp_id} obj={obj} campanas_hoy={_CAMPANAS_HOY}")
        return (
            f"✅ Campaña creada en estado PAUSADA\n"
            f"Nombre: {nombre}\n"
            f"Objetivo: {obj}\n"
            f"Presupuesto/día: {_fmt_cop(presupuesto)}\n"
            f"ID: {camp_id}\n\n"
            f"Campañas creadas hoy: {_CAMPANAS_HOY}/{POLITICAS_META['max_campanas_por_dia']}\n"
            f"Ahora crea los conjuntos de anuncios en Meta Ads Manager."
        )

    def create_campaign_completa(self, params: dict) -> str:
        """
        Crea la campaña completa: Campaign + Ad Set con audiencia + N anuncios placeholder.
        Siempre en estado PAUSED para revisión antes de publicar.
        """
        _verificar_politicas("create_campaign")

        nombre      = params.get("nombre", "Nueva campaña IM")
        objetivo    = params.get("objetivo", "LEAD_GENERATION")
        presupuesto = int(float(str(params.get("presupuesto_diario") or 50000)
                               .replace(".", "").replace(",", "").replace("$", "").strip() or 50000))
        edad_min    = int(params.get("edad_min", 18))
        edad_max    = int(params.get("edad_max", 65))
        ubicacion   = params.get("ubicacion", "Medellín")
        radio_km    = int(params.get("radio_km", 10))
        intereses   = params.get("intereses", [])
        num_anuncios = int(params.get("num_anuncios", 1))
        canal       = params.get("canal", "")

        # Mapear objetivo a constante Meta
        _OBJ_MAP = {
            "leads": "LEAD_GENERATION", "lead_generation": "LEAD_GENERATION",
            "conversiones": "CONVERSIONS", "conversions": "CONVERSIONS",
            "trafico": "TRAFFIC", "traffic": "TRAFFIC",
            "reconocimiento": "BRAND_AWARENESS", "brand_awareness": "BRAND_AWARENESS",
            "alcance": "REACH", "reach": "REACH",
            "ventas": "CONVERSIONS", "whatsapp": "MESSAGES", "messages": "MESSAGES",
        }
        obj = _OBJ_MAP.get(str(objetivo).lower(), objetivo.upper())

        # PASO 1 — Campaign
        camp_result = self._post(
            f"{self.account}/campaigns",
            {"name": nombre, "objective": obj, "status": "PAUSED",
             "special_ad_categories": "[]"}
        )
        camp_id = camp_result.get("id", "")
        _log_accion("create_campaign", nombre, f"id={camp_id}")

        # PASO 2 — Geocodificar ciudad
        location_data: list = []
        try:
            geo = self._get("search", {
                "type": "adgeolocation", "q": ubicacion,
                "location_types": '["city"]',
            })
            locs = geo.get("data", [])
            if locs:
                location_data = [{
                    "key": locs[0].get("key", ""),
                    "radius": radio_km,
                    "distance_unit": "kilometer",
                }]
        except Exception:
            pass
        if not location_data:
            location_data = [{"country": "CO"}]

        # PASO 3 — Buscar intereses en Meta
        interest_ids: list = []
        for interes in intereses[:5]:
            try:
                int_data = self._get("search", {"type": "adinterest", "q": interes})
                items = int_data.get("data", [])
                if items:
                    interest_ids.append({"id": items[0]["id"], "name": items[0]["name"]})
            except Exception:
                pass

        # PASO 4 — Targeting dict
        targeting: dict = {
            "age_min": edad_min,
            "age_max": edad_max,
        }
        if location_data and location_data[0].get("key"):
            targeting["geo_locations"] = {"cities": location_data}
        else:
            targeting["geo_locations"] = {"countries": ["CO"]}
        if interest_ids:
            targeting["interests"] = interest_ids

        # Optimización según objetivo/canal
        _OPT_MAP = {
            "LEAD_GENERATION": ("LEAD_GENERATION", "IMPRESSION"),
            "MESSAGES":        ("CONVERSATIONS",   "IMPRESSION"),
            "CONVERSIONS":     ("OFFSITE_CONVERSIONS", "IMPRESSION"),
            "TRAFFIC":         ("LINK_CLICKS",     "LINK_CLICKS"),
            "BRAND_AWARENESS": ("REACH",           "IMPRESSION"),
            "REACH":           ("REACH",           "IMPRESSION"),
        }
        opt_goal, billing = _OPT_MAP.get(obj, ("LINK_CLICKS", "LINK_CLICKS"))

        # PASO 5 — Ad Set
        centavos = presupuesto * 100
        adset_result = self._post(
            f"{self.account}/adsets",
            {
                "name":             f"Ad Set — {nombre}",
                "campaign_id":      camp_id,
                "daily_budget":     centavos,
                "billing_event":    billing,
                "optimization_goal": opt_goal,
                "targeting":        json.dumps(targeting),
                "status":           "PAUSED",
            }
        )
        adset_id = adset_result.get("id", "")
        _log_accion("create_adset", nombre, f"id={adset_id}")

        # PASO 6 — Anuncios placeholder
        ads_ids: list = []
        for i in range(min(num_anuncios, 5)):
            try:
                ad_result = self._post(
                    f"{self.account}/ads",
                    {"name": f"Anuncio {i+1} — {nombre}",
                     "adset_id": adset_id, "status": "PAUSED"}
                )
                if "id" in ad_result:
                    ads_ids.append(ad_result["id"])
                    _log_accion("create_ad", f"Anuncio {i+1}", f"id={ad_result['id']}")
            except Exception as e:
                ads_ids.append(f"[error: {e}]")

        account_num = self.account.replace("act_", "")
        resumen = (
            f"CAMPAÑA CREADA EN BORRADOR:\n"
            f"Campaign ID: {camp_id}\n"
            f"Ad Set ID:   {adset_id}\n"
            f"Anuncios:    {len(ads_ids)} en borrador\n"
            f"Audiencia:   {edad_min}-{edad_max} años | {ubicacion} {radio_km}km\n"
            f"Intereses:   {len(interest_ids)} configurados\n"
            f"Presupuesto: {_fmt_cop(presupuesto)}/día\n\n"
            f"Ve a Meta Ads Manager para:\n"
            f"1. Agregar creativos a cada anuncio\n"
            f"2. Revisar audiencia detallada\n"
            f"3. Publicar cuando estés listo\n\n"
            f"URL: https://adsmanager.facebook.com/adsmanager/manage/campaigns"
            f"?act={account_num}"
        )
        return resumen

    # ── DIAGNÓSTICO SIN TOKEN ─────────────────────────────────

    def estado_configuracion(self):
        """Retorna estado de configuración para mostrar en Telegram."""
        token = bool(self.token)
        account = bool(self.account)
        if token and account:
            try:
                info = self.get_account_info()
                dias = self._verificar_token()
                expiry_str = f" — expira en {dias:.0f} días" if dias > 0 else ""
                return f"✅ Meta Ads conectado — {info.get('name','')}{expiry_str}"
            except MetaAdsError as e:
                return f"⚠️ Token inválido o expirado: {e}"
        missing = []
        if not token:
            missing.append("META_ACCESS_TOKEN")
        if not account:
            missing.append("META_AD_ACCOUNT_ID")
        return f"❌ Faltan variables en .env: {', '.join(missing)}"
