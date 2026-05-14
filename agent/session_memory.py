#!/usr/bin/env python3
"""
session_memory.py — Memoria persistente para todos los agentes IM.

Guarda en platform.db:
  memoria_leads          → historial de contactos por email
  memoria_performance    → tasas de éxito por asunto / nicho / hora
  memoria_investigaciones → cache de investigaciones (30 días TTL)
"""
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).parent.parent
DB   = BASE / "logs" / "platform.db"

# ── SCHEMA ────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memoria_leads (
    email              TEXT PRIMARY KEY,
    veces_contactado   INTEGER DEFAULT 0,
    ultimo_contacto    TEXT,
    respondio          INTEGER DEFAULT 0,
    ultimo_asunto      TEXT,
    ultimo_copy        TEXT,
    resultado          TEXT
);

CREATE TABLE IF NOT EXISTS memoria_performance (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo           TEXT,
    valor          TEXT,
    tasa_exito     REAL DEFAULT 0.0,
    total_intentos INTEGER DEFAULT 1,
    fecha          TEXT
);

CREATE TABLE IF NOT EXISTS memoria_investigaciones (
    negocio              TEXT PRIMARY KEY,
    url                  TEXT,
    fecha_investigacion  TEXT,
    job_id               TEXT,
    resumen              TEXT
);
"""


def _conn():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB))
    c.row_factory = sqlite3.Row
    return c


def _init():
    c = _conn()
    c.executescript(_SCHEMA)
    c.commit()
    c.close()


_init()


# ════════════════════════════════════════════════════════════════
# CLASE PRINCIPAL
# ════════════════════════════════════════════════════════════════

class MemoriaAgentes:

    # ── MEMORIA DE LEADS ──────────────────────────────────────────

    def ya_contactado(self, email: str) -> bool:
        """True si el email ya fue contactado al menos una vez."""
        c = _conn()
        row = c.execute(
            "SELECT veces_contactado FROM memoria_leads WHERE LOWER(email)=LOWER(?)",
            (email,)
        ).fetchone()
        c.close()
        return bool(row and row["veces_contactado"] > 0)

    def registrar_contacto(self, email: str, asunto: str = "", copy: str = ""):
        """Registra o incrementa el contador de contactos para un email."""
        now = datetime.now().isoformat()
        c = _conn()
        c.execute("""
            INSERT INTO memoria_leads (email, veces_contactado, ultimo_contacto, ultimo_asunto, ultimo_copy)
            VALUES (LOWER(?), 1, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                veces_contactado = veces_contactado + 1,
                ultimo_contacto  = excluded.ultimo_contacto,
                ultimo_asunto    = excluded.ultimo_asunto,
                ultimo_copy      = excluded.ultimo_copy
        """, (email, now, asunto[:200], copy[:500]))
        c.commit()
        c.close()
        self._registrar_performance("asunto", asunto)

    def marcar_apertura(self, email: str):
        """Marca que el destinatario abrió el email."""
        c = _conn()
        c.execute(
            "UPDATE memoria_leads SET resultado='abierto' WHERE LOWER(email)=LOWER(?)",
            (email,)
        )
        c.commit()
        c.close()
        self._actualizar_tasa("apertura", email)

    def marcar_respuesta(self, email: str):
        """Marca que el destinatario respondió."""
        c = _conn()
        c.execute(
            """UPDATE memoria_leads
               SET respondio=1, resultado='respondio'
               WHERE LOWER(email)=LOWER(?)""",
            (email,)
        )
        c.commit()
        c.close()

    def get_info_lead(self, email: str) -> dict:
        """Retorna el registro completo de un lead."""
        c = _conn()
        row = c.execute(
            "SELECT * FROM memoria_leads WHERE LOWER(email)=LOWER(?)",
            (email,)
        ).fetchone()
        c.close()
        return dict(row) if row else {}

    # ── MEMORIA DE PERFORMANCE ────────────────────────────────────

    def _registrar_performance(self, tipo: str, valor: str):
        if not valor:
            return
        now = datetime.now().isoformat()
        c = _conn()
        row = c.execute(
            "SELECT id, total_intentos FROM memoria_performance WHERE tipo=? AND valor=?",
            (tipo, valor[:200])
        ).fetchone()
        if row:
            c.execute(
                "UPDATE memoria_performance SET total_intentos=total_intentos+1, fecha=? WHERE id=?",
                (now, row["id"])
            )
        else:
            c.execute(
                "INSERT INTO memoria_performance (tipo, valor, tasa_exito, total_intentos, fecha) "
                "VALUES (?,?,0,1,?)",
                (tipo, valor[:200], now)
            )
        c.commit()
        c.close()

    def _actualizar_tasa(self, evento: str, email: str):
        """Cuando hay apertura, incrementa tasa_exito del último asunto usado."""
        c = _conn()
        row = c.execute(
            "SELECT ultimo_asunto FROM memoria_leads WHERE LOWER(email)=LOWER(?)",
            (email,)
        ).fetchone()
        if row and row["ultimo_asunto"]:
            c.execute("""
                UPDATE memoria_performance
                SET tasa_exito = (tasa_exito * total_intentos + 1.0) / (total_intentos + 1)
                WHERE tipo='asunto' AND valor=?
            """, (row["ultimo_asunto"],))
        c.commit()
        c.close()

    def get_mejores_asuntos(self, top: int = 5) -> list:
        """Retorna los asuntos con mayor tasa de éxito (mín. 3 intentos)."""
        c = _conn()
        rows = c.execute("""
            SELECT valor, tasa_exito, total_intentos
            FROM memoria_performance
            WHERE tipo='asunto' AND total_intentos >= 3
            ORDER BY tasa_exito DESC
            LIMIT ?
        """, (top,)).fetchall()
        c.close()
        return [dict(r) for r in rows]

    def registrar_nicho(self, nicho: str, respondio: bool = False):
        """Acumula stats de respuesta por nicho."""
        self._registrar_performance("nicho", nicho)
        if respondio:
            c = _conn()
            c.execute("""
                UPDATE memoria_performance
                SET tasa_exito = (tasa_exito * total_intentos + 1.0) / (total_intentos + 1)
                WHERE tipo='nicho' AND valor=?
            """, (nicho,))
            c.commit()
            c.close()

    def get_performance_stats(self) -> dict:
        """Resumen general de performance."""
        c = _conn()
        total_leads = c.execute("SELECT COUNT(*) FROM memoria_leads").fetchone()[0]
        total_respondieron = c.execute(
            "SELECT COUNT(*) FROM memoria_leads WHERE respondio=1"
        ).fetchone()[0]
        mejores = self.get_mejores_asuntos(3)
        nichos = c.execute("""
            SELECT valor, tasa_exito, total_intentos
            FROM memoria_performance WHERE tipo='nicho'
            ORDER BY tasa_exito DESC LIMIT 5
        """).fetchall()
        c.close()
        tasa = round(total_respondieron / total_leads * 100, 1) if total_leads else 0
        return {
            "total_contactados": total_leads,
            "total_respondieron": total_respondieron,
            "tasa_respuesta_pct": tasa,
            "mejores_asuntos": mejores,
            "mejores_nichos": [dict(r) for r in nichos],
        }

    # ── MEMORIA DE INVESTIGACIONES ────────────────────────────────

    def get_investigacion(self, negocio: str, dias_ttl: int = 30):
        """
        Retorna investigación guardada si existe y es menor de `dias_ttl` días.
        Retorna None si no existe o expiró.
        """
        c = _conn()
        row = c.execute(
            "SELECT * FROM memoria_investigaciones WHERE LOWER(negocio)=LOWER(?)",
            (negocio,)
        ).fetchone()
        c.close()
        if not row:
            return None
        fecha = datetime.fromisoformat(row["fecha_investigacion"])
        if datetime.now() - fecha > timedelta(days=dias_ttl):
            return None
        return dict(row)

    def guardar_investigacion(self, negocio: str, url: str, job_id: str, resumen: str):
        """Guarda o actualiza la investigación de un negocio."""
        now = datetime.now().isoformat()
        c = _conn()
        c.execute("""
            INSERT INTO memoria_investigaciones (negocio, url, fecha_investigacion, job_id, resumen)
            VALUES (LOWER(?), ?, ?, ?, ?)
            ON CONFLICT(negocio) DO UPDATE SET
                url                 = excluded.url,
                fecha_investigacion = excluded.fecha_investigacion,
                job_id              = excluded.job_id,
                resumen             = excluded.resumen
        """, (negocio, url, now, job_id, resumen[:2000]))
        c.commit()
        c.close()

    # ── MEMORIA DEL ORQUESTADOR ───────────────────────────────────

    def nicho_reciente(self, nicho: str, dias: int = 7) -> bool:
        """True si el nicho ya fue procesado en los últimos `dias` días."""
        c = _conn()
        row = c.execute("""
            SELECT fecha FROM memoria_performance
            WHERE tipo='nicho' AND valor=?
            ORDER BY fecha DESC LIMIT 1
        """, (nicho,)).fetchone()
        c.close()
        if not row:
            return False
        fecha = datetime.fromisoformat(row["fecha"])
        return datetime.now() - fecha < timedelta(days=dias)
