"""
API: Sincronización entre instancias (software LOCAL ↔ software ONLINE)

La organización usa DOS instancias de DINAMYT con bases de datos separadas:

- ONLINE (internet): recibe las inscripciones de los maestros antes del evento
  y publica los resultados al público.
- LOCAL (LAN del polideportivo, sin depender de internet): corre el evento.

No es una sincronización bidireccional, sino DOS traspasos de un solo sentido
en momentos distintos:

  1. Antes del evento:  ONLINE → LOCAL, con un paquete de campeonato completo
     (este módulo).
  2. Después:           LOCAL → ONLINE, publicando podios y rankings
     (`api/resultados.py`, que ya existía).

── Por qué un paquete y no varios archivos sueltos ──────────────────────────────
Cada instancia numera sus filas con su propia PK entera: el juez `id=7` del
online es otra persona en el local. Si se importara "primero los usuarios, luego
el campeonato", el orden equivocado dejaría asignaciones apuntando a gente que
no existe. Por eso el paquete de campeonato es AUTO-CONTENIDO: lleva dentro los
usuarios, competidores, tatamis, asignaciones, inscripciones y llaves que
necesita, y el importador resuelve las dependencias él mismo, siempre en el
mismo orden. El emparejamiento entre instancias se hace por `uid` (ver
`app/uid.py`) y, si no hay, por la clave natural (correo o documento).

── Reglas que evitan sorpresas ─────────────────────────────────────────────────
- Todo lo importado pasa al workspace del admin que importa (`created_by` /
  `creado_por_id`). Si no, el aislamiento por workspace de `scoping.py` lo
  escondería: estaría en la base pero el admin no lo vería.
- Las CONTRASEÑAS no viajan. Los usuarios importados se crean sin clave
  utilizable: los jueces entran con el QR de su tatami (que no pide contraseña)
  y, si alguien necesita entrar con clave, el admin se la asigna en Usuarios.
- Una importación NUNCA crea administradores ni superadministradores.
- Si el campeonato local ya tiene llaves activas o terminadas (el evento
  arrancó), importar exige confirmación explícita para no pisar resultados.
- La vista previa ejecuta EXACTAMENTE el mismo código que la importación real y
  al final revierte la transacción: lo que anuncia es lo que va a pasar.
"""

import json
import re
import secrets
from datetime import date, datetime, timezone

from flask import Blueprint, Response, jsonify, request
from flask_jwt_extended import jwt_required

from ..extensions import db
from ..security import limitar
from ..models.asignacion import AsignacionJuez
from ..models.campeonato import ESTADOS_CAMPEONATO, Campeonato
from ..models.competidor import (
    ESTADOS_INSCRIPCION, Competidor, Inscripcion, normalizar_cinturon,
)
from ..models.llave import Llave
from ..models.tatami import Tatami
from ..models.usuario import Usuario
from ..timeutil import iso_utc
from ..uid import asegurar_uid, nuevo_uid
from ..ultima_bajada import anotar as anotar_bajada, estado as estado_bajada
from .scoping import (
    es_dueno_campeonato, filtrar_competidores, require_admin, workspace_owner_id,
)

sincronizacion_bp = Blueprint("sincronizacion", __name__)

FORMATO_CAMPEONATO = "dinamyt-campeonato"
FORMATO_USUARIOS = "dinamyt-usuarios"
FORMATO_COMPETIDORES = "dinamyt-competidores"
FORMATOS_VALIDOS = (FORMATO_CAMPEONATO, FORMATO_USUARIOS, FORMATO_COMPETIDORES)

# 2 desde F6: los usuarios viajan con `eco_sub`, la identidad del ecosistema.
#
# El importador NO comprueba la versión, y es a propósito: los campos nuevos
# son opcionales y los viejos no se han quitado, así que un paquete de la 1
# —uno exportado antes de esta fase, o por una instalación que aún no se ha
# actualizado— se importa igual, con la identidad en blanco. Eso importa el 9
# de octubre: ese día el paquete que haya es el que hay.
VERSION_PAQUETE = 2

# Tope del archivo subido (25 MB). Un campeonato de 1000 competidores con sus
# llaves ronda los 3 MB; más que esto no es un paquete de DINAMYT.
MAX_BYTES_PAQUETE = 25 * 1024 * 1024

# Roles que viajan en un paquete. Los administradores NUNCA se importan: cada
# instancia tiene los suyos y una importación no debe poder crear uno.
ROLES_EXPORTABLES = ("maestro", "juez")

MODOS_IMPORTACION = ("fusionar", "reemplazar")


class ErrorImportacion(Exception):
    """Paquete inválido o incompatible con esta instancia (aborta todo)."""

    def __init__(self, mensaje, status=400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status = status


# ═══════════════════════════════════════════════════════════════════════════
#  Serialización (exportar)
# ═══════════════════════════════════════════════════════════════════════════

def _fecha(valor):
    return valor.isoformat() if valor else None


def _usuario_a_dict(u):
    """Usuario para el paquete. Sin contraseña, sin es_superadmin, sin ids.

    `eco_sub` es el «quién eres» que firma el portal (ver `espejo.py`). Viaja
    porque sin él la fila importada queda sin enlace con el ecosistema: ni le
    llega el tema y el idioma de su cuenta, ni la vuelta de los resultados
    sabe a quién corresponde. Es opcional —el modo local crea usuarios que no
    vienen del portal y esos no tienen ninguno— y NUNCA pisa el que ya haya
    en el destino (ver `_enlazar_eco_sub`).
    """
    return {
        "uid": asegurar_uid(u),
        "eco_sub": u.eco_sub,
        "email": u.email,
        "nombre": u.nombre,
        "rol": u.rol,
        # `club` y la delegación (los del principal) viajan además de la lista
        # para que una instalación vieja, que solo lee esas claves, siga
        # importando bien. En `clubes` va cada dojang con la suya.
        "club": u.club,
        "clubes": u.clubes,
        "delegacion": u.delegacion,
        "pais_delegacion": u.pais_delegacion,
        "puede_juzgar": bool(u.puede_juzgar),
        "activo": bool(u.activo),
    }


def _competidor_a_dict(c):
    return {
        "uid": asegurar_uid(c),
        "nombre_completo": c.nombre_completo,
        "documento": c.documento,
        "fecha_nacimiento": _fecha(c.fecha_nacimiento),
        "genero": c.genero,
        "cinturon": c.cinturon,
        "grupo_cinturon": c.grupo_cinturon,
        "peso": c.peso,
        "club": c.club,
        "categoria_especial": bool(c.categoria_especial),
        "activo": bool(c.activo),
        "updated_at": iso_utc(c.updated_at or c.created_at),
    }


def _campeonato_a_dict(camp):
    return {
        "uid": asegurar_uid(camp),
        "nombre": camp.nombre,
        "descripcion": camp.descripcion,
        "fecha_inicio": _fecha(camp.fecha_inicio),
        "fecha_fin": _fecha(camp.fecha_fin),
        "lugar": camp.lugar,
        "ciudad": camp.ciudad,
        "pais": camp.pais,
        "estado": camp.estado or "preparacion",
        "activo": bool(camp.activo),
        "config_categorias": camp.config_categorias,
    }


def _tatami_a_dict(t):
    return {"uid": asegurar_uid(t), "numero": t.numero, "activo": bool(t.activo)}


def _asignacion_a_dict(a, usuario, tatami):
    return {
        "uid": asegurar_uid(a),
        "usuario_uid": asegurar_uid(usuario),
        "tatami_uid": asegurar_uid(tatami),
        "rol_tatami": a.rol_tatami,
        "nombre_display": a.nombre_display,
    }


def _inscripcion_a_dict(ins, solicitante):
    return {
        "uid": asegurar_uid(ins),
        "competidor_uid": asegurar_uid(ins.competidor),
        "modalidades": ins.modalidades or [],
        "peso": ins.peso,
        "grupo_cinturon": ins.grupo_cinturon,
        "estado": ins.estado or "aceptada",
        "motivo_rechazo": ins.motivo_rechazo,
        # Quién la envió (un maestro). Si fue el admin no viaja: al importar,
        # la inscripción queda a nombre del admin que importa.
        "solicitante_uid": asegurar_uid(solicitante) if solicitante else None,
        "created_at": iso_utc(ins.created_at),
    }


def _llave_a_dict(ll, tatami):
    return {
        "uid": asegurar_uid(ll),
        "tatami_uid": asegurar_uid(tatami) if tatami else None,
        "tipo": ll.tipo_norm,
        "nombre": ll.nombre,
        "descripcion": ll.descripcion,
        "estado": ll.estado_norm,
        "seccion_clave": ll.seccion_clave,
        # La estructura ya lleva a los competidores embebidos por nombre y club
        # (ver engine de llaves): no depende de ids, viaja tal cual.
        "estructura": ll.estructura,
    }


def _slug(texto, defecto="campeonato"):
    limpio = re.sub(r"[^a-zA-Z0-9._-]+", "-", (texto or "").strip()).strip("-")
    return (limpio or defecto).lower()[:60]


def _descarga(envelope, nombre_archivo):
    cuerpo = json.dumps(envelope, ensure_ascii=False, indent=2)
    return Response(
        cuerpo,
        mimetype="application/json",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )


def _sobre(formato, admin, extra):
    """Cabecera común a todos los paquetes."""
    return {
        "formato": formato,
        "version": VERSION_PAQUETE,
        "exportado_at": datetime.now(timezone.utc).isoformat(),
        "origen": {"admin": admin.email},
        **extra,
    }


def _flag(nombre, defecto=True):
    valor = request.args.get(nombre)
    if valor is None:
        return defecto
    return valor in ("1", "true", "si", "yes")


# ═══════════════════════════════════════════════════════════════════════════
#  Exportar
# ═══════════════════════════════════════════════════════════════════════════

@sincronizacion_bp.route("/campeonato/<int:camp_id>/exportar", methods=["GET"])
@jwt_required()
def exportar_campeonato(camp_id):
    """
    GET /api/sincronizacion/campeonato/:id/exportar
        ?usuarios=1&competidores=1&llaves=1
    Descarga el paquete completo del campeonato para llevarlo a la otra
    instancia. Cada sección se puede excluir con su bandera en 0.
    """
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Solo administradores"}), 403

    camp = Campeonato.query.get(camp_id)
    if not camp or not es_dueno_campeonato(admin, camp):
        # 404 (no 403) para no revelar campeonatos de otro workspace.
        return jsonify({"error": "Campeonato no encontrado"}), 404

    con_usuarios = _flag("usuarios")
    con_competidores = _flag("competidores")
    con_llaves = _flag("llaves")

    tatamis = (
        Tatami.query.filter_by(campeonato_id=camp.id).order_by(Tatami.numero).all()
    )
    tatami_por_id = {t.id: t for t in tatamis}

    asignaciones = []
    if tatami_por_id:
        asignaciones = AsignacionJuez.query.filter(
            AsignacionJuez.tatami_id.in_(list(tatami_por_id.keys()))
        ).all()

    inscripciones = camp.inscripciones.all()

    # Usuarios del campeonato: los jueces asignados a sus tatamis y los maestros
    # que enviaron inscripciones. Los administradores quedan fuera a propósito.
    usuarios = {}
    if con_usuarios:
        candidatos = [a.usuario for a in asignaciones]
        candidatos += [ins.autor for ins in inscripciones]
        for u in candidatos:
            if u is not None and u.rol in ROLES_EXPORTABLES:
                usuarios[u.id] = u

    paquete = _sobre(FORMATO_CAMPEONATO, admin, {
        "campeonato": _campeonato_a_dict(camp),
        "tatamis": [_tatami_a_dict(t) for t in tatamis],
    })
    paquete["incluye"] = ["tatamis"]

    if con_usuarios:
        paquete["usuarios"] = [_usuario_a_dict(u) for u in usuarios.values()]
        # Solo viajan las asignaciones cuyo juez va en el paquete: si no, al
        # importar apuntarían a alguien que no existe.
        paquete["asignaciones"] = [
            _asignacion_a_dict(a, a.usuario, tatami_por_id[a.tatami_id])
            for a in asignaciones
            if a.usuario_id in usuarios and a.tatami_id in tatami_por_id
        ]
        paquete["incluye"] += ["usuarios", "asignaciones"]

    if con_competidores:
        vistos = {}
        for ins in inscripciones:
            if ins.competidor is not None:
                vistos[ins.competidor.id] = ins.competidor
        paquete["competidores"] = [_competidor_a_dict(c) for c in vistos.values()]
        paquete["inscripciones"] = [
            _inscripcion_a_dict(
                ins,
                ins.autor if (ins.autor and ins.autor.id in usuarios) else None,
            )
            for ins in inscripciones
            if ins.competidor is not None
        ]
        paquete["incluye"] += ["competidores", "inscripciones"]

    if con_llaves:
        llaves = Llave.query.filter_by(campeonato_id=camp.id).all()
        paquete["llaves"] = [
            _llave_a_dict(ll, tatami_por_id.get(ll.tatami_id)) for ll in llaves
        ]
        paquete["incluye"].append("llaves")

    # Los uid recién generados durante la serialización se persisten: así el
    # mismo campeonato exportado otra vez conserva su identidad.
    db.session.commit()

    return _descarga(paquete, f"campeonato-{_slug(camp.nombre)}.json")


@sincronizacion_bp.route("/usuarios/exportar", methods=["GET"])
@jwt_required()
def exportar_usuarios():
    """
    GET /api/sincronizacion/usuarios/exportar
    Paquete con los maestros y jueces del workspace (sin contraseñas). Sirve
    para dejar lista la otra instancia antes de traspasar campeonatos.
    """
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Solo administradores"}), 403

    query = Usuario.query.filter(Usuario.rol.in_(ROLES_EXPORTABLES))
    if not admin.es_super:
        query = query.filter(Usuario.creado_por_id == admin.id)
    usuarios = query.order_by(Usuario.nombre).all()

    paquete = _sobre(FORMATO_USUARIOS, admin, {
        "incluye": ["usuarios"],
        "usuarios": [_usuario_a_dict(u) for u in usuarios],
    })
    db.session.commit()
    return _descarga(paquete, "usuarios-dinamyt.json")


@sincronizacion_bp.route("/competidores/exportar", methods=["GET"])
@jwt_required()
def exportar_competidores():
    """
    GET /api/sincronizacion/competidores/exportar
    Paquete con los competidores del workspace, con todos sus campos (a
    diferencia del Excel, que es para capturar listas a mano).
    """
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Solo administradores"}), 403

    query = filtrar_competidores(admin, Competidor.query)
    competidores = query.order_by(Competidor.nombre_completo).all()

    paquete = _sobre(FORMATO_COMPETIDORES, admin, {
        "incluye": ["competidores"],
        "competidores": [_competidor_a_dict(c) for c in competidores],
    })
    db.session.commit()
    return _descarga(paquete, "competidores-dinamyt.json")


# ═══════════════════════════════════════════════════════════════════════════
#  Informe de la importación
# ═══════════════════════════════════════════════════════════════════════════

class Informe:
    """Contadores y avisos. Se llena igual en vista previa que en la real."""

    SECCIONES = (
        "usuarios", "competidores", "tatamis", "asignaciones",
        "inscripciones", "llaves",
    )

    def __init__(self):
        self.resumen = {
            s: {"nuevos": 0, "actualizados": 0, "omitidos": 0}
            for s in self.SECCIONES
        }
        self.avisos = []
        self.campeonato_nuevo = None  # True/False cuando el paquete lo trae
        # Identidades del ecosistema (`eco_sub`) pegadas a una fila local, y
        # las que no se pudieron pegar. Se cuentan aparte de las secciones
        # porque no son filas: son enlaces entre una fila y una cuenta.
        self.identidades = {"enlazadas": 0, "omitidas": 0}

    def nuevo(self, seccion):
        self.resumen[seccion]["nuevos"] += 1

    def actualizado(self, seccion):
        self.resumen[seccion]["actualizados"] += 1

    def omitido(self, seccion, aviso=None):
        self.resumen[seccion]["omitidos"] += 1
        if aviso:
            self.avisos.append(aviso)

    def aviso(self, texto):
        if texto not in self.avisos:
            self.avisos.append(texto)

    def identidad_enlazada(self):
        self.identidades["enlazadas"] += 1

    def identidad_omitida(self, texto=None):
        self.identidades["omitidas"] += 1
        if texto:
            self.aviso(texto)

    def a_dict(self):
        # Solo las secciones que movieron algo: el informe se lee de un vistazo.
        return {
            s: v for s, v in self.resumen.items()
            if v["nuevos"] or v["actualizados"] or v["omitidos"]
        }


# ═══════════════════════════════════════════════════════════════════════════
#  Importar: una función por sección, en orden de dependencia
# ═══════════════════════════════════════════════════════════════════════════

def _texto(valor, tope=None):
    texto = str(valor or "").strip()
    return texto[:tope] if tope else texto


def _nombre(valor, tope=None):
    """Un NOMBRE del paquete, normalizado como los que se escriben aquí.

    Un paquete exportado por una instalación vieja trae los nombres tal y como
    se teclearon entonces ("Juan pérez"). Si se importaran así, la lista de
    inscritos volvería a mezclar mayúsculas y minúsculas justo donde se acaba de
    ordenar. Ver `mayusculas` en `api/auth.py`.
    """
    return _texto(str(valor or "").upper(), tope)


def _fecha_de(valor):
    try:
        return date.fromisoformat(valor) if valor else None
    except (TypeError, ValueError):
        return None


def _enlazar_eco_sub(local, eco_sub, informe):
    """Pega la identidad del ecosistema a la fila local. Sin pisar ninguna.

    Tres casos, y solo el primero escribe:

      · la fila local no tiene identidad → se le pone la del paquete.
      · ya tiene OTRA → se deja la local y se avisa. No se elige por el
        importador cuál de las dos cuentas es la buena: es la misma prudencia
        de `resolver_espejo` con `correo_ocupado` —no se pisa ninguna, se para
        y que lo mire una persona—, y aquí además el enlace decide de quién
        son los resultados que suben después del evento.
      · esa identidad ya la tiene OTRA fila de esta instancia → tampoco. Dos
        filas no pueden ser la misma cuenta.
    """
    if not eco_sub:
        return
    if local.eco_sub:
        if local.eco_sub != eco_sub:
            informe.identidad_omitida(
                f"'{local.email}' ya está enlazado aquí a otra cuenta del "
                "ecosistema: se dejó el enlace local y no se aplicó el del paquete."
            )
        return
    query = Usuario.query.filter(Usuario.eco_sub == eco_sub)
    if local.id is not None:
        query = query.filter(Usuario.id != local.id)
    otro = query.first()
    if otro is not None:
        informe.identidad_omitida(
            f"La cuenta del ecosistema que trae '{local.email}' ya la tiene "
            f"'{otro.email}' en esta instancia: no se enlaza."
        )
        return
    local.eco_sub = eco_sub
    informe.identidad_enlazada()


def _importar_usuarios(lista, admin, informe):
    """Crea o actualiza maestros y jueces. Devuelve {uid del paquete: Usuario}."""
    mapa = {}
    for datos in lista or []:
        if not isinstance(datos, dict):
            continue
        uid = _texto(datos.get("uid"))
        eco_sub = _texto(datos.get("eco_sub")) or None
        email = _texto(datos.get("email")).lower()
        rol = _texto(datos.get("rol")) or "juez"

        if not email:
            informe.omitido("usuarios", "Un usuario del paquete no trae correo: se omite.")
            continue
        if rol not in ROLES_EXPORTABLES:
            informe.omitido(
                "usuarios",
                f"'{email}' viene con rol '{rol}': una importación solo crea "
                "maestros y jueces.",
            )
            continue

        local = Usuario.query.filter_by(uid=uid).first() if uid else None
        if local is None and eco_sub:
            # La identidad del ecosistema pesa más que el correo: el correo se
            # puede cambiar en el portal, el `sub` no cambia nunca.
            local = Usuario.query.filter_by(eco_sub=eco_sub).first()
            if local is not None and uid and local.uid != uid:
                informe.aviso(
                    f"'{local.email}' ya estaba aquí como la misma cuenta del "
                    "ecosistema: se vincula con la identidad del paquete."
                )
                local.uid = uid
        if local is None:
            local = Usuario.query.filter_by(email=email).first()
            if local is not None and uid:
                # Mismo correo con otra identidad: es la misma persona creada a
                # mano en las dos instancias. Se vinculan (no se duplica).
                if local.uid and local.uid != uid:
                    informe.aviso(
                        f"'{email}' ya existía aquí con otra identidad: se vincula "
                        "con la del paquete (no se duplica ni se toca su contraseña)."
                    )
                local.uid = uid

        if local is not None and (local.rol == "admin" or local.es_super):
            informe.omitido(
                "usuarios",
                f"'{email}' es administrador en esta instancia: no se modifica.",
            )
            if uid:
                mapa[uid] = local
            continue

        nombre = _nombre(datos.get("nombre"), 150) or email
        # Un paquete de una instalación anterior solo trae `club` + la
        # delegación suelta; uno nuevo trae la lista entera, con la delegación
        # de cada dojang (un maestro puede tener uno en cada ciudad).
        crudos = datos.get("clubes")
        if not isinstance(crudos, list):
            crudos = [{
                "nombre": datos.get("club"),
                "ciudad": datos.get("delegacion"),
                "pais": datos.get("pais_delegacion"),
            }]
        clubes = []
        for valor in crudos:
            if not isinstance(valor, dict):
                valor = {"nombre": valor}
            uno = _nombre(valor.get("nombre"), 80)
            if not uno or any(uno == c["nombre"] for c in clubes):
                continue
            clubes.append({
                "nombre": uno,
                # Ciudad y país NO se pasan a mayúsculas: salen del catálogo
                # geográfico y se comparan con él por valor exacto.
                "ciudad": _texto(valor.get("ciudad"), 120) or None,
                "pais": _texto(valor.get("pais"), 80) or None,
            })
        if rol == "maestro" and not clubes:
            informe.aviso(
                f"El maestro '{email}' llega sin club: asígnaselo en Usuarios "
                "antes de que inscriba alumnos."
            )

        if local is None:
            local = Usuario(
                uid=uid or nuevo_uid(),
                email=email,
                nombre=nombre,
                rol=rol,
                activo=bool(datos.get("activo", True)),
                # Workspace del admin que importa: si no, no lo vería.
                creado_por_id=admin.id,
                es_superadmin=False,
            )
            # Las contraseñas no viajan en el paquete: se deja una clave
            # aleatoria que nadie conoce. Los jueces entran con el QR de su
            # tatami; para entrar con clave, el admin la asigna en Usuarios.
            local.set_password(secrets.token_urlsafe(32))
            db.session.add(local)
            informe.nuevo("usuarios")
        else:
            local.nombre = nombre
            local.rol = rol
            local.activo = bool(datos.get("activo", True))
            informe.actualizado("usuarios")

        # Por la lista: el setter fija también el club principal y su
        # delegación (`club`, `delegacion`, `pais_delegacion`).
        local.clubes = clubes if rol == "maestro" else []

        # Si deja de poder juzgar, sus asignaciones de tatami dejan de valer
        # (misma regla que al editarlo desde Usuarios, ver api/auth.py).
        podia_juzgar = bool(local.puede_juzgar)
        local.puede_juzgar = bool(datos.get("puede_juzgar")) if rol == "maestro" else False
        if podia_juzgar and not local.puede_juzgar and local.id is not None:
            AsignacionJuez.query.filter_by(usuario_id=local.id).delete()

        _enlazar_eco_sub(local, eco_sub, informe)

        if uid:
            mapa[uid] = local

    db.session.flush()
    return mapa


def _importar_competidores(lista, admin, informe):
    """Crea o actualiza competidores. Devuelve {uid del paquete: Competidor}."""
    mapa = {}
    dueno = workspace_owner_id(admin)
    for datos in lista or []:
        if not isinstance(datos, dict):
            continue
        uid = _texto(datos.get("uid"))
        nombre = _nombre(datos.get("nombre_completo"), 200)
        documento = _texto(datos.get("documento"), 30) or None
        if not nombre:
            informe.omitido("competidores", "Un competidor del paquete no trae nombre: se omite.")
            continue

        local = Competidor.query.filter_by(uid=uid).first() if uid else None
        if local is None and documento:
            local = Competidor.query.filter_by(documento=documento).first()
            if local is not None and uid:
                local.uid = uid

        cinturon = _texto(datos.get("cinturon")) or None
        canonico, grupo = normalizar_cinturon(cinturon) if cinturon else (None, None)

        if local is None:
            local = Competidor(
                uid=uid or nuevo_uid(),
                nombre_completo=nombre,
                # Workspace del admin que importa (ver nota del módulo).
                created_by=dueno,
            )
            db.session.add(local)
            informe.nuevo("competidores")
        else:
            informe.actualizado("competidores")

        local.nombre_completo = nombre
        # El documento es único en la base: si otro atleta ya lo tiene, se
        # conserva el local y se avisa, en vez de reventar toda la importación.
        if documento and documento != local.documento:
            duenno = Competidor.query.filter(
                Competidor.documento == documento, Competidor.id != local.id
            ).first()
            if duenno is not None:
                informe.aviso(
                    f"El documento '{documento}' de {nombre} ya lo tiene "
                    f"'{duenno.nombre_completo}' en esta instancia: se dejó como estaba."
                )
                documento = local.documento
        local.documento = documento
        local.fecha_nacimiento = _fecha_de(datos.get("fecha_nacimiento"))
        local.genero = _texto(datos.get("genero")).upper() or None
        local.cinturon = canonico or cinturon
        # El grupo se deriva del cinturón; solo se acepta el del paquete si el
        # cinturón no está en el catálogo (listas viejas o de otro idioma).
        local.grupo_cinturon = grupo or (_texto(datos.get("grupo_cinturon")).upper() or None)
        local.peso = datos.get("peso") if isinstance(datos.get("peso"), (int, float)) else None
        local.club = _nombre(datos.get("club"), 200) or None
        local.categoria_especial = bool(datos.get("categoria_especial"))
        local.activo = bool(datos.get("activo", True))

        if uid:
            mapa[uid] = local

    db.session.flush()
    return mapa


def _importar_campeonato(datos, admin, informe):
    """Crea o actualiza el campeonato del paquete y lo devuelve."""
    if not isinstance(datos, dict):
        raise ErrorImportacion("El paquete no trae los datos del campeonato.")
    uid = _texto(datos.get("uid"))
    nombre = _nombre(datos.get("nombre"), 255)
    if not nombre:
        raise ErrorImportacion("El campeonato del paquete no trae nombre.")

    camp = Campeonato.query.filter_by(export_uuid=uid).first() if uid else None
    if camp is not None and not es_dueno_campeonato(admin, camp):
        raise ErrorImportacion(
            f"El campeonato '{camp.nombre}' ya existe en esta instancia pero "
            "pertenece a otro administrador.",
            status=409,
        )

    if camp is None:
        camp = Campeonato(
            export_uuid=uid or nuevo_uid(),
            created_by=admin.id,
        )
        db.session.add(camp)
        informe.campeonato_nuevo = True
    else:
        informe.campeonato_nuevo = False

    estado = _texto(datos.get("estado")) or "preparacion"
    camp.nombre = nombre
    camp.descripcion = _texto(datos.get("descripcion")) or None
    camp.fecha_inicio = _fecha_de(datos.get("fecha_inicio"))
    camp.fecha_fin = _fecha_de(datos.get("fecha_fin"))
    # La sede es un nombre a mano libre; ciudad y país salen del catálogo y se
    # comparan con él por valor exacto (ver `_validar_campo_texto`).
    camp.lugar = _nombre(datos.get("lugar"), 120) or None
    camp.ciudad = _texto(datos.get("ciudad"), 120) or None
    camp.pais = _texto(datos.get("pais"), 120) or None
    camp.estado = estado if estado in ESTADOS_CAMPEONATO else "preparacion"
    camp.activo = bool(datos.get("activo", True))
    if isinstance(datos.get("config_categorias"), dict):
        camp.config_categorias = datos["config_categorias"]

    db.session.flush()
    return camp


def _importar_tatamis(lista, camp, informe):
    """Crea o actualiza los tatamis. Devuelve {uid del paquete: Tatami}."""
    mapa = {}
    for datos in lista or []:
        if not isinstance(datos, dict):
            continue
        uid = _texto(datos.get("uid"))
        try:
            numero = int(datos.get("numero"))
        except (TypeError, ValueError):
            informe.omitido("tatamis", "Un tatami del paquete no trae número: se omite.")
            continue

        local = Tatami.query.filter_by(uid=uid).first() if uid else None
        if local is not None and local.campeonato_id != camp.id:
            # El uid pertenece a un tatami de otro campeonato: no se toca.
            local = None
        if local is None:
            local = Tatami.query.filter_by(
                campeonato_id=camp.id, numero=numero
            ).first()
            if local is not None and uid:
                local.uid = uid

        if local is None:
            local = Tatami(
                uid=uid or nuevo_uid(),
                campeonato_id=camp.id,
                numero=numero,
                activo=bool(datos.get("activo", True)),
            )
            db.session.add(local)
            informe.nuevo("tatamis")
        else:
            # El número es único dentro del campeonato: si ya lo ocupa otro
            # tatami, este conserva el suyo (renumerar rompería sus llaves).
            if numero != local.numero:
                ocupado = Tatami.query.filter(
                    Tatami.campeonato_id == camp.id,
                    Tatami.numero == numero,
                    Tatami.id != local.id,
                ).first()
                if ocupado is not None:
                    informe.aviso(
                        f"El número {numero} ya lo usa otro tatami de este "
                        f"campeonato: se conservó como tatami {local.numero}."
                    )
                    numero = local.numero
            local.numero = numero
            local.activo = bool(datos.get("activo", True))
            informe.actualizado("tatamis")

        if uid:
            mapa[uid] = local

    db.session.flush()
    return mapa


def _importar_asignaciones(lista, usuarios, tatamis, informe):
    """Asigna los jueces del paquete a sus tatamis."""
    for datos in lista or []:
        if not isinstance(datos, dict):
            continue
        usuario = usuarios.get(_texto(datos.get("usuario_uid")))
        tatami = tatamis.get(_texto(datos.get("tatami_uid")))
        rol = _texto(datos.get("rol_tatami"))
        if usuario is None or tatami is None:
            informe.omitido(
                "asignaciones",
                "Una asignación del paquete apunta a un juez o tatami que no "
                "viene incluido: se omite.",
            )
            continue
        if not usuario.puede_ser_juez:
            informe.omitido(
                "asignaciones",
                f"'{usuario.email}' no puede juzgar (es maestro sin permiso): "
                "no se le asigna tatami.",
            )
            continue

        existente = AsignacionJuez.query.filter_by(
            usuario_id=usuario.id, tatami_id=tatami.id
        ).first()
        # Un juez solo puede estar en un tatami: si venía de otro, se mueve.
        otra = AsignacionJuez.query.filter(
            AsignacionJuez.usuario_id == usuario.id,
            AsignacionJuez.tatami_id != tatami.id,
        ).first()
        if otra is not None:
            db.session.delete(otra)

        # El rol (árbitro, j1…) es único por tatami: si ya lo ocupa otro, este
        # se queda sin asignar en vez de romper el cuadro de jueces.
        ocupado = AsignacionJuez.query.filter(
            AsignacionJuez.tatami_id == tatami.id,
            AsignacionJuez.rol_tatami == rol,
            AsignacionJuez.usuario_id != usuario.id,
        ).first()
        if ocupado is not None:
            informe.omitido(
                "asignaciones",
                f"En el tatami {tatami.numero} el rol '{rol}' ya está ocupado: "
                f"'{usuario.email}' quedó sin asignar.",
            )
            continue

        if existente is None:
            db.session.add(AsignacionJuez(
                uid=_texto(datos.get("uid")) or nuevo_uid(),
                usuario_id=usuario.id,
                tatami_id=tatami.id,
                rol_tatami=rol,
                nombre_display=_nombre(datos.get("nombre_display"), 150) or usuario.nombre,
            ))
            informe.nuevo("asignaciones")
        else:
            existente.rol_tatami = rol
            existente.nombre_display = _nombre(datos.get("nombre_display"), 150) or usuario.nombre
            informe.actualizado("asignaciones")

    db.session.flush()


def _importar_inscripciones(lista, camp, competidores, usuarios, admin, informe):
    """Inscribe en el campeonato a los competidores del paquete."""
    for datos in lista or []:
        if not isinstance(datos, dict):
            continue
        competidor = competidores.get(_texto(datos.get("competidor_uid")))
        if competidor is None:
            informe.omitido(
                "inscripciones",
                "Una inscripción del paquete apunta a un competidor que no "
                "viene incluido: se omite.",
            )
            continue

        uid = _texto(datos.get("uid"))
        local = Inscripcion.query.filter_by(uid=uid).first() if uid else None
        if local is None:
            local = Inscripcion.query.filter_by(
                campeonato_id=camp.id, competidor_id=competidor.id
            ).first()
            if local is not None and uid:
                local.uid = uid

        estado = _texto(datos.get("estado")) or "aceptada"
        if estado not in ESTADOS_INSCRIPCION:
            estado = "aceptada"
        solicitante = usuarios.get(_texto(datos.get("solicitante_uid")))

        if local is None:
            local = Inscripcion(
                uid=uid or nuevo_uid(),
                campeonato_id=camp.id,
                competidor_id=competidor.id,
            )
            db.session.add(local)
            informe.nuevo("inscripciones")
        else:
            informe.actualizado("inscripciones")

        modalidades = datos.get("modalidades")
        local.modalidades = modalidades if isinstance(modalidades, list) else None
        local.peso = datos.get("peso") if isinstance(datos.get("peso"), (int, float)) else None
        local.grupo_cinturon = _texto(datos.get("grupo_cinturon")).upper() or None
        local.estado = estado
        local.motivo_rechazo = _texto(datos.get("motivo_rechazo")) or None
        # Sin solicitante identificable, la inscripción queda a nombre del
        # admin que importa (así aparece en su workspace).
        local.created_by = solicitante.id if solicitante is not None else admin.id

    db.session.flush()


def _importar_llaves(lista, camp, tatamis, admin, informe):
    """Crea o actualiza las llaves.

    Una llave local activa o terminada NUNCA se sobrescribe, ni siquiera con
    `forzar`: guarda resultados del evento y no habría forma de recuperarlos.
    `forzar` solo sirve para autorizar la importación en sí (ver `importar`).
    """
    for datos in lista or []:
        if not isinstance(datos, dict):
            continue
        nombre = _texto(datos.get("nombre"), 120)
        estructura = datos.get("estructura")
        if not nombre or not isinstance(estructura, dict):
            informe.omitido("llaves", "Una llave del paquete llega incompleta: se omite.")
            continue

        uid = _texto(datos.get("uid"))
        seccion = _texto(datos.get("seccion_clave"), 300) or None
        local = Llave.query.filter_by(uid=uid).first() if uid else None
        if local is not None and local.campeonato_id != camp.id:
            local = None
        if local is None and seccion:
            local = Llave.query.filter_by(
                campeonato_id=camp.id, seccion_clave=seccion
            ).first()
            if local is not None and uid:
                local.uid = uid

        if local is not None and local.estado_norm != "pendiente":
            informe.omitido(
                "llaves",
                f"La llave '{local.nombre}' ya está {local.estado_norm} aquí: "
                "no se sobrescribe.",
            )
            continue

        tatami = tatamis.get(_texto(datos.get("tatami_uid")))
        tipo = _texto(datos.get("tipo")) or "combate"
        estado = _texto(datos.get("estado")) or "pendiente"

        if local is None:
            local = Llave(
                uid=uid or nuevo_uid(),
                campeonato_id=camp.id,
                estructura=estructura,
                nombre=nombre,
                created_by=admin.id,
            )
            db.session.add(local)
            informe.nuevo("llaves")
        else:
            informe.actualizado("llaves")

        local.nombre = nombre
        local.descripcion = _texto(datos.get("descripcion")) or None
        local.tipo = tipo if tipo in ("combate", "figuras") else "combate"
        local.estado = estado if estado in ("pendiente", "activa", "terminada") else "pendiente"
        local.seccion_clave = seccion
        local.tatami_id = tatami.id if tatami is not None else None
        local.estructura = estructura

    db.session.flush()


def _limpiar_para_reemplazar(camp, informe):
    """Modo «reemplazar»: deja el campeonato como lo diga el paquete.

    Borra sus llaves e inscripciones locales, EXCEPTO las llaves ya activas o
    terminadas: esas guardan resultados del evento y no se destruyen nunca.
    Los competidores y los usuarios tampoco se tocan: viven fuera del
    campeonato y pueden estar en otros.
    """
    disputadas = Llave.query.filter(
        Llave.campeonato_id == camp.id,
        Llave.estado.in_(("activa", "terminada")),
    ).count()
    llaves = Llave.query.filter(
        Llave.campeonato_id == camp.id,
        db.or_(Llave.estado.is_(None), Llave.estado == "pendiente"),
    )
    borradas = llaves.count()
    llaves.delete(synchronize_session=False)

    inscripciones = Inscripcion.query.filter_by(campeonato_id=camp.id)
    borradas_ins = inscripciones.count()
    inscripciones.delete(synchronize_session=False)
    db.session.flush()

    if borradas or borradas_ins:
        informe.aviso(
            f"Modo reemplazar: se borraron {borradas_ins} inscripción(es) y "
            f"{borradas} llave(s) pendiente(s) que ya había aquí."
        )
    if disputadas:
        informe.aviso(
            f"{disputadas} llave(s) ya disputada(s) se conservaron: una "
            "importación nunca borra resultados."
        )


def _evento_ya_iniciado(camp):
    """True si el campeonato local ya tiene llaves disputándose o disputadas."""
    if camp is None or camp.id is None:
        return False
    return Llave.query.filter(
        Llave.campeonato_id == camp.id,
        Llave.estado.in_(("activa", "terminada")),
    ).count() > 0


# ═══════════════════════════════════════════════════════════════════════════
#  Endpoint de importación (vista previa y real comparten camino)
# ═══════════════════════════════════════════════════════════════════════════

def _leer_paquete():
    """Paquete subido como archivo (`file`) o como cuerpo JSON."""
    archivo = request.files.get("file")
    if archivo is not None:
        crudo = archivo.read(MAX_BYTES_PAQUETE + 1)
        if len(crudo) > MAX_BYTES_PAQUETE:
            raise ErrorImportacion(
                f"El archivo supera el tope de {MAX_BYTES_PAQUETE // (1024 * 1024)} MB."
            )
        try:
            return json.loads(crudo.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ErrorImportacion("El archivo no es un JSON válido.")
    cuerpo = request.get_json(silent=True)
    if cuerpo is None:
        raise ErrorImportacion("No se recibió el paquete.")
    return cuerpo


def _opcion(nombre, defecto=""):
    """Opción enviada como campo de formulario (multipart) o en el JSON."""
    if nombre in request.form:
        return request.form.get(nombre, defecto)
    cuerpo = request.get_json(silent=True)
    if isinstance(cuerpo, dict) and nombre in cuerpo:
        return cuerpo[nombre]
    return defecto


def _es_si(valor):
    return str(valor).lower() in ("1", "true", "si", "yes")


@sincronizacion_bp.route("/ultima-bajada", methods=["GET"])
@jwt_required()
def ultima_bajada():
    """
    GET /api/sincronizacion/ultima-bajada
    De cuándo es la copia que corre en esta instalación, qué trae, y si
    conviene volver a bajarla (`avisar`). Con `hay: false` mientras nadie
    haya importado un campeonato — el estado normal de una instalación recién
    montada, no un error.
    """
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Solo administradores"}), 403
    return jsonify(estado_bajada()), 200


@sincronizacion_bp.route("/importar", methods=["POST"])
@jwt_required()
@limitar(10, 60, nombre="sincronizacion-importar")
def importar():
    """
    POST /api/sincronizacion/importar
    Campos (multipart o JSON): `file` (el paquete), `vista_previa`, `modo`
    (fusionar|reemplazar) y `forzar` (sobrescribir llaves ya disputadas).

    Con `vista_previa` se ejecuta la importación completa y se REVIERTE al
    final: el informe devuelto es exactamente lo que pasaría al confirmar.
    """
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Solo administradores"}), 403

    try:
        paquete = _leer_paquete()
        if not isinstance(paquete, dict):
            raise ErrorImportacion("El paquete no tiene el formato esperado.")
        formato = paquete.get("formato")
        if formato not in FORMATOS_VALIDOS:
            raise ErrorImportacion(
                "El archivo no es un paquete de DINAMYT "
                f"(formato recibido: {formato or 'ninguno'})."
            )

        vista_previa = _es_si(_opcion("vista_previa", "0"))
        forzar = _es_si(_opcion("forzar", "0"))
        modo = str(_opcion("modo", "fusionar") or "fusionar")
        if modo not in MODOS_IMPORTACION:
            raise ErrorImportacion(f"Modo de importación inválido: '{modo}'.")

        informe = Informe()
        respuesta = _ejecutar_importacion(paquete, formato, modo, forzar, admin, informe)

        if vista_previa:
            # Nada de lo anterior llegó a confirmarse: se descarta entero.
            db.session.rollback()
        else:
            db.session.commit()
            # Y queda escrito de cuándo es esta copia. Solo el paquete del
            # campeonato: ver `anotar` en `app/ultima_bajada.py`.
            if formato == FORMATO_CAMPEONATO:
                anotar_bajada(
                    paquete, formato, admin,
                    campeonato_nombre=(respuesta.get("campeonato") or {}).get("nombre"),
                )

        respuesta.update({
            "vista_previa": vista_previa,
            "formato": formato,
            "modo": modo,
            "exportado_at": paquete.get("exportado_at"),
            "origen": paquete.get("origen"),
            "resumen": informe.a_dict(),
            "identidades": informe.identidades,
            "avisos": informe.avisos,
        })
        return jsonify(respuesta), 200

    except ErrorImportacion as e:
        db.session.rollback()
        return jsonify({"error": e.mensaje}), e.status
    except Exception:
        # Cualquier fallo inesperado deja la base intacta.
        db.session.rollback()
        raise


def _ejecutar_importacion(paquete, formato, modo, forzar, admin, informe):
    """Aplica el paquete sobre la base. El llamador decide commit o rollback."""
    if formato == FORMATO_USUARIOS:
        _importar_usuarios(paquete.get("usuarios"), admin, informe)
        return {"message": "Usuarios del paquete procesados."}

    if formato == FORMATO_COMPETIDORES:
        _importar_competidores(paquete.get("competidores"), admin, informe)
        return {"message": "Competidores del paquete procesados."}

    # ── Paquete de campeonato: orden fijo de dependencias ──
    usuarios = _importar_usuarios(paquete.get("usuarios"), admin, informe)
    camp = _importar_campeonato(paquete.get("campeonato"), admin, informe)

    # Freno: si aquí ya se está compitiendo, importar podría pisar resultados.
    trae_competencia = bool(paquete.get("llaves") or paquete.get("inscripciones"))
    if trae_competencia and not informe.campeonato_nuevo and _evento_ya_iniciado(camp):
        if not forzar:
            raise ErrorImportacion(
                f"El campeonato '{camp.nombre}' ya tiene llaves activas o "
                "terminadas en esta instancia: importar podría pisar resultados. "
                "Confirma explícitamente si quieres continuar.",
                status=409,
            )
        informe.aviso(
            "El evento ya había empezado aquí y se importó de todas formas "
            "(confirmado por el administrador)."
        )

    if modo == "reemplazar" and not informe.campeonato_nuevo:
        _limpiar_para_reemplazar(camp, informe)

    tatamis = _importar_tatamis(paquete.get("tatamis"), camp, informe)
    _importar_asignaciones(paquete.get("asignaciones"), usuarios, tatamis, informe)
    competidores = _importar_competidores(paquete.get("competidores"), admin, informe)
    _importar_inscripciones(
        paquete.get("inscripciones"), camp, competidores, usuarios, admin, informe
    )
    _importar_llaves(paquete.get("llaves"), camp, tatamis, admin, informe)

    nuevos_usuarios = informe.resumen["usuarios"]["nuevos"]
    if nuevos_usuarios:
        informe.aviso(
            f"{nuevos_usuarios} usuario(s) se crearon SIN contraseña: los jueces "
            "entran con el QR de su tatami; si alguien necesita entrar con clave, "
            "asígnasela desde Usuarios."
        )

    return {
        "message": (
            f"Campeonato '{camp.nombre}' "
            + ("importado" if informe.campeonato_nuevo else "actualizado")
        ),
        "campeonato": {
            "id": camp.id,
            "nombre": camp.nombre,
            "uid": camp.export_uuid,
            "nuevo": informe.campeonato_nuevo,
        },
    }
