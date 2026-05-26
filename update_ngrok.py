
import requests, os, re
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(override=True)

try:
    r = requests.get('http://localhost:4040/api/tunnels', timeout=5)
    tunnels = r.json().get('tunnels', [])
    for t in tunnels:
        url = t.get('public_url', '')
        if 'https' in url:
            print('ngrok URL:', url)
            env = Path('.env').read_text(encoding='utf-8')
            if 'NGROK_URL=' in env:
                env = re.sub(r'NGROK_URL=.*', f'NGROK_URL={url}', env)
            else:
                env += f'\nNGROK_URL={url}'
            Path('.env').write_text(env, encoding='utf-8')
            os.environ['NGROK_URL'] = url

            token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
            if token:
                requests.post(
                    f'https://api.telegram.org/bot{token}/deleteWebhook',
                    json={'drop_pending_updates': True}
                )
                print('Bot usando polling - OK')
            break
except Exception as e:
    print('Error ngrok:', e)
