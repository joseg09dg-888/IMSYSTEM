import re, sys
sys.stdout.reconfigure(encoding='utf-8')

content = open('frontend/index.html', encoding='utf-8').read()

nuevo_panel = r"""<div class="panel" id="p-investigacion">
<div style="padding:28px">
  <div style="font-family:Georgia,serif;font-size:22px;color:white;margin-bottom:6px">Investigacion con 7 Maletas</div>
  <div style="color:#666;font-size:12px;margin-bottom:24px">Datos del negocio para analisis completo + estrategia ADS + plan de contenido</div>

  <div style="display:grid;gap:14px;margin-bottom:20px">
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
      <div>
        <div style="color:#555;font-size:10px;letter-spacing:2px;margin-bottom:5px">NOMBRE DEL NEGOCIO *</div>
        <input id="inv-nombre" placeholder="Clinica Dental Ospina" style="width:100%;background:#111;border:1px solid #222;color:white;padding:10px 13px;border-radius:6px;font-size:13px;outline:none">
      </div>
      <div>
        <div style="color:#555;font-size:10px;letter-spacing:2px;margin-bottom:5px">URL DE LA WEB</div>
        <input id="inv-url" placeholder="https://clinica.com" style="width:100%;background:#111;border:1px solid #222;color:white;padding:10px 13px;border-radius:6px;font-size:13px;outline:none">
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">
      <div>
        <div style="color:#555;font-size:10px;letter-spacing:2px;margin-bottom:5px">INSTAGRAM</div>
        <input id="inv-instagram" placeholder="@negocio" style="width:100%;background:#111;border:1px solid #222;color:white;padding:10px 13px;border-radius:6px;font-size:13px;outline:none">
      </div>
      <div>
        <div style="color:#555;font-size:10px;letter-spacing:2px;margin-bottom:5px">CIUDAD</div>
        <input id="inv-ciudad" value="Medellin" style="width:100%;background:#111;border:1px solid #222;color:white;padding:10px 13px;border-radius:6px;font-size:13px;outline:none">
      </div>
      <div>
        <div style="color:#555;font-size:10px;letter-spacing:2px;margin-bottom:5px">SECTOR/BARRIO</div>
        <input id="inv-sector" placeholder="El Poblado, Envigado" style="width:100%;background:#111;border:1px solid #222;color:white;padding:10px 13px;border-radius:6px;font-size:13px;outline:none">
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
      <div>
        <div style="color:#555;font-size:10px;letter-spacing:2px;margin-bottom:5px">NICHO</div>
        <select id="inv-nicho" style="width:100%;background:#111;border:1px solid #222;color:white;padding:10px 13px;border-radius:6px;font-size:13px">
          <option value="odontologos">Odontologos</option>
          <option value="dermatologo">Dermatologo</option>
          <option value="agencia_viajes">Agencias de Viajes</option>
          <option value="seguros">Seguros</option>
          <option value="autos_alta_gama">Autos Alta Gama</option>
          <option value="sello_musical">Sello Musical</option>
          <option value="artista_independiente">Artista Independiente</option>
          <option value="ecommerce">E-commerce</option>
          <option value="restaurante">Restaurante</option>
          <option value="otro">Otro</option>
        </select>
      </div>
      <div>
        <div style="color:#555;font-size:10px;letter-spacing:2px;margin-bottom:5px">TAMANO EMPRESA</div>
        <select id="inv-tamanio" style="width:100%;background:#111;border:1px solid #222;color:white;padding:10px 13px;border-radius:6px;font-size:13px">
          <option value="pequena">Pequena (1-5 personas)</option>
          <option value="mediana" selected>Mediana (6-20 personas)</option>
          <option value="grande">Grande (20+ personas)</option>
        </select>
      </div>
    </div>
  </div>

  <button id="btn-investigar" onclick="runInv()" style="width:100%;background:white;color:black;border:none;padding:14px;border-radius:7px;font-size:14px;font-weight:700;cursor:pointer;letter-spacing:0.5px">
    INICIAR INVESTIGACION CON 7 MALETAS
  </button>

  <div id="inv-prog" style="display:none;margin-top:20px;background:#0a0a0a;border:1px solid #222;border-radius:8px;padding:20px">
    <div style="color:#fbbf24;font-size:12px;font-family:monospace;margin-bottom:14px" id="inv-log">Iniciando...</div>
    <div style="display:grid;gap:8px">
      <div style="display:flex;align-items:center;gap:10px;font-size:11px;color:#555">
        <span style="width:200px">Web oficial</span>
        <div style="flex:1;height:4px;background:#1a1a1a;border-radius:2px"><div id="ip-web" style="height:100%;background:white;border-radius:2px;width:0%;transition:width 0.5s"></div></div>
        <span id="ip-web-p" style="width:35px;text-align:right;font-family:monospace">0%</span>
      </div>
      <div style="display:flex;align-items:center;gap:10px;font-size:11px;color:#555">
        <span style="width:200px">Google reviews</span>
        <div style="flex:1;height:4px;background:#1a1a1a;border-radius:2px"><div id="ip-rev" style="height:100%;background:white;border-radius:2px;width:0%;transition:width 0.5s"></div></div>
        <span id="ip-rev-p" style="width:35px;text-align:right;font-family:monospace">0%</span>
      </div>
      <div style="display:flex;align-items:center;gap:10px;font-size:11px;color:#555">
        <span style="width:200px">Facebook Ads Library</span>
        <div style="flex:1;height:4px;background:#1a1a1a;border-radius:2px"><div id="ip-ads" style="height:100%;background:white;border-radius:2px;width:0%;transition:width 0.5s"></div></div>
        <span id="ip-ads-p" style="width:35px;text-align:right;font-family:monospace">0%</span>
      </div>
      <div style="display:flex;align-items:center;gap:10px;font-size:11px;color:#555">
        <span style="width:200px">Competidores</span>
        <div style="flex:1;height:4px;background:#1a1a1a;border-radius:2px"><div id="ip-comp" style="height:100%;background:white;border-radius:2px;width:0%;transition:width 0.5s"></div></div>
        <span id="ip-comp-p" style="width:35px;text-align:right;font-family:monospace">0%</span>
      </div>
      <div style="display:flex;align-items:center;gap:10px;font-size:11px;color:#555">
        <span style="width:200px">Analisis 7 Maletas</span>
        <div style="flex:1;height:4px;background:#1a1a1a;border-radius:2px"><div id="ip-mal" style="height:100%;background:white;border-radius:2px;width:0%;transition:width 0.5s"></div></div>
        <span id="ip-mal-p" style="width:35px;text-align:right;font-family:monospace">0%</span>
      </div>
    </div>
  </div>

  <div id="inv-res" style="display:none;margin-top:20px">
    <div style="display:flex;gap:8px;margin-bottom:12px">
      <button onclick="navigator.clipboard.writeText(document.getElementById('inv-txt').value).then(function(){alert('Copiado')})" style="background:#111;color:white;border:1px solid #333;padding:8px 16px;border-radius:6px;cursor:pointer;font-size:12px">Copiar informe</button>
      <button id="btn-descargar-inv" style="background:#111;color:white;border:1px solid #333;padding:8px 16px;border-radius:6px;cursor:pointer;font-size:12px">Descargar TXT</button>
    </div>
    <textarea id="inv-txt" readonly style="width:100%;height:650px;background:#050505;border:1px solid #222;color:#ccc;font-family:monospace;font-size:12px;padding:16px;border-radius:8px;resize:vertical;line-height:1.9"></textarea>
  </div>

  <div style="margin-top:20px;border-top:1px solid #1a1a1a;padding-top:16px">
    <div style="color:#555;font-size:10px;letter-spacing:2px;margin-bottom:10px">INVESTIGACIONES ANTERIORES</div>
    <div id="inv-historial-v2"><div style="color:#444;font-size:12px">Sin investigaciones aun</div></div>
  </div>

</div>
</div>
"""

nuevo = re.sub(
    r'<div class="panel" id="p-investigacion"[^>]*>.*?(?=<div class="panel" id="p-)',
    nuevo_panel + '\n',
    content,
    flags=re.DOTALL
)

open('frontend/index.html', 'w', encoding='utf-8').write(nuevo)

result = open('frontend/index.html', encoding='utf-8').read()
checks = ['inv-nombre', 'btn-investigar', 'inv-prog', 'inv-res', 'inv-txt', 'ip-web', 'ip-mal', 'inv-historial-v2']
for c in checks:
    print(('OK  ' if c in result else 'MISS') + ' ' + c)
print('Total: {:,} chars'.format(len(result)))
