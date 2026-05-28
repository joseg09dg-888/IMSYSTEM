# -*- coding: utf-8 -*-
import sys, os, json, re, uuid, threading, sqlite3, urllib.request
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "jobs.db")

CLAUDE_API_KEY = os.environ.get("ANTHROPIC_API_KEY", os.environ.get("CLAUDE_API_KEY", ""))
CLAUDE_MODEL   = "claude-sonnet-4-5"

# ──────────────────────────────────────────────────────────────
# The 6 phases (Felipe Vergara / 7 Maletas mapping)
# ──────────────────────────────────────────────────────────────

PHASES = [
    {
        "id": 1,
        "nombre": "Fase 1 — Conexión con el Dolor",
        "objetivo": "Activar el reconocimiento de problema en el público objetivo",
        "maleta": "maleta_2_problema",
        "principio": "Pain Awareness (Eugene Schwartz Stage 1)",
        "cta": "Cuéntanos en comentarios: ¿te ha pasado esto?",
        "formato_sugerido": "Reel 30-45s + historia personal",
    },
    {
        "id": 2,
        "nombre": "Fase 2 — Educación y Autoridad",
        "objetivo": "Posicionarse como experto con contenido de valor",
        "maleta": "maleta_3_solucion",
        "principio": "Authority Bias (Cialdini)",
        "cta": "Guarda este video — te va a servir",
        "formato_sugerido": "Carrusel educativo 5-8 slides",
    },
    {
        "id": 3,
        "nombre": "Fase 3 — Prueba Social y Testimonios",
        "objetivo": "Reducir el escepticismo con casos reales",
        "maleta": "maleta_5_testimonios",
        "principio": "Social Proof (Cialdini) + Herd Behavior",
        "cta": "¿Quieres un resultado así? Link en bio",
        "formato_sugerido": "Reel testimonio + subtítulos",
    },
    {
        "id": 4,
        "nombre": "Fase 4 — Manejo de Objeciones",
        "objetivo": "Eliminar las barreras mentales de compra",
        "maleta": "maleta_6_objeciones",
        "principio": "Cognitive Dissonance Resolution (Festinger)",
        "cta": "¿Tienes esta duda? Escríbenos",
        "formato_sugerido": "Video corto Q&A estilo directo",
    },
    {
        "id": 5,
        "nombre": "Fase 5 — Diferenciación y Valor",
        "objetivo": "Destacar por qué elegirlos vs la competencia",
        "maleta": "maleta_4_diferenciales",
        "principio": "Contrast Principle (Ariely) + Unique Value",
        "cta": "Compara y decide — nosotros confiamos en nuestro trabajo",
        "formato_sugerido": "Comparativa visual / Before-After",
    },
    {
        "id": 6,
        "nombre": "Fase 6 — Llamado a la Acción y Garantía",
        "objetivo": "Convertir la intención en acción con garantía clara",
        "maleta": "maleta_7_garantia",
        "principio": "Risk Reversal + Loss Aversion (Kahneman)",
        "cta": "Agenda tu consulta gratuita hoy",
        "formato_sugerido": "Video directo a cámara + oferta clara",
    },
]


# ──────────────────────────────────────────────────────────────
# DB helpers
# ──────────────────────────────────────────────────────────────

def _get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contenido_jobs (
            id TEXT PRIMARY KEY,
            investigacion_job_id TEXT,
            nombre_negocio TEXT,
            nicho TEXT,
            ciudad TEXT,
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
    conn.execute(f"UPDATE contenido_jobs SET {sets} WHERE id=?", vals)
    conn.commit()
    conn.close()


# ──────────────────────────────────────────────────────────────
# Claude helper
# ──────────────────────────────────────────────────────────────

def _claude(prompt, max_tokens=3000):
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
# Script generator (local, no Claude)
# ──────────────────────────────────────────────────────────────

def _generar_script(fase, video_num, nombre, nicho, ciudad,
                    maleta_data, reviews_pos, reviews_neg):
    """
CONTEXTO TEMPORAL Y GEOGRÁFICO:
- Año actual: 2026
- Rango de análisis: 2024-2025-2026
- Alcance: MUNDIAL (no solo Colombia)
- Prioridad: tendencias globales adaptadas al mercado local

FUENTES DE REFERENCIA:
- Creadores virales de EEUU, España, México, Colombia, Argentina
- TikTok, Instagram Reels, YouTube Shorts
- Videos con más de 1M de vistas en 2025-2026

Generate a complete video script for one of the 18 slots."""

    fase_id = fase["id"]
    principio = fase["principio"]
    cta = fase["cta"]

    # Extract relevant data from the correct maleta
    m = maleta_data if maleta_data else {}

    problemas   = m.get("maleta_2_problema", {}).get("problemas_principales", [])
    soluciones  = m.get("maleta_3_solucion", {}).get("soluciones_identificadas", [])
    diferenc    = m.get("maleta_4_diferenciales", {}).get("diferenciales_propios", [])
    testimonios = m.get("maleta_5_testimonios", {}).get("mejores_testimonios", [])
    objeciones  = m.get("maleta_6_objeciones", {}).get("lista_objeciones", [])
    garantias   = m.get("maleta_7_garantia", {}).get("garantias_identificadas", [])

    prob_str = str(problemas[0]) if problemas else f"encontrar un buen {nicho} en {ciudad}"
    sol_str  = str(soluciones[0]) if soluciones else f"nuestro servicio especializado"
    dif_str  = str(diferenc[0])   if diferenc   else f"atención personalizada"
    gar_str  = str(garantias[0])  if garantias  else "satisfacción garantizada"

    test_text = ""
    if testimonios:
        t = testimonios[0]
        test_text = t.get("texto", "") if isinstance(t, dict) else str(t)
    elif reviews_pos:
        test_text = str(reviews_pos[0])[:150]

    obj_text = str(objeciones[0]) if objeciones else "el precio es alto"

    # Hook variants per video_num (1, 2, or 3 within phase)
    hooks_by_phase = {
        1: [  # Dolor
            f"¿Sabías que el 80% de las personas en {ciudad} nunca resuelven {prob_str}?",
            f"Esto es lo que nadie te dice sobre {nicho} en {ciudad}...",
            f"Cometí el error de ignorar {prob_str} y esto fue lo que pasó",
        ],
        2: [  # Educación
            f"3 cosas que debes saber antes de contratar {nicho} en {ciudad}",
            f"Por qué la mayoría falla con {nicho} (y cómo evitarlo)",
            f"El método que usamos en {nombre} para resolver {prob_str}",
        ],
        3: [  # Prueba social
            f'"{test_text[:80]}..." — cliente real de {nombre}' if test_text else f"Así transformamos el negocio de Andrés en {ciudad}",
            f"De cero a resultados: el caso de uno de nuestros clientes en {ciudad}",
            f"Lo que nuestros clientes dicen después de trabajar con {nombre}",
        ],
        4: [  # Objeciones
            f'¿Crees que "{obj_text}"? Déjame mostrarte algo',
            f"La pregunta que nos hacen TODO el tiempo (y la respuesta honesta)",
            f"Por qué la gente duda de {nicho} y cómo lo resolvimos",
        ],
        5: [  # Diferenciación
            f"¿Por qué elegir {nombre} y no la competencia? La respuesta te va a sorprender",
            f"Esto es lo que nos diferencia de todos en {ciudad}",
            f"Comparamos: {dif_str} vs lo que ofrecen los demás",
        ],
        6: [  # CTA/Garantía
            f"Hoy puedes resolver {prob_str} — sin riesgo",
            f"Si no quedas satisfecho, {gar_str} — así de simple",
            f"Tienes 24 horas para aprovechar esto en {ciudad}",
        ],
    }

    escenas_by_phase = {
        1: [
            f"Muestra a alguien frustrado intentando resolver {prob_str}. Entorno reconocible de {ciudad}.",
            f"Presentador a cámara en entorno profesional. Tono cercano y empático.",
            f"Reconstrucción visual del problema con texto sobreimpuesto.",
        ],
        2: [
            f"Presentador en escritorio con pizarrón o tablet. Explica paso a paso.",
            f"Pantalla dividida: problema vs solución. Infografía animada.",
            f"Detrás de cámaras del proceso de {sol_str}.",
        ],
        3: [
            f"Entrevista breve con cliente real o lectura animada de reseña.",
            f"Fotos/videos de antes y después del cliente.",
            f"Presentador leyendo reseña positiva con comentario personal.",
        ],
        4: [
            f"Presentador directo a cámara, tono conversacional. Responde con datos.",
            f"Pantalla con objeción escrita → presentador la desmonta.",
            f"Video corto tipo respuesta TikTok a comentario real.",
        ],
        5: [
            f"Tabla comparativa visual animada. {nombre} vs 'otros'.",
            f"Demostración en vivo del diferencial: {dif_str}.",
            f"Presentador con pruebas físicas o testimonios del diferencial.",
        ],
        6: [
            f"Presentador a cámara, tono directo. Muestra la garantía en pantalla.",
            f"Demostración del proceso de agendamiento en 3 pasos simples.",
            f"Testimonios + CTA final con cuenta regresiva de oferta.",
        ],
    }

    desarrollos_by_phase = {
        1: [
            f"Contextualizá el problema. Datos reales si existen. Validá la emoción del espectador. Hacé que se identifique antes de ofrecer cualquier solución.",
            f"Describí cómo se ve el día a día con este problema sin resolver. Costos emocionales y económicos de no actuar.",
            f"Historia de 3 actos: situación inicial → problema peak → punto de quiebre que lleva a buscar solución.",
        ],
        2: [
            f"Explicá el método o proceso de {sol_str} en 3 pasos concretos. Usá lenguaje simple. Mostrá resultados esperados.",
            f"Desmitificá una creencia falsa del mercado. Presentá evidencia. Posicioná a {nombre} como la alternativa inteligente.",
            f"Tutorial corto o 'qué hacer vs qué no hacer'. Terminá con cómo {nombre} aplica esto.",
        ],
        3: [
            f"Dejá que el cliente hable. Presentá el contexto inicial, el proceso con {nombre}, y el resultado específico con métricas si hay.",
            f"Enfocate en el momento de transformación. ¿Qué cambió exactamente? ¿Cómo se sintió el cliente?",
            f"Acumulá varios testimonios cortos (15s cada uno) sobre el mismo tema para crear efecto de masa crítica.",
        ],
        4: [
            f"Nombrá la objeción sin defensas. Explicá por qué es válida. Luego mostrá la evidencia que la resuelve. Terminá con la garantía.",
            f"Marco de reencuadre: cambiá la perspectiva del costo a la del costo de no actuar.",
            f"Comparación de escenarios: con {nombre} vs sin {nombre} en 6 meses.",
        ],
        5: [
            f"Lista los 3 diferenciales clave. Para cada uno: qué es, por qué importa, prueba de que es real.",
            f"Historia de cliente que fue a la competencia, no funcionó, y luego llegó a {nombre}.",
            f"Proceso detrás de cámaras: mostrá {dif_str} en acción para demostrar que no es marketing vacío.",
        ],
        6: [
            f"Presentá la oferta clara: qué incluye, cuánto vale, qué garantía hay. Sin ambigüedades. CTA concreto.",
            f"Manejá la última objeción de timing: 'lo haré después'. Mostrá el costo de esperar.",
            f"Resumen de la transformación completa + llamado urgente a actuar con garantía de respaldo.",
        ],
    }

    idx = (video_num - 1) % 3
    hooks    = hooks_by_phase.get(fase_id, [f"Hook para {nombre}"] * 3)
    escenas  = escenas_by_phase.get(fase_id, [f"Escena principal"] * 3)
    desarro  = desarrollos_by_phase.get(fase_id, [f"Desarrollo"] * 3)

    hook      = hooks[idx]
    escena    = escenas[idx]
    desarr    = desarro[idx]
    cierre    = f"Recordá: {cta} — link en bio o mensaje directo."

    # ── REGLA TIKTOK/REELS: Hook de 3 segundos obligatorio ───
    # Los primeros 3 segundos son el 80% del éxito.
    # El hook debe parar el scroll o el video no existe.
    hook_tipo = (
        "pregunta_que_duela"      if hook.startswith("¿")
        else "afirmacion_que_sorprenda" if any(hook.startswith(p) for p in ["3 ", "Esto", "Cometí", "Por qué", "De cero"])
        else "resultado_antes_proceso"  if any(w in hook for w in ["transformamos", "caso de", "lo que dicen", "Sin riesgo", "satisfecho"])
        else "hook_generico"
    )
    hook_3_seg = hook.split("...")[0].rstrip(",").strip()
    if len(hook_3_seg) > 80:
        hook_3_seg = hook_3_seg[:77] + "..."

    return {
        "fase_id": fase_id,
        "fase_nombre": fase["nombre"],
        "video_num": video_num,
        "script_id": f"V{fase_id}.{video_num}",
        "titulo": f"V{fase_id}.{video_num} — {fase['nombre'].split('—')[1].strip()}",
        "objetivo": fase["objetivo"],
        "formato": fase["formato_sugerido"],
        "duracion_estimada": "30-60s",
        "principio_psicologico": principio,
        "hook_3_seg": hook_3_seg,
        "hook_tipo": hook_tipo,
        "hook_regla": (
            "OBLIGATORIO: Si este hook no para el scroll en 3 segundos, "
            "reemplazar antes de publicar. Opciones: pregunta que duela | "
            "afirmación que sorprenda | resultado antes del proceso."
        ),
        "HOOK": hook,
        "ESCENA": escena,
        "DESARROLLO": desarr,
        "CIERRE": cierre,
        "hashtags": [
            f"#{nicho.replace(' ','')}",
            f"#{ciudad.lower().replace(' ','')}",
            f"#{nombre.replace(' ','').lower()[:15]}",
            "#emprendimiento",
            "#marketing",
        ],
        "momento_publicacion": fase.get("momento", ""),
    }


# ──────────────────────────────────────────────────────────────
# 30-day calendar builder
# ──────────────────────────────────────────────────────────────

def _construir_calendario(scripts):
    """Spread 18 scripts over 30 days with optimal posting times."""

    # Best days: Tue, Thu, Sat (engagement peaks in LATAM)
    posting_days = []
    base = datetime.now()
    day = base
    while len(posting_days) < 18:
        if day.weekday() in (1, 3, 5):  # Tue, Thu, Sat
            posting_days.append(day)
        day += timedelta(days=1)

    times = ["07:00", "12:00", "19:00"]
    calendario = []
    for i, script in enumerate(scripts):
        post_date = posting_days[i] if i < len(posting_days) else base + timedelta(days=i * 2)
        post_time = times[i % 3]
        calendario.append({
            "dia": i + 1,
            "fecha": post_date.strftime("%Y-%m-%d"),
            "hora": post_time,
            "dia_semana": ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"][post_date.weekday()],
            "fase": script["fase_nombre"],
            "titulo": script["titulo"],
            "formato": script["formato"],
            "script_id": f"V{script['fase_id']}.{script['video_num']}",
        })

    return calendario


# ──────────────────────────────────────────────────────────────
# HTML report
# ──────────────────────────────────────────────────────────────

def _esc(s):
    if not isinstance(s, str):
        s = str(s)
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;"))


PHASE_COLORS = {
    1: "#ff3b30", 2: "#0071e3", 3: "#30d158",
    4: "#ff9500", 5: "#5e5ce6", 6: "#ff2d55",
}


def _generar_html(resultado):
    nombre = _esc(resultado.get("nombre_negocio", ""))
    nicho  = _esc(resultado.get("nicho", ""))
    ciudad = _esc(resultado.get("ciudad", ""))
    fecha  = _esc(resultado.get("generado_at", ""))
    scripts   = resultado.get("scripts", [])
    calendario = resultado.get("calendario", [])

    # Phase summary cards
    fases_html = ""
    for fase in PHASES:
        color = PHASE_COLORS.get(fase["id"], "#0071e3")
        fase_scripts = [s for s in scripts if s["fase_id"] == fase["id"]]
        fases_html += f"""
        <div class="fase-card" style="border-top:4px solid {color}">
          <div class="fase-num" style="color:{color}">Fase {fase['id']}</div>
          <div class="fase-title">{_esc(fase['nombre'].split('—')[1].strip() if '—' in fase['nombre'] else fase['nombre'])}</div>
          <div class="fase-obj">{_esc(fase['objetivo'])}</div>
          <div class="fase-scripts">{len(fase_scripts)} videos</div>
          <div class="fase-psic">🧠 {_esc(fase['principio'])}</div>
        </div>"""

    # All 18 scripts
    scripts_html = ""
    for s in scripts:
        color = PHASE_COLORS.get(s["fase_id"], "#0071e3")
        hashtags = " ".join(s.get("hashtags", []))
        scripts_html += f"""
        <div class="script-card" id="script-{_esc(s['script_id'])}">
          <div class="script-header" style="border-left:4px solid {color}">
            <span class="script-id" style="color:{color}">{_esc(s['script_id'])}</span>
            <span class="script-titulo">{_esc(s['titulo'])}</span>
            <span class="script-formato">{_esc(s['formato'])}</span>
          </div>
          <div class="script-section hook">
            <span class="sec-label">🎣 HOOK</span>
            <div class="sec-content">{_esc(s['HOOK'])}</div>
          </div>
          <div class="script-section escena">
            <span class="sec-label">🎬 ESCENA</span>
            <div class="sec-content">{_esc(s['ESCENA'])}</div>
          </div>
          <div class="script-section desarrollo">
            <span class="sec-label">📖 DESARROLLO</span>
            <div class="sec-content">{_esc(s['DESARROLLO'])}</div>
          </div>
          <div class="script-section cierre">
            <span class="sec-label">🚀 CIERRE & CTA</span>
            <div class="sec-content">{_esc(s['CIERRE'])}</div>
          </div>
          <div class="script-footer">
            <span class="psic">🧠 {_esc(s['principio_psicologico'])}</span>
            <span class="tags">{_esc(hashtags)}</span>
          </div>
        </div>"""

    # Calendar table
    cal_rows = ""
    for c in calendario:
        color = PHASE_COLORS.get(
            next((f["id"] for f in PHASES if f["nombre"] == c["fase"]), 1), "#0071e3"
        )
        cal_rows += f"""
        <tr>
          <td>{_esc(str(c['dia']))}</td>
          <td>{_esc(c['fecha'])}</td>
          <td>{_esc(c['dia_semana'])}</td>
          <td>{_esc(c['hora'])}</td>
          <td><span class="cal-id" style="color:{color}">{_esc(c['script_id'])}</span></td>
          <td>{_esc(c['titulo'])}</td>
          <td>{_esc(c['formato'])}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Plan de Contenido 30 Días — {nombre}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;
        background:#f5f5f7;color:#1d1d1f;line-height:1.6}}
  .hero{{background:#1d1d1f;color:#fff;padding:60px 40px;text-align:center}}
  .hero h1{{font-size:2.4rem;font-weight:700;margin-bottom:8px}}
  .hero .sub{{color:#86868b;font-size:1.1rem}}
  .hero .counter{{font-size:4rem;font-weight:800;color:#0071e3;margin:20px 0 4px}}
  .hero .counter-lbl{{color:#86868b;font-size:.9rem}}
  .badge{{display:inline-block;padding:6px 18px;border-radius:20px;
          font-size:.85rem;font-weight:600;margin:4px;background:#333;color:#fff}}
  .container{{max-width:1200px;margin:0 auto;padding:40px 20px}}
  .section{{background:#fff;border-radius:18px;padding:32px;margin-bottom:24px;
            box-shadow:0 2px 12px rgba(0,0,0,.06)}}
  .section h2{{font-size:1.4rem;font-weight:700;margin-bottom:20px}}
  .section h2::before{{content:'';display:inline-block;width:4px;height:1.2em;
                       background:#0071e3;margin-right:10px;border-radius:2px;vertical-align:middle}}
  .fases-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}}
  .fase-card{{background:#f5f5f7;border-radius:12px;padding:20px}}
  .fase-num{{font-size:1.4rem;font-weight:800;margin-bottom:4px}}
  .fase-title{{font-size:1rem;font-weight:700;margin-bottom:6px}}
  .fase-obj{{font-size:.85rem;color:#636366;margin-bottom:8px}}
  .fase-scripts{{font-size:.85rem;font-weight:600;color:#0071e3}}
  .fase-psic{{font-size:.8rem;color:#86868b;margin-top:6px}}
  .script-card{{background:#f5f5f7;border-radius:14px;padding:22px;margin-bottom:16px}}
  .script-header{{padding-left:12px;margin-bottom:14px;display:flex;
                  flex-wrap:wrap;align-items:center;gap:10px}}
  .script-id{{font-size:1.1rem;font-weight:800}}
  .script-titulo{{font-size:.95rem;font-weight:700;flex:1}}
  .script-formato{{font-size:.8rem;color:#86868b;background:#e5e5ea;
                   border-radius:20px;padding:3px 10px}}
  .script-section{{background:#fff;border-radius:10px;padding:14px;margin-bottom:10px}}
  .sec-label{{font-size:.8rem;font-weight:700;text-transform:uppercase;
              letter-spacing:.06em;color:#86868b;display:block;margin-bottom:6px}}
  .sec-content{{font-size:.93rem;color:#1d1d1f}}
  .script-section.hook .sec-content{{font-size:1rem;font-weight:600}}
  .script-footer{{display:flex;justify-content:space-between;
                  align-items:center;margin-top:10px;flex-wrap:wrap;gap:8px}}
  .psic{{font-size:.8rem;color:#5e5ce6;background:#f0f0ff;
         border-radius:20px;padding:4px 10px}}
  .tags{{font-size:.78rem;color:#86868b}}
  table{{width:100%;border-collapse:collapse;font-size:.88rem}}
  th{{background:#1d1d1f;color:#fff;padding:10px 14px;text-align:left;
      font-weight:600}}
  td{{padding:10px 14px;border-bottom:1px solid #e5e5ea}}
  tr:hover td{{background:#f5f5f7}}
  .cal-id{{font-weight:700}}
  .footer{{text-align:center;color:#86868b;font-size:.85rem;padding:40px 20px}}
  @media print{{.script-card{{break-inside:avoid}}}}
</style>
</head>
<body>

<div class="hero">
  <h1>Plan de Contenido 30 Días</h1>
  <div class="sub">{nombre} · {nicho} · {ciudad} · generado {fecha}</div>
  <div style="margin-top:16px">
    <span class="badge">{nicho}</span>
    <span class="badge">{ciudad}</span>
  </div>
  <div class="counter">18</div>
  <div class="counter-lbl">guiones completos · 6 fases × 3 videos · 30 días</div>
</div>

<div class="container">

  <section class="section">
    <h2>Las 6 Fases del Plan</h2>
    <div class="fases-grid">
      {fases_html}
    </div>
  </section>

  <section class="section">
    <h2>Calendario de 30 Días</h2>
    <table>
      <thead>
        <tr>
          <th>#</th><th>Fecha</th><th>Día</th><th>Hora</th>
          <th>Video</th><th>Título</th><th>Formato</th>
        </tr>
      </thead>
      <tbody>
        {cal_rows}
      </tbody>
    </table>
  </section>

  <section class="section">
    <h2>18 Guiones Completos</h2>
    {scripts_html}
  </section>

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

def _run_pipeline(job_id, investigacion_job_id, nombre, nicho, ciudad):
    try:
        _update_job(job_id, estado="procesando", progreso=5)

        maleta_data = {}
        reviews_pos = []
        reviews_neg = []

        if investigacion_job_id:
            try:
                from agent.deep_researcher import get_job_reporte as get_inv_reporte
            except ImportError:
                from deep_researcher import get_job_reporte as get_inv_reporte

            inv = get_inv_reporte(investigacion_job_id)
            if inv and inv.get("resultado"):
                res = inv["resultado"]
                maleta_data = res.get("7_maletas", {})
                reviews_pos = res.get("reviews_positivas", [])
                reviews_neg = res.get("reviews_negativas", [])

        _update_job(job_id, progreso=20)

        # NUEVO: Analizar formatos que funcionan en Meta Ads Library y TikTok
        print('Analizando formatos virales y Ads Library...')
        contexto_formatos = ""
        try:
            ads_data = _analizar_ads_library_nicho(nicho, pais='CO')
            tiktok_data = _analizar_tiktok_tendencias(nicho)
            contexto_formatos = (
                f"\nFORMATOS QUE MAS FUNCIONAN EN EL NICHO (Meta Ads Library + TikTok):\n"
                f"Video corto 15-60s: FORMATO DOMINANTE\n"
                f"Carrusel educativo: alto engagement\n"
                f"Fake podcast: posiciona autoridad\n"
                f"Anuncios activos detectados: {len(ads_data.get('anuncios_encontrados', []))}\n"
                f"Oportunidades: {'; '.join(ads_data.get('oportunidades', [])[:3])}\n"
                f"Tendencias TikTok: {'; '.join(tiktok_data[:2])}\n"
            )
        except Exception:
            pass

        # Generate all 18 scripts
        scripts = []
        for fase in PHASES:
            for vid_num in (1, 2, 3):
                script = _generar_script(
                    fase, vid_num, nombre, nicho, ciudad,
                    maleta_data, reviews_pos, reviews_neg,
                )
                scripts.append(script)
            _update_job(job_id, progreso=20 + fase["id"] * 10)

        _update_job(job_id, progreso=80)

        calendario = _construir_calendario(scripts)

        _update_job(job_id, progreso=88)

        # Optional Claude enhancement for script quality
        claude_tips = ""
        if CLAUDE_API_KEY and scripts:
            sample = scripts[0]
            prompt = (
                f"Eres un experto en contenido para redes sociales en Colombia.\n"
                f"Negocio: {nombre} ({nicho} en {ciudad}).\n"
                f"Revisa este hook y mejóralo para máximo impacto en Instagram Reels:\n"
                f"HOOK ORIGINAL: {sample['HOOK']}\n\n"
                f"Dame 2 versiones mejoradas (máx 15 palabras cada una) "
                f"con el mismo principio psicológico ({sample['principio_psicologico']}). "
                f"Solo los dos hooks, sin explicación."
            )
            claude_tips = _claude(prompt, max_tokens=200)

        resultado = {
            "nombre_negocio": nombre,
            "nicho": nicho,
            "ciudad": ciudad,
            "investigacion_job_id": investigacion_job_id,
            "total_scripts": len(scripts),
            "scripts": scripts,
            "calendario": calendario,
            "claude_tips": claude_tips,
            "generado_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

        # Save HTML
        reports_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
        os.makedirs(reports_dir, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", nombre.lower())[:30]
        date_str = datetime.now().strftime("%Y%m%d")
        html_filename = f"content-plan-{slug}-{date_str}.html"
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

def crear_job(nombre, nicho, ciudad, investigacion_job_id=""):
    job_id = str(uuid.uuid4())
    conn = _get_conn()
    conn.execute(
        """INSERT INTO contenido_jobs
           (id, investigacion_job_id, nombre_negocio, nicho, ciudad,
            estado, progreso, creado_at)
           VALUES (?,?,?,?,?,'pendiente',0,?)""",
        (job_id, investigacion_job_id, nombre, nicho, ciudad,
         datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()

    t = threading.Thread(
        target=_run_pipeline,
        args=(job_id, investigacion_job_id, nombre, nicho, ciudad),
        daemon=True,
    )
    t.start()
    return job_id


def get_job_estado(job_id):
    conn = _get_conn()
    row = conn.execute(
        "SELECT id,nombre_negocio,estado,progreso,creado_at,terminado_at FROM contenido_jobs WHERE id=?",
        (job_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)


def get_job_reporte(job_id):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM contenido_jobs WHERE id=?", (job_id,)).fetchone()
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
        "SELECT id,nombre_negocio,nicho,ciudad,estado,progreso,creado_at "
        "FROM contenido_jobs ORDER BY creado_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ──────────────────────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────────────────────

import datetime as _dt_cp
_HOY_CP = _dt_cp.datetime.now()
AÑO_ACTUAL_CP = _HOY_CP.year
AÑO_ANTERIOR_CP = AÑO_ACTUAL_CP - 1
AÑO_MAS_ANTERIOR_CP = AÑO_ACTUAL_CP - 2
RANGO_AÑOS_CP = f"2024 2025 2026"

if __name__ == "__main__":
    import argparse, time

    parser = argparse.ArgumentParser(description="IM Content Planner — 18 scripts / 30 días")
    parser.add_argument("--nombre",  required=True)
    parser.add_argument("--nicho",   required=True)
    parser.add_argument("--ciudad",  default="Medellín")
    parser.add_argument("--inv-job", default="", help="ID del job de investigación")
    args = parser.parse_args()

    print(f"Generando plan de contenido para: {args.nombre}")
    job_id = crear_job(
        nombre=args.nombre,
        nicho=args.nicho,
        ciudad=args.ciudad,
        investigacion_job_id=args.inv_job,
    )
    print(f"Job ID: {job_id}")

    while True:
        estado = get_job_estado(job_id)
        print(f"  [{estado['progreso']}%] {estado['estado']}")
        if estado["estado"] in ("completado", "error"):
            break
        time.sleep(1)

    reporte = get_job_reporte(job_id)
    if reporte and reporte.get("resultado"):
        res = reporte["resultado"]
        if isinstance(res, dict):
            print(f"\n✅ Plan generado: {res.get('total_scripts', 0)} guiones")
            print(f"   Calendario: {len(res.get('calendario', []))} fechas")
            if res.get("html_filename"):
                print(f"   Reporte: reports/{res['html_filename']}")
        else:
            print(f"\n❌ Error: {res}")


def _analizar_ads_library_nicho(nicho, pais='CO'):
    import requests, os, time
    from bs4 import BeautifulSoup
    import datetime

    anio_actual = datetime.datetime.now().year
    resultados = {
        'anuncios_encontrados': [],
        'formatos_populares': {},
        'mensajes_mas_usados': [],
        'hooks_identificados': [],
        'oportunidades': []
    }

    queries_nicho = {
        'odontologos': ['odontologo', 'dental', 'sonrisa', 'implante'],
        'dermatologo': ['dermatologia', 'piel', 'acne', 'botox'],
        'agencia_viajes': ['viaje', 'tour', 'vacaciones', 'paquete'],
        'seguros': ['seguro', 'proteccion', 'poliza'],
        'sello_musical': ['musica', 'artista', 'lanzamiento', 'album'],
        'artista_independiente': ['artista', 'musica', 'concierto'],
        'ecommerce': ['compra', 'tienda', 'envio', 'oferta'],
    }

    keywords = queries_nicho.get(nicho, [nicho])
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    for keyword in keywords[:2]:
        try:
            url = f"https://www.facebook.com/ads/library/?country={pais}&q={requests.utils.quote(keyword)}&ad_type=all&active_status=active"
            resultados['anuncios_encontrados'].append({
                'keyword': keyword,
                'url': url,
                'nota': f'Consultar manualmente: {url}'
            })
            query = f'facebook ads {keyword} {nicho} formato video imagen carrusel {anio_actual} mejor rendimiento'
            r = requests.get(
                f"https://www.google.com/search?q={requests.utils.quote(query)}&hl=es",
                headers=headers, timeout=10
            )
            soup = BeautifulSoup(r.text, 'html.parser')
            snippets = [d.get_text(strip=True) for d in soup.find_all('div', class_=['BNeawe','VwiC3b'])]
            for s in snippets[:3]:
                if len(s) > 30:
                    resultados['mensajes_mas_usados'].append(s[:150])
            time.sleep(2)
        except Exception:
            pass

    token = os.environ.get('META_ACCESS_TOKEN', '')
    account = os.environ.get('META_AD_ACCOUNT_ID', '')
    if token and account:
        try:
            r = requests.get(
                f'https://graph.facebook.com/v19.0/{account}/ads',
                params={
                    'access_token': token,
                    'fields': 'name,creative,status',
                    'effective_status': ['ACTIVE'],
                    'limit': 20
                }, timeout=10
            )
            ads = r.json().get('data', [])
            formatos = {}
            for ad in ads:
                creative_id = ad.get('creative', {}).get('id', '')
                if creative_id:
                    rc = requests.get(
                        f'https://graph.facebook.com/v19.0/{creative_id}',
                        params={'access_token': token, 'fields': 'object_type,body,title'},
                        timeout=10
                    )
                    creative = rc.json()
                    tipo = creative.get('object_type', 'UNKNOWN')
                    formatos[tipo] = formatos.get(tipo, 0) + 1
                    body = creative.get('body', '')
                    if body:
                        resultados['hooks_identificados'].append(body[:100])
            resultados['formatos_populares'] = formatos
        except Exception as e:
            resultados['formatos_populares'] = {'error': str(e)}

    resultados['tendencias_formatos_2024_2026'] = {
        'video_corto': {'plataformas': ['TikTok','Instagram Reels','YouTube Shorts'], 'duracion_optima': '15-60s', 'recomendacion': 'PRIORIDAD ALTA - formato dominante 2024-2026'},
        'carrusel':    {'plataformas': ['Instagram','Facebook'], 'slides_optimos': '5-7', 'recomendacion': 'Ideal para educativo y comparativas'},
        'imagen_unica':{'plataformas': ['Facebook','Instagram'], 'recomendacion': 'Util para ofertas directas y testimonios'},
        'video_largo': {'plataformas': ['YouTube','Facebook'], 'duracion_optima': '8-15 min', 'recomendacion': 'Para educativo profundo y podcast'},
    }

    resultados['oportunidades'] = [
        f'Video corto con hook en 3 segundos — formato dominante en {nicho} {anio_actual}',
        'Carrusel educativo — alto engagement para sector salud y servicios',
        'Behind the scenes — humaniza la marca y genera confianza',
        'Testimonios en video corto — prueba social inmediata',
        'Fake podcast — posiciona como autoridad con bajo costo',
    ]
    return resultados


def _analizar_tiktok_tendencias(nicho):
    import requests, time
    import datetime
    anio_actual = datetime.datetime.now().year
    headers = {'User-Agent': 'Mozilla/5.0'}
    queries = [
        f'tiktok {nicho} viral tendencia {anio_actual} colombia latinoamerica',
        f'tiktok {nicho} millones vistas {anio_actual} formato ganador',
        f'hashtag {nicho} tiktok trending {anio_actual}',
    ]
    tendencias = []
    for query in queries[:2]:
        try:
            r = requests.get(
                f"https://www.google.com/search?q={requests.utils.quote(query)}&hl=es",
                headers=headers, timeout=10
            )
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, 'html.parser')
            snippets = [d.get_text(strip=True) for d in soup.find_all('div', class_='BNeawe')]
            tendencias.extend([s[:150] for s in snippets[:3] if len(s) > 20])
            time.sleep(2)
        except Exception:
            pass
    return tendencias[:10]


def _investigar_algoritmos_redes(nicho='general'):
    import requests, time, os
    import datetime
    from bs4 import BeautifulSoup
    import anthropic

    anio_actual = datetime.datetime.now().year
    anio_anterior = anio_actual - 1
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    resultado = {
        'instagram': {},
        'tiktok': {},
        'meta_api_insights': {},
        'recomendaciones_nicho': [],
        'que_no_hacer': [],
        'fecha_analisis': datetime.datetime.now().isoformat()
    }

    fuentes_queries = {
        'instagram_algoritmo_oficial': [
            f'site:about.instagram.com algorithm ranking {anio_actual}',
            f'instagram algorithm how it works official {anio_actual}',
            f'instagram reels algorithm ranking factors {anio_actual} {anio_anterior}',
            f'instagram seo hashtags reach {anio_actual} what works',
        ],
        'tiktok_algoritmo_oficial': [
            f'site:newsroom.tiktok.com algorithm {anio_actual}',
            f'tiktok algorithm ranking factors official {anio_actual}',
            f'tiktok for you page algorithm {anio_actual} how it works',
            f'tiktok seo search optimization {anio_actual}',
        ],
        'blogs_especializados': [
            f'hootsuite instagram algorithm {anio_actual} complete guide',
            f'later.com tiktok algorithm {anio_actual} guide',
            f'hubspot social media algorithm {anio_actual} report',
            f'metricool instagram tiktok algoritmo {anio_actual}',
        ],
        'viralidad_formatos': [
            f'instagram reels viral factors {anio_actual} reach boost',
            f'tiktok viral video formula {anio_actual} what works',
            f'instagram shadowban {anio_actual} causes solutions',
        ],
        'geolocalizacion_seo': [
            f'instagram geolocation tags reach local {anio_actual}',
            f'instagram seo keywords bio captions {anio_actual}',
            f'tiktok local seo geolocation {anio_actual}',
        ]
    }

    datos_crudos = {}
    for categoria, queries in fuentes_queries.items():
        datos_crudos[categoria] = []
        for query in queries[:2]:
            try:
                url = f"https://www.google.com/search?q={requests.utils.quote(query)}&hl=es&num=5"
                r = requests.get(url, headers=headers, timeout=10)
                soup = BeautifulSoup(r.text, "html.parser")
                for div in soup.find_all(["div","span"], class_=["BNeawe","VwiC3b","IsZvec"]):
                    texto = div.get_text(strip=True)
                    if len(texto) > 40:
                        datos_crudos[categoria].append(texto[:200])
                time.sleep(2)
            except Exception:
                pass

    token = os.environ.get("META_ACCESS_TOKEN", "")
    account = os.environ.get("META_AD_ACCOUNT_ID", "")
    if token and account:
        try:
            r = requests.get(
                f"https://graph.facebook.com/v19.0/{account}/insights",
                params={"access_token": token, "fields": "impressions,reach,ctr,cpm",
                        "date_preset": "last_30d", "level": "ad", "limit": 20},
                timeout=10
            )
            insights = r.json().get("data", [])
            resultado["meta_api_insights"] = {
                "total_ads_analizados": len(insights),
                "nota": "Basado en cuenta de Intelligent Markets"
            }
        except Exception as e:
            resultado["meta_api_insights"] = {"error": str(e)}

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        client = anthropic.Anthropic(api_key=api_key)
        contexto = f"""
Datos recopilados de fuentes oficiales y especializadas sobre
los algoritmos de Instagram y TikTok en {anio_anterior}-{anio_actual}:

INSTAGRAM:
{chr(10).join(datos_crudos.get("instagram_algoritmo_oficial", [])[:4])}

TIKTOK:
{chr(10).join(datos_crudos.get("tiktok_algoritmo_oficial", [])[:4])}

BLOGS ESPECIALIZADOS (Hootsuite, Later, HubSpot, Metricool):
{chr(10).join(datos_crudos.get("blogs_especializados", [])[:4])}

VIRALIDAD Y FORMATOS:
{chr(10).join(datos_crudos.get("viralidad_formatos", [])[:4])}

GEOLOCALIZACIÓN Y SEO:
{chr(10).join(datos_crudos.get("geolocalizacion_seo", [])[:4])}

NICHO: {nicho} | AÑO: {anio_actual}
"""
        prompt = f"""{contexto}

Genera un informe COMPLETO sobre cómo funcionan los algoritmos de Instagram y TikTok en {anio_actual}.
Incluye obligatoriamente:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INFORME DE ALGORITMOS — INSTAGRAM Y TIKTOK {anio_actual}
Nicho: {nicho} | IM System — Intelligent Markets
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. ALGORITMO INSTAGRAM {anio_actual} — señales de ranking, ventana crítica, pesos de interacciones, SEO
2. ALGORITMO TIKTOK {anio_actual} — For You Page, watch time/completion rate con números exactos, SEO interno
3. FORMATOS QUE MÁS FUNCIONAN — con métricas de engagement por formato
4. FACTORES DE VIRALIDAD — los primeros 3 segundos, save rate, share rate, comment velocity
5. QUÉ DAÑA EL ALCANCE — shadowban causas, contenido penalizado, errores críticos
6. GEOLOCALIZACIÓN Y SEO AVANZADO — keywords, hashtags, ubicación
7. ESTRATEGIA ESPECÍFICA PARA {nicho} — horarios, frecuencia, formatos ganadores, hashtags Colombia/LATAM
8. CALENDARIO DE PUBLICACIÓN RECOMENDADO — frecuencia semanal, horarios Colombia
9. KPIs Y MÉTRICAS — lo que importa vs vanity metrics, benchmarks {anio_actual}
10. PLAN DE ACCIÓN — top 5 acciones inmediatas

Sé específico con números y porcentajes. Sin JSON. Formato texto limpio con separadores visuales.
"""
        try:
            msg = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=8000,
                messages=[{"role": "user", "content": prompt}]
            )
            resultado["informe_completo"] = msg.content[0].text
        except Exception as e:
            resultado["informe_completo"] = f"Error generando informe: {e}"

    return resultado
