"""
API: Autenticación
Endpoints: login, register, me
"""

from datetime import datetime, timedelta, timezone

from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token,
    jwt_required,
    get_jwt_identity,
    set_access_cookies,
    unset_jwt_cookies,
    verify_jwt_in_request,
)
from ..espejo import es_super, resolver_espejo
from ..extensions import db
from ..geo import pais_de_ciudad, pais_valido
from ..identidad import abre_campeonatos, hay_ecosistema, verificar_pase
from ..models.asignacion import AsignacionJuez
from ..models.usuario import ROLES_VALIDOS, Usuario
from ..security import (
    intento_bloqueado,
    ip_cliente,
    limpiar_intentos,
    segundos_restantes,
)
from .scoping import (
    es_dueno_usuario,
    require_admin,
    usuario_actual,
    workspace_owner_id,
)

auth_bp = Blueprint("auth", __name__)

# Límite de intentos de login: 5 por correo y 20 por IP cada 5 minutos
LOGIN_MAX_POR_EMAIL = 5
LOGIN_MAX_POR_IP = 20
LOGIN_VENTANA_SEG = 300

# Tope de caracteres del club (espejo del competidor).
CLUB_MAX = 80
DELEGACION_MAX = 120
# Cuántos dojangs puede dirigir un maestro. No hay un límite "real": es un
# tope de cordura para que un cliente no llene la columna JSON.
CLUBES_MAX = 20


def mayusculas(valor):
    """Un NOMBRE, tal y como se guarda: en MAYÚSCULAS.

    Nombres de personas y de clubes los teclea gente distinta en momentos
    distintos, y en la misma lista salían "Juan pérez", "JUAN PEREZ" y "Juan
    Pérez". Normalizándolos al guardar, la lista de inscritos, la llave, el acta
    y la planilla dicen todos lo mismo sin que ninguna pantalla tenga que
    acordarse de convertirlo (el frontend lo aplica también mientras se escribe,
    ver frontend/src/lib/texto.ts).

    `str.upper()` de Python respeta Unicode: josé → JOSÉ, ñuñez → ÑUÑEZ. El
    acento y la eñe son parte del nombre de la persona.
    """
    return None if valor is None else str(valor).upper()


def _validar_clubes(data):
    """(clubes, error): los dojangs del maestro, limpios y validados.

    Cada uno con SU delegación, porque los dojangs de un mismo maestro suelen
    estar en ciudades distintas:

        [{"nombre": "DOJANG SUR", "ciudad": "Cali", "pais": "Colombia"}, ...]

    Acepta las tres formas del cuerpo, de la más nueva a la más vieja:
      · `clubes: [{"nombre", "ciudad", "pais"}, ...]` — la de ahora
      · `clubes: ["DOJANG SUR", ...]` — nombres sueltos, sin delegación
      · `club: "DOJANG SUR"` (+ `delegacion`/`pais_delegacion` arriba) — la de
        siempre, que siguen usando el importador de paquetes y cualquier
        cliente que no se haya actualizado

    Devuelve `None` (y no `[]`) cuando el cuerpo no menciona ninguna: quien
    llama distingue así "no me hables del club" de "déjalo sin clubes".
    """
    if "clubes" in data:
        crudos = data.get("clubes")
        if crudos is None:
            crudos = []
        if not isinstance(crudos, list):
            return None, "Los clubes deben venir como una lista."
    elif "club" in data:
        # Forma antigua: el club suelto se queda con la delegación que venga
        # al nivel del usuario, que era la única que había.
        crudos = [{
            "nombre": data.get("club"),
            "ciudad": data.get("delegacion"),
            "pais": data.get("pais_delegacion"),
        }]
    else:
        return None, None

    limpios = []
    for valor in crudos:
        if isinstance(valor, dict):
            crudo_nombre = valor.get("nombre")
            crudo_ciudad = valor.get("ciudad")
            crudo_pais = valor.get("pais")
        else:
            crudo_nombre, crudo_ciudad, crudo_pais = valor, None, None

        nombre = mayusculas(str(crudo_nombre or "").strip())
        if not nombre:
            continue
        if len(nombre) > CLUB_MAX:
            return None, f"El club no puede superar {CLUB_MAX} caracteres."
        # Sin repetidos: el mismo dojang dos veces no significa nada y saldría
        # duplicado en el desplegable al inscribir.
        if any(nombre == c["nombre"] for c in limpios):
            continue

        ciudad, pais, error = _validar_delegacion(crudo_ciudad, crudo_pais)
        if error:
            return None, error
        limpios.append({"nombre": nombre, "ciudad": ciudad, "pais": pais})

    if len(limpios) > CLUBES_MAX:
        return None, f"Un maestro no puede tener más de {CLUBES_MAX} clubes."
    return limpios, None


def _validar_delegacion(valor, pais_valor=None):
    """(delegacion, pais, error): delegación (ciudad) recortada + país.

    El país lo elige el admin de un catálogo y debe ser uno válido. Si llega un
    país reconocido se usa tal cual; si no llega (o no se reconoce) se deriva de
    la ciudad para no perder el dato en datos viejos o clientes antiguos.
    """
    delegacion = str(valor or "").strip()
    if len(delegacion) > DELEGACION_MAX:
        return None, None, f"La delegación no puede superar {DELEGACION_MAX} caracteres."
    pais = pais_valido(pais_valor) or pais_de_ciudad(delegacion)
    return (delegacion or None), pais, None


@auth_bp.route("/login", methods=["POST"])
def login():
    """
    POST /api/auth/login
    Body: { "email": "...", "password": "..." }
    Returns: { "token": "...", "user": {...} }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Datos requeridos"}), 400

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "Email y contraseña son requeridos"}), 400

    ip = ip_cliente()
    clave_email = f"login:{email}"
    clave_ip = f"login-ip:{ip}"
    if (
        intento_bloqueado(clave_email, LOGIN_MAX_POR_EMAIL, LOGIN_VENTANA_SEG)
        or intento_bloqueado(clave_ip, LOGIN_MAX_POR_IP, LOGIN_VENTANA_SEG)
    ):
        espera = max(segundos_restantes(clave_email), segundos_restantes(clave_ip))
        return jsonify({
            "error": f"Demasiados intentos de inicio de sesión. Intenta de nuevo en {max(espera, 30)} segundos."
        }), 429

    user = Usuario.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "Credenciales inválidas"}), 401

    # Login correcto: limpiar contador de intentos fallidos
    limpiar_intentos(clave_email)

    if not user.activo:
        return jsonify({"error": "Usuario desactivado"}), 403

    # Migración transparente del costo de bcrypt: si el hash se creó con más
    # rondas de las configuradas (p. ej. el admin sembrado con 12), se vuelve a
    # hashear con BCRYPT_ROUNDS para que los siguientes logins sean más rápidos.
    if user.necesita_rehash():
        user.set_password(password)
        db.session.commit()

    # Crear token JWT con identity como string del user ID
    token = create_access_token(
        identity=str(user.id),
        additional_claims={
            "rol": user.rol,
            "nombre": user.nombre,
            "email": user.email,
        },
    )

    # La sesión del navegador va en cookie httpOnly; el token sigue en el
    # cuerpo para las pantallas de tatami y cualquier cliente que no sea
    # navegador (ahí el JWT viaja por cabecera, como siempre).
    respuesta = jsonify({
        "token": token,
        "user": user.to_dict(),
    })
    set_access_cookies(respuesta, token)
    return respuesta, 200


def _token_de_cabecera():
    """El token del `Authorization: Bearer …`, o None."""
    partes = (request.headers.get("Authorization") or "").split()
    if len(partes) == 2 and partes[0].lower() == "bearer":
        return partes[1]
    return None


def _respuesta_con_cookie(user, horas=None):
    """La respuesta de sesión abierta, con la cookie httpOnly puesta."""
    token = create_access_token(
        identity=str(user.id),
        additional_claims={
            "rol": user.rol,
            "nombre": user.nombre,
            "email": user.email,
        },
        expires_delta=timedelta(hours=horas) if horas else None,
    )
    respuesta = jsonify({"user": user.to_dict()})
    set_access_cookies(respuesta, token)
    return respuesta


# Lo que dura una sesión abierta con un pase del ecosistema.
#
# No son las 72 h del login propio, y la diferencia importa: el pase del
# ecosistema se puede revocar (cerrar sesión en todos lados), pero esta cookie
# ya no depende de él. Doce horas cubren una jornada de competencia entera y
# acotan cuánto sobrevive aquí una sesión que allá ya se cerró. El QR del juez
# conserva las suyas: se reparte por la mañana y tiene que aguantar el fin de
# semana sin internet.
SESION_SSO_HORAS = 12

# Qué se contesta cuando el pase es válido pero la persona no abre la consola.
MOTIVOS_SSO = {
    "sin_plan": (
        "Tu club no tiene Campeonatos en su plan. Escríbele a tu maestro o "
        "entra a DINAMYT para ver el tuyo.",
        403,
    ),
    "sin_consola": (
        "Tu cuenta de DINAMYT no administra ni juzga campeonatos. Lo tuyo "
        "—tus inscripciones y tus resultados— se ve desde el portal.",
        403,
    ),
    "correo_ocupado": (
        "Ese correo ya está enlazado con otra cuenta de DINAMYT. Escribe a "
        "soporte@dinamyt.org para que lo revisen.",
        409,
    ),
    "pase_incompleto": ("El pase no trae los datos necesarios.", 401),
    "desactivado": ("Tu usuario está desactivado en Campeonatos.", 403),
}


def _sesion_con_pase(pase):
    """Abre la sesión de Campeonatos a partir de un pase del ecosistema."""
    # El super-admin del ecosistema no pertenece a ningún club, así que su pase
    # no trae `app_scopes`: exigirle el plan lo dejaba fuera de su propia
    # plataforma. Es la misma excepción que ya hace el portal para enseñarle el
    # botón.
    if not abre_campeonatos(pase) and not es_super(pase):
        return _error_sso("sin_plan")

    user, motivo = resolver_espejo(pase, _token_de_cabecera())
    if user is None:
        return _error_sso(motivo or "pase_incompleto")
    if not user.activo:
        return _error_sso("desactivado")

    return _respuesta_con_cookie(user, SESION_SSO_HORAS), 200


def _error_sso(motivo):
    texto, codigo = MOTIVOS_SSO.get(motivo, ("No se pudo abrir la sesión.", 403))
    # `motivo` viaja aparte del texto para que el frontend pueda decidir qué
    # ofrecer —volver al portal, avisar al maestro— sin leer el mensaje.
    return jsonify({"error": texto, "motivo": motivo}), codigo


@auth_bp.route("/sesion", methods=["POST"])
def abrir_sesion():
    """
    POST /api/auth/sesion — Canjea un token de cabecera por la cookie httpOnly.

    **Dos puertas, y esta es la que une DINAMYT con Campeonatos:**

    · **El pase del ecosistema** (RS256, firmado por `ecosystem-api`). Es el
      salto desde el portal: se verifica contra el JWKS, se resuelve el espejo
      local y se abre sesión aquí sin pedir una segunda contraseña. Sin
      `ECOSYSTEM_JWKS_URL` esta puerta sencillamente no existe y todo sigue
      como antes — que es el modo local del día del campeonato.

    · **El token propio** (HS256), que es el acceso por QR del juez: el enlace
      trae el token en el fragmento de la URL y aquí se cambia por la cookie,
      para que no se quede en localStorage al alcance de cualquier script.

    Se prueba primero el pase porque es el único que se puede distinguir sin
    ambigüedad (firma RS256 y emisor propio); si no lo es, se cae al camino de
    siempre, que responde exactamente lo que respondía.

    Sin limitador propio a propósito: los dos caminos verifican una firma antes
    de tocar la base, y el techo global de `/api/*` ya cubre el martilleo. Un
    límite por IP aquí castigaría a un gimnasio entero detrás de un solo router
    el día que veinte jueces entran por QR a la vez.
    """
    pase = verificar_pase(_token_de_cabecera())
    if pase:
        return _sesion_con_pase(pase)

    # Camino de siempre. `verify_jwt_in_request` responde 401/422 por su cuenta
    # si no hay token propio válido.
    verify_jwt_in_request()
    user = usuario_actual()
    if not user or not user.activo:
        return jsonify({"error": "Usuario no válido"}), 401

    return _respuesta_con_cookie(user), 200


@auth_bp.route("/socket-ticket", methods=["POST"])
@jwt_required()
def socket_ticket():
    """
    POST /api/auth/socket-ticket — Token corto para abrir el Socket.IO.

    El socket manda su credencial en el payload `auth`, así que necesita un
    valor que JavaScript pueda leer — justo lo que la cookie httpOnly ya no
    deja. En vez de exponer la sesión de 72 h se entrega uno de 12: cubre una
    jornada de competencia (incluidas las reconexiones por caídas de WiFi, que
    reusan el mismo payload) y caduca esa noche.

    Vive solo en memoria del navegador, así que se pierde al recargar. Es la
    diferencia con lo de antes: el token de 72 h estaba en localStorage, y ahí
    seguía disponible para cualquier script hasta que expiraba.
    """
    from datetime import timedelta

    user = usuario_actual()
    if not user or not user.activo:
        return jsonify({"error": "Usuario no válido"}), 401

    ticket = create_access_token(
        identity=str(user.id),
        additional_claims={
            "rol": user.rol,
            "nombre": user.nombre,
            "email": user.email,
        },
        expires_delta=timedelta(hours=12),
    )
    return jsonify({"ticket": ticket}), 200


@auth_bp.route("/logout", methods=["POST"])
def logout():
    """
    POST /api/auth/logout — Borra la cookie de sesión.

    Sin @jwt_required a propósito: si la cookie ya caducó, cerrar sesión tiene
    que funcionar igual. Exigir un token válido para poder salir deja al usuario
    atrapado con una sesión rota que no puede ni cerrar.

    ── Por qué la respuesta lleva `portal` ──────────────────────────────────

    Quien salta desde DINAMYT (§4.13) tiene DOS sesiones: esta cookie y la del
    portal, que vive en otro dominio y solo se cierra pasando por él. Cerrando
    solo la de aquí, el portal sigue reconociendo a la persona y el siguiente
    «Entrar a Campeonatos» la mete dentro sin enseñarle una sola pantalla — que
    por fuera se ve exactamente como si salir no funcionara.

    Quién sabe si hay portal es el **servidor**, no el navegador: es la misma
    variable que habilita el pase (`ECOSYSTEM_JWKS_URL`). Guardarlo en el
    navegador es lo que le costó dos pulsaciones a Membresías (§5.12): una
    marca del `localStorage` se pierde sola y no había forma de notarlo.
    """
    respuesta = jsonify({"ok": True, "portal": hay_ecosistema()})
    unset_jwt_cookies(respuesta)
    return respuesta, 200


@auth_bp.route("/register", methods=["POST"])
@jwt_required()
def register():
    """
    POST /api/auth/register (solo Admin)
    Body: { "email": "...", "password": "...", "nombre": "...", "rol": "juez" }
    """
    # Verificar que el usuario actual sea admin
    current_user = require_admin()
    if not current_user:
        return jsonify({"error": "Solo administradores pueden crear usuarios"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"error": "Datos requeridos"}), 400

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    nombre = mayusculas(data.get("nombre", "").strip())
    rol = data.get("rol", "juez")

    if not email or not password or not nombre:
        return jsonify({"error": "Email, contraseña y nombre son requeridos"}), 400

    if rol not in ROLES_VALIDOS:
        return jsonify({"error": "Rol debe ser 'admin', 'maestro' o 'juez'"}), 400

    # Jerarquía: solo el superadmin crea administradores. Un admin normal
    # agrega jueces y maestros a SU workspace (los demás admins no los ven).
    if rol == "admin" and not current_user.es_super:
        return jsonify({
            "error": "Solo el superadministrador puede crear administradores"
        }), 403

    # Clubes y permiso de juez: solo tienen sentido para un maestro.
    clubes, error = _validar_clubes(data)
    if error:
        return jsonify({"error": error}), 400
    if rol == "maestro" and not clubes:
        return jsonify({"error": "El club es obligatorio para un maestro"}), 400
    puede_juzgar = bool(data.get("puede_juzgar")) if rol == "maestro" else False

    if Usuario.query.filter_by(email=email).first():
        return jsonify({"error": f"El email '{email}' ya está registrado"}), 409

    new_user = Usuario(
        email=email,
        nombre=nombre,
        rol=rol,
        activo=True,
        creado_por_id=current_user.id,
        puede_juzgar=puede_juzgar,
    )
    # Por la lista y nunca campo a campo: el setter fija además el club
    # principal y su delegación, que es lo que leen `club`, `delegacion` y
    # `pais_delegacion`. La delegación suelta del cuerpo (clientes antiguos) ya
    # viene doblada dentro de la lista, ver `_validar_clubes`.
    new_user.clubes = clubes if rol == "maestro" else []
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()

    return jsonify({
        "message": f"Usuario '{nombre}' creado exitosamente",
        "user": new_user.to_dict(),
    }), 201


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    """
    GET /api/auth/me
    Retorna datos del usuario autenticado.
    """
    current_user_id = get_jwt_identity()
    user = Usuario.query.get(int(current_user_id))
    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404

    # Incluir tatamis asignados si es juez (o un maestro que también juzga)
    data = user.to_dict()
    if user.puede_ser_juez:
        from ..models.asignacion import AsignacionJuez
        asignaciones = AsignacionJuez.query.filter_by(usuario_id=user.id).all()
        data["tatamis_asignados"] = [a.to_dict() for a in asignaciones]

    return jsonify(data), 200


@auth_bp.route("/users", methods=["GET"])
@jwt_required()
def list_users():
    """
    GET /api/auth/users (solo Admin)
    Superadmin: todos los usuarios. Admin normal: solo los que él creó
    (sus jueces) y él mismo — los usuarios de otros admins no se ven.
    """
    current_user = require_admin()
    if not current_user:
        return jsonify({"error": "Solo administradores"}), 403

    include_inactive = request.args.get("include_inactive") == "1"
    query = Usuario.query
    if not current_user.es_super:
        query = query.filter(db.or_(
            Usuario.creado_por_id == current_user.id,
            Usuario.id == current_user.id,
        ))
    if not include_inactive:
        query = query.filter_by(activo=True)

    users = query.order_by(Usuario.nombre).all()
    return jsonify([u.to_dict(include_asignaciones=True) for u in users]), 200


@auth_bp.route("/clubes", methods=["GET"])
@jwt_required()
def listar_clubes():
    """
    GET /api/auth/clubes[?detalle=1] (solo Admin)

    Clubes distintos de los maestros del workspace. Sin `detalle` devuelve solo
    los NOMBRES, que es lo que necesita el desplegable de club al inscribir
    competidores ("Independiente"/"Otro…" los agrega el cliente).

    Con `detalle=1` devuelve además la delegación de cada uno
    ({nombre, ciudad, pais}), para que al asignarle a un maestro un club que ya
    existe se rellene la ciudad que ese club ya tiene en vez de volver a
    elegirla —y acabar con el mismo dojang en dos ciudades distintas—.
    """
    current_user = require_admin()
    if not current_user:
        return jsonify({"error": "Solo administradores"}), 403

    query = Usuario.query.filter(Usuario.rol == "maestro")
    if not current_user.es_super:
        query = query.filter(Usuario.creado_por_id == current_user.id)

    # TODOS los clubes de cada maestro, no solo el principal: un maestro con
    # dos dojangs aporta los dos. Y un mismo club dirigido por varios maestros
    # aparece una sola vez — se queda la primera ficha que traiga delegación,
    # porque la de un maestro que la dejó en blanco no aporta nada.
    por_nombre = {}
    for usuario in query.all():
        for club in usuario.clubes:
            nombre = club["nombre"].strip()
            if not nombre:
                continue
            previo = por_nombre.get(nombre.casefold())
            if previo is None or (not previo["ciudad"] and club["ciudad"]):
                por_nombre[nombre.casefold()] = {**club, "nombre": nombre}

    clubes = sorted(por_nombre.values(), key=lambda c: c["nombre"].lower())
    if request.args.get("detalle") == "1":
        return jsonify(clubes), 200
    return jsonify([c["nombre"] for c in clubes]), 200


@auth_bp.route("/users/<int:user_id>", methods=["PUT"])
@jwt_required()
def update_user(user_id):
    """
    PUT /api/auth/users/:id (solo Admin)
    Body opcional: { "nombre", "email", "password", "activo", "rol" }
    Permite al administrador corregir correo, restablecer contraseña,
    cambiar el rol (admin/juez) o activar/desactivar un usuario.
    Un admin normal solo puede editar los usuarios que él creó.
    """
    current_user = require_admin()
    if not current_user:
        return jsonify({"error": "Solo administradores"}), 403

    user = Usuario.query.get(user_id)
    # 404 también cuando el usuario es de otro workspace (no revelar existencia)
    if not user or not es_dueno_usuario(current_user, user):
        return jsonify({"error": "Usuario no encontrado"}), 404

    # El superadmin solo se edita a sí mismo (nadie lo degrada ni desactiva)
    if user.es_super and user.id != current_user.id:
        return jsonify({
            "error": "El superadministrador no puede ser modificado por otros usuarios"
        }), 403

    data = request.get_json() or {}

    if data.get("nombre"):
        user.nombre = mayusculas(data["nombre"].strip())

    if data.get("email"):
        email = data["email"].strip().lower()
        existente = Usuario.query.filter(
            Usuario.email == email, Usuario.id != user.id
        ).first()
        if existente:
            return jsonify({"error": f"El email '{email}' ya está registrado"}), 409
        user.email = email

    if data.get("password"):
        if len(data["password"]) < 6:
            return jsonify({"error": "La contraseña debe tener al menos 6 caracteres"}), 400
        user.set_password(data["password"])

    if data.get("rol"):
        nuevo_rol = data["rol"]
        if nuevo_rol not in ROLES_VALIDOS:
            return jsonify({"error": "Rol inválido (debe ser 'admin', 'maestro' o 'juez')"}), 400
        if user.id == current_user.id and nuevo_rol != "admin":
            return jsonify({"error": "No puedes quitarte tu propio rol de administrador"}), 400
        # Jerarquía: solo el superadmin promueve o degrada ADMINISTRADORES.
        # Alternar entre juez y maestro sí lo puede hacer un admin normal en su
        # propio workspace.
        toca_admin = "admin" in (nuevo_rol, user.rol)
        if nuevo_rol != user.rol and toca_admin and not current_user.es_super:
            return jsonify({
                "error": "Solo el superadministrador puede cambiar el rol de administrador"
            }), 403
        if nuevo_rol != user.rol:
            if nuevo_rol == "admin":
                # Un admin no actúa como juez de tatami: liberar sus asignaciones
                AsignacionJuez.query.filter_by(usuario_id=user.id).delete()
            if nuevo_rol != "maestro":
                # Al dejar de ser maestro, los clubes (con su delegación) y el
                # permiso de juez dejan de aplicar. El setter limpia también
                # `club`, `delegacion` y `pais_delegacion`.
                user.clubes = []
                user.puede_juzgar = False
            user.rol = nuevo_rol

    # Clubes del maestro, cada uno con su delegación (los fija/edita el admin).
    # Se acepta la lista completa o el `club` suelto de siempre; ver
    # `_validar_clubes`. Con la lista viaja la delegación de cada dojang, así
    # que no hay un bloque aparte para `delegacion`/`pais_delegacion`: sería
    # otra vía de escritura capaz de dejarlos discrepando de la lista.
    clubes, error = _validar_clubes(data)
    if error:
        return jsonify({"error": error}), 400
    if clubes is not None:
        if user.rol == "maestro" and not clubes:
            return jsonify({"error": "El club es obligatorio para un maestro"}), 400
        user.clubes = clubes
    elif "delegacion" in data or "pais_delegacion" in data:
        # Cliente antiguo que solo corrige la delegación, sin tocar el club:
        # se aplica al dojang principal, que es el único que conoce.
        ciudad, pais, error = _validar_delegacion(
            data.get("delegacion"), data.get("pais_delegacion")
        )
        if error:
            return jsonify({"error": error}), 400
        actuales = user.clubes
        if actuales:
            actuales[0] = {**actuales[0], "ciudad": ciudad, "pais": pais}
            user.clubes = actuales

    # Permiso de juez del maestro. Si se le revoca, se liberan sus asignaciones.
    if "puede_juzgar" in data:
        nuevo = bool(data["puede_juzgar"]) and user.rol == "maestro"
        if user.puede_juzgar and not nuevo:
            AsignacionJuez.query.filter_by(usuario_id=user.id).delete()
        user.puede_juzgar = nuevo

    if "activo" in data:
        if user.id == current_user.id and not data["activo"]:
            return jsonify({"error": "No puedes desactivar tu propio usuario"}), 400
        user.activo = bool(data["activo"])
        if user.activo:
            user.eliminado_at = None
        else:
            # Al desactivar, liberar sus asignaciones de tatami
            AsignacionJuez.query.filter_by(usuario_id=user.id).delete()
            user.eliminado_at = datetime.now(timezone.utc)

    # Red de seguridad: un juez que pasa a maestro en la misma petición que no
    # trae clubes se quedaría sin ninguno, y no podría inscribir a nadie.
    if user.rol == "maestro" and not user.clubes:
        return jsonify({"error": "El club es obligatorio para un maestro"}), 400

    db.session.commit()
    return jsonify({
        "message": "Usuario actualizado",
        "user": user.to_dict(),
    }), 200


@auth_bp.route("/users/<int:user_id>", methods=["DELETE"])
@jwt_required()
def delete_user(user_id):
    """
    DELETE /api/auth/users/:id (solo Admin)
    Desactiva el usuario y elimina sus asignaciones activas.
    Un admin normal solo puede quitar usuarios que él creó.
    """
    current_user = require_admin()
    if not current_user:
        return jsonify({"error": "Solo administradores"}), 403

    if current_user.id == user_id:
        return jsonify({"error": "No puedes quitar tu propio usuario"}), 400

    user = Usuario.query.get(user_id)
    if not user or not es_dueno_usuario(current_user, user):
        return jsonify({"error": "Usuario no encontrado"}), 404
    if user.es_super:
        return jsonify({"error": "El superadministrador no puede ser eliminado"}), 403

    AsignacionJuez.query.filter_by(usuario_id=user.id).delete()
    user.activo = False
    user.eliminado_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({"message": "Usuario quitado de la aplicación"}), 200
