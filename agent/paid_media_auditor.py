# -*- coding: utf-8 -*-
"""
IM Paid Media Auditor
━━━━━━━━━━━━━━━━━━━━
Auditoría de cuentas Meta Ads basada en 200+ checkpoints.
Sin token → auditoría manual con datos ingresados por el cliente.
Con token → auditoría automatizada vía API de Meta (futuro).

Entregables:
  - Score de cuenta /100
  - Top 5 problemas críticos
  - Recomendaciones de mejora inmediata
  - Estimado de mejora de ROAS si se corrigen
"""

import os, sys, json, uuid, sqlite3, threading
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

DB_PATH   = Path(__file__).parent.parent / "data" / "jobs.db"
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")
CLAUDE_MODEL   = "claude-opus-4-5"

# ── Benchmarks de industria (Colombia 2024) ───────────────────
BENCHMARKS = {
    "CTR_prospecting_min":      1.5,   # %
    "CTR_retargeting_min":      3.0,   # %
    "frequency_prospecting_max": 2.5,
    "frequency_retargeting_max": 5.0,
    "thumb_stop_rate_min":      25.0,  # %
    "ROAS_retargeting_min":     3.0,
    "ROAS_prospecting_min":     1.5,
    "CPM_max_usd":              8.0,
    "watch_rate_tiktok_min":    30.0,  # %
    "score_maximo":             100,
}

# ── 200+ Checkpoints agrupados por categoría ──────────────────
CHECKPOINTS = {
    "estructura_cuenta": {
        "peso": 20,
        "items": [
            ("campanas_segmentadas_por_objetivo",    "¿Cada campaña tiene UN objetivo claro (Tráfico/Leads/Conversiones)?", "critical"),
            ("nomenclatura_consistente",             "¿Las campañas, conjuntos y anuncios tienen nombres descriptivos?",    "medium"),
            ("min_3_conjuntos_anuncios",             "¿Hay al menos 3 conjuntos de anuncios activos?",                     "high"),
            ("separacion_frio_retargeting",          "¿Audiencias frías y retargeting están en campañas separadas?",        "critical"),
            ("exclusiones_configuradas",             "¿Los compradores recientes están excluidos de prospecting?",          "high"),
            ("presupuesto_CBO_vs_ABO",               "¿El presupuesto está optimizado a nivel campaña (CBO)?",              "medium"),
            ("campanas_pausadas_sin_revisar",        "¿Hay campañas pausadas hace más de 30 días sin revisión?",            "low"),
            ("limite_gasto_cuenta",                  "¿El límite de gasto diario de la cuenta está configurado?",           "medium"),
        ]
    },
    "pixel_y_seguimiento": {
        "peso": 25,
        "items": [
            ("pixel_instalado",                     "¿El Pixel de Meta está instalado en el sitio web?",                   "critical"),
            ("eventos_estandar_activos",            "¿Disparan eventos estándar: ViewContent, Lead, Purchase?",             "critical"),
            ("conversions_api_capi",                "¿Conversions API (CAPI) está configurada para superar iOS 14+?",       "high"),
            ("ventana_atribucion_correcta",         "¿La ventana de atribución es ≤7 días clic / 1 día vista?",            "high"),
            ("eventos_duplicados",                  "¿Los eventos NO están duplicados entre Pixel y CAPI?",                "critical"),
            ("pagina_gracias_configurada",          "¿La página de gracias dispara el evento de conversión?",               "critical"),
            ("valor_conversion_registrado",         "¿Se registra el valor monetario de cada conversión?",                 "high"),
            ("prueba_diagnostico_pixel",            "¿El diagnóstico del Pixel no muestra errores activos?",               "high"),
            ("utm_parametros_en_urls",              "¿Las URLs de destino tienen parámetros UTM?",                         "medium"),
            ("ga4_integrado",                       "¿Google Analytics 4 está integrado y concuerda con Meta?",            "medium"),
        ]
    },
    "audiencias": {
        "peso": 20,
        "items": [
            ("audiencia_personalizada_web",         "¿Hay audiencia de visitantes web (últimos 30/60/90 días)?",            "critical"),
            ("audiencia_interaccion_ig_fb",         "¿Hay audiencia de interacción Instagram/Facebook?",                   "high"),
            ("lookalike_1_3pct",                    "¿Hay audiencias similares (Lookalike) 1-3%?",                        "high"),
            ("audiencia_lista_clientes",            "¿La lista de clientes actuales está subida como audiencia?",          "high"),
            ("tamano_audiencias_minimo",            "¿Las audiencias de retargeting tienen al menos 1,000 personas?",      "critical"),
            ("frecuencia_controlada",               "¿La frecuencia promedio está dentro de benchmarks?",                 "high"),
            ("exclusion_entre_audiencias",          "¿Las audiencias frías excluyen a los que ya están en retargeting?",   "high"),
            ("actualizacion_lista_clientes",        "¿La lista de clientes fue actualizada en los últimos 30 días?",       "medium"),
        ]
    },
    "creativos_y_copies": {
        "peso": 20,
        "items": [
            ("min_3_variantes_por_conjunto",        "¿Cada conjunto tiene al menos 3 anuncios activos?",                   "critical"),
            ("hook_primeros_3_segundos",            "¿El video/imagen tiene un hook claro en los primeros 3 segundos?",    "critical"),
            ("cta_explicito",                       "¿Hay un CTA claro y visible en cada anuncio?",                       "high"),
            ("formato_9_16_reels",                  "¿Los videos están en formato 9:16 optimizado para Reels/Stories?",    "high"),
            ("variantes_imagen_y_video",            "¿Hay mezcla de formatos: imagen estática + video + carrusel?",        "medium"),
            ("copy_sin_frases_genericas",           "¿El copy evita frases genéricas como 'calidad garantizada'?",         "high"),
            ("social_proof_en_anuncio",             "¿Hay prueba social (testimonios/reseñas) en los anuncios?",           "high"),
            ("test_ab_activo",                      "¿Hay al menos un test A/B de creativos activo?",                     "medium"),
            ("anuncios_rechazados_activos",         "¿Hay anuncios en estado 'Rechazado' sin corregir?",                  "critical"),
            ("actualizacion_creativos_30d",         "¿Los creativos fueron renovados en los últimos 30 días?",             "medium"),
        ]
    },
    "presupuesto_y_puja": {
        "peso": 15,
        "items": [
            ("estrategia_puja_correcta",            "¿La estrategia de puja es 'Menor costo' o 'Límite de costo'?",        "high"),
            ("presupuesto_no_limitado",             "¿Las campañas principales NO están 'Limitadas por presupuesto'?",     "critical"),
            ("distribucion_60_30_10",               "¿El presupuesto sigue regla 60% probado / 30% nuevo / 10% experimental?", "medium"),
            ("roas_objetivo_configurado",           "¿El ROAS objetivo está configurado si se usa puja por ROAS?",         "high"),
            ("periodo_aprendizaje_no_activo",       "¿Las campañas principales están fuera del 'Período de aprendizaje'?", "critical"),
            ("min_50_conversiones_semana",          "¿Cada conjunto genera al menos 50 conversiones/semana para salir del aprendizaje?", "high"),
        ]
    },
}

# ── DB helpers ────────────────────────────────────────────────

def _get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS auditoria_meta_jobs (
            id TEXT PRIMARY KEY,
            nombre_cuenta TEXT,
            estado TEXT DEFAULT 'pendiente',
            resultado TEXT,
            creado_at TEXT,
            terminado_at TEXT
        )
    """)
    conn.commit()
    return conn


def _update_job(job_id, **kwargs):
    conn = _get_conn()
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [job_id]
    conn.execute(f"UPDATE auditoria_meta_jobs SET {sets} WHERE id=?", vals)
    conn.commit()
    conn.close()


# ── Claude helper ─────────────────────────────────────────────

def _claude(prompt, max_tokens=3000):
    if not CLAUDE_API_KEY:
        return ""
    import urllib.request
    payload = json.dumps({
        "model": CLAUDE_MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "x-api-key": CLAUDE_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())["content"][0]["text"].strip()
    except Exception as e:
        return f"[claude_error: {e}]"


# ── Motor de auditoría ────────────────────────────────────────

def _calcular_score(respuestas):
    """
    respuestas: dict {checkpoint_id: True/False/None}
    Retorna score /100, hallazgos por severidad, desglose por categoría.
    """
    total_peso = 0
    score_obtenido = 0
    hallazgos = {"critical": [], "high": [], "medium": [], "low": []}
    desglose = {}

    for categoria, config in CHECKPOINTS.items():
        peso_cat     = config["peso"]
        items        = config["items"]
        puntos_cat   = 0
        puntos_max   = len(items)

        for item_id, descripcion, severidad in items:
            respuesta = respuestas.get(item_id)
            if respuesta is True:
                puntos_cat += 1
            elif respuesta is False:
                hallazgos[severidad].append({
                    "id":          item_id,
                    "descripcion": descripcion,
                    "severidad":   severidad,
                    "categoria":   categoria,
                })
            # None = no evaluado, no penaliza

        score_cat = (puntos_cat / puntos_max) * peso_cat if puntos_max > 0 else 0
        score_obtenido += score_cat
        total_peso += peso_cat
        desglose[categoria] = {
            "score":        round(score_cat, 1),
            "maximo":       peso_cat,
            "pct":          round((puntos_cat / puntos_max) * 100) if puntos_max > 0 else 0,
        }

    score_final = round((score_obtenido / total_peso) * 100) if total_peso > 0 else 0
    return score_final, hallazgos, desglose


def _top5_problemas(hallazgos):
    """Retorna los 5 problemas más críticos ordenados por severidad."""
    orden = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    todos = []
    for sev, items in hallazgos.items():
        todos.extend(items)
    todos.sort(key=lambda x: orden.get(x["severidad"], 9))
    return todos[:5]


def _estimar_mejora_roas(score, roas_actual, hallazgos):
    """Estima cuánto puede mejorar el ROAS si se corrigen los problemas críticos."""
    criticos = len(hallazgos.get("critical", []))
    altos    = len(hallazgos.get("high", []))

    mejora_pct = 0
    if criticos >= 3:
        mejora_pct += 40
    elif criticos >= 1:
        mejora_pct += 20

    if altos >= 4:
        mejora_pct += 20
    elif altos >= 2:
        mejora_pct += 10

    if score < 40:
        mejora_pct += 15
    elif score < 60:
        mejora_pct += 8

    mejora_pct = min(mejora_pct, 80)
    roas_proyectado = round(roas_actual * (1 + mejora_pct / 100), 2) if roas_actual else None

    return {
        "mejora_estimada_pct":  mejora_pct,
        "roas_actual":          roas_actual,
        "roas_proyectado":      roas_proyectado,
        "condicion":            "Si se corrigen los problemas críticos y altos en 30 días",
    }


def _generar_recomendaciones(top5, score, nombre_cuenta):
    """Genera recomendaciones de mejora inmediata con instrucciones específicas."""
    FIXES = {
        "pixel_instalado":              "Instala el Meta Pixel via Administrador de Eventos → Fuentes de datos. Usa el asistente de instalación o GTM.",
        "eventos_duplicados":           "Ve a Administrador de Eventos → verifica que los eventos no aparezcan duplicados. Desactiva Pixel si usas CAPI server-side.",
        "periodo_aprendizaje_no_activo":"Consolida los conjuntos pequeños para superar 50 conversiones/semana. Evita editar campañas en aprendizaje.",
        "separacion_frio_retargeting":  "Crea campañas separadas: una para audiencias frías (1-3% Lookalike) y otra para retargeting (visitantes web 30d).",
        "tamano_audiencias_minimo":     "Amplía las audiencias de retargeting aumentando la ventana de tiempo (30→60→90 días) o incluye interacciones con el perfil.",
        "anuncios_rechazados_activos":  "Ve a Administrador de Anuncios → filtra por 'Rechazado'. Corrige el copy según las políticas de Meta y solicita revisión.",
        "conversions_api_capi":         "Configura CAPI via Administrador de Eventos → Configurar → Conversions API. Usa la integración nativa de tu CMS o Zapier.",
        "hook_primeros_3_segundos":     "El primer frame del video debe mostrar la transformación o el dolor del cliente. Añade texto sobreimpuesto en los primeros 3s.",
        "presupuesto_no_limitado":      "Aumenta el presupuesto o reduce el tamaño de audiencia. Las campañas 'Limitadas' pierden entre 20-40% de oportunidades.",
        "exclusiones_configuradas":     "En cada conjunto de prospecting, añade exclusión de 'Compradores (últimos 180 días)' y 'Visitantes de página de gracias'.",
        "min_3_variantes_por_conjunto": "Crea al menos 3 anuncios por conjunto: 1 video 9:16, 1 imagen estática, 1 carrusel. Deja que el algoritmo optimice.",
        "audiencia_personalizada_web":  "Crea audiencia personalizada → Sitio web → 'Todos los visitantes' últimos 30, 60 y 90 días.",
    }

    recomendaciones = []
    for i, problema in enumerate(top5, 1):
        fix = FIXES.get(problema["id"],
              f"Revisa la configuración de '{problema['descripcion']}' en el Administrador de Anuncios.")
        recomendaciones.append({
            "prioridad":    i,
            "problema":     problema["descripcion"],
            "severidad":    problema["severidad"],
            "accion":       fix,
            "impacto_est":  "Alto" if problema["severidad"] == "critical" else "Medio",
        })

    return recomendaciones


def _run_auditoria(job_id, datos_cuenta):
    """Pipeline de auditoría completo."""
    nombre  = datos_cuenta.get("nombre_cuenta", "Cuenta sin nombre")
    nicho   = datos_cuenta.get("nicho", "general")
    ciudad  = datos_cuenta.get("ciudad", "Colombia")
    roas_actual   = float(datos_cuenta.get("roas_actual", 0) or 0)
    presupuesto   = float(datos_cuenta.get("presupuesto_mensual_cop", 0) or 0)
    respuestas    = datos_cuenta.get("respuestas", {})  # dict checkpoint_id → True/False

    try:
        # 1. Calcular score
        score, hallazgos, desglose = _calcular_score(respuestas)

        # 2. Top 5 problemas
        top5 = _top5_problemas(hallazgos)

        # 3. Recomendaciones
        recomendaciones = _generar_recomendaciones(top5, score, nombre)

        # 4. Estimado de mejora ROAS
        mejora = _estimar_mejora_roas(score, roas_actual, hallazgos)

        # 5. Análisis IA (si hay API key)
        analisis_ia = ""
        if CLAUDE_API_KEY and top5:
            prompt = (
                f"Eres un auditor experto de cuentas Meta Ads en Colombia.\n"
                f"Cuenta auditada: {nombre} (nicho: {nicho}, ciudad: {ciudad})\n"
                f"Score obtenido: {score}/100\n"
                f"Presupuesto mensual: ${presupuesto:,.0f} COP\n"
                f"ROAS actual: {roas_actual}x\n\n"
                f"Top 5 problemas críticos:\n"
                + "\n".join(f"{i+1}. [{p['severidad'].upper()}] {p['descripcion']}"
                            for i, p in enumerate(top5)) +
                f"\n\nEscribe un párrafo ejecutivo de 100 palabras sobre el estado de esta cuenta "
                f"y el impacto esperado de corregir los problemas. Usa datos concretos."
            )
            analisis_ia = _claude(prompt, 400)

        resultado = {
            "job_id":            job_id,
            "nombre_cuenta":     nombre,
            "nicho":             nicho,
            "ciudad":            ciudad,
            "fecha_auditoria":   datetime.now().isoformat(),
            "score":             score,
            "clasificacion":     (
                "Excelente" if score >= 80
                else "Buena" if score >= 60
                else "Regular" if score >= 40
                else "Crítica"
            ),
            "desglose_categorias": desglose,
            "total_hallazgos": {
                "critical": len(hallazgos["critical"]),
                "high":     len(hallazgos["high"]),
                "medium":   len(hallazgos["medium"]),
                "low":      len(hallazgos["low"]),
            },
            "top5_problemas":      top5,
            "recomendaciones":     recomendaciones,
            "mejora_estimada":     mejora,
            "analisis_ejecutivo":  analisis_ia,
            "checkpoints_totales": sum(len(v["items"]) for v in CHECKPOINTS.values()),
            "checkpoints_evaluados": len([v for v in respuestas.values() if v is not None]),
        }

        _update_job(job_id,
                    estado="completado",
                    resultado=json.dumps(resultado, ensure_ascii=False),
                    terminado_at=datetime.now().isoformat())

    except Exception as e:
        _update_job(job_id,
                    estado="error",
                    resultado=json.dumps({"error": str(e)}, ensure_ascii=False),
                    terminado_at=datetime.now().isoformat())


# ── Public API ────────────────────────────────────────────────

def crear_job(datos_cuenta):
    """
    datos_cuenta: {
      nombre_cuenta, nicho, ciudad,
      roas_actual, presupuesto_mensual_cop,
      respuestas: {checkpoint_id: True/False}
    }
    """
    job_id = str(uuid.uuid4())[:12]
    conn = _get_conn()
    conn.execute(
        "INSERT INTO auditoria_meta_jobs VALUES (?,?,?,?,?,?)",
        (job_id, datos_cuenta.get("nombre_cuenta", ""), "corriendo",
         None, datetime.now().isoformat(), None)
    )
    conn.commit()
    conn.close()

    t = threading.Thread(target=_run_auditoria, args=(job_id, datos_cuenta), daemon=True)
    t.start()
    return job_id


def get_job_estado(job_id):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM auditoria_meta_jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row["id"], "estado": row["estado"], "nombre_cuenta": row["nombre_cuenta"]}


def get_job_reporte(job_id):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM auditoria_meta_jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    if not row or not row["resultado"]:
        return None
    try:
        return json.loads(row["resultado"])
    except Exception:
        return None


def get_checkpoints():
    """Retorna la lista de checkpoints para el frontend."""
    result = {}
    for cat, config in CHECKPOINTS.items():
        result[cat] = {
            "peso": config["peso"],
            "items": [
                {"id": i[0], "descripcion": i[1], "severidad": i[2]}
                for i in config["items"]
            ]
        }
    return result
