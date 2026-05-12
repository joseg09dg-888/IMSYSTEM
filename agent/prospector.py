#!/usr/bin/env python3
"""
IM Prospector Agent - Intelligent Markets
Agente de prospección B2B para IM Music + IM Empresas
Autor: Intelligent Markets | intelligentmarkets@gmail.com
"""

import json
import time
import random
import os
import re
import csv
import smtplib
import argparse
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

# ─────────────────────────────────────────────
# CONFIGURACIÓN CENTRAL
# ─────────────────────────────────────────────

CONFIG = {
    "email": {
        "sender": "intelligentmarkets@gmail.com",
        "name": "Mateo Galvis | Intelligent Markets",
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        # Usa App Password de Google (no tu contraseña normal)
        # Genera en: https://myaccount.google.com/apppasswords
        "password": os.environ.get("IM_EMAIL_PASSWORD", ""),
    },
    "calendly": {
        "music":     "https://cal.com/intelligent-markets-agencia/sello-30min",
        "empresas":  "https://cal.com/intelligent-markets-agencia/30min",
    },
    "brochures": {
        "music":    str(Path(__file__).parent.parent / "brochures" / "im_music_2026.pdf"),
        "empresas": str(Path(__file__).parent.parent / "brochures" / "deck_im_empresas.pdf"),
    },
    "delays": {
        "between_emails": (45, 90),   # segundos entre emails (parecer humano)
        "between_searches": (3, 8),
    },
    "targets": {
        "colombia": ["Medellín", "Bogotá", "Cali", "Barranquilla"],
        "spain":    ["Madrid", "Barcelona", "Valencia", "Sevilla"],
        "mexico":   ["Ciudad de México", "Guadalajara", "Monterrey"],
        "puerto_rico": ["San Juan"],
        "dominican_republic": ["Santo Domingo", "Santiago"],
    }
}

# ─────────────────────────────────────────────
# TEMPLATES DE EMAIL
# ─────────────────────────────────────────────

EMAIL_TEMPLATES = {

    # ── MÚSICA ──────────────────────────────
    "music_sello": {
        "subject": "Tu artista merece más que streams — IM Music 🎵",
        "body": """Hola {nombre},

Vi el trabajo que están haciendo con {empresa} y me llama mucho la atención.

Soy Mateo Galvis, Gerente de Marketing en Intelligent Markets. Trabajamos con artistas y sellos para construir carreras musicales con retorno de inversión real — no solo métricas vacías.

Lo que hacemos diferente:
→ Neurociencia y psicología aplicada al marketing musical
→ Distribución a todas las plataformas de streaming
→ Videos musicales de talla mundial
→ Campañas de ads con resultados medibles
→ Financiamiento para proyectos musicales
→ Conexión con productores e ingenieros de master certificados

Tenemos resultados concretos: campañas con alcance de +200K personas con presupuestos optimizados.

¿Tienes 30 minutos esta semana para conocernos?
👉 Agenda aquí: {cal_link}

También te adjunto nuestro deck completo.

Saludos,
Mateo Galvis
Gerente de Marketing | Intelligent Markets
intelligentmarkets@gmail.com
"""
    },

    "music_manager": {
        "subject": "Llevemos la carrera de tu artista al siguiente nivel 🚀",
        "body": """Hola {nombre},

Te escribo porque vi que manejas artistas en {pais} y creo que podemos ser un aliado estratégico clave.

En IM Music somos más que una agencia — somos tu socio de crecimiento a largo plazo.

Aplicamos neurociencia y psicología del consumidor directamente a las estrategias de posicionamiento de tus artistas. El resultado: fans más comprometidos, más streams genuinos y más ingresos reales.

Nuestros servicios incluyen:
✓ Estrategia de marca y contenido viral
✓ Distribución musical global
✓ Campañas de pauta en Meta y Google con segmentación quirúrgica
✓ Videos musicales de producción mundial
✓ Acceso a financiamiento para proyectos

¿Agendamos una llamada de 30 min esta semana?
📅 {cal_link}

Adjunto nuestro deck de servicios.

Mateo Galvis
IM Music | Intelligent Markets
"""
    },

    # ── EMPRESAS — SALUD ─────────────────────
    "empresa_salud": {
        "subject": "Más pacientes, sin depender del voz a voz — {empresa}",
        "body": """Hola {nombre},

Vi tu consulta/clínica de {especialidad} en {ciudad} y quería contactarte directamente.

Soy Mateo Galvis de Intelligent Markets. Ayudamos a profesionales de la salud a conseguir pacientes nuevos de manera predecible y medible, usando publicidad digital y neurociencia del consumidor.

Esto es lo que logramos para consultorios como el tuyo:
→ Campañas en Facebook e Instagram segmentadas a tu paciente ideal
→ Páginas de aterrizaje altamente persuasivas que convierten
→ Remarketing para recuperar pacientes que visitaron tu página
→ Agentes de IA que responden consultas 24/7

Resultado típico: 886 contactos nuevos con $1.268.167 COP invertidos.

¿Tienes 30 minutos para una llamada sin compromiso?
📅 {cal_link}

Adjunto nuestro brochure con casos reales.

Mateo Galvis
Gerente de Marketing | Intelligent Markets
intelligentmarkets@gmail.com
"""
    },

    "empresa_viajes": {
        "subject": "Más reservas, menos intermediarios — Intelligent Markets",
        "body": """Hola {nombre},

Vi tu agencia de viajes {empresa} y creo que hay una oportunidad enorme que probablemente estás dejando en la mesa.

La mayoría de agencias de viajes en {pais} todavía depende del voz a voz o de Booking. Nosotros ayudamos a agencias como la tuya a generar reservas directas con publicidad digital altamente segmentada.

Lo que hacemos:
✓ Campañas en Meta Ads y Google dirigidas a viajeros con poder adquisitivo
✓ Estrategia de contenido para Instagram y TikTok
✓ Embudos de conversión con página de destino persuasiva
✓ Remarketing para clientes que casi reservaron

¿30 minutos esta semana?
📅 {cal_link}

Con gusto te mostramos casos reales.

Mateo Galvis | Intelligent Markets
intelligentmarkets@gmail.com
"""
    },

    "empresa_seguros": {
        "subject": "Leads de seguros cualificados — {empresa}",
        "body": """Hola {nombre},

Trabajo con agencias y corredores de seguros en {pais} para generar leads de calidad de manera consistente.

En Intelligent Markets usamos neurociencia aplicada al marketing para construir campañas que conectan emocionalmente con el cliente potencial — mucho más efectivo que los anuncios genéricos.

Resultados que hemos logrado:
→ Costo por lead optimizado con segmentación avanzada
→ Campañas de Google Ads para búsquedas de intención de compra
→ Páginas de aterrizaje que convierten visitas en cotizaciones
→ Automatización de seguimiento con IA

¿Te parece bien una llamada de 30 min para explorar opciones?
📅 {cal_link}

Mateo Galvis
Intelligent Markets
"""
    },

    "empresa_autos": {
        "subject": "Más compradores de alta gama para tu concesionario 🚗",
        "body": """Hola {nombre},

Vi {empresa} y me pareció importante contactarlos directamente.

Trabajamos con concesionarios y vendedores de vehículos de alta gama para atraer compradores cualificados — personas con real intención y capacidad de compra.

Nuestra propuesta:
✓ Campañas en Meta e Instagram dirigidas a NSE alto
✓ Contenido visual premium (fotografía y video profesional)
✓ Remarketing a visitantes interesados
✓ Estrategia de branding que transmite exclusividad y confianza
✓ Leads segmentados por ubicación, edad e intereses premium

¿Tienes 30 minutos para ver cómo lo hacemos?
📅 {cal_link}

Mateo Galvis | Intelligent Markets
intelligentmarkets@gmail.com
"""
    },
}

# ─────────────────────────────────────────────
# RESPUESTAS AUTOMÁTICAS
# ─────────────────────────────────────────────

def generate_follow_up(original_lead: dict) -> str:
    """Genera seguimiento si no responde en 5 días"""
    nombre = original_lead.get("nombre", "")
    vertical = original_lead.get("vertical", "empresas")
    cal = CONFIG["calendly"]["music"] if vertical == "music" else CONFIG["calendly"]["empresas"]

    return f"""Hola {nombre},

Te escribí hace unos días y quería hacer un seguimiento rápido.

Entiendo que el tiempo es escaso — por eso quería preguntarte directamente: ¿tiene sentido explorar cómo podemos ayudarte a conseguir más clientes/fans de manera predecible?

Si no es el momento, con gusto lo dejamos para después. Pero si tienes 30 min esta semana, me encantaría mostrarte resultados concretos.

👉 {cal}

Saludos,
Mateo Galvis | Intelligent Markets
"""


def generate_reply_to_interest(lead: dict) -> str:
    """Genera respuesta cuando alguien muestra interés"""
    nombre = lead.get("nombre", "")
    vertical = lead.get("vertical", "empresas")
    cal = CONFIG["calendly"]["music"] if vertical == "music" else CONFIG["calendly"]["empresas"]

    return f"""¡Hola {nombre}!

Me alegra mucho saber de ti 🙌

Para darte información más precisa y personalizada, lo mejor es que hablemos directamente. Tengo disponibilidad esta semana y la próxima.

Puedes agendar en el horario que mejor te convenga aquí:
👉 {cal}

La llamada dura 30 minutos y en ella te mostramos exactamente qué podemos hacer por {lead.get('empresa', 'tu negocio/proyecto')}.

¡Hablamos pronto!

Mateo Galvis
Gerente de Marketing | Intelligent Markets
intelligentmarkets@gmail.com
"""


# ─────────────────────────────────────────────
# ENVÍO DE EMAILS
# ─────────────────────────────────────────────

def send_email(to_email: str, subject: str, body: str, vertical: str, lead_name: str = "") -> bool:
    """Envía email con brochure adjunto"""
    password = CONFIG["email"]["password"]
    if not password:
        print(f"  ⚠️  Sin contraseña de email. Simulating send to {to_email}")
        log_sent(to_email, subject, lead_name, vertical, simulated=True)
        return True

    try:
        msg = MIMEMultipart()
        msg["From"] = f"{CONFIG['email']['name']} <{CONFIG['email']['sender']}>"
        msg["To"] = to_email
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "plain", "utf-8"))

        # Adjuntar brochure
        brochure_path = CONFIG["brochures"].get(vertical)
        if brochure_path and os.path.exists(brochure_path):
            with open(brochure_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            filename = "IM_Music_2026.pdf" if vertical == "music" else "Intelligent_Markets_Brochure.pdf"
            part.add_header("Content-Disposition", f"attachment; filename={filename}")
            msg.attach(part)

        with smtplib.SMTP(CONFIG["email"]["smtp_server"], CONFIG["email"]["smtp_port"]) as server:
            server.starttls()
            server.login(CONFIG["email"]["sender"], password)
            server.sendmail(CONFIG["email"]["sender"], to_email, msg.as_string())

        log_sent(to_email, subject, lead_name, vertical)
        return True

    except Exception as e:
        print(f"  ❌ Error enviando a {to_email}: {e}")
        return False


def log_sent(email: str, subject: str, name: str, vertical: str, simulated: bool = False):
    """Registra email enviado en CSV"""
    log_file = Path(__file__).parent.parent / "logs" / "sent_emails.csv"
    log_file.parent.mkdir(exist_ok=True)

    is_new = not log_file.exists()
    with open(log_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["timestamp", "email", "name", "vertical", "subject", "simulated", "status"])
        writer.writerow([
            datetime.now().isoformat(),
            email, name, vertical, subject,
            "YES" if simulated else "NO",
            "SENT"
        ])


# ─────────────────────────────────────────────
# PROCESADOR DE LEADS DESDE CSV
# ─────────────────────────────────────────────

def process_leads_file(csv_path: str, vertical: str, template_key: str, dry_run: bool = False):
    """
    Procesa un CSV de leads y envía emails.
    
    CSV esperado con columnas:
    nombre, empresa, email, ciudad, pais, especialidad (opcional)
    """
    if not os.path.exists(csv_path):
        print(f"❌ Archivo no encontrado: {csv_path}")
        return

    template = EMAIL_TEMPLATES.get(template_key)
    if not template:
        print(f"❌ Template no encontrado: {template_key}")
        print(f"   Disponibles: {list(EMAIL_TEMPLATES.keys())}")
        return

    cal_link = CONFIG["calendly"]["music"] if vertical == "music" else CONFIG["calendly"]["empresas"]

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        leads = list(reader)

    print(f"\n{'='*55}")
    print(f"  IM PROSPECTOR — {vertical.upper()}")
    print(f"  Template: {template_key}")
    print(f"  Leads a procesar: {len(leads)}")
    print(f"  Modo: {'DRY RUN (sin envío)' if dry_run else '🚀 ENVÍO REAL'}")
    print(f"{'='*55}\n")

    sent = 0
    skipped = 0

    for i, lead in enumerate(leads, 1):
        nombre   = lead.get("nombre", "").strip()
        empresa  = lead.get("empresa", "").strip()
        email    = lead.get("email", "").strip()
        ciudad   = lead.get("ciudad", "").strip()
        pais     = lead.get("pais", "Colombia").strip()
        especialidad = lead.get("especialidad", "salud").strip()

        if not email or "@" not in email:
            print(f"  [{i}/{len(leads)}] ⏭️  Sin email válido: {nombre} ({empresa})")
            skipped += 1
            continue

        # Personalizar template
        subject = template["subject"].format(
            nombre=nombre, empresa=empresa, ciudad=ciudad,
            pais=pais, especialidad=especialidad
        )
        body = template["body"].format(
            nombre=nombre, empresa=empresa, ciudad=ciudad,
            pais=pais, especialidad=especialidad, cal_link=cal_link
        )

        print(f"  [{i}/{len(leads)}] 📧 {nombre} | {empresa} | {email}")

        if dry_run:
            print(f"          [DRY RUN] Subject: {subject[:60]}...")
        else:
            success = send_email(email, subject, body, vertical, nombre)
            if success:
                sent += 1
                print(f"          ✅ Enviado")
                # Pausa humana entre emails
                if i < len(leads):
                    delay = random.uniform(*CONFIG["delays"]["between_emails"])
                    print(f"          ⏳ Esperando {delay:.0f}s...")
                    time.sleep(delay)
            else:
                skipped += 1

    print(f"\n{'='*55}")
    print(f"  ✅ Enviados: {sent}")
    print(f"  ⏭️  Omitidos: {skipped}")
    print(f"  📊 Log: logs/sent_emails.csv")
    print(f"{'='*55}\n")


# ─────────────────────────────────────────────
# GENERADOR DE LEADS DEMO
# ─────────────────────────────────────────────

def create_sample_csv(vertical: str):
    """Crea CSV de ejemplo con estructura correcta"""
    output_dir = Path(__file__).parent.parent / "data"
    output_dir.mkdir(exist_ok=True)

    if vertical == "music":
        rows = [
            {"nombre": "Carlos Restrepo", "empresa": "Sello Urban Colombia", "email": "carlos@urbancoMBIA.com",
             "ciudad": "Medellín", "pais": "Colombia", "especialidad": ""},
            {"nombre": "Ana Rodríguez", "empresa": "ArtistManager PR", "email": "ana@artistmgr.com",
             "ciudad": "San Juan", "pais": "Puerto Rico", "especialidad": ""},
        ]
        filename = "leads_music_sample.csv"
        template = "music_sello"
    else:
        rows = [
            {"nombre": "Dr. Andrés Ospina", "empresa": "Clínica Dental Ospina", "email": "andres@clinicaospina.com",
             "ciudad": "Medellín", "pais": "Colombia", "especialidad": "odontología"},
            {"nombre": "Dra. Laura Gómez", "empresa": "DermaLaura", "email": "laura@derma.co",
             "ciudad": "Bogotá", "pais": "Colombia", "especialidad": "dermatología"},
        ]
        filename = "leads_empresas_sample.csv"
        template = "empresa_salud"

    filepath = output_dir / filename
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["nombre", "empresa", "email", "ciudad", "pais", "especialidad"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"✅ CSV de ejemplo creado: {filepath}")
    print(f"   Template sugerido: {template}")
    return str(filepath)


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="IM Prospector — Agente de prospección B2B de Intelligent Markets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EJEMPLOS:
  # Ver leads de ejemplo y simular envío
  python prospector.py --vertical music --template music_sello --csv data/leads_music_sample.csv --dry-run

  # Envío real
  python prospector.py --vertical empresas --template empresa_salud --csv mis_leads.csv

  # Crear CSV de ejemplo
  python prospector.py --create-sample music

TEMPLATES DISPONIBLES:
  music_sello, music_manager
  empresa_salud, empresa_viajes, empresa_seguros, empresa_autos

VARIABLES DE ENTORNO:
  IM_EMAIL_PASSWORD   App Password de Gmail (generada en myaccount.google.com/apppasswords)
        """
    )

    parser.add_argument("--vertical",       choices=["music", "empresas"], help="Línea de negocio")
    parser.add_argument("--template",       help="Clave del template de email")
    parser.add_argument("--csv",            help="Ruta al CSV de leads")
    parser.add_argument("--dry-run",        action="store_true", help="Simula sin enviar emails")
    parser.add_argument("--create-sample",  metavar="VERTICAL", help="Crea CSV de ejemplo (music/empresas)")
    parser.add_argument("--list-templates", action="store_true", help="Lista todos los templates")

    args = parser.parse_args()

    if args.list_templates:
        print("\n📋 TEMPLATES DISPONIBLES:\n")
        for key, tmpl in EMAIL_TEMPLATES.items():
            print(f"  {key}")
            print(f"    Subject: {tmpl['subject']}")
            print()
        return

    if args.create_sample:
        create_sample_csv(args.create_sample)
        return

    if not all([args.vertical, args.template, args.csv]):
        parser.print_help()
        return

    process_leads_file(args.csv, args.vertical, args.template, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
