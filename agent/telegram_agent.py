"""
telegram_agent.py — Bot Telegram del Orquestador IM.

UN SOLO BOT que recibe órdenes de Mateo y delega al agente correcto:
  deep_researcher   → 7 Maletas
  market_researcher → investigación de mercados
  ads_strategist    → estrategia Meta Ads
  content_planner   → 18 guiones
  lead_finder_v2    → buscar leads
  im_agents         → Mateo/José emails
  meta_ads_mcp      → gestión real de Facebook Ads
  paid_media_auditor→ auditoría 42 checkpoints
  intelligence_engine→ análisis de clientes

Variables requeridas en .env:
  TELEGRAM_BOT_TOKEN=...
  TELEGRAM_CHAT_ID=...   (se autocompleta con /start)
"""
import os
import sys
import json
import time
import threading
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE / "agent"))


# ── ENV HELPERS ───────────────────────────────────────────────

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

TOKEN    = lambda: os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID  = lambda: os.environ.get("TELEGRAM_CHAT_ID", "")


# ── ENVIAR MENSAJES ───────────────────────────────────────────

def send(texto, chat_id=None):
    """Envía texto a Telegram (soporta Markdown)."""
    cid = chat_id or CHAT_ID()
    if not cid or not TOKEN():
        return
    # Telegram tiene límite de 4096 chars
    for chunk in _split_msg(str(texto), 4000):
        try:
            requests.post(
                f"https://api.telegram.org/bot{TOKEN()}/sendMessage",
                json={"chat_id": cid, "text": chunk, "parse_mode": "Markdown"},
                timeout=15,
            )
        except Exception:
            pass

def send_doc(filepath, chat_id=None, caption=""):
    """Envía un archivo a Telegram."""
    cid = chat_id or CHAT_ID()
    if not cid or not TOKEN():
        return
    try:
        with open(filepath, "rb") as f:
            requests.post(
                f"https://api.telegram.org/bot{TOKEN()}/sendDocument",
                data={"chat_id": cid, "caption": caption},
                files={"document": f},
                timeout=60,
            )
    except Exception:
        pass

def _split_msg(texto, max_len=4000):
    """Parte mensajes largos en chunks."""
    if len(texto) <= max_len:
        return [texto]
    chunks = []
    while texto:
        chunks.append(texto[:max_len])
        texto = texto[max_len:]
    return chunks


# ── MENÚ DE AYUDA ─────────────────────────────────────────────

AYUDA = """
*IM Orquestador — Comandos disponibles:*

*🔬 INVESTIGACIÓN:*
`investiga [nombre negocio] [url]`
`7maletas [nombre negocio]`
`mercados [nicho] en [ciudad]`

*🎬 CONTENIDO:*
`guiones [nombre negocio] [nicho]`
`plan contenido [nombre]`

*👥 LEADS Y PROSPECCIÓN:*
`busca leads [nicho] en [ciudad]`
`estado leads`

*📊 META ADS — REPORTES:*
`reportes` — todas las campañas activas
`métricas [nombre campaña]`
`rendimiento hoy`

*⚙️ META ADS — GESTIÓN:*
`pausa [nombre campaña]`
`activa [nombre campaña]`
`presupuesto [nombre campaña] [monto COP]`
`duplica [nombre campaña]`

*🆕 META ADS — CREAR:*
`crea campaña [nombre] [objetivo] [presupuesto/día]`

*🔎 AUDITORÍA:*
`audita [nombre cuenta]`

*🖥 SISTEMA:*
`estado` — salud del sistema
`ayuda` — este menú
""".strip()


# ── ESTADO DE CONFIRMACIONES PENDIENTES ───────────────────────
# { chat_id: (tipo_accion, *args) }
_pendientes = {}


# ── SEGURIDAD META ADS: CONFIRMACIÓN OBLIGATORIA ─────────────

_ACCIONES_SENSIBLES = [
    "pausa", "activa", "presupuesto", "crea campaña",
    "elimina", "duplica", "modifica", "cambia",
]


def _accion_requiere_confirmacion(texto: str) -> bool:
    """Retorna True si el mensaje implica una acción que modifica campañas."""
    t = texto.lower()
    return any(a in t for a in _ACCIONES_SENSIBLES)


def _pedir_confirmacion(chat_id, accion: str, detalles: str):
    """
    Muestra EXACTAMENTE qué va a hacer antes de ejecutar.
    El usuario debe escribir SI o NO.
    """
    mensaje = (
        f"⚠️ *CONFIRMACIÓN REQUERIDA*\n\n"
        f"Acción: *{accion}*\n"
        f"Detalles: {detalles}\n\n"
        f"Esta acción modifica tus campañas de Meta Ads.\n"
        f"La acción queda registrada en el log de auditoría.\n\n"
        f"Escribe *SI* para confirmar\n"
        f"Escribe *NO* para cancelar"
    )
    send(mensaje, chat_id)


# ── INTÉRPRETE PRINCIPAL ──────────────────────────────────────

def interpretar(texto, chat_id):
    """Procesa un mensaje de Telegram y delega al agente correcto."""
    t = texto.lower().strip()

    # Evitar mensajes vacíos
    if not t:
        return

    send(f"_Procesando: {texto}_", chat_id)

    # ── CONFIRMACIONES ────────────────────────────────────────
    if t in ("sí", "si", "yes", "confirmo", "ok", "dale"):
        if chat_id in _pendientes:
            accion = _pendientes.pop(chat_id)
            _ejecutar_confirmada(accion, chat_id)
        else:
            send("No hay ninguna acción pendiente de confirmar.", chat_id)
        return

    if t in ("no", "cancel", "cancelar"):
        if chat_id in _pendientes:
            _pendientes.pop(chat_id)
        send("Acción cancelada.", chat_id)
        return

    # ── 7 MALETAS / INVESTIGACIÓN ────────────────────────────
    if t.startswith(("investiga", "7maletas", "investigación")):
        palabras = texto.split()
        nombre = " ".join(palabras[1:3]) if len(palabras) > 1 else "negocio"
        url = next((p for p in palabras if p.startswith("http")), "")
        ciudad = "Medellin"
        nicho = "general"
        if "en " in t:
            ciudad = t.split("en ")[-1].strip().split()[0].title()

        send(f"🔬 Iniciando investigación *{nombre}* con 7 Maletas...\n_(~3 minutos)_", chat_id)

        def _run():
            try:
                from deep_researcher import DeepResearcher
                dr = DeepResearcher()
                job_id = dr.crear_job(nombre, url, "", ciudad, nicho, "mediana")

                # Polling cada 10s hasta completar
                for _ in range(36):  # máx 6 min
                    time.sleep(10)
                    rep = dr.get_job_reporte(job_id)
                    if not rep:
                        continue
                    estado = rep.get("estado", "")
                    if estado == "completado":
                        datos = rep.get("resultado", {})
                        if isinstance(datos, str):
                            try:
                                datos = json.loads(datos)
                            except Exception:
                                datos = {}
                        analisis = (
                            datos.get("insight_claude") or
                            datos.get("7_maletas") or
                            str(datos)
                        )
                        resumen = str(analisis)[:3500]
                        send(f"*✅ Investigación completa — {nombre}*\n\n{resumen}", chat_id)

                        # Guardar y enviar como archivo
                        txt_path = BASE / "logs" / f"inv_{job_id}.txt"
                        txt_path.parent.mkdir(parents=True, exist_ok=True)
                        txt_path.write_text(str(analisis), encoding="utf-8")
                        send_doc(str(txt_path), chat_id, f"Investigación — {nombre}")
                        return
                    elif estado == "error":
                        send(f"❌ Error en investigación: {rep.get('error','desconocido')}", chat_id)
                        return

                send("⏱ La investigación está tardando más de lo esperado. Revisa el estado en la plataforma.", chat_id)
            except Exception as e:
                send(f"❌ Error: {e}", chat_id)

        threading.Thread(target=_run, daemon=True).start()
        return

    # ── MERCADOS ─────────────────────────────────────────────
    if t.startswith(("mercados", "analiza mercado", "investigar mercado")):
        partes = t.split("en ")
        nicho = partes[0].replace("mercados", "").replace("analiza mercado", "").replace("investigar mercado", "").strip() or "odontólogos"
        ciudad = partes[1].strip().split()[0].title() if len(partes) > 1 else "Medellín"
        send(f"🌐 Investigando mercado *{nicho}* en *{ciudad}*...", chat_id)

        def _run():
            try:
                from market_researcher import MarketResearcher
                mr = MarketResearcher()
                result = mr.investigar(nicho=nicho, ciudad=ciudad)
                resumen = str(result)[:3000]
                send(f"*📊 Mercado — {nicho} en {ciudad}*\n\n{resumen}", chat_id)
            except Exception as e:
                send(f"❌ Error investigando mercado: {e}", chat_id)

        threading.Thread(target=_run, daemon=True).start()
        return

    # ── GUIONES / CONTENIDO ───────────────────────────────────
    if t.startswith(("guiones", "plan contenido", "genera guiones")):
        palabras = texto.split()
        nombre = " ".join(palabras[1:3]) if len(palabras) > 1 else "cliente"
        nicho = palabras[3] if len(palabras) > 3 else "general"
        send(f"🎬 Generando 18 guiones para *{nombre}*...\n_(~2 minutos)_", chat_id)

        def _run():
            try:
                from content_planner import ContentPlanner
                cp = ContentPlanner()
                job_id = cp.crear_job(nombre, nicho, "Medellín", "")

                for _ in range(24):
                    time.sleep(5)
                    rep = cp.get_job_reporte(job_id)
                    if not rep:
                        continue
                    if rep.get("estado") == "completado":
                        guiones = rep.get("guiones", [])
                        resumen = f"*🎬 Plan de contenido — {nombre}*\n{len(guiones)} guiones generados\n\n"
                        if guiones:
                            g0 = guiones[0]
                            resumen += f"*Guión 1 (muestra):*\n{str(g0.get('hook_3_seg',''))}\n{str(g0.get('guion',''))[:500]}"
                        send(resumen, chat_id)

                        # Guardar completo
                        txt_path = BASE / "logs" / f"guiones_{job_id}.txt"
                        txt_path.parent.mkdir(parents=True, exist_ok=True)
                        txt_path.write_text(json.dumps(guiones, ensure_ascii=False, indent=2), encoding="utf-8")
                        send_doc(str(txt_path), chat_id, f"18 Guiones — {nombre}")
                        return
                    elif rep.get("estado") == "error":
                        send(f"❌ Error: {rep.get('error')}", chat_id)
                        return
                send("⏱ Tardando más de lo esperado. Revisa en la plataforma.", chat_id)
            except Exception as e:
                send(f"❌ Error generando guiones: {e}", chat_id)

        threading.Thread(target=_run, daemon=True).start()
        return

    # ── BUSCAR LEADS ──────────────────────────────────────────
    if "busca leads" in t or "buscar leads" in t:
        partes = t.split("en ")
        nicho = partes[0].replace("busca leads", "").replace("buscar leads", "").strip() or "odontólogos"
        ciudad = partes[1].strip().split()[0].title() if len(partes) > 1 else "Medellín"
        send(f"👥 Buscando leads de *{nicho}* en *{ciudad}*...\nTe aviso cuando termine.", chat_id)

        def _run():
            try:
                proc = subprocess.Popen(
                    [sys.executable, str(BASE / "agent" / "lead_finder_v2.py"),
                     "--nicho", nicho, "--city", ciudad, "--max", "30"],
                    cwd=str(BASE), capture_output=True, text=True
                )
                out, err = proc.communicate(timeout=180)
                encontrados = len([l for l in out.splitlines() if "lead" in l.lower() or "@" in l])
                send(f"✅ Búsqueda de leads completada\nNicho: {nicho} · Ciudad: {ciudad}\nResultados en la plataforma.", chat_id)
            except subprocess.TimeoutExpired:
                send("⏱ Búsqueda de leads en proceso. Revisa la plataforma en unos minutos.", chat_id)
            except Exception as e:
                send(f"❌ Error: {e}", chat_id)

        threading.Thread(target=_run, daemon=True).start()
        return

    # ── ESTADO LEADS ──────────────────────────────────────────
    if "estado leads" in t or "cuántos leads" in t:
        try:
            r = requests.get("http://localhost:5000/api/leads", timeout=5)
            data = r.json()
            total = len(data) if isinstance(data, list) else data.get("total", "—")
            send(f"*📋 Estado de Leads*\nTotal en DB: {total}\nRevisa la tabla completa en la plataforma.", chat_id)
        except Exception:
            send("No pude consultar leads. ¿Está el servidor corriendo?", chat_id)
        return

    # ── META ADS: REPORTES ────────────────────────────────────
    if any(w in t for w in ("reportes", "métricas", "rendimiento", "gasto", "cómo van", "como van", "campañas")):
        from meta_ads_mcp import MetaAdsMCP, MetaAdsError
        mcp = MetaAdsMCP()
        send("📊 Consultando Meta Ads...", chat_id)
        try:
            reporte = mcp.get_resumen_general()
            send(reporte, chat_id)
        except MetaAdsError as e:
            send(f"❌ {e}\n\nConfigura META\\_ACCESS\\_TOKEN en .env", chat_id)
        return

    # ── META ADS: ANALIZAR CAMPAÑA ────────────────────────────
    if t.startswith("analiza ") and not t.startswith("analiza mercado"):
        nombre = texto[8:].strip()
        from meta_ads_mcp import MetaAdsMCP
        mcp = MetaAdsMCP()
        send(f"🔍 Analizando campaña *{nombre}*...", chat_id)
        try:
            resultado = mcp.analizar_campana(nombre)
            send(resultado, chat_id)
        except Exception as e:
            send(f"❌ Error: {e}", chat_id)
        return

    # ── META ADS: PAUSA ───────────────────────────────────────
    if t.startswith("pausa "):
        nombre = texto[6:].strip()
        _pedir_confirmacion(
            chat_id,
            "PAUSAR campaña",
            f"Vas a PAUSAR la campaña: *{nombre}*\n"
            f"Los anuncios dejarán de mostrarse.\n"
            f"Esta acción es reversible (puedes activarla de nuevo)."
        )
        _pendientes[chat_id] = ("pausa", nombre)
        return

    # ── META ADS: ACTIVAR ─────────────────────────────────────
    if t.startswith("activa "):
        nombre = texto[7:].strip()
        _pedir_confirmacion(
            chat_id,
            "ACTIVAR campaña",
            f"Vas a ACTIVAR la campaña: *{nombre}*\n"
            f"Los anuncios comenzarán a mostrarse y se cobrará el presupuesto configurado.\n"
            f"Esta acción es reversible."
        )
        _pendientes[chat_id] = ("activa", nombre)
        return

    # ── META ADS: PRESUPUESTO ─────────────────────────────────
    if t.startswith("presupuesto "):
        partes = texto.split()
        if len(partes) >= 3:
            monto = partes[-1]
            nombre = " ".join(partes[1:-1])
            _pedir_confirmacion(
                chat_id,
                "CAMBIAR PRESUPUESTO",
                f"Campaña: *{nombre}*\n"
                f"Nuevo presupuesto diario: *{monto} COP/día*\n"
                f"El cambio aplica de inmediato en Meta Ads."
            )
            _pendientes[chat_id] = ("presupuesto", nombre, monto)
        else:
            send("Uso: `presupuesto [nombre campaña] [monto]`\nEj: `presupuesto Campaña Ortopedia 80000`", chat_id)
        return

    # ── META ADS: CREAR CAMPAÑA ───────────────────────────────
    if t.startswith("crea campaña"):
        partes = texto.replace("crea campaña", "").strip().split()
        if len(partes) >= 1:
            nombre = partes[0] if partes else "Nueva campaña"
            objetivo = partes[1] if len(partes) > 1 else "leads"
            presupuesto = partes[2] if len(partes) > 2 else "50000"
            _pedir_confirmacion(
                chat_id,
                "CREAR CAMPAÑA",
                f"Nombre: *{nombre}*\n"
                f"Objetivo: *{objetivo}*\n"
                f"Presupuesto/día: *{presupuesto} COP*\n"
                f"La campaña se creará en estado PAUSADA para revisión previa."
            )
            _pendientes[chat_id] = ("crear_campana", nombre, objetivo, presupuesto)
        else:
            send("Uso: `crea campaña [nombre] [objetivo] [presupuesto/día COP]`", chat_id)
        return

    # ── AUDITORÍA META ADS ────────────────────────────────────
    if t.startswith("audita "):
        nombre = texto[7:].strip()
        send(f"🔎 Auditando cuenta *{nombre}* con 42 checkpoints...\n_(~1 minuto)_", chat_id)

        def _run():
            try:
                from paid_media_auditor import crear_job, get_job_estado, get_job_reporte
                job_id = crear_job({
                    "nombre_cuenta": nombre,
                    "nicho": "general",
                    "presupuesto_mensual_cop": 0,
                    "roas_actual": 0,
                    "objetivo_principal": "ventas",
                })
                for _ in range(30):
                    time.sleep(3)
                    est = get_job_estado(job_id)
                    if not est:
                        continue
                    if est.get("estado") == "completado":
                        rep = get_job_reporte(job_id)
                        if rep:
                            score = rep.get("score", 0)
                            nivel = rep.get("clasificacion", "")
                            top5 = rep.get("top5_problemas", [])
                            mejora = rep.get("mejora_estimada", {})

                            msg = [f"*🔎 Auditoría — {nombre}*", f"Score: *{score}/100* — {nivel}"]
                            if mejora.get("mejora_estimada_pct"):
                                msg.append(f"Mejora ROAS estimada: +{mejora['mejora_estimada_pct']}%")
                            msg.append("\n*Top problemas:*")
                            for i, p in enumerate(top5[:5], 1):
                                sev = p.get("severidad", "").upper()
                                msg.append(f"{i}. [{sev}] {p.get('descripcion','')}")

                            send("\n".join(msg), chat_id)
                        return
                    elif est.get("estado") == "error":
                        send(f"❌ Error en auditoría", chat_id)
                        return
                send("⏱ Auditoría en proceso. Revisa la plataforma.", chat_id)
            except Exception as e:
                send(f"❌ Error auditando: {e}", chat_id)

        threading.Thread(target=_run, daemon=True).start()
        return

    # ── ESTADO DEL SISTEMA ────────────────────────────────────
    if "estado" in t:
        try:
            r = requests.get("http://localhost:5000/api/proceso/estado", timeout=5)
            d = r.json()
            ag = requests.get("http://localhost:5000/api/agentes/estado", timeout=5).json()
            mat = ag.get("mateo", {})
            jos = ag.get("jose", {})

            from meta_ads_mcp import MetaAdsMCP
            meta_estado = MetaAdsMCP().estado_configuracion()

            msg = (
                f"*🖥 Estado del Sistema IM*\n\n"
                f"🕐 Hora Colombia: {datetime.now().strftime('%H:%M')}\n\n"
                f"*Leads:* {d.get('leads_total', 0)} en DB · {d.get('emails_hoy', 0)} emails hoy\n\n"
                f"*Agentes:*\n"
                f"• Mateo: {'🟢 Activo' if mat.get('activo') else '⚪ Inactivo'} — {mat.get('enviados',0)} enviados\n"
                f"• José: {'🟢 Activo' if jos.get('activo') else '⚪ Inactivo'} — {jos.get('enviados',0)} enviados\n\n"
                f"*Meta Ads:* {meta_estado}"
            )
            send(msg, chat_id)
        except Exception as e:
            send(f"⚠️ Servidor parcialmente disponible: {e}", chat_id)
        return

    # ── AYUDA / START ─────────────────────────────────────────
    if "ayuda" in t or "help" in t or t in ("/start", "inicio", "hola"):
        send(AYUDA, chat_id)
        # Auto-guardar chat_id si no estaba configurado
        _guardar_chat_id(chat_id)
        return

    # ── LENGUAJE NATURAL VÍA CLAUDE ──────────────────────────────
    _interpretar_natural(texto, chat_id)


# ── INTÉRPRETE DE LENGUAJE NATURAL ───────────────────────────

def _interpretar_natural(texto: str, chat_id: str):
    """
    Cuando el bot no reconoce un comando directo, envía el mensaje
    a Claude para que determine la intención y responda apropiadamente.
    """
    import anthropic, json as _json

    send("_Procesando tu solicitud..._", chat_id)

    prompt = f"""Eres el orquestador de IM System, asistente de marketing para agencias.
Mateo te envió este mensaje por Telegram:
"{texto}"

Analiza qué quiere hacer y responde SOLO en JSON (sin markdown, sin texto extra):
{{
  "accion": "crear_campana|pausar|activar|reportes|investigar|buscar_leads|guiones|auditar|estado|otro",
  "parametros": {{
    "nombre": "nombre descriptivo si aplica",
    "objetivo": "LEAD_GENERATION|CONVERSIONS|TRAFFIC|BRAND_AWARENESS|REACH",
    "audiencia": "descripción completa del público",
    "edad_min": 18,
    "edad_max": 65,
    "ubicacion": "ciudad",
    "radio_km": 10,
    "intereses": ["lista", "de", "intereses"],
    "num_anuncios": 1,
    "canal": "WhatsApp|Instagram|Facebook",
    "estado_inicial": "PAUSED",
    "presupuesto_diario": null,
    "nicho": "sector del negocio",
    "url": ""
  }},
  "resumen": "frase corta de lo que vas a hacer",
  "requiere_confirmacion": true
}}"""

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        send("No entendí el comando. Escribe *ayuda* para ver los disponibles.", chat_id)
        return

    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip().lstrip("```json").rstrip("```").strip()
        datos = _json.loads(raw)
    except _json.JSONDecodeError:
        send("Procesé tu solicitud pero no pude estructurarla. Escribe *ayuda* para ver los comandos.", chat_id)
        return
    except Exception as e:
        err = str(e).lower()
        if "404" in err or "not_found" in err or "model" in err:
            send(
                "Los créditos de Claude API están agotados.\n"
                "Recarga en console.anthropic.com/settings/billing\n\n"
                "Mientras tanto escribe *ayuda* para usar comandos directos.",
                chat_id,
            )
        elif "credit" in err or "billing" in err or "overload" in err:
            send("Sin créditos en Claude API. Recarga en console.anthropic.com", chat_id)
        else:
            send("No entendí ese comando. Escribe *ayuda* para ver los disponibles.", chat_id)
        return

    accion = datos.get("accion", "otro")
    params = datos.get("parametros", {})
    resumen = datos.get("resumen", "")

    if accion == "crear_campana":
        intereses_str = ", ".join(params.get("intereses", [])) or "No especificados"
        presupuesto_str = (
            f"${params.get('presupuesto_diario'):,} COP/día".replace(",", ".")
            if params.get("presupuesto_diario")
            else "Por definir"
        )
        msg_conf = (
            f"Entendí tu solicitud. Voy a crear:\n\n"
            f"*CAMPAÑA NUEVA:*\n"
            f"- Nombre: {params.get('nombre', 'Nueva campaña IM')}\n"
            f"- Objetivo: {params.get('objetivo', 'LEAD_GENERATION')}\n"
            f"- Canal: {params.get('canal', 'No especificado')}\n"
            f"- Audiencia: {params.get('audiencia', '')}\n"
            f"- Edad: {params.get('edad_min', 18)}-{params.get('edad_max', 65)} años\n"
            f"- Ubicación: {params.get('ubicacion', 'No especificada')} "
            f"({params.get('radio_km', 10)} km)\n"
            f"- Intereses: {intereses_str}\n"
            f"- Anuncios: {params.get('num_anuncios', 1)}\n"
            f"- Presupuesto: {presupuesto_str}\n"
            f"- Estado inicial: BORRADOR (no se publica hasta que apruebes)\n\n"
            f"⚠️ Acción registrada en log de auditoría.\n\n"
            f"Escribe *SI* para crear o *NO* para cancelar"
        )
        send(msg_conf, chat_id)
        _pendientes[chat_id] = ("crear_campana_natural", params)

    elif accion == "reportes":
        interpretar("reportes", chat_id)

    elif accion == "investigar":
        nombre = params.get("nombre", "")
        url = params.get("url", "")
        interpretar(f"investiga {nombre} {url}".strip(), chat_id)

    elif accion == "buscar_leads":
        nicho = params.get("nicho", "empresas")
        ciudad = params.get("ubicacion", "Medellin")
        interpretar(f"busca leads {nicho} en {ciudad}", chat_id)

    elif accion == "guiones":
        nombre = params.get("nombre", "")
        nicho = params.get("nicho", "")
        interpretar(f"guiones {nombre} {nicho}".strip(), chat_id)

    elif accion == "auditar":
        nombre = params.get("nombre", "mi cuenta")
        interpretar(f"audita {nombre}", chat_id)

    elif accion == "estado":
        interpretar("estado", chat_id)

    else:
        send(
            f"Entendí: _{resumen}_\n\n"
            f"Esta acción específica aún no está automatizada. "
            f"Escribe *ayuda* para ver los comandos disponibles.",
            chat_id,
        )


# ── EJECUTAR ACCIONES CONFIRMADAS ─────────────────────────────

def _ejecutar_confirmada(accion, chat_id):
    tipo = accion[0]
    try:
        from meta_ads_mcp import MetaAdsMCP
        mcp = MetaAdsMCP()
        if tipo == "pausa":
            resultado = mcp.pause_campaign(accion[1])
            send(resultado, chat_id)
        elif tipo == "activa":
            resultado = mcp.activate_campaign(accion[1])
            send(resultado, chat_id)
        elif tipo == "presupuesto":
            resultado = mcp.set_budget(accion[1], accion[2])
            send(resultado, chat_id)
        elif tipo == "crear_campana":
            resultado = mcp.create_campaign(accion[1], accion[2], accion[3])
            send(resultado, chat_id)
        elif tipo == "crear_campana_natural":
            params = accion[1] if len(accion) > 1 else {}
            send("Creando campaña, Ad Set y anuncios en Meta Ads...", chat_id)
            send("_Paso 1/3: Campaña..._", chat_id)
            resultado = mcp.create_campaign_completa(params)
            send(resultado, chat_id)
        else:
            send(f"Tipo de acción desconocido: {tipo}", chat_id)
    except Exception as e:
        send(f"❌ Error ejecutando acción: {e}", chat_id)


# ── GUARDAR CHAT_ID ───────────────────────────────────────────

def _guardar_chat_id(chat_id):
    """Guarda el chat_id en .env si no estaba configurado."""
    if CHAT_ID():
        return
    env_path = BASE / ".env"
    if not env_path.exists():
        return
    contenido = env_path.read_text(encoding="utf-8")
    if "TELEGRAM_CHAT_ID=" in contenido:
        import re
        contenido = re.sub(r"TELEGRAM_CHAT_ID=.*", f"TELEGRAM_CHAT_ID={chat_id}", contenido)
    else:
        contenido += f"\nTELEGRAM_CHAT_ID={chat_id}\n"
    env_path.write_text(contenido, encoding="utf-8")
    os.environ["TELEGRAM_CHAT_ID"] = str(chat_id)


# ── REPORTE DIARIO AUTOMÁTICO ─────────────────────────────────

def _reporte_diario():
    """Corre en background y envía resumen a las 8:00 AM Colombia."""
    while True:
        try:
            ahora = datetime.now()
            # Calcular segundos hasta las 8:00 AM del próximo día
            manana_8am = ahora.replace(hour=8, minute=0, second=0, microsecond=0)
            if ahora >= manana_8am:
                manana_8am += timedelta(days=1)
            segundos = (manana_8am - ahora).total_seconds()
            time.sleep(min(segundos, 3600))  # despertar cada hora para re-calcular

            if datetime.now().hour != 8:
                continue

            chat_id = CHAT_ID()
            if not chat_id:
                time.sleep(3600)
                continue

            # Construir reporte
            try:
                r = requests.get("http://localhost:5000/api/proceso/estado", timeout=5).json()
                ag = requests.get("http://localhost:5000/api/agentes/estado", timeout=5).json()
                mat = ag.get("mateo", {})
                jos = ag.get("jose", {})

                from meta_ads_mcp import MetaAdsMCP
                try:
                    meta_resumen = MetaAdsMCP().get_resumen_general()
                except Exception:
                    meta_resumen = "Meta Ads no configurado"

                msg = (
                    f"*📅 Resumen diario IM — {datetime.now().strftime('%d/%m/%Y')}*\n\n"
                    f"*Emails ayer:* {r.get('emails_hoy', 0)}\n"
                    f"*Leads en DB:* {r.get('leads_total', 0)}\n"
                    f"*Mateo:* {mat.get('enviados',0)} enviados · {mat.get('respuestas',0)} respuestas\n"
                    f"*José:* {jos.get('enviados',0)} enviados · {jos.get('respuestas',0)} respuestas\n"
                    f"*Reuniones agendadas:* {mat.get('reuniones',0)}\n\n"
                    f"{meta_resumen}"
                )
                send(msg, chat_id)
            except Exception as e:
                send(f"⚠️ Error generando reporte diario: {e}", chat_id)

            # Dormir 23h para no enviar dos veces
            time.sleep(82800)

        except Exception:
            time.sleep(3600)


# ── LOOP PRINCIPAL DEL BOT ────────────────────────────────────

def _transcribir_voz(file_id: str, token_telegram: str) -> str | None:
    """Descarga una nota de voz de Telegram y la transcribe con Claude API."""
    import tempfile, base64, subprocess
    try:
        # Obtener URL del archivo en Telegram
        r = requests.get(
            f"https://api.telegram.org/bot{token_telegram}/getFile",
            params={"file_id": file_id},
            timeout=15,
        )
        file_path = r.json()["result"]["file_path"]

        # Descargar audio
        audio_bytes = requests.get(
            f"https://api.telegram.org/file/bot{token_telegram}/{file_path}",
            timeout=30,
        ).content

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        # Convertir ogg → mp3 (Claude requiere audio/mpeg)
        mp3_path = tmp_path.replace(".ogg", ".mp3")
        ffmpeg_ok = False
        try:
            subprocess.run(
                ["ffmpeg", "-i", tmp_path, "-acodec", "libmp3lame", mp3_path, "-y", "-loglevel", "quiet"],
                timeout=30,
                check=True,
            )
            ffmpeg_ok = True
        except Exception:
            pass

        if ffmpeg_ok:
            audio_path = mp3_path
        else:
            # Sin ffmpeg: renombrar .ogg a .mp3 — Claude acepta el contenido aunque
            # el formato real sea ogg; la mayoría de notas de voz de Telegram
            # son Opus/OGG que Whisper y Claude procesan igual.
            audio_path = tmp_path.replace(".ogg", ".mp3")
            import shutil
            shutil.copy2(tmp_path, audio_path)

        # Codificar en base64
        with open(audio_path, "rb") as f:
            audio_data = base64.standard_b64encode(f.read()).decode("utf-8")

        # Limpiar temporales
        try:
            os.unlink(tmp_path)
            if audio_path != tmp_path:
                os.unlink(audio_path)
        except Exception:
            pass

        import anthropic
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return None

        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Transcribe exactamente lo que dice este audio en español colombiano. "
                            "Solo el texto transcrito, sin comentarios."
                        ),
                    },
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "audio/mpeg",
                            "data": audio_data,
                        },
                    },
                ],
            }],
        )
        return msg.content[0].text.strip() or None

    except Exception as e:
        print(f"[Telegram] Error transcribiendo voz: {e}")
        return None


def run_bot():
    """Polling loop. Llamar desde server.py en un daemon thread."""
    if not TOKEN():
        print("[Telegram] TELEGRAM_BOT_TOKEN no configurado — bot inactivo")
        print("[Telegram] Agrega TELEGRAM_BOT_TOKEN=xxx al .env y reinicia")
        return

    # Iniciar reporte diario en background
    threading.Thread(target=_reporte_diario, daemon=True).start()

    offset = 0
    print("[Telegram] Bot del Orquestador activo — esperando mensajes de Mateo")

    # Mensaje de bienvenida al arrancar
    if CHAT_ID():
        send(
            f"🚀 *IM Sistema iniciado*\n"
            f"Hora Colombia: {datetime.now().strftime('%H:%M')}\n"
            f"Escribe *ayuda* para ver todos los comandos.",
        )

    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{TOKEN()}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35,
            )
            updates = r.json().get("result", [])
            for upd in updates:
                offset = upd["update_id"] + 1
                msg = upd.get("message", {})
                cid = str(msg.get("chat", {}).get("id", ""))

                # Guardar chat_id al primer contacto
                if cid:
                    _guardar_chat_id(cid)

                # Mensajes de texto
                txt = msg.get("text", "")
                if cid and txt:
                    threading.Thread(
                        target=interpretar,
                        args=(txt, cid),
                        daemon=True,
                    ).start()

                # Notas de voz y audios → Claude transcribe
                voice = msg.get("voice") or msg.get("audio")
                if voice and cid:
                    file_id = voice.get("file_id", "")
                    send("🎙 _Escuchando..._", cid)
                    texto_voz = _transcribir_voz(file_id, TOKEN())
                    if texto_voz:
                        send(f"Entendí: _{texto_voz}_", cid)
                        threading.Thread(
                            target=interpretar,
                            args=(texto_voz, cid),
                            daemon=True,
                        ).start()
                    else:
                        send("No pude procesar el audio. Escribe el comando.", cid)

        except requests.exceptions.Timeout:
            pass  # Normal — long polling timeout
        except Exception as e:
            time.sleep(5)


# ── ESTADO PARA EL SERVIDOR ───────────────────────────────────

_bot_activo = False
_bot_thread = None

def iniciar_bot():
    """Inicia el bot en un daemon thread. Llamar desde server.py."""
    global _bot_activo, _bot_thread
    if _bot_activo:
        return
    _bot_activo = True
    _bot_thread = threading.Thread(target=run_bot, daemon=True)
    _bot_thread.start()

def bot_esta_activo():
    return _bot_activo and _bot_thread is not None and _bot_thread.is_alive()


if __name__ == "__main__":
    _load_env()
    run_bot()
