# -*- coding: utf-8 -*-
import sys, os, json, re, uuid, threading, sqlite3, urllib.request, urllib.parse
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "jobs.db")

CLAUDE_API_KEY = os.environ.get("ANTHROPIC_API_KEY", os.environ.get("CLAUDE_API_KEY", ""))
CLAUDE_MODEL   = "claude-sonnet-4-5"

# ──────────────────────────────────────────────────────────────
# DB helpers
# ──────────────────────────────────────────────────────────────

def _get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ads_jobs (
            id TEXT PRIMARY KEY,
            investigacion_job_id TEXT,
            nombre_negocio TEXT,
            nicho TEXT,
            ciudad TEXT,
            tamanio TEXT,
            estado TEXT DEFAULT 'pendiente',
            progreso INTEGER DEFAULT 0,
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
    conn.execute(f"UPDATE ads_jobs SET {sets} WHERE id=?", vals)
    conn.commit()
    conn.close()


# ──────────────────────────────────────────────────────────────
# Claude helper
# ──────────────────────────────────────────────────────────────

def _claude(prompt, max_tokens=4000):
    if not CLAUDE_API_KEY:
        return ""
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
        with urllib.request.urlopen(req, timeout=90) as r:
            body = json.loads(r.read())
            return body["content"][0]["text"].strip()
    except Exception as e:
        return f"[claude_error: {e}]"


# ──────────────────────────────────────────────────────────────
# Funnel analysis
# ──────────────────────────────────────────────────────────────

def _analizar_funnel(nombre, nicho, ciudad, tamanio,
                     maletas, reviews_pos, reviews_neg,
                     competidores, fb_ads_data):
    """Diagnose funnel leaks and build repair plan."""

    rating = maletas.get("maleta_5_testimonios", {}).get("calificacion_promedio", 4.0)
    if isinstance(rating, str):
        try:
            rating = float(re.search(r"[\d.]+", rating).group())
        except Exception:
            rating = 4.0

    total_reviews = maletas.get("maleta_5_testimonios", {}).get("total_reviews", 0)
    objeciones = maletas.get("maleta_6_objeciones", {}).get("lista_objeciones", [])
    problemas = maletas.get("maleta_2_problema", {}).get("problemas_principales", [])
    diferenc = maletas.get("maleta_4_diferenciales", {}).get("diferenciales_propios", [])
    garantias = maletas.get("maleta_7_garantia", {}).get("garantias_identificadas", [])

    def _score(crit):
        return "alto" if crit else "medio"

    bajo_rating = rating < 4.2
    pocas_reviews = total_reviews < 50
    muchas_objeciones = len(objeciones) >= 3
    sin_diferencial = len(diferenc) < 2
    sin_garantia = len(garantias) == 0

    etapas = [
        {
            "etapa": "Impresiones",
            "benchmark_ctr": "2-4%",
            "problema_tipico": "Creativos genéricos sin gancho emocional",
            "causa_raiz": "No se usan los dolores reales del público en el copy",
            "solucion": "Usar los 3 problemas principales identificados en Maleta 2 como hooks",
            "prioridad": "ALTA" if sin_diferencial else "MEDIA",
        },
        {
            "etapa": "Clics",
            "benchmark_ctr": "1-3%",
            "problema_tipico": "CTA poco claro o poco urgente",
            "causa_raiz": "Oferta no diferenciada vs competencia",
            "solucion": f"Destacar '{diferenc[0] if diferenc else 'servicio premium'}' en headline",
            "prioridad": "ALTA" if sin_diferencial else "MEDIA",
        },
        {
            "etapa": "Visitas",
            "benchmark_ctr": "40-60% permanencia",
            "problema_tipico": "Landing page no responde la promesa del anuncio",
            "causa_raiz": "Mensaje inconsistente entre anuncio y página",
            "solucion": "Alinear headline de landing con copy del anuncio (message match)",
            "prioridad": "ALTA",
        },
        {
            "etapa": "Contacto",
            "benchmark_ctr": "5-15%",
            "problema_tipico": "Formulario largo o sin trust signals",
            "causa_raiz": "Poco social proof visible en el momento de decisión",
            "solucion": f"Mostrar '{total_reviews} reseñas · {rating}★' justo sobre el formulario",
            "prioridad": "ALTA" if pocas_reviews or bajo_rating else "MEDIA",
        },
        {
            "etapa": "Consulta",
            "benchmark_ctr": "30-50%",
            "problema_tipico": "Equipo de ventas sin manejo de objeciones",
            "causa_raiz": "Objeciones no anticipadas en el proceso de cierre",
            "solucion": f"Script de objeciones para: {', '.join(str(o) for o in objeciones[:3])}",
            "prioridad": "ALTA" if muchas_objeciones else "MEDIA",
        },
        {
            "etapa": "Cierre",
            "benchmark_ctr": "20-40%",
            "problema_tipico": "Sin garantía clara que reduzca el riesgo percibido",
            "causa_raiz": "Cliente percibe riesgo alto sin red de seguridad",
            "solucion": f"Implementar: {garantias[0] if garantias else 'garantía de satisfacción 30 días'}",
            "prioridad": "ALTA" if sin_garantia else "MEDIA",
        },
    ]

    fugas_criticas = [e for e in etapas if e["prioridad"] == "ALTA"]
    score_funnel = max(0, 10 - len(fugas_criticas) * 1.5)

    return {
        "etapas": etapas,
        "fugas_criticas": fugas_criticas,
        "score_funnel": round(score_funnel, 1),
        "rating": rating,
        "total_reviews": total_reviews,
        "num_objeciones": len(objeciones),
        "resumen": (
            f"Funnel score {score_funnel}/10 — "
            f"{len(fugas_criticas)} fugas críticas detectadas. "
            f"Rating {rating}★ con {total_reviews} reseñas."
        ),
    }


# ──────────────────────────────────────────────────────────────
# Budget tiers by company size
# ──────────────────────────────────────────────────────────────

BUDGET_TIERS = {
    "pequeña": {
        "mensual_total_cop": 1_500_000,
        "campanas": 2,
        "roas_objetivo": 3.0,
        "descripcion": "PyME local — foco en generación de leads y reconocimiento barrio/ciudad",
    },
    "mediana": {
        "mensual_total_cop": 5_000_000,
        "campanas": 3,
        "roas_objetivo": 4.5,
        "descripcion": "Empresa en crecimiento — foco en escalar leads calificados y retargeting",
    },
    "grande": {
        "mensual_total_cop": 15_000_000,
        "campanas": 4,
        "roas_objetivo": 6.0,
        "descripcion": "Marca establecida — foco en dominancia de mercado y máxima escala",
    },
}


# ──────────────────────────────────────────────────────────────
# Copy variations engine
# ──────────────────────────────────────────────────────────────

def _generar_copies(nombre, nicho, ciudad, problema, diferencial,
                    hook_review, objetivo_campana, formato):
    """Return 3 copy variations without Claude (fast path), or Claude-enhanced."""

    problema_str = str(problema) if problema else f"problemas con {nicho}"
    dif_str = str(diferencial) if diferencial else f"servicio experto en {nicho}"

    copies_base = [
        {
            "variacion": "A — Dolor directo",
            "hook": f"¿Cansado de {problema_str}?",
            "cuerpo": (
                f"En {nombre} lo resolvemos diferente. {dif_str}. "
                f"Más de {hook_review} clientes satisfechos en {ciudad}. "
                f"👉 Agenda tu consulta GRATIS hoy."
            ),
            "cta": "QUIERO SABER MÁS",
            "principio_psicologico": "Pain-Agitate-Solve (Sugarman)",
        },
        {
            "variacion": "B — Prueba social",
            "hook": hook_review if hook_review else f"Así resolvimos {problema_str}",
            "cuerpo": (
                f"'{hook_review}' — cliente real de {nombre}. "
                f"Ofrecemos {dif_str} en {ciudad}. Sin compromisos. "
                f"Respuesta en menos de 2 horas."
            ),
            "cta": "VER CASOS DE ÉXITO",
            "principio_psicologico": "Social Proof (Cialdini)",
        },
        {
            "variacion": "C — Escasez/Urgencia",
            "hook": f"Solo 5 cupos disponibles este mes en {ciudad}",
            "cuerpo": (
                f"{nombre} — especialistas en {nicho}. {dif_str}. "
                f"Agenda antes del viernes y recibe una auditoría gratuita de tu situación actual."
            ),
            "cta": "RESERVAR MI CUPO",
            "principio_psicologico": "Scarcity + Loss Aversion (Kahneman)",
        },
    ]

    return copies_base


# ──────────────────────────────────────────────────────────────
# Campaign builder
# ──────────────────────────────────────────────────────────────

def _construir_campanas(nombre, nicho, ciudad, tamanio, maletas,
                        funnel_data, reviews_pos, reviews_neg):

    tier = BUDGET_TIERS.get(tamanio, BUDGET_TIERS["mediana"])
    presupuesto_total = tier["mensual_total_cop"]
    num_campanas = tier["campanas"]
    roas = tier["roas_objetivo"]

    publico_obj = maletas.get("maleta_1_publico", {})
    problemas   = maletas.get("maleta_2_problema", {}).get("problemas_principales", [])
    diferenc    = maletas.get("maleta_4_diferenciales", {}).get("diferenciales_propios", [])
    objeciones  = maletas.get("maleta_6_objeciones", {}).get("lista_objeciones", [])
    testimonios = maletas.get("maleta_5_testimonios", {}).get("mejores_testimonios", [])

    edad_rango = publico_obj.get("rango_edad", "25-54")
    genero     = publico_obj.get("genero_predominante", "Todos")
    intereses  = publico_obj.get("intereses_principales", [nicho, "emprendimiento"])
    ingresos   = publico_obj.get("nivel_ingresos", "medio")

    hook_review = ""
    if testimonios:
        t = testimonios[0]
        hook_review = str(t.get("texto", ""))[:120] if isinstance(t, dict) else str(t)[:120]
    elif reviews_pos:
        hook_review = str(reviews_pos[0])[:120]

    problema_principal = str(problemas[0]) if problemas else f"encontrar {nicho} confiable"
    diferencial_key    = str(diferenc[0])  if diferenc  else f"servicio personalizado de {nicho}"

    # Budget splits
    splits = {
        2: [0.60, 0.40],
        3: [0.50, 0.30, 0.20],
        4: [0.40, 0.30, 0.20, 0.10],
    }
    pcts = splits.get(num_campanas, splits[3])

    campanas_config = [
        {
            "nombre": f"C1 — Tráfico Frío | {nicho} | {ciudad}",
            "objetivo_meta": "LEADS",
            "etapa_funnel": "Impresiones → Clics → Visitas",
            "formato": "Video 9:16 (Reels) + Imagen carrusel",
            "duracion_video": "15-30 segundos",
            "publico": {
                "ubicacion": ciudad,
                "edad": edad_rango,
                "genero": genero,
                "intereses": intereses[:5],
                "comportamientos": ["pequeñas_empresas", "compradores_en_linea"],
                "ingresos_estimados": ingresos,
            },
            "copies": _generar_copies(
                nombre, nicho, ciudad,
                problema_principal, diferencial_key,
                hook_review, "LEADS", "Video"
            ),
            "presupuesto_cop": int(presupuesto_total * pcts[0]),
            "roas_objetivo": roas * 0.8,
            "kpis": {"cpm_max": 8000, "ctr_min": "2%", "cpl_max": 25000},
            "notas": "Audiencia fría. Priorizar hook emocional en primeros 3s.",
        },
        {
            "nombre": f"C2 — Retargeting | Visitantes web | {ciudad}",
            "objetivo_meta": "CONVERSIONES",
            "etapa_funnel": "Visitas → Contacto → Consulta",
            "formato": "Imagen estática + Story con CTA swipe-up",
            "duracion_video": "N/A",
            "publico": {
                "ubicacion": ciudad,
                "edad": edad_rango,
                "genero": genero,
                "audiencia_personalizada": "Visitantes web últimos 30 días",
                "excluir": "Compradores recientes",
            },
            "copies": _generar_copies(
                nombre, nicho, ciudad,
                objeciones[0] if objeciones else problema_principal,
                diferencial_key,
                hook_review, "CONVERSIONES", "Story"
            ),
            "presupuesto_cop": int(presupuesto_total * pcts[1]),
            "roas_objetivo": roas * 1.2,
            "kpis": {"ctr_min": "3%", "cpl_max": 15000, "frecuencia_max": 7},
            "notas": "Manejo de objeciones en copy. Mostrar garantía prominente.",
        },
        {
            "nombre": f"C3 — Lookalike | Clientes actuales | {ciudad}",
            "objetivo_meta": "REACH + LEADS",
            "etapa_funnel": "Impresiones → Clics",
            "formato": "Video corto 15s + carrusel testimonios",
            "duracion_video": "15 segundos",
            "publico": {
                "ubicacion": ciudad,
                "edad": edad_rango,
                "genero": genero,
                "lookalike": "1-3% similares a base de clientes",
            },
            "copies": _generar_copies(
                nombre, nicho, ciudad,
                problema_principal, diferencial_key,
                hook_review, "REACH", "Carrusel"
            ),
            "presupuesto_cop": int(presupuesto_total * pcts[2]) if num_campanas > 2 else 0,
            "roas_objetivo": roas,
            "kpis": {"cpm_max": 6000, "ctr_min": "2.5%", "cpl_max": 20000},
            "notas": "Usar testimonios reales como prueba social. A/B test de hooks.",
        },
        {
            "nombre": f"C4 — Awareness | Marca | {ciudad} regional",
            "objetivo_meta": "BRAND_AWARENESS",
            "etapa_funnel": "Impresiones → Reconocimiento",
            "formato": "Video 16:9 (Feed) + Reels",
            "duracion_video": "30-60 segundos",
            "publico": {
                "ubicacion": f"{ciudad} + área metropolitana",
                "edad": edad_rango,
                "genero": "Todos",
                "intereses": intereses,
            },
            "copies": _generar_copies(
                nombre, nicho, ciudad,
                problema_principal, diferencial_key,
                hook_review, "AWARENESS", "Video largo"
            ),
            "presupuesto_cop": int(presupuesto_total * pcts[3]) if num_campanas > 3 else 0,
            "roas_objetivo": roas * 0.5,
            "kpis": {"frecuencia_objetivo": "3-5x/semana", "recall_lift": ">5%"},
            "notas": "Solo para empresas grandes. Foco en brand recall, no conversión directa.",
        },
    ]

    campanas_activas = campanas_config[:num_campanas]

    # ── Validación de benchmarks de industria ─────────────────
    estrategia_str = json.dumps(campanas_activas, ensure_ascii=False)
    alertas_benchmark = []

    for camp in campanas_activas:
        etapa = camp.get("etapa_funnel", "")
        es_retargeting = "Retargeting" in camp.get("nombre", "") or "CONVERSIONES" in camp.get("objetivo_meta", "")
        es_tiktok = "TikTok" in camp.get("formato", "")

        ctr_min_esperado = 3.0 if es_retargeting else 1.5
        roas_min = 3.0 if es_retargeting else 1.5
        roas_camp = camp.get("roas_objetivo", 0)

        if roas_camp < roas_min:
            alertas_benchmark.append(
                f"{camp['nombre']}: ROAS objetivo {roas_camp:.1f}x "
                f"está por debajo del benchmark ({roas_min}x)"
            )

        if es_tiktok:
            copies = camp.get("copies", {})
            hook = str(copies.get("hook_principal", ""))
            if len(hook) < 10:
                alertas_benchmark.append(
                    f"{camp['nombre']}: TikTok sin hook explícito en primeros 3s"
                )

    benchmarks_industria = {
        "meta_ads": {
            "CTR_prospecting_min":     "1.5%",
            "CTR_retargeting_min":     "3.0%",
            "frequency_prospecting_max": 2.5,
            "frequency_retargeting_max": 5.0,
            "thumb_stop_rate_objetivo": "25%+",
            "ROAS_retargeting_objetivo": "3:1",
            "ROAS_prospecting_objetivo": "1.5:1",
            "CPM_referencia_Colombia":  "3-8 USD",
            "horizonte_validacion":     "14 días para copies, 30 días para pujas",
        },
        "tiktok_ads": {
            "hook_obligatorio":  "Primeros 3 segundos — si no para el scroll, el video no existe",
            "watch_rate_min":    "30%+",
            "CTR_objetivo":      "2%+",
            "formatos_top":      ["Spark Ads", "TopView", "In-Feed Video 9:16"],
            "regla_3_segundos":  "Hook debe preguntar que duela, afirmar que sorprenda, o mostrar resultado antes del proceso",
        },
        "alertas_detectadas": alertas_benchmark,
        "nota": (
            "Benchmarks basados en promedios de industria Colombia 2024. "
            "Ajustar según histórico real de la cuenta en 30 días."
        ),
    }

    return {
        "campanas": campanas_activas,
        "presupuesto_total_cop": presupuesto_total,
        "roas_objetivo_global": roas,
        "descripcion_tier": tier["descripcion"],
        "horizonte_prueba": "14 días para validar copies, 30 días para optimizar pujas",
        "regla_70_20_10": {
            "70": "Presupuesto en lo que ya probó funcionar",
            "20": "Prueba de nuevos formatos/audiencias",
            "10": "Experimentos creativos arriesgados",
        },
        "benchmarks_industria": benchmarks_industria,
    }


# ──────────────────────────────────────────────────────────────
# HTML report generator
# ──────────────────────────────────────────────────────────────

def _esc(s):
    if not isinstance(s, str):
        s = str(s)
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;"))


def _generar_html(resultado):
    nombre   = _esc(resultado.get("nombre_negocio", ""))
    nicho    = _esc(resultado.get("nicho", ""))
    ciudad   = _esc(resultado.get("ciudad", ""))
    tamanio  = _esc(resultado.get("tamanio", ""))
    fecha    = _esc(resultado.get("generado_at", ""))
    funnel   = resultado.get("funnel", {})
    campanas = resultado.get("campanas", {})
    claude_insights = resultado.get("claude_insights", "")

    score = funnel.get("score_funnel", 0)
    score_color = "#34c759" if score >= 7 else ("#ff9500" if score >= 5 else "#ff3b30")

    # Funnel stages
    etapas_html = ""
    for e in funnel.get("etapas", []):
        prio = e.get("prioridad", "MEDIA")
        prio_color = "#ff3b30" if prio == "ALTA" else "#ff9500"
        etapas_html += f"""
        <div class="etapa-card">
          <div class="etapa-header">
            <span class="etapa-nombre">{_esc(e['etapa'])}</span>
            <span class="etapa-bench">{_esc(e.get('benchmark_ctr',''))}</span>
            <span class="etapa-prio" style="color:{prio_color}">{prio}</span>
          </div>
          <div class="etapa-problema"><strong>Problema:</strong> {_esc(e.get('problema_tipico',''))}</div>
          <div class="etapa-causa"><strong>Causa raíz:</strong> {_esc(e.get('causa_raiz',''))}</div>
          <div class="etapa-sol"><strong>Solución:</strong> {_esc(e.get('solucion',''))}</div>
        </div>"""

    # Campaigns
    campanas_html = ""
    for c in campanas.get("campanas", []):
        copies_html = ""
        for cv in c.get("copies", []):
            copies_html += f"""
            <div class="copy-var">
              <div class="copy-label">{_esc(cv.get('variacion',''))}</div>
              <div class="copy-hook">🎣 {_esc(cv.get('hook',''))}</div>
              <div class="copy-body">{_esc(cv.get('cuerpo',''))}</div>
              <div class="copy-cta">CTA: <strong>{_esc(cv.get('cta',''))}</strong></div>
              <div class="copy-psic">🧠 {_esc(cv.get('principio_psicologico',''))}</div>
            </div>"""

        pub = c.get("publico", {})
        intereses_str = ", ".join(str(i) for i in pub.get("intereses", []))
        budget_fmt = f"${c.get('presupuesto_cop', 0):,.0f} COP/mes"

        campanas_html += f"""
        <div class="campana-card">
          <div class="campana-titulo">{_esc(c.get('nombre',''))}</div>
          <div class="campana-meta">
            <span class="tag">🎯 {_esc(c.get('objetivo_meta',''))}</span>
            <span class="tag">📊 {_esc(c.get('etapa_funnel',''))}</span>
            <span class="tag">🎬 {_esc(c.get('formato',''))}</span>
            <span class="tag budget">{_esc(budget_fmt)}</span>
            <span class="tag roas">ROAS {c.get('roas_objetivo',0):.1f}x</span>
          </div>
          <div class="publico-box">
            <strong>Público:</strong> {_esc(pub.get('edad',''))} · {_esc(pub.get('genero',''))} · {_esc(pub.get('ubicacion',''))}
            {f'<br><strong>Intereses:</strong> {_esc(intereses_str)}' if intereses_str else ''}
          </div>
          <div class="copies-section">
            <div class="copies-title">3 Variaciones de Copy</div>
            {copies_html}
          </div>
          <div class="campana-nota">📝 {_esc(c.get('notas',''))}</div>
        </div>"""

    # Claude insights section
    insights_html = ""
    if claude_insights and not claude_insights.startswith("[claude_error"):
        insights_html = f"""
        <section class="section">
          <h2>Insights Estratégicos (IA)</h2>
          <div class="claude-box">{_esc(claude_insights)}</div>
        </section>"""

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Estrategia ADS — {nombre}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;
        background:#f5f5f7;color:#1d1d1f;line-height:1.6}}
  .hero{{background:#1d1d1f;color:#fff;padding:60px 40px;text-align:center}}
  .hero h1{{font-size:2.4rem;font-weight:700;margin-bottom:8px}}
  .hero .sub{{color:#86868b;font-size:1.1rem}}
  .badge{{display:inline-block;padding:6px 18px;border-radius:20px;
          font-size:.85rem;font-weight:600;margin:4px}}
  .badge-nicho{{background:#0071e3;color:#fff}}
  .badge-ciudad{{background:#5e5ce6;color:#fff}}
  .badge-size{{background:#30d158;color:#fff}}
  .score-big{{font-size:4rem;font-weight:800;color:{score_color};margin:20px 0 4px}}
  .score-label{{color:#86868b;font-size:.9rem}}
  .container{{max-width:1100px;margin:0 auto;padding:40px 20px}}
  .section{{background:#fff;border-radius:18px;padding:32px;margin-bottom:24px;
            box-shadow:0 2px 12px rgba(0,0,0,.06)}}
  .section h2{{font-size:1.4rem;font-weight:700;margin-bottom:20px;color:#1d1d1f}}
  .section h2::before{{content:'';display:inline-block;width:4px;height:1.2em;
                       background:#0071e3;margin-right:10px;border-radius:2px;vertical-align:middle}}
  .funnel-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}}
  .etapa-card{{background:#f5f5f7;border-radius:12px;padding:18px;
               border-left:4px solid #0071e3}}
  .etapa-header{{display:flex;justify-content:space-between;align-items:center;
                 margin-bottom:10px;flex-wrap:wrap;gap:8px}}
  .etapa-nombre{{font-weight:700;font-size:1.05rem}}
  .etapa-bench{{color:#86868b;font-size:.85rem}}
  .etapa-prio{{font-weight:700;font-size:.85rem}}
  .etapa-problema,.etapa-causa,.etapa-sol{{font-size:.9rem;margin-top:6px;color:#3a3a3c}}
  .campana-card{{background:#f5f5f7;border-radius:16px;padding:24px;margin-bottom:20px;
                 border:1px solid #e5e5ea}}
  .campana-titulo{{font-size:1.15rem;font-weight:700;margin-bottom:12px;color:#1d1d1f}}
  .campana-meta{{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px}}
  .tag{{background:#e5e5ea;border-radius:20px;padding:4px 12px;font-size:.8rem;
        font-weight:600;color:#3a3a3c}}
  .tag.budget{{background:#0071e3;color:#fff}}
  .tag.roas{{background:#30d158;color:#fff}}
  .publico-box{{background:#fff;border-radius:10px;padding:14px;
                font-size:.9rem;margin-bottom:16px;border:1px solid #e5e5ea}}
  .copies-section{{margin-top:12px}}
  .copies-title{{font-weight:700;font-size:.9rem;color:#86868b;
                 text-transform:uppercase;letter-spacing:.05em;margin-bottom:12px}}
  .copy-var{{background:#fff;border-radius:10px;padding:16px;margin-bottom:10px;
             border-left:3px solid #0071e3}}
  .copy-label{{font-weight:700;font-size:.85rem;color:#0071e3;margin-bottom:8px}}
  .copy-hook{{font-size:1rem;font-weight:600;margin-bottom:6px}}
  .copy-body{{font-size:.9rem;color:#3a3a3c;margin-bottom:6px}}
  .copy-cta{{font-size:.85rem;margin-bottom:4px}}
  .copy-psic{{font-size:.8rem;color:#86868b}}
  .campana-nota{{margin-top:12px;font-size:.85rem;color:#636366;
                 background:#fffbf0;border-radius:8px;padding:10px 14px}}
  .budget-summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
                   gap:16px;margin-top:20px}}
  .budget-card{{background:#f5f5f7;border-radius:12px;padding:20px;text-align:center}}
  .budget-num{{font-size:1.6rem;font-weight:800;color:#0071e3}}
  .budget-lbl{{font-size:.85rem;color:#86868b;margin-top:4px}}
  .regla-box{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:16px}}
  .regla-item{{background:#f5f5f7;border-radius:10px;padding:16px;text-align:center}}
  .regla-pct{{font-size:2rem;font-weight:800;color:#0071e3}}
  .regla-desc{{font-size:.85rem;color:#3a3a3c;margin-top:6px}}
  .claude-box{{background:#f0f4ff;border-radius:12px;padding:20px;
               font-size:.95rem;white-space:pre-wrap;border-left:4px solid #5e5ce6}}
  .footer{{text-align:center;color:#86868b;font-size:.85rem;padding:40px 20px}}
</style>
</head>
<body>

<div class="hero">
  <h1>Estrategia ADS — {nombre}</h1>
  <div class="sub">{nicho} · {ciudad} · generado {fecha}</div>
  <div style="margin-top:16px">
    <span class="badge badge-nicho">{nicho}</span>
    <span class="badge badge-ciudad">{ciudad}</span>
    <span class="badge badge-size">{tamanio}</span>
  </div>
  <div class="score-big">{score}/10</div>
  <div class="score-label">Score de Funnel — {funnel.get('resumen','')}</div>
</div>

<div class="container">

  <section class="section">
    <h2>Diagnóstico de Funnel</h2>
    <div class="funnel-grid">
      {etapas_html}
    </div>
  </section>

  <section class="section">
    <h2>Campañas Recomendadas</h2>
    <div class="budget-summary">
      <div class="budget-card">
        <div class="budget-num">${campanas.get('presupuesto_total_cop',0):,.0f}</div>
        <div class="budget-lbl">Presupuesto mensual COP</div>
      </div>
      <div class="budget-card">
        <div class="budget-num">{campanas.get('roas_objetivo_global',0):.1f}x</div>
        <div class="budget-lbl">ROAS objetivo global</div>
      </div>
      <div class="budget-card">
        <div class="budget-num">{len(campanas.get('campanas',[]))}</div>
        <div class="budget-lbl">Campañas activas</div>
      </div>
      <div class="budget-card">
        <div class="budget-num">30d</div>
        <div class="budget-lbl">Horizonte de optimización</div>
      </div>
    </div>
    <div class="regla-box">
      <div class="regla-item">
        <div class="regla-pct">70%</div>
        <div class="regla-desc">{_esc(campanas.get('regla_70_20_10',{}).get('70',''))}</div>
      </div>
      <div class="regla-item">
        <div class="regla-pct">20%</div>
        <div class="regla-desc">{_esc(campanas.get('regla_70_20_10',{}).get('20',''))}</div>
      </div>
      <div class="regla-item">
        <div class="regla-pct">10%</div>
        <div class="regla-desc">{_esc(campanas.get('regla_70_20_10',{}).get('10',''))}</div>
      </div>
    </div>
    <div style="margin-top:24px">
      {campanas_html}
    </div>
  </section>

  {insights_html}

</div>

<div class="footer">
  Generado por IM System · Intelligent Markets · {fecha}
</div>

</body>
</html>"""
    return html


# ──────────────────────────────────────────────────────────────
# Main pipeline
# ──────────────────────────────────────────────────────────────

def _run_pipeline(job_id, investigacion_job_id, nombre, nicho, ciudad, tamanio):
    try:
        _update_job(job_id, estado="procesando", progreso=5)

        # Load investigation data
        maletas = {}
        reviews_pos = []
        reviews_neg = []
        competidores = []
        fb_ads_data = {}

        if investigacion_job_id:
            try:
                from agent.deep_researcher import get_job_reporte as get_inv_reporte
            except ImportError:
                from deep_researcher import get_job_reporte as get_inv_reporte

            inv = get_inv_reporte(investigacion_job_id)
            if inv and inv.get("resultado"):
                res = inv["resultado"]
                maletas      = res.get("7_maletas", {})
                reviews_pos  = res.get("reviews_positivas", [])
                reviews_neg  = res.get("reviews_negativas", [])
                competidores = res.get("competidores", [])
                fb_ads_data  = res.get("facebook_ads", {})

        _update_job(job_id, progreso=25)

        # Funnel diagnosis
        funnel = _analizar_funnel(
            nombre, nicho, ciudad, tamanio,
            maletas, reviews_pos, reviews_neg,
            competidores, fb_ads_data,
        )
        _update_job(job_id, progreso=50)

        # Campaign builder
        campanas = _construir_campanas(
            nombre, nicho, ciudad, tamanio,
            maletas, funnel, reviews_pos, reviews_neg,
        )
        _update_job(job_id, progreso=75)

        # Claude strategic layer (optional enhancement)
        claude_insights = ""
        if CLAUDE_API_KEY:
            fugas = "\n".join(
                f"- {f['etapa']}: {f['solucion']}"
                for f in funnel.get("fugas_criticas", [])
            )
            claude_prompt = (
                f"Eres un experto en Meta Ads y marketing digital colombiano.\n"
                f"Negocio: {nombre} ({nicho} en {ciudad}, tamaño {tamanio}).\n"
                f"Fugas críticas del funnel:\n{fugas}\n\n"
                f"En máximo 300 palabras, dame 3 recomendaciones estratégicas priorizadas "
                f"con acciones concretas para los próximos 30 días. Sé directo y accionable."
            )
            claude_insights = _claude(claude_prompt, max_tokens=600)

        _update_job(job_id, progreso=90)

        resultado = {
            "nombre_negocio": nombre,
            "nicho": nicho,
            "ciudad": ciudad,
            "tamanio": tamanio,
            "investigacion_job_id": investigacion_job_id,
            "funnel": funnel,
            "campanas": campanas,
            "claude_insights": claude_insights,
            "generado_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

        # Save HTML report
        reports_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
        os.makedirs(reports_dir, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", nombre.lower())[:30]
        date_str = datetime.now().strftime("%Y%m%d")
        html_filename = f"ads-strategy-{slug}-{date_str}.html"
        html_path = os.path.join(reports_dir, html_filename)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(_generar_html(resultado))

        resultado["html_filename"] = html_filename
        resultado["html_path"] = html_path

        _update_job(
            job_id,
            estado="completado",
            progreso=100,
            resultado=json.dumps(resultado, ensure_ascii=False),
            terminado_at=datetime.now().isoformat(),
        )

    except Exception as e:
        _update_job(
            job_id,
            estado="error",
            resultado=json.dumps({"error": str(e)}, ensure_ascii=False),
            terminado_at=datetime.now().isoformat(),
        )


# ──────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────

def crear_job(nombre, nicho, ciudad, tamanio="mediana",
              investigacion_job_id=""):
    job_id = str(uuid.uuid4())
    conn = _get_conn()
    conn.execute(
        """INSERT INTO ads_jobs
           (id, investigacion_job_id, nombre_negocio, nicho, ciudad, tamanio,
            estado, progreso, creado_at)
           VALUES (?,?,?,?,?,?,'pendiente',0,?)""",
        (job_id, investigacion_job_id, nombre, nicho, ciudad, tamanio,
         datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()

    t = threading.Thread(
        target=_run_pipeline,
        args=(job_id, investigacion_job_id, nombre, nicho, ciudad, tamanio),
        daemon=True,
    )
    t.start()
    return job_id


def get_job_estado(job_id):
    conn = _get_conn()
    row = conn.execute(
        "SELECT id,nombre_negocio,estado,progreso,creado_at,terminado_at FROM ads_jobs WHERE id=?",
        (job_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)


def get_job_reporte(job_id):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM ads_jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    if d.get("resultado"):
        try:
            d["resultado"] = json.loads(d["resultado"])
        except Exception:
            pass
    return d


def lista_jobs(limit=20):
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id,nombre_negocio,nicho,ciudad,tamanio,estado,progreso,creado_at "
        "FROM ads_jobs ORDER BY creado_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _investigar_algoritmo_meta_ads(nicho='general', presupuesto_cop=0):
    import requests, time
    import datetime

    try:
        from bs4 import BeautifulSoup
        import anthropic
    except ImportError:
        return {'informe': 'Faltan dependencias: beautifulsoup4, anthropic', 'datos_cuenta': {}}

    anio_actual = datetime.datetime.now().year
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    datos_crudos = {}
    queries = {
        'meta_oficial': [
            f'meta ads delivery system algorithm how it works {anio_actual}',
            f'facebook ads auction algorithm {anio_actual} official',
        ],
        'conversiones_ventas': [
            f'meta ads lowest cost conversions algorithm {anio_actual}',
            f'meta ads cost per result reduce {anio_actual} strategy',
        ],
        'alcance_bajo_costo': [
            f'facebook ads reduce cpm cost {anio_actual} strategy',
            f'meta advantage+ audience algorithm {anio_actual}',
        ],
        'blogs_especializados': [
            f'wordstream meta ads algorithm {anio_actual} guide',
            f'hubspot facebook ads algorithm {anio_actual}',
        ],
        'errores_que_danan': [
            f'facebook ads what kills performance {anio_actual}',
            f'meta ads learning phase disruption {anio_actual}',
        ]
    }

    for categoria, qs in queries.items():
        datos_crudos[categoria] = []
        for q in qs[:2]:
            try:
                url = 'https://www.google.com/search?q=' + requests.utils.quote(q) + '&hl=es&num=5'
                r = requests.get(url, headers=headers, timeout=10)
                soup = BeautifulSoup(r.text, 'html.parser')
                snippets = [d.get_text(strip=True) for d in
                           soup.find_all(['div', 'span'], class_=['BNeawe', 'VwiC3b'])]
                datos_crudos[categoria].extend([s[:200] for s in snippets[:3] if len(s) > 40])
                time.sleep(2)
            except Exception:
                pass

    token = os.environ.get('META_ACCESS_TOKEN', '')
    account = os.environ.get('META_AD_ACCOUNT_ID', '')
    datos_cuenta_real = {}

    if token and account:
        try:
            r = requests.get(
                'https://graph.facebook.com/v19.0/' + account + '/insights',
                params={
                    'access_token': token,
                    'fields': 'impressions,reach,frequency,spend,ctr,cpm',
                    'date_preset': 'last_30d',
                    'level': 'account'
                }, timeout=10
            )
            insights = r.json().get('data', [{}])
            if insights:
                ins = insights[0]
                datos_cuenta_real = {
                    'cpm_actual': float(ins.get('cpm', 0)),
                    'ctr_actual': float(ins.get('ctr', 0)),
                    'gasto_30d': float(ins.get('spend', 0)),
                    'alcance_30d': int(ins.get('reach', 0)),
                    'frecuencia': float(ins.get('frequency', 0)),
                }
            rc = requests.get(
                'https://graph.facebook.com/v19.0/' + account + '/campaigns',
                params={
                    'access_token': token,
                    'fields': 'name,status,objective,daily_budget',
                    'effective_status': ['ACTIVE'],
                    'limit': 10
                }, timeout=10
            )
            campanas = rc.json().get('data', [])
            datos_cuenta_real['campanas_activas'] = len(campanas)
        except Exception as e:
            datos_cuenta_real['error'] = str(e)

    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    informe = ''

    if api_key:
        client = anthropic.Anthropic(api_key=api_key)

        lineas_meta = '\n'.join(datos_crudos.get('meta_oficial', [])[:3])
        lineas_conv = '\n'.join(datos_crudos.get('conversiones_ventas', [])[:3])
        lineas_alcance = '\n'.join(datos_crudos.get('alcance_bajo_costo', [])[:3])
        lineas_blogs = '\n'.join(datos_crudos.get('blogs_especializados', [])[:3])
        lineas_errores = '\n'.join(datos_crudos.get('errores_que_danan', [])[:3])

        prompt = (
            "Eres el estratega de Meta Ads de Intelligent Markets.\n"
            "Datos de fuentes oficiales Meta, blogs especializados y cuenta real:\n\n"
            "FUENTES OFICIALES META:\n" + lineas_meta + "\n\n"
            "CONVERSIONES Y VENTAS:\n" + lineas_conv + "\n\n"
            "ALCANCE Y BAJO COSTO:\n" + lineas_alcance + "\n\n"
            "BLOGS (WordStream, HubSpot, AdEspresso):\n" + lineas_blogs + "\n\n"
            "ERRORES QUE DANAN:\n" + lineas_errores + "\n\n"
            "DATOS REALES CUENTA IM:\n"
            "CPM actual: $" + str(datos_cuenta_real.get('cpm_actual', 'N/A')) + " USD\n"
            "CTR actual: " + str(datos_cuenta_real.get('ctr_actual', 'N/A')) + "%\n"
            "Alcance 30 dias: " + str(datos_cuenta_real.get('alcance_30d', 'N/A')) + "\n"
            "Frecuencia: " + str(datos_cuenta_real.get('frecuencia', 'N/A')) + "\n"
            "Campanas activas: " + str(datos_cuenta_real.get('campanas_activas', 0)) + "\n\n"
            "NICHO: " + nicho + " | PRESUPUESTO: $" + str(presupuesto_cop) + " COP/mes | ANNO: " + str(anio_actual) + "\n\n"
            "Genera informe COMPLETO y ACCIONABLE:\n\n"
            "=" * 50 + "\n"
            "INFORME: ALGORITMO META ADS - MAXIMO RENDIMIENTO " + str(anio_actual) + "\n"
            "Nicho: " + nicho + " | Presupuesto: $" + str(presupuesto_cop) + " COP\n"
            "Intelligent Markets - Confidencial\n"
            "=" * 50 + "\n\n"
            "1. COMO FUNCIONA EL ALGORITMO DE SUBASTA DE META " + str(anio_actual) + "\n"
            "2. COMO LOGRAR MAS ALCANCE CON MENOS DINERO\n"
            "3. COMO MAXIMIZAR CONVERSIONES Y VENTAS REALES\n"
            "4. ESTRUCTURA DE CAMPANA OPTIMA " + str(anio_actual) + "\n"
            "5. CREATIVOS QUE EL ALGORITMO PREMIA\n"
            "6. COSTOS EXTREMADAMENTE BAJOS - ESTRATEGIAS AVANZADAS\n"
            "   (CPM promedio Colombia " + str(anio_actual) + " por nicho, costo por lead optimo para " + nicho + ")\n"
            "7. QUE DANA O DESTRUYE EL RENDIMIENTO - EVITAR\n"
            "8. ESTRATEGIA ESPECIFICA PARA NICHO: " + nicho + "\n"
            "9. DIAGNOSTICO DE LA CUENTA ACTUAL\n"
            "10. PLAN DE ACCION INMEDIATA - semana 1, mes 2-3\n\n"
            "Sin JSON. Texto formateado. Numeros especificos."
        )

        try:
            msg = client.messages.create(
                model='claude-sonnet-4-5',
                max_tokens=8000,
                messages=[{'role': 'user', 'content': prompt}]
            )
            informe = msg.content[0].text
        except Exception as e:
            informe = 'Error: ' + str(e)

    return {
        'informe': informe,
        'datos_cuenta': datos_cuenta_real,
        'fuentes_consultadas': list(queries.keys())
    }


# ──────────────────────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="IM ADS Strategist")
    parser.add_argument("--nombre",  required=True)
    parser.add_argument("--nicho",   required=True)
    parser.add_argument("--ciudad",  default="Medellín")
    parser.add_argument("--tamanio", default="mediana",
                        choices=["pequeña", "mediana", "grande"])
    parser.add_argument("--inv-job", default="", help="ID del job de investigación")
    args = parser.parse_args()

    print(f"Iniciando estrategia ADS para: {args.nombre}")
    job_id = crear_job(
        nombre=args.nombre,
        nicho=args.nicho,
        ciudad=args.ciudad,
        tamanio=args.tamanio,
        investigacion_job_id=args.inv_job,
    )
    print(f"Job ID: {job_id}")

    import time
    while True:
        estado = get_job_estado(job_id)
        print(f"  [{estado['progreso']}%] {estado['estado']}")
        if estado["estado"] in ("completado", "error"):
            break
        time.sleep(2)

    reporte = get_job_reporte(job_id)
    if reporte and reporte.get("resultado"):
        res = reporte["resultado"]
        if isinstance(res, dict):
            print(f"\n✅ Estrategia generada")
            print(f"   Funnel score: {res.get('funnel',{}).get('score_funnel','?')}/10")
            campanas = res.get("campanas", {}).get("campanas", [])
            print(f"   Campañas: {len(campanas)}")
            presupuesto = res.get("campanas", {}).get("presupuesto_total_cop", 0)
            print(f"   Presupuesto: ${presupuesto:,.0f} COP/mes")
            if res.get("html_filename"):
                print(f"   Reporte: reports/{res['html_filename']}")
        else:
            print(f"\n❌ Error: {res}")
