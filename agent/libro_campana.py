#!/usr/bin/env python3
"""
CAMPAÑA PARALELA DEL LIBRO — "Music Business Para Todos Los Humanos" (Hotmart).

Propuesta a sellos, managers y agencias de booking: copia digital gratis y, si lo
recomiendan con su link de afiliado, 70% de cada venta (~$10,31 USD por copia,
cifra neta ya corregida en docs/libro/estrategia_email_artistas_afiliados.md).
Oferta de riesgo cero: es mucho mas facil decir "si" que a un servicio de $1,000+.

Cuenta remitente: IM Music (José). Plantilla = version corta de la estrategia.
Un solo seguimiento a los 6 dias si no respondio. No repite: data/libro_enviados.csv.
Nunca escribe a quien ya fue contactado por el sistema (memoria) salvo --a-contactados.

Uso:  python agent/libro_campana.py --max 10
      python agent/libro_campana.py --dry-run
"""
import argparse, csv, email, imaplib, random, re, sys, time
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import im_agents                                  # noqa: E402
import im_deliverability as deliv                 # noqa: E402
from session_memory import MemoriaAgentes         # noqa: E402

BASE = Path(__file__).parent.parent
MUSICA = BASE / "data" / "MAESTRO_leads_musica.csv"
ENVIADOS = BASE / "data" / "libro_enviados.csv"
_FALLOS = 0
DIAS_SEGUIMIENTO = 6
EXCLUIR_NOMBRE = ("tienda", "store", "vinyl", "vinilo", "almacén", "almacen", "teatro", "discotienda",
                  "hidental", "vion music", "kapital music")
MAL_DOMINIO = ("mysite.com", "example.", "domain.com", "email.com")
EMAIL_OK = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

ASUNTOS = [
    "Una propuesta sin inversión para {empresa}",
    "Libro de music business — 70% de comisión para {empresa}",
    "Para el roster de {empresa}: copia gratis y comisión del 70%",
]

CUERPO = """Hola equipo de {empresa},

Directo al punto: armamos una guía de iniciación al negocio musical, pensada para artistas emergentes — no es solo el típico manual de derechos y contratos. Trae además cómo construir marca propia y hacer marketing sin agencia, y un capítulo sobre inteligencia artificial en la industria musical: qué está pasando, los riesgos legales que ya se están viendo (demandas a plataformas de IA) y cómo usarla a favor sin quedar expuesto.

La propuesta: les damos una copia digital gratis para que la revisen sin compromiso. Si deciden recomendarla con su link de afiliado de Hotmart, se quedan con el 70% de cada venta (≈ $10,31 USD por copia), sin invertir nada de su parte. Como referencia, 100 ventas por su link serían ≈ $1.031 USD.

Pueden ver el libro y el programa de afiliados aquí: https://immusicsello.hotmart.host/music

¿Les envío la copia digital para que la revisen?

José Galvis
IM Music — Sello discográfico independiente
https://www.instagram.com/immusicsello"""

SEGUIMIENTO = """Hola equipo de {empresa},

Subo este correo por si se perdió entre tantos mensajes.

La oferta sigue en pie: copia digital del libro sin costo y sin compromiso, y si deciden recomendarlo con su link de afiliado se quedan con el 70% de cada venta.

Si prefieren que no les vuelva a escribir sobre esto, díganme y no hay problema.

José Galvis
IM Music — Sello discográfico independiente"""


def _env():
    env = {}
    for line in open(BASE / ".env", encoding="utf-8"):
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.strip().split("=", 1)
            env[k] = v
    return env


def _leer_enviados():
    if not ENVIADOS.exists():
        return []
    return list(csv.DictReader(open(ENVIADOS, encoding="utf-8")))


def _guardar_enviados(rows):
    with open(ENVIADOS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["email", "empresa", "fecha", "seguimiento"])
        w.writeheader()
        w.writerows(rows)


def _respondieron():
    env = _env()
    M = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    M.login(env["IM_EMAIL_MUSIC"], env["IM_EMAIL_MUSIC_PASSWORD"])
    M.select("INBOX", readonly=True)
    desde = (datetime.now() - timedelta(days=30)).strftime("%d-%b-%Y")
    _, nums = M.search(None, f"SINCE {desde}")
    quienes = set()
    for n in nums[0].split():
        _, d = M.fetch(n, "(BODY.PEEK[HEADER.FIELDS (FROM)])")
        m = email.message_from_bytes(d[0][1])
        quienes.add(email.utils.parseaddr(m.get("From", ""))[1].lower())
    M.logout()
    return quienes


def _candidatos(a_contactados):
    mem = MemoriaAgentes()
    ya = {r["email"].lower() for r in _leer_enviados()}
    out = []
    for r in csv.DictReader(open(MUSICA, encoding="utf-8")):
        e = re.sub(r"%20|\s|;", "", r.get("email", "")).lower()
        nombre = r.get("empresa", "")
        if not EMAIL_OK.match(e) or any(m in e for m in MAL_DOMINIO):
            continue
        if any(x in nombre.lower() for x in EXCLUIR_NOMBRE):
            continue
        if e in ya or (not a_contactados and mem.ya_contactado(e)):
            continue
        out.append((e, nombre.strip()))
    vistos, unicos = set(), []
    for e, n in out:
        dom = e.split("@")[1]
        if dom in vistos and dom not in ("gmail.com", "hotmail.com", "outlook.com", "yahoo.com"):
            continue
        vistos.add(dom)
        unicos.append((e, n))
    return unicos


CUERPO_ARTISTA = """Hola equipo de {artista},

Directo al punto: tenemos un libro sobre negocio musical (derechos, contratos, regalías y marca propia) que le puede servir a la audiencia de {artista}: muchos de sus seguidores son artistas emergentes buscando justo esta información.

La propuesta: les damos una copia digital gratis para que la revisen sin compromiso. Si deciden recomendarla con su link de afiliado de Hotmart, se quedan con el 70% de cada venta (≈ $10,31 USD por copia), sin invertir nada de su parte. Como referencia, 500 ventas por su link serían ≈ $5.155 USD.

Pueden ver el libro y el programa de afiliados aquí: https://immusicsello.hotmart.host/music

¿Les envío la copia digital para que la revisen?

José Galvis
IM Music — Sello discográfico independiente
https://www.instagram.com/immusicsello"""

ASUNTOS_ARTISTA = [
    "Una propuesta sin inversión para el equipo de {artista}",
    "70% de comisión para el equipo de {artista} — 2 minutos",
    "Para {artista}: libro de music business, copia gratis",
]
DOCS_LIBRO = Path("C:/Users/JOSÉ/Projects/immusic-content-engine/docs/libro")


def _candidatos_equipos(incluir_baja):
    """Contactos de booking/management definidos en el proyecto del libro."""
    ya = {r["email"].lower() for r in _leer_enviados()}
    out, vistos = [], set()
    for f in ("contactos_master.csv", "contactos_artistas_afiliados.csv", "contactos_batch_colombia.csv",
              "contactos_batch_pr_mexico.csv", "contactos_batch_arg_chile_industria.csv"):
        p = DOCS_LIBRO / f
        if not p.exists():
            continue
        for r in csv.DictReader(open(p, encoding="utf-8")):
            m = re.search(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", r.get("Correo_o_Contacto", ""))
            if not m:
                continue
            e = m.group(0).lower()
            if e in ya or e in vistos:
                continue
            if r.get("Confianza", "").strip().lower() == "baja" and not incluir_baja:
                continue
            vistos.add(e)
            artista = re.sub(r"\s*\(.*?\)\s*", "", r.get("Artista", "")).strip()
            out.append((e, artista, "artista"))
    # contactos nuevos encontrados por los agentes de investigacion
    for f in ("libro_contactos_nuevos_A.csv", "libro_contactos_nuevos_B.csv"):
        p2 = BASE / "data" / f
        if not p2.exists():
            continue
        for r in csv.DictReader(open(p2, encoding="utf-8")):
            e = r.get("Correo", "").strip().lower()
            if not EMAIL_OK.match(e) or e in ya or e in vistos:
                continue
            vistos.add(e)
            if f.endswith("_B.csv"):
                ag = re.sub(r"\s*\(.*?\)\s*", "", r.get("Nombre_Agencia_o_Manager", "")).strip()
                out.append((e, ag, "agencia"))
            else:
                out.append((e, re.sub(r"\s*\(.*?\)\s*", "", r.get("Artista", "")).strip(), "artista"))
    return out


CUENTA_ENVIO = "jose"


def _smtp_desde_mateo(email_to, asunto, cuerpo):
    """Texto plano desde la cuenta de Mateo (que no esta bloqueada por Gmail);
    las respuestas llegan a la bandeja de IM Music (Reply-To)."""
    import smtplib, ssl
    from email.message import EmailMessage
    from email.utils import formatdate, make_msgid
    env = _env()
    user, pwd = env["IM_EMAIL"], env["IM_EMAIL_PASSWORD"]
    msg = EmailMessage()
    msg["From"] = f"José Galvis - IM Music <{user}>"
    msg["Reply-To"] = env.get("IM_EMAIL_MUSIC", "immusicsello@gmail.com")
    msg["To"] = email_to
    msg["Subject"] = asunto
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    msg.set_content(cuerpo)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
            s.login(user, pwd)
            s.send_message(msg)
        return True
    except Exception as e:
        print(f"[libro] error SMTP Mateo: {str(e)[:100]}")
        return False


def _enviar(email_to, asunto, cuerpo, dry):
    if dry:
        print(f"--- DRY-RUN a {email_to}\nAsunto: {asunto}\n{cuerpo}\n")
        return True
    ok_h, espera, razon_h = deliv.verificar_horario()
    if not ok_h:
        print("[libro] " + razon_h)
        return None
    if espera:
        print("[libro] " + razon_h + ": retoma en " + str(espera // 60) + " min")
        time.sleep(espera)
    puede, razon = deliv.puede_enviar_ahora(CUENTA_ENVIO)
    if not puede:
        print(f"[libro] ⛔ {razon}")
        return None
    global _FALLOS
    if CUENTA_ENVIO == "mateo":
        ok = _smtp_desde_mateo(email_to, asunto, cuerpo)
    else:
        ok = im_agents.enviar_email("jose", email_to, asunto, cuerpo, False)
    if ok:
        _FALLOS = 0
        deliv.registrar_email_warmup(CUENTA_ENVIO)
    else:
        _FALLOS += 1
        if _FALLOS >= 2:
            print("[libro] 2 fallos seguidos (posible limite de Gmail): se detiene esta corrida")
            return None
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=10)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cuenta", choices=["jose", "mateo"], default="jose",
                    help="cuenta de Gmail desde la que se envia (mateo = respaldo si la de José esta bloqueada)")
    ap.add_argument("--equipos", action="store_true",
                    help="enviar al equipo/booking de los artistas definidos en docs/libro")
    ap.add_argument("--incluir-baja", action="store_true", help="incluir contactos de confianza baja")
    ap.add_argument("--a-contactados", action="store_true",
                    help="tambien a quienes ya recibieron otro correo del sistema")
    args = ap.parse_args()
    global CUENTA_ENVIO
    CUENTA_ENVIO = args.cuenta

    enviados = _leer_enviados()
    hechos = 0

    # 1) seguimiento unico a quien no respondio en DIAS_SEGUIMIENTO dias
    if enviados and not args.dry_run:
        resp = _respondieron()
        limite = datetime.now() - timedelta(days=DIAS_SEGUIMIENTO)
        for r in enviados:
            if hechos >= args.max:
                break
            if r["seguimiento"] == "si" or r["email"] in resp or datetime.fromisoformat(r["fecha"]) > limite:
                continue
            ok = _enviar(r["email"], "Re: " + ASUNTOS[0].format(empresa=r["empresa"]),
                         SEGUIMIENTO.format(empresa=r["empresa"]), False)
            if ok is None:
                break
            if ok:
                r["seguimiento"] = "si"
                hechos += 1
                print(f"[libro] seguimiento -> {r['email']}")
                time.sleep(random.uniform(60, 120))
        _guardar_enviados(enviados)

    # 2a) equipos de artistas / agencias de booking definidos en docs/libro
    if args.equipos:
        for e, artista, tipo_c in _candidatos_equipos(args.incluir_baja):
            if hechos >= args.max:
                break
            if tipo_c == "agencia":
                asunto = random.choice(ASUNTOS).format(empresa=artista)
                cuerpo_c = CUERPO.format(empresa=artista)
            else:
                asunto = random.choice(ASUNTOS_ARTISTA).format(artista=artista)
                cuerpo_c = CUERPO_ARTISTA.format(artista=artista)
            ok = _enviar(e, asunto, cuerpo_c, args.dry_run)
            if ok is None:
                break
            if ok and not args.dry_run:
                enviados.append({"email": e, "empresa": artista, "fecha": datetime.now().isoformat(), "seguimiento": ""})
                _guardar_enviados(enviados)
                MemoriaAgentes().registrar_contacto(e, asunto, "libro afiliados equipo artista")
                hechos += 1
                print(f"[libro] equipo de {artista} -> {e}")
                time.sleep(random.uniform(60, 120))
            elif ok:
                hechos += 1
        print(f"[libro] {hechos} correos en esta corrida")
        return

    # 2) primer correo a los nuevos
    for e, nombre in _candidatos(args.a_contactados):
        if hechos >= args.max:
            break
        asunto = random.choice(ASUNTOS).format(empresa=nombre)
        ok = _enviar(e, asunto, CUERPO.format(empresa=nombre), args.dry_run)
        if ok is None:
            break
        if ok and not args.dry_run:
            enviados.append({"email": e, "empresa": nombre, "fecha": datetime.now().isoformat(), "seguimiento": ""})
            _guardar_enviados(enviados)
            MemoriaAgentes().registrar_contacto(e, asunto, "libro afiliados")
            hechos += 1
            print(f"[libro] enviado -> {nombre} <{e}>")
            time.sleep(random.uniform(60, 120))
        elif ok:
            hechos += 1
    print(f"[libro] {hechos} correos en esta corrida")


if __name__ == "__main__":
    main()
