"""
IM Platform — Wompi Payment Integration
POST /api/pagos/crear    → genera link de pago Wompi
POST /api/pagos/webhook  → recibe confirmación de Wompi
GET  /api/pagos/estado/<org_id>  → estado suscripción
"""
import os, json, hashlib, hmac, time, smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from flask import Blueprint, request, jsonify

pagos_bp = Blueprint("pagos", __name__)

BASE = Path(__file__).parent.parent.parent

PLANES = {
    "esencial":    {"precio_cop": 700_000,   "monto_wompi": 70_000_000,   "label": "Esencial",    "emails_mes": 0,    "agentes": False, "intelligence": False},
    "profesional": {"precio_cop": 3_500_000, "monto_wompi": 350_000_000,  "label": "Profesional", "emails_mes": 2000, "agentes": True,  "intelligence": False},
    "premium":     {"precio_cop": 6_000_000, "monto_wompi": 600_000_000,  "label": "Premium",     "emails_mes": 5000, "agentes": True,  "intelligence": True},
}

def get_db():
    import sqlite3
    DB = BASE / "logs" / "platform.db"
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    return conn

def _wompi_env():
    return {
        "public_key":     os.environ.get("WOMPI_PUBLIC_KEY", ""),
        "private_key":    os.environ.get("WOMPI_PRIVATE_KEY", ""),
        "events_secret":  os.environ.get("WOMPI_EVENTS_SECRET", ""),
        "events_key":     os.environ.get("WOMPI_EVENTS_KEY", ""),
        "env":            os.environ.get("WOMPI_ENV", "production"),
    }

def _wompi_base_url():
    cfg = _wompi_env()
    return "https://sandbox.wompi.co/v1" if cfg["env"] == "sandbox" else "https://production.wompi.co/v1"

def _send_bienvenida(org_email: str, org_nombre: str, plan: str):
    pwd = os.environ.get("IM_EMAIL_PASSWORD", "")
    if not pwd:
        return
    try:
        msg = MIMEMultipart()
        msg["From"] = f"Intelligent Markets <{os.environ.get('IM_EMAIL','intelligentsmarkets@gmail.com')}>"
        msg["To"] = org_email
        msg["Subject"] = f"¡Bienvenido a IM — Plan {plan.capitalize()} activado!"
        cuerpo = f"""Hola {org_nombre},

Tu suscripción al Plan {plan.capitalize()} de Intelligent Markets está activa.

🔑 Accede a tu panel: https://www.intelligentmarkets.com.co
📧 Email: {org_email}

¿Necesitas ayuda? Agenda una llamada:
https://cal.com/intelligent-markets-agencia/30min

— Equipo Intelligent Markets
"""
        msg.attach(MIMEText(cuerpo, "plain", "utf-8"))
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls()
            s.login(os.environ.get("IM_EMAIL","intelligentsmarkets@gmail.com"), pwd)
            s.sendmail(msg["From"], org_email, msg.as_string())
    except Exception:
        pass

@pagos_bp.route("/api/pagos/crear", methods=["POST"])
def crear_pago():
    d = request.json or {}
    plan = str(d.get("plan","")).lower().strip()
    org_id = d.get("org_id")

    if plan not in PLANES:
        return jsonify({"ok": False, "error": f"Plan inválido. Opciones: {list(PLANES.keys())}"}), 400

    if not org_id:
        return jsonify({"ok": False, "error": "org_id requerido"}), 400

    conn = get_db()
    org = conn.execute("SELECT * FROM organizaciones WHERE id=?", (org_id,)).fetchone()
    conn.close()
    if not org:
        return jsonify({"ok": False, "error": "Organización no encontrada"}), 404

    info = PLANES[plan]
    wompi = _wompi_env()

    if not wompi["public_key"]:
        return jsonify({
            "ok": False,
            "error": "Wompi no configurado. Agrega WOMPI_PUBLIC_KEY y WOMPI_PRIVATE_KEY al .env",
            "pendiente": "credenciales_wompi"
        }), 503

    # Generar referencia única
    ref = f"IM-{plan[:3].upper()}-{org_id}-{int(time.time())}"
    base_url = _wompi_base_url()

    # Llamar a Wompi API para crear link de pago
    try:
        import urllib.request as _req
        payload = json.dumps({
            "name":          f"IM Plan {info['label']} — {dict(org)['nombre']}",
            "description":   f"Suscripción mensual Plan {info['label']} — Intelligent Markets",
            "single_use":    True,
            "collect_shipping": False,
            "currency":      "COP",
            "amount_in_cents": info["monto_wompi"],
            "redirect_url":  "https://www.intelligentmarkets.com.co/panel",
        }).encode()

        req = _req.Request(
            f"{base_url}/payment_links",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {wompi['private_key']}",
            },
            method="POST"
        )
        resp = _req.urlopen(req, timeout=15)
        result = json.loads(resp.read().decode())
        link_id = result.get("data", {}).get("id")
        link_url = f"https://checkout.wompi.co/l/{link_id}" if link_id else None

        # Guardar referencia en DB
        conn = get_db()
        conn.execute(
            "UPDATE organizaciones SET wompi_subscription_id=? WHERE id=?",
            (ref, org_id)
        )
        conn.commit(); conn.close()

        return jsonify({
            "ok": True,
            "plan": plan,
            "monto_cop": info["precio_cop"],
            "link_pago": link_url,
            "referencia": ref,
        })
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": f"Error Wompi: {str(e)[:200]}",
            "tip": "Verifica WOMPI_PRIVATE_KEY y WOMPI_ENV en .env"
        }), 500


@pagos_bp.route("/api/pagos/webhook", methods=["POST"])
def webhook_wompi():
    """
    Wompi envía eventos con firma en X-Wompi-Signature.
    Fórmula: SHA256(id + status + amount_in_cents + currency + payment_method_type + integrity_key)
    Docs: https://docs.wompi.co/docs/colombia/eventos/
    """
    wompi    = _wompi_env()
    sig_hdr  = request.headers.get("X-Wompi-Signature", "")
    event    = request.json or {}
    tx       = event.get("data", {}).get("transaction", {})

    # Verificar firma: usa events_key (prod_events_*) si está disponible,
    # si no cae en events_secret (prod_integrity_*)
    verify_key = wompi["events_key"] or wompi["events_secret"]
    if verify_key and sig_hdr and tx:
        concat = (
            str(tx.get("id", "")) +
            str(tx.get("status", "")) +
            str(tx.get("amount_in_cents", "")) +
            str(tx.get("currency", "")) +
            str(tx.get("payment_method_type", "")) +
            verify_key
        )
        expected = hashlib.sha256(concat.encode()).hexdigest()
        if not hmac.compare_digest(sig_hdr, expected):
            return jsonify({"error": "Firma invalida"}), 401

    event = request.json or {}
    event_type = event.get("event", "")
    data = event.get("data", {}).get("transaction", {})

    if event_type == "transaction.updated" and data.get("status") == "APPROVED":
        ref = data.get("reference", "")
        if ref.startswith("IM-"):
            parts = ref.split("-")
            if len(parts) >= 3:
                plan_code = parts[1].lower()
                plan_map = {"ess": "esencial", "pro": "profesional", "pre": "premium"}
                plan = plan_map.get(plan_code, "profesional")
                try:
                    org_id = int(parts[2])
                    venc = (datetime.now() + timedelta(days=30)).isoformat()
                    conn = get_db()
                    conn.execute(
                        "UPDATE organizaciones SET plan=?, estado='activo', fecha_vencimiento=? WHERE id=?",
                        (plan, venc, org_id)
                    )
                    org = conn.execute("SELECT email, nombre FROM organizaciones WHERE id=?", (org_id,)).fetchone()
                    conn.commit(); conn.close()
                    if org:
                        _send_bienvenida(org["email"], org["nombre"], plan)
                except Exception:
                    pass

    return jsonify({"received": True}), 200


@pagos_bp.route("/api/pagos/estado/<int:org_id>")
def estado_pago(org_id):
    conn = get_db()
    org = conn.execute(
        "SELECT id, nombre, email, plan, estado, fecha_registro, fecha_vencimiento, wompi_subscription_id FROM organizaciones WHERE id=?",
        (org_id,)
    ).fetchone()
    conn.close()
    if not org:
        return jsonify({"error": "No encontrado"}), 404

    org_dict = dict(org)
    plan_info = PLANES.get(org_dict.get("plan","esencial"), PLANES["esencial"])

    # Calcular días restantes
    dias_restantes = None
    if org_dict.get("fecha_vencimiento"):
        try:
            venc = datetime.fromisoformat(org_dict["fecha_vencimiento"])
            dias_restantes = (venc - datetime.now()).days
        except Exception:
            pass

    return jsonify({
        **org_dict,
        "plan_info": plan_info,
        "dias_restantes": dias_restantes,
        "activo": org_dict.get("estado") == "activo",
    })


@pagos_bp.route("/api/pagos/planes")
def listar_planes():
    return jsonify({
        plan: {
            "label": info["label"],
            "precio_cop": info["precio_cop"],
            "precio_formato": f"${info['precio_cop']:,.0f}".replace(",","."),
            "emails_mes": info["emails_mes"],
            "agentes": info["agentes"],
            "intelligence": info["intelligence"],
        }
        for plan, info in PLANES.items()
    })


@pagos_bp.route("/api/pagos/activar-manual", methods=["POST"])
def activar_manual():
    """Solo para el superadmin — activar plan sin Wompi (pruebas o pagos offline)."""
    d = request.json or {}
    token = request.headers.get("Authorization","").replace("Bearer ","")
    # Solo intelligentmarkets@gmail.com puede hacer esto
    try:
        from server import _jwt_decode
        payload = _jwt_decode(token)
        if payload.get("email") != "intelligentmarkets@gmail.com":
            return jsonify({"error": "Solo superadmin"}), 403
    except Exception:
        return jsonify({"error": "Token inválido"}), 401

    org_id = d.get("org_id")
    plan   = str(d.get("plan","profesional")).lower()
    dias   = int(d.get("dias", 30))
    if plan not in PLANES:
        return jsonify({"error": "Plan inválido"}), 400

    venc = (datetime.now() + timedelta(days=dias)).isoformat()
    conn = get_db()
    conn.execute(
        "UPDATE organizaciones SET plan=?, estado='activo', fecha_vencimiento=? WHERE id=?",
        (plan, venc, org_id)
    )
    conn.commit(); conn.close()
    return jsonify({"ok": True, "plan": plan, "fecha_vencimiento": venc})
