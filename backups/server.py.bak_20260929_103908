#!/usr/bin/env python3
"""IM Platform Server v3 — Intelligent Markets (multi-tenant ready)"""
import os, json, csv, sqlite3, subprocess, sys, threading, time
import hmac, hashlib, base64
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

try:
    from flask import Flask, jsonify, request, send_from_directory, send_file
    from flask_cors import CORS
except ImportError:
    os.system(f"{sys.executable} -m pip install flask flask-cors -q")
    from flask import Flask, jsonify, request, send_from_directory, send_file
    from flask_cors import CORS

BASE = Path(__file__).parent.parent

def load_env():
    f = BASE / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if k.strip() and not os.environ.get(k.strip()):
                    os.environ[k.strip()] = v.strip()
load_env()

MODO = os.environ.get("MODO", "interno")   # "interno" | "saas"
SUPERADMIN_EMAIL = "intelligentmarkets@gmail.com"

# ── PLANES Y LÍMITES ─────────────────────────────────────────
PLANES = {
    "esencial":    {"emails_mes": 0,    "agentes": False, "intelligence": False, "precio_cop": 700_000},
    "profesional": {"emails_mes": 2000, "agentes": True,  "intelligence": False, "precio_cop": 3_500_000},
    "premium":     {"emails_mes": 5000, "agentes": True,  "intelligence": True,  "precio_cop": 6_000_000},
}

app = Flask(__name__, static_folder=str(BASE/"frontend"), static_url_path="")
CORS(app)
DB = BASE / "logs" / "platform.db"

# ── JWT MÍNIMO (sin dependencias externas) ───────────────────
def _jwt_encode(payload: dict, exp_hours: int = 168) -> str:
    payload = {**payload, "exp": time.time() + exp_hours * 3600, "iat": time.time()}
    header  = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b"=").decode()
    body    = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    secret  = os.environ.get("JWT_SECRET", "im-internal-secret-2026").encode()
    sig     = hmac.new(secret, f"{header}.{body}".encode(), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    return f"{header}.{body}.{sig_b64}"

def _jwt_decode(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Token malformado")
    header, body, sig = parts
    secret  = os.environ.get("JWT_SECRET", "im-internal-secret-2026").encode()
    expected = base64.urlsafe_b64encode(
        hmac.new(secret, f"{header}.{body}".encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    if not hmac.compare_digest(sig, expected):
        raise ValueError("Firma inválida")
    pad = "=" * (-len(body) % 4)
    payload = json.loads(base64.urlsafe_b64decode(body + pad))
    if payload.get("exp") and time.time() > payload["exp"]:
        raise ValueError("Token expirado")
    return payload

def _hash_password(pwd: str) -> str:
    salt = os.environ.get("JWT_SECRET", "im-salt-2026")
    return hashlib.sha256(f"{salt}{pwd}".encode()).hexdigest()

def _get_org_from_token() -> dict | None:
    """Extrae org del JWT del header Authorization. None en modo interno."""
    if MODO == "interno":
        return {"id": 0, "plan": "premium", "estado": "activo", "email": SUPERADMIN_EMAIL}
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        return None
    try:
        return _jwt_decode(token)
    except Exception:
        return None

def _require_auth():
    """Middleware: retorna (org, None) o (None, error_response)."""
    org = _get_org_from_token()
    if org is None:
        return None, (jsonify({"error": "No autenticado"}), 401)
    return org, None

# ── RATE LIMITING ─────────────────────────────────────────────
_rate_log = defaultdict(list)

# IPs locales — nunca se limitan (desarrollo)
_LOCAL_IPS = {"127.0.0.1", "::1", "localhost"}

def check_rate(ip, limit=2000, window=3600):
    """Rate limit general: 2000 req/hora por IP externa. Localhost ilimitado."""
    if ip in _LOCAL_IPS:
        return True
    now = time.time()
    _rate_log[ip] = [t for t in _rate_log[ip] if now - t < window]
    if len(_rate_log[ip]) >= limit:
        return False
    _rate_log[ip].append(now)
    return True

_rate_post_log = defaultdict(list)

def check_rate_post(ip, limit=200, window=60):
    """Rate limit POST: 200 req/minuto por IP externa. Localhost ilimitado."""
    if ip in _LOCAL_IPS:
        return True
    now = time.time()
    _rate_post_log[ip] = [t for t in _rate_post_log[ip] if now - t < window]
    if len(_rate_post_log[ip]) >= limit:
        return False
    _rate_post_log[ip].append(now)
    return True

def _sanitizar_str_srv(valor, max_len=500):
    """Sanitiza strings de input del servidor antes de usarlos."""
    if not isinstance(valor, str):
        valor = str(valor) if valor is not None else ""
    import re as _re
    valor = _re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', valor)
    return valor[:max_len].strip()

@app.before_request
def _security_checks():
    """Validaciones de seguridad en cada request."""
    ip = request.remote_addr or "0.0.0.0"

    # Rate limit general (localhost siempre pasa)
    if not check_rate(ip):
        return jsonify({"error": "Demasiadas solicitudes. Espera un momento."}), 429

    # Rate limit POST (excluir login, localhost siempre pasa)
    if request.method == "POST" and not request.path.endswith("/login"):
        if not check_rate_post(ip):
            return jsonify({"error": "Demasiadas solicitudes POST. Intenta en un momento."}), 429

    # Validar Content-Type en POST con body
    if request.method == "POST" and request.content_length and request.content_length > 0:
        ct = request.content_type or ""
        if "application/json" not in ct and "multipart/form-data" not in ct and "application/x-www-form-urlencoded" not in ct:
            return jsonify({"error": "Content-Type inválido. Use application/json."}), 415

# ── SECURITY HEADERS ──────────────────────────────────────────
@app.after_request
def security_headers(resp):
    resp.headers["X-Frame-Options"]        = "SAMEORIGIN"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"]        = "strict-origin-when-cross-origin"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Log de request (solo API, no assets)
    if request.path.startswith("/api/"):
        print(f"[{ts}] {request.method} {request.path} → {resp.status_code} | {request.remote_addr}")
    return resp

# ── DECORATOR login_required ──────────────────────────────────
import functools
def login_required(f):
    """Decorator: valida token JWT en modo SaaS, pasa en modo interno."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        org, err = _require_auth()
        if err:
            return err
        return f(*args, **kwargs)
    return decorated

# ── DATABASE ──────────────────────────────────────────────────
def get_db():
    DB.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS organizaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            plan TEXT DEFAULT 'esencial',
            estado TEXT DEFAULT 'trial',
            wompi_subscription_id TEXT,
            fecha_registro TEXT,
            fecha_vencimiento TEXT,
            api_key TEXT UNIQUE
        );
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER DEFAULT 0,
            nombre TEXT, empresa TEXT, email TEXT,
            telefono TEXT, ciudad TEXT, pais TEXT DEFAULT 'Colombia',
            nicho TEXT, vertical TEXT DEFAULT 'empresas',
            url TEXT, instagram TEXT, linkedin TEXT, fuente TEXT DEFAULT 'manual',
            status TEXT DEFAULT 'pendiente', notas TEXT,
            fecha_creacion TEXT, fecha_contacto TEXT);
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER DEFAULT 0,
            nombre_negocio TEXT NOT NULL, nicho TEXT, vertical TEXT DEFAULT 'empresas',
            ciudad TEXT, pais TEXT DEFAULT 'Colombia',
            descripcion TEXT, objetivo TEXT, presupuesto TEXT,
            diferenciador TEXT, canales TEXT, notas TEXT,
            fecha_creacion TEXT, tiene_reporte INTEGER DEFAULT 0,
            reporte_path TEXT, estado TEXT DEFAULT 'activo');
        CREATE TABLE IF NOT EXISTS emails_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER DEFAULT 0,
            agente TEXT, to_email TEXT, to_nombre TEXT,
            empresa TEXT, nicho TEXT, asunto TEXT, tipo INTEGER,
            estado TEXT DEFAULT 'enviado', enviado_at TEXT,
            abierto_at TEXT, respondido_at TEXT);
        CREATE TABLE IF NOT EXISTS campanas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER DEFAULT 0,
            nombre TEXT, agente TEXT, nicho TEXT, tipo INTEGER,
            enviados INTEGER DEFAULT 0, abiertos INTEGER DEFAULT 0,
            respondidos INTEGER DEFAULT 0, estado TEXT DEFAULT 'activa',
            creada_at TEXT);
    """)
    # Migraciones seguras
    migrations = [
        "ALTER TABLE leads ADD COLUMN linkedin TEXT",
        "ALTER TABLE leads ADD COLUMN org_id INTEGER DEFAULT 0",
        "ALTER TABLE emails_log ADD COLUMN abierto_at TEXT",
        "ALTER TABLE emails_log ADD COLUMN respondido_at TEXT",
        "ALTER TABLE emails_log ADD COLUMN org_id INTEGER DEFAULT 0",
        "ALTER TABLE clientes ADD COLUMN org_id INTEGER DEFAULT 0",
        "ALTER TABLE campanas ADD COLUMN org_id INTEGER DEFAULT 0",
        """CREATE TABLE IF NOT EXISTS mercado_jobs (
            id TEXT PRIMARY KEY,
            nicho TEXT, pais TEXT, ciudad TEXT,
            sectores TEXT, barrios TEXT, profundidad TEXT,
            estado TEXT DEFAULT 'pendiente',
            progreso INTEGER DEFAULT 0,
            modulo_actual TEXT DEFAULT '',
            resultado TEXT,
            creado_at TEXT, terminado_at TEXT
        )""",
    ]
    for m in migrations:
        try: conn.execute(m)
        except Exception: pass
    conn.commit(); conn.close()
    _auto_import_csvs()

def _auto_import_csvs():
    import csv as csv_mod
    data_dir = BASE / "data"
    if not data_dir.exists():
        return
    conn = get_db(); cursor = conn.cursor(); total = 0
    for csv_path in sorted(data_dir.glob("*.csv")):
        try:
            content = csv_path.read_text(encoding="utf-8", errors="replace")
            for row in csv_mod.DictReader(content.splitlines()):
                email = (row.get("email") or "").strip()
                if not email or "@" not in email:
                    continue
                if cursor.execute("SELECT id FROM leads WHERE email=?", (email,)).fetchone():
                    continue
                nicho    = row.get("nicho", "")
                vertical = "music" if nicho in ("sello_musical","artista_independiente") else (row.get("vertical") or "empresas")
                cursor.execute(
                    "INSERT INTO leads (nombre,empresa,email,telefono,ciudad,pais,nicho,vertical,url,fuente,status,fecha_creacion) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (row.get("nombre",""), row.get("empresa",""), email, row.get("telefono",""),
                     row.get("ciudad","Medellin"), row.get("pais","Colombia"), nicho, vertical,
                     row.get("url",""), row.get("fuente","csv"), row.get("status","pendiente"), datetime.now().isoformat())
                )
                total += 1
        except Exception:
            pass
    conn.commit(); conn.close()
    if total:
        print(f"  -> Auto-importados {total} leads de CSVs")

_procs = {}

# ── MODO INFO ─────────────────────────────────────────────────
@app.route("/api/modo")
def get_modo():
    return jsonify({"modo": MODO, "version": "3.0"})

# ── AUTH ──────────────────────────────────────────────────────
@app.route("/api/auth/registro", methods=["POST"])
def auth_registro():
    d = request.json or {}
    nombre   = str(d.get("nombre",""))[:200].strip()
    email    = str(d.get("email",""))[:200].strip().lower()
    password = str(d.get("password",""))
    plan     = str(d.get("plan","esencial")).lower()

    if not nombre or not email or not password:
        return jsonify({"ok": False, "error": "nombre, email y password requeridos"}), 400
    if "@" not in email:
        return jsonify({"ok": False, "error": "Email inválido"}), 400
    if plan not in PLANES:
        plan = "esencial"
    if len(password) < 6:
        return jsonify({"ok": False, "error": "Password mínimo 6 caracteres"}), 400

    conn = get_db()
    existe = conn.execute("SELECT id FROM organizaciones WHERE email=?", (email,)).fetchone()
    if existe:
        conn.close()
        return jsonify({"ok": False, "error": "Email ya registrado"}), 409

    pwd_hash = _hash_password(password)
    api_key  = hashlib.sha256(f"{email}{time.time()}".encode()).hexdigest()[:32]
    venc     = (datetime.now() + timedelta(days=14)).isoformat()  # 14 días trial

    conn.execute(
        "INSERT INTO organizaciones (nombre,email,password_hash,plan,estado,fecha_registro,fecha_vencimiento,api_key) VALUES (?,?,?,?,?,?,?,?)",
        (nombre, email, pwd_hash, plan, "trial", datetime.now().isoformat(), venc, api_key)
    )
    conn.commit()
    org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()

    token = _jwt_encode({"org_id": org_id, "email": email, "plan": plan, "nombre": nombre})
    return jsonify({
        "ok": True,
        "token": token,
        "org": {"id": org_id, "nombre": nombre, "email": email, "plan": plan, "estado": "trial"},
        "mensaje": "14 días de prueba gratis — activa tu plan para continuar después del trial"
    })

@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    d = request.json or {}
    email    = str(d.get("email","")).strip().lower()
    password = str(d.get("password",""))

    if not email or not password:
        return jsonify({"ok": False, "error": "email y password requeridos"}), 400

    conn = get_db()
    org = conn.execute("SELECT * FROM organizaciones WHERE email=?", (email,)).fetchone()
    conn.close()

    if not org or org["password_hash"] != _hash_password(password):
        return jsonify({"ok": False, "error": "Credenciales incorrectas"}), 401

    token = _jwt_encode({
        "org_id": org["id"], "email": org["email"],
        "plan": org["plan"], "nombre": org["nombre"],
        "estado": org["estado"]
    })
    return jsonify({
        "ok": True,
        "token": token,
        "org": {
            "id": org["id"], "nombre": org["nombre"], "email": org["email"],
            "plan": org["plan"], "estado": org["estado"],
            "fecha_vencimiento": org["fecha_vencimiento"],
        }
    })

@app.route("/api/auth/perfil")
def auth_perfil():
    if MODO == "interno":
        return jsonify({"modo": "interno", "plan": "premium", "email": SUPERADMIN_EMAIL})
    org = _get_org_from_token()
    if not org:
        return jsonify({"error": "No autenticado"}), 401
    conn = get_db()
    row = conn.execute("SELECT * FROM organizaciones WHERE id=?", (org.get("org_id",0),)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Organización no encontrada"}), 404
    return jsonify(dict(row))

# ── SUPERADMIN ────────────────────────────────────────────────
@app.route("/api/admin/organizaciones")
def admin_organizaciones():
    org = _get_org_from_token()
    if MODO == "saas" and (not org or org.get("email") != SUPERADMIN_EMAIL):
        return jsonify({"error": "Solo superadmin"}), 403
    conn = get_db()
    rows = [dict(r) for r in conn.execute(
        "SELECT id,nombre,email,plan,estado,fecha_registro,fecha_vencimiento FROM organizaciones ORDER BY id DESC"
    ).fetchall()]
    # Métricas por org
    for r in rows:
        oid = r["id"]
        r["leads"]  = conn.execute("SELECT COUNT(*) FROM leads WHERE org_id=?", (oid,)).fetchone()[0]
        r["emails"] = conn.execute("SELECT COUNT(*) FROM emails_log WHERE org_id=?", (oid,)).fetchone()[0]
    total_leads  = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    total_emails = conn.execute("SELECT COUNT(*) FROM emails_log").fetchone()[0]
    total_orgs   = len(rows)
    conn.close()
    return jsonify({
        "organizaciones": rows,
        "metricas_globales": {"total_orgs": total_orgs, "total_leads": total_leads, "total_emails": total_emails}
    })

@app.route("/api/admin/organizaciones/<int:oid>/plan", methods=["PATCH"])
def admin_cambiar_plan(oid):
    org = _get_org_from_token()
    if MODO == "saas" and (not org or org.get("email") != SUPERADMIN_EMAIL):
        return jsonify({"error": "Solo superadmin"}), 403
    d = request.json or {}
    plan   = str(d.get("plan","profesional")).lower()
    estado = str(d.get("estado","activo"))
    dias   = int(d.get("dias", 30))
    if plan not in PLANES:
        return jsonify({"error": "Plan inválido"}), 400
    venc = (datetime.now() + timedelta(days=dias)).isoformat()
    conn = get_db()
    conn.execute("UPDATE organizaciones SET plan=?, estado=?, fecha_vencimiento=? WHERE id=?", (plan, estado, venc, oid))
    conn.commit(); conn.close()
    return jsonify({"ok": True, "plan": plan, "estado": estado, "fecha_vencimiento": venc})

# ── DASHBOARD ─────────────────────────────────────────────────
@app.route("/api/dashboard")
def dashboard():
    conn = get_db()
    tl  = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    lh  = conn.execute("SELECT COUNT(*) FROM leads WHERE date(fecha_creacion)=date('now')").fetchone()[0]
    tc  = conn.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]
    ee  = conn.execute("SELECT COUNT(*) FROM emails_log").fetchone()[0]
    ab  = conn.execute("SELECT COUNT(*) FROM emails_log WHERE estado IN ('abierto','respondido')").fetchone()[0]
    re  = conn.execute("SELECT COUNT(*) FROM emails_log WHERE estado='respondido'").fetchone()[0]
    ru  = conn.execute("SELECT COUNT(*) FROM leads WHERE status='reunion'").fetchone()[0]
    pipeline = {s: conn.execute("SELECT COUNT(*) FROM leads WHERE status=?", (s,)).fetchone()[0]
                for s in ["pendiente","enviado","abierto","respondido","reunion","cliente","cerrado"]}
    nichos    = [dict(r) for r in conn.execute(
        "SELECT nicho, COUNT(*) as total, SUM(CASE WHEN status='reunion' THEN 1 ELSE 0 END) as reuniones FROM leads GROUP BY nicho ORDER BY total DESC"
    ).fetchall()]
    actividad = [dict(r) for r in conn.execute(
        "SELECT agente, to_nombre, empresa, asunto, estado, enviado_at FROM emails_log ORDER BY enviado_at DESC LIMIT 10"
    ).fetchall()]
    conn.close()
    return jsonify({
        "stats": {"total_leads":tl,"leads_hoy":lh,"total_clientes":tc,"emails_enviados":ee,
                  "tasa_apertura":f"{ab/ee*100:.1f}%" if ee else "0%",
                  "tasa_respuesta":f"{re/ee*100:.1f}%" if ee else "0%","reuniones":ru},
        "pipeline": pipeline, "nichos": nichos, "actividad": actividad,
    })

# ── LEADS ─────────────────────────────────────────────────────
@app.route("/api/leads")
def get_leads():
    conn   = get_db()
    pg     = int(request.args.get("page",1))
    pp     = int(request.args.get("per_page",50))
    nicho  = request.args.get("nicho","")
    status = request.args.get("status","")
    ciudad = request.args.get("ciudad","")
    search = request.args.get("search","")
    q, p   = "SELECT * FROM leads WHERE 1=1", []
    if nicho:  q += " AND nicho=?";          p.append(nicho)
    if status: q += " AND status=?";         p.append(status)
    if ciudad: q += " AND ciudad LIKE ?";    p.append(f"%{ciudad}%")
    if search: q += " AND (nombre LIKE ? OR empresa LIKE ? OR email LIKE ? OR telefono LIKE ? OR url LIKE ?)"; p += [f"%{search}%"]*5
    total = conn.execute(q.replace("SELECT *","SELECT COUNT(*)"), p).fetchone()[0]
    leads = [dict(r) for r in conn.execute(q + f" ORDER BY id DESC LIMIT {pp} OFFSET {(pg-1)*pp}", p).fetchall()]
    conn.close()
    return jsonify({"leads": leads, "total": total, "page": pg})

@app.route("/api/leads", methods=["POST"])
def create_lead():
    d       = request.json; conn = get_db()
    nombre  = str(d.get("nombre",""))[:200]
    empresa = str(d.get("empresa",""))[:200]
    email   = str(d.get("email",""))[:200]
    try:
        conn.execute(
            "INSERT OR IGNORE INTO leads (nombre,empresa,email,telefono,ciudad,pais,nicho,vertical,url,instagram,fuente,fecha_creacion) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (nombre, empresa, email, str(d.get("telefono",""))[:50], str(d.get("ciudad",""))[:100],
             str(d.get("pais","Colombia"))[:100], str(d.get("nicho",""))[:100],
             str(d.get("vertical","empresas"))[:50], str(d.get("url",""))[:500],
             str(d.get("instagram",""))[:200], str(d.get("fuente","manual"))[:50],
             datetime.now().isoformat())
        )
        conn.commit(); return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    finally:
        conn.close()

@app.route("/api/leads/<int:lid>", methods=["PATCH"])
def update_lead(lid):
    d = request.json or {}; conn = get_db()
    allowed = {"status","notas","fecha_contacto","nombre","empresa","email","telefono","ciudad","nicho","url","instagram"}
    for k, v in d.items():
        if k in allowed:
            conn.execute(f"UPDATE leads SET {k}=? WHERE id=?", (str(v)[:500], lid))
    conn.commit(); conn.close()
    return jsonify({"ok": True})

@app.route("/api/leads/<int:lid>", methods=["DELETE"])
def delete_lead(lid):
    conn = get_db()
    conn.execute("DELETE FROM leads WHERE id=?", (lid,))
    conn.commit(); conn.close()
    return jsonify({"ok": True})

@app.route("/api/leads/import", methods=["POST"])
def import_leads():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "Sin archivo"}), 400
    f = request.files["file"]
    if not f.filename.lower().endswith(".csv"):
        return jsonify({"ok": False, "error": "Solo archivos .csv"}), 400
    content = f.read().decode("utf-8", errors="ignore")
    reader  = csv.DictReader(content.splitlines()); conn = get_db(); imp = 0
    for row in reader:
        email = str(row.get("email","")).strip()[:200]
        if email and "@" in email:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO leads (nombre,empresa,email,ciudad,pais,nicho,vertical,url,instagram,fuente,fecha_creacion) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (str(row.get("nombre",""))[:200], str(row.get("empresa",""))[:200], email,
                     str(row.get("ciudad",""))[:100], str(row.get("pais","Colombia"))[:100],
                     str(row.get("nicho",""))[:100], str(row.get("vertical","empresas"))[:50],
                     str(row.get("url",""))[:500], str(row.get("instagram",""))[:200],
                     "csv_import", datetime.now().isoformat())
                )
                imp += 1
            except Exception:
                pass
    conn.commit(); conn.close()
    return jsonify({"ok": True, "importados": imp})

# ── CLIENTES ──────────────────────────────────────────────────
@app.route("/api/clientes")
def get_clientes():
    conn          = get_db()
    search        = request.args.get("search","")
    nicho         = request.args.get("nicho","")
    ciudad        = request.args.get("ciudad","")
    estado        = request.args.get("estado","")
    tiene_reporte = request.args.get("tiene_reporte","")
    q, p = "SELECT * FROM clientes WHERE 1=1", []
    if search:        q += " AND (nombre_negocio LIKE ? OR nicho LIKE ? OR ciudad LIKE ?)"; p += [f"%{search}%"]*3
    if nicho:         q += " AND nicho=?";           p.append(nicho)
    if ciudad:        q += " AND ciudad LIKE ?";     p.append(f"%{ciudad}%")
    if estado:        q += " AND estado=?";          p.append(estado)
    if tiene_reporte: q += " AND tiene_reporte=?";  p.append(1 if tiene_reporte=="si" else 0)
    total = conn.execute(q.replace("SELECT *","SELECT COUNT(*)"), p).fetchone()[0]
    c = [dict(r) for r in conn.execute(q + " ORDER BY id DESC", p).fetchall()]
    conn.close()
    return jsonify({"clientes": c, "total": total})

@app.route("/api/clientes", methods=["POST"])
def create_cliente():
    d = request.json; conn = get_db()
    conn.execute(
        "INSERT INTO clientes (nombre_negocio,nicho,vertical,ciudad,pais,descripcion,objetivo,presupuesto,diferenciador,canales,notas,fecha_creacion) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (str(d.get("nombre_negocio",""))[:200], str(d.get("nicho",""))[:100], str(d.get("vertical","empresas"))[:50],
         str(d.get("ciudad",""))[:100], str(d.get("pais","Colombia"))[:100], str(d.get("descripcion",""))[:2000],
         str(d.get("objetivo",""))[:500], str(d.get("presupuesto",""))[:100], str(d.get("diferenciador",""))[:500],
         str(d.get("canales",""))[:500], str(d.get("notas",""))[:2000], datetime.now().isoformat())
    )
    conn.commit()
    cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]; conn.close()
    jp  = BASE / "data" / f"cliente_{cid}.json"; jp.parent.mkdir(exist_ok=True)
    jp.write_text(json.dumps({**d,"id":cid}, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({"ok": True, "id": cid})

@app.route("/api/clientes/<int:cid>/analizar", methods=["POST"])
def analizar_cliente(cid):
    if not check_rate(request.remote_addr):
        return jsonify({"ok": False, "error": "Rate limit excedido"}), 429
    conn = get_db(); c = conn.execute("SELECT * FROM clientes WHERE id=?", (cid,)).fetchone(); conn.close()
    if not c: return jsonify({"ok": False, "error": "No encontrado"}), 404
    jp = BASE / "data" / f"cliente_{cid}.json"
    if not jp.exists(): jp.write_text(json.dumps(dict(c), ensure_ascii=False, indent=2), encoding="utf-8")
    modulos = (request.json or {}).get("modulos", ["investigacion","estrategia","contenido","marca"])
    def run():
        cmd = [sys.executable, str(BASE/"agent"/"intelligence_engine.py"), "--cliente", str(jp), "--modulos"] + modulos
        subprocess.run(cmd, cwd=str(BASE))
        conn2 = get_db(); conn2.execute("UPDATE clientes SET tiene_reporte=1 WHERE id=?", (cid,)); conn2.commit(); conn2.close()
    threading.Thread(target=run, daemon=True).start()
    return jsonify({"ok": True, "status": f"Intelligence Engine iniciado para '{c['nombre_negocio']}'", "modulos": modulos})

@app.route("/api/clientes/<int:cid>/reporte")
def get_reporte_cliente(cid):
    conn = get_db(); c = conn.execute("SELECT nombre_negocio FROM clientes WHERE id=?", (cid,)).fetchone(); conn.close()
    slug    = c[0].lower().replace(" ","-")[:20] if c else str(cid)
    reports = sorted((BASE/"reports").glob(f"im-report-{slug}*.html"), reverse=True)
    if not reports: reports = sorted((BASE/"reports").glob("im-report-*.html"), reverse=True)[:1]
    if reports: return send_file(str(reports[0]))
    return jsonify({"error": "Sin reporte aún"}), 404

@app.route("/api/clientes/<int:cid>/modulos")
def get_modulos_cliente(cid):
    conn = get_db(); c = conn.execute("SELECT nombre_negocio FROM clientes WHERE id=?", (cid,)).fetchone(); conn.close()
    if not c: return jsonify({"ok": False, "error": "No encontrado"}), 404
    slug  = c[0].lower().replace(" ","-")[:20]
    files = sorted((BASE/"reports").glob(f"im-data-{slug}*.json"), reverse=True) if (BASE/"reports").exists() else []
    if not files and (BASE/"reports").exists():
        files = sorted((BASE/"reports").glob("im-data-*.json"), reverse=True)[:1]
    if files:
        try:
            data = json.loads(files[0].read_text(encoding="utf-8"))
            return jsonify({"ok": True, "modulos": data.get("modulos",{}), "archivo": files[0].name})
        except Exception:
            pass
    return jsonify({"ok": False, "modulos": {}, "archivo": None})

# ── CAMPAÑAS ──────────────────────────────────────────────────
@app.route("/api/campanas")
def get_campanas():
    conn = get_db()
    search = request.args.get("search","")
    agente = request.args.get("agente","")
    nicho  = request.args.get("nicho","")
    estado = request.args.get("estado","")
    q, p   = "SELECT * FROM campanas WHERE 1=1", []
    if search: q += " AND (nombre LIKE ? OR agente LIKE ? OR nicho LIKE ?)"; p += [f"%{search}%"]*3
    if agente: q += " AND LOWER(agente)=LOWER(?)"; p.append(agente)
    if nicho:  q += " AND nicho=?"; p.append(nicho)
    if estado: q += " AND estado=?"; p.append(estado)
    total = conn.execute(q.replace("SELECT *","SELECT COUNT(*)"), p).fetchone()[0]
    c = [dict(r) for r in conn.execute(q + " ORDER BY id DESC", p).fetchall()]
    conn.close()
    return jsonify({"campanas": c, "total": total})

@app.route("/api/campanas", methods=["POST"])
def create_campana():
    d = request.json; conn = get_db()
    conn.execute(
        "INSERT INTO campanas (nombre,agente,nicho,tipo,creada_at) VALUES (?,?,?,?,?)",
        (str(d.get("nombre",""))[:200], str(d.get("agente","mateo"))[:50],
         str(d.get("nicho",""))[:100], int(d.get("tipo",1)), datetime.now().isoformat())
    )
    conn.commit(); conn.close()
    return jsonify({"ok": True})

# ── AGENTES ───────────────────────────────────────────────────
@app.route("/api/agentes/estado")
def agentes_estado():
    conn = get_db()
    def agent_stats(key):
        nom = {"mateo":"Mateo","jose":"José"}.get(key, key.capitalize())
        env  = conn.execute("SELECT COUNT(*) FROM emails_log WHERE LOWER(agente)=LOWER(?)", (nom,)).fetchone()[0]
        resp = conn.execute("SELECT COUNT(*) FROM emails_log WHERE LOWER(agente)=LOWER(?) AND estado='respondido'", (nom,)).fetchone()[0]
        meet = conn.execute("SELECT COUNT(*) FROM leads WHERE status='reunion'").fetchone()[0]
        return {"enviados": env, "respuestas": resp, "reuniones": meet}
    ms = agent_stats("mateo"); js = agent_stats("jose")
    conn.close()
    return jsonify({
        "mateo": {"activo": "mateo" in _procs and _procs["mateo"].poll() is None, "nombre": "Mateo Galvis", "rol": "Intelligent Markets", **ms},
        "jose":  {"activo": "jose"  in _procs and _procs["jose"].poll()  is None, "nombre": "José Galvis",  "rol": "IM Music", **js},
    })

@app.route("/api/agentes/<agente>/iniciar", methods=["POST"])
def iniciar_agente(agente):
    if agente not in ["mateo","jose"]: return jsonify({"ok": False}), 400
    if not check_rate(request.remote_addr): return jsonify({"ok": False, "error": "Rate limit"}), 429
    if agente in _procs and _procs[agente].poll() is None: return jsonify({"ok": False, "error": "Ya corriendo"})
    d    = request.json or {}
    cmd  = [sys.executable, str(BASE/"agent"/"im_scheduler.py"), "run", "--agente", agente,
            "--csv", d.get("csv", str(BASE/"data"/"leads_*.csv")), "--tipo", str(d.get("tipo",1)), "--max", str(d.get("max",40))]
    _procs[agente] = subprocess.Popen(cmd, cwd=str(BASE))
    return jsonify({"ok": True, "pid": _procs[agente].pid, "agente": agente})

@app.route("/api/agentes/<agente>/detener", methods=["POST"])
def detener_agente(agente):
    if agente in _procs: _procs[agente].terminate(); del _procs[agente]
    return jsonify({"ok": True})

@app.route("/api/agentes/email-prueba", methods=["POST"])
def email_prueba():
    d = request.json or {}
    agente = str(d.get("agente","mateo"))[:20]
    if agente not in ["mateo","jose"]: return jsonify({"ok": False}), 400
    if not os.environ.get("ANTHROPIC_API_KEY",""):
        return jsonify({"ok": False, "output": "ANTHROPIC_API_KEY no configurada"})
    return jsonify({"ok": True, "output": f"[{agente.upper()}] Listo para enviar"})

@app.route("/api/agentes/log")
def agentes_log():
    lf = BASE / "logs" / "scheduler.log"
    if not lf.exists(): return jsonify({"lineas": []})
    return jsonify({"lineas": lf.read_text(encoding="utf-8", errors="ignore").splitlines()[-50:]})

# ── PROCESO EN VIVO ───────────────────────────────────────────
@app.route("/api/proceso/estado")
def proceso_estado():
    conn = get_db()
    leads_total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    emails_hoy  = conn.execute("SELECT COUNT(*) FROM emails_log WHERE date(enviado_at)=date('now')").fetchone()[0]
    conn.close()
    data_dir = BASE / "data"
    csvs     = [f.name for f in data_dir.glob("leads_*.csv")] if data_dir.exists() else []
    rep_dir  = BASE / "reports"
    reportes = [f.name for f in sorted(rep_dir.glob("*.html"), reverse=True)[:5]] if rep_dir.exists() else []
    procesos = {n: {"activo": p.poll() is None, "pid": p.pid} for n, p in _procs.items()}
    return jsonify({"procesos": procesos, "leads_total": leads_total, "emails_hoy": emails_hoy, "csvs": csvs, "reportes_recientes": reportes})

@app.route("/api/proceso/log/<nombre>")
def proceso_log(nombre):
    safe = nombre.replace("/","").replace("..","").replace("\\","")[:60]
    for f in [BASE/"logs"/f"{safe}.log", BASE/"logs"/f"actividad_{safe}.csv", BASE/"logs"/f"{safe}.csv"]:
        if f.exists():
            lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
            return jsonify({"lineas": lines[-100:], "archivo": f.name})
    return jsonify({"lineas": [], "archivo": None})

# ── INFORMES ──────────────────────────────────────────────────
@app.route("/api/informes")
def get_informes():
    d      = BASE / "reports"; d.mkdir(exist_ok=True)
    search = request.args.get("search","").lower()
    tipo   = request.args.get("tipo","")
    inf    = []
    todos  = sorted(d.glob("*.html"), reverse=True)
    # Primero: investigaciones 7 Maletas (7m-*)
    for f in [x for x in todos if x.name.startswith("7m-")][:20]:
        s = f.stat()
        if search and search not in f.name.lower(): continue
        if tipo and tipo != "7maletas": continue
        inf.append({"nombre": f.name, "ruta": f"/api/informes/{f.name}",
                    "tamanio": f"{s.st_size//1024}KB",
                    "fecha": datetime.fromtimestamp(s.st_mtime).strftime("%d/%m/%Y %H:%M"),
                    "tipo": "7maletas"})
    # Luego: otros informes (mercado, prospecto, cliente)
    for f in [x for x in todos if not x.name.startswith("7m-")][:40]:
        s = f.stat()
        t = "cliente" if "im-report" in f.name else "prospecto"
        if tipo and tipo != t: continue
        if search and search not in f.name.lower(): continue
        inf.append({"nombre": f.name, "ruta": f"/api/informes/{f.name}",
                    "tamanio": f"{s.st_size//1024}KB",
                    "fecha": datetime.fromtimestamp(s.st_mtime).strftime("%d/%m/%Y %H:%M"),
                    "tipo": t})
    return jsonify(inf)

@app.route("/api/informes/<nombre>")
def ver_informe(nombre):
    return send_from_directory(str(BASE/"reports"), nombre)

@app.route("/api/informes/generar", methods=["POST"])
def generar_informe():
    if not check_rate(request.remote_addr): return jsonify({"ok": False, "error": "Rate limit"}), 429
    d       = request.json or {}
    empresa = str(d.get("empresa","Empresa"))[:200]
    import tempfile
    cliente_data = {"nombre_negocio": empresa, "nicho": str(d.get("nicho","general"))[:100],
                    "descripcion": str(d.get("descripcion",""))[:500], "objetivo": str(d.get("objetivo","Atraer más clientes"))[:300],
                    "ciudad": d.get("ciudad","Medellín"), "pais": d.get("pais","Colombia")}
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8", dir=str(BASE/"logs"))
    json.dump(cliente_data, tmp, ensure_ascii=False); tmp.close()
    engine   = BASE / "agent" / "intelligence_engine.py"
    log_file = BASE / "logs" / "informes.log"; log_file.parent.mkdir(exist_ok=True)
    p = subprocess.Popen([sys.executable, str(engine), "--cliente", tmp.name], cwd=str(BASE),
                         stdout=open(str(log_file),"a",encoding="utf-8"), stderr=subprocess.STDOUT)
    _procs[f"informe_{empresa[:20]}"] = p
    return jsonify({"ok": True, "pid": p.pid, "mensaje": f"Generando informe para {empresa}"})

# ── EMAILS LOG ────────────────────────────────────────────────
@app.route("/api/emails-log")
def get_emails_log():
    conn   = get_db()
    pg     = int(request.args.get("page",1))
    pp     = int(request.args.get("per_page",50))
    agente = request.args.get("agente","")
    nicho  = request.args.get("nicho","")
    estado = request.args.get("estado","")
    search = request.args.get("search","")
    q, p   = "SELECT * FROM emails_log WHERE 1=1", []
    if agente: q += " AND LOWER(agente)=LOWER(?)"; p.append(agente)
    if nicho:  q += " AND nicho=?"; p.append(nicho)
    if estado: q += " AND LOWER(estado)=LOWER(?)"; p.append(estado)
    if search: q += " AND (to_email LIKE ? OR empresa LIKE ? OR asunto LIKE ? OR to_nombre LIKE ?)"; p += [f"%{search}%"]*4
    total = conn.execute(q.replace("SELECT *","SELECT COUNT(*)"), p).fetchone()[0]
    rows  = [dict(r) for r in conn.execute(q + f" ORDER BY id DESC LIMIT {pp} OFFSET {(pg-1)*pp}", p).fetchall()]
    conn.close()
    return jsonify({"emails": rows, "total": total, "page": pg})

# ── STATS Y WARMUP ────────────────────────────────────────────
@app.route("/api/stats")
def get_stats():
    conn = get_db()
    ee   = conn.execute("SELECT COUNT(*) FROM emails_log").fetchone()[0]
    ab   = conn.execute("SELECT COUNT(*) FROM emails_log WHERE estado IN ('abierto','respondido')").fetchone()[0]
    re   = conn.execute("SELECT COUNT(*) FROM emails_log WHERE estado='respondido'").fetchone()[0]
    conn.close()
    cf = BASE / "logs" / "warmup_config.json"
    w  = {"dia":1,"max_hoy":20,"emails_enviados_hoy":0,"emails_esta_hora":0,"pausado_por_rebotes":False}
    if cf.exists():
        try:
            raw = json.loads(cf.read_text(encoding="utf-8"))
            w.update(raw)
            if raw.get("inicio_warmup"):
                inicio = datetime.fromisoformat(raw["inicio_warmup"])
                dias   = (datetime.now() - inicio).days + 1
                w["dia"] = dias
                SCHED = {**{d:20 for d in range(1,8)}, **{d:40 for d in range(8,15)},
                         **{d:70 for d in range(15,22)}, **{d:100 for d in range(22,31)}}
                w["max_hoy"] = SCHED.get(dias, 150)
        except Exception: pass
    return jsonify({"enviados":ee,"abiertos":ab,"respondidos":re,"warmup":w})

@app.route("/api/warmup/estado")
def warmup_estado():
    sys.path.insert(0, str(BASE/"agent"))
    try:
        import im_deliverability as _d
        restantes, dia, max_hoy, enviados_hoy = _d.get_max_emails_hoy()
        bounce = _d.check_bounce_rate()
        puede, razon = _d.puede_enviar_ahora()
        cf  = BASE / "logs" / "warmup_config.json"
        cfg = json.loads(cf.read_text(encoding="utf-8")) if cf.exists() else {}
        return jsonify({"dia_warmup":dia,"max_hoy":max_hoy,"enviados_hoy":enviados_hoy,
                        "restantes_hoy":restantes,"puede_enviar":puede,"razon":razon,
                        "pausado_por_rebotes":cfg.get("pausado_por_rebotes",False),
                        "tasa_rebotes":bounce["tasa"],"rebotes_accion":bounce["accion"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/warmup/reset", methods=["POST"])
def warmup_reset():
    sys.path.insert(0, str(BASE/"agent"))
    try:
        import im_deliverability as _d
        cfg = _d.reset_warmup()
        return jsonify({"ok": True, "mensaje": "Warmup reiniciado", "config": cfg})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/scheduler/log")
def scheduler_log():
    lf = BASE / "logs" / "scheduler.log"
    if not lf.exists(): return jsonify({"lineas": []})
    return jsonify({"lineas": lf.read_text(encoding="utf-8", errors="ignore").splitlines()[-50:]})

@app.route("/api/scheduler/config", methods=["GET"])
def scheduler_config_get():
    cf = BASE / "logs" / "warmup_config.json"
    default = {
        "timezone": "America/Bogota",
        "ventana_am_inicio": "08:00",
        "ventana_am_fin": "11:30",
        "ventana_pm_inicio": "14:00",
        "ventana_pm_fin": "17:30",
        "dias_activos": ["lun","mar","mie","jue","vie"],
        "max_emails_dia": 40,
    }
    if cf.exists():
        try:
            raw = json.loads(cf.read_text(encoding="utf-8"))
            default.update(raw)
        except Exception:
            pass
    return jsonify(default)

@app.route("/api/scheduler/config", methods=["POST"])
def scheduler_config_post():
    d   = request.json or {}
    cf  = BASE / "logs" / "warmup_config.json"
    cfg = {}
    if cf.exists():
        try: cfg = json.loads(cf.read_text(encoding="utf-8"))
        except Exception: pass
    allowed = {"ventana_am_inicio","ventana_am_fin","ventana_pm_inicio","ventana_pm_fin",
               "dias_activos","max_emails_dia","inicio_warmup","pausado_por_rebotes"}
    for k, v in d.items():
        if k in allowed:
            cfg[k] = v
    cf.parent.mkdir(exist_ok=True)
    cf.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({"ok": True, "config": cfg})

# ── ALIAS /api/mercados/* → /api/mercado/* (compat) ──────────
@app.route("/api/mercados/lista")
def mercados_lista_alias():
    """Alias for /api/mercado/lista (plural compat)."""
    try:
        import market_researcher as _mr_alias
        return jsonify({"jobs": _mr_alias.lista_jobs()})
    except Exception as e:
        return jsonify({"jobs": [], "error": str(e)})

@app.route("/api/mercados/nichos")
def mercados_nichos_alias():
    """Alias for /api/mercado/nichos (plural compat)."""
    try:
        import market_researcher as _mr_alias2
        return jsonify({
            "nichos": list(_mr_alias2.NICHOS_KEYWORDS.keys()),
            "ciudades": _mr_alias2.CIUDADES_SECTORES,
        })
    except Exception as e:
        return jsonify({"nichos": [], "ciudades": {}, "error": str(e)})

# ── BUSCAR LEADS ──────────────────────────────────────────────
@app.route("/api/scraping/detener", methods=["POST"])
def detener_scraping():
    detenidos = []
    for k in list(_procs.keys()):
        if k.startswith("scraping_"):
            try: _procs[k].terminate()
            except Exception: pass
            del _procs[k]; detenidos.append(k)
    return jsonify({"ok": True, "detenidos": detenidos})

@app.route("/api/buscar-leads/todos", methods=["POST"])
def buscar_leads_todos():
    if not check_rate(request.remote_addr): return jsonify({"ok": False, "error": "Rate limit"}), 429
    d   = request.json or {}
    city          = str(d.get("city","Medellin"))[:100]
    country       = str(d.get("country","Colombia"))[:100]
    max_por_nicho = min(int(d.get("max",30)), 100)
    NICHOS = [
        ("odontologos",          "empresas", "Odontólogos Medellín"),
        ("dermatologo",          "empresas", "Dermatólogos Medellín"),
        ("agencia_viajes",       "empresas", "Agencias de Viajes"),
        ("seguros",              "empresas", "Seguros Colombia"),
        ("autos_alta_gama",      "empresas", "Autos Alta Gama"),
        ("sello_musical",        "music",    "Sellos Musicales"),
        ("artista_independiente","music",    "Artistas Independientes"),
    ]
    pids = {}; ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    for nicho, vertical, label in NICHOS:
        key = f"scraping_{nicho}"
        if key in _procs and _procs[key].poll() is None:
            pids[nicho] = {"pid": _procs[key].pid, "status": "ya_activo", "label": label}; continue
        log_file   = BASE / "logs" / f"scraping_{nicho}_{ts}.log"; log_file.parent.mkdir(exist_ok=True)
        output_csv = BASE / "data" / f"leads_{nicho}_{city}_{ts}.csv"; output_csv.parent.mkdir(exist_ok=True)
        cmd = [sys.executable, str(BASE/"agent"/"lead_finder_v2.py"),
               "--nicho", nicho, "--city", city, "--country", country,
               "--max", str(max_por_nicho), "--output", str(output_csv)]
        with open(str(log_file),"w",encoding="utf-8") as lf:
            lf.write(f"[{datetime.now().isoformat()}] INICIO {nicho}\n")
        p = subprocess.Popen(cmd, cwd=str(BASE), stdout=open(str(log_file),"a",encoding="utf-8"), stderr=subprocess.STDOUT)
        _procs[key] = p
        pids[nicho] = {"pid": p.pid, "status": "iniciado", "label": label, "log": log_file.name}
    return jsonify({"ok": True, "nichos": pids, "mensaje": f"{len(pids)} nichos iniciados", "city": city})

@app.route("/api/buscar-leads/estado-todos")
def estado_todos_nichos():
    NICHOS = ["odontologos","dermatologo","agencia_viajes","seguros","autos_alta_gama","sello_musical","artista_independiente"]
    result = {}
    for nicho in NICHOS:
        key = f"scraping_{nicho}"
        if key in _procs:
            proc = _procs[key]; code = proc.poll()
            result[nicho] = {"activo": code is None, "pid": proc.pid, "finalizado": code is not None, "exitcode": code}
        else:
            result[nicho] = {"activo": False, "pid": None, "finalizado": False, "exitcode": None}
        data_dir = BASE / "data"
        if data_dir.exists():
            csvs = sorted(data_dir.glob(f"leads_{nicho}_*.csv"), reverse=True)
            leads_count = 0
            if csvs:
                try:
                    import csv as _csv
                    with open(str(csvs[0]), encoding="utf-8") as f:
                        leads_count = sum(1 for _ in _csv.DictReader(f))
                except Exception: pass
            result[nicho]["leads_csv"] = leads_count; result[nicho]["csv"] = csvs[0].name if csvs else None
        else:
            result[nicho]["leads_csv"] = 0; result[nicho]["csv"] = None
    return jsonify(result)

@app.route("/api/buscar-leads", methods=["POST"])
def buscar_leads():
    if not check_rate(request.remote_addr): return jsonify({"ok": False, "error": "Rate limit"}), 429
    d     = request.json or {}
    nicho = str(d.get("nicho","odontologos"))[:100]
    city  = str(d.get("city","Medellin"))[:100]
    cmd   = [sys.executable, str(BASE/"agent"/"lead_finder_v2.py"),
             "--nicho", nicho, "--city", city, "--country", str(d.get("country","Colombia"))[:100],
             "--max", str(min(int(d.get("max",30)), 200))]
    if d.get("apollo"): cmd.append("--apollo")
    log_file = BASE / "logs" / f"scraping_{nicho.replace(' ','_')}.log"; log_file.parent.mkdir(exist_ok=True)
    with open(str(log_file),"a",encoding="utf-8") as lf:
        lf.write(f"\n[{datetime.now().isoformat()}] INICIO {nicho} {city}\n")
    p = subprocess.Popen(cmd, cwd=str(BASE), stdout=open(str(log_file),"a",encoding="utf-8"), stderr=subprocess.STDOUT)
    _procs[f"scraping_{nicho}"] = p
    return jsonify({"ok": True, "pid": p.pid, "log": f"scraping_{nicho.replace(' ','_')}"})

# ── MERCADO / INVESTIGACIÓN DE MERCADOS ───────────────────────
try:
    sys.path.insert(0, str(BASE/"agent"))
    import market_researcher as _mr

    @app.route("/api/mercado/investigar", methods=["POST"])
    def mercado_investigar():
        d = request.json or {}
        nicho      = str(d.get("nicho", "odontologos"))[:80]
        pais       = str(d.get("pais", "Colombia"))[:60]
        ciudad     = str(d.get("ciudad", "Medellín"))[:80]
        sectores   = [str(s)[:60] for s in (d.get("sectores") or [])[:10]]
        barrios    = [str(b)[:60] for b in (d.get("barrios") or [])[:10]]
        profundidad = "completa" if d.get("profundidad","completa") == "completa" else "basica"

        if not nicho or not ciudad:
            return jsonify({"ok": False, "error": "nicho y ciudad son requeridos"}), 400

        job_id = _mr.crear_job(nicho, pais, ciudad, sectores, barrios, profundidad)
        return jsonify({"ok": True, "job_id": job_id, "mensaje": f"Investigación iniciada para {nicho} en {ciudad}"})

    @app.route("/api/mercado/estado/<job_id>")
    def mercado_estado(job_id):
        estado = _mr.get_job_estado(job_id)
        if not estado:
            return jsonify({"error": "Job no encontrado"}), 404
        return jsonify(estado)

    @app.route("/api/mercado/reporte/<job_id>")
    def mercado_reporte(job_id):
        reporte = _mr.get_job_reporte(job_id)
        if not reporte:
            return jsonify({"error": "Reporte no encontrado"}), 404
        if reporte.get("estado") != "completado":
            return jsonify({"error": "Investigación aún en curso", "estado": reporte.get("estado"), "progreso": reporte.get("progreso")}), 202
        return jsonify(reporte)

    @app.route("/api/mercado/lista")
    def mercado_lista():
        return jsonify({"jobs": _mr.lista_jobs()})

    @app.route("/api/mercado/nichos")
    def mercado_nichos():
        return jsonify({
            "nichos": list(_mr.NICHOS_KEYWORDS.keys()),
            "ciudades": _mr.CIUDADES_SECTORES,
        })

    @app.route("/api/mercado/informe/<job_id>")
    def mercado_informe(job_id):
        """Genera y retorna el informe HTML del job."""
        reporte = _mr.get_job_reporte(job_id)
        if not reporte:
            return jsonify({"error": "Reporte no encontrado"}), 404
        if reporte.get("estado") != "completado":
            return jsonify({"error": "Investigación aún en curso"}), 202
        data = reporte.get("resultado")
        if not data:
            return jsonify({"error": "Sin datos"}), 404
        rutas = _mr.guardar_informes(data, job_id)
        fmt = request.args.get("fmt", "html")
        if fmt == "txt":
            from flask import Response
            txt = _mr.generar_informe_txt(data)
            return Response(txt, mimetype="text/plain; charset=utf-8",
                            headers={"Content-Disposition": f'attachment; filename="{rutas["txt_filename"]}"'})
        html_path = Path(rutas["html"])
        if html_path.exists():
            return send_file(str(html_path))
        return jsonify({"error": "Error generando HTML"}), 500

    @app.route("/api/mercado/informe-json/<job_id>")
    def mercado_informe_json(job_id):
        """Retorna el informe en formato TXT y rutas de archivos."""
        reporte = _mr.get_job_reporte(job_id)
        if not reporte or reporte.get("estado") != "completado":
            return jsonify({"error": "No disponible"}), 404
        data = reporte.get("resultado")
        if not data:
            return jsonify({"error": "Sin datos"}), 404
        txt   = _mr.generar_informe_txt(data)
        rutas = _mr.guardar_informes(data, job_id)
        return jsonify({"txt": txt, "rutas": rutas})

except Exception as _e:
    print(f"  [WARN] market_researcher.py no cargado: {_e}")

# ── DEEP RESEARCHER / ADS STRATEGIST / CONTENT PLANNER ───────
try:
    sys.path.insert(0, str(Path(__file__).parent.parent / "agent"))
    import deep_researcher as _dr
    import ads_strategist  as _as
    import content_planner as _cp

    # ── Investigación profunda ─────────────────────────────────
    def _modulos_to_progreso(modulos_raw):
        """Map SQLite modulos_detalle keys to JS-expected progreso keys."""
        if isinstance(modulos_raw, str):
            try:
                modulos_raw = __import__('json').loads(modulos_raw)
            except Exception:
                modulos_raw = {}
        m = modulos_raw if isinstance(modulos_raw, dict) else {}
        def _pct(key):
            v = m.get(key, 0)
            if isinstance(v, dict): return int(v.get("progreso", 0))
            return int(v) if isinstance(v, (int, float)) else 0
        analisis_pct = max(_pct("analisis"), _pct("claude"), _pct("reporte"))
        return {
            "maletas":    analisis_pct,
            "estrategia": max(_pct("facebook_ads"), _pct("maps_competidores") // 2),
            "guiones":    max(_pct("academico"), _pct("instagram") // 2),
            "branding":   max(_pct("web"), _pct("maps_negocio") // 2),
            "informe":    _pct("reporte") or analisis_pct,
        }

    def _reporte_to_frontend(reporte):
        """Normalize a deep_researcher reporte dict for frontend consumption."""
        resultado = reporte.get("resultado") or {}
        if isinstance(resultado, str):
            try:
                resultado = __import__('json').loads(resultado)
            except Exception:
                resultado = {}
        analisis_txt = (
            resultado.get("informe_formateado")
            or resultado.get("claude_insights")
            or ""
        )
        if not analisis_txt:
            maletas = resultado.get("7_maletas", {})
            for k, v in maletas.items():
                analisis_txt += f"\n## {k.upper()}\n{__import__('json').dumps(v, ensure_ascii=False, indent=2)}\n"
        nombre = reporte.get("nombre") or reporte.get("nombre_negocio", "")
        return {
            "job_id":  reporte.get("id", ""),
            "nombre":  nombre,
            "nicho":   reporte.get("nicho", ""),
            "ciudad":  reporte.get("ciudad", ""),
            "fecha":   reporte.get("creado_at", ""),
            "estado":  reporte.get("estado", ""),
            "progreso": _modulos_to_progreso(reporte.get("modulos_detalle", {})),
            "html_filename": resultado.get("meta", {}).get("html_filename", ""),
            "datos": {
                "analisis_7maletas": analisis_txt or "Sin analisis (configura ANTHROPIC_API_KEY)",
                "estrategia_ads": (
                    resultado.get("facebook_ads", {}).get("texto", "")
                    if isinstance(resultado.get("facebook_ads"), dict)
                    else ""
                ) or "",
                "guiones": str(resultado.get("guiones") or resultado.get("contenido") or ""),
                "web": resultado.get("web_data", {}),
                "reviews_google": resultado.get("reviews_positivas", []),
            },
        }

    @app.route("/api/investigacion/informe/<job_id>")
    def investigacion_informe(job_id):
        """Sirve el HTML generado por deep_researcher (igual que /api/mercado/informe/)."""
        row = _dr.get_job_reporte(job_id)
        if not row:
            return jsonify({"error": "No encontrado"}), 404
        resultado = row.get("resultado") or {}
        if isinstance(resultado, str):
            try:
                resultado = __import__('json').loads(resultado)
            except Exception:
                resultado = {}
        html_path = resultado.get("meta", {}).get("html_path", "")
        if html_path and Path(html_path).exists():
            return send_file(str(html_path))
        # Regenerar si no existe
        try:
            html = _dr._generar_html_reporte(resultado)
            REPORTS_DIR = Path(__file__).parent.parent / "reports"
            REPORTS_DIR.mkdir(exist_ok=True)
            import re as _re, datetime as _dt
            nombre = row.get("nombre") or row.get("nombre_negocio", "inv")
            slug = _re.sub(r'[^a-z0-9]', '-', nombre.lower())[:30]
            path_html = REPORTS_DIR / f"7m-{slug}-{_dt.datetime.now().strftime('%Y-%m-%d')}.html"
            path_html.write_text(html, encoding="utf-8")
            return send_file(str(path_html))
        except Exception as e:
            return jsonify({"error": f"No se pudo generar el HTML: {e}"}), 500

    @app.route("/api/investigacion/iniciar", methods=["POST"])
    def investigacion_iniciar():
        body      = request.get_json(force=True) or {}
        nombre    = body.get("nombre", "").strip()
        url       = body.get("url", "").strip()
        instagram = body.get("instagram", "").strip()
        ciudad    = body.get("ciudad", "Medellín").strip()
        nicho     = body.get("nicho", "").strip()
        tamanio   = body.get("tamanio", "mediana").strip()
        if not nombre:
            return jsonify({"ok": False, "error": "Nombre requerido"}), 400
        if not nicho:
            nicho = "general"
        job_id = _dr.crear_job(nombre, url, instagram, ciudad, nicho, tamanio)
        return jsonify({"ok": True, "job_id": job_id})

    @app.route("/api/investigacion/estado/<job_id>")
    def investigacion_estado(job_id):
        row = _dr.get_job_reporte(job_id)
        if not row:
            return jsonify({"estado": "no_encontrado", "progreso": {}})
        return jsonify(_reporte_to_frontend(row))

    @app.route("/api/investigacion/reporte/<job_id>")
    def investigacion_reporte(job_id):
        row = _dr.get_job_reporte(job_id)
        if not row:
            return jsonify({"error": "No encontrado"}), 404
        return jsonify(_reporte_to_frontend(row))

    @app.route("/api/investigacion/lista")
    def investigacion_lista():
        jobs = _dr.lista_jobs()
        return jsonify([{
            "job_id": j.get("id", ""),
            "nombre": j.get("nombre") or j.get("nombre_negocio", ""),
            "nicho":  j.get("nicho", ""),
            "fecha":  j.get("creado_at", ""),
            "estado": j.get("estado", ""),
        } for j in jobs])

    # ── Estrategia ADS ────────────────────────────────────────
    @app.route("/api/estrategia/ads", methods=["POST"])
    def estrategia_ads():
        body    = request.get_json(force=True) or {}
        nombre  = body.get("nombre", "").strip()
        nicho   = body.get("nicho", "").strip()
        ciudad  = body.get("ciudad", "Medellín").strip()
        tamanio = body.get("tamanio", "mediana").strip()
        inv_job = body.get("investigacion_job_id", "").strip()
        if not nombre or not nicho:
            return jsonify({"error": "nombre y nicho son obligatorios"}), 400
        job_id = _as.crear_job(nombre, nicho, ciudad, tamanio, inv_job)
        return jsonify({"job_id": job_id, "estado": "pendiente"})

    @app.route("/api/estrategia/ads/estado/<job_id>")
    def estrategia_ads_estado(job_id):
        estado = _as.get_job_estado(job_id)
        if not estado:
            return jsonify({"error": "Job no encontrado"}), 404
        return jsonify(estado)

    @app.route("/api/estrategia/ads/reporte/<job_id>")
    def estrategia_ads_reporte(job_id):
        reporte = _as.get_job_reporte(job_id)
        if not reporte:
            return jsonify({"error": "Job no encontrado"}), 404
        return jsonify(reporte)

    # ── Algoritmo Meta Ads ────────────────────────────────────
    @app.route("/api/estrategia/algoritmo-ads", methods=["POST"])
    def estrategia_algoritmo_ads():
        body   = request.get_json(force=True) or {}
        nicho  = body.get("nicho", "general").strip()
        ppto   = int(body.get("presupuesto", 0))
        job_id = str(__import__("uuid").uuid4())
        result_path = BASE / "logs" / f"algo_ads_{job_id}.json"

        def _run():
            try:
                data = _as._investigar_algoritmo_meta_ads(nicho, ppto)
                result_path.write_text(
                    json.dumps(data, ensure_ascii=False), encoding="utf-8"
                )
            except Exception as e:
                result_path.write_text(
                    json.dumps({"informe": f"Error: {e}", "datos_cuenta": {}}),
                    encoding="utf-8"
                )

        threading.Thread(target=_run, daemon=True).start()
        return jsonify({"job_id": job_id, "estado": "procesando"})

    @app.route("/api/estrategia/algoritmo-ads/<job_id>")
    def estrategia_algoritmo_ads_estado(job_id):
        result_path = BASE / "logs" / f"algo_ads_{job_id}.json"
        if not result_path.exists():
            return jsonify({"estado": "procesando"})
        try:
            data = json.loads(result_path.read_text(encoding="utf-8"))
            return jsonify({"estado": "listo", **data})
        except Exception as e:
            return jsonify({"estado": "error", "informe": str(e)})

    # ── Plan de contenido ─────────────────────────────────────
    @app.route("/api/contenido/plan", methods=["POST"])
    def contenido_plan():
        body    = request.get_json(force=True) or {}
        nombre  = body.get("nombre", "").strip()
        nicho   = body.get("nicho", "").strip()
        ciudad  = body.get("ciudad", "Medellín").strip()
        inv_job = body.get("investigacion_job_id", "").strip()
        if not nombre or not nicho:
            return jsonify({"error": "nombre y nicho son obligatorios"}), 400
        job_id = _cp.crear_job(nombre, nicho, ciudad, inv_job)
        return jsonify({"job_id": job_id, "estado": "pendiente"})

    @app.route("/api/contenido/estado/<job_id>")
    def contenido_estado(job_id):
        estado = _cp.get_job_estado(job_id)
        if not estado:
            return jsonify({"error": "Job no encontrado"}), 404
        return jsonify(estado)

    @app.route("/api/contenido/reporte/<job_id>")
    def contenido_reporte(job_id):
        reporte = _cp.get_job_reporte(job_id)
        if not reporte:
            return jsonify({"error": "Job no encontrado"}), 404
        return jsonify(reporte)

    # ── Proyectos ─────────────────────────────────────────────
    @app.route("/api/proyectos")
    def proyectos_lista():
        return jsonify(_dr.lista_proyectos())

    @app.route("/api/proyectos/<int:proyecto_id>/contexto-completo")
    def proyecto_contexto(proyecto_id):
        proyectos = _dr.lista_proyectos()
        proy = next((p for p in proyectos if p.get("id") == proyecto_id), None)
        if not proy:
            return jsonify({"error": "Proyecto no encontrado"}), 404
        contexto = {"proyecto": proy}
        if proy.get("ultimo_job_id"):
            inv = _dr.get_job_reporte(proy["ultimo_job_id"])
            if inv:
                contexto["investigacion"] = inv
        return jsonify(contexto)

    @app.route("/api/proyectos/<int:proyecto_id>/subir-branding", methods=["POST"])
    def proyecto_subir_branding(proyecto_id):
        if "file" not in request.files:
            return jsonify({"error": "No se envió archivo"}), 400
        f = request.files["file"]
        uploads_dir = BASE / "uploads" / "branding"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        ext = Path(f.filename).suffix if f.filename else ".bin"
        filename = f"branding-{proyecto_id}-{int(datetime.now().timestamp())}{ext}"
        save_path = uploads_dir / filename
        f.save(str(save_path))
        rel_path = f"uploads/branding/{filename}"
        _dr.guardar_proyecto(
            nombre="", nicho="", ciudad="", url="", instagram="",
            tamanio="", branding_path=rel_path, proyecto_id=proyecto_id
        )
        return jsonify({"path": rel_path, "ok": True})

    print("  [OK] deep_researcher / ads_strategist / content_planner cargados")

except Exception as _e:
    print(f"  [WARN] agentes nuevos no cargados: {_e}")

# ── SISTEMA DE ALERTAS ────────────────────────────────────────
try:
    from im_deliverability import (
        escanear_texto_alerta, listar_alertas, monitorear_inbox_alertas
    )

    @app.route("/api/alertas", methods=["GET"])
    def alertas_lista():
        limit = int(request.args.get("limit", 50))
        return jsonify(listar_alertas(limit))

    @app.route("/api/alertas/escanear", methods=["POST"])
    def alertas_escanear():
        body   = request.get_json(force=True) or {}
        texto  = body.get("texto", "")
        asunto = body.get("asunto", "")
        origen = body.get("origen", "api_manual")
        if not texto:
            return jsonify({"error": "texto requerido"}), 400
        resultado = escanear_texto_alerta(texto, asunto=asunto, origen=origen)
        return jsonify(resultado)

    # Start inbox monitor in background on server boot
    monitorear_inbox_alertas(intervalo_min=15)
    print("  [OK] Sistema de alertas activo")

except Exception as _e:
    print(f"  [WARN] Sistema de alertas no cargado: {_e}")

# ── REGISTRAR PAGOS BLUEPRINT ─────────────────────────────────
try:
    sys.path.insert(0, str(Path(__file__).parent))
    from routes.pagos import pagos_bp
    app.register_blueprint(pagos_bp)
except Exception as _e:
    print(f"  [WARN] pagos.py no cargado: {_e}")

# ── ORQUESTADOR ───────────────────────────────────────────────
try:
    from orchestrator import (
        crear_job as _orc_crear, get_estado as _orc_estado,
        get_informe as _orc_informe, aprobar as _orc_aprobar,
        rechazar as _orc_rechazar, lista_jobs as _orc_lista
    )

    @app.route("/api/orquestar/iniciar", methods=["POST"])
    def orc_iniciar():
        body      = request.get_json(force=True) or {}
        nombre    = body.get("nombre", "").strip()
        url       = body.get("url", "")
        instagram = body.get("instagram", "")
        ciudad    = body.get("ciudad", "Medellin")
        nicho     = body.get("nicho", "otro")
        tamanio   = body.get("tamanio", "mediana")
        fase      = body.get("fase", "todas")
        if not nombre:
            return jsonify({"error": "nombre requerido"}), 400
        job_id = _orc_crear(nombre, url, instagram, ciudad, nicho, tamanio, fase)
        return jsonify({"ok": True, "job_id": job_id})

    @app.route("/api/orquestar/estado/<job_id>", methods=["GET"])
    def orc_estado(job_id):
        estado = _orc_estado(job_id)
        if not estado:
            return jsonify({"error": "job no encontrado"}), 404
        return jsonify(estado)

    @app.route("/api/orquestar/informe/<job_id>", methods=["GET"])
    def orc_informe(job_id):
        informe = _orc_informe(job_id)
        if not informe:
            return jsonify({"error": "informe no disponible"}), 404
        return jsonify(informe)

    @app.route("/api/orquestar/aprobar/<job_id>", methods=["POST"])
    def orc_aprobar(job_id):
        body       = request.get_json(force=True) or {}
        comentario = body.get("comentario", "")
        ok, msg    = _orc_aprobar(job_id, comentario)
        if not ok:
            return jsonify({"error": msg}), 400
        return jsonify({"ok": True, "mensaje": msg})

    @app.route("/api/orquestar/rechazar/<job_id>", methods=["POST"])
    def orc_rechazar(job_id):
        body       = request.get_json(force=True) or {}
        comentario = body.get("comentario", "")
        ok, msg    = _orc_rechazar(job_id, comentario)
        if not ok:
            return jsonify({"error": msg}), 400
        return jsonify({"ok": True, "mensaje": msg})

    @app.route("/api/orquestar/lista", methods=["GET"])
    def orc_lista():
        limit = int(request.args.get("limit", 20))
        return jsonify(_orc_lista(limit))

    print("  [OK] Orquestador activo")

except Exception as _e:
    print(f"  [WARN] Orquestador no cargado: {_e}")

# ── PAID MEDIA AUDITOR ────────────────────────────────────────
try:
    sys.path.insert(0, str(BASE / "agent"))
    from paid_media_auditor import (
        crear_job    as _aud_crear,
        get_job_estado  as _aud_estado,
        get_job_reporte as _aud_reporte,
        get_checkpoints as _aud_checkpoints,
    )

    @app.route("/api/auditoria/meta", methods=["POST"])
    @login_required
    def aud_meta_crear():
        datos = request.get_json(force=True) or {}
        if not datos.get("nombre_cuenta"):
            return jsonify({"error": "nombre_cuenta requerido"}), 400
        # Sanear inputs
        datos["nombre_cuenta"] = str(datos.get("nombre_cuenta", ""))[:200]
        datos["nicho"]         = str(datos.get("nicho", "general"))[:100]
        datos["ciudad"]        = str(datos.get("ciudad", "Colombia"))[:100]
        job_id = _aud_crear(datos)
        return jsonify({"ok": True, "job_id": job_id})

    @app.route("/api/auditoria/estado/<job_id>", methods=["GET"])
    @login_required
    def aud_meta_estado(job_id):
        est = _aud_estado(job_id)
        if not est:
            return jsonify({"error": "Job no encontrado"}), 404
        return jsonify(est)

    @app.route("/api/auditoria/reporte/<job_id>", methods=["GET"])
    @login_required
    def aud_meta_reporte(job_id):
        rep = _aud_reporte(job_id)
        if not rep:
            return jsonify({"error": "Reporte no disponible"}), 404
        return jsonify(rep)

    @app.route("/api/auditoria/checkpoints", methods=["GET"])
    @login_required
    def aud_checkpoints():
        return jsonify(_aud_checkpoints())

    print("  [OK] Paid Media Auditor activo")

except Exception as _e:
    print(f"  [WARN] Paid Media Auditor no cargado: {_e}")

# ── TELEGRAM BOT ──────────────────────────────────────────────
try:
    sys.path.insert(0, str(BASE / "agent"))
    from telegram_agent import iniciar_bot, bot_esta_activo, send as _tg_send

    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        iniciar_bot()
        print("  [OK] Bot Telegram activo")
    else:
        print("  [INFO] Telegram: agrega TELEGRAM_BOT_TOKEN al .env para activar el bot")

    @app.route("/api/telegram/estado", methods=["GET"])
    def tg_estado():
        return jsonify({
            "activo": bot_esta_activo(),
            "chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""),
            "token_configurado": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
        })

    @app.route("/api/telegram/send", methods=["POST"])
    def tg_send():
        d = request.get_json(force=True) or {}
        mensaje = str(d.get("mensaje", "")).strip()
        if not mensaje:
            return jsonify({"error": "mensaje requerido"}), 400
        chat_id = d.get("chat_id") or os.environ.get("TELEGRAM_CHAT_ID", "")
        if not chat_id:
            return jsonify({"error": "TELEGRAM_CHAT_ID no configurado"}), 400
        _tg_send(mensaje, chat_id)
        return jsonify({"ok": True})

    @app.route("/api/telegram/configurar", methods=["POST"])
    def tg_configurar():
        d = request.get_json(force=True) or {}
        chat_id = str(d.get("chat_id", "")).strip()
        token   = str(d.get("token", "")).strip()
        if not chat_id and not token:
            return jsonify({"error": "chat_id o token requerido"}), 400

        env_path = BASE / ".env"
        contenido = env_path.read_text(encoding="utf-8") if env_path.exists() else ""

        import re
        if chat_id:
            if "TELEGRAM_CHAT_ID=" in contenido:
                contenido = re.sub(r"TELEGRAM_CHAT_ID=.*", f"TELEGRAM_CHAT_ID={chat_id}", contenido)
            else:
                contenido += f"\nTELEGRAM_CHAT_ID={chat_id}\n"
            os.environ["TELEGRAM_CHAT_ID"] = chat_id

        if token:
            if "TELEGRAM_BOT_TOKEN=" in contenido:
                contenido = re.sub(r"TELEGRAM_BOT_TOKEN=.*", f"TELEGRAM_BOT_TOKEN={token}", contenido)
            else:
                contenido += f"\nTELEGRAM_BOT_TOKEN={token}\n"
            os.environ["TELEGRAM_BOT_TOKEN"] = token

        env_path.write_text(contenido, encoding="utf-8")
        return jsonify({"ok": True, "mensaje": "Configuración guardada. Reinicia el servidor para activar el bot."})

except Exception as _e:
    print(f"  [WARN] Telegram no iniciado: {_e}")

# ── FRONTEND ──────────────────────────────────────────────────
@app.route("/")
@app.route("/<path:path>")
def frontend(path=""):
    f = BASE / "frontend" / (path or "index.html")
    if f.exists() and f.is_file(): return send_file(str(f))
    return send_file(str(BASE / "frontend" / "index.html"))

def _meta_token_renewal_daemon():
    """Renueva el token de Meta automáticamente cuando quedan < 10 días."""
    import threading, time as _time

    def _loop():
        while True:
            try:
                load_env()
                token      = os.environ.get("META_ACCESS_TOKEN", "")
                app_id     = os.environ.get("META_APP_ID", "")
                app_secret = os.environ.get("META_APP_SECRET", "")

                if not (token and app_id and app_secret):
                    _time.sleep(3600)
                    continue

                r = requests.get(
                    "https://graph.facebook.com/debug_token",
                    params={"input_token": token, "access_token": f"{app_id}|{app_secret}"},
                    timeout=10,
                )
                data = r.json().get("data", {})
                expires_at = data.get("expires_at", 0)
                dias = (expires_at - _time.time()) / 86400 if expires_at else 999

                if dias < 10:
                    r2 = requests.get(
                        "https://graph.facebook.com/v19.0/oauth/access_token",
                        params={
                            "grant_type": "fb_exchange_token",
                            "client_id": app_id,
                            "client_secret": app_secret,
                            "fb_exchange_token": token,
                        },
                        timeout=10,
                    )
                    d2 = r2.json()
                    if "access_token" in d2:
                        nuevo = d2["access_token"]
                        env_path = BASE / ".env"
                        env_txt = env_path.read_text(encoding="utf-8")
                        env_txt = re.sub(r"META_ACCESS_TOKEN=.*", f"META_ACCESS_TOKEN={nuevo}", env_txt)
                        env_path.write_text(env_txt, encoding="utf-8")
                        os.environ["META_ACCESS_TOKEN"] = nuevo
                        print(f"[Meta] Token renovado automaticamente ({d2.get('expires_in',0)//86400} dias)")

            except Exception as e:
                print(f"[Meta] Error renovacion: {e}")

            _time.sleep(86400)  # revisar cada 24 horas

    threading.Thread(target=_loop, daemon=True).start()


# ── EMAIL TRACKING ────────────────────────────────────────────
# Pixel 1x1 GIF transparente en base64
_PIXEL_GIF = base64.b64decode(
    "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)

@app.route("/track/open/<token>")
def track_open(token):
    """Pixel de seguimiento para detectar apertura de email."""
    try:
        decoded = base64.b64decode(token + "==").decode("utf-8")
        parts   = decoded.split("|")
        to_email = parts[0] if parts else ""
        agente   = parts[1] if len(parts) > 1 else ""
        empresa  = parts[2] if len(parts) > 2 else ""
        if to_email:
            conn = get_db()
            conn.execute(
                "INSERT INTO email_tracking (to_email, agente, empresa, evento, ip, user_agent) VALUES (?,?,?,?,?,?)",
                (to_email, agente, empresa, "abierto",
                 request.remote_addr, request.user_agent.string[:200])
            )
            conn.execute(
                "UPDATE emails_log SET abierto_at=datetime('now') WHERE to_email=? AND abierto_at IS NULL",
                (to_email,)
            )
            conn.commit()
            conn.close()
    except Exception:
        pass
    resp = make_response(_PIXEL_GIF)
    resp.headers["Content-Type"]  = "image/gif"
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return resp

@app.route("/track/click/<token>")
def track_click(token):
    """Redirect con tracking de click."""
    url = "https://intelligentmarkets.com.co"
    try:
        decoded = base64.b64decode(token + "==").decode("utf-8")
        parts   = decoded.split("|")
        to_email = parts[0] if parts else ""
        url      = parts[3] if len(parts) > 3 else url
        if to_email:
            conn = get_db()
            conn.execute(
                "INSERT INTO email_tracking (to_email, agente, empresa, evento, ip) VALUES (?,?,?,?,?)",
                (to_email, parts[1] if len(parts)>1 else "", parts[2] if len(parts)>2 else "", "click", request.remote_addr)
            )
            conn.commit()
            conn.close()
    except Exception:
        pass
    from flask import redirect
    return redirect(url)

@app.route("/api/tracking/stats")
def tracking_stats():
    """Estadísticas de tracking de emails."""
    conn = get_db()
    stats = {
        "aperturas": conn.execute("SELECT COUNT(DISTINCT to_email) FROM email_tracking WHERE evento='abierto'").fetchone()[0],
        "clicks":    conn.execute("SELECT COUNT(DISTINCT to_email) FROM email_tracking WHERE evento='click'").fetchone()[0],
        "por_agente": dict(conn.execute(
            "SELECT agente, COUNT(*) FROM email_tracking WHERE evento='abierto' GROUP BY agente"
        ).fetchall()),
        "recientes": [dict(zip(['email','agente','evento','fecha'], r))
            for r in conn.execute(
                "SELECT to_email, agente, evento, fecha FROM email_tracking ORDER BY fecha DESC LIMIT 20"
            ).fetchall()],
    }
    conn.close()
    return jsonify(stats)

@app.route("/api/respuestas")
def get_respuestas():
    """Lista de respuestas recibidas a los emails."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT de_email, de_nombre, empresa, asunto, fecha_recibido, procesado FROM respuestas_recibidas ORDER BY fecha_recibido DESC LIMIT 50"
        ).fetchall()
        conn.close()
        return jsonify([dict(zip(['de_email','de_nombre','empresa','asunto','fecha','procesado'], r)) for r in rows])
    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 500

@app.route("/api/imap/leer", methods=["POST"])
def imap_leer():
    """Dispara la lectura de respuestas IMAP."""
    if not check_rate(request.remote_addr):
        return jsonify({"ok": False, "error": "Rate limit"}), 429
    try:
        sys.path.insert(0, str(BASE / "agent"))
        from im_agents import leer_respuestas_imap
        agente = (request.json or {}).get("agente", "mateo")
        encontradas = leer_respuestas_imap(agente_key=agente, max_emails=20)
        return jsonify({"ok": True, "encontradas": len(encontradas), "respuestas": encontradas[:5]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/contenido/algoritmos", methods=["POST"])
def analizar_algoritmos():
    d = request.json or {}
    nicho = d.get("nicho", "general")
    try:
        sys.path.insert(0, str(BASE / "agent"))
        from content_planner import _investigar_algoritmos_redes
        import uuid as _uuid

        job_id = str(_uuid.uuid4())[:8]
        result_path = BASE / f"logs/algoritmos_{job_id}.json"

        def _run():
            try:
                data = _investigar_algoritmos_redes(nicho)
                result_path.write_text(
                    json.dumps({"estado": "listo", **data}, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
            except Exception as ex:
                result_path.write_text(
                    json.dumps({"estado": "error", "error": str(ex)}),
                    encoding="utf-8"
                )

        threading.Thread(target=_run, daemon=True).start()
        return jsonify({"ok": True, "job_id": job_id, "estado": "procesando"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/contenido/algoritmos/<job_id>")
def get_algoritmos(job_id):
    f = BASE / f"logs/algoritmos_{job_id}.json"
    if not f.exists():
        return jsonify({"estado": "procesando"})
    try:
        return jsonify(json.loads(f.read_text(encoding="utf-8")))
    except Exception as e:
        return jsonify({"estado": "error", "error": str(e)})


if __name__ == "__main__":
    init_db()
    _meta_token_renewal_daemon()
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    print(f"\n  IM PLATFORM v3 — http://0.0.0.0:{port}  [MODO: {MODO}]\n")
    app.run(host="0.0.0.0", port=port, debug=debug)
