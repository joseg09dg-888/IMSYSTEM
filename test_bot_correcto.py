#!/usr/bin/env python3
"""
Test correcto del bot de Telegram.
- Lee el bot_id real
- Obtiene el update_id actual (no usa 0)
- Envía mensajes y espera respuestas del bot
"""
import urllib.request, urllib.parse, json, time, os, sys
from pathlib import Path
if hasattr(sys.stdout, 'reconfigure'):
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass

def load_env():
    env = Path(__file__).parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if k.strip():
                    os.environ[k.strip()] = v.strip()
load_env()

TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

if not TOKEN or not CHAT_ID:
    print("❌ Falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en .env")
    sys.exit(1)

BASE = f"https://api.telegram.org/bot{TOKEN}"

def api(method, **params):
    url = f"{BASE}/{method}"
    data = json.dumps(params).encode()
    req = urllib.request.Request(url, data=data,
          headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"ok": False, "error": str(e)}

def send(text):
    return api("sendMessage", chat_id=int(CHAT_ID), text=text)

# 1. Obtener info del bot
bot_info = api("getMe")
if not bot_info.get("ok"):
    print("❌ Token inválido:", bot_info)
    sys.exit(1)
bot_id = bot_info["result"]["id"]
bot_name = bot_info["result"]["username"]
print(f"✅ Bot: @{bot_name} (id={bot_id})")

# 2. Obtener el update_id máximo actual (para no leer mensajes viejos)
updates = api("getUpdates", limit=1, timeout=0)
if updates.get("ok") and updates["result"]:
    last_update_id = updates["result"][-1]["update_id"]
else:
    last_update_id = 0
print(f"📍 Último update_id conocido: {last_update_id}")

# 3. Confirmar offset para limpiar cola
if last_update_id > 0:
    api("getUpdates", offset=last_update_id + 1, limit=1, timeout=0)

# 4. Enviar comandos de prueba
comandos = ["estado", "ayuda"]
print(f"\n📤 Enviando {len(comandos)} comandos a chat_id={CHAT_ID}...\n")
for cmd in comandos:
    r = send(cmd)
    if r.get("ok"):
        print(f"  ✅ Enviado: '{cmd}' (msg_id={r['result']['message_id']})")
    else:
        print(f"  ❌ Error enviando '{cmd}': {r}")
    time.sleep(0.5)

# 5. Esperar respuestas del bot (mensajes FROM bot_id)
print(f"\n⏳ Esperando respuestas del bot (hasta 30 seg)...")
offset = last_update_id + 1
deadline = time.time() + 30
respuestas = []

while time.time() < deadline and len(respuestas) < len(comandos):
    updates = api("getUpdates", offset=offset, limit=20, timeout=5)
    if not updates.get("ok"):
        time.sleep(1)
        continue
    for upd in updates.get("result", []):
        offset = upd["update_id"] + 1
        msg = upd.get("message") or upd.get("edited_message")
        if not msg:
            continue
        sender_id = msg.get("from", {}).get("id")
        text = msg.get("text", "")
        if sender_id == bot_id:
            preview = text[:100].replace("\n", " ")
            print(f"  🤖 Bot respondió: '{preview}...'")
            respuestas.append(text)

if respuestas:
    print(f"\n✅ Bot funciona — {len(respuestas)}/{len(comandos)} respuestas recibidas")
else:
    print("\n⚠️  No se detectaron respuestas del bot en 30 segundos.")
    print("   → Verifica que el servidor esté corriendo: python server/server.py")
    print("   → O abre Telegram directamente y prueba el bot manualmente")
