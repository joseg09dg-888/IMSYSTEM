# IM SYSTEM — INSTRUCCIONES PERMANENTES PARA CLAUDE CODE
# LEE ESTE ARCHIVO ANTES DE TOCAR CUALQUIER COSA

## REGLA 1 — ANTES DE TRABAJAR
1. Lee este archivo completo
2. Lee agent/agency_skills/im-frontend/SKILL.md
3. Haz backup de cualquier archivo antes de modificarlo
4. Verifica después de cada cambio que funciona
5. NUNCA digas que terminaste sin verificar

## EL SISTEMA
IM System — plataforma de prospección B2B de Intelligent Markets
Carpeta: C:\Users\jose-\Downloads\IM-COMPLETO
Servidor: Flask en puerto 5000
Frontend: frontend/index.html (UN SOLO archivo)
Repositorio: https://github.com/joseg09dg-888/IMSYSTEM

## CREDENCIALES EN .env
- ANTHROPIC_API_KEY — Claude API (modelo: claude-sonnet-4-5)
- TELEGRAM_BOT_TOKEN — Bot @im_orquestador_bot
- TELEGRAM_CHAT_ID — IDs separados por coma
- META_ACCESS_TOKEN — Meta Ads API (expira cada 60 días)
- META_AD_ACCOUNT_ID — act_2604881333134474
- META_APP_ID — 2295402611266259
- META_APP_SECRET — a69d0b6ec1551a669d8144cb4d88d18d
- IM_EMAIL — intelligentmarkets@gmail.com

## ARQUITECTURA DE AGENTES
Jerarquía obligatoria:
1. Gerente de Plataforma (auditor supremo)
2. Gerente de Marketing (coordinador)
3. PM-A (identidad/narrativa) y PM-B (crecimiento/performance)
4. Especialistas: Investigador, Estratega ADS, Director Contenido, Lead Finder, PR/Correo

## MÓDULO INVESTIGACIÓN 7 MALETAS — MÁS IMPORTANTE
El investigador debe buscar en ESTAS fuentes en DOS niveles:

NIVEL MACRO (el nicho/sector — NO la empresa):
- DANE: "comportamiento consumidor {nicho} Colombia 2024 2025"
- Google Scholar: "psicología paciente {nicho} Colombia neurociencia"
- Google Scholar: "sesgos cognitivos consumidor {nicho} latinoamerica"
- Google Scholar: "toma de decisiones {nicho} Colombia estudios"
- Noticias: "mercado {nicho} Colombia 2024 2025 tendencias"
- Gremios del sector
- Estadísticas gobierno

NIVEL MICRO (la empresa específica):
- Web oficial — scraping LIMPIO sin JS/CSS
- Google Maps — mínimo 50 reviews con texto completo
- Facebook Ads Library — anuncios activos
  URL: https://www.facebook.com/ads/library/?country=CO&q={nombre}
- Instagram — buscar aunque no lo den
- TikTok — buscar perfil y contenido
- Top 5 competidores — reviews, precios, anuncios
- Menciones externas — foros, grupos, Reddit

ANÁLISIS CON CLAUDE API debe incluir OBLIGATORIAMENTE:
1. SESGOS COGNITIVOS identificados con evidencia real
2. INFLUENCIADORES de la decisión (pareja, hijos, padres, amigos)
3. PROCESO DE DECISIÓN (tiempo, fuentes, comparativas)
4. MOTIVACIONES PROFUNDAS (declaradas vs reales)
5. ANÁLISIS 7 MALETAS completo con citas textuales
6. PERFIL PSICOGRÁFICO detallado
7. ESTRATEGIA ADS con 3 copies y hooks basados en dolores reales
8. 18 GUIONES en 6 fases × 3 videos

ESTRUCTURA DEL INFORME (texto formateado — NUNCA JSON):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INFORME DE INTELIGENCIA — [NOMBRE]
[Ciudad] | [Nicho] | [Fecha]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FUENTES CONSULTADAS:
✓ Web oficial: [URL]
✓ Google Maps: [X reviews]
✓ Facebook Ads Library: [X anuncios]
✓ Instagram: [@handle o no encontrado]
✓ Competidores: [X analizados]
✓ Estudios académicos: [X fuentes]
✓ DANE/Gobierno: [datos encontrados]

1. PERFIL DEL NEGOCIO
[datos reales]

2. VOZ DEL CLIENTE — REVIEWS REALES
[mínimo 10 citas textuales]

3. COMPETIDORES
[5 competidores con rating, precios, diferenciales]

4. PUBLICIDAD ACTIVA — META ADS
[anuncios encontrados o "ninguno"]

5. CONTEXTO DEL SECTOR 2024-2025
[datos del NIVEL MACRO — psicología del nicho]

6. ANÁLISIS 7 MALETAS
MALETA 1 — QUÉ TIENE: [con evidencia]
MALETA 2 — QUÉ FALTA: [con evidencia]
MALETA 3 — QUÉ DUELE: [citas textuales de reviews]
MALETA 4 — QUÉ DESEA: [citas textuales]
MALETA 5 — QUÉ LO FRENA: [objeciones + sesgos cognitivos]
MALETA 6 — QUÉ LO MUEVE: [disparadores con evidencia]
MALETA 7 — OPORTUNIDAD IM: [conclusión accionable]

7. SESGOS COGNITIVOS Y NEUROCIENCIA
[sesgos identificados con evidencia real]

8. INFLUENCIADORES DE DECISIÓN
[quién influye: pareja, hijos, padres — con evidencia]

9. PROCESO DE DECISIÓN
[tiempo, pasos, qué buscan antes de comprar]

10. PERFIL PSICOGRÁFICO
[edad, NSE, motivación, miedo, cómo busca]

11. ESTRATEGIA ADS
[campañas según tamaño empresa]
[3 copies con hooks basados en dolores reales]

12. 18 GUIONES
FASE 1 — ATRACCIÓN (3 videos):
VIDEO 1.1: Hook + Escena + Desarrollo + CTA
[etc para las 6 fases]

## MÓDULO TELEGRAM
Bot: @im_orquestador_bot
El bot debe entender lenguaje natural usando Claude API.
Comandos que DEBE ejecutar correctamente:
- "reportes" → métricas reales de Meta Ads
- "investiga [negocio]" → investigación 7 Maletas
- "busca leads [nicho] en [ciudad]" → scraping
- "pausa [campaña]" → con confirmación sí/no
- "activa [campaña]" → con confirmación sí/no
- "presupuesto [campaña] [monto]" → con confirmación
- "estado" → resumen del sistema
- nota de voz → transcribir con Claude API

## MÓDULO META ADS
Token: en .env META_ACCESS_TOKEN (60 días)
Account: act_2604881333134474
Funciones que DEBEN funcionar:
- get_resumen_general() → todas las campañas con métricas
- pause_campaign(nombre) → pausar con confirmación
- activate_campaign(nombre) → activar con confirmación
- set_budget(nombre, monto) → cambiar presupuesto
- create_campaign_completa(params) → crear con audiencia real

## MÓDULO CONTENIDO
Estructura OBLIGATORIA — 6 fases × 3 videos = 18 guiones:
FASE 1 — ATRACCIÓN: objetivo aversión a la pérdida
FASE 2 — EDUCATIVO/FAKE PODCAST: objetivo autoridad
FASE 3 — DOCUMENTACIÓN/BLOG: objetivo prueba social
FASE 4 — VALIDACIÓN: objetivo evidencia concreta
FASE 5 — ORGÁNICO/STORYTELLING: objetivo conexión
FASE 6 — FIDELIZACIÓN/MANIFIESTO: objetivo identidad tribal

Cada guión DEBE tener:
- Hook (primeros 3 segundos — regla TikTok)
- Escena (descripción visual)
- Desarrollo (guión completo)
- CTA (llamada a la acción)
- Principio psicológico activado

## FLUJO DE TRABAJO CORRECTO
1. Mateo/José buscan leads por nicho y ciudad
2. Investigador investiga cada lead (7 Maletas)
3. Orquestador audita con PM-B (datos reales, no genéricos)
4. Si pasa auditoría → generar email personalizado
5. Scheduler envía en horario Colombia (Lun-Vie 6am-7pm, Sáb 6am-12pm)
6. Sistema monitorea aperturas y respuestas
7. Si responde → generar informe pre-reunión
8. Si firma → Intelligence Engine completo del cliente

## ERRORES COMUNES — NO REPETIR
1. NUNCA usar re.sub para reemplazar el CSS completo — solo append
2. NUNCA modificar el frontend sin hacer backup primero
3. NUNCA decir que terminó sin verificar con curl
4. NUNCA usar el modelo claude-sonnet-4-20250514 — usar claude-sonnet-4-5
5. NUNCA mostrar JSON crudo en el frontend — siempre texto formateado
6. SIEMPRE leer este CLAUDE.md antes de trabajar
7. SIEMPRE verificar que el servidor corre después de reiniciar
8. El modelo correcto es: claude-sonnet-4-5

## REGLAS ANTI-BAN META ADS API — OBLIGATORIAS
Fuente: políticas oficiales Meta + video Felipe Vergara (368JQmfakVg)

### SISTEMA DE PUNTUACIÓN META (más importante):
- Score máximo: 60 puntos cada 300 segundos (5 minutos)
- Llamada de LECTURA (ver datos) = 1 punto
- Llamada de ESCRITURA (crear/editar) = 3 puntos
- Superar 60 → error throttling → si persiste → BANEO
- Crear 3 campañas + 3 adsets + 5 anuncios = 102 llamadas → BANEO INMEDIATO

### LÍMITES IMPLEMENTADOS EN meta_ads_mcp.py:
- delay_entre_llamadas: 3 segundos mínimo
- max_campanas_por_dia: 5 (límite voluntario IM)
- max_cambios_presupuesto_hora: 4 por ad set (límite oficial Meta)
- delay_entre_campanas: 60 segundos

### NUNCA hacer sin aprobación humana explícita:
- Crear campañas nuevas
- Cambiar presupuestos
- Pausar o activar campañas
- Cualquier llamada de ESCRITURA a Meta API

### MODO CORRECTO DE ANÁLISIS:
- Un fetch masivo (1 sola llamada con todos los campos)
- Guardar respuesta en archivo local
- Analizar el archivo local (sin más llamadas)
- Secuencial: una campaña a la vez, nunca toda la cuenta

### TOKEN SEGURO (setup correcto):
- Usar Business Manager de RESPALDO (no el BM principal)
- Crear System User (no token personal)
- Token sin expiración con permisos: ads_read + business_management SOLAMENTE
- NUNCA ads_management (permite crear campañas → riesgo de baneo)

### CONTENIDO PROHIBIDO EN ANUNCIOS:
garantizado, garantia, gratis, gana dinero, ingresos pasivos,
antes y despues, cura, elimina, urgente, ultima oportunidad

### SI HAY RESTRICCIÓN:
1. DETENER todo de inmediato
2. Notificar por Telegram
3. NO crear cuentas alternativas
4. Ir a facebook.com/help/contact/adsreview
5. Ver logs/guia_anti_ban_meta.txt para protocolo completo

## COMANDOS ÚTILES
Iniciar servidor: start /min pythonw server\server.py
Detener servidor: taskkill /F /IM pythonw.exe 2>nul
Verificar: curl -s http://localhost:5000/api/dashboard
Subir GitHub: git add . && git commit -m "update" && git push origin main
Ver logs: type logs\platform.log | tail -50
Guia anti-ban: type logs\guia_anti_ban_meta.txt
