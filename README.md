# IM System v3 — Intelligent Markets

Sistema de automatización de marketing con IA para agencias.

## Stack

- **Backend**: Python + Flask + SQLite (Neon PostgreSQL en producción)
- **Frontend**: HTML + Vanilla JS (puerto 3001)
- **Agentes IA**: Claude (Anthropic) + Google Maps + Meta Ads API
- **Bot**: Telegram con soporte multi-usuario

## Módulos

| Módulo | Descripción |
|--------|-------------|
| `im_agents.py` | Agentes Mateo y José — emails de prospección |
| `deep_researcher.py` | Investigación profunda 7 Maletas |
| `market_researcher.py` | Investigación de mercados por nicho/ciudad |
| `telegram_agent.py` | Bot orquestador en Telegram |
| `lead_finder_v2.py` | Búsqueda de leads con Google Maps + Apollo |
| `content_planner.py` | Generador de 18 guiones de contenido |
| `ads_strategist.py` | Estrategia Meta Ads |
| `paid_media_auditor.py` | Auditoría 42 checkpoints |
| `intelligence_engine.py` | Análisis de clientes |
| `im_deliverability.py` | Anti-spam + tracking de aperturas |
| `im_scheduler.py` | Scheduler automático de envíos |
| `session_memory.py` | Memoria persistente entre sesiones |
| `orchestrator.py` | Orquestador de flujos completos |
| `meta_ads_mcp.py` | Gestión real de Facebook Ads |

## Instalación

```bash
pip install -r requirements.txt
cp .env.example .env
# Editar .env con tus credenciales
pythonw server/server.py
```

O usar `INICIAR_BACKGROUND.bat` en Windows.

## Puertos

- Backend API: `http://localhost:5000`
- Frontend: abrir `frontend/index.html` directo o con live server
