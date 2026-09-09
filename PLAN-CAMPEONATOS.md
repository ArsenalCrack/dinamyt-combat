# PLAN CAMPEONATOS — de consola de jueces a aplicación del ecosistema

> Estado: **propuesta**, escrita el 9 de septiembre de 2026. Nada de lo que hay
> aquí está implementado todavía. Lo que sí está implementado se cuenta en la
> PARTE 1, con archivo y línea, para que el plan se apoye en lo que hay y no en
> lo que uno recuerda que hay.
>
> Los documentos hermanos siguen valiendo y este no los sustituye:
> `PLAN-SINCRONIZACION-LOCAL-ONLINE.md` (cómo viajan los datos, ya funciona),
> `B3-RIESGOS.md` (lo que se decidió NO resolver) e `INICIAR-LOCAL.md` (el
> manual del día del evento).

---

## La pregunta que ordena todo lo demás

> *«Los usuarios pasan todos por el mismo login. ¿Cuál es la diferencia?»*

La diferencia **no está en la puerta, está en lo que la puerta trae escrito**.

Todo el mundo entra por DINAMYT, siempre. El portal firma un pase (JWT RS256) y
en ese pase van tres cosas: **quién eres** (`sub`, `email`), **qué club te
respalda** (`org_id`) y **qué eres dentro de cada app** (`role_campeonatos`,
`role_membresias`, `role_academy`), más los `app_scopes` que dice tu plan.
Campeonatos verifica la firma contra el JWKS y no le pregunta nada a nadie
(`backend/app/identidad.py`) — por eso funciona con el ecosistema lento, y por
eso una sesión revocada sigue entrando hasta 30 minutos (`B3-RIESGOS.md` §1.3).

Así que la respuesta a «¿cuál es la diferencia?» es: **la misma puerta, y detrás
de ella tantas casas como papeles tengas**. Hoy Campeonatos solo sabe abrir una
casa por persona, y a los alumnos no les abre ninguna. Eso es lo que hay que
cambiar.

---

# PARTE 1 · Lo que hay hoy, sin adornos

## 1.1 · El rol es UNO, y ese es el problema de fondo

En el ecosistema, `org_members` guarda **un** `role_campeonatos` por
membresía (`apps/ecosystem-api/src/db/schema/index.ts:427`). En Campeonatos,
`usuarios.rol` es **una** cadena de tres valores posibles:

```python
# backend/app/models/usuario.py
ROLES_VALIDOS = ("admin", "maestro", "juez")
```

Y ya se rompió una vez. Cuando hizo falta que un maestro también puntuara, no se
amplió el modelo: se le colgó un booleano al lado.

```python
# backend/app/models/usuario.py
puede_juzgar = db.Column(db.Boolean, default=False, nullable=True)

@property
def puede_ser_juez(self) -> bool:
    return self.rol == "juez" or (self.rol == "maestro" and bool(self.puede_juzgar))
```

**`puede_juzgar` es la prueba de que el modelo de un solo rol ya no daba.** Y un
booleano por combinación no escala: «el admin que compite», «el juez que además
inscribe a los suyos», «el maestro que arbitra y compite» serían tres columnas
más, cada una con su propia excepción en cada endpoint.

## 1.2 · El alumno no tiene dónde aterrizar. Literalmente

La traducción del rol del ecosistema al de aquí no contempla al alumno:

```python
# backend/app/espejo.py
ROL_DESDE_ECOSISTEMA = {
    "admin": "admin", "maestro": "maestro",
    "coach": "maestro", "judge": "juez", "juez": "juez",
}
# Los que faltan —`competitor`, `student`, `guardian`, `member`— no operan nada.
```

El camino completo de un alumno que pulsa «Entrar a Campeonatos» hoy:

1. `rol_operativo()` devuelve `None` (`espejo.py:91`).
2. `resolver_espejo()` devuelve `motivo="sin_consola"` (`espejo.py:196`).
3. La API contesta 403 con ese motivo (`backend/app/api/auth.py:253`).
4. El login **lo devuelve al portal** con `?campeonatos=sin_consola`
   (`frontend/src/app/login/page.tsx`).
5. El portal le enseña una tarjeta de solo lectura
   (`apps/ecosystem-portal/src/app/dashboard/page.tsx:440`).

El mensaje que lee es honesto y hoy es verdad:

> «Tu cuenta de DINAMYT no administra ni juzga campeonatos. Lo tuyo —tus
> inscripciones y tus resultados— se ve desde el portal.»

**Ese mensaje es exactamente lo que el plan viene a dejar de ser verdad.**

## 1.3 · En Campeonatos no existe la organización

No hay `org_id` en ninguna tabla. Buscado: cero apariciones en `backend/app/models/`
y en `backend/app/api/`. El aislamiento se hace por **workspace del creador**:

```python
# backend/app/api/scoping.py
def workspace_owner_id(user):
    if user.rol == "maestro":
        return user.creado_por_id or user.id
    return user.id
```

Consecuencia directa, y es la que responde a *«solo puede haber un administrador
por organización»*: **hoy eso no se puede ni comprobar.** Dos personas del mismo
club con `rol=admin` son dos mundos paralelos que no se ven entre sí — y como la
regla de visibilidad al negar es 404 y no 403 (`scoping.py`, cabecera), ninguno
de los dos descubre que el otro existe. Cada uno crea sus campeonatos, sus
jueces y sus competidores, y el club acaba con dos verdades.

## 1.4 · Inscribirse: el permiso existe, pero es implícito

Un maestro inscribe a los suyos en los campeonatos del admin **que lo creó**
(`workspace_owner_id`). O sea: el permiso para inscribirse **ya existe**, pero no
es una decisión que alguien tome campeonato a campeonato — es un efecto colateral
de quién creó la cuenta. No hay forma de decir «este club sí entra a este
campeonato y a este otro no».

## 1.5 · Los paquetes de sincronización pierden la identidad

`_usuario_a_dict` (`backend/app/api/sincronizacion.py:103`) lleva `email`,
`nombre`, `rol`, `clubes` y `puede_juzgar`. **No lleva `eco_sub`.** Y
`competidores` no tiene `eco_sub` en absoluto
(`backend/app/models/competidor.py:100`).

Dos consecuencias:

- Un usuario que viaja al local y vuelve **pierde el enlace con su cuenta de
  DINAMYT**, y se vuelve a enlazar por correo la próxima vez que entre — que es
  el camino que puede acabar en `correo_ocupado`.
- **Un competidor no se puede conectar con la persona que es.** Sin eso, el
  panel del alumno de §2.3 no tiene de dónde sacar «tus» resultados.

## 1.5-bis · **El rol local MANDA sobre el del pase** — y esto lo cambia todo

*(añadido el 9 de septiembre de 2026, releyendo `OPERAR.md` §4.13 y §6.1)*

Es la regla que faltaba en la primera versión de este plan, y **es la que decide
si la fase 1 sirve de algo**:

> **El pase solo decide el rol AL CREAR la fila.** Después manda el local.
> *(`OPERAR.md` §4.13, «La fila local es un espejo, y su rol manda»)*

O sea: se puede implementar entero el pase con varios roles (F1) y **no cambiaría
nada en Campeonatos** para nadie que ya haya entrado una vez. El espejo ya
existe, y su `rol` gana.

Y está puesta a propósito, con una razón buena:

> Evita que un cambio de rol en el portal **degrade en silencio al administrador
> de un campeonato en marcha**.

`OPERAR.md` §6.1 lo lleva abierto desde el 30 de agosto —«El cambio de rol solo
viaja a Membresías»— y dice también **cuándo** se puede cerrar:

> Para cerrarlo hace falta el equivalente de `/sync/rol` en cada una: […] en
> Campeonatos es Flask y **no puede depender de la red el 9 de octubre**, así
> que ahí conviene esperar a **después del campeonato**.

**Consecuencia para este plan:** F2 no es «leer la lista del pase». F2 tiene que
decidir **cuándo el ecosistema puede pisar el rol local y cuándo no** — y la
respuesta no es «siempre», porque entonces se reabre el fallo que esta regla
evita. La propuesta está en F2.

## 1.5-ter · Y hoy el alumno no crea fila, también a propósito

> **El pase de un alumno no crea ninguna fila** en `usuarios`. Sin esa regla, una
> federación con doscientos alumnos serían doscientas filas de gente que no va a
> entrar nunca, cada una ocupando un correo único en la consola.
> *(`OPERAR.md` §4.13)*

**F3 revierte esta decisión**, y hay que saberlo antes de empezarla: el panel del
competidor significa exactamente eso, una fila por alumno. El coste que la regla
evitaba —el listado de usuarios de la consola inundado de gente que no opera— hay
que pagarlo o esquivarlo. Cómo, en F3.

Lo que sí existe ya, y la primera versión de este plan no reconoció: **el portal
no deja al alumno en el vacío.** Desde el 30 de agosto su tarjeta lleva a las
**páginas públicas** de Campeonatos —los campeonatos abiertos y los resultados—,
que no piden sesión. No es «nada»: es una sala de espera. Lo que no hay es nada
**suyo**.

## 1.5-quater · Las dos puertas tienen duraciones distintas

`POST /auth/sesion` abre sesiones de distinta duración según por dónde se entre
(`OPERAR.md` §4.13):

| Entra con… | Quién | Dura |
|---|---|---|
| El pase del ecosistema (RS256) | Quien salta desde el portal | **12 h** |
| Su token propio (HS256) | **El QR del juez** | **72 h** |

Las 12 h acotan cuánto sobrevive aquí una sesión que en el portal ya se cerró
(§1.3 de `B3-RIESGOS.md`). Las 72 del QR son porque se reparte por la mañana y
tiene que aguantar el fin de semana **sin internet**.

**Para F3:** el competidor entra por la primera puerta, así que su panel caduca
cada 12 h. Para lo que va a hacer —mirar sus resultados— está bien y no hay que
tocarlo. **Pero no se le puede dar un QR de 72 h**: esa puerta es la del juez y
existe para el modo sin internet.

## 1.6 · Lo local ya arranca, y ya está decidido que es solo Campeonatos

Existen `1-INSTALAR.bat`, `2-INICIAR.bat` y `abrir-firewall.bat`, y el manual es
`INICIAR-LOCAL.md`. Y la pregunta *«¿solo campeonatos o toda ecosystem?»* **ya
tiene respuesta, y es una decisión tomada**, no algo por decidir:

> **B3-RIESGOS.md §1.4 — Sin internet no existe el ecosystem, y punto.**
> En modo local no hay recuperación de contraseña, ni cuentas nuevas, ni
> invitaciones, ni «una cuenta para todo». El local vive con su propio
> administrador y con el QR de los tatamis.

**Solo Campeonatos baja al gimnasio.** El modo local se reconoce por la ausencia
de `ECOSYSTEM_JWKS_URL` (`identidad.py:hay_ecosistema`) y de
`NEXT_PUBLIC_ECOSYSTEM_PORTAL_URL` (`frontend/src/lib/portal.ts`).

Lo que le falta al arranque no es alcance, es **acabado**: `2-INICIAR.bat` abre
dos ventanas negras y confía. No comprueba que el `venv` exista, ni que el
frontend esté compilado, ni que los puertos estén libres, ni espera al «Ready»
—el manual pide contar quince segundos a ojo (`INICIAR-LOCAL.md` §3)— ni hay un
`3-APAGAR.bat`, así que apagar es «cierra las dos ventanas negras».

## 1.6-bis · El puente con el ecosistema estaba a medias, y en silencio

*(arreglado el 9 de septiembre de 2026 — se cuenta aquí porque es el patrón,
no la anécdota)*

El tema y el idioma elegidos en el portal no llegaban a Campeonatos. Las dos
funciones que lo hacen —`guardar_apariencia` y `leer_apariencia`, en
`espejo.py`— empiezan igual:

```python
secreto = os.getenv("ECOSYSTEM_SYNC_SECRET", "").strip()
if not secreto or not raiz or not eco_sub:
    return None          # ← y aquí no se escribía NADA en el registro
```

Dos causas, **las dos mudas**: la tabla de variables de `OPERAR.md` §1.4 pedía
ese secreto en `ecosystem-api` y en `membresias-api` y **no nombraba a
`campeonatos-api`**; y `eco_sub` en `NULL` apaga las dos direcciones aunque el
secreto esté puesto. Ya está corregida la tabla, y la app **lo dice al arrancar**
(`_decir_como_quedo_el_ecosistema`, en `backend/app/__init__.py`).

**Por qué importa para este plan y no es solo una anécdota:** las fases F4, F6 y
F8 añaden **tres puentes más** con el ecosistema, y las tres tienen la misma
forma —una variable de entorno que, al faltar, hace que la función se calle y
devuelva `None`—. Es el diseño correcto para una app que tiene que arrancar sin
internet, y es también la forma más fiable de que algo lleve semanas apagado sin
que nadie se entere.

> **Regla para las tres fases que vienen:** *ningún puente nuevo se da por hecho
> en silencio.* Si una pieza del ecosistema está apagada, **se dice al arrancar y
> se ve en `/admin`**. «Apagado» es un estado válido; «apagado sin que se note»
> no lo es. Es la misma lección que `PLAN-SINCRONIZACION-LOCAL-ONLINE.md` ya
> había pagado: *«el fallo más peligroso no era un error, sino el silencio»*.

## 1.7 · La vuelta de los resultados es a mano, pero el destino ya existe

Hoy: en el local, Reportes → «Exportar resultados» → USB → en el online,
`/admin/importar-resultados`.

Y esto es la buena noticia del plan: **el endpoint de destino ya está y ya es
idempotente.**

```python
# backend/app/api/resultados.py:318
@resultados_bp.route("/importar", methods=["POST"])
@jwt_required()
def importar_resultados():
    """Reimportar el mismo campeonato REEMPLAZA el anterior."""
```

Acepta el cuerpo JSON directo (no solo multipart) y reemplaza por `export_uuid`.
Para la subida automática **no hay que inventar el destino ni el formato**: falta
una credencial que sobreviva en la máquina del gimnasio, una cola y quien la
empuje.

---

# PARTE 2 · A dónde vamos

## 2.1 · El modelo de roles, en una frase

> **Una persona tiene un CONJUNTO de papeles en Campeonatos, y competir es uno
> más.**

`{admin}`, `{maestro, competidor}`, `{juez, competidor}`,
`{admin, juez, competidor}` — todas válidas. Ser competidor no quita nada y no
lo da todo: es el papel que **todo el mundo** tiene por defecto si su club tiene
el plan.

Y la regla que lo hace manejable:

> **Los papeles se SUMAN, nunca se restan.** Lo que ve alguien es la unión de lo
> que le abren todos sus papeles. Nunca hay que preguntarse cuál «gana».

Eso mata la pregunta de «¿a dónde mando a un maestro que también es juez?», que
hoy se resuelve eligiendo uno (`destinoDe(rol)` en `login/page.tsx`).

## 2.2 · Las tres alturas, y qué ve cada una

| Papel | Qué abre | Alcance |
|---|---|---|
| **competidor** (todos) | Su panel: sus inscripciones, sus resultados, su historial y sus estadísticas | Solo lo suyo |
| **maestro** | Además: inscribe a los suyos, en los campeonatos a los que su club fue invitado | Su club |
| **juez** | Además: sus tatamis y la consola de puntuar | Los tatamis donde lo asignaron |
| **admin** | Además: crea campeonatos, tatamis, llaves, invita clubes, reportes | Su organización |

Un solo administrador de Campeonatos por organización, que es la regla que pide
el negocio. Los demás papeles no tienen tope.

## 2.3 · La organización pasa a mandar

El aislamiento deja de ser «quién creó esta fila» y pasa a ser «de qué
organización es». `created_by` **se queda** —hace falta para la auditoría y para
la reconciliación de los paquetes— pero deja de ser quien decide qué se ve.

---

# PARTE 3 · El plan, paso a paso

Nueve fases. Cada una deja la aplicación **funcionando y desplegable**: ninguna
depende de que la siguiente esté hecha. El orden no es negociable en los tres
primeros bloques (F1 → F2 → F3), porque cada uno se apoya en el anterior.

---

## F0 · Las decisiones, antes de escribir una línea

### Decidido el 9 de septiembre de 2026

**D1 · El panel del alumno es de SOLO MIRAR.** Sus inscripciones y su estado,
sus resultados y podios, su historial y sus estadísticas. **Inscribir sigue
siendo cosa del maestro**, como hoy. Es la fase más pequeña que ya cambia el
producto, y no toca el flujo de inscripciones — que es el único que puede
romper un campeonato en marcha.

> Si más adelante hace falta, el paso natural es un «quiero competir en esto»
> que le llegue al maestro como solicitud, para que deje de perseguir a los
> alumnos por WhatsApp. Una tabla y una pantalla. **No entra en F3.**

**D2 · El portal DA papeles; solo la consola los QUITA.** Es la respuesta al
conflicto de §1.5-bis, desarrollada en el punto 6 de F1:

| Situación | Qué se hace |
|---|---|
| El pase trae un papel que la fila NO tiene | **Se añade** |
| El pase NO trae uno que la fila SÍ tiene | **Se conserva** |
| Quitar un papel | **Solo desde la consola de Campeonatos** |

**D3 · Los admins duplicados de hoy no se tocan: primero el informe.** La
migración de F4 **no cambia a nadie**. Saca la lista de organizaciones con más
de un admin, con nombres, y la decisión se toma club por club antes de aplicar
la regla. Nadie pierde la consola por sorpresa — que es la mitad de lo que este
plan intenta evitar en todas partes.

**D4 · Se empieza por lo del evento.** F7 (encendido local) y F6 (paquetes con
identidad) **antes de octubre**: las dos se notan ESE fin de semana y ninguna
toca permisos. Los roles (F1–F2), el panel del alumno (F3) y la organización
(F4–F5), **después del 11**. Ver la PARTE 4.

### Todavía sin decidir — **no bloquean a F6 ni a F7**

**P1 · ¿El competidor entra aunque su club no tenga el plan de Campeonatos?**
Propuesta en pie: **no**. `app_scopes` sigue mandando y el mensaje `sin_plan` se
queda como está; sus resultados se ven en el portal, que es donde ya se ven hoy.
**Hace falta antes de empezar F3.**

**P2 · ¿Caduca la credencial de la máquina local?** Propuesta en pie: **sí, 90
días**, renovable desde el panel del admin online. Una llave eterna en un PC que
viaja a los gimnasios es una llave perdida. **Hace falta antes de empezar F8.**

---

## F1 · El pase lleva varios roles (ecosystem)

**Dónde:** `apps/ecosystem-api` (monorepo `dinamyt`).

1. Migración: añadir `org_members.roles_campeonatos` (`text[]`), rellenándola
   con `ARRAY[role_campeonatos]` para las filas que lo tengan y `ARRAY[]` para
   las que no. `role_campeonatos` **no se toca**.
2. `roles-por-app.ts`: `rolesParaApp(app, propios, general)` devolviendo lista.
   La traducción existente se reutiliza tal cual; a `campeonatos` se le añade
   `student → competitor` y `member → competitor`.
3. El JWT emite **las dos cosas**: `role_campeonatos` (el de mayor rango, como
   hoy) y `roles_campeonatos` (la lista). Academy y Membresías no se enteran.
4. La pantalla de roles del portal (`mi-organizacion/miembro/[id]`) pasa a
   casillas en vez de desplegable, solo para Campeonatos.

> **Por qué las dos a la vez y no un cambio limpio.** Porque Campeonatos en
> producción lee `role_campeonatos` hoy, y el VPS despliega las apps por
> separado (`OPERAR.md` §1.2). Si el pase deja de traer el campo viejo antes de
> que F2 esté desplegada, **nadie entra a Campeonatos** entre un despliegue y el
> otro. El campo viejo se retira en F9, cuando ya no lo lee nadie.

**Pruebas:** un miembro con `{maestro, judge}` produce las dos formas; uno sin
nada produce lista vacía y `null`. Los tres archivos `*.spec.ts` que ya cubren
esto (`roles-por-app.spec.ts`, `cambiar-rol.spec.ts`, `herencia-plan.spec.ts`)
se amplían, no se sustituyen.

---

## F2 · Campeonatos entiende varios roles

**Dónde:** `dinamyt-combat/backend`.

**El patrón ya existe en esta casa y hay que copiarlo, no inventar otro.**
`usuarios.clubes` es la lista y fuente de verdad; `usuarios.club` se mantiene
como «el principal» y lo escribe el *setter* de la lista, así que no hay dos
verdades que puedan discrepar (`models/usuario.py`). Los roles se hacen igual.

1. `usuarios.roles` (JSON, lista). `usuarios.rol` se queda como **el principal**
   —el de mayor rango de la lista— y **solo lo escribe el setter de `roles`**.
   El getter de `roles` arma la lista desde `rol` + `puede_juzgar` cuando la
   columna está vacía, así que **no hace falta backfill**: las filas viejas
   contestan bien desde el primer arranque. `schema_compat.py` crea la columna
   al iniciar, como hace con todo.
2. `ROLES_VALIDOS` pasa a `("admin", "maestro", "juez", "competidor")`.
3. `puede_juzgar` queda **derivado**: `"juez" in roles`. La columna se mantiene
   escribiéndose por compatibilidad con los paquetes de sincronización de
   instalaciones viejas, y se retira en F9.
4. `scoping.py`: `require_admin()` / `require_maestro()` pasan a apoyarse en
   `tiene_rol(user, "admin")`. **La firma y el valor de retorno no cambian**, así
   que los endpoints no se tocan en esta fase.
5. `espejo.py`: `rol_operativo()` → `roles_operativos()`, leyendo
   `roles_campeonatos` del pase y cayendo a `role_campeonatos` si no viene (una
   instalación con el ecosystem sin actualizar tiene que seguir entrando).
6. **Y quién gana, que es la pregunta de verdad (ver §1.5-bis).** Hoy el rol
   local manda **siempre** después de crear la fila, y eso deja a F1 sin efecto.
   Propuesta —**suman, no restan**, que es la regla de §2.1 aplicada al
   conflicto:

   | | Qué se hace | Por qué |
   |---|---|---|
   | El pase trae un papel que la fila NO tiene | **Se añade** | Es el caso de «lo puse en el portal y allí no cambia nada», y añadir no puede romper un campeonato en marcha |
   | El pase NO trae un papel que la fila SÍ tiene | **Se conserva** | Es exactamente el degradado en silencio que la regla actual evita. `puede_juzgar` y el mando de un campeonato se ponen a mano aquí, y eso no se pisa desde fuera |
   | Quitar un papel de verdad | **Solo desde la consola de aquí** | Con nombre y apellidos de quien lo quita |

   Así F1 empieza a servir para algo **sin reabrir** el fallo que §4.13 evita: el
   portal puede DAR, y solo la consola puede QUITAR.

   > **Esto NO cierra `OPERAR.md` §6.1 («El cambio de rol solo viaja a
   > Membresías»).** Cerrarlo del todo pide un `/sync/rol` que empuje desde el
   > ecosistema, y ahí `OPERAR.md` es explícito: en Campeonatos es Flask y **no
   > puede depender de la red el 9 de octubre**, así que se espera a después del
   > campeonato. Lo de arriba no depende de la red: se aplica con el pase que la
   > persona ya trae al entrar.
6. Frontend: `destinoDe(rol)` deja de elegir. Con un solo papel se entra directo
   como hoy; con varios se entra al **panel de competidor** (§F3), que es el
   único que todos tienen, y desde ahí se cambia de sombrero.

> **Lo que a propósito NO se toca en F2:** ningún endpoint gana ni pierde
> permisos. Al terminar esta fase la aplicación hace **exactamente** lo mismo que
> antes; lo único que cambia es que sabe representar a alguien con dos papeles.
> Es la misma disciplina que dejó escrita `roles-por-app.ts`: *«una ampliación de
> permisos no se cuela de propina en un arreglo de otra cosa»*.

---

## F3 · El alumno entra: el panel del competidor

**Dónde:** `dinamyt-combat` (backend + frontend). **Es la fase que le cambia la
cara al producto**, y por eso va sola.

1. **Enlazar la persona con el atleta.** `competidores.eco_sub` (nullable,
   indexada) + `competidores.usuario_id`. Sin esto el panel no sabe qué filas son
   tuyas. Se rellena por tres caminos, en este orden:
   - el maestro inscribe desde el ecosistema y el alta trae el `sub`;
   - la persona entra y reclama su ficha por documento + fecha de nacimiento;
   - el admin lo enlaza a mano desde `/admin/competidores`.
2. `ROL_DESDE_ECOSISTEMA` gana `competitor` y `student` → `competidor`.
3. `resolver_espejo` deja de devolver `sin_consola` cuando el pase trae plan:
   crea el espejo con `roles=["competidor"]`. **`sin_consola` no desaparece** —
   sigue siendo la respuesta correcta para un pase sin ningún rol de esta app.
4. Nueva pantalla `/mi-panel`:
   - mis inscripciones (y su estado: pendiente / aceptada / rechazada, con el
     motivo, que ya existe en `inscripciones.motivo_rechazo`);
   - mis resultados y podios, del histórico completo;
   - mis estadísticas: combates, victorias, medallas por año y por modalidad;
   - mis campeonatos próximos, y quién es mi maestro.
5. El endpoint `/api/mi/*` filtra **siempre** por el `eco_sub` del pase. Nunca
   por un id que venga del cliente.
6. El portal cambia la tarjeta de solo lectura por el botón de entrar
   (`dashboard/page.tsx:440`), y el mensaje `sin_consola` deja de mencionar el
   portal como único sitio.

7. **Y la consola no se puede inundar (§1.5-ter).** La regla que F3 revierte
   —«el pase de un alumno no crea ninguna fila»— existía para que una federación
   de doscientos alumnos no metiera doscientas filas en el listado de usuarios
   de la consola. Así que al crear el espejo de un competidor:
   - `/admin` → Jueces **filtra por defecto a quien opera** (`admin`, `maestro`,
     `juez`) y los competidores quedan detrás de un contador «+184 competidores»;
   - el buscador sí los encuentra, porque el admin necesita poder enlazar una
     ficha a mano;
   - y la fila se crea **la primera vez que la persona entra**, no al firmar el
     pase: quien nunca abra Campeonatos sigue sin existir aquí.

> **El riesgo de esta fase, dicho claro:** hasta hoy, entrar a Campeonatos era la
> excepción; a partir de aquí es lo normal. Todo endpoint que asumiera «quien
> está dentro es de la casa» se convierte en superficie expuesta. **Antes de
> desplegar F3 hay que repasar los endpoints uno a uno**, y ese repaso es parte
> de la fase, no un extra.

---

## F4 · La organización llega a Campeonatos

**Dónde:** `dinamyt-combat/backend`.

1. `usuarios.org_id` y `campeonatos.org_id` (texto, el UUID del ecosistema).
   `usuarios.org_id` se rellena desde el pase en `resolver_espejo`;
   `campeonatos.org_id` con la del creador al crear.
2. Backfill: a cada campeonato existente, la `org_id` de su `created_by`. Los que
   no la tengan (creados antes de la identidad única, o en local) se quedan en
   `NULL` = **«del workspace de siempre»**, y siguen funcionando por
   `created_by`. `NULL` deja pasar, igual que hizo `plan_bloqueado_desde` en
   Membresías (`OPERAR.md` §2.4).
3. `es_dueno_campeonato` pasa a comparar `org_id` cuando las dos filas la tienen,
   y a `created_by` cuando alguna no. **Las dos reglas conviven** hasta que el
   backfill esté completo y verificado.
4. **La regla del admin único.** Al resolver el espejo, si el pase trae
   `admin` y su organización ya tiene otro admin activo con distinto `eco_sub`,
   entra como `maestro` y **se registra el hecho en el log**. No se le quita el
   papel a nadie por sorpresa y no se falla la entrada: el segundo admin entra,
   trabaja, y alguien lo mira.
5. `/admin` enseña, en su cabecera, de qué organización es lo que se está viendo.
   Hoy no lo dice, y con dos workspaces conviviendo eso ya era confuso.

**Verificación imprescindible antes de desplegar:** un informe que liste las
organizaciones con más de un admin. Si sale largo, F0.2 se decide otra vez.

---

## F5 · Inscribirse por invitación, no por herencia

**Dónde:** `dinamyt-combat` (backend + frontend).

1. Tabla `campeonato_clubes`: `campeonato_id`, `org_id` (o nombre de club en
   local), `estado` (`invitado` | `aceptado` | `retirado`), `invitado_por_id`,
   `uid` para que viaje en los paquetes.
2. El admin invita clubes desde la ficha del campeonato. El maestro ve el
   campeonato en su lista **solo si su club está invitado** — o si el campeonato
   está publicado, que es lectura y ya funciona (`/campeonatos/publico`, que
   `scoping.py` nunca filtra).
3. La inscripción comprueba la invitación. Sin ella: 403 con un motivo que se
   pueda leer («tu club no está invitado a este campeonato»), no un 404 mudo.
4. Migración blanda: **todo maestro que hoy inscribe queda invitado** a los
   campeonatos de su workspace. Nadie pierde acceso el día del despliegue.

---

## F6 · Los paquetes llevan la identidad

**Dónde:** `dinamyt-combat/backend/app/api/sincronizacion.py`.

Esto es lo que responde a *«acomodar los imports a como trabaja hoy la
aplicación»*: el formato se escribió antes de que existieran la identidad única,
los roles múltiples y la organización, y hoy los deja fuera.

1. `_usuario_a_dict` añade `eco_sub`, `roles` y `org_id`.
2. `_competidor_a_dict` añade `eco_sub` y `usuario_uid`.
3. `_importar_usuarios` y `_importar_competidores` los leen **sin pisar** lo que
   ya haya: si la fila local ya tiene `eco_sub` y el paquete trae otro, se
   **omite con aviso**. La misma prudencia que `resolver_espejo` con
   `correo_ocupado`: no se pisa ninguna, se para y que lo mire una persona.
4. Sube `FORMATO_EXPORT` de versión, y el importador **acepta la anterior**
   (los campos nuevos entran vacíos). Un paquete exportado antes de esta fase
   tiene que seguir importándose el día del evento.
5. El informe previo —el que ya enseña «5 nuevos · 3 actualizados»— gana su
   línea de identidades enlazadas y omitidas.

---

## F7 · Encender en local: un archivo, y que avise

**Dónde:** `dinamyt-combat`, raíz. **Solo Campeonatos** (`B3-RIESGOS.md` §1.4).

Nuevo `INICIAR.bat` que sustituye a `2-INICIAR.bat` y **comprueba antes de
arrancar**, porque el sitio donde falla esto es un gimnasio a las siete de la
mañana:

1. ¿Existe `backend/venv`? ¿Existe `frontend/.next`? Si no: dice que falta correr
   `1-INSTALAR.bat` **y no arranca a medias**.
2. ¿Están libres los puertos 5000 y 3000? Si no, dice **qué** los ocupa.
3. Arranca los dos, **espera al «Ready» de verdad** (sondea el puerto, no cuenta
   quince segundos como pide hoy `INICIAR-LOCAL.md` §3).
4. Enseña la IP **en grande** y genera un **QR de `http://IP:3000`** en pantalla,
   para que los treinta celulares no la escriban a mano.
5. Escribe `local-<fecha>.log` con lo que pasó, que es lo único que quedará si
   algo se tuerce.
6. `APAGAR.bat` que para los dos servicios de verdad, en vez de «cierra las dos
   ventanas negras».

`2-INICIAR.bat` se queda un tiempo llamando al nuevo, porque el manual impreso
que hay en la carpeta del evento dice «2-INICIAR».

---

## F8 · La subida automática de resultados

**Dónde:** `dinamyt-combat/backend`. **Depende de F6** (sin `eco_sub` en el
paquete, lo que sube son filas huérfanas).

**La regla del diseño no cambia y no se toca:** sigue siendo un solo sentido, y
**solo suben podios y rankings**
(`PLAN-SINCRONIZACION-LOCAL-ONLINE.md`, «El viaje de vuelta»). Lo que se
automatiza es el USB, no la dirección.

1. **La credencial.** El admin online genera un *token de instalación* desde
   `/admin`, se pega una vez en el `.env` del PC del evento. Caduca a los 90
   días (F0.3). Es de máquina, no de persona: no abre la consola, solo deja
   publicar resultados.
2. **La cola.** Tabla local `cola_sync`: `export_uuid`, `payload`, `intentos`,
   `ultimo_error`, `enviado_at`. Publicar un podio **encola**; no envía.
3. **El cartero.** Un hilo que cada N minutos: ¿hay red? ¿contesta el online?
   → `POST /api/resultados/importar` con el cuerpo JSON, que **ya es idempotente
   por `export_uuid`** (`resultados.py:318`). Reintento con espera creciente;
   nunca en mitad de un combate.
4. **Se ve.** Una línea en `/admin`: «3 resultados pendientes de subir · último
   intento hace 4 min · [Subir ahora]». Una cola invisible es una cola que nadie
   vacía, y el fallo silencioso es justo el que ya mordió una vez en esta app
   (`PLAN-SINCRONIZACION-LOCAL-ONLINE.md`, «el fallo más peligroso no era un
   error, sino el silencio»).
5. **El USB se queda.** El botón de exportar a mano no se quita: es el plan B del
   día que la automática no funcione, y ese día no se programa.

---

## F9 · Retirar los andamios

Solo cuando F1–F8 lleven **un campeonato real** encima:

- Quitar `role_campeonatos` (singular) del JWT.
- Quitar la columna `puede_juzgar` y la doble regla de `es_dueno_campeonato`.
- Dejar `campeonatos.org_id` en `NOT NULL`, si el backfill está completo.

---

# PARTE 4 · El calendario manda antes que el orden

*(añadido el 9 de septiembre de 2026)*

Hay **un campeonato real el 9, 10 y 11 de octubre de 2026**, y eso no es un
detalle de agenda: es una restricción del plan.

- **Los días 9, 10 y 11 no se sube nada.** El 8 solo entran arreglos
  (`OPERAR.md` §1.5). La regla era de trece días y se recortó a tres el 4 de
  septiembre, así que **hasta la víspera se trabaja normal**.
- **La última semana de septiembre se corre el ensayo** de `OPERAR.md` §6.0, y
  hay que anotar los números del cierre. Cada fase de este plan que toque login,
  roles o identidad **reabre justo los tres eslabones que ese ensayo mide**.
- Y `OPERAR.md` §6.1 ya lo dice para el cambio de rol: en Campeonatos **conviene
  esperar a después del campeonato**.

**Lo que eso significa, en concreto:**

| Antes del 8 de octubre | Después del 11 |
|---|---|
| **F7** (encendido local) — se nota justo ese fin de semana | F1, F2, F4, F5 |
| **F6** (paquetes con identidad) — hace falta para el evento | F3 (el panel del alumno) |
| F0 (decidir) — no toca código | F8, F9 |

F3 después del campeonato no es prudencia de más: es la fase que **multiplica por
cien la gente que entra**, y estrenarla tres semanas antes del evento, con el
ensayo ya corrido, es exactamente lo que §1.5 protege.

---

# PARTE 4-bis · El orden, y por qué

```
F0 decidir
   │
   ├─► F1 pase con varios roles (ecosystem)
   │      └─► F2 Campeonatos los entiende      ← nada cambia de cara al usuario
   │             └─► F3 el panel del alumno    ← aquí cambia el producto
   │
   ├─► F4 organización ──► F5 invitaciones     ← puede ir en paralelo a F3
   │
   └─► F6 paquetes con identidad ──► F8 subida automática
          F7 encendido local (independiente, se puede hacer cuando sea)
```

**Lo que se puede hacer ya, sin esperar a nada:** F7. Es independiente, se nota
el día del evento y no toca ni identidad ni permisos.

**Lo que no se puede adelantar:** F3 sin F2, y F8 sin F6. Empezar por el panel
del alumno con el modelo de un solo rol significa escribirlo dos veces.

---

# PARTE 5 · Lo que este plan NO hace

Escrito para que dentro de tres meses nadie lo busque aquí:

- **No junta COMBAT con PROJECT.** Eso es `PLAN_FUSION.md` del monorepo.
- **No arregla la sesión revocada de los 30 minutos.** Es el precio del diseño y
  está aceptado (`B3-RIESGOS.md` §1.3).
- **No cierra el bloqueo por plan vencido.** `OPERAR.md` §6.1 lo tiene abierto y
  razonado: el 9 de octubre Campeonatos no puede depender de la red, y un club
  cerrado por una columna mal puesta a mitad de un campeonato es peor que un club
  que operó un mes de más. Lo que sí corta hoy a un club vencido es el pase — sin
  `app_scopes` no entra quien llegue del portal. Después de F4 habría por fin
  dónde colgarlo (`campeonatos.org_id`), pero sigue siendo otra conversación.
- **No retira `POST /auth/register`.** Está previsto «después del campeonato»
  (`OPERAR.md` §4.13) y es independiente de todo esto.
- **No lleva el ecosystem al gimnasio.** Decidido que no (§1.4 del mismo).
- **No sincroniza en tiempo real.** Sigue siendo un sentido y por tandas.
- **No toca el motor de combate ni el de figuras.** Ni una línea de
  `backend/app/engine/`.
