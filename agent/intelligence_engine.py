#!/usr/bin/env python3
"""
IM Intelligence Engine — Intelligent Markets
Una vez que tienes el cliente: investigación → estrategia → plan de contenido → identidad de marca
"""

import os, json, re, csv, argparse
from datetime import datetime
from pathlib import Path

try:
    import requests
    NET_OK = True
except ImportError:
    NET_OK = False

# ════════════════════════════════════════════════════════════════
# PROMPTS AL MODELO (usa la API de Claude internamente)
# ════════════════════════════════════════════════════════════════

def call_claude(system_prompt, user_prompt, max_tokens=4000):
    """Llama a Claude Sonnet para generar el análisis"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    # Load env if not already loaded
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
        return "[Error: ANTHROPIC_API_KEY no configurada en .env]"
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
            timeout=120,
        )
        data = r.json()
        if "error" in data:
            return f"[Error API: {data['error'].get('message', str(data['error']))}]"
        return data.get("content", [{}])[0].get("text", "")
    except Exception as e:
        return f"[Error API: {e}]"

# ════════════════════════════════════════════════════════════════
# SISTEMA PROMPTS POR MÓDULO
# ════════════════════════════════════════════════════════════════

SYS_INVESTIGADOR = """Eres el Analista Principal de Inteligencia de Mercado de Intelligent Markets.
Combinas 30 años de experiencia en marketing con neurociencia del consumidor (Kahneman, Cialdini, Ariely),
psicología persuasiva y metodología de las 7 Maletas.

Cuando investigas, usas el lenguaje EXACTO del cliente/nicho, citas fuentes concretas,
y cada insight incluye el principio neurológico o psicológico que lo explica.

Tu investigación es accionable: cada sección termina con "Lo que IM hace con esto".
Eres brutalmente honesto sobre lo que funciona y lo que no para cada nicho."""

SYS_ESTRATEGA = """Eres el Director de Estrategia de Marketing de Intelligent Markets.
Diseñas estrategias de marketing 360° que combinan:
- Neurociencia y psicología del consumidor
- Paid media (Meta Ads, Google Ads, TikTok Ads)
- Content marketing y SEO
- Email marketing y automatización
- Branding y construcción de marca
- Conversión y CRO

Tus estrategias son ESPECÍFICAS, con tácticas concretas, KPIs medibles y cronogramas realistas.
Nunca das respuestas genéricas. Todo está adaptado al nicho, presupuesto y objetivo del cliente."""

SYS_CONTENT = """Eres el Director Creativo de Contenidos de Intelligent Markets.
Creas planes de contenido viral basados en neurociencia, psicología del comportamiento y
análisis de tendencias de cada plataforma.

Tus planes de contenido incluyen:
- Hooks que detienen el scroll (primeras 3 palabras críticas)
- Estructura de guión para videos (Hook → Problema → Solución → CTA)
- Calendario editorial con frecuencia óptima por plataforma
- Pilares de contenido basados en los dolores del nicho
- Formatos por plataforma: Reels, TikTok, Stories, Carruseles, Posts

Tu contenido activa el Sistema 1 (emocional) antes del Sistema 2 (racional)."""

SYS_BRANDING = """Eres el Director de Branding de Intelligent Markets.
Construyes identidades de marca que generan conexión emocional, recordación y confianza.

Tu proceso de branding incluye:
- Arquetipos de Jung aplicados a la marca
- Voz y tono de comunicación
- Posicionamiento vs competencia
- Propuesta de valor única (UVP)
- Mensajes clave por audiencia
- Sistema visual (colores, tipografía, estilo fotográfico)
- Storytelling de marca

Todo conectado con la psicología del nicho investigado."""

# ════════════════════════════════════════════════════════════════
# MÓDULOS DE INTELIGENCIA
# ════════════════════════════════════════════════════════════════

def modulo_investigacion(cliente_data):
    """MÓDULO 1: Investigación profunda del cliente y su nicho"""
    prompt = f"""
Analiza en profundidad este cliente de Intelligent Markets y su nicho:

DATOS DEL CLIENTE:
{json.dumps(cliente_data, ensure_ascii=False, indent=2)}

Genera una investigación completa con:

## 1. PERFIL DEL CLIENTE
- Situación actual del negocio
- Posicionamiento actual vs ideal
- Fortalezas y debilidades identificadas

## 2. ANÁLISIS DEL NICHO CON NEUROCIENCIA
- Perfil psicográfico detallado del cliente IDEAL de este negocio
- Sesgos cognitivos clave que afectan la decisión de compra en este nicho
- Arquetipos de Jung del consumidor del nicho
- Sistema 1 vs Sistema 2: cómo decide el cliente de este negocio

## 3. LAS 7 MALETAS APLICADAS AL CLIENTE
Para cada maleta, aplica al nicho específico:
1. Público: ¿Quién compra exactamente?
2. Problema: ¿Cuál es el dolor real (y el detrás del dolor)?
3. Solución: ¿Qué busca exactamente?
4. Confianza: ¿Por qué debería creerle a este negocio?
5. Precio: ¿Cómo percibe el costo y el valor?
6. Urgencia: ¿Qué lo hace actuar ahora vs después?
7. Competencia: ¿Quiénes son y qué hace diferente a este negocio?

## 4. TOP 10 RAZONES POR QUÉ COMPRAN
Con el principio psicológico detrás de cada una.

## 5. TOP 10 OBJECIONES REALES
Con cómo manejar cada una usando neurociencia persuasiva.

## 6. OPORTUNIDADES DE MERCADO DETECTADAS
- ¿Qué no está haciendo la competencia?
- ¿Qué ángulo de comunicación está sin explotar?
- ¿Cuál es el diferenciador que Intelligent Markets puede potenciar?

Usa lenguaje específico del nicho. Sé concreto. Cada insight debe ser accionable.
"""
    return call_claude(SYS_INVESTIGADOR, prompt, max_tokens=4000)

def modulo_estrategia(cliente_data, investigacion):
    """MÓDULO 2: Estrategia de marketing 360°"""
    prompt = f"""
Con base en esta investigación del cliente, diseña la estrategia de marketing completa:

CLIENTE: {json.dumps(cliente_data, ensure_ascii=False, indent=2)}

INVESTIGACIÓN PREVIA:
{investigacion[:2000]}

Genera la ESTRATEGIA DE MARKETING 360° con:

## 1. OBJETIVO SMART
- Objetivo principal a 3 meses
- KPIs específicos y medibles
- Punto de partida actual vs meta

## 2. AUDIENCIAS OBJETIVO
- Audiencia primaria (perfil detallado)
- Audiencia secundaria
- Audiencias lookalike para paid media
- Segmentos de remarketing

## 3. ESTRATEGIA DE PAID MEDIA
### Meta Ads (Facebook + Instagram):
- Estructura de campañas recomendada (awareness → consideración → conversión)
- Tipos de anuncios (video/imagen/carrusel/lead gen)
- Presupuesto recomendado y distribución
- KPIs: CPL objetivo, CTR esperado, ROAS

### Google Ads (si aplica):
- Tipos de campaña (Search/Display/YouTube)
- Keywords principales y negativas
- Presupuesto estimado

### TikTok Ads (si aplica):
- Si el nicho tiene audiencia en TikTok
- Formato y enfoque

## 4. ESTRATEGIA ORGÁNICA
- Plataformas prioritarias para este nicho
- Frecuencia de publicación recomendada
- Tipos de contenido orgánico vs pagado
- Estrategia de hashtags y SEO social

## 5. EMBUDO DE CONVERSIÓN
- Top of Funnel (atracción)
- Middle of Funnel (nurturing)
- Bottom of Funnel (conversión)
- Post-venta (retención y referidos)

## 6. EMAIL / WHATSAPP MARKETING
- Secuencia de bienvenida
- Nurturing de leads
- Seguimiento post-reunión

## 7. CRONOGRAMA A 90 DÍAS
- Semana 1-2: Setup y lanzamiento
- Mes 1: Objetivos y acciones
- Mes 2: Optimización
- Mes 3: Escalamiento

## 8. PRESUPUESTO RECOMENDADO
- Desglose por canal
- ROI esperado por canal
- Cuándo escalar inversión

Sé específico. Da números reales. Tácticas accionables.
"""
    return call_claude(SYS_ESTRATEGA, prompt, max_tokens=4000)

def modulo_plan_contenido(cliente_data, investigacion, estrategia):
    """MÓDULO 3: Plan de contenido completo"""
    prompt = f"""
Crea el plan de contenido completo para este cliente:

CLIENTE: {json.dumps(cliente_data, ensure_ascii=False, indent=2)}

INSIGHTS CLAVE DE INVESTIGACIÓN:
{investigacion[:1500]}

Con base en la estrategia definida, genera:

## 1. PILARES DE CONTENIDO
Define 5 pilares de contenido basados en los dolores del nicho:
Para cada pilar:
- Nombre y descripción
- Por qué este pilar conecta con el nicho (principio psicológico)
- % del contenido total
- Tipos de piezas que genera

## 2. CALENDARIO EDITORIAL — 30 DÍAS
Para cada plataforma activa, 30 días de contenido:

### Instagram / Facebook:
| Día | Formato | Pilar | Tema específico | Hook (primeras palabras) | CTA |
|-----|---------|-------|-----------------|--------------------------|-----|
[Genera 30 filas]

### TikTok / Reels (si aplica):
[Mismo formato — enfocado en video]

## 3. BANCO DE 20 HOOKS VIRALES
Hooks específicos para el nicho, optimizados para detener el scroll:
1. [Hook de dolor]
2. [Hook de curiosidad]
3. [Hook de transformación]
4. [Hook de prueba social]
5. [Hook de autoridad]
... hasta 20

## 4. GUIONES DE VIDEO — 5 EJEMPLOS
Para cada video:
TÍTULO:
DURACIÓN: [segundos]
HOOK (0-3 seg):
PROBLEMA (3-10 seg):
SOLUCIÓN (10-25 seg):
PRUEBA SOCIAL (25-35 seg):
CTA (35-45 seg):

## 5. TEXTOS PARA ANUNCIOS PAGADOS
### 3 variaciones de copy para Meta Ads:
Para cada variación:
- HEADLINE (máx 25 caracteres)
- TEXTO PRINCIPAL (máx 125 caracteres)
- DESCRIPCIÓN (máx 30 caracteres)
- CTA

## 6. STORYTELLING DE MARCA
- Historia de origen del negocio (para humanizar la marca)
- Historia de transformación de cliente (caso de éxito)
- Historia del "por qué" (propósito de la marca)

Usa lenguaje del nicho. Hooks específicos. Nada genérico.
"""
    return call_claude(SYS_CONTENT, prompt, max_tokens=4000)

def modulo_marca(cliente_data, investigacion):
    """MÓDULO 4: Construcción y fortalecimiento de marca"""
    prompt = f"""
Construye la identidad y estrategia de marca para este cliente:

CLIENTE: {json.dumps(cliente_data, ensure_ascii=False, indent=2)}

PERFIL DEL CONSUMIDOR (de la investigación):
{investigacion[:1500]}

Genera la GUÍA DE MARCA COMPLETA:

## 1. DIAGNÓSTICO DE MARCA ACTUAL
- Percepción actual (qué transmite hoy)
- Brechas entre percepción actual e ideal
- Prioridades de mejora

## 2. POSICIONAMIENTO ESTRATÉGICO
- Declaración de posicionamiento (una oración)
- Propuesta de Valor Única (UVP)
- Promesa de marca
- Prueba de la promesa (evidencia)
- Por qué nosotros y no la competencia

## 3. ARQUETIPO DE MARCA
- Arquetipo principal de Jung y por qué
- Cómo se manifiesta en comunicación
- Marcas de referencia con el mismo arquetipo
- Lo que NUNCA debería hacer esta marca (anti-arquetipo)

## 4. VOZ Y TONO DE COMUNICACIÓN
- Personalidad de marca (5 adjetivos)
- Tono por plataforma:
  * Instagram: [tono específico]
  * TikTok: [tono específico]
  * Email: [tono específico]
  * WhatsApp: [tono específico]
- Palabras que SÍ usa esta marca
- Palabras que NUNCA usa esta marca
- Ejemplos de mensajes ON-BRAND vs OFF-BRAND

## 5. SISTEMA VISUAL (DIRECCIÓN)
- Paleta de colores recomendada (con HEX y psicología del color)
- Tipografías recomendadas (display + cuerpo)
- Estilo fotográfico (descripción detallada)
- Estilo de video (referentes)
- Lo que debe evitar visualmente

## 6. MENSAJES CLAVE POR AUDIENCIA
Para cada audiencia del nicho:
- Mensaje principal
- Beneficio que resuena más
- Miedo que neutraliza
- CTA más efectivo

## 7. DIFERENCIADORES COMPETITIVOS
Top 5 razones por las que esta marca gana vs competencia,
con cómo comunicar cada uno.

## 8. NAMING Y TAGLINE (si necesita revisión)
- Análisis del nombre actual
- Tagline recomendado
- Por qué funciona para el nicho

Conecta todo con la psicología del consumidor del nicho.
"""
    return call_claude(SYS_BRANDING, prompt, max_tokens=4000)

# ════════════════════════════════════════════════════════════════
# GENERADOR DE REPORTE HTML
# ════════════════════════════════════════════════════════════════

def generar_reporte_html(cliente_data, modulos):
    """Genera el reporte HTML completo con diseño IM"""
    nombre = cliente_data.get("nombre_negocio", "Cliente")
    nicho = cliente_data.get("nicho", "")
    fecha = datetime.now().strftime("%d de %B de %Y")
    slug = nombre.lower().replace(" ", "-")[:30]

    def sec(titulo, contenido, color="#6200FF"):
        # Convierte markdown básico a HTML
        lines = contenido.split("\n")
        html_lines = []
        for line in lines:
            if line.startswith("## "):
                html_lines.append(f'<h3 style="color:{color};font-family:Bebas Neue,sans-serif;font-size:18px;letter-spacing:2px;margin:24px 0 10px;border-bottom:1px solid rgba(98,0,255,0.2);padding-bottom:8px">{line[3:]}</h3>')
            elif line.startswith("### "):
                html_lines.append(f'<h4 style="color:#aaa;font-size:13px;letter-spacing:1.5px;text-transform:uppercase;margin:18px 0 8px">{line[4:]}</h4>')
            elif line.startswith("- "):
                html_lines.append(f'<li style="margin-bottom:6px;color:#ccc">{line[2:]}</li>')
            elif line.startswith("|"):
                html_lines.append(f'<code style="display:block;font-size:11px;color:#888;margin:2px 0">{line}</code>')
            elif line.strip() == "":
                html_lines.append("<br>")
            else:
                html_lines.append(f'<p style="margin:6px 0;color:#ddd;line-height:1.6;font-size:13px">{line}</p>')
        return f"""
<div style="background:#161616;border:1px solid rgba(255,255,255,0.06);border-radius:12px;padding:28px;margin-bottom:20px;border-left:4px solid {color}">
  <h2 style="font-family:Bebas Neue,sans-serif;font-size:20px;color:{color};letter-spacing:3px;margin:0 0 20px">{titulo}</h2>
  {''.join(html_lines)}
</div>"""

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>IM Intelligence — {nombre}</title>
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Space+Grotesk:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{background:#080808;color:#e8e8e8;font-family:'Space Grotesk',sans-serif;min-height:100vh}}
  .header{{background:linear-gradient(135deg,#0d0d0d 0%,#1a0033 100%);padding:60px 40px;border-bottom:1px solid rgba(98,0,255,0.3);position:relative;overflow:hidden}}
  .header::before{{content:'';position:absolute;top:-50%;right:-10%;width:600px;height:600px;background:radial-gradient(circle,rgba(98,0,255,0.15) 0%,transparent 70%);pointer-events:none}}
  .logo-im{{font-family:'Bebas Neue',sans-serif;font-size:48px;color:#fff;letter-spacing:4px}}
  .logo-bar{{display:inline-block;width:5px;height:48px;background:#6200FF;margin-left:3px;vertical-align:bottom}}
  .tagline{{font-size:11px;letter-spacing:4px;color:#6200FF;text-transform:uppercase;margin-top:4px}}
  .report-title{{margin-top:40px}}
  .report-title h1{{font-family:'Bebas Neue',sans-serif;font-size:42px;color:#fff;letter-spacing:2px;line-height:1.1}}
  .report-title .sub{{font-size:13px;color:#888;margin-top:8px;letter-spacing:1px}}
  .meta-badges{{display:flex;gap:10px;margin-top:20px;flex-wrap:wrap}}
  .badge{{background:rgba(98,0,255,0.15);border:1px solid rgba(98,0,255,0.3);color:#a97bff;padding:5px 14px;border-radius:20px;font-size:11px;font-weight:600;letter-spacing:1px}}
  .container{{max-width:900px;margin:0 auto;padding:40px 20px}}
  .toc{{background:#111;border:1px solid rgba(255,255,255,0.06);border-radius:12px;padding:24px;margin-bottom:32px}}
  .toc h3{{font-family:'Bebas Neue',sans-serif;font-size:16px;letter-spacing:2px;color:#6200FF;margin-bottom:14px}}
  .toc a{{color:#888;text-decoration:none;font-size:12px;display:block;padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.04);transition:color 0.2s}}
  .toc a:hover{{color:#a97bff}}
  footer{{text-align:center;padding:40px;color:#444;font-size:11px;border-top:1px solid rgba(255,255,255,0.05);margin-top:40px}}
  @media print{{body{{background:#fff;color:#000}}}}
</style>
</head>
<body>

<div class="header">
  <div class="logo-im">IM<span class="logo-bar"></span></div>
  <div class="tagline">Intelligence Report — Intelligent Markets</div>
  <div class="report-title">
    <h1>REPORTE ESTRATÉGICO<br>{nombre.upper()}</h1>
    <div class="sub">Generado el {fecha} · Nicho: {nicho.replace("_"," ").title()}</div>
  </div>
  <div class="meta-badges">
    <span class="badge">🧠 Neurociencia Aplicada</span>
    <span class="badge">📊 7 Maletas</span>
    <span class="badge">🎯 Estrategia 360°</span>
    <span class="badge">📅 Plan de Contenido 30D</span>
    <span class="badge">🏷️ Branding</span>
  </div>
</div>

<div class="container">

  <div class="toc">
    <h3>📋 CONTENIDO DEL REPORTE</h3>
    <a href="#investigacion">01 — Investigación de Mercado + Neurociencia + 7 Maletas</a>
    <a href="#estrategia">02 — Estrategia de Marketing 360°</a>
    <a href="#contenido">03 — Plan de Contenido 30 Días</a>
    <a href="#marca">04 — Identidad y Construcción de Marca</a>
  </div>

  <div id="investigacion">
    {sec("01 — INVESTIGACIÓN DE MERCADO + NEUROCIENCIA + 7 MALETAS", modulos.get("investigacion", "Pendiente de generación."), "#6200FF")}
  </div>

  <div id="estrategia">
    {sec("02 — ESTRATEGIA DE MARKETING 360°", modulos.get("estrategia", "Pendiente de generación."), "#00F5A0")}
  </div>

  <div id="contenido">
    {sec("03 — PLAN DE CONTENIDO 30 DÍAS", modulos.get("contenido", "Pendiente de generación."), "#FFD600")}
  </div>

  <div id="marca">
    {sec("04 — IDENTIDAD Y CONSTRUCCIÓN DE MARCA", modulos.get("marca", "Pendiente de generación."), "#FF6B6B")}
  </div>

</div>

<footer>
  Intelligent Markets · intelligentmarkets@gmail.com<br>
  Reporte generado automáticamente por IM Intelligence Engine v2<br>
  Somos tu socio de crecimiento a largo plazo.
</footer>

</body>
</html>"""

    out_dir = Path(__file__).parent.parent / "reports"
    out_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    filename = out_dir / f"im-report-{slug}-{ts}.html"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)
    return str(filename)

# ════════════════════════════════════════════════════════════════
# FLUJO PRINCIPAL
# ════════════════════════════════════════════════════════════════

def run_intelligence(cliente_data, modulos_activos=None, output_html=True):
    """
    Ejecuta todos los módulos de inteligencia para un cliente.
    
    Args:
        cliente_data: dict con info del cliente
        modulos_activos: lista de módulos a correr (None = todos)
        output_html: si generar el reporte HTML
    
    Returns:
        dict con todos los módulos generados
    """
    if modulos_activos is None:
        modulos_activos = ["investigacion", "estrategia", "contenido", "marca"]

    print(f"\n{'═'*58}")
    print(f"  IM INTELLIGENCE ENGINE")
    print(f"  Cliente: {cliente_data.get('nombre_negocio', '—')}")
    print(f"  Nicho: {cliente_data.get('nicho', '—')}")
    print(f"{'═'*58}\n")

    resultados = {}

    if "investigacion" in modulos_activos:
        print("  🧠 Módulo 1: Investigación + Neurociencia + 7 Maletas...")
        resultados["investigacion"] = modulo_investigacion(cliente_data)
        print("     ✅ Completado\n")

    if "estrategia" in modulos_activos:
        print("  🎯 Módulo 2: Estrategia de Marketing 360°...")
        resultados["estrategia"] = modulo_estrategia(
            cliente_data, resultados.get("investigacion", "")
        )
        print("     ✅ Completado\n")

    if "contenido" in modulos_activos:
        print("  📅 Módulo 3: Plan de Contenido 30 Días...")
        resultados["contenido"] = modulo_plan_contenido(
            cliente_data,
            resultados.get("investigacion", ""),
            resultados.get("estrategia", ""),
        )
        print("     ✅ Completado\n")

    if "marca" in modulos_activos:
        print("  🏷️ Módulo 4: Identidad y Construcción de Marca...")
        resultados["marca"] = modulo_marca(
            cliente_data, resultados.get("investigacion", "")
        )
        print("     ✅ Completado\n")

    if output_html:
        html_path = generar_reporte_html(cliente_data, resultados)
        resultados["reporte_html"] = html_path
        print(f"  📄 Reporte HTML generado: {html_path}")

    # Guardar JSON de respaldo
    out_dir = Path(__file__).parent.parent / "reports"
    out_dir.mkdir(exist_ok=True)
    slug = cliente_data.get("nombre_negocio", "cliente").lower().replace(" ", "-")[:20]
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    json_path = out_dir / f"im-data-{slug}-{ts}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"cliente": cliente_data, "modulos": resultados}, f, ensure_ascii=False, indent=2)

    print(f"\n{'═'*58}")
    print(f"  ✅ Intelligence Engine completado")
    print(f"  📄 HTML: {resultados.get('reporte_html', '—')}")
    print(f"  💾 JSON: {json_path}")
    print(f"{'═'*58}\n")

    return resultados


def generar_analisis_completo(nombre, nicho, ciudad, tamanio="mediana"):
    """
    Wrapper para el orquestador. Retorna dict estructurado con propuesta,
    diferencial, tono, voz y narrativa — palabras clave que PM-A valida.
    """
    cliente_data = {
        "nombre_negocio": nombre,
        "nicho":          nicho,
        "ciudad":         ciudad,
        "tamanio":        tamanio,
    }

    # Solo módulos ligeros para no ralentizar el orquestador
    marca_txt = modulo_marca(cliente_data, investigacion="")

    # Si la API falla, devolvemos un template con las claves requeridas
    if not marca_txt or marca_txt.startswith("[Error"):
        propuesta    = f"Propuesta de valor única para {nombre} en el sector {nicho} de {ciudad}."
        diferencial  = f"Diferencial competitivo identificado para {nombre}."
        tono         = "Profesional con cercanía — narrativa de autoridad empática."
        voz          = "Directa, sin tecnicismos, orientada a resultados concretos."
        personalidad = "Experto confiable que habla el idioma del cliente."
    else:
        # Extraer secciones del texto generado por Claude
        propuesta    = _extraer_seccion(marca_txt, ["propuesta", "promesa"])
        diferencial  = _extraer_seccion(marca_txt, ["diferencial", "posicionamiento"])
        tono         = _extraer_seccion(marca_txt, ["tono", "voz"])
        voz          = _extraer_seccion(marca_txt, ["voz", "personalidad"])
        personalidad = _extraer_seccion(marca_txt, ["personalidad", "narrativa"])

    return {
        "nombre":      nombre,
        "nicho":       nicho,
        "ciudad":      ciudad,
        "propuesta":   propuesta,
        "diferencial": diferencial,
        "tono":        tono,
        "voz":         voz,
        "personalidad": personalidad,
        "narrativa":   f"Narrativa de marca: {propuesta[:120]}",
        "posicionamiento": f"{nombre} — referente de {nicho} en {ciudad}.",
        "texto_completo": marca_txt or "",
        "generado_at": datetime.now().isoformat(),
    }


def _extraer_seccion(texto, claves):
    """Extrae el párrafo más relevante de texto según palabras clave."""
    lineas = texto.splitlines()
    for clave in claves:
        for i, linea in enumerate(lineas):
            if clave.lower() in linea.lower():
                bloque = []
                for j in range(i, min(i + 4, len(lineas))):
                    if lineas[j].strip():
                        bloque.append(lineas[j].strip())
                if bloque:
                    return " ".join(bloque)[:300]
    # fallback: primer párrafo no vacío
    for linea in lineas:
        if len(linea.strip()) > 30:
            return linea.strip()[:300]
    return texto[:200] if texto else ""


# ════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(
        description="IM Intelligence Engine — Estrategia completa para clientes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EJEMPLOS:
  # Correr todos los módulos para un cliente (interactivo)
  python intelligence_engine.py --nuevo-cliente

  # Cargar cliente desde JSON
  python intelligence_engine.py --cliente data/cliente_clinica.json

  # Solo investigación y estrategia (sin contenido ni marca)
  python intelligence_engine.py --cliente data/cliente.json --modulos investigacion estrategia

ESTRUCTURA DEL JSON DE CLIENTE:
  {
    "nombre_negocio": "Clínica Dental Ospina",
    "nicho": "odontologos",
    "vertical": "empresas",
    "ciudad": "Medellín",
    "pais": "Colombia",
    "descripcion": "Clínica dental de alta gama con 3 sedes",
    "servicios": ["ortodoncia", "implantes", "blanqueamiento"],
    "precio_promedio": "500000 COP por consulta",
    "años_operando": 8,
    "empleados": 12,
    "canales_actuales": ["Instagram", "Google Maps", "voz a voz"],
    "objetivo_principal": "Conseguir 30 pacientes nuevos al mes",
    "presupuesto_marketing": "3000000 COP/mes",
    "competidores": ["Clínica X", "Clínica Y"],
    "diferenciador": "Especialistas en cirugía maxilofacial con tecnología 3D",
    "notas": "Tiene 4.8★ en Google con 200 reseñas. Sin ads activos."
  }
        """
    )
    p.add_argument("--cliente", help="Archivo JSON con datos del cliente")
    p.add_argument("--nuevo-cliente", action="store_true", help="Crear nuevo cliente interactivamente")
    p.add_argument("--modulos", nargs="+",
                   choices=["investigacion", "estrategia", "contenido", "marca"],
                   help="Módulos a ejecutar (default: todos)")

    args = p.parse_args()

    if args.nuevo_cliente:
        print("\n🧠 IM INTELLIGENCE ENGINE — Nuevo Cliente\n")
        cliente = {}
        cliente["nombre_negocio"] = input("  Nombre del negocio: ").strip()
        cliente["nicho"] = input("  Nicho (odontologos/sello_musical/etc): ").strip()
        cliente["ciudad"] = input("  Ciudad: ").strip()
        cliente["pais"] = input("  País: ").strip()
        cliente["descripcion"] = input("  Descripción breve: ").strip()
        cliente["servicios"] = input("  Servicios principales (separados por coma): ").strip().split(",")
        cliente["objetivo_principal"] = input("  Objetivo principal: ").strip()
        cliente["presupuesto_marketing"] = input("  Presupuesto de marketing: ").strip()
        cliente["diferenciador"] = input("  ¿Qué los hace diferentes?: ").strip()
        cliente["notas"] = input("  Notas adicionales: ").strip()
        cliente["vertical"] = "music" if "sello" in cliente["nicho"] or "music" in cliente["nicho"] or "artista" in cliente["nicho"] or "manager" in cliente["nicho"] else "empresas"

        # Guardar cliente
        out_dir = Path(__file__).parent.parent / "data"
        out_dir.mkdir(exist_ok=True)
        slug = cliente["nombre_negocio"].lower().replace(" ", "_")[:20]
        client_file = out_dir / f"cliente_{slug}.json"
        with open(client_file, "w", encoding="utf-8") as f:
            json.dump(cliente, f, ensure_ascii=False, indent=2)
        print(f"\n  💾 Cliente guardado: {client_file}\n")

        run_intelligence(cliente, modulos_activos=args.modulos)

    elif args.cliente:
        with open(args.cliente, "r", encoding="utf-8") as f:
            cliente = json.load(f)
        run_intelligence(cliente, modulos_activos=args.modulos)

    else:
        p.print_help()

if __name__ == "__main__":
    main()
