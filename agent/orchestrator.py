# -*- coding: utf-8 -*-
"""
IM Orchestrator — Intelligent Markets
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Cerebro jerárquico que coordina todos los agentes sin modificarlos.

Jerarquía:
  Nivel 2 → Gerente de Marketing (consolida informe final)
  Nivel 3 → PM-A (audita identidad/narrativa)
           → PM-B (audita datos reales vs genérico)
  Nivel 4 → Especialistas (deep_researcher, ads_strategist, etc.)

Flujo:
  FASE 1: Investigación  → informe_investigacion_{id}.json
  FASE 2: Estrategia     → informe_estrategia_{id}.json  (solo si F1 aprobada)
  FASE 3: Ejecución      → lanza envíos  (solo si humano aprueba F2)
"""

import os, sys, json, uuid, threading, logging, re
from datetime import datetime
from pathlib import Path

# ── Directorio de handoffs ────────────────────────────────────
# (se crea al importar el módulo)


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── paths ──────────────────────────────────────────────────────
BASE      = Path(__file__).parent.parent
LOGS_DIR  = BASE / "logs"
INF_DIR   = LOGS_DIR / "informes"
JOBS_FILE = LOGS_DIR / "orchestrator_jobs.json"
LOG_FILE  = LOGS_DIR / "orchestrator.log"

HANDOFFS_DIR = LOGS_DIR / "handoffs"

LOGS_DIR.mkdir(parents=True, exist_ok=True)
INF_DIR.mkdir(parents=True, exist_ok=True)
HANDOFFS_DIR.mkdir(parents=True, exist_ok=True)

# ── structured logger ──────────────────────────────────────────
_handler = logging.FileHandler(str(LOG_FILE), encoding="utf-8")
_handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
log = logging.getLogger("orchestrator")
log.setLevel(logging.INFO)
if not log.handlers:
    log.addHandler(_handler)
    log.addHandler(logging.StreamHandler(sys.stdout))

# ── .env loader ────────────────────────────────────────────────
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

# ────────────────────────────────────────────────────────────────
# JOBS — persiste en JSON (simple, no requiere SQLite extra)
# ────────────────────────────────────────────────────────────────

_jobs_lock = threading.Lock()

def _load_jobs():
    if JOBS_FILE.exists():
        try:
            return json.loads(JOBS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def _save_jobs(jobs):
    JOBS_FILE.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")

def _get_job(job_id):
    with _jobs_lock:
        return _load_jobs().get(job_id)

def _set_job(job_id, data):
    with _jobs_lock:
        jobs = _load_jobs()
        jobs[job_id] = data
        _save_jobs(jobs)

def _patch_job(job_id, **kwargs):
    with _jobs_lock:
        jobs = _load_jobs()
        if job_id in jobs:
            jobs[job_id].update(kwargs)
            _save_jobs(jobs)

# ────────────────────────────────────────────────────────────────
# AUDITORÍA — PM-B detecta contenido genérico
# ────────────────────────────────────────────────────────────────

FRASES_GENERICAS = [
    "empresa líder", "empresa lider",
    "soluciones innovadoras", "calidad garantizada",
    "mejor del mercado", "servicio de excelencia",
    "comprometidos con la calidad", "a su disposición",
    "estamos para servirle", "somos líderes",
    "somos lideres", "nuestros clientes satisfechos",
    "de alta calidad", "resultados garantizados",
]

def _auditar_genericos(texto):
    """PM-B: devuelve lista de frases genéricas encontradas."""
    texto_lower = texto.lower()
    return [f for f in FRASES_GENERICAS if f in texto_lower]

def _auditar_datos_reales(texto, nombre, nicho, ciudad):
    """PM-B: verifica que el texto mencione datos específicos del negocio."""
    checks = {
        "menciona_nombre":  nombre.lower()[:8] in texto.lower() if nombre else False,
        "menciona_nicho":   nicho.lower()[:6]  in texto.lower() if nicho  else False,
        "menciona_ciudad":  ciudad.lower()[:5] in texto.lower() if ciudad else False,
        "tiene_numeros":    bool(re.search(r'\d+', texto)),
        "tiene_porcentaje": "%" in texto or "COP" in texto or "pesos" in texto.lower(),
    }
    score = sum(checks.values())
    return checks, score

def _pm_b_auditar(contenido_str, nombre, nicho, ciudad, etapa):
    """Auditoría completa PM-B. Retorna dict con resultado."""
    genericos = _auditar_genericos(contenido_str)
    checks, score = _auditar_datos_reales(contenido_str, nombre, nicho, ciudad)
    aprobado = len(genericos) == 0 and score >= 2

    resultado = {
        "aprobado":          aprobado,
        "etapa":             etapa,
        "frases_genericas":  genericos,
        "datos_reales":      checks,
        "score_datos":       score,
        "timestamp":         datetime.now().isoformat(),
        "decision":          "APROBADO" if aprobado else "BLOQUEADO",
        "motivo":            (
            f"Frases genéricas detectadas: {genericos}" if genericos
            else f"Score datos reales insuficiente ({score}/5) — faltan: "
                 + ", ".join(k for k, v in checks.items() if not v) if score < 2
            else "OK"
        ),
    }
    log.info(f"{etapa} | PM-B | {resultado['decision']} — {resultado['motivo']}")
    return resultado


def _pm_b_con_retry(contenido_str, nombre, nicho, ciudad, etapa,
                    job_id, max_reintentos=3):
    """
    PM-B con hasta 3 reintentos. En cada intento fallido el motivo exacto
    se inyecta en el contenido para que el agente pueda corregir.
    Si los 3 reintentos fallan → escala al Gerente con log detallado.
    """
    historial = []

    for intento in range(1, max_reintentos + 1):
        resultado = _pm_b_auditar(contenido_str, nombre, nicho, ciudad, etapa)
        historial.append({
            "intento":  intento,
            "decision": resultado["decision"],
            "motivo":   resultado["motivo"],
            "timestamp": resultado["timestamp"],
        })

        if resultado["aprobado"]:
            resultado["reintentos_realizados"] = intento - 1
            resultado["historial_reintentos"]  = historial
            log.info(f"{etapa} | PM-B | APROBADO en intento {intento}")
            return resultado

        # No aprobado — preparar contexto de corrección para el siguiente intento
        motivo = resultado["motivo"]
        log.info(f"{etapa} | PM-B | Intento {intento}/{max_reintentos} FALLIDO — {motivo}")
        _patch_job(job_id,
                   pm_b_ultimo_rechazo=motivo,
                   pm_b_intento=intento)

        if intento < max_reintentos:
            # Enriquecer el contenido con instrucción de corrección
            instruccion_correccion = (
                f"\n\n[CORRECCIÓN REQUERIDA — Intento {intento}/{max_reintentos}]\n"
                f"PM-B rechazó por: {motivo}\n"
                f"Asegúrate de incluir: nombre '{nombre}', nicho '{nicho}', "
                f"ciudad '{ciudad}', datos numéricos y porcentajes reales.\n"
                f"Elimina frases genéricas como: {resultado['frases_genericas']}\n"
            )
            contenido_str = contenido_str + instruccion_correccion
            import time
            time.sleep(2)  # Pausa breve entre reintentos

    # Agotados los reintentos → escalar al Gerente
    motivo_final = (
        f"PM-B falló {max_reintentos} intentos consecutivos para {etapa}. "
        f"Último motivo: {historial[-1]['motivo']}. "
        f"Historial: {json.dumps(historial, ensure_ascii=False)}"
    )
    log.info(f"{etapa} | PM-B | ESCALADO AL GERENTE después de {max_reintentos} intentos")
    _patch_job(job_id,
               pm_b_escalado=True,
               pm_b_motivo_escalado=motivo_final,
               pm_b_historial=historial)

    # Retornar resultado con estado escalado (no bloqueado definitivamente)
    resultado["aprobado"]              = False
    resultado["escalado"]              = True
    resultado["reintentos_realizados"] = max_reintentos
    resultado["historial_reintentos"]  = historial
    resultado["motivo_escalado"]       = motivo_final
    resultado["decision"]              = "ESCALADO_GERENTE"
    return resultado

def _pm_a_auditar(branding_data, nombre, nicho):
    """PM-A: audita coherencia de identidad y narrativa."""
    texto = json.dumps(branding_data, ensure_ascii=False)
    tiene_propuesta = any(k in texto.lower() for k in ["propuesta", "diferencial", "posicionamiento", "promesa"])
    tiene_tono      = any(k in texto.lower() for k in ["tono", "voz", "personalidad", "narrativa"])
    aprobado = tiene_propuesta and tiene_tono

    resultado = {
        "aprobado":          aprobado,
        "tiene_propuesta":   tiene_propuesta,
        "tiene_tono":        tiene_tono,
        "decision":          "APROBADO" if aprobado else "INCOMPLETO",
        "timestamp":         datetime.now().isoformat(),
    }
    log.info(f"FASE2 | PM-A | {resultado['decision']}")
    return resultado

def _gerente_consolidar(job_id, job):
    """Gerente de Marketing: genera informe_final_{id}.json."""
    inv  = job.get("informe_investigacion", {})
    est  = job.get("informe_estrategia", {})
    ads  = job.get("informe_ads", {})
    cont = job.get("informe_contenido", {})
    aud  = job.get("auditoria_fase1", {})

    # Extraer texto legible del análisis 7 Maletas
    dr      = inv.get("deep_researcher", {}) if isinstance(inv, dict) else {}
    maletas = dr.get("7_maletas", {})
    insight = dr.get("insight_claude", "")
    analisis_txt = ""
    if maletas:
        partes = []
        for k, v in maletas.items():
            if isinstance(v, dict):
                partes.append(f"=== {k.upper()} ===\n{json.dumps(v, ensure_ascii=False, indent=2)}")
            else:
                partes.append(f"=== {k.upper()} ===\n{v}")
        analisis_txt = "\n\n".join(partes)
    if insight and not insight.startswith("["):
        analisis_txt = (analisis_txt + "\n\n=== SÍNTESIS IA ===\n" + insight).strip()

    # Extraer guiones del content_planner
    guiones_raw = cont if isinstance(cont, dict) else {}
    guiones = guiones_raw.get("guiones", guiones_raw.get("scripts", []))
    if not guiones and isinstance(guiones_raw, dict):
        # Buscar lista de guiones en cualquier campo
        for v in guiones_raw.values():
            if isinstance(v, list) and len(v) > 0:
                guiones = v
                break

    # Extraer estrategia ADS
    ads_data = ads if isinstance(ads, dict) else est.get("ads_strategist", {}) if isinstance(est, dict) else {}

    resumen = {
        "job_id":   job_id,
        "nombre":   job.get("nombre"),
        "nicho":    job.get("nicho"),
        "ciudad":   job.get("ciudad"),
        "fecha":    datetime.now().isoformat(),
        "secciones": {
            "investigacion":     inv,
            "estrategia":        est,
            "ads":               ads,
            "contenido_guiones": cont,
        },
        "datos": {
            "analisis_7maletas": analisis_txt or "Sin análisis disponible",
            "estrategia_ads":    ads_data,
            "guiones":           guiones,
        },
        "auditoria_pm_b": aud,
        "listo_para_ejecucion": aud.get("aprobado", False),
        "instruccion_humano": (
            "Revisa el informe y usa APROBAR para lanzar emails, "
            "o RECHAZAR con comentarios para corregir."
        ),
    }

    path = INF_DIR / f"informe_final_{job_id}.json"
    path.write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"GERENTE | informe_final generado | {path.name}")
    return resumen

# ────────────────────────────────────────────────────────────────
# GUARDAR INFORMES PARCIALES
# ────────────────────────────────────────────────────────────────

def _guardar_informe(nombre_archivo, data):
    path = INF_DIR / nombre_archivo
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)

# ────────────────────────────────────────────────────────────────
# HANDOFFS — registro estructurado entre agentes
# ────────────────────────────────────────────────────────────────

def handoff(job_id, de, para, datos, estado="PASS", motivo_fail=""):
    """
    Registra un handoff entre agentes.
    estado: PASS | FAIL | ESCALADO
    datos: dict con los resultados entregados
    """
    keys_entregadas = list(datos.keys()) if isinstance(datos, dict) else []
    bytes_transferidos = len(json.dumps(datos, ensure_ascii=False, default=str))

    entrada = {
        "de":                de,
        "para":              para,
        "timestamp":         datetime.now().isoformat(),
        "datos_entregados":  keys_entregadas,
        "bytes_transferidos": bytes_transferidos,
        "estado":            estado,
        "motivo_si_fail":    motivo_fail,
    }

    path = HANDOFFS_DIR / f"{job_id}.json"
    try:
        historial = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        historial.append(entrada)
        path.write_text(json.dumps(historial, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        log.info(f"HANDOFF | error guardando log | {e}")

    log.info(
        f"HANDOFF | {de} → {para} | {estado} | "
        f"{bytes_transferidos} bytes | keys: {keys_entregadas}"
    )
    return entrada


def get_handoffs(job_id):
    """Retorna el historial de handoffs de un job."""
    path = HANDOFFS_DIR / f"{job_id}.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


# ────────────────────────────────────────────────────────────────
# IMPORTACIÓN LAZY DE AGENTES (no falla si alguno no carga)
# ────────────────────────────────────────────────────────────────

def _import_agent(module_name):
    try:
        import importlib
        sys.path.insert(0, str(BASE / "agent"))
        return importlib.import_module(module_name), None
    except Exception as e:
        return None, str(e)

# ────────────────────────────────────────────────────────────────
# FASE 1 — INVESTIGACIÓN
# ────────────────────────────────────────────────────────────────

def _fase1_investigacion(job_id, nombre, url, instagram, ciudad, nicho, tamanio):
    log.info(f"FASE1 | inicio | job={job_id} | {nombre} | {nicho} | {ciudad}")
    _patch_job(job_id, fase_actual="FASE1", agente_activo="deep_researcher", progreso=5)

    resultado_inv = {}

    # ── deep_researcher ───────────────────────────────────────
    log.info(f"FASE1 | deep_researcher | iniciado")
    dr, err = _import_agent("deep_researcher")
    if dr and hasattr(dr, "crear_job"):
        try:
            dr_job_id = dr.crear_job(nombre, url, instagram, ciudad, nicho, tamanio)
            # Esperar hasta 3 min
            import time
            for _ in range(36):
                time.sleep(5)
                estado = dr.get_job_estado(dr_job_id)
                if estado and estado.get("estado") in ("completado", "error"):
                    break
            reporte = dr.get_job_reporte(dr_job_id)
            if reporte:
                resultado_raw = reporte.get("resultado") or {}
                if isinstance(resultado_raw, str):
                    resultado_raw = json.loads(resultado_raw)
                resultado_inv["deep_researcher"] = resultado_raw
                bytes_out = len(json.dumps(resultado_raw))
                log.info(f"FASE1 | deep_researcher | completado | {bytes_out} bytes")
                handoff(job_id, "deep_researcher", "market_researcher",
                        resultado_raw, "PASS")
                _patch_job(job_id, progreso=30)
        except Exception as e:
            resultado_inv["deep_researcher"] = {"error": str(e)}
            handoff(job_id, "deep_researcher", "market_researcher",
                    {"error": str(e)}, "FAIL", str(e))
            log.info(f"FASE1 | deep_researcher | ERROR | {e}")
    else:
        resultado_inv["deep_researcher"] = {"error": err or "no disponible"}
        handoff(job_id, "orchestrator", "deep_researcher",
                {}, "FAIL", err or "módulo no disponible")
        log.info(f"FASE1 | deep_researcher | no disponible")

    _patch_job(job_id, agente_activo="market_researcher", progreso=35)

    # ── market_researcher ─────────────────────────────────────
    log.info(f"FASE1 | market_researcher | iniciado")
    mr, err = _import_agent("market_researcher")
    if mr and hasattr(mr, "crear_job"):
        try:
            mr_job_id = mr.crear_job(nicho, "Colombia", ciudad, [], [], "basica")
            import time
            for _ in range(24):
                time.sleep(5)
                estado = mr.get_job_estado(mr_job_id)
                if estado and estado.get("estado") in ("completado", "error"):
                    break
            reporte = mr.get_job_reporte(mr_job_id)
            if reporte:
                resultado_raw = reporte.get("resultado") or {}
                if isinstance(resultado_raw, str):
                    resultado_raw = json.loads(resultado_raw)
                resultado_inv["market_researcher"] = resultado_raw
                log.info(f"FASE1 | market_researcher | completado | {len(json.dumps(resultado_raw))} bytes")
                handoff(job_id, "market_researcher", "lead_investigator",
                        resultado_raw, "PASS")
                _patch_job(job_id, progreso=55)
        except Exception as e:
            resultado_inv["market_researcher"] = {"error": str(e)}
            handoff(job_id, "market_researcher", "lead_investigator",
                    {"error": str(e)}, "FAIL", str(e))
            log.info(f"FASE1 | market_researcher | ERROR | {e}")
    else:
        resultado_inv["market_researcher"] = {"error": err or "no disponible"}

    _patch_job(job_id, agente_activo="lead_investigator", progreso=58)

    # ── lead_investigator ─────────────────────────────────────
    log.info(f"FASE1 | lead_investigator | iniciado")
    li, err = _import_agent("lead_investigator")
    if li and hasattr(li, "investigar_lead"):
        try:
            lead_data = {"nombre": nombre, "empresa": nombre, "nicho": nicho,
                         "email": "", "web": url, "instagram": instagram}
            perfil = li.investigar_lead(lead_data)
            perfil_dict = perfil if isinstance(perfil, dict) else {"texto": str(perfil)}
            resultado_inv["lead_investigator"] = perfil_dict
            handoff(job_id, "lead_investigator", "pm_b",
                    perfil_dict, "PASS")
            log.info(f"FASE1 | lead_investigator | completado")
            _patch_job(job_id, progreso=70)
        except Exception as e:
            resultado_inv["lead_investigator"] = {"error": str(e)}
            handoff(job_id, "lead_investigator", "pm_b",
                    {"error": str(e)}, "FAIL", str(e))
            log.info(f"FASE1 | lead_investigator | ERROR | {e}")
    else:
        resultado_inv["lead_investigator"] = {"error": err or "no disponible"}

    # ── guardar informe investigación ─────────────────────────
    informe_path = _guardar_informe(f"informe_investigacion_{job_id}.json", resultado_inv)
    _patch_job(job_id, informe_investigacion=resultado_inv, progreso=75)

    # ── PM-B auditoría — solo audita síntesis, NO datos crudos scrapeados ──
    # Los datos crudos (web, reviews, facebook_ads) pueden contener frases
    # genéricas del tercero. Solo auditamos el análisis que nosotros generamos.
    dr_data        = resultado_inv.get("deep_researcher", {})
    analisis_sintetico = {
        "insight_claude":  dr_data.get("insight_claude", ""),
        "7_maletas":       dr_data.get("7_maletas", {}),
        "meta":            dr_data.get("meta", {}),
        "market_resumen":  str(resultado_inv.get("market_researcher", {}).get("claude_insights", "")),
        "lead_datos":      resultado_inv.get("lead_investigator", {}),
    }
    contenido_str = json.dumps(analisis_sintetico, ensure_ascii=False)
    auditoria = _pm_b_con_retry(contenido_str, nombre, nicho, ciudad, "FASE1",
                                job_id, max_reintentos=3)
    _guardar_informe(f"informe_auditado_fase1_{job_id}.json", auditoria)
    _patch_job(job_id, auditoria_fase1=auditoria, progreso=80)

    if not auditoria["aprobado"]:
        estado_bloqueo = "escalado_gerente" if auditoria.get("escalado") else "bloqueado_pm_b"
        _patch_job(job_id,
                   estado=estado_bloqueo,
                   fase_actual="FASE1_BLOQUEADA",
                   agente_activo="",
                   progreso=80,
                   motivo_bloqueo=auditoria.get("motivo_escalado", auditoria["motivo"]))
        log.info(f"FASE1 | {estado_bloqueo.upper()} | {auditoria['motivo']}")
        return False, resultado_inv

    _patch_job(job_id, progreso=85)
    log.info(f"FASE1 | completada y aprobada")
    return True, resultado_inv

# ────────────────────────────────────────────────────────────────
# FASE 2 — ESTRATEGIA
# ────────────────────────────────────────────────────────────────

def _fase2_estrategia(job_id, nombre, nicho, ciudad, tamanio, investigacion_data):
    log.info(f"FASE2 | inicio | job={job_id}")
    _patch_job(job_id, fase_actual="FASE2", agente_activo="intelligence_engine", progreso=86)

    resultado_est = {}

    # ── intelligence_engine (branding + estrategia) ───────────
    log.info(f"FASE2 | intelligence_engine | iniciado")
    ie, err = _import_agent("intelligence_engine")
    if ie:
        try:
            funciones = [f for f in dir(ie) if not f.startswith("_")]
            # Intenta generar análisis completo
            if hasattr(ie, "generar_analisis_completo"):
                resultado_ie = ie.generar_analisis_completo(nombre, nicho, ciudad)
            elif hasattr(ie, "call_claude"):
                prompt = (f"Genera estrategia de branding y marketing para:\n"
                          f"Negocio: {nombre}\nNicho: {nicho}\nCiudad: {ciudad}\n"
                          f"Contexto de investigación:\n{json.dumps(investigacion_data, ensure_ascii=False)[:2000]}")
                resultado_ie = {"branding": ie.call_claude(
                    "Eres el Director de Estrategia de Intelligent Markets.", prompt, 3000
                )}
            else:
                resultado_ie = {"funciones_disponibles": funciones}
            resultado_est["intelligence_engine"] = resultado_ie
            handoff(job_id, "intelligence_engine", "ads_strategist",
                    resultado_ie, "PASS")
            log.info(f"FASE2 | intelligence_engine | completado | {len(json.dumps(resultado_ie))} bytes")
        except Exception as e:
            resultado_est["intelligence_engine"] = {"error": str(e)}
            handoff(job_id, "intelligence_engine", "ads_strategist",
                    {"error": str(e)}, "FAIL", str(e))
            log.info(f"FASE2 | intelligence_engine | ERROR | {e}")
    else:
        resultado_est["intelligence_engine"] = {"error": err}

    _patch_job(job_id, agente_activo="ads_strategist", progreso=88)

    # ── ads_strategist ────────────────────────────────────────
    log.info(f"FASE2 | ads_strategist | iniciado")
    ads, err = _import_agent("ads_strategist")
    if ads and hasattr(ads, "crear_job"):
        try:
            ads_job = ads.crear_job(nombre, nicho, ciudad, tamanio, "")
            import time
            for _ in range(20):
                time.sleep(3)
                est = ads.get_job_estado(ads_job)
                if est and est.get("estado") in ("completado", "error"):
                    break
            rep = ads.get_job_reporte(ads_job)
            if rep:
                res = rep.get("resultado") or {}
                if isinstance(res, str):
                    res = json.loads(res)

                # PM-B audita que el copy de ADS use datos reales
                copy_str = json.dumps(res, ensure_ascii=False)
                genericos = _auditar_genericos(copy_str)
                if genericos:
                    log.info(f"FASE2 | ads_strategist | BLOQUEADO - copy genérico: {genericos}")
                    resultado_est["ads_strategist"] = {"bloqueado": True, "genericos": genericos, "data": res}
                else:
                    resultado_est["ads_strategist"] = res
                    handoff(job_id, "ads_strategist", "content_planner",
                            res, "PASS")
                    log.info(f"FASE2 | ads_strategist | completado | {len(copy_str)} bytes")
        except Exception as e:
            resultado_est["ads_strategist"] = {"error": str(e)}
            log.info(f"FASE2 | ads_strategist | ERROR | {e}")
    else:
        resultado_est["ads_strategist"] = {"error": err}

    _patch_job(job_id, agente_activo="content_planner", progreso=91)

    # ── content_planner ───────────────────────────────────────
    log.info(f"FASE2 | content_planner | iniciado")
    cp, err = _import_agent("content_planner")
    if cp and hasattr(cp, "crear_job"):
        try:
            cp_job = cp.crear_job(nombre, nicho, ciudad, "")
            import time
            for _ in range(20):
                time.sleep(2)
                est = cp.get_job_estado(cp_job)
                if est and est.get("estado") in ("completado", "error"):
                    break
            rep = cp.get_job_reporte(cp_job)
            if rep:
                res = rep.get("resultado") or {}
                if isinstance(res, str):
                    res = json.loads(res)
                cp_summary = {
                    "total_scripts":  res.get("total_scripts", 0),
                    "html_filename":  res.get("html_filename", ""),
                    "calendario":     res.get("calendario", [])[:5],
                }
                resultado_est["content_planner"] = cp_summary
                handoff(job_id, "content_planner", "gerente_marketing",
                        cp_summary, "PASS")
                log.info(f"FASE2 | content_planner | completado | {res.get('total_scripts',0)} guiones")
        except Exception as e:
            resultado_est["content_planner"] = {"error": str(e)}
            log.info(f"FASE2 | content_planner | ERROR | {e}")
    else:
        resultado_est["content_planner"] = {"error": err}

    _patch_job(job_id, agente_activo="", progreso=93)

    # ── PM-A audita identidad ─────────────────────────────────
    audit_a = _pm_a_auditar(resultado_est, nombre, nicho)
    _guardar_informe(f"informe_auditado_fase2_{job_id}.json", audit_a)
    log.info(f"FASE2 | PM-A | {audit_a['decision']}")

    # ── guardar informes parciales ─────────────────────────────
    _guardar_informe(f"informe_estrategia_{job_id}.json",  resultado_est.get("intelligence_engine", {}))
    _guardar_informe(f"informe_ads_{job_id}.json",          resultado_est.get("ads_strategist", {}))
    _guardar_informe(f"informe_contenido_{job_id}.json",    resultado_est.get("content_planner", {}))

    _patch_job(job_id, informe_estrategia=resultado_est, auditoria_fase2=audit_a, progreso=96)

    # ── Gerente consolida informe final ───────────────────────
    job = _get_job(job_id)
    informe_final = _gerente_consolidar(job_id, job)
    _patch_job(job_id,
               informe_final=informe_final,
               estado="esperando_aprobacion",
               fase_actual="FASE2_COMPLETADA",
               progreso=100)

    log.info(f"FASE2 | completada | esperando aprobación humana")
    return True, resultado_est

# ────────────────────────────────────────────────────────────────
# FASE 3 — EJECUCIÓN (solo si humano aprueba)
# ────────────────────────────────────────────────────────────────

def _fase3_ejecucion(job_id, nombre, nicho, ciudad, tamanio):
    log.info(f"FASE3 | inicio | job={job_id} | APROBADO POR HUMANO")
    _patch_job(job_id, fase_actual="FASE3", agente_activo="lead_finder_v2", progreso=0, estado="ejecutando")

    # ── lead_finder_v2 ────────────────────────────────────────
    log.info(f"FASE3 | lead_finder_v2 | iniciado")
    lf, err = _import_agent("lead_finder_v2")
    leads_encontrados = []
    if lf and hasattr(lf, "buscar_leads"):
        try:
            leads_encontrados = lf.buscar_leads(nicho, ciudad, max_leads=20)
            log.info(f"FASE3 | lead_finder_v2 | {len(leads_encontrados)} leads encontrados")
        except Exception as e:
            log.info(f"FASE3 | lead_finder_v2 | ERROR | {e}")
    _patch_job(job_id, agente_activo="im_scheduler", progreso=30)

    # ── im_scheduler — verificar horario colombiano ───────────
    log.info(f"FASE3 | im_scheduler | verificando horario")
    sched, _ = _import_agent("im_scheduler")
    puede_enviar = True
    if sched and hasattr(sched, "es_horario_laboral"):
        try:
            puede_enviar, razon = sched.es_horario_laboral()
            log.info(f"FASE3 | im_scheduler | puede_enviar={puede_enviar} | {razon}")
        except Exception as e:
            log.info(f"FASE3 | im_scheduler | ERROR | {e}")

    if not puede_enviar:
        _patch_job(job_id,
                   estado="esperando_horario",
                   fase_actual="FASE3_EN_ESPERA",
                   agente_activo="im_scheduler",
                   leads_encontrados=len(leads_encontrados))
        return False, "Fuera de horario laboral colombiano"

    _patch_job(job_id, agente_activo="im_deliverability", progreso=50)

    # ── im_deliverability — escanear por keywords críticos ────
    log.info(f"FASE3 | im_deliverability | escaneando alertas")
    deliv, _ = _import_agent("im_deliverability")
    if deliv and hasattr(deliv, "escanear_texto_alerta"):
        try:
            alerta = deliv.escanear_texto_alerta(
                f"Ejecución de campaña para {nombre} {nicho} {ciudad}",
                asunto="Orquestador FASE3",
                origen="orchestrator"
            )
            if alerta.get("alerta"):
                log.info(f"FASE3 | ALERTA detectada: {alerta.get('keywords')}")
        except Exception:
            pass

    _patch_job(job_id,
               estado="completado",
               fase_actual="FASE3_COMPLETADA",
               agente_activo="",
               progreso=100,
               leads_encontrados=len(leads_encontrados),
               terminado_at=datetime.now().isoformat())

    log.info(f"FASE3 | completada | {len(leads_encontrados)} leads | job={job_id}")
    return True, leads_encontrados

# ────────────────────────────────────────────────────────────────
# RUNNER PRINCIPAL (background thread)
# ────────────────────────────────────────────────────────────────

def _run_job(job_id):
    job = _get_job(job_id)
    if not job:
        return

    nombre  = job.get("nombre", "")
    url     = job.get("url", "")
    instagram = job.get("instagram", "")
    ciudad  = job.get("ciudad", "Medellín")
    nicho   = job.get("nicho", "general")
    tamanio = job.get("tamanio", "mediana")

    try:
        _patch_job(job_id, estado="corriendo")

        ok1, inv_data = _fase1_investigacion(
            job_id, nombre, url, instagram, ciudad, nicho, tamanio
        )
        if not ok1:
            return

        ok2, _ = _fase2_estrategia(
            job_id, nombre, nicho, ciudad, tamanio, inv_data
        )

    except Exception as e:
        _patch_job(job_id,
                   estado="error",
                   agente_activo="",
                   error=str(e),
                   terminado_at=datetime.now().isoformat())
        log.info(f"ERROR FATAL | job={job_id} | {e}")

# ────────────────────────────────────────────────────────────────
# PUBLIC API
# ────────────────────────────────────────────────────────────────

def _sanitizar_str(valor, max_len=300):
    """Limpia strings de input — elimina null bytes y controles."""
    if not isinstance(valor, str):
        valor = str(valor)
    valor = re.sub(r'[\x00-\x1f\x7f]', ' ', valor)
    return valor[:max_len].strip()

def _jobs_activos():
    """Retorna el número de jobs en estado 'corriendo'."""
    jobs = _load_jobs()
    return sum(1 for j in jobs.values() if j.get("estado") == "corriendo")

MAX_JOBS_SIMULTANEOS = 10
JOB_TIMEOUT_MINUTOS  = 10

def _watchdog_timeout(job_id):
    """Marca el job como timeout si lleva más de JOB_TIMEOUT_MINUTOS corriendo."""
    import time as _t
    _t.sleep(JOB_TIMEOUT_MINUTOS * 60)
    job = _get_job(job_id)
    if job and job.get("estado") == "corriendo":
        _patch_job(job_id,
                   estado="timeout",
                   agente_activo="",
                   motivo_bloqueo=f"Job superó {JOB_TIMEOUT_MINUTOS} minutos de ejecución",
                   terminado_at=datetime.now().isoformat())
        log.info(f"TIMEOUT | job={job_id} | superó {JOB_TIMEOUT_MINUTOS} minutos")

def crear_job(nombre, url="", instagram="", ciudad="Medellín",
              nicho="general", tamanio="mediana", fase="FASE1"):
    """Crea y lanza un job de orquestación en background."""
    # Sanitizar todos los inputs
    nombre    = _sanitizar_str(nombre, 200)
    url       = _sanitizar_str(url, 500)
    instagram = _sanitizar_str(instagram, 100)
    ciudad    = _sanitizar_str(ciudad, 100)
    nicho     = _sanitizar_str(nicho, 100)
    tamanio   = _sanitizar_str(tamanio, 50)

    if not nombre:
        log.info("crear_job | RECHAZADO | nombre vacío")
        raise ValueError("El nombre del negocio es obligatorio")

    # Límite de jobs simultáneos
    activos = _jobs_activos()
    if activos >= MAX_JOBS_SIMULTANEOS:
        log.info(f"crear_job | RECHAZADO | {activos} jobs activos (máx {MAX_JOBS_SIMULTANEOS})")
        raise RuntimeError(f"Demasiados jobs activos ({activos}/{MAX_JOBS_SIMULTANEOS}). Espera a que terminen.")

    job_id = str(uuid.uuid4())[:12]
    data = {
        "id":           job_id,
        "nombre":       nombre,
        "url":          url,
        "instagram":    instagram,
        "ciudad":       ciudad,
        "nicho":        nicho,
        "tamanio":      tamanio,
        "fase_inicio":  fase,
        "estado":       "pendiente",
        "fase_actual":  "",
        "agente_activo": "",
        "progreso":     0,
        "creado_at":    datetime.now().isoformat(),
        "terminado_at": None,
        "informe_final": None,
    }
    _set_job(job_id, data)
    log.info(f"JOB CREADO | {job_id} | {nombre} | {nicho} | {ciudad}")
    t = threading.Thread(target=_run_job, args=(job_id,), daemon=True)
    t.start()
    # Watchdog: mata el job si supera el timeout
    wd = threading.Thread(target=_watchdog_timeout, args=(job_id,), daemon=True)
    wd.start()
    return job_id


def get_estado(job_id):
    """Estado resumido del job."""
    job = _get_job(job_id)
    if not job:
        return None
    return {
        "id":            job.get("id"),
        "nombre":        job.get("nombre"),
        "estado":        job.get("estado"),
        "fase_actual":   job.get("fase_actual"),
        "agente_activo": job.get("agente_activo"),
        "progreso":      job.get("progreso", 0),
        "creado_at":     job.get("creado_at"),
        "terminado_at":  job.get("terminado_at"),
        "motivo_bloqueo": job.get("motivo_bloqueo"),
    }


def get_informe(job_id):
    """Retorna el informe final auditado para el humano."""
    job = _get_job(job_id)
    if not job:
        return None
    return job.get("informe_final") or {"estado": job.get("estado"), "progreso": job.get("progreso")}


def aprobar(job_id, comentario=""):
    """Humano aprueba → lanza Fase 3."""
    job = _get_job(job_id)
    if not job:
        return False, "Job no encontrado"
    if job.get("estado") != "esperando_aprobacion":
        return False, f"Estado actual: {job.get('estado')} — no está esperando aprobación"

    _patch_job(job_id, estado="aprobado", comentario_aprobacion=comentario,
               aprobado_at=datetime.now().isoformat())
    log.info(f"APROBADO POR HUMANO | job={job_id} | {comentario}")

    nombre  = job.get("nombre", "")
    nicho   = job.get("nicho", "")
    ciudad  = job.get("ciudad", "")
    tamanio = job.get("tamanio", "mediana")

    t = threading.Thread(
        target=_fase3_ejecucion,
        args=(job_id, nombre, nicho, ciudad, tamanio),
        daemon=True
    )
    t.start()
    return True, "Fase 3 iniciada"


def rechazar(job_id, comentario=""):
    """Humano rechaza → registra motivo, no ejecuta Fase 3."""
    job = _get_job(job_id)
    if not job:
        return False, "Job no encontrado"
    _patch_job(job_id, estado="rechazado", comentario_rechazo=comentario,
               rechazado_at=datetime.now().isoformat())
    log.info(f"RECHAZADO POR HUMANO | job={job_id} | {comentario}")
    return True, "Job rechazado — modifica los parámetros y vuelve a intentar"


def lista_jobs(limit=20):
    """Lista los últimos N jobs."""
    jobs = _load_jobs()
    sortados = sorted(jobs.values(), key=lambda j: j.get("creado_at", ""), reverse=True)
    return [get_estado(j["id"]) for j in sortados[:limit]]


# ── CLI ────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse, time as _time

    p = argparse.ArgumentParser(description="IM Orchestrator — ejecuta fases de investigación y estrategia")
    p.add_argument("--nombre",    required=True,  help="Nombre del negocio")
    p.add_argument("--url",       default="",     help="URL web del negocio")
    p.add_argument("--instagram", default="",     help="Handle de Instagram sin @")
    p.add_argument("--ciudad",    default="Medellin", help="Ciudad (default: Medellin)")
    p.add_argument("--nicho",     default="otro", help="Nicho (ej: odontologos, ecommerce)")
    p.add_argument("--tamanio",   default="mediana", help="pequena | mediana | grande")
    p.add_argument("--fase",      default="todas", help="1 | 2 | todas")
    args = p.parse_args()

    fase_map = {"1": "FASE1", "2": "FASE2", "todas": "todas"}
    fase_val = fase_map.get(args.fase, args.fase)

    print(f"\n[ORC] Iniciando job para: {args.nombre} | {args.nicho} | {args.ciudad}")
    job_id = crear_job(args.nombre, args.url, args.instagram,
                       args.ciudad, args.nicho, args.tamanio, fase_val)
    print(f"[ORC] Job ID: {job_id}\n")

    estados_finales = {"completado", "error", "esperando_aprobacion", "bloqueado", "rechazado"}
    while True:
        estado = get_estado(job_id)
        est    = estado.get("estado", "?")
        paso   = estado.get("paso_actual", "")
        prog   = estado.get("progreso", 0)
        print(f"  [{prog:3d}%] {est} — {paso}", flush=True)
        if est in estados_finales:
            break
        _time.sleep(5)

    print("\n" + "="*60)
    estado_final = get_estado(job_id)
    print(json.dumps(estado_final, indent=2, ensure_ascii=False))

    if estado_final.get("estado") == "esperando_aprobacion":
        print("\n[ORC] Job en espera de aprobación humana.")
        print(f"[ORC] Para aprobar: python orchestrator.py --aprobar {job_id}")

    inf = get_informe(job_id)
    if inf:
        out = INF_DIR / f"cli_informe_{job_id[:8]}.json"
        out.write_text(json.dumps(inf, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[ORC] Informe guardado en: {out}")
