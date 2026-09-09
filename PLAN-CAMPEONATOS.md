# PLAN CAMPEONATOS — de consola de jueces a aplicación del ecosistema

> Estado: **en marcha**. Escrito el 9 de septiembre de 2026, revisado el mismo
> día, y empezado esa misma tarde por el orden de la PARTE 4:
>
> | | | |
> |---|---|---|
> | **F5-bis** | ✅ **hecha** | La ficha del alumno se reutiliza. Backend, pantalla del maestro y las pruebas que fijaban lo roto, dadas la vuelta |
> | **F6** | 🟡 **a medias** | El paquete ya lleva `eco_sub`. `roles`, `org_id` y la identidad del competidor **no tienen todavía dónde vivir**: las crean F2, F4 y F3. Ver la nota dentro de F6 |
>
> El resto sigue sin empezar.
>
> **⏱ Fecha límite: el 8 de octubre de 2026.** Hay campeonato el 9, 10 y 11 y
> **no hay «después»** (decisión D6): lo que no esté dentro para entonces, no
> existe el día del evento. La PARTE 4 es el orden que sale de eso. Lo que sí está implementado se cuenta en la
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

**~~D4 · Se empieza por lo del evento y lo demás va después del 11.~~**
**REVOCADA el 9 de septiembre**, ver D6.

**D5 · El competidor sin plan es el que está FUERA de un club.** No es un fallo
de facturación: es el atleta independiente, o el de un club que no está en la
organización. **Se le inscribe igual** —lo hace el administrador del
campeonato— y su ficha **se guarda**, de modo que el día que se cree una cuenta
de DINAMYT o entre a un club, **su historial ya está ahí esperándolo**. O sea
que la ficha del competidor **no depende de tener cuenta**, y la cuenta se le
engancha después. Desarrollado en F3.

**D6 · TODO tiene que estar funcional para el 9 de octubre.** No hay «después
del campeonato». Lo que no esté antes del 8, no existe el día del evento — así
que el plan deja de estar ordenado por prudencia y pasa a estarlo por **lo que
más duele el sábado por la mañana**. Ver la PARTE 4, reescrita entera.

### Todas las preguntas, contestadas

**~~P1 · ¿El competidor entra aunque su club no tenga el plan?~~** Contestada:
ver **D5**. La pregunta estaba mal planteada — «sin plan» no era un problema de
suscripción, era el atleta independiente.

**~~P2 · ¿Caduca la credencial de la máquina local?~~** Contestada en F8, y la
pregunta hizo falta para descubrir que **la respuesta buena es no tener ninguna
credencial guardada**. Ver «Las tres cosas que se llaman *local*» aquí abajo y
el diseño de F8.

---

## F0-bis · Las tres cosas que se llaman «local», y no son la misma

*(9 de septiembre de 2026 — escrito porque en la conversación se mezclaron, y
mezcladas no se puede decidir nada)*

| | **1 · Servidor local** | **2 · Modo offline del dispositivo** | **3 · Subida automática** |
|---|---|---|---|
| Qué es | La aplicación ENTERA corriendo en el PC del gimnasio | Una pantalla (`/local`) que funciona **sin servidor ninguno** | El PC del gimnasio mandando resultados a internet |
| Quién lo usa | Todos, por el WiFi del evento | El juez de esquina, **cuando se cae hasta la LAN** | Nadie: es una tarea de fondo |
| Dónde viven los datos | SQLite en `backend/instance/` | `localStorage` del celular del juez | Se copian a la base de internet |
| Cómo se entra | **Usuario y contraseña de ESA instalación**, o el QR del tatami | No se entra: es una libreta | — |
| Estado | ✅ Funciona (`2-INICIAR.bat`) | ✅ Funciona (`app/local/page.tsx`) | ❌ Hoy es un USB a mano |
| Fase | F7 lo pule | No se toca | F8 |

**Las dos primeras no se hablan entre sí y no se parecen.** El *servidor local*
es DINAMYT entero sin internet: hay base de datos, hay llaves, hay marcador en
vivo, y treinta dispositivos conectados a un PC. El *modo offline* es una
libreta digital para un juez cuando ni siquiera eso funciona: no hay servidor,
no hay sesión, y lo anotado **se dicta a la mesa** o se reingresa a mano.

### Y sobre «credenciales», que es donde estaba el enredo

Hay **dos cosas distintas** que la palabra tapa, y solo una es de personas:

**a) Con qué entra una PERSONA.** El día del evento, con la instalación local:
**el usuario y la contraseña de esa instalación**, o el QR del tatami. **Nunca
la cuenta de DINAMYT** — no hay internet al que preguntarle quién es nadie. Está
en `INICIAR-LOCAL.md` §3.1 y en `B3-RIESGOS.md` §1.4. **Esto no cambia y este
plan no lo toca.**

**b) Con qué se identifica un PROGRAMA ante otro.** Es lo que pedía F8, y a lo
que se refería la pregunta P2. Cuando el PC del gimnasio quiere subir los
resultados, llama a `POST /api/resultados/importar` de la instalación de
internet — y ese endpoint exige un administrador. **Un programa no puede
teclear una contraseña.** Nadie ve ese valor, no abre ninguna pantalla, y no
tiene nada que ver con cómo entran las personas.

**Y precisamente por lo enredado que resulta, la respuesta de F8 pasa a ser:
NO guardar ninguna llave en el PC del evento.** El diseño elegido usa la sesión
del propio administrador, la que ya tiene, en el momento en que vuelve la red.
Ver F8.

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

   > **Y la ficha existe ANTES que la cuenta, que es D5.** Un atleta
   > independiente —fuera de un club, o de un club que no está en la
   > organización— lo inscribe el administrador del campeonato, con su ficha
   > completa y **sin cuenta de DINAMYT ninguna**. Compite, gana, y sus podios
   > quedan colgando de esa ficha.
   >
   > El día que se cree una cuenta o entre a un club, **el segundo camino de
   > arriba le devuelve su historial entero**: reclama la ficha por documento y
   > fecha de nacimiento, se le engancha el `eco_sub`, y todo lo que compitió
   > antes de existir en DINAMYT aparece en su panel. Nada se pierde por haber
   > llegado sin cuenta.
   >
   > Es la misma mecánica que ya enlaza a los usuarios viejos por correo
   > (`resolver_espejo`), y con la misma prudencia: si esa ficha ya está
   > enganchada a OTRA cuenta, **no se pisa** — se para y lo mira una persona.
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

## F5-bis · **LA FICHA DEL ALUMNO SE REUTILIZA** — ✅ hecha

*(añadido el 9 de septiembre de 2026 —**la fase más urgente de todo el plan**, y
no estaba en la primera versión— e implementado ese mismo día.)*

> **Hecho.** Los cinco puntos de «Qué se hace», y dos cosas que salieron al
> hacerlo:
>
> - `GET /api/inscripciones/maestro/alumnos` (`api/competidores.py`), con el
>   `uid` de cada ficha y, si se le pasa `campeonato_id`, si ya está inscrito
>   ahí. Los alumnos son los competidores de su workspace apuntados a uno de
>   sus dojangs (`_alumnos_del_maestro`).
> - `maestro_inscribir` acepta `competidor_uid`, y un documento ya conocido
>   **de su propio workspace** deja de ser un 400 y pasa a ser esa persona
>   (`_ficha_del_alumno`). La ficha de otro administrador sigue sin tocarse:
>   el aislamiento no se movió, y hay prueba de ello.
> - En la pantalla del maestro se **elige** al alumno de una lista con
>   buscador; los ya inscritos salen apagados. El peso se deja en blanco a
>   propósito: es lo único que cambia de un campeonato a otro.
> - **Lo que apareció al hacerlo (1):** con la ficha compartida, la unicidad
>   `(campeonato, competidor)` sí se puede tocar —antes era inalcanzable
>   porque cada inscripción estrenaba ficha—. Sin comprobarlo, inscribir dos
>   veces en el mismo campeonato habría sido un **500**. Ahora es un 409 con
>   una frase.
> - **Lo que apareció al hacerlo (2):** `maestro_reenviar` escribía el peso en
>   la FICHA. Con la ficha compartida eso es la contaminación que el punto 5
>   viene a evitar, así que también manda el peso a la inscripción.
>
> `backend/tests/test_alumno_en_dos_campeonatos.py` pasó de fijar el fallo a
> fijar el arreglo: las dos primeras pruebas cambiaron de signo, como estaba
> previsto, y hay cuatro más (el peso por inscripción, el 409, y las dos del
> aislamiento).

### Esto no es una mejora: es un fallo, y muerde en octubre

`maestro_inscribir` (`backend/app/api/competidores.py:919`) hace esto, siempre:

```python
comp = Competidor(nombre_completo="", activo=True, created_by=workspace_owner_id(maestro))
```

**Una ficha NUEVA en cada inscripción.** No mira si ese alumno ya existe. Y como
`competidores.documento` es único en todo el sistema, salen dos caminos y los
dos son malos:

| | Qué pasa |
|---|---|
| **El maestro pone el documento** | La segunda inscripción **se rechaza**: *«Ya existe un competidor con documento 1088123456»*. **Un maestro no puede inscribir a su propia alumna en el segundo campeonato del año.** |
| **No lo pone** | Pasa, y deja **dos fichas distintas** para la misma persona. Sin ficha estable no hay historial — y por tanto F3 (el panel del alumno) no tiene de dónde sacar «tus resultados» |

Está fijado en `backend/tests/test_alumno_en_dos_campeonatos.py`, tres pruebas
que **hoy pasan** describiendo el comportamiento roto. Cuando esto se arregle,
las dos primeras cambian de signo y hay que reescribirlas: a propósito.

Y la tercera prueba fija lo otro: **no existe ninguna ruta que le diga al maestro
quiénes son sus alumnos.** El formulario arranca en
`{ ...COMPETIDOR_FORM_VACIO, club }` (`app/maestro/page.tsx:109`), así que el
nombre, la fecha de nacimiento, el género, el documento y el cinturón —que no
cambian nunca— cuestan exactamente lo mismo de teclear que el peso, que sí
cambia. Multiplicado por cuarenta alumnos y por cada campeonato.

### Qué se hace

1. **`GET /api/inscripciones/maestro/alumnos`** — los competidores de los clubes
   de ese maestro, con todo lo suyo. Es la ruta que hoy devuelve 404.
2. **El maestro elige de una lista, no rellena un formulario.** Busca a su
   alumna, la marca, y **solo escribe lo que cambia**: el peso, y las
   modalidades. Lo demás viene de la ficha y se puede corregir si hace falta —
   una alumna que subió de cinturón desde el campeonato pasado.
3. **`maestro_inscribir` acepta `competidor_uid`** además del objeto entero:
   con `uid` **reutiliza la ficha** y solo crea la inscripción. Sin él, sigue
   creando —es como se da de alta a quien compite por primera vez.
4. **Y cuando llega un objeto entero con un documento que ya existe**, deja de
   ser un 400 y pasa a ser lo obvio: **es esa persona**. Se reutiliza la ficha,
   se actualiza lo que venga distinto, y se avisa de que se reutilizó. Un
   documento repetido nunca fue un error del maestro: era el sistema sin
   entender que las personas vuelven.
5. **El peso vive en la INSCRIPCIÓN, no en la ficha** — y esto ya es así
   (`inscripciones.peso`, `models/competidor.py:211`), solo que hoy no se
   aprovecha porque la ficha nace nueva cada vez. Con la ficha reutilizada, el
   peso del año pasado no contamina el de este.

### Lo que esto desbloquea, y por eso va primero

- **El día del campeonato**: cuarenta inscripciones que hoy son cuarenta
  formularios en blanco pasan a ser cuarenta casillas. Es la diferencia entre
  que los maestros inscriban la semana antes o el mismo sábado a mano.
- **F3 (el panel del alumno) empieza a ser posible**: sin ficha estable no hay
  «mis resultados».
- **D5 (el atleta independiente)** cae solo: una ficha que no depende de tener
  cuenta ya es exactamente lo que D5 pide. Lo único que falta es poder
  engancharle la cuenta después, que es el punto 1 de F3.

---

## F6 · Los paquetes llevan la identidad — 🟡 a medias

**Dónde:** `dinamyt-combat/backend/app/api/sincronizacion.py`.

> **Hecho: la identidad del USUARIO.** `_usuario_a_dict` exporta `eco_sub`; el
> importador empareja por `uid` → `eco_sub` → correo (en ese orden: el correo
> se cambia en el portal, el `sub` no cambia nunca), **nunca pisa** un enlace
> que ya esté puesto ni le da a dos filas la misma cuenta, y el informe previo
> gana su línea de «identidades: N enlazadas · N sin enlazar».
> `VERSION_PAQUETE` sube a 2 y un paquete de la 1 **se importa igual** —los
> campos nuevos son opcionales—, que es lo que hace falta el 9 de octubre.
>
> **Y el hallazgo, que toca al orden de la PARTE 4.** Los otros tres datos de
> esta fase **no tienen columna todavía**, y las columnas las crean fases que
> van DESPUÉS en el orden:
>
> | Dato | Dónde tendría que vivir | La crea |
> |---|---|---|
> | `usuarios.roles` | Campeonatos | **F2** (nº 6) |
> | `competidores.eco_sub` / `usuario_uid` | Campeonatos | **F3** (nº 7) |
> | `org_id` | **no existe en ninguna tabla** (§1.3) | **F4** (nº 8) |
>
> O sea que F6 no se puede *terminar* en el puesto nº 2 — pero **sí se puede
> hacer la parte que importa**, y es justo la que sostiene su lugar en la
> lista: «cada paquete que se importe sin `eco_sub` deja cuentas sin
> enlazar». Esa mitad ya está. Lo demás se retoma **dentro de cada fase que
> crea su columna** (F2, F3 y F4 se llevan cada una su línea del paquete), en
> vez de esperar a que estén las tres.

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

## F6-bis · Bajarse la VPS al PC del evento — **ya funciona; lo que falta es saber cuándo se hizo**

*(añadido el 9 de septiembre de 2026, tras la pregunta de si esto estaba en el
plan. **No estaba, y hacía falta que estuviera** — aunque no por lo que
parecía.)*

### La buena noticia: la bajada ya existe, y es re-ejecutable

`exportar_campeonato()` en la VPS y `POST /sincronizacion/importar` en el local
llevan funcionando desde el 26 de julio, con vista previa antes de escribir
nada. Y lo importante para lo que se pregunta:

- **El modo por defecto es `fusionar`** (`sincronizacion.py:1027`). Reimportar
  **añade lo nuevo y actualiza lo cambiado, sin duplicar**: la identidad viaja
  por `uid`, no por el id de la tabla.
- Así que **sí**: si el jueves entran tres inscripciones nuevas y un maestro se
  crea una cuenta, se vuelve a exportar el viernes, se vuelve a importar, y
  aparecen. Las que ya estaban no se tocan.
- Y hay un **freno**: si en el local ya hay llaves `activa` o `terminada`, la
  importación se niega con un 409 —*«importar podría pisar resultados»*— salvo
  confirmación explícita (`sincronizacion.py:1076`). Correcto y hay que dejarlo.

O sea que la respuesta a *«¿hay que construir la bajada?»* es **no**. Se baja
tantas veces como haga falta **hasta que empiece a competirse**, y desde ese
momento ya no, a propósito.

> **Y no puede ser al revés.** `B3-RIESGOS.md` §1.1: pasarse a local a mitad de
> campeonato es imposible —el paquete no lleva `combates` ni el estado vivo del
> tatami, y sin internet ni siquiera se puede exportar—. **El local no es el
> plan B: es el plan A.** El campeonato corre en local desde el minuto uno, y la
> VPS puede estar apagada esos tres días.

### La mala: nadie sabe de cuándo es la copia

Eso es lo que sí falta, y es barato:

1. **El local dice qué se trajo y cuándo.** Una línea en `/admin`:
   > *Copia traída de la VPS el 7 de octubre a las 18:42 · 148 competidores ·
   > 160 inscripciones · 12 usuarios*

   Hoy esa información **existe** —el sobre del paquete lleva `exportado_por` y
   la fecha (`_sobre()`)— pero se enseña una vez en la vista previa y se pierde.
   Se guarda en `ajustes` y se pinta siempre.
2. **Y avisa cuando se está quedando vieja.** Si la última bajada tiene más de
   24 h y todavía no se compite, lo dice en amarillo. El sábado a las siete de
   la mañana nadie se acuerda de si la copia incluye las inscripciones del
   jueves, y esa duda se resuelve **volviendo a bajar**, que cuesta dos minutos
   y no rompe nada.
3. **El runbook, escrito en `INICIAR-LOCAL.md`.** Hoy el manual del día del
   evento **no menciona la bajada en ninguna parte**: salta de «instala» a
   «enciende». Le falta el paso de en medio, que es el que trae el campeonato:
   - **La víspera, con internet:** exportar de la VPS → importar en el local →
     comprobar que los números cuadran con lo que dice la VPS.
   - **Y una última bajada la mañana del evento si todavía hay red**, antes de
     que se active la primera llave.
   - **Asignar contraseñas a quien vaya a necesitarlas**, porque las contraseñas
     **no viajan** en el paquete (decisión de
     `PLAN-SINCRONIZACION-LOCAL-ONLINE.md`) y los jueces entran con el QR.

### Lo que F6 le añade a esto

F6 mete `eco_sub`, `roles` y `org_id` en el paquete. Sin eso, las cuentas que
bajan de la VPS llegan **sin su enlace al ecosistema**, y al volver a subir los
resultados se reconcilian por correo — que es el camino que puede acabar en
`correo_ocupado`. Por eso F6 va antes que el evento y no después.

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

### Cómo se identifica el PC del evento — y por qué NO guarda ninguna llave

*(reescrito el 9 de septiembre. La primera versión decía «un token de
instalación en el `.env`, caducado a los 90 días». La pregunta de por qué hacía
falta una credencial nueva era la buena, y la respuesta es que no hace falta.)*

El endpoint de destino exige un administrador (`resultados.py:318`), y **un
programa no puede teclear una contraseña**. Había dos formas de resolverlo:

| | Cómo | Por qué no / por qué sí |
|---|---|---|
| **Llave de máquina** | Un token largo en el `.env` del PC del evento | Automático del todo, sin humano. Pero es **una llave viva en un portátil que viaja a los gimnasios**, y que hay que acordarse de renovar. Descartada |
| **La sesión del propio admin** ✅ | Cuando vuelve la red, el admin **entra a Campeonatos local con su cuenta de DINAMYT** y desde ahí se vacía la cola | **Nada guardado.** El permiso es el suyo, dura lo que dura su sesión, y queda registrado quién publicó qué |

**Se elige la segunda**, y la razón de fondo es la de todo este plan: **no se
inventa una credencial nueva cuando ya hay una que sirve.** El administrador ya
tiene su cuenta de DINAMYT; lo que faltaba no era una llave, era que el PC
supiera aprovechar el momento en que su dueño está delante y con red.

**Qué significa en la práctica, el lunes después del campeonato:**

1. El PC del evento vuelve a casa y coge WiFi con internet.
2. El admin abre Campeonatos local y **entra normalmente**. En el gimnasio había
   entrado con la contraseña local (§F0-bis); ahora, con red, el botón de
   «Entrar con DINAMYT» funciona y es el que se usa.
3. La cola se vacía sola, en segundo plano, mientras él hace otra cosa.
4. Si no entra nadie, la cola espera. **No se pierde nada** — y el USB de
   siempre sigue estando.

> **Lo que esto NO es.** No cambia cómo entran las personas el día del evento:
> ahí sigue siendo la contraseña de esa instalación y el QR del tatami, porque
> no hay internet (`INICIAR-LOCAL.md` §3.1). Esto solo ocurre **después**, con
> red, y con el administrador delante.

### Las piezas

1. **La cola.** Tabla local `cola_sync`: `export_uuid`, `payload`, `intentos`,
   `ultimo_error`, `enviado_at`. Publicar un podio **encola**; no envía.
3. **El cartero.** Cuando hay una sesión de ecosistema viva y hay red:
   `POST /api/resultados/importar` con el cuerpo JSON, que **ya es idempotente
   por `export_uuid`** (`resultados.py:318`). Reintento con espera creciente;
   **nunca mientras haya un combate en marcha.**
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

# PARTE 4 · El orden — TODO antes del 8 de octubre

*(reescrita el 9 de septiembre de 2026, tras D6. La versión anterior repartía el
plan en «antes» y «después del campeonato». **Ya no hay después**: lo que no
esté el 8, no existe el 9.)*

### Lo único que sigue siendo intocable

- **Los días 9, 10 y 11 no se despliega nada.** El 8 solo arreglos
  (`OPERAR.md` §1.5). Eso no es prudencia opcional: es que hay gente delante y
  una llave en marcha.
- **La última semana de septiembre se corre el ensayo** de `OPERAR.md` §6.0, y
  se anotan los números. Todo lo que toque login, roles o identidad **tiene que
  estar dentro antes de ese ensayo**, o el ensayo no mide lo que va a correr.

Eso da **dos fechas reales**, y son las que ordenan lo de abajo:

| | |
|---|---|
| **~26 de septiembre** | Todo lo que toca identidad, roles o login, DENTRO. Después se corre el ensayo sobre lo que de verdad va a correr el 9 |
| **8 de octubre** | Todo lo demás, DENTRO. Y a partir del 9, nada |

### EL ORDEN DE TRABAJO — se empieza por arriba

| # | Fase | Qué es | Por qué ahí | Bloquea a |
|---|---|---|---|---|
| **1** | **F5-bis** ✅ | La ficha del alumno se reutiliza | **Lo único ROTO.** Un maestro no podía inscribir a su alumna en el segundo campeonato del año | F3, D5 |
| **2** | **F6** 🟡 | Los paquetes llevan `eco_sub`, ~~`roles`, `org_id`~~ | Todo lo que baje de la VPS antes de tenerlo llega sin enlace al ecosistema. `eco_sub` hecho; los otros dos **no tienen columna hasta F2 y F4** y se hacen ahí | F6-bis, F8 |
| **3** | **F6-bis** | La copia dice de cuándo es + el runbook | Sin esto, el sábado nadie sabe si la copia trae las inscripciones del jueves | — |
| **4** | **F7** | Encender en local con comprobaciones | Se nota el 9 a las siete de la mañana. **No toca nada de nadie**: se puede hacer en paralelo desde el primer día | — |
| **5** | **F1** | El pase lleva varios roles (ecosystem) | Empieza el bloque de identidad. **Todo esto, dentro antes del ensayo del ~26 de septiembre** | F2 |
| **6** | **F2** | Campeonatos entiende varios roles | De cara al usuario **no cambia nada**: es el andamio de F3 | F3 |
| **7** | **F3** | El panel del alumno + el atleta independiente | Lo que multiplica por cien quién entra. Necesita ficha estable (1) y roles (6) | — |
| **8** | **F4** | La organización llega a Campeonatos | El admin único por organización | F5 |
| **9** | **F5** | Inscribirse por invitación | El admin invita clubes al campeonato | — |
| **10** | **F8** | La subida automática de resultados | Ocurre **después** del evento, con red. Lo último que hace falta | — |
| — | ~~F9~~ | Retirar los andamios | **Después del 11.** Su definición es «cuando lleve un campeonato real encima» | — |

### Los tres carriles, para no trabajar en serie lo que no lo es

```
CARRIL A (el evento)     1·F5-bis ──► 2·F6 ──► 3·F6-bis
                                                   │
CARRIL B (independiente)          4·F7 ────────────┤  ← desde el primer día
                                                   │
CARRIL C (identidad)     5·F1 ─► 6·F2 ─► 7·F3      │
                                    └─► 8·F4 ─► 9·F5
                                                   │
                                          10·F8 ◄──┘
```

**A y B no se estorban.** F7 no toca base de datos ni permisos, así que puede
avanzar en paralelo con cualquier cosa. El carril C es el único que toca login e
identidad, y por eso entero **antes del ensayo del ~26 de septiembre**.

### Las tres reglas del orden, y por qué

**F5-bis va primera y no es discutible.** Es la única fase que **repara**; todas
las demás añaden. Y es la que más se nota el día del evento: cuarenta
inscripciones que hoy son cuarenta formularios en blanco.

**F6 va antes que cualquier bajada de la VPS.** Cada paquete que se importe sin
`eco_sub` deja cuentas sin enlazar, y eso se arrastra hasta la subida de vuelta.

**Lo que no se puede adelantar:** F3 sin F2 (el panel escrito contra el modelo
de un rol se escribe dos veces), F8 sin F6 (subiría filas huérfanas), F5 sin F4
(no hay organización a la que invitar).

### Y el riesgo de meterlo todo antes, dicho una vez

Es apretado y toca los tres eslabones que el ensayo de septiembre mide. Lo que
lo hace asumible no es optimismo: es que **cada fase deja la aplicación
desplegable** —esa condición estaba en el plan desde el principio y ahora es la
que sostiene el calendario—, que F2 no cambia nada de cara al usuario, y que el
ensayo de §6.0 corre **después** de lo pesado y **antes** del evento, que es
justo para lo que existe. Si algo se cae, se cae con margen y se puede dejar
fuera sin arrastrar al resto.

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
  (`OPERAR.md` §4.13) y es independiente de todo esto. **Y ahora menos que
  nunca**: es la puerta por la que el modo local crea usuarios sin ecosistema, o
  sea la que hace falta el 9 de octubre.
- **No toca cómo entran las personas en el modo local.** Contraseña de esa
  instalación y QR del tatami, como hoy (§F0-bis, `INICIAR-LOCAL.md` §3.1). Lo
  único que F8 añade ocurre **después** del evento y con red.
- **No lleva el ecosystem al gimnasio.** Decidido que no (§1.4 del mismo).
- **No sincroniza en tiempo real.** Sigue siendo un sentido y por tandas.
- **No toca el motor de combate ni el de figuras.** Ni una línea de
  `backend/app/engine/`.
