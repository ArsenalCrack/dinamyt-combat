"""
EL CANDADO DE SEDE — un escritor a la vez (decisión 8 del plan maestro).

── El problema ──

El campeonato se inscribe en internet y se corre en el PC del evento, con la
copia que se bajó la víspera (`INICIAR-LOCAL.md` §2.1). Hasta el 26 sep 2026
nada impedía que, mientras tanto, alguien siguiera tocando llaves,
inscripciones o tatamis EN INTERNET: dos escritores, y lo que diverge no
avisa — el paquete de vuelta solo trae resultados, así que se descubre al
subir, o no se descubre.

── La solución: no resolver conflictos, hacerlos imposibles ──

La instalación que CEDE el campeonato lo marca (`sede_local_desde`) y a partir
de ahí, en ella, ese campeonato es de SOLO LECTURA: toda ruta que escribe sobre
él contesta 423. La copia del PC del evento nunca trae la marca —el paquete no
la lleva—, así que allí se escribe como siempre.

· Ceder es un gesto: se hace al bajarse el paquete «para el evento»
  (`?para_el_evento=1`) o con `POST /api/campeonatos/:id/sede`.
· Recuperarlo también es un gesto, nunca automático: cuando los resultados
  subieron y ya no queda nada que correr, el admin lo devuelve a la nube.
· Un minicampeonato sin PC a mano no se cede nunca y corre aquí sin tocar nada:
  por eso el candado se pone y se quita, y la consola de internet no se amputa.

Lo que SÍ sigue abierto con el candado puesto: mirar (todas las lecturas), las
fichas de competidores (son del workspace, no del campeonato) y la SUBIDA de
resultados (`/api/resultados/importar`), que es justo el camino de vuelta.
"""
from datetime import datetime, timezone
from functools import wraps

from flask import jsonify, request

from .extensions import db


def en_otra_sede(camp) -> bool:
    """`True` si esta instalación cedió el campeonato al PC del evento."""
    return camp is not None and getattr(camp, "sede_local_desde", None) is not None


def sede_ocupada(camp):
    """La respuesta 423 si el campeonato está cedido; `None` si se puede escribir."""
    if not en_otra_sede(camp):
        return None
    desde = camp.sede_local_desde
    if desde.tzinfo is None:
        desde = desde.replace(tzinfo=timezone.utc)
    return jsonify({
        "error": (
            "Este campeonato se está operando en el PC del evento. Aquí solo se "
            "puede mirar hasta que se devuelva a la nube (campeonato → «Devolver "
            "a la nube»)."
        ),
        "sede": "local",
        "sede_local_desde": desde.isoformat(),
        "sede_local_por": camp.sede_local_por,
    }), 423


def _campeonato_de_la_peticion(kwargs):
    """El campeonato sobre el que escribe la petición, por su ruta o su cuerpo.

    `None` si no se sabe o no existe: entonces decide la vista (su 404 de
    siempre). Un id que no es un número tampoco es asunto de esta guarda.
    """
    from .models.campeonato import Campeonato
    from .models.competidor import Inscripcion
    from .models.llave import Llave
    from .models.tatami import Tatami

    def por(modelo, valor):
        try:
            return db.session.get(modelo, int(valor))
        except (TypeError, ValueError):
            return None

    if "camp_id" in kwargs:
        return por(Campeonato, kwargs["camp_id"])
    if "tatami_id" in kwargs:
        tatami = por(Tatami, kwargs["tatami_id"])
        return tatami.campeonato if tatami else None
    if "llave_id" in kwargs:
        llave = por(Llave, kwargs["llave_id"])
        return por(Campeonato, llave.campeonato_id) if llave else None
    if "ins_id" in kwargs:
        ins = por(Inscripcion, kwargs["ins_id"])
        return ins.campeonato if ins else None

    # Las rutas de llaves que traen el campeonato en el cuerpo.
    datos = request.get_json(silent=True) or {}
    if not isinstance(datos, dict):
        return None
    if datos.get("campeonato_id") is not None:
        return por(Campeonato, datos["campeonato_id"])
    ids = datos.get("llave_ids") or [datos.get("origen_id")]
    if isinstance(ids, list) and ids and ids[0] is not None:
        llave = por(Llave, ids[0])
        return por(Campeonato, llave.campeonato_id) if llave else None
    return None


def sede_aqui(vista):
    """Decorador para las rutas que ESCRIBEN sobre un campeonato.

    Va debajo de `@jwt_required()`, para que la identidad se compruebe antes.
    """

    @wraps(vista)
    def envuelta(*args, **kwargs):
        bloqueo = sede_ocupada(_campeonato_de_la_peticion(kwargs))
        if bloqueo is not None:
            return bloqueo
        return vista(*args, **kwargs)

    return envuelta


def ceder_sede(camp, admin):
    """Pasa el campeonato al PC del evento. Idempotente: la fecha es la primera."""
    if camp.sede_local_desde is None:
        camp.sede_local_desde = datetime.now(timezone.utc)
        camp.sede_local_por = getattr(admin, "email", None)


def recuperar_sede(camp):
    """Lo devuelve a esta instalación: vuelve a poder escribirse aquí."""
    camp.sede_local_desde = None
    camp.sede_local_por = None
