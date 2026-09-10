"""
De cuándo es la copia que corre en este PC.

── El problema, dicho como se vive ─────────────────────────────────────────────
El sábado a las siete de la mañana, en el polideportivo, la pregunta no es «¿se
puede bajar el campeonato?» —eso lleva funcionando desde julio y es
re-ejecutable (`api/sincronizacion.py`)— sino **«¿esta copia trae las
inscripciones del jueves?»**. Y esa no se podía contestar: el sobre del paquete
sí dice quién lo exportó y cuándo (`_sobre`), pero se enseñaba una vez en la
vista previa y se perdía al confirmar.

Sin una fecha a la vista, la única salida era volver a bajar a ciegas. Cuesta
dos minutos y no rompe nada, así que tampoco es un desastre — pero **deja de
poder hacerse en cuanto se activa la primera llave**, que es justo el momento
en el que a alguien se le ocurre la duda.

── Cómo se guarda ─────────────────────────────────────────────────────────────
En `ajustes` (clave `ultima_bajada`), igual que el modo mantenimiento: es un
dato de LA INSTALACIÓN, no de un workspace —lo que corre en este PC es una
copia y punto, la trajera quien la trajera—, y por eso queda fuera de las
políticas de RLS.

Y como el mantenimiento, **leerlo no puede reventar nunca**: una instalación
recién montada no tiene ni tabla, y que falte el dato no puede tumbar la
pantalla que lo enseña.
"""

from datetime import datetime, timezone

from .extensions import db
from .models.ajuste import Ajuste
from .timeutil import iso_utc

CLAVE = "ultima_bajada"

# A partir de aquí la copia se considera vieja y se avisa. Un día entero es el
# hueco típico entre la bajada de la víspera y la mañana del evento: menos
# avisaría siempre y el aviso dejaría de leerse.
HORAS_PARA_AVISAR = 24

# Secciones cuyo tamaño se anota: las que alguien cuenta a ojo para comprobar
# que la copia cuadra con lo que dice la VPS.
SECCIONES = ("usuarios", "competidores", "inscripciones", "llaves")


def _ahora():
    return datetime.now(timezone.utc)


def _conteos(paquete):
    """Cuántas filas trae el paquete, por sección."""
    conteos = {}
    for seccion in SECCIONES:
        lista = paquete.get(seccion)
        if isinstance(lista, list) and lista:
            conteos[seccion] = len(lista)
    return conteos


def anotar(paquete, formato, admin, campeonato_nombre=None):
    """Deja escrito que esta copia se trajo, de cuándo es y qué trae.

    Dos cosas que NO se anotan, y las dos por el mismo motivo:

      · **Una vista previa.** Se revierte entera (ver `importar`), así que
        anotarla dejaría dicho que se trajo algo que no se trajo.
      · **Un paquete que no es el del campeonato.** Importar solo usuarios es
        una bajada, sí, pero no trae inscripciones: si pisara la fecha de la
        copia buena, la pantalla diría «traída hace diez minutos» de algo que
        no tiene el campeonato dentro.

    Los dos serían el mismo error que este módulo viene a arreglar, en
    pequeño: una fecha a la vista que no significa lo que parece.

    No propaga errores: si esto falla, la importación ya está hecha y
    confirmada, y perder la nota es mucho menos grave que perder el paquete.
    """
    try:
        fila = db.session.get(Ajuste, CLAVE)
        if fila is None:
            fila = Ajuste(clave=CLAVE)
            db.session.add(fila)
        fila.valor = {
            # Cuándo se trajo aquí y de cuándo es la copia son DOS fechas
            # distintas, y la que importa para «¿trae lo del jueves?» es la
            # segunda: una copia exportada el jueves e importada el sábado
            # sigue sin traer lo del viernes.
            "importado_at": iso_utc(_ahora()),
            "exportado_at": paquete.get("exportado_at"),
            "origen_admin": (paquete.get("origen") or {}).get("admin"),
            "formato": formato,
            "campeonato": campeonato_nombre,
            "importado_por": getattr(admin, "email", None),
            "conteos": _conteos(paquete),
        }
        fila.actualizado_por_id = getattr(admin, "id", None)
        db.session.commit()
    except Exception:  # noqa: BLE001 — la nota es un extra, no la importación
        db.session.rollback()


def _horas_desde(texto):
    """Horas transcurridas desde una fecha ISO, o None si no se entiende."""
    if not texto:
        return None
    try:
        momento = datetime.fromisoformat(str(texto).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return max(0.0, (_ahora() - momento).total_seconds() / 3600.0)


def _ya_se_compite():
    """True si en esta instalación ya hay una llave en juego o terminada.

    Es el mismo umbral con el que la importación se frena (`_evento_ya_iniciado`
    en `api/sincronizacion.py`), y por eso es también el umbral del aviso: a
    partir de ahí volver a bajar ya no es una opción, así que recordarlo solo
    sería ruido en la peor mañana del año.
    """
    from .models.llave import Llave

    return db.session.query(
        Llave.query.filter(Llave.estado.in_(("activa", "terminada"))).exists()
    ).scalar()


def estado():
    """Qué copia corre aquí, y si conviene volver a bajarla.

    Devuelve `{"hay": False}` mientras nadie haya importado nada — que es el
    estado normal de una instalación recién montada, no un error.
    """
    try:
        fila = db.session.get(Ajuste, CLAVE)
        valor = dict(fila.valor) if fila and isinstance(fila.valor, dict) else None
    except Exception:  # noqa: BLE001 — sin tabla o sin base: no hay copia que contar
        db.session.rollback()
        valor = None

    if not valor:
        return {"hay": False}

    # La edad se mide desde que la copia SALIÓ de la VPS. Si el sobre no lo
    # dice —un paquete muy viejo—, se cae a cuándo entró aquí, que es lo único
    # que se sabe.
    horas = _horas_desde(valor.get("exportado_at"))
    if horas is None:
        horas = _horas_desde(valor.get("importado_at"))

    try:
        compitiendo = bool(_ya_se_compite())
    except Exception:  # noqa: BLE001
        db.session.rollback()
        compitiendo = False

    valor.update({
        "hay": True,
        "horas": round(horas, 1) if horas is not None else None,
        "ya_se_compite": compitiendo,
        "avisar": bool(
            horas is not None and horas >= HORAS_PARA_AVISAR and not compitiendo
        ),
    })
    return valor
