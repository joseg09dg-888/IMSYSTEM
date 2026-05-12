import sys, re
sys.stdout.reconfigure(encoding='utf-8')

c = open('frontend/index.html', encoding='utf-8').read()
original_len = len(c)

# ─────────────────────────────────────────────
# FIX 1: IDs rotos en JS
# ─────────────────────────────────────────────
# city-input / nicho-input → los IDs reales en p-leads son lf-city / lf-nicho
c = c.replace("getElementById('city-input')", "getElementById('lf-city')")
c = c.replace("getElementById('nicho-input')", "getElementById('lf-nicho')")
print('FIX 1: city-input → lf-city, nicho-input → lf-nicho')

# ─────────────────────────────────────────────
# FIX 2: Agregar clases CSS faltantes
# ─────────────────────────────────────────────
css_nuevo = """
/* ── Agent cards ── */
.agent-card { background:var(--surface2); border:1px solid var(--border); border-radius:12px; padding:20px; display:flex; flex-direction:column; gap:14px; }
.agent-card-name { font-size:15px; font-weight:600; color:var(--white); font-family:var(--fs); }
.agent-card-role { font-size:11px; color:var(--muted); font-family:var(--fm); letter-spacing:.5px; text-transform:uppercase; }
.agent-info { display:flex; align-items:center; gap:12px; }
.agent-stat-row { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-top:4px; }
.agent-stat { background:var(--surface); border-radius:8px; padding:10px 12px; text-align:center; }
.agent-stat-v { font-size:18px; font-weight:700; color:var(--white); font-family:var(--fs); }
.agent-stat-l { font-size:10px; color:var(--muted); font-family:var(--fm); margin-top:2px; }

/* ── Buttons extra ── */
.btn-clear { background:transparent; border:1px solid var(--border); color:var(--muted); padding:6px 12px; border-radius:6px; font-size:12px; cursor:pointer; font-family:var(--fm); transition:all .15s; }
.btn-clear:hover { border-color:var(--white); color:var(--white); }
.btn-danger { background:#7f1d1d; border:1px solid #991b1b; color:#fca5a5; padding:6px 14px; border-radius:6px; font-size:12px; cursor:pointer; font-family:var(--fm); transition:all .15s; }
.btn-danger:hover { background:#991b1b; }

/* ── Stat card decoration ── */
.corner-line { position:absolute; top:0; right:0; width:40px; height:40px; border-top:2px solid var(--green); border-right:2px solid var(--green); border-radius:0 10px 0 0; opacity:.4; }

/* ── Form elements (mercados/marketing) ── */
.form-label { font-size:11px; color:var(--muted); font-family:var(--fm); letter-spacing:.3px; margin-bottom:5px; }
.form-input { width:100%; background:var(--surface2); border:1px solid var(--border); color:var(--white); padding:9px 12px; border-radius:8px; font-size:13px; font-family:var(--fm); box-sizing:border-box; outline:none; transition:border-color .15s; }
.form-input:focus { border-color:rgba(255,255,255,.25); }
.form-input option { background:var(--surface2); }

/* ── Intelligence step dots ── */
.intel-step-dot { width:8px; height:8px; border-radius:50%; background:var(--border); display:inline-block; transition:background .3s; }
.intel-step-dot.done { background:var(--green); }
.intel-step-dot.running { background:var(--yellow); animation:pulse 1s infinite; }

/* ── Lead / sector checkboxes ── */
.lead-cb, .mkt-sector-cb { accent-color:var(--green); width:14px; height:14px; cursor:pointer; }

/* ── Results count ── */
.results-count { font-size:11px; color:var(--muted); font-family:var(--fm); padding:3px 8px; background:var(--surface2); border-radius:20px; }

/* ── Scheduler bars ── */
.schedule-row { display:flex; align-items:center; gap:12px; padding:8px 0; border-bottom:1px solid var(--border); }
.schedule-day { font-size:11px; color:var(--muted); font-family:var(--fm); width:80px; flex-shrink:0; }
.schedule-time { font-size:11px; color:var(--white); font-family:var(--fm); width:90px; flex-shrink:0; }
.schedule-bar { flex:1; background:var(--surface2); border-radius:4px; height:6px; overflow:hidden; }
.schedule-fill { height:100%; background:var(--green); border-radius:4px; transition:width .3s; }

/* ── Search separator ── */
.search-sep { width:1px; height:18px; background:var(--border); flex-shrink:0; }
"""

# Insertar el CSS nuevo antes del cierre de </style>
style_close = c.rfind('</style>')
if style_close < 0:
    print('ERROR: no encontre </style>')
    sys.exit(1)

c = c[:style_close] + css_nuevo + '\n' + c[style_close:]
print(f'FIX 2: {len(css_nuevo):,} chars de CSS añadidos ({len(css_nuevo.strip().splitlines())} reglas)')

# ─────────────────────────────────────────────
# Guardar
# ─────────────────────────────────────────────
open('frontend/index.html', 'w', encoding='utf-8').write(c)
print(f'Guardado: {original_len:,} → {len(c):,} chars')

# Verificación final
c2 = open('frontend/index.html', encoding='utf-8').read()
checks = [
    ("lf-city en JS", "getElementById('lf-city')" in c2),
    ("lf-nicho en JS", "getElementById('lf-nicho')" in c2),
    ("city-input eliminado", "getElementById('city-input')" not in c2),
    ("nicho-input eliminado", "getElementById('nicho-input')" not in c2),
    (".agent-card CSS", ".agent-card {" in c2),
    (".form-input CSS", ".form-input {" in c2),
    (".schedule-row CSS", ".schedule-row {" in c2),
    (".corner-line CSS", ".corner-line {" in c2),
    (".btn-danger CSS", ".btn-danger {" in c2),
    (".results-count CSS", ".results-count {" in c2),
]
print()
print('=== VERIFICACION ===')
all_ok = True
for label, ok in checks:
    status = 'OK' if ok else 'FALLO'
    if not ok: all_ok = False
    print(f'  {status}  {label}')
print()
print('RESULTADO:', 'TODO OK' if all_ok else 'HAY FALLOS')
