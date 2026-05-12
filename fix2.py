import sys, re
sys.stdout.reconfigure(encoding='utf-8')

c = open('frontend/index.html', encoding='utf-8').read()
original = len(c)

# ─────────────────────────────────────────────────────────
# FIX 1: CSS faltante — agent-avatar y lead-cb
# ─────────────────────────────────────────────────────────
css_extra = """
/* ── Agent avatar ── */
.agent-avatar {
  width: 44px; height: 44px; border-radius: 50%;
  background: linear-gradient(135deg, var(--green), #22c55e);
  color: #000; font-weight: 700; font-size: 18px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; font-family: var(--fh);
}

/* ── Lead checkbox ── */
.lead-cb { accent-color: var(--green); width: 14px; height: 14px; cursor: pointer; }
"""

style_close = c.rfind('</style>')
c = c[:style_close] + css_extra + '\n' + c[style_close:]
print('FIX 1: CSS agent-avatar y lead-cb añadidos')

# ─────────────────────────────────────────────────────────
# FIX 2: Null-safety en funciones JS que referencian IDs
#         que ya no existen en el HTML actual
# ─────────────────────────────────────────────────────────

# invCargarLista — se llama al navegar a 'investigacion'
# Usa inv-lista que no existe → TypeError
old_lista = """async function invCargarLista() {
  const token = localStorage.getItem('im_token') || '';
  const res = await fetch(`${API}/api/investigacion/lista`, {headers:{'Authorization':'Bearer '+token}});
  const jobs = await res.json();
  const box = document.getElementById('inv-lista');
  if (!jobs.length) { box.innerHTML = '<div style="color:#86868b;font-size:.9rem">Sin investigaciones prev"""

new_lista_check = """async function invCargarLista() {
  const token = localStorage.getItem('im_token') || '';
  const res = await fetch(`${API}/api/investigacion/lista`, {headers:{'Authorization':'Bearer '+token}});
  const jobs = await res.json();
  const box = document.getElementById('inv-lista');
  if (!box) return; // elemento puede no existir en esta version del panel
  if (!jobs.length) { box.innerHTML = '<div style="color:#86868b;font-size:.9rem">Sin investigaciones prev"""

if old_lista in c:
    c = c.replace(old_lista, new_lista_check, 1)
    print('FIX 2a: null-check añadido a invCargarLista')
else:
    # Buscar solo la linea critica
    idx = c.find("const box = document.getElementById('inv-lista')")
    if idx > 0:
        old_line = "const box = document.getElementById('inv-lista');\n  if (!jobs.length)"
        new_line = "const box = document.getElementById('inv-lista');\n  if (!box) return;\n  if (!jobs.length)"
        c = c.replace(old_line, new_line, 1)
        print('FIX 2a: null-check añadido a invCargarLista (linea exacta)')
    else:
        print('WARN 2a: no encontre invCargarLista para parchear')

# invPollJob — usa inv-progress-pct, inv-modulo-actual, inv-modulos-list, inv-btn, inv-ver-btn
# Agregar null-checks en las asignaciones criticas
old_poll_pct = "document.getElementById('inv-progress-pct').textContent = (d.progreso||0) + '%';"
new_poll_pct = "const _pct=document.getElementById('inv-progress-pct'); if(_pct) _pct.textContent=(d.progreso||0)+'%';"
if old_poll_pct in c:
    c = c.replace(old_poll_pct, new_poll_pct, 1)
    print('FIX 2b: null-check inv-progress-pct')

old_poll_mod = "document.getElementById('inv-modulo-actual').textContent = d.modulo_actual || '';"
new_poll_mod = "const _mod=document.getElementById('inv-modulo-actual'); if(_mod) _mod.textContent=d.modulo_actual||'';"
if old_poll_mod in c:
    c = c.replace(old_poll_mod, new_poll_mod, 1)
    print('FIX 2c: null-check inv-modulo-actual')

old_poll_mlist = "document.getElementById('inv-modulos-list').innerHTML = invModuloHtml(detParsed);"
new_poll_mlist = "const _ml=document.getElementById('inv-modulos-list'); if(_ml) _ml.innerHTML=invModuloHtml(detParsed);"
if old_poll_mlist in c:
    c = c.replace(old_poll_mlist, new_poll_mlist, 1)
    print('FIX 2d: null-check inv-modulos-list')

old_poll_btn = "document.getElementById('inv-btn').disabled = false;\n      document.getElementById('inv-btn').textContent = 'Iniciar Investigación';"
new_poll_btn = "const _ib=document.getElementById('inv-btn'); if(_ib){_ib.disabled=false;_ib.textContent='Iniciar Investigación';}"
if old_poll_btn in c:
    c = c.replace(old_poll_btn, new_poll_btn, 1)
    print('FIX 2e: null-check inv-btn')

old_poll_ver = "document.getElementById('inv-ver-btn').style.display = 'inline-block';\n        document.getElementById('inv-ver-btn').onclick = () => invVerReporte(jobId);"
new_poll_ver = "const _vb=document.getElementById('inv-ver-btn'); if(_vb){_vb.style.display='inline-block';_vb.onclick=()=>invVerReporte(jobId);}"
if old_poll_ver in c:
    c = c.replace(old_poll_ver, new_poll_ver, 1)
    print('FIX 2f: null-check inv-ver-btn')

old_inv_btn2 = "const btn = document.getElementById('inv-btn');\n  btn.disabled = true; btn.textContent = 'Iniciando...';"
new_inv_btn2 = "const btn = document.getElementById('inv-btn'); if(btn){btn.disabled=true;btn.textContent='Iniciando...';}"
if old_inv_btn2 in c:
    c = c.replace(old_inv_btn2, new_inv_btn2, 1)
    print('FIX 2g: null-check inv-btn en invIniciar')

old_inv_pbox = "document.getElementById('inv-progress-box').style.display = 'block';"
new_inv_pbox = "const _pb=document.getElementById('inv-progress-box'); if(_pb) _pb.style.display='block';"
if old_inv_pbox in c:
    c = c.replace(old_inv_pbox, new_inv_pbox, 1)
    print('FIX 2h: null-check inv-progress-box')

# ─────────────────────────────────────────────────────────
# Guardar
# ─────────────────────────────────────────────────────────
open('frontend/index.html', 'w', encoding='utf-8').write(c)
print(f'\nGuardado: {original:,} → {len(c):,} chars')

# Verificación
c2 = open('frontend/index.html', encoding='utf-8').read()
checks = [
    ('agent-avatar CSS', '.agent-avatar {' in c2),
    ('lead-cb CSS', '.lead-cb {' in c2 or "lead-cb { accent" in c2),
    ('invCargarLista null-safe', "if (!box) return;" in c2),
    ('inv-progress-pct null-safe', "const _pct=" in c2),
    ('inv-modulo-actual null-safe', "const _mod=" in c2),
    ('--dark definido', '--dark:' in c2),
    ('--ink definido', '--ink:' in c2),
    ('--fs definido', '--fs:' in c2),
]
print()
print('=== VERIFICACION ===')
all_ok = True
for label, ok in checks:
    if not ok: all_ok = False
    print(f'  {"OK" if ok else "FALLO"}  {label}')
print('RESULTADO:', 'TODO OK' if all_ok else 'HAY FALLOS')
