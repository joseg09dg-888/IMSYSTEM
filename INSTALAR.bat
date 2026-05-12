@echo off
title IM System — Instalador Completo
color 0F
cd /d "%~dp0"

echo.
echo  ===================================================
echo   IM SYSTEM v3 COMPLETO — INTELLIGENT MARKETS
echo   Instalador automatico para Windows
echo  ===================================================
echo.

REM Verificar Python
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo  [X] Python no encontrado
    echo.
    echo  Instala Python 3.12 desde: https://www.python.org/downloads/
    echo  IMPORTANTE: Marca [X] Add Python to PATH durante la instalacion
    echo.
    start "" "https://www.python.org/downloads/"
    pause
    exit /b 1
)

echo  [OK] Python encontrado
echo.

REM Instalar dependencias
echo  Instalando dependencias Python...
python -m pip install flask flask-cors requests beautifulsoup4 pytz -q
echo  [OK] Dependencias instaladas
echo.

REM Crear .env si no existe
if not exist ".env" (
    echo  Configurando credenciales...
    echo.
    echo  Necesitas tu Gmail App Password.
    echo  Obtenerla en: https://myaccount.google.com/apppasswords
    echo.
    set /p GMAIL_PWD="  App Password de Gmail (Enter para omitir): "
    set /p APOLLO_KEY="  Apollo.io API Key (Enter para omitir): "
    set /p ANTHROPIC_KEY="  Anthropic API Key (para generar copy): "
    echo.
    
    (
        echo # IM System v3 - Configuracion
        echo IM_EMAIL_PASSWORD=%GMAIL_PWD%
        echo APOLLO_API_KEY=%APOLLO_KEY%
        echo ANTHROPIC_API_KEY=%ANTHROPIC_KEY%
        echo IM_EMAIL=intelligentmarkets@gmail.com
        echo CAL_MUSIC=https://cal.com/intelligent-markets-agencia/sello-30min
        echo CAL_EMPRESAS=https://cal.com/intelligent-markets-agencia/30min
        echo IM_TRACKING_HOST=
    ) > .env
    echo  [OK] .env creado
) else (
    echo  [OK] .env ya existe
)

echo.
echo  ===================================================
echo   INSTALACION COMPLETA
echo  ===================================================
echo.
echo  COMO USAR:
echo.
echo  1. PLATAFORMA WEB (panel completo):
echo     Doble clic en: INICIAR_PLATAFORMA.bat
echo     Abre: http://localhost:5000
echo.
echo  2. AGENTES (modo interactivo):
echo     Doble clic en: mateo.bat
echo     Doble clic en: jose.bat
echo.
echo  3. BUSCAR LEADS:
echo     Doble clic en: buscar_leads.bat
echo.
echo  4. SCHEDULER (envio automatico):
echo     Doble clic en: mateo_scheduler.bat
echo     Doble clic en: jose_scheduler.bat
echo.
echo  5. VER ESTADISTICAS:
echo     Doble clic en: stats.bat
echo.
echo  Abriendo la plataforma...
timeout /t 3 /nobreak >nul

start "" "http://localhost:5000"
start "" INICIAR_PLATAFORMA.bat
