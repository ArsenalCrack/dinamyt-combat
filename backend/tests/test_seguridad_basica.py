"""
Tres arreglos de la revisión de seguridad del 25 de septiembre de 2026.

  1. **El secreto del PC del evento.** Corre en `development`, donde la guarda
     de secretos débiles no llegaba: con el valor de ejemplo —que está en el
     repositorio— cualquiera en la WiFi fabricaba un token de administrador.
     `iniciar_local.py` genera uno propio antes de arrancar.
  2. **Un tope al tamaño de las peticiones** (`MAX_CONTENT_LENGTH`): sin él,
     Flask leía a memoria cualquier cuerpo, también en rutas sin sesión.
  3. **Inyección de fórmulas en los Excel.** `openpyxl` convertía en fórmula
     todo texto que empezara por `=`: un nombre de competidor podía ser un
     enlace vivo en el Excel del admin.
"""

import importlib.util
import io
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "backend"))

import pytest  # noqa: E402

from app import create_app  # noqa: E402
from app.config import DevelopmentConfig  # noqa: E402

DevelopmentConfig.SQLALCHEMY_DATABASE_URI = "sqlite://"


def _lanzador(backend):
    """`iniciar_local.py` con su carpeta `backend` apuntando a otra parte."""
    spec = importlib.util.spec_from_file_location("iniciar_local_prueba", RAIZ / "iniciar_local.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    modulo.BACKEND = backend
    return modulo


# ── 1 · El secreto del PC del evento ────────────────────────────────────────

def test_sin_env_se_genera_un_secreto_propio(tmp_path):
    lanzador = _lanzador(tmp_path)

    assert lanzador.asegurar_secreto() is True

    (linea,) = [l for l in (tmp_path / ".env").read_text().splitlines() if l.startswith("JWT_")]
    assert len(linea.split("=", 1)[1]) == 64


def test_el_de_ejemplo_se_cambia_y_lo_demas_se_queda(tmp_path):
    (tmp_path / ".env").write_text(
        "ADMIN_EMAIL=admin@evento.org\nJWT_SECRET_KEY=CAMBIAR-POR-UN-VALOR-ALEATORIO-LARGO\n"
        "RESPALDO_MINUTOS=10\n",
        encoding="utf-8",
    )
    lanzador = _lanzador(tmp_path)

    assert lanzador.asegurar_secreto() is True

    texto = (tmp_path / ".env").read_text()
    assert "CAMBIAR-POR" not in texto
    assert "ADMIN_EMAIL=admin@evento.org" in texto and "RESPALDO_MINUTOS=10" in texto
    assert texto.count("JWT_SECRET_KEY=") == 1


def test_uno_propio_no_se_toca_y_los_qr_siguen_valiendo(tmp_path):
    propio = "a" * 64
    (tmp_path / ".env").write_text(f"JWT_SECRET_KEY={propio}\n", encoding="utf-8")
    lanzador = _lanzador(tmp_path)

    assert lanzador.asegurar_secreto() is False
    assert (tmp_path / ".env").read_text() == f"JWT_SECRET_KEY={propio}\n"


def test_uno_corto_tampoco_vale(tmp_path):
    (tmp_path / ".env").write_text("JWT_SECRET_KEY=1234\n", encoding="utf-8")
    assert _lanzador(tmp_path).asegurar_secreto() is True


# ── 2 · El tope de tamaño ───────────────────────────────────────────────────

def test_un_cuerpo_gigante_es_un_413_sin_leerlo(monkeypatch):
    app = create_app("development")
    cliente = app.test_client()
    enorme = b"x" * (app.config["MAX_CONTENT_LENGTH"] + 1)

    r = cliente.post("/api/auth/login", data=enorme, content_type="application/json")

    assert r.status_code == 413


def test_el_paquete_del_evento_cabe():
    from app.api.sincronizacion import MAX_BYTES_PAQUETE

    assert create_app("development").config["MAX_CONTENT_LENGTH"] > MAX_BYTES_PAQUETE


# ── 3 · Las fórmulas en los Excel ───────────────────────────────────────────

def test_un_nombre_que_empieza_por_igual_se_queda_en_texto():
    openpyxl = pytest.importorskip("openpyxl")
    from app.api.reportes import _como_texto

    wb = openpyxl.Workbook()
    ws = wb.active
    _como_texto(ws.cell(row=1, column=1, value='=HYPERLINK("http://malo.example";"ver")'))
    _como_texto(ws.cell(row=1, column=2, value="ANA GOMEZ"))
    _como_texto(ws.cell(row=1, column=3, value=7))
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    hoja = openpyxl.load_workbook(buf).active

    assert hoja["A1"].data_type == "s"
    assert hoja["A1"].value.startswith("=HYPERLINK")
    assert (hoja["B1"].value, hoja["C1"].value) == ("ANA GOMEZ", 7)
