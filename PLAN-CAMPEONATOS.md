# PLAN CAMPEONATOS — de consola de jueces a aplicación del ecosistema

> Estado: **en marcha**. Escrito el 9 de septiembre de 2026, revisado el mismo
> día, y empezado esa misma tarde por el orden de la PARTE 4:
>
> | | | |
> |---|---|---|
> | **F5-bis** | ✅ **hecha** | La ficha del alumno se reutiliza. Backend, pantalla del maestro y las pruebas que fijaban lo roto, dadas la vuelta |
> | **F6-a** | ✅ **hecha** | El paquete lleva `eco_sub`. Los otros tres datos de F6 **no tienen todavía dónde vivir**, así que F6 se reparte: ver «F6 se reparte» en la PARTE 4 |
> | **F6-bis** | ✅ **hecha** | El local dice de cuándo es la copia y avisa cuando envejece. Y el runbook de la víspera, en `INICIAR-LOCAL.md` |
> | **F7** | ✅ **hecha** | `INICIAR.bat` comprueba antes de arrancar, espera al «listo» de verdad y saca la dirección en QR. `APAGAR.bat` apaga por puerto |
> | **F1** | ✅ **hecha** | El pase lleva `roles_campeonatos` además de `role_campeonatos`, y el portal tiene casillas para marcarlos. Con dos cambios sobre lo escrito: ver la nota dentro de F1 |
> | **F2** + **F6-b** | ✅ **hecha** | Campeonatos guarda y lee varios papeles, el pase los SUMA a quien ya estaba, y lo que quita la consola se recuerda. El paquete lleva `roles`. Con una contradicción del plan resuelta: ver la nota dentro de F2 |
> | **F3** + **F6-c** | ✅ **hecha** | El alumno entra a **su panel** (`/mi-panel`): inscripciones con su estado, próximos campeonatos, su maestro, resultados y números. La ficha se reclama con documento y fecha, o la enlaza el admin, y viaja en el paquete. Las lecturas del personal se cerraron antes de abrir la puerta. Con cuatro cambios sobre lo escrito: ver la nota de la parte 3 dentro de F3 |
>
> | **F4** + **F6-d** | ✅ **hecha** | La organización del ecosistema llega a Campeonatos (`org_id` en usuarios y campeonatos), la regla del admin único al crear el espejo y el informe de D3 para el superadmin. El punto 3 (que `org_id` decida quién es dueño) **a propósito no**: ver la nota dentro de F4 |
> | **F5** + **F6-e** | ✅ **hecha** | El admin invita clubes desde la ficha del campeonato (buscador contra el directorio de DINAMYT, `GET /sync/clubes`), el maestro invitado inscribe en el workspace del campeonato, y la invitación viaja en el paquete. El documento pasó a ser único **por workspace** |
> | **F8** | ✅ **hecha** | Los resultados del PC del evento suben solos a internet con la sesión del propio admin (nada guardado en el PC). Endurecida el 25 de septiembre, y con su puerta: el portal devuelve el pase al PC del evento visto desde sí mismo (`localhost:3000`), opción A |
>
> **Todas las fases de F1 a F8 están escritas y probadas** (también contra
> PostgreSQL con RLS). **Nada del carril C está desplegado todavía**: la VPS
> sigue con Campeonatos en `8dbc599` y el portal en `583abc4` (comprobado el
> 25 sep). Lo que queda es desplegar (PARTE 4, nº 0), las decisiones del nº 5,
> el ensayo §6.0 y, tras un campeonato real, F9.
>
> **⏱ Ya no hay fecha límite (D7, 24 de septiembre de 2026).** El campeonato
> del 9, 10 y 11 de octubre **no se hace**, y el siguiente es el año que viene,
> sin fecha todavía. Lo que ordenaba este plan —«lo que no esté el 8 no existe
> el 9» (D6)— deja de valer: ahora se hace **bien y con pruebas**, fase a fase,
> y lo que estaba aplazado «hasta después del campeonato» ya se puede
> programar. La PARTE 4 está reescrita con eso. Lo que sí está implementado se
> cuenta en la PARTE 1, con archivo y línea, para que el plan se apoye en lo
> que hay y no en lo que uno recuerda que hay.
>
> ### 📍 Dónde quedamos — LEER PRIMERO (se actualiza al cerrar cada sesión)
>
> **Sesión del 25 de septiembre de 2026.** Ver el diario al final de este
> archivo (**PARTE 6**): qué se hizo, qué quedó a medias y qué sigue.
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

> **Y dejó de serlo el 13 de septiembre de 2026 (F3).** `competitor` y
> `student` crean el espejo con `competidor` de principal (`rol_principal` en
> `espejo.py`), el login lo manda a `/mi-panel`, y el portal le pone el botón
> de entrar (`entraACampeonatos`). `sin_consola` sigue existiendo, pero ya solo
> le llega a quien no trae NINGÚN papel de Campeonatos, y dice eso.

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

> **Cómo quedó (F3, 13 sep 2026):** esquivado, no pagado. La fila nace al
> canjear el pase —la primera vez que la persona abre Campeonatos—, así que
> los alumnos que nunca entran siguen sin existir aquí; y `/admin` → Jueces
> los esconde detrás de un «+N competidores», con el buscador encontrándolos
> igual.

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

**~~D6 · TODO tiene que estar funcional para el 9 de octubre.~~** **REVOCADA
el 24 de septiembre de 2026**, ver D7. Decía: no hay «después del campeonato»,
lo que no esté antes del 8 no existe el día del evento, y el plan se ordena por
lo que más duele el sábado por la mañana.

**D7 · No hay campeonato en octubre: se hace con tiempo** *(24 de septiembre de
2026)*. El del 9, 10 y 11 de octubre no se celebra y el siguiente es el año que
viene, sin fecha. Consecuencias:

- **No hay congelación de despliegues** el 8–11 de octubre (`OPERAR.md` §1.5
  se actualiza).
- **El ensayo de `OPERAR.md` §6.0 pasa a «antes del próximo campeonato»**, no a
  la última semana de septiembre. Sigue siendo obligatorio: lo que cambia es
  cuándo.
- **Lo aplazado «hasta después del campeonato» se puede programar**: el
  `/sync/rol` de Campeonatos (`OPERAR.md` §6.1), el bloqueo por plan vencido
  (PARTE 5) y retirar `POST /auth/register` en internet. Van a la PARTE 4.
- **F9 sigue esperando un campeonato real**: su definición no era una fecha,
  era «cuando F1–F8 lleven un campeonato encima». Eso será el año que viene.
- **Cada fase se prueba también contra PostgreSQL** (`tests/test_rls_postgres.py`):
  la batería corre en SQLite, donde RLS no existe, y así se escapó un fallo
  que rompía el flujo entero del maestro (ver PARTE 6).

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

## F1 · El pase lleva varios roles (ecosystem) — ✅ hecha

**Dónde:** `apps/ecosystem-api` (monorepo `dinamyt`).

> **Hecho, el 13 de septiembre de 2026.** Los puntos 1 a 3 tal cual, el 4 de
> otra manera, y una regla que no estaba escrita:
>
> - **La migración `0023_roles_campeonatos`** añade `roles_campeonatos` (`text[]`)
>   a `org_members` **y también a `org_member_bajas`**, que el plan no nombraba:
>   readmitir a alguien tiene que devolverle todos sus papeles, igual que la
>   0018 le devuelve el rol. Probada sobre una base vacía (de la 0000 a la 0023)
>   y el relleno, con filas de muestra.
> - **`roles-por-app.ts`** gana `rolesParaApp`, `rolPrincipal`,
>   `propiosDeCampeonatos` y `rolesCampeonatosDelPase`, y la traducción
>   `member → competitor`. Una fila escrita por las puertas de un solo papel
>   —invitar, aceptar una solicitud— sigue contando: si la lista está vacía,
>   vale el singular.
> - **El pase lleva las dos formas**, y Academy y Membresías no se enteran.
> - **Cambiar el rol general vacía también la lista**, como ya vaciaba las
>   otras tres excepciones. Si no, el rol nuevo no llegaría a Campeonatos.
>
> **Cambio 1 · la pantalla del punto 4 no tiene roles.** `mi-organizacion/
> miembro/[id]` es el editor de PERFIL —nombre, sangre, cinturón—; el rol se
> cambia en la fila de la lista del club (`FilaMiembro`), y lo que se cambia
> ahí es el rol GENERAL. **No había ningún desplegable de Campeonatos que
> convertir en casillas.** Las casillas son nuevas: van plegadas en esa fila
> («Campeonatos: Maestro + Juez»), con su ruta
> `PATCH /organizations/:id/members/:userId/campeonatos`. Y reparten **lo que
> esa organización ya daba** (`ROLES_POR_TIPO`): un club da maestros, coaches y
> competidores; la federación, administradores y jueces. Lo que alguien ya
> tenía se le puede quitar aunque no se pueda dar — si no, marcarle «maestro» a
> un alumno que llegó con «juez» obligaría a quitarle el de juez.
>
> **Cambio 2 · el singular NO es «el de mayor rango», y la lista suma clubes.**
> Al escribirlo apareció que el caso que motiva todo esto casi nunca vive en
> una fila: el maestro lo es de SU club y juez lo es de la FEDERACIÓN. Son dos
> pertenencias, y mirando solo la principal el pase seguiría sin poder decir
> «maestro y juez». Así que:
>
> | | De dónde sale |
> |---|---|
> | `roles_campeonatos` | Todos los papeles de **todas** sus pertenencias, sumados |
> | `role_campeonatos` | **La pertenencia principal, como hasta hoy.** Dentro de ella, el de mayor rango |
>
> Si el singular fuera el mayor de la suma, **el administrador de una
> federación que además es alumno de un club entraría a Campeonatos como
> administrador** de un despliegue para otro, sin que nadie hubiera tocado
> nada. Hay una prueba que lo fija.
>
> **Pruebas:** los tres archivos que nombraba el plan, ampliados — 26 pruebas
> nuevas. La batería entera del ecosistema, en verde.
>
> ⚠️ **Al desplegar, el orden importa** (`OPERAR.md` §1.2 y §1.3): compilar
> `packages/shared` antes que la API, y **migrar antes de reiniciar**. El código
> nuevo pide `roles_campeonatos` al firmar el pase: sin la columna, **no entra
> nadie**. Campeonatos no se toca: todavía no lee la lista.

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

## F2 · Campeonatos entiende varios roles — ✅ hecha (con F6-b)

**Dónde:** `dinamyt-combat/backend`.

> **Hecho, el 13 de septiembre de 2026.** Los puntos 1, 3, 4 y 5 como estaban
> escritos, y el paquete lleva `roles` (F6-b, versión 3). Y **una
> contradicción que el plan tenía dentro**, resuelta así:
>
> **El plan pedía dos cosas que no caben a la vez.** El punto 6 —y D2, que ya
> estaba decidido— dice que el pase **añade** los papeles que la fila no
> tiene. La nota del final dice que en F2 *«ningún endpoint gana ni pierde
> permisos»*. Pero añadir `juez` a un maestro es, justamente, que pueda
> juzgar. **Manda D2**, porque es la decisión y es lo único que hace servir a
> F1. Con dos límites:
>
> - **El pase nunca da `admin`** a quien ya estaba. El mando de los
>   campeonatos se pone a mano aquí (`OPERAR.md` §1.5), y F4 todavía no ha
>   contado cuántos administradores hay por organización: repartir más desde
>   fuera antes de ese informe es lo que D3 pide no hacer. Al CREAR la fila sí
>   puede traerlo, como hasta hoy.
> - **`require_maestro` sigue preguntando por el principal.** Con `tiene_rol`,
>   un administrador que además es maestro entraría a los endpoints del
>   maestro, que miran el workspace del admin que lo creó: dejaría de ver sus
>   propios campeonatos. `require_admin` sí pasa a `tiene_rol`, y da lo mismo
>   que antes porque `admin` es el papel de más rango.
>
> **Lo que el plan no decía y hacía falta · `roles_quitados`.** Con «el pase
> añade» y «solo la consola quita» a secas, quitarle el de juez a alguien
> desde la consola duraba **hasta su siguiente inicio de sesión**, cuando el
> pase se lo volvía a sumar. Así que la consola RECUERDA lo que quita, el pase
> no puede devolverlo, y si la consola lo vuelve a dar se olvida. Quién lo
> quitó queda en el registro, que es lo que pedía «con nombre y apellidos».
>
> **Tres cosas menores:**
>
> - **`ROLES_VALIDOS` no gana `competidor`.** Queda en otra lista, `PAPELES`:
>   se puede TENER, pero no ser SOLO eso, porque hasta F3 no hay pantalla para
>   quien solo compite y el login lo mandaría al panel del juez. El pase del
>   alumno sigue sin crear fila (§1.5-ter), también hasta F3.
> - **El punto 6 del frontend pasa a F3.** «Con varios papeles se entra al
>   panel del competidor» necesita un panel del competidor. Hasta entonces se
>   entra por el principal, como hoy.
> - **Un arreglo que salió al hacerlo:** a quien ya estaba enlazado,
>   `resolver_espejo` le ponía su club y no hacía `commit`, así que se perdía
>   al terminar la petición. Ahora se guarda.
>
> **Pruebas:** `tests/test_roles_multiples.py`, 34 nuevas. La que más importa:
> para toda fila anterior a F2, `roles` y `puede_ser_juez` contestan
> exactamente lo mismo que antes, sin backfill.
>
> **Despliegue:** nada que migrar a mano. `schema_compat` crea `roles` y
> `roles_quitados` al arrancar, como hizo con `clubes`. Da igual el orden con
> el ecosistema: sin `roles_campeonatos` en el pase, se lee `role_campeonatos`.

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

## F3 · El alumno entra: el panel del competidor — ✅ hecha (con F6-c)

**Dónde:** `dinamyt-combat` (backend + frontend). **Es la fase que le cambia la
cara al producto**, y por eso va sola.

> **Parte 1 · la puerta, hecha el 13 de septiembre de 2026.** El aviso del
> final de esta fase —*«antes de desplegar F3 hay que repasar los endpoints uno
> a uno»*— se hizo PRIMERO, porque dejar entrar al alumno sin haberlo hecho es
> abrir la puerta antes de mirar qué hay detrás. Salió del grafo
> (`graphify affected "usuario_actual"`) y de un inventario de las 77 rutas con
> la guarda de cada una:
>
> | Lectura | Qué dejaba ver a una sesión que no fuera admin | Quién la usa | Ahora |
> |---|---|---|---|
> | `GET /api/competidores` | **Todas las fichas de todos los workspaces, con documento y fecha de nacimiento** | solo `/admin` | solo admin, su workspace |
> | `GET /api/inscripciones/campeonato/:id` | Las inscripciones con la ficha entera | solo `/admin` | solo admin, su campeonato |
> | `GET /api/campeonatos/:id` | El campeonato con tatamis y categorías | solo `/admin` | personal |
> | `GET /api/llaves/campeonato/:id`, `/llaves/:id` | Las llaves completas | `/admin` | personal |
> | `GET /api/llaves/tatami/:id` | Las llaves del tatami (sin guarda) | panel del juez | personal |
> | `GET /api/tatamis/campeonato/:id`, `/tatamis/:id` | Tatamis y quién los juzga | `/admin` | personal |
> | `GET /api/combates/*` | El historial de combates (sin guarda) | nadie | personal |
>
> **Las dos primeras filas eran un hueco YA, no en F3.** Un maestro o un juez
> con sesión recibía las fichas de todos los clubes de todos los
> administradores. Nadie lo notó porque ninguna pantalla suya las pide.
>
> Revisado y sin cambios: ningún `to_dict` enseña el PIN de un tatami; el
> socket del tatami exige asignación para actuar de juez; categorías y la
> plantilla de Excel no llevan datos de nadie; `GET /api/campeonatos` ya filtra
> por workspace a todo el mundo. «Personal» es `require_personal()` en
> `scoping.py`: papel principal admin, maestro o juez, y activo — para
> cualquiera que tuviera sesión antes de F3 da lo mismo que no tener guarda,
> salvo un usuario dado de baja, que deja de leer.
>
> ### Los resultados no están enlazados a nadie — y eso decide el panel
>
> Al ir a construir «mis resultados» (punto 4), el grafo enseñó que **ningún
> resultado apunta a una ficha**:
>
> - `Llave.estructura` guarda a cada competidor como `{id, nombre, club}`, y ese
>   `id` es **la posición dentro de la llave**, no el competidor
>   (`api/llaves.py:55`, `api/campeonatos.py:476`).
> - El ranking de figuras y los combates sueltos guardan **solo nombres**
>   (`_construir_resultados` en `api/resultados.py`).
>
> O sea que «mis podios», «mis estadísticas» —y la promesa de D5 de que el
> historial queda colgando de la ficha— **hoy solo se pueden sacar comparando
> nombre y club**. Eso falla con dos homónimos en un campeonato y con cualquier
> nombre corregido después. Las dos salidas, por orden de coste:
>
> | | Qué es | Lo bueno | Lo malo |
> |---|---|---|---|
> | **A · Por nombre y club** | El panel busca los resultados comparando el texto | Sale ya, y trae TODO el histórico | Homónimos y nombres corregidos dan resultados de otro, o ninguno |
> | **B · Enlace desde hoy + nombre para lo viejo** | Las llaves que se generen desde ahora guardan el `uid` de la ficha; lo anterior se busca por nombre y se enseña marcado «sin confirmar» | Lo nuevo es exacto, lo viejo se ve y se dice que es aproximado | Toca cómo se generan las llaves a menos de un mes del campeonato |
>
> **Decidido el 13 de septiembre de 2026: B.** Lo nuevo exacto, lo viejo por
> nombre y avisando.
>
> **Parte 2 · el enlace, hecha el mismo día.** Lo que la opción B exigía
> comprobar primero —que el motor, el socket y el PDF ignoran el campo nuevo—
> salió bien: todo lo que LEE una llave mira solo `nombre` y `club`. Lo que
> perdía el enlace eran los sitios que REHACEN al competidor, y eran cinco:
>
> - **La generación automática ya lo tenía y lo tiraba.** La sección lleva
>   `competidor_id` (`campeonatos.py`), y tres líneas después se construía la
>   llave con nombre y club. Ahora lleva `competidor_uid` —el uid, no el id: es
>   el que no cambia entre la instalación local y la de internet—.
> - **`_comp_estructura`**, **combinar** y **mover** lo conservan
>   (`_comp_plano`). Los partidos guardan el mismo competidor, así que el
>   podio lo hereda sin tocar el avance del cuadro.
> - **Editar** una llave regenera el cuadro con la lista que manda el
>   formulario, que solo trae nombres: sin arreglo, añadir UN competidor le
>   quitaba el enlace a todos. `_conservar_enlaces` se lo devuelve por nombre y
>   club — **y con dos homónimos de fichas distintas no adivina**: ninguno lo
>   recupera.
> - **Figuras:** el servidor pone el enlace al cargar el grupo en el motor
>   (`_competidores_de_llave_a_figuras`), y el ranking lo hereda. **No viaja en
>   el evento**: el motor no lo lee del cliente, así que nadie puede colgarle un
>   resultado a la ficha de otra persona. Hay prueba de eso.
>
> **Lo que no enseña el uid:** `podio_llave` solo lo añade con `con_uid=True`,
> porque alimenta los resultados PÚBLICOS; y el ranking público de figuras ya
> elige campo a campo. Una llave hecha a mano y los combates sueltos siguen
> sin enlace —no hay ficha que enlazar— y el panel los buscará por nombre,
> marcados «sin confirmar». El uid sí viaja dentro del estado del tatami, que
> ven las pantallas: es un valor opaco que no identifica a nadie sin la consola.
>
> **Parte 3 · la puerta abierta, hecha el mismo 13 de septiembre.** Se
> despliega junta porque es lo que abre la puerta: la ficha enlazada a la
> cuenta, el espejo del competidor, `/api/mi/*`, el panel, el botón del portal
> y el filtro de `/admin`. Los siete puntos de abajo están, con **cuatro
> cambios sobre lo escrito** — los cuatro por leer el código:
>
> - **Solo `competidores.eco_sub`, sin `usuario_id`.** El id de la fila cambia
>   entre la instalación de internet y la del evento; el `sub` es el mismo en
>   las dos y viaja en el paquete sin traducir nada (**F6-c**,
>   `VERSION_PAQUETE` 4). Sin `unique`: una persona puede tener una ficha en
>   cada workspace que la inscribió, y las dos son suyas.
> - **De los tres caminos del punto 1 hay dos, más el paquete.** Reclamarla
>   (`POST /api/mi/ficha/reclamar`: documento **y** fecha de nacimiento, cinco
>   intentos cada quince minutos, y «no existe» contesta igual que «la fecha no
>   cuadra») y enlazarla a mano (`PUT`/`DELETE /api/competidores/:id/cuenta`,
>   por el correo de alguien que ya entró). **El primero —«el maestro inscribe
>   desde el ecosistema y el alta trae el `sub`»— no tiene por dónde entrar
>   todavía**: el maestro elige entre sus fichas (F5-bis), no entre los
>   miembros de su club. Su sitio es F5, que es la que trae esa lista.
> - **`/api/mi/*` levanta la red de RLS** (`rls.sin_workspace`). Un maestro que
>   además compite tiene la ficha en el workspace de OTRO administrador: con la
>   red puesta su panel saldría vacío en PostgreSQL — y lleno en SQLite, que es
>   donde corren las pruebas. Lo que acota ahí es el `eco_sub` de la sesión. El
>   mismo bloque sirve para enlazar a mano: el espejo de un competidor nace sin
>   `creado_por_id`, y un admin normal no lo vería.
> - **«Sin confirmar» se busca solo en los campeonatos donde esa ficha está
>   inscrita.** Por nombre en todos sería colgarle a alguien los podios de un
>   homónimo de otra liga. Y un puesto con el `competidor_uid` de OTRA ficha no
>   es tuyo aunque se llame igual. Cuando en vivo no hay nada, se miran los
>   resultados importados del modo local con el mismo `export_uuid`: el 9 de
>   octubre es lo único que llega a internet, y sale por nombre hasta F8.
>
> Lo demás, como estaba escrito: el setter de `roles` acepta `competidor` solo;
> la consola no lo reparte pero lo conserva al editar (sin eso, corregirle el
> nombre daba 400); `/mi-panel` con inscripciones, próximos, maestro,
> resultados y números por año y modalidad; el portal elige el botón con
> `entraACampeonatos`; y `destinoDe` vive en un solo archivo
> (`frontend/src/lib/destino.ts`) — eran tres copias, y la que se olvidara
> mandaba al competidor al panel del juez.
>
> **El repaso de endpoints, cerrado.** El grafo (`graphify affected
> "usuario_actual"`) enseñó dos llamadas sin guarda que la parte 1 no listó: el
> interruptor de mantenimiento (exige superadmin) y el contexto de RLS (solo
> fija el workspace; el competidor recibe acceso total como el juez, y lo que
> lo acota son `require_personal` y `/api/mi/*`).
>
> **Al desplegar: Campeonatos ANTES que el portal.** Al revés, el botón le sale
> al alumno y Campeonatos lo devuelve con `sin_consola`.

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

## F4 · La organización llega a Campeonatos — ✅ hecha (con F6-d)

**Dónde:** `dinamyt-combat/backend`.

> **Hecho, el 24 de septiembre de 2026.** Todo vive en `app/organizacion.py`,
> más su enganche en `espejo.py`. Los puntos 1, 2, 4 y 5 como estaban
> escritos; el 3, **a propósito no**:
>
> - **Punto 1.** `usuarios.org_id` + `usuarios.org_nombre` y `campeonatos.org_id`
>   (texto: se copian, no se relacionan). La organización se reescribe en CADA
>   entrada desde el portal —es un reflejo, no algo que se edite aquí—, y el
>   nombre se pregunta solo cuando cambia. **Una sola pregunta al ecosistema
>   por entrada** (`_ClubDelPase`): el club del maestro y el nombre de la
>   organización salen de la misma. Sin `org_id` en el pase no se borra nada.
> - **Punto 2.** `rellenar_org_de_campeonatos`: al arrancar y cuando entra un
>   admin cuya organización se acaba de saber. Un campeonato que ya tiene
>   organización no se cambia nunca (el creador pudo cambiarse de club).
> - **Punto 3 NO se hizo: `org_id` todavía no decide quién es dueño de qué.**
>   Tres razones, escritas también en la cabecera de `organizacion.py`: (1)
>   RLS filtra por `created_by`, así que un segundo admin de la misma
>   organización vería el campeonato pero no sus llaves, fichas ni resultados
>   —una consola a medias—; (2) sería un cambio por sorpresa para los
>   duplicados de hoy, justo lo que D3 pide no hacer; (3) con un solo admin
>   por organización las dos reglas dicen lo mismo. Queda para cuando el
>   informe esté limpio, y entonces se decide si hace falta.
> - **Punto 4.** Al CREAR el espejo de un admin cuya organización ya tiene
>   otro activo: entra sin `admin` (con sus otros papeles, o `maestro` si no
>   le queda ninguno) y queda en el registro. El super-admin no cuenta.
> - **Punto 5.** `/admin` dice la organización debajo del nombre. El dato sale
>   de la lista fresca de usuarios, no de `localStorage`.
> - **La verificación de D3.** `GET /api/auth/organizaciones/administradores`
>   (solo superadmin) y su tarjeta en `/admin`, que no pinta nada si no hay
>   nada que decidir.
> - **F6-d.** Usuarios y campeonato viajan con `org_id` (el usuario, también
>   con `org_nombre`); `VERSION_PAQUETE` 5. El importador no pisa una
>   organización que ya esté (avisa), y un campeonato nuevo sin organización en
>   el paquete recibe la de quien lo importa.
>
> **De propina:** crear o editar un campeonato con una fecha mal escrita era
> un 500 (`date.fromisoformat` sin mirar); y editar sin cuerpo JSON, también.
> Ahora son un 400 con una frase.
>
> **Pruebas:** `tests/test_organizacion.py` (21), cuatro más en
> `test_sincronizacion.py` y el relleno contra PostgreSQL.
>
> **Al desplegar:** nada que migrar a mano (`schema_compat` crea las
> columnas). El informe sale vacío hasta que los admins vuelvan a entrar desde
> el portal: es cuando se sabe su organización.

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

## F5 · Inscribirse por invitación, no por herencia — ✅ hecha (con F6-e)

**Dónde:** `dinamyt-combat` (backend + frontend), y una ruta en el ecosystem.

> **Hecho, el 24 de septiembre de 2026.** Los cuatro puntos, con tres
> decisiones que el plan no tomaba y un arreglo de fondo que hizo falta antes:
>
> - **Punto 1.** `campeonato_clubes` (`models/invitacion.py`): `org_id` (el
>   club del ecosistema), `club_nombre` (siempre, y lo único en local),
>   `estado` y `uid`. **`aceptado` lo pone el sistema** con la primera
>   solicitud del club: participar ES aceptar, no hay botón que pulsar.
> - **Punto 2.** Sección «Clubes invitados» en la ficha del campeonato
>   (`components/ClubesInvitados.tsx`): buscar, invitar, retirar. El buscador
>   pregunta al directorio de DINAMYT por el canal servidor-a-servidor —
>   **ruta nueva en el ecosystem, `GET /sync/clubes`**, con los afiliados a la
>   federación que invita primero—. Sin conexión lo dice, sugiere los clubes
>   que ya conoce el workspace, y deja invitar por nombre.
> - **Punto 3.** Sin invitación, 403 «Tu club no está invitado a este
>   campeonato.» (`app/invitaciones.py`).
> - **Punto 4 (migración blanda), por otro camino: no se crean filas.** La
>   puerta vieja —«el campeonato es del admin que me creó»— se CONSERVA y se
>   SUMA a la nueva. Crear invitaciones para todos los maestros de hoy habría
>   obligado a invitar a los propios maestros en cada campeonato nuevo, y en
>   el modo local (sin ecosistema) es la única puerta que hay.
>
> **Decisión 1 · un nombre no es una llave.** La invitación solo por nombre
> NO deja entrar a nadie de fuera del workspace. Un nombre lo escribe
> cualquier admin en la ficha de cualquier maestro: si abriera la puerta, el
> admin de otra federación se colaría en tus campeonatos poniéndole a su
> maestro el nombre de un club invitado. Hay prueba.
>
> **Decisión 2 · todo lo del maestro invitado vive en el workspace del
> CAMPEONATO.** La ficha del alumno y la solicitud son de ese admin: es quien
> las ve y las acepta. Para operar ahí, `rls.en_workspace()` —solo después de
> comprobar la invitación—; y las lecturas del maestro (`/maestro/mias`, su
> lista de campeonatos) van con la red levantada y filtradas a mano, como
> `/api/mi/*`.
>
> **Decisión 3 · retirar no borra.** El club deja de ver el campeonato y ya no
> corrige sus rechazadas; lo que inscribió se queda y lo modera el admin.
> Volver a invitar lo reabre (la misma fila).
>
> **El arreglo de fondo: el documento es único por WORKSPACE.** Era único en
> toda la base, y eso chocaba con que la ficha es del workspace que la
> inscribió. Dos síntomas: en PostgreSQL, un admin que daba de alta a alguien
> con ficha en OTRO workspace recibía un **500** (RLS escondía la ficha ajena
> y el INSERT chocaba); y con F5, la misma alumna no podía ir a campeonatos de
> dos federaciones. Ahora `(created_by, documento)` es único, `schema_compat`
> cambia las bases viejas al arrancar (el índice era aparte, así que no hay
> que reconstruir la tabla ni en SQLite), `_aplicar_datos` y el importador
> comparan dentro del workspace, y **reclamar la ficha enlaza TODAS** las que
> tengan ese documento y esa fecha (una por organización con la que compitió).
> La prueba que fijaba el 400 viejo cambió de signo, a propósito.
>
> **F6-e.** Las invitaciones viajan en el paquete (`VERSION_PAQUETE` 6). Un
> paquete no BAJA una invitación que aquí ya se aceptó; `retirado` sí se
> aplica.
>
> **Pruebas:** `tests/test_invitaciones.py` (23), tres en
> `test_sincronizacion.py`, cinco contra PostgreSQL (el flujo entero del
> maestro invitado con RLS, el documento en dos workspaces, la migración del
> índice y el borrado en cascada), y `clubes.spec.ts` en el ecosystem.
>
> **Al desplegar:** el ecosystem (la ruta `/sync/clubes`) y Campeonatos, en
> cualquier orden: sin la ruta, el buscador dice que no hay directorio y se
> invita por nombre. Nada que migrar a mano.
>
> **Lo que queda fuera, a propósito:** avisar al maestro de que lo invitaron
> (hoy lo ve al entrar en su lista), y un interruptor por campeonato de «solo
> clubes invitados» que cierre también la puerta vieja. Ver PARTE 6.

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

## F6 · Los paquetes llevan la identidad — ✅ F6-a, F6-b, F6-c y F6-d hechas (la d, con F4, el 24 sep)

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
> | `usuarios.roles` | Campeonatos | **F2** (nº 6) — ✅ viaja desde el 13 sep |
> | `competidores.eco_sub` ~~/ `usuario_uid`~~ | Campeonatos | **F3** (nº 7) — ✅ viaja desde el 13 sep. Sin `usuario_uid`: el `sub` ya es el mismo en las dos instalaciones |
> | `org_id` | ~~no existe en ninguna tabla~~ (§1.3) | **F4** (nº 8) — ✅ viaja desde el 24 sep (versión 5) |
>
> O sea que F6 no se puede *terminar* en el puesto nº 2 — pero **sí se puede
> hacer la parte que importa**, y es justo la que sostiene su lugar en la
> lista: «cada paquete que se importe sin `eco_sub` deja cuentas sin
> enlazar». Esa mitad ya está, y se llama **F6-a**. Lo demás se retoma
> **dentro de cada fase que crea su columna** (F2, F3 y F4 se llevan cada una
> su línea del paquete), en vez de esperar a que estén las tres. El orden de
> trabajo de la PARTE 4 ya está reescrito así: ver «F6 se reparte».

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

## F6-bis · Bajarse la VPS al PC del evento — ✅ hecha

*(añadido el 9 de septiembre de 2026, tras la pregunta de si esto estaba en el
plan —**no estaba, y hacía falta que estuviera**, aunque no por lo que
parecía— e implementado ese mismo día.)*

> **Hecho.** Los tres puntos de «La mala: nadie sabe de cuándo es la copia»:
>
> - **`app/ultima_bajada.py`** guarda en `ajustes` de cuándo es la copia, de
>   dónde vino y qué trae, y `GET /api/sincronizacion/ultima-bajada` lo
>   devuelve con la edad ya calculada. Como el modo mantenimiento: es un dato
>   de la instalación, no de un workspace, y **leerlo no revienta nunca**.
> - **La línea en `/admin`** (`components/UltimaBajada.tsx`), en dorado cuando
>   la copia pasa de un día y todavía no se compite.
> - **El runbook**, en `INICIAR-LOCAL.md` §2.1 — el paso que faltaba entre
>   «instala» y «enciende»: exportar, importar, **comprobar que los números
>   cuadran**, asignar contraseñas, y la última bajada la mañana del evento
>   antes de la primera llave.
>
> **Tres decisiones que salieron al escribirlo:**
>
> - **La edad se mide desde que la copia SALIÓ de la VPS**, no desde que entró
>   aquí. Una copia exportada el jueves e importada el sábado sigue sin traer
>   lo del viernes, y la pregunta de las siete de la mañana es esa.
> - **Una vista previa no anota nada.** Se revierte entera: anotarla diría que
>   se trajo algo que no se trajo — el mismo error que esta fase arregla.
> - **Un paquete de solo usuarios tampoco.** Es una bajada, pero no trae
>   inscripciones: si pisara la fecha de la copia buena, la pantalla diría
>   «traída hace diez minutos» de algo sin el campeonato dentro. Las dos cosas
>   tienen prueba.
>
> Y una que ya estaba decidida y se respeta: **el aviso calla en cuanto se
> compite**. Es el mismo umbral con el que la importación se frena — a partir
> de ahí volver a bajar no es una opción, así que recordarlo sería ruido en la
> peor mañana del año.

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

> **`eco_sub` ya viaja** (F6-a). Los otros dos llegarán con F2 y F4, y hasta
> entonces cada paquete se exporta con lo que ya se puede meter en vez de con
> nada — ver «F6 se reparte» en la PARTE 4.

---

## F7 · Encender en local: un archivo, y que avise — ✅ hecha

**Dónde:** `dinamyt-combat`, raíz. **Solo Campeonatos** (`B3-RIESGOS.md` §1.4).

> **Hecho.** `INICIAR.bat` + `iniciar_local.py`, `APAGAR.bat` +
> `apagar_local.py`, y `INICIAR-LOCAL.md` §3 reescrita. Los seis puntos, más
> uno que no estaba:
>
> - **`INICIAR.bat --comprobar`**: comprueba y **no arranca nada**. Es lo que
>   se corre la víspera, junto con la bajada de F6-bis, cuando todavía queda
>   tiempo de arreglar lo que falte. No estaba pedido y es la mitad del valor:
>   un arrancador que solo avisa el sábado avisa tarde.
>
> **Lo que se midió al probarlo**, y por qué el punto 3 importaba: en este PC
> el backend contestó a los **9 s** y el frontend a los **26 s**. El manual
> decía «espera unos 15 segundos» — o sea que repartir la dirección a los 15
> era repartirla once segundos antes de que existiera, y esperar por si acaso
> era esperar de más. Ahora no se cuenta: se sondea el puerto y se dice LISTO
> cuando lo está.
>
> **Tres decisiones del camino:**
>
> - **Se arranca con `CREATE_NEW_CONSOLE`, no con `start`.** Con `start` el
>   proceso que se puede vigilar es la shell que lanza y muere al instante, así
>   que el sondeo lo habría leído como «el servicio se murió» en el primer
>   segundo. Las dos ventanas negras siguen ahí a propósito (§6 del manual): si
>   un servicio revienta, el error se queda a la vista.
> - **Se apaga por PUERTO, no por ventana.** Cerrar la ventana mata al `cmd` y
>   puede dejar el servidor vivo escuchando; el síntoma aparece después y
>   disfrazado —el puerto ocupado «por nada» al volver a encender—.
> - **El QR sale del `qrcode` que el frontend ya trae.** Ninguna dependencia
>   nueva, y por tanto nada que instalar el día del evento — que es la única
>   condición que cuenta: ahí no hay internet.
>
> `2-INICIAR.bat` se queda llamando al nuevo, como decía el plan.

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

## F8 · La subida automática de resultados — ✅ hecha

**Dónde:** `dinamyt-combat/backend`. **Depende de F6** (sin `eco_sub` en el
paquete, lo que sube son filas huérfanas).

> **Hecho, el 24 de septiembre de 2026** (`app/cartero.py`, `api/subida.py`,
> `components/SubidaResultados.tsx`). El diseño de abajo —la sesión del propio
> admin, nada guardado en el PC— tal cual, con un cambio en la cola y dos
> arreglos que hacían falta ANTES para que la vuelta sirviera de algo:
>
> - **Cambio · la cola no guarda copias, guarda qué se subió**
>   (`subidas_resultados`: una fila por `export_uuid` con la huella sha256 de
>   lo último que llegó). «Pendiente» es todo campeonato cuyos resultados de
>   HOY no coinciden con los subidos, y lo que sube se construye en el momento
>   con la MISMA función que el USB (`sobre_de_resultados`). Así no hace falta
>   engancharse a los tres sitios donde termina una llave (dos son de los
>   sockets), y una copia encolada no se queda vieja si alguien corrige un
>   podio después.
> - **El pase, solo en memoria.** Lo guarda la entrada con DINAMYT de un ADMIN
>   (`recordar_pase`, solo si hay destino), abre sesión en internet con él
>   (`POST /api/auth/sesion`, leyendo la cookie de entre las DOS `Set-Cookie`)
>   y se olvida al salir. Un hilo de fondo vacía la cola mientras el pase dure
>   (cada minuto; espera creciente 1 → 60 min tras un fallo). Nunca con una
>   llave activa.
> - **Se ve:** la línea en `/admin` con los pendientes, el destino, el último
>   intento, el último error, por qué no sube y [Subir ahora]. Y al arrancar:
>   destino con pase (info), o destino SIN pase (aviso: nadie podrá subir).
> - **Configuración del PC del evento:** `CAMPEONATOS_ONLINE_URL` (la raíz de
>   internet) y `ECOSYSTEM_JWKS_URL` (para poder entrar con DINAMYT cuando
>   vuelva la red). Va en `INICIAR-LOCAL.md`.
>
> **Arreglo 1 · lo que volvía del evento no se veía.** El campeonato sigue
> activo en internet —es el mismo del que salió— y sin combates propios, y en
> `/resultados` ganaba siempre el vivo: «0 resultados», y los que volvieron
> escondidos. Ahora manda el que tiene algo que enseñar, y el enlace por id
> del campeonato lleva a lo publicado.
>
> **Arreglo 2 · cualquier admin con el archivo pisaba lo publicado por otro**
> (y en PostgreSQL era un 500: RLS le escondía el snapshot ajeno y el INSERT
> chocaba). Ahora es un 409 con una frase.
>
> **Arreglo 3 · el QR del juez ya no sale a la red.** `verificar_pase`
> descargaba el JWKS para CUALQUIER token. Con `ECOSYSTEM_JWKS_URL` puesta en
> el PC del evento (que F8 pide) y sin internet, cada juez que entraba por QR
> esperaba el tiempo de espera de esa descarga. Un token que no es RS256 del
> ecosistema se descarta sin preguntar.
>
> **Pruebas:** `tests/test_subida_resultados.py` (13) con DOS instalaciones
> reales en el mismo proceso —el cartero habla con la de internet por su
> cliente de pruebas, no con un simulacro—, `test_vuelta_resultados.py` (5),
> una en `test_identidad_ecosystem.py` y dos contra PostgreSQL.
>
> **Endurecida el 25 de septiembre de 2026**, al revisarla antes del commit.
> Tres agujeros que la primera versión dejaba:
>
> - **Resultados falsos sobre un campeonato ajeno.** El arreglo 1 hace que lo
>   publicado TAPE al campeonato vivo sin combates. Eso convertía el
>   `export_uuid` en una llave: quien lo tuviera —viaja en el paquete que se
>   baja al PC del evento, lo ve cualquiera que toque ese PC— publicaba
>   resultados que se veían como los de otro organizador. Ahora
>   `importar_resultados` mira, con la red levantada, el campeonato vivo de
>   ese `export_uuid`: si existe y no es tuyo (`es_dueno_campeonato`), 409
>   `campeonato_de_otro`. Vale igual para el USB que para el cartero.
> - **El botón y el hilo se cruzaban.** Dos pasadas a la vez creaban dos
>   veces la fila del mismo `export_uuid` (única): el botón devolvía un 500, o
>   el hilo moría en silencio. Ahora hay UNA pasada a la vez (`_vaciando`); la
>   segunda no espera, contesta `subiendo` y la pantalla lo dice.
> - **El pase viajaba en claro si el destino era `http://`.** Lo primero que
>   el cartero envía es el pase de DINAMYT del admin. Un destino que no es
>   `https://` (salvo `localhost`, para ensayar) cuenta como ninguno, y el
>   arranque avisa de que la subida quedó apagada y por qué.
>
> **Límite conocido, a propósito:** el pase del ecosistema dura 30 minutos
> (`B3-RIESGOS.md` §1.3), así que el cartero trabaja durante la media hora
> siguiente a que el admin entre con DINAMYT. Si no terminó, basta con volver
> a entrar. Y una llave que quedó `activa` sin terminar (un combate
> abandonado) frena la subida de TODO: la línea de `/admin` lo dice («hay un
> combate en marcha»), y el USB sigue ahí.
>
> ### La puerta de entrada — ✅ opción A, hecha el 25 sep 2026
>
> **Decidido por el usuario: A.** El portal acepta también
> `http://localhost:3000` y `http://127.0.0.1:3000` como vuelta de
> Campeonatos, y nada más (`VUELTAS_DEL_PC_DEL_EVENTO` en
> `apps/ecosystem-portal/src/lib/apps.ts`). Ni la IP de la LAN, ni otro
> puerto, ni `https://localhost`. Primera prueba del portal:
> `src/lib/apps.test.mts` (`node:test`, sin dependencias; `pnpm test` en el
> paquete, y el CI la corre por turbo), con las trampas de siempre
> (`localhost:3000@malo.example`, `localhost.malo.example`…).
>
> Y en Campeonatos, el botón «Entrar con el portal DINAMYT» **avisa en vez de
> fallar callado** cuando la página se abrió por `http://` desde una dirección
> que no es el propio PC (un celular por la IP de la LAN): el portal no
> volvería, y la persona se quedaría en su panel de DINAMYT sin saber por qué.
>
> **Al desplegar:** el portal se recompila (va en §2.3 de `OPERAR.md`). Nada
> más: el PC del evento no cambia su compilación.
>
> Lo que sigue es cómo estaba el hueco antes de decidir, para que se entienda
> el porqué:
>
> Todo lo de arriba funciona **una vez que el pase llega** al backend del PC
> del evento. Lo que no funciona es que llegue: «Entrar con DINAMYT» manda al
> portal con `?redirect=<origen de este PC>/login`, y el portal solo devuelve
> el `#token=` a los orígenes de `NEXT_PUBLIC_CAMPEONATOS_URL`,
> `…_MEMBRESIAS_URL` y `…_ACADEMY_URL` (`destinoSeguro`,
> `apps/ecosystem-portal/src/lib/apps.ts:66`). El PC del evento
> (`http://localhost:3000`, o su IP de la LAN) no es ninguno: la persona
> entra al portal y se queda en su panel. Las pruebas no lo ven porque
> entregan el pase directamente a `POST /api/auth/sesion`.
>
> **Hay que decidirlo, y es del usuario** (toca la lista blanca del portal en
> producción):
>
> | Opción | Qué es | Coste |
> |---|---|---|
> | **A · Volver a este mismo PC** (recomendada) | El portal acepta también `http://localhost:3000` y `http://127.0.0.1:3000` como vuelta **de Campeonatos**, nada más (el patrón de «loopback» de las apps nativas, RFC 8252 §7.3). El admin sube desde el navegador del PC del evento | Un programa que escuche en ese puerto de ese PC recibiría un pase de 30 min. Si ya hay algo así en el PC, el PC está perdido de todos modos. La IP de la LAN NO entra: esa sí la puede suplantar otro en la red del evento |
> | **B · Dejarlo dormido** | F8 queda escrita y probada, sin puerta. La vuelta sigue siendo el USB | Nada, salvo que la subida automática no existe de cara al usuario |
> | C · Llave de máquina | La descartada arriba | Una llave viva en un portátil que viaja |
>
> Con A: un cambio de pocas líneas en `destinoSeguro` (más su prueba) y
> recompilar el portal (§1.3 de `OPERAR.md`: es `NEXT_PUBLIC_*`, no basta con
> reiniciar).

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

# PARTE 4 · El orden

*(reescrita el 24 de septiembre de 2026, tras D7. La versión del 9 de
septiembre lo metía todo antes del 8 de octubre; ese campeonato no se hace y el
siguiente es el año que viene. Lo que queda abajo de «EL ORDEN DE TRABAJO» es
la historia de cómo se llegó hasta F3, y se conserva.)*

### Lo que manda ahora

- **Sin fecha: cada fase entra cuando está probada**, también contra
  PostgreSQL (ver D7). Mejor una fase bien que tres a medias.
- **El ensayo de `OPERAR.md` §6.0 se corre antes del próximo campeonato**, con
  todo lo que toque login, roles e identidad ya desplegado. Sigue siendo
  obligatorio.
- **Cada fase sigue dejando la aplicación desplegable**, y se despliega en
  cuanto está: nada de acumular tres fases para un despliegue grande.

### EL ORDEN NUEVO (24 de septiembre de 2026)

| # | Qué | Estado |
|---|---|---|
| **0** | **Desplegar lo que ya está hecho y no está en la VPS** (comprobado el 25 sep: sigue igual): el portal va sin F1 (`583abc4`) y Campeonatos sin la parte 3 de F3 (`8dbc599`), ni F4, F5 ni F8. Orden: Campeonatos → ecosystem (shared, migrar 0023, reiniciar; trae `/sync/clubes`) → portal. Los comandos, en el diario (PARTE 6) | ⏳ lo hace el usuario |
| **1** | **Arreglo de RLS en `inscripciones`** — el maestro no podía inscribir en PostgreSQL | ✅ hecho el 24 sep, sin desplegar |
| **2** | **F4 + F6-d** — la organización llega a Campeonatos | ✅ hecho el 24 sep, sin desplegar |
| **3** | **F5 + F6-e** — inscribirse por invitación, y la invitación viaja en el paquete | ✅ hecho el 24 sep, sin desplegar |
| **4** | **F8** — la subida automática de resultados | ✅ hecho el 24 sep, endurecido el 25, y con puerta el 25 (opción A: el portal vuelve a `localhost:3000`). Sin desplegar |
| **5** | **Lo que esperaba «a después del campeonato»**: `/sync/rol` a Campeonatos (`OPERAR.md` §6.1), bloqueo por plan vencido (PARTE 5), retirar `POST /auth/register` de la instalación de internet | pendiente, por decidir cada uno |
| **6** | **Ensayo §6.0** con todo lo anterior dentro | antes del próximo campeonato |
| **7** | **F9** — retirar los andamios | después del próximo campeonato |

### EL ORDEN DE TRABAJO — se empieza por arriba *(versión del 9 de septiembre, histórica)*

*(reordenado el 9 de septiembre de 2026, al implementar F6 y descubrir que en
el puesto 2 no se puede terminar. Ver «F6 se reparte» aquí abajo.)*

| # | Fase | Qué es | Por qué ahí | Bloquea a |
|---|---|---|---|---|
| **1** | **F5-bis** ✅ | La ficha del alumno se reutiliza | **Lo único ROTO.** Un maestro no podía inscribir a su alumna en el segundo campeonato del año | F3, D5 |
| **2** | **F6-a** ✅ | El paquete lleva **`eco_sub`** | Todo lo que baje de la VPS antes de tenerlo llega sin enlace al ecosistema. Es la parte de F6 que **sí tiene columna hoy**, y la que sostiene su puesto | F6-bis, F8 |
| **3** | **F6-bis** ✅ | La copia dice de cuándo es + el runbook | Sin esto, el sábado nadie sabe si la copia trae las inscripciones del jueves | — |
| **4** | **F7** ✅ | Encender en local con comprobaciones | Se nota el 9 a las siete de la mañana. **No toca nada de nadie**: se puede hacer en paralelo desde el primer día | — |
| **5** | **F1** ✅ | El pase lleva varios roles (ecosystem) | Empieza el bloque de identidad. **Todo esto, dentro antes del ensayo del ~26 de septiembre** | F2 |
| **6** | **F2** + **F6-b** ✅ | Campeonatos entiende varios roles — **y el paquete lleva `roles`** | De cara al usuario **no cambia nada**: es el andamio de F3. La columna nace aquí, así que el paquete la lleva aquí | F3 |
| **7** | **F3** + **F6-c** ✅ | El panel del alumno + el atleta independiente — **y el paquete lleva la identidad del competidor** | Lo que multiplica por cien quién entra. Necesita ficha estable (1) y roles (6) | — |
| **8** | **F4** + **F6-d** | La organización llega a Campeonatos — **y el paquete lleva `org_id`** | El admin único por organización. `org_id` no existe hoy en ninguna tabla (§1.3): nace aquí | F5 |
| **9** | **F5** | Inscribirse por invitación | El admin invita clubes al campeonato | — |
| **10** | **F8** | La subida automática de resultados | Ocurre **después** del evento, con red. Lo último que hace falta | — |
| — | ~~F9~~ | Retirar los andamios | **Después del 11.** Su definición es «cuando lleve un campeonato real encima» | — |

### F6 se reparte, y por eso el orden cambió

F6 pedía cuatro datos en el paquete. Al ir a escribirlos apareció que **tres no
tienen dónde vivir todavía**, y que las columnas las crean fases que van
DESPUÉS en esta misma lista:

| Trozo | Dato | Necesita |
|---|---|---|
| **F6-a** ✅ | `usuarios.eco_sub` | nada: la columna ya existe |
| **F6-b** ✅ | `usuarios.roles` | **F2** (nº 6) |
| **F6-c** ✅ | `competidores.eco_sub` | **F3** (nº 7) |
| **F6-d** | `org_id` | **F4** (nº 8) — hoy no existe en ninguna tabla |

Había dos salidas y una es peor: **bajar F6 entera al puesto 8**, detrás de F4.
Eso dejaría todo lo que se baje de la VPS hasta entonces sin `eco_sub`, que es
exactamente lo que F6 estaba en el puesto 2 para evitar. Así que **F6 deja de
ser un paso y pasa a ser una línea de cada fase**: la que crea la columna se
lleva su trozo del paquete, en el mismo commit. Nadie espera a nadie, y ningún
paquete se exporta sin lo que ya se podía meter.

> **Y una consecuencia que hay que decir en voz alta:** el paquete cambia de
> forma cuatro veces, no una. Por eso `VERSION_PAQUETE` sube en cada trozo y
> por eso el importador **acepta siempre las versiones anteriores** — un
> paquete exportado hoy tiene que poder importarse el 9 de octubre, aunque
> para entonces el formato vaya por la 5.

### Los tres carriles, para no trabajar en serie lo que no lo es

```
                          [ok]      [ok]       [ok]
CARRIL A (el evento)     1·F5-bis ──► 2·F6-a ──► 3·F6-bis
                                                      │
                                  [ok]                │
CARRIL B (independiente)          4·F7 ───────────────┤
                         [ok]    [ok]    [ok]         │
CARRIL C (identidad)     5·F1 ─► 6·F2 ─► 7·F3         │
                                  +F6-b  +F6-c        │
                                    └─► 8·F4 ─► 9·F5  │
                                        +F6-d         │
                                                      │
                                             10·F8 ◄──┘
```

**A y B no se estorban.** F7 no toca base de datos ni permisos, así que puede
avanzar en paralelo con cualquier cosa. El carril C es el único que toca login e
identidad, y por eso entero **antes del ensayo del ~26 de septiembre**.

**El carril A ya está cerrado.** Lo que quedaba de F6 no vive en A: viaja
colgado de C, una línea por fase.

### Las cuatro reglas del orden, y por qué

**F5-bis va primera y no es discutible.** Es la única fase que **repara**; todas
las demás añaden. Y es la que más se nota el día del evento: cuarenta
inscripciones que hoy son cuarenta formularios en blanco.

**F6-a va antes que cualquier bajada de la VPS.** Cada paquete que se importe
sin `eco_sub` deja cuentas sin enlazar, y eso se arrastra hasta la subida de
vuelta.

**Lo que no tiene columna no se espera: se reparte.** Es la regla que salió de
implementar F6, y vale para cualquier fase futura que pida un dato que todavía
no existe. Se hace la parte que ya cabe, y el resto viaja con la fase que crea
su sitio — en vez de mover la fase entera al final, que era la otra salida y la
mala.

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

---

# PARTE 6 · Diario de sesiones — dónde quedamos

*Una entrada por sesión, la más reciente arriba. Es lo primero que lee la
siguiente: qué se hizo, qué quedó a medias, qué falta desplegar y qué sigue.*

## Sesión del 25 de septiembre de 2026

**Contexto:** la sesión del 24 se cortó por el límite de uso con F8 escrita y
en verde pero **sin commit**, y con F4 y F5 con commit pero **sin empujar**
(ni en `dinamyt-combat` ni el `/sync/clubes` del monorepo). Esta sesión la
cierra.

### Qué se hizo

1. **F8 revisada antes del commit, y tres agujeros cerrados** (detalle en la
   nota «Endurecida» dentro de F8): resultados falsos sobre un campeonato
   ajeno vía `export_uuid` (409 `campeonato_de_otro`), el botón y el hilo del
   cartero cruzándose (una pasada a la vez), y el pase viajando en claro a un
   destino `http://` (solo `https://` o `localhost`). +6 pruebas.
2. **El hueco que las pruebas no veían: F8 no tiene puerta** (nota ⚠️ dentro
   de F8). El portal no devuelve el pase al PC del evento. Documentado aquí y
   en `INICIAR-LOCAL.md` §7.2; **decisión A/B pendiente del usuario**.
3. **Commits:** `e67acbf` (F8) en `dinamyt-combat`; empujados con él
   `248df50` (RLS de inscripciones), `d7f145a` (F4) y `7d5bf4f` (F5). En el
   monorepo, `0c30eeb` (`/sync/clubes`) y el espejo de `productos/campeonatos`.
4. **La VPS, comprobada por SSH:** igual que el 24. Campeonatos en `8dbc599`,
   portal en `583abc4`, Membresías en `3488b31`; los seis servicios activos.

### Baterías al cerrar

- Campeonatos, SQLite: **444 en verde** (12 saltadas: son las de PostgreSQL).
- Campeonatos contra PostgreSQL 18 con `FORCE ROW LEVEL SECURITY` y un rol
  sin superusuario: **13/13**.
- Frontend de Campeonatos: `tsc` y `eslint` limpios.
- Ecosystem (el 24, con `/sync/clubes`): 362/362 y `tsc` limpio.

### Hallazgos que siguen en pie

- **F8 sin puerta** (arriba). Mientras no se decida, la vuelta es el USB.
- **`/srv/campeonatos/backend/.env.bak-2026-08-30`**: una copia del `.env`
  —con sus secretos— dentro de la carpeta del repositorio en la VPS. No la
  sirve nada (el backend no expone archivos de su carpeta), pero **git no la
  ignora** —por eso sale como `??` en `git status`—: un `git add -A` en el
  servidor la subiría a GitHub con los secretos. Desde esta sesión el
  `.gitignore` ignora `*.env.bak*` (tras el `git pull` deja de salir), pero el
  archivo sigue ahí: moverlo fuera del repo o borrarlo. Lo hace el usuario.
- **Una llave abandonada en `activa` frena toda la subida** (F8). Se ve en
  `/admin`; no se arregla solo.
- Lo que F5 dejó fuera a propósito: avisar al maestro de que lo invitaron, y
  el interruptor «solo clubes invitados» que cierre la puerta vieja.

### Cómo desplegar lo pendiente (`OPERAR.md` §1.2, §2.3, §2.4-bis)

Orden: **respaldo → Campeonatos → ecosystem (shared, migrar 0023) → portal**.
Campeonatos no migra (`schema_compat` crea al arrancar las columnas de F4,
la tabla de F5, la de F8 y el índice nuevo del documento), pero ese arranque
hace `ALTER TABLE`: si se cuelga es §5.1-ter (`NRestarts`, `pg_stat_activity`).

```bash
sudo -v && sudo -u postgres pg_dump -Fc dinamyt > ~/respaldo-$(date +%F).dump && sudo mv ~/respaldo-$(date +%F).dump /var/backups/ && sudo ls -lh /var/backups/
```

```bash
cd /srv/campeonatos && git fetch && git log --oneline -1 origin/main && git status --short
```

```bash
cd /srv/campeonatos && git pull && backend/venv/bin/pip install -r backend/requirements.txt && cd frontend && npm ci && npm run build && sudo systemctl restart campeonatos-api campeonatos-web && systemctl is-active campeonatos-api campeonatos-web
```

```bash
cd /srv/dinamyt && git fetch && git log --oneline -1 origin/main && git status --short
```

```bash
cd /srv/dinamyt && git pull && pnpm install --frozen-lockfile && pnpm --filter @dinamyt/shared build && pnpm --filter @dinamyt/ecosystem-api build && pnpm --filter @dinamyt/ecosystem-portal build
```

```bash
cd /srv/dinamyt/apps/ecosystem-api && pnpm db:migrar
```

```bash
sudo systemctl restart dinamyt-id dinamyt-portal && sudo systemctl status dinamyt-id --no-pager
```

Comprobaciones que no mienten: las rutas nuevas dan **401, no 404**
(`curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5000/api/subida/estado`
y `…/api/mi/panel`); a los cinco minutos, `systemctl show campeonatos-api -p
NRestarts` sigue igual; y `curl -s -o /dev/null -w "%{http_code}
"
http://127.0.0.1:3001/sync/clubes` da **401** (un 404 querría decir que falta
`ECOSYSTEM_SYNC_SECRET`: entonces el buscador de clubes no funciona).

### Qué sigue, en orden

1. **Desplegar** (arriba). Es lo único que hace visible el carril C.
2. **Decidir la puerta de F8** (A o B). Si es A, es una tarde: el cambio en
   `destinoSeguro`, su prueba y recompilar el portal.
3. **Las tres decisiones del nº 5 de la PARTE 4**: `/sync/rol` a Campeonatos,
   el bloqueo por plan vencido y retirar `POST /auth/register` de internet.
4. **El ensayo de `OPERAR.md` §6.0** con todo desplegado.
5. **F9**, solo después de un campeonato real.

## Sesión del 24 de septiembre de 2026

**Contexto que cambió:** no hay campeonato en octubre (D7). Se revisó lo hecho
antes de seguir, y se trabajó con una base PostgreSQL de verdad al lado.

### Estado de la VPS al empezar (comprobado por SSH)

| App | Commit en la VPS | Lo que le falta |
|---|---|---|
| Campeonatos (`/srv/campeonatos`) | `8dbc599` | la parte 3 de F3 (`d26d300`) y todo lo de hoy |
| Portal + ecosystem (`/srv/dinamyt`) | `583abc4` | **F1** (`58b3e08`, migración 0023) y el botón de F3 (`696e1dd`) |
| Membresías | `3488b31` | nada |

Consecuencia: **F2 corre en producción sin F1** — no pasa nada, porque sin
`roles_campeonatos` en el pase Campeonatos lee `role_campeonatos`, que es para
lo que F2 se escribió así. Pero nada del carril C se ve todavía de cara al
usuario.

### 1 · El fallo que la batería no podía ver: RLS en `inscripciones` — ✅ arreglado

`tests/test_rls_postgres.py` (nuevo) corre contra un PostgreSQL con
`FORCE ROW LEVEL SECURITY` y un rol normal, como producción. La primera prueba
—el maestro inscribe a una alumna y el admin la ve— **falló al insertar**:

    new row violates row-level security policy for table "inscripciones"

La solicitud del maestro se guarda con `created_by = maestro.id` (es quien la
envía), y la política pedía `created_by = workspace` (el id del admin). En
producción eso es un **500 en cada inscripción de un maestro**, y aunque
hubiera entrado, el admin no la habría visto. En SQLite no hay RLS: 374 pruebas
en verde y el flujo roto.

**Arreglo** (`app/rls.py`): la política de `inscripciones` mira el workspace de
SU CAMPEONATO, no quién la envió. Se aplica sola al reiniciar (`ensure_rls`
reescribe las políticas). Sirve también al importador, que ya guardaba las
solicitudes con el maestro como autor.

**Cómo correr la prueba contra PostgreSQL:** ver la cabecera de
`tests/test_rls_postgres.py`. Sin `CAMPEONATOS_PG_URL` se salta sola.
