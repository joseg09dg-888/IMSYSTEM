import re, sys
sys.stdout.reconfigure(encoding='utf-8')
c = open('frontend/index.html', encoding='utf-8').read()

nuevo_css = """
:root {
  --bg:      #0A0A0A;
  --surface: #111111;
  --surface2:#1A1A1A;
  --border:  rgba(255,255,255,0.07);
  --border2: rgba(255,255,255,0.12);
  --white:   #FFFFFF;
  --off:     #F0F0F0;
  --muted:   #888888;
  --subtle:  #555555;
  --green:   #4ADE80;
  --yellow:  #FBBF24;
  --red:     #F87171;
  --blue:    #60A5FA;
  --fh: 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif;
  --fb: 'SF Pro Text', -apple-system, BlinkMacSystemFont, sans-serif;
  --fm: 'SF Mono', 'Fira Code', monospace;
  --sidebar: 240px;
  --radius:  12px;
  --radius-sm: 8px;
}

* { margin:0; padding:0; box-sizing:border-box; }
html { scroll-behavior:smooth; }
body {
  background: var(--bg);
  color: var(--off);
  font-family: var(--fb);
  font-size: 14px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
  min-height: 100vh;
}

/* SIDEBAR */
.sidebar {
  position: fixed;
  left:0; top:0; bottom:0;
  width: var(--sidebar);
  background: var(--surface);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  z-index: 200;
  overflow-y: auto;
}

.logo-area {
  padding: 28px 20px 20px;
  border-bottom: 1px solid var(--border);
}

.logo-mark {
  font-size: 24px;
  font-weight: 700;
  color: var(--white);
  letter-spacing: -0.5px;
}

.logo-sub {
  font-size: 10px;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: var(--subtle);
  margin-top: 4px;
  font-family: var(--fm);
}

.nav-section { padding: 16px 0 4px; }

.nav-label {
  font-size: 9px;
  letter-spacing: 2.5px;
  text-transform: uppercase;
  color: var(--subtle);
  padding: 0 16px;
  margin-bottom: 2px;
  font-family: var(--fm);
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 400;
  color: var(--muted);
  border: none;
  background: none;
  width: 100%;
  text-align: left;
  border-radius: 0;
  transition: all 0.15s;
  position: relative;
}

.nav-item:hover { color: var(--white); background: rgba(255,255,255,0.04); }

.nav-item.active {
  color: var(--white);
  font-weight: 500;
  background: rgba(255,255,255,0.06);
}

.nav-item.active::before {
  content: '';
  position: absolute;
  left: 0; top: 6px; bottom: 6px;
  width: 2px;
  background: var(--white);
  border-radius: 0 2px 2px 0;
}

.nav-icon { width: 18px; text-align: center; font-size: 14px; }

.sidebar-bottom {
  margin-top: auto;
  padding: 16px;
  border-top: 1px solid var(--border);
}

.agent-pill {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  margin-bottom: 6px;
  cursor: pointer;
  transition: border-color 0.2s;
}

.agent-pill:hover { border-color: var(--border2); }
.agent-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--subtle); }
.agent-dot.on { background: var(--green); box-shadow: 0 0 8px var(--green); }
.agent-name { font-size: 12px; font-weight: 500; color: var(--white); }
.agent-role { font-size: 10px; color: var(--muted); }

/* MAIN */
.main { margin-left: var(--sidebar); min-height: 100vh; display: flex; flex-direction: column; }

.topbar {
  position: sticky; top:0;
  background: rgba(10,10,10,0.92);
  backdrop-filter: blur(24px);
  border-bottom: 1px solid var(--border);
  padding: 0 32px;
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  z-index: 100;
}

.page-title { font-size: 15px; font-weight: 600; color: var(--white); letter-spacing: -0.2px; }

.topbar-right { display: flex; align-items: center; gap: 10px; }

.status-indicator {
  display: flex; align-items: center; gap: 6px;
  font-size: 11px; color: var(--muted); font-family: var(--fm);
}

.live-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--green);
  animation: pulse 2s infinite;
}

@keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:0.5;transform:scale(0.8)} }

.content { flex:1; padding: 32px; max-width: 1400px; }

/* PANELS */
.panel { display: none; }
.panel.active { display: block; animation: fadeUp 0.2s ease; }
@keyframes fadeUp { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)} }

/* CARDS */
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 24px;
  transition: border-color 0.2s;
}

.card:hover { border-color: var(--border2); }
.card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 18px; }
.card-title { font-size: 14px; font-weight: 600; color: var(--white); letter-spacing: -0.2px; }
.card-subtitle { font-size: 11px; color: var(--muted); margin-top: 2px; }

/* STATS */
.stats-row { display: grid; grid-template-columns: repeat(4,1fr); gap: 14px; margin-bottom: 24px; }

.stat-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px 22px;
  transition: border-color 0.2s;
}

.stat-card:hover { border-color: var(--border2); }
.stat-label { font-size: 10px; letter-spacing: 2px; text-transform: uppercase; color: var(--muted); font-family: var(--fm); margin-bottom: 10px; }
.stat-value { font-size: 36px; font-weight: 700; color: var(--white); line-height: 1; letter-spacing: -1px; }
.stat-sub { font-size: 11px; color: var(--subtle); margin-top: 5px; }

/* GRID */
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 14px; }
.mb-16 { margin-bottom: 16px; }
.mb-24 { margin-bottom: 24px; }

/* BUTTONS */
.btn {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 9px 18px; border-radius: var(--radius-sm);
  font-family: var(--fb); font-size: 13px; font-weight: 500;
  cursor: pointer; border: none; transition: all 0.15s;
  letter-spacing: -0.1px;
}

.btn-primary { background: var(--white); color: #000; }
.btn-primary:hover { background: var(--off); transform: translateY(-1px); }
.btn-primary:active { transform: translateY(0); }
.btn-primary:disabled { background: var(--surface2); color: var(--subtle); cursor: not-allowed; transform: none; }

.btn-outline { background: transparent; color: var(--white); border: 1px solid var(--border2); }
.btn-outline:hover { border-color: rgba(255,255,255,0.3); background: rgba(255,255,255,0.04); }

.btn-ghost { background: var(--surface2); color: var(--muted); border: 1px solid var(--border); }
.btn-ghost:hover { color: var(--white); border-color: var(--border2); }

.btn-green { background: rgba(74,222,128,0.12); color: var(--green); border: 1px solid rgba(74,222,128,0.25); }
.btn-green:hover { background: rgba(74,222,128,0.2); }

.btn-red { background: rgba(248,113,113,0.1); color: var(--red); border: 1px solid rgba(248,113,113,0.2); }
.btn-red:hover { background: rgba(248,113,113,0.18); }

.btn-sm { padding: 6px 13px; font-size: 12px; }
.btn-lg { padding: 13px 28px; font-size: 14px; font-weight: 600; }
.btn-full { width: 100%; justify-content: center; }

/* FORMS */
.form-group { margin-bottom: 14px; }
.form-row { display: grid; gap: 12px; margin-bottom: 14px; }
.form-2 { grid-template-columns: 1fr 1fr; }
.form-3 { grid-template-columns: 1fr 1fr 1fr; }

label {
  font-size: 10px; letter-spacing: 1.5px; text-transform: uppercase;
  color: var(--muted); display: block; margin-bottom: 5px; font-family: var(--fm);
}

input, select, textarea {
  width: 100%;
  background: var(--surface2);
  border: 1px solid var(--border);
  color: var(--white);
  padding: 10px 13px;
  border-radius: var(--radius-sm);
  font-family: var(--fb);
  font-size: 13px;
  outline: none;
  transition: border-color 0.2s, background 0.2s;
}

input:focus, select:focus, textarea:focus {
  border-color: rgba(255,255,255,0.25);
  background: var(--surface);
}

input::placeholder { color: var(--subtle); }
select option { background: var(--surface2); }
textarea { resize: vertical; min-height: 90px; line-height: 1.6; }

/* BADGES */
.badge {
  display: inline-flex; align-items: center;
  padding: 3px 9px; border-radius: 20px;
  font-size: 10px; font-weight: 500;
  letter-spacing: 0.3px; font-family: var(--fm);
}

.badge-white  { background:rgba(255,255,255,0.08); color:var(--white);  border:1px solid rgba(255,255,255,0.12); }
.badge-green  { background:rgba(74,222,128,0.1);   color:var(--green);  border:1px solid rgba(74,222,128,0.2); }
.badge-yellow { background:rgba(251,191,36,0.1);   color:var(--yellow); border:1px solid rgba(251,191,36,0.2); }
.badge-red    { background:rgba(248,113,113,0.1);  color:var(--red);    border:1px solid rgba(248,113,113,0.2); }
.badge-muted  { background:rgba(255,255,255,0.04); color:var(--muted);  border:1px solid var(--border); }
.badge-blue   { background:rgba(96,165,250,0.1);   color:var(--blue);   border:1px solid rgba(96,165,250,0.2); }

/* TABLES */
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
thead th {
  text-align: left; padding: 8px 14px;
  font-size: 9.5px; letter-spacing: 2px; text-transform: uppercase;
  color: var(--subtle); border-bottom: 1px solid var(--border);
  font-family: var(--fm); font-weight: 400;
}
tbody td { padding: 12px 14px; border-bottom: 1px solid rgba(255,255,255,0.03); color: var(--off); }
tbody tr:hover td { background: rgba(255,255,255,0.02); }
tbody tr:last-child td { border-bottom: none; }

/* SEARCH */
.search-bar {
  display: flex; align-items: center; gap: 10px;
  background: var(--surface2); border: 1px solid var(--border);
  border-radius: var(--radius-sm); padding: 9px 14px; margin-bottom: 16px;
}
.search-bar input { background:none; border:none; padding:0; font-size:13px; color:var(--white); flex:1; }
.search-icon { color: var(--subtle); font-size: 15px; }

/* PIPELINE */
.pipeline { display:flex; gap:1px; background:var(--border); border-radius:var(--radius); overflow:hidden; margin-bottom:20px; }
.pipe-stage { flex:1; background:var(--surface); padding:16px 8px; text-align:center; }
.pipe-label { font-size:9px; letter-spacing:2px; text-transform:uppercase; color:var(--subtle); font-family:var(--fm); margin-bottom:5px; }
.pipe-num { font-size:26px; font-weight:700; color:var(--white); line-height:1; }

/* PROGRESS BARS */
.prog-row { display:flex; align-items:center; gap:12px; padding:9px 0; }
.prog-label { font-size:11px; color:var(--muted); width:180px; flex-shrink:0; }
.prog-bar { flex:1; height:4px; background:var(--surface2); border-radius:2px; overflow:hidden; }
.prog-fill { height:100%; background:var(--white); border-radius:2px; transition:width 0.5s ease; }
.prog-pct { font-size:10px; color:var(--subtle); font-family:var(--fm); width:32px; text-align:right; }

/* TERMINAL */
.terminal { background:#050505; border:1px solid var(--border); border-radius:var(--radius); overflow:hidden; }
.term-bar { background:var(--surface2); padding:8px 14px; display:flex; align-items:center; gap:7px; border-bottom:1px solid var(--border); }
.tdot { width:9px; height:9px; border-radius:50%; }
.tr { background:#FF5F57; } .ty { background:#FFBD2E; } .tg { background:#28C840; }
.tname { flex:1; text-align:center; font-size:10px; color:var(--subtle); }
.term-body { padding:16px 18px; font-size:12px; line-height:1.9; color:var(--muted); max-height:280px; overflow-y:auto; font-family:var(--fm); }
.log-ok { color:var(--green); } .log-run { color:var(--yellow); } .log-err { color:var(--red); } .log-info { color:#aaa; }

/* TABS */
.tab-bar { display:flex; gap:2px; background:var(--surface2); border-radius:var(--radius-sm); padding:3px; margin-bottom:20px; border:1px solid var(--border); }
.tab-btn { flex:1; padding:8px 12px; border:none; background:transparent; color:var(--muted); font-size:12px; font-weight:500; cursor:pointer; border-radius:6px; transition:all 0.15s; font-family:var(--fb); }
.tab-btn.active { background:var(--surface); color:var(--white); }
.tab-btn:hover:not(.active) { color:var(--off); }

/* MODALS */
.modal-bg { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.75); z-index:500; align-items:center; justify-content:center; padding:20px; backdrop-filter:blur(4px); }
.modal-bg.open { display:flex; }
.modal { background:var(--surface); border:1px solid var(--border2); border-radius:var(--radius); padding:28px; width:100%; max-width:540px; max-height:90vh; overflow-y:auto; }

/* EMPTY STATE */
.empty-state { text-align:center; padding:60px 20px; color:var(--subtle); }
.empty-icon { font-size:28px; margin-bottom:10px; opacity:0.4; }
.empty-title { font-size:16px; color:var(--muted); margin-bottom:5px; font-weight:500; }
.empty-sub { font-size:12px; }

/* ALERTS */
.alert { padding:12px 16px; border-radius:var(--radius-sm); font-size:13px; margin-bottom:14px; display:flex; gap:10px; align-items:flex-start; }
.alert-info   { background:rgba(255,255,255,0.03); border:1px solid var(--border); color:var(--off); }
.alert-green  { background:rgba(74,222,128,0.06);  border:1px solid rgba(74,222,128,0.15); color:#86efac; }
.alert-yellow { background:rgba(251,191,36,0.06);  border:1px solid rgba(251,191,36,0.15); color:#fde68a; }
.alert-red    { background:rgba(248,113,113,0.06); border:1px solid rgba(248,113,113,0.15); color:#fca5a5; }

/* INV MODULE */
.inv-mod { display:flex; align-items:center; gap:12px; padding:10px 14px; background:var(--surface2); border:1px solid var(--border); border-radius:var(--radius-sm); font-size:12px; color:var(--muted); transition:border-color 0.3s; }
.inv-mod.done    { border-color:rgba(74,222,128,0.3);  color:var(--green); }
.inv-mod.running { border-color:rgba(251,191,36,0.3);  color:var(--yellow); }
.inv-bar { flex:1; height:4px; background:var(--surface); border-radius:2px; overflow:hidden; }
.inv-fill { height:100%; background:var(--white); border-radius:2px; transition:width 0.5s; }
.inv-fill.done    { background:var(--green); }
.inv-fill.running { background:var(--yellow); }
.inv-pct { font-family:var(--fm); font-size:10px; width:32px; text-align:right; }

/* FLUJO PASOS */
.flujo-paso { display:grid; grid-template-columns:36px 1fr auto; gap:0 12px; align-items:center; background:var(--surface2); border:1px solid var(--border); border-radius:var(--radius-sm); padding:13px 16px; transition:border-color 0.2s; }
.flujo-paso[data-estado=running] { border-color:rgba(251,191,36,0.3); }
.flujo-paso[data-estado=done]    { border-color:rgba(74,222,128,0.3); }
.flujo-paso[data-estado=error]   { border-color:rgba(248,113,113,0.3); }
.paso-icon { font-size:18px; text-align:center; }
.paso-titulo { font-size:13px; font-weight:500; color:var(--white); }
.paso-desc { font-size:11px; color:var(--muted); margin-top:2px; }
.paso-badge { padding:3px 9px; border-radius:12px; font-size:10px; font-weight:500; font-family:var(--fm); }
.paso-badge.idle    { background:rgba(255,255,255,0.04); color:var(--muted);   border:1px solid var(--border); }
.paso-badge.running { background:rgba(251,191,36,0.1);  color:var(--yellow);  border:1px solid rgba(251,191,36,0.2); }
.paso-badge.done    { background:rgba(74,222,128,0.1);  color:var(--green);   border:1px solid rgba(74,222,128,0.2); }
.paso-badge.error   { background:rgba(248,113,113,0.1); color:var(--red);     border:1px solid rgba(248,113,113,0.2); }

/* MODULOS INTEL */
.modulo-card { background:var(--surface2); border:1px solid var(--border); border-radius:var(--radius-sm); padding:16px; text-align:center; transition:border-color 0.2s; }
.modulo-card.running { border-color:rgba(251,191,36,0.3); }
.modulo-card.done    { border-color:rgba(74,222,128,0.3); }
.modulo-icon { font-size:22px; margin-bottom:7px; }
.modulo-nombre { font-size:12px; font-weight:600; color:var(--white); }
.modulo-sub { font-size:10px; color:var(--muted); margin-top:2px; }
.modulo-estado { display:inline-block; margin-top:7px; padding:2px 8px; border-radius:10px; font-size:9.5px; font-family:var(--fm); }
.modulo-estado.idle    { background:rgba(255,255,255,0.04); color:var(--muted);  border:1px solid var(--border); }
.modulo-estado.running { background:rgba(251,191,36,0.1);  color:var(--yellow); border:1px solid rgba(251,191,36,0.2); }
.modulo-estado.done    { background:rgba(74,222,128,0.1);  color:var(--green);  border:1px solid rgba(74,222,128,0.2); }

/* INV FORM */
.inv-form-grid { display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-bottom:16px; }
@media (max-width:640px) { .inv-form-grid { grid-template-columns:1fr; } }

/* SCROLL */
::-webkit-scrollbar { width:4px; height:4px; }
::-webkit-scrollbar-track { background:transparent; }
::-webkit-scrollbar-thumb { background:var(--surface2); border-radius:2px; }
::-webkit-scrollbar-thumb:hover { background:var(--subtle); }

hr { border:none; border-top:1px solid var(--border); margin:18px 0; }
.mb-20 { margin-bottom:20px; }
.mb-28 { margin-bottom:28px; }
"""

nuevo = re.sub(r'<style>.*?</style>', '<style>' + nuevo_css + '</style>', c, flags=re.DOTALL, count=1)
open('frontend/index.html', 'w', encoding='utf-8').write(nuevo)
print('CSS reemplazado OK')
print(f'Tamaño nuevo: {len(nuevo):,} bytes')
