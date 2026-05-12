# Configurar el Bot Telegram del Orquestador IM

Un solo bot controla todo: investigación, leads, Meta Ads, guiones, auditorías.

---

## Paso 1 — Crear el bot en Telegram

1. Abre Telegram en tu celular o escritorio
2. Busca **@BotFather**
3. Escribe: `/newbot`
4. Nombre del bot: `IM Orquestador`
5. Username: `im_orquestador_bot` (o cualquiera disponible)
6. BotFather te dará un token como este:
   ```
   7412345678:AAHdqTcvCH1vGWJxfSeofSs35m1234567890
   ```

---

## Paso 2 — Agregar el token al .env

Abre `.env` y pega el token:

```
TELEGRAM_BOT_TOKEN=7412345678:AAHdqTcvCH1vGWJxfSeofSs35m1234567890
```

---

## Paso 3 — Obtener tu Chat ID (automático)

1. Busca tu bot en Telegram por el username que elegiste
2. Escribe `/start`
3. El bot responderá y guardará tu Chat ID en `.env` automáticamente

---

## Paso 4 — Configurar Meta Ads (opcional pero recomendado)

### Obtener el Access Token:
1. Ve a [developers.facebook.com](https://developers.facebook.com)
2. Crea una app (tipo: Business) o usa una existente
3. Agrega el producto **Marketing API**
4. Ve a **Herramientas** → **Explorador de la API Graph**
5. Selecciona tu app → genera un token con permisos:
   - `ads_read`
   - `ads_management`
   - `business_management`
6. Para token de larga duración: cámbialo por uno de 60 días o usa un System User en Business Manager

### Obtener el Ad Account ID:
1. Ve a [business.facebook.com](https://business.facebook.com)
2. Configuración del negocio → Cuentas publicitarias
3. El ID tiene formato `act_XXXXXXXXXXXXXXXXX`

### Agregar al .env:
```
META_ACCESS_TOKEN=EAAxxxxxxxxxxxxxxxx
META_AD_ACCOUNT_ID=act_1234567890
```

---

## Paso 5 — Reiniciar el servidor

```bash
# En la terminal del proyecto:
python server/server.py
```

Debes ver:
```
[OK] Bot Telegram activo
```

---

## Paso 6 — Probar el bot

Escribe estos comandos en Telegram:

```
ayuda          → ver todos los comandos
estado         → salud del sistema
reportes       → campañas Meta Ads activas
investiga Clínica Dental Sonrisa https://clinica.com
busca leads odontólogos en Medellín
guiones Ortopédica El Éxito ortopedia
audita Mi Cuenta Publicitaria
```

---

## Comandos completos

### Investigación
```
investiga [nombre negocio] [url]
7maletas [nombre negocio]
mercados [nicho] en [ciudad]
```

### Contenido
```
guiones [nombre negocio] [nicho]
plan contenido [nombre]
```

### Leads
```
busca leads [nicho] en [ciudad]
estado leads
```

### Meta Ads — Reportes
```
reportes
métricas [nombre campaña]
rendimiento hoy
analiza [nombre campaña]
```

### Meta Ads — Gestión
```
pausa [nombre campaña]
activa [nombre campaña]
presupuesto [nombre campaña] [monto COP]
crea campaña [nombre] [objetivo] [presupuesto/día]
```

### Auditoría
```
audita [nombre cuenta]
```

### Sistema
```
estado
ayuda
```

---

## Arquitectura

```
Mateo en Telegram
      ↓
telegram_agent.py (bot + intérprete)
      ↓ según el comando:
      ├── deep_researcher.py     → 7 Maletas
      ├── market_researcher.py   → mercados
      ├── ads_strategist.py      → estrategia ADS
      ├── content_planner.py     → 18 guiones
      ├── lead_finder_v2.py      → buscar leads
      ├── meta_ads_mcp.py        → Meta Ads real
      ├── paid_media_auditor.py  → auditoría 42 checkpoints
      └── intelligence_engine.py → análisis clientes
      ↓
Respuesta en Telegram
```

---

## Reporte diario automático

El bot envía un resumen automático cada día a las **8:00 AM Colombia** con:
- Emails enviados ayer
- Leads en DB
- Respuestas recibidas
- Reuniones agendadas
- Rendimiento de campañas Meta

---

## Troubleshooting

**El bot no responde:**
- Verifica que `TELEGRAM_BOT_TOKEN` está en .env
- Reinicia el servidor
- Revisa que el servidor imprima `[OK] Bot Telegram activo`

**Meta Ads da error:**
- El token puede haber expirado (duran 60 días por defecto)
- Genera un nuevo token en developers.facebook.com
- Verifica permisos: `ads_read` + `ads_management`

**"Chat ID no configurado":**
- Escribe `/start` en el bot → se guarda automáticamente
- O agrégalo manualmente en .env: `TELEGRAM_CHAT_ID=123456789`
