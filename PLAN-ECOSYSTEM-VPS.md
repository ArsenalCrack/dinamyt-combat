# Plan maestro — Un DINAMYT: cuenta única, un repo, un servidor

> **Reemplaza a `PLANVPS.md` / `PLAN-VPS.md`** (dos copias idénticas byte a byte
> del mismo archivo) y a `PLAN-INTEGRACION-ECOSYSTEM.md`.
>
> Escrito 2026-08-19 · Actualizado 2026-08-19 con las respuestas del dueño.

---

## Cómo se lleva este plan

Cada paso lleva su marca. **Al terminar un paso, se cambia la marca aquí mismo**
— este archivo es el tablero, no hay otro.

| Marca | Significa |
|---|---|
| `[ ]` | Pendiente |
| `[~]` | En curso |
| `[x]` | **Hecho** — añadir la fecha entre paréntesis |
| `[-]` | Descartado o ya no aplica — añadir el motivo |

### Tablero de avance

| Bloque | Qué | Fecha tope | Estado |
|---|---|---|---|
| **B0** | Seguros: respaldos y commits | 21 ago | `[~]` commits hechos (19 ago); faltan los volcados — **hace falta la contraseña real de las dos bases** |
| **B1** | **Servicio de vuelta** — VPS + datos + apps tal cual | **29 ago** | `[~]` arreglos previos hechos (19 ago) |
| **B2** | Correo | 5 sep | `[ ]` |
| **B2b** | Actualizar el monorepo `dinamyt` | 5 sep | `[ ]` |
| **B3** | **Identidad única** | **19 sep** | `[ ]` |
| **B3s** | Reposo y observación | 20–30 sep | `[ ]` |
| **🔒** | **CONGELADO — campeonato del 9, 10 y 11 de octubre** | 1–13 oct | — |
| **B4** | Fase 2: portada, planes, multi-arte, plan gratuito, academy | desde 14 oct | `[ ]` |

---

## 0. Las decisiones que gobiernan todo lo demás

| # | Decisión | Consecuencia principal |
|---|---|---|
| 1 | **Ecosystem = único emisor de identidad.** Campeonatos y Membresías dejan de emitir tokens; solo validan el RS256 contra su JWKS. | Una cuenta, un login, una recuperación de contraseña. Casi todo el trabajo cae en Campeonatos. |
| 2 | **Una base `dinamyt` en el VPS, cuatro esquemas.** | Los datos buenos vienen de **tres proyectos de Supabase distintos** (§1.3). |
| 3 | **El monorepo `dinamyt` se pone al día, y los dos repos originales se quedan donde están y siguen mandando.** | Nada se pierde y nada se mueve. La regla de oro está en §6. |
| 4 | **Las cuentas nacen en el ecosystem**, nunca en las apps. El maestro no crea cuentas: crea *fichas* e *invita*. | §2. |
| 5 | **El club también vive en el ecosystem.** `ecosystem.organizations` es el registro único; cada app guarda un espejo. | Es lo que hace que un club aparezca en Campeonatos con sus alumnos ya asociados. §2.5. |
| 6 | **El campeonato del 9–11 de octubre manda sobre el calendario.** Congelación del 1 al 13 de octubre. | §8. |

### 0.1 Aviso de seguridad · las cadenas de conexión

Las tres cadenas de conexión con contraseña **no van en este archivo ni en
ningún archivo del repo**. Van en un `.env.migracion` fuera del repositorio,
usado solo durante el traslado y borrado después.

`[ ]` Rotar las contraseñas de los tres proyectos de Supabase **después** de que
la migración esté verificada — han viajado por chat, y una contraseña que viajó
se cambia.

`[ ]` Añadir `.env.migracion` a `.gitignore` antes de crearlo.

> **Corrección respecto a la primera versión de este plan.** Ahí decía que
> `private.pem` estaba commiteado. **No lo está**: `.gitignore:22` lo cubre con
> `*.pem` y `git log --all` no lo encuentra en ninguna parte del historial. El
> riesgo real es el contrario y está en §11.

---

## 1. Qué hay hoy, de verdad

### 1.1 Los tres repositorios

| Repo | Remote | Qué es | Estado |
|---|---|---|---|
| `D:\Repositorios\dinamyt` | `ArsenalCrack/dinamyt` | Monorepo «ecosystem»: `ecosystem-api` (NestJS), `ecosystem-portal` (Next), `academy-*`, + copias **viejas** de campeonatos y membresías | Rama `integracion-campeonatos-local`, 30 archivos sin commitear, **no compila** (§1.4) |
| `D:\hapkido\DINAMYT-LOCAL - copia` | `ArsenalCrack/dinamyt-combat` | Campeonatos de verdad: Flask + Next + Socket.IO | Rama `main`, 2 archivos modificados sin commitear |
| `D:\Repositorios\dinamyt-membresias` | `ArsenalCrack/dinamyt-membresias` | Membresías de verdad: Fastify + Next PWA + Drizzle | Rama limpia |

**La distancia entre las copias viejas y las buenas es enorme:**

- **Membresías:** el monorepo se quedó en la **migración 0001**; el repo bueno va
  por la **0014**. Entre medias entró la identidad propia, RLS por club, carnet
  con fecha, modo mantenimiento, clases del club, fecha de nacimiento… Además el
  monorepo todavía tiene `apps/membresias-agent` (lector de huella), **retirado
  del producto**.
- **Campeonatos:** la copia del monorepo es un Fastify **sin combate en vivo por
  Socket.IO, sin llaves, sin tatamis, sin puntuación y sin reportes PDF/Excel**.
  Hay además `apps/campeonatos-api-local/` y `apps/campeonatos-web-local/`: una
  copia antigua del repo bueno **sin commitear jamás** (`git status` las da `??`).

> **Esto es exactamente lo que pediste proteger.** El frontend de Campeonatos,
> el motor de puntuación (`app/engine/combate_engine.py`, 782 líneas), el
> namespace de Socket.IO (1.685 líneas) y las funciones de Membresías **no
> existen** en el monorepo. La dirección del trasvase es siempre la misma:
> **de los repos buenos hacia `dinamyt`, nunca al revés.**

### 1.2 La identidad, hoy

| App | Emite token | Verifica | Login |
|---|---|---|---|
| `ecosystem-api` | **Sí**, RS256, publica `GET /auth/jwks` | Propio | Portal. Registro, OTP de verificación, `forgot-password` y `reset-password` **ya implementados** |
| `membresias-api` | Sí, HS256 propio | Híbrido: el suyo y, si hay `ECOSYSTEM_JWKS_URL`, el del ecosystem | Propio + botón SSO (`#token=`). **Ya funciona** |
| Campeonatos (Flask) | Sí, HS256 | Solo el suyo | Propio. **Sin ninguna noción del ecosystem** |

El contrato del token vive en `packages/shared/src/auth.ts` y ya trae
`role_campeonatos`, `role_membresias`, `role_academy`, `app_scopes`, `org_id` e
`is_super_admin`. **No hay que inventar nada.**

### 1.3 Las bases de datos — son TRES proyectos de Supabase, no uno

```
Proyecto yabnklhtfknwvpgadacp · us-west-2 · pooler 6543
   ├── esquema ecosystem     → LAS CUENTAS.        Se conserva.
   ├── esquema academy       → Academy.            Se conserva (academy entra).
   ├── esquema membresias    → VIEJO (migr. 0001). Se DESCARTA.
   └── esquema campeonatos   → VIEJO (el Fastify). Se DESCARTA.

Proyecto lhgisckrvyfqjslbzpuj · us-west-2 · pooler 6543
   └── esquema membresias    → migración 0014, DATOS REALES.   ES LA BUENA.
       (+ esquema drizzle, el diario de migraciones)

Proyecto zcenyqtgaqqsmhjccwck · us-east-2 · puerto 5432
   └── esquema public        → el esquema de Flask, DATOS REALES. ES LA BUENA.
```

> **Corrección respecto a la primera versión.** El README de Campeonatos dice
> Neon; la realidad es Supabase (`zcenyqtgaqqsmhjccwck`). Hay que actualizar ese
> README. `[ ]`

**Que sean tres proyectos separados es buena noticia:** no hay colisión de
nombres de esquema entre el bueno y el viejo, cada volcado es independiente, y
el proyecto `yabnkl…` solo aporta `ecosystem` y `academy`.

### 1.4 Estado de producción · **está caída**

Render está **suspendido por agotar el plan gratuito**. Las dos APIs no
responden, y con ellas las dos webs de Vercel, que dependen de ellas.

Tres consecuencias que cambian el plan:

1. **Ya no hay «no romper producción», porque producción está rota.** El bloque
   B1 deja de ser una mudanza y pasa a ser **una reparación**: el VPS es lo que
   devuelve el servicio.
2. **No hay marcha atrás a la que volver.** Render apagado no es un respaldo. El
   respaldo son los volcados de las tres bases (B0), y por eso B0 va primero y
   solo.
3. **Los datos están intactos.** Supabase sigue vivo; lo que se suspendió es el
   cómputo, no la base. Nada se ha perdido.

### 1.5 Cosas rotas que hay que arreglar sí o sí

`[x]` **1 · `ecosystem-api` no compila.** *(19 ago —
`fix/arreglos-previos-vps` en `dinamyt`)* `auth.controller.ts:44` lanzaba
`BadRequestException` sin importarlo y `nest build` moría con TS2304. Añadido al
import; `tsc --noEmit` sale limpio.

`[x]` **2 · El diario de migraciones de Drizzle va a chocar.** *(19 ago —
`fix/diario-migraciones-por-esquema` en `dinamyt-membresias` y
`fix/arreglos-previos-vps` en `dinamyt`)* Ni `ecosystem-api` ni `membresias-db`
fijaban `migrationsSchema`, así que los dos usaban
`drizzle.__drizzle_migrations`. Ahora cada uno lleva el suyo dentro de su
esquema.

> **Cambiar `migrationsSchema` a secas habría sido peor que el problema:** una
> base que YA funciona no encontraría su diario, daría las 15 migraciones por
> pendientes y moriría en la primera tabla existente. Por eso Membresías trae
> `mudarDiarioSiHaceFalta()` en `migrate.ts`, que traslada el diario del sitio
> viejo al nuevo antes de migrar — idempotente y no-op en base nueva.
> **Comprobado sobre una copia del `.localdb` real:** 15 filas pasaron de
> `drizzle` a `membresias`, los datos intactos, segunda pasada sin efecto.

`[ ]` **3 · Campeonatos tiene 8 claves foráneas contra `usuarios.id`** (Integer),
no 3 como decía el plan viejo: `ajuste.py:28`, `asignacion.py:21,32,79`,
`campeonato.py:50`, `competidor.py:119,217`, `llave.py:54`,
`resultado_publicado.py:37`. El RLS por workspace también es entero. Por eso el
diseño de §4.2 usa un espejo y no una migración a UUID.

`[x]` **4 · `admin@dinamyt.com`** *(19 ago)* — eran **ocho** apariciones, no dos:
`config.py`, `seeds/seed_admin.py`, `app/__init__.py`, `fix_superadmins.py`,
`reset_admin.py` y el `README` en Campeonatos; `planes/page.tsx` y
**`privacidad/page.tsx`** en el portal. La última es la que más urgía: la
política de privacidad daba como dirección de contacto un dominio ajeno.

`[x]` **5 · `PLANVPS.md` y `PLAN-VPS.md` eran el mismo archivo.** *(19 ago)*
`PLAN-VPS.md` eliminado tras comprobar con `diff` que eran idénticos byte a
byte. `PLANVPS.md` y `PLAN-INTEGRACION-ECOSYSTEM.md` quedan con una nota de
«superado por este plan» y el motivo.

`[x]` **6 · El README decía que la base está en Neon.** *(19 ago)* Está en
Supabase. Corregido, incluido el apartado de RLS: el rol dueño de las tablas no
es el `owner` de Neon sino `postgres`.

---

## 2. La cuenta no es la ficha

**El maestro no debe crear la cuenta, y el motivo es estructural.** Hoy
Membresías mezcla dos cosas distintas:

| | **Cuenta** | **Ficha** |
|---|---|---|
| Qué es | La identidad de la persona | Lo que esa persona es dentro de un producto |
| Qué guarda | Correo, contraseña, documento, nombre, foto, nacimiento | Cinturón, plan, pagos, asistencias, carnet · categoría, inscripciones, resultados |
| Dónde vive | `ecosystem.users` | `membresias.users` · `campeonatos.competidores` |
| Cuántas hay | **Una por persona, para siempre** | Una por producto |
| Quién manda | La persona | El club |

Si el maestro crea la cuenta, la contraseña de alguien la elige otro **y la
misma persona acaba con una cuenta por club**. Pero si exiges cuenta para tener
ficha, rompes la inscripción presencial de dos minutos.

### 2.1 Los tres caminos de alta — y por qué C solo no basta

**Preguntaste si el camino C es el mejor. Lo es para lo que sirve, pero no cubre
los otros dos casos**, y los tres tienen que existir:

| Camino | Para quién | Cuándo se usa |
|---|---|---|
| **A · Auto-registro** en el portal | Adultos, maestros, competidores, padres | El caso normal a partir de ahora. **Ya implementado** |
| **B · Invitación del maestro** | El alumno que se inscribe presencialmente y todavía no tiene cuenta | Alta del día a día en el club |
| **C · Código del club** | Quien **ya tiene** cuenta DINAMYT | Competidores, traslados, y todo el que se registró solo |

C es el más limpio **porque no crea nada**: solo une una cuenta que ya existe
con un club que ya existe. Por eso es el camino preferente. Pero:

- Un alumno nuevo sin cuenta necesita **B** (o registrarse él por **A** antes).
- Los usuarios que **ya existen hoy** no pasan por ninguno de los tres: van por
  una **reconciliación de una sola vez** (§2.4), que es distinta y automática.

**Camino B, en detalle.** El maestro crea la ficha como hoy y pulsa «invitar».
El ecosystem crea la cuenta sin contraseña y manda un enlace firmado. Al ponerla,
**cuenta creada y correo verificado en el mismo acto** — el enlace ya probó que
la dirección existe. Sin correo, la ficha vive sin cuenta y la persona entra con
**carnet QR o PIN**, que ya funcionan.

**Camino C, en detalle.** El club tiene un código rotable. Quien lo escribe queda
*solicitando entrar*; el maestro aprueba desde su panel y ahí se crea la ficha,
enlazada a la cuenta que la persona ya tenía.

### 2.2 Los niños — con una advertencia que hay que ver ahora

Dijiste que la cuenta del niño la puede crear el padre con su correo. **Funciona
para un hijo. Para el segundo, no**, y el motivo es una restricción que ya está
en la base:

```
ecosystem.users.email       varchar(200) NOT NULL UNIQUE
ecosystem.users.document_id varchar(30)  NOT NULL UNIQUE
```

Un correo = una cuenta. Un padre con dos hijos no puede crear dos cuentas con su
correo, y el `document_id` obligatorio tampoco sería el suyo.

**La salida ya está construida en el esquema:** `ecosystem.user_guardians` existe
(minor_user_id, guardian_user_id, relationship, consent_at) y Membresías ya tiene
el rol `guardian`.

| Situación | Cómo se resuelve |
|---|---|
| Padre con 1 o varios hijos | **El padre tiene UNA cuenta.** Cada hijo es una **ficha sin cuenta** en Membresías, enlazada al padre por `user_guardians` + `memberships.payer_user_id`. El padre ve el estado de todos y paga por todos. El hijo entra al tatami con su carnet QR |
| El hijo crece y quiere su cuenta | Se registra con **su propio correo** (camino A) y se enlaza a la ficha que ya tenía. No se pierde ni un pago ni una asistencia |
| Adolescente con correo propio desde el principio | Camino A o B, normal, con el padre como acudiente |

`[ ]` Añadir a Membresías la pantalla «acudiente y sus menores» y el enlace a
`user_guardians`.

### 2.3 Recuperación de contraseña

Una sola, en el ecosystem (`/auth/forgot-password` + `/auth/reset-password`, ya
implementadas). Las apps no tienen contraseñas después de esto: su enlace
«olvidé mi contraseña» lleva al portal.

### 2.4 Qué pasa con el club y los usuarios que YA existen

Es una **reconciliación de una sola vez**, con guion escrito y ensayado sobre
una copia antes de tocar nada.

**Paso 1 · El club.**

`[ ]` Por cada fila de `membresias.orgs`, buscar o crear la organización
equivalente en `ecosystem.organizations` (`type = 'club'`), y guardar el UUID
resultante en una columna nueva `membresias.orgs.eco_org_id`.

> **El `id` de `membresias.orgs` NO se toca.** Lo referencian 8 tablas y todas
> las políticas de RLS. El espejo es una columna nueva, no un cambio de clave.

`[ ]` Lo mismo con los clubes que Campeonatos conoce: hoy viven como texto libre
dentro de `campeonatos.usuarios.clubes` (JSON con `nombre`, `ciudad`, `pais`).
Se cruzan por nombre normalizado contra las organizaciones del ecosystem; lo que
no case, se crea y **se le enseña la lista al maestro para que confirme**.

**Paso 2 · Las personas.**

`[ ]` Sacar los tres censos: `ecosystem.users`, `membresias.users`,
`campeonatos.usuarios`. Cruzar **por correo**, en minúsculas y sin espacios.

| Montón | Qué se hace |
|---|---|
| Ya está en el ecosystem | Se enlaza: `eco_sub` en Campeonatos y en Membresías. Nada más |
| No está, con correo válido | Se crea la cuenta **sin contraseña** y se manda el correo de «pon tu contraseña». **La contraseña vieja no se migra** — los hashes son de esquemas y costos distintos, y migrar contraseñas ajenas a un sistema nuevo es lo que no se debe hacer |
| Sin correo utilizable | Se queda **sin cuenta**, como ficha pura. Entra por carnet QR/PIN. Se le da la lista al maestro |

**Paso 3 · La pertenencia.**

`[ ]` Por cada persona con cuenta, crear su fila en `ecosystem.org_members`
(`org_id`, `user_id`, `role`) con el rol que ya tenía. Eso es lo que hace que el
token traiga `org_id` y `role_membresias`/`role_campeonatos` correctos desde el
primer login.

### 2.5 Por qué el club tiene que estar en el ecosystem

Preguntaste si el club debería crearse en el ecosystem para que aparezca después
en Campeonatos con sus alumnos ya asociados. **Sí, y es justo el motivo.**

```
                  ecosystem.organizations   ← el club, UNA vez
                            │
              ┌─────────────┴─────────────┐
   membresias.orgs                  campeonatos (por org_id del token)
   .eco_org_id ──┘                          └── inscripciones prellenadas
   (espejo, id propio intacto)                   con el roster del club
```

Con esto:

- El maestro registra su club **una vez**, en el portal.
- En Membresías gestiona alumnos, pagos y asistencias.
- En Campeonatos, al inscribir, **ve a sus alumnos** — el token trae `org_id` y
  Campeonatos pide el roster al ecosystem. Es el bloque B11 («autorrellenado»)
  del plan de integración viejo, y ahora tiene sentido porque hay un club único
  al que preguntar.
- El superadmin activa o suspende un club **en un sitio** y el corte alcanza a
  las tres apps.

### 2.6 Lo que NO se pierde por el camino

Las dos apps guardan la sesión en **cookie httpOnly**, a propósito: un XSS no
puede llevarse la sesión. El portal guarda el token en `localStorage` y lo
entrega por el fragmento de la URL.

**Ese patrón no se propaga.** `#token=` se usa solo para el salto; al aterrizar,
cada app lo **canjea de inmediato por su propia cookie httpOnly** y descarta el
token del ecosystem. Campeonatos ya tiene la ruta (`POST /auth/sesion`) y
Membresías ya hace el canje.

---

## 3. La base de datos

### 3.1 Cómo queda

Un **PostgreSQL 17** en el VPS (no el 16 del repositorio de Ubuntu: hay que
añadir el de PGDG), base `dinamyt`, cuatro esquemas, **un rol por app** —
ninguno superusuario:

| Esquema | Rol dueño | Quién se conecta | `search_path` |
|---|---|---|---|
| `ecosystem` | `dinamyt_eco` | `ecosystem-api` | `ecosystem, public` |
| `membresias` | `dinamyt_memb` | `membresias-api` | `membresias, public` |
| `campeonatos` | `dinamyt_camp` | Flask | `campeonatos, public` |
| `academy` | `dinamyt_acad` | `academy-api` | `academy, public` |

```bash
sudo -u postgres createdb dinamyt
sudo -u postgres psql -d dinamyt <<'SQL'
CREATE ROLE dinamyt_eco  LOGIN PASSWORD 'xxx';
CREATE ROLE dinamyt_memb LOGIN PASSWORD 'xxx';
CREATE ROLE dinamyt_camp LOGIN PASSWORD 'xxx';
CREATE ROLE dinamyt_acad LOGIN PASSWORD 'xxx';

CREATE SCHEMA ecosystem   AUTHORIZATION dinamyt_eco;
CREATE SCHEMA membresias  AUTHORIZATION dinamyt_memb;
CREATE SCHEMA campeonatos AUTHORIZATION dinamyt_camp;
CREATE SCHEMA academy     AUTHORIZATION dinamyt_acad;

ALTER ROLE dinamyt_eco  SET search_path = ecosystem, public;
ALTER ROLE dinamyt_memb SET search_path = membresias, public;
ALTER ROLE dinamyt_camp SET search_path = campeonatos, public;
ALTER ROLE dinamyt_acad SET search_path = academy, public;

REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO dinamyt_eco, dinamyt_memb, dinamyt_camp, dinamyt_acad;
SQL
```

> **Ninguno de los cuatro roles lleva `SUPERUSER` ni `BYPASSRLS`.** No es
> higiene: es requisito. El RLS `FORCE` de Membresías y de Campeonatos se lo
> salta cualquier rol con esos atributos y el aislamiento se apaga en silencio.
> Comprobar: `SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname LIKE 'dinamyt_%';`
> — las cuatro filas tienen que dar `f, f`.

### 3.2 De dónde sale cada esquema

| Destino | Origen correcto | Origen que hay que NO usar |
|---|---|---|
| `ecosystem` | `yabnklhtfknwvpgadacp`, esquema `ecosystem` | — |
| `academy` | `yabnklhtfknwvpgadacp`, esquema `academy` | — |
| `membresias` | **`lhgisckrvyfqjslbzpuj`**, esquemas `membresias` + `drizzle` | ~~`membresias` de `yabnkl…`~~ (migr. 0001) |
| `campeonatos` | **`zcenyqtgaqqsmhjccwck`**, esquema `public` | ~~`campeonatos` de `yabnkl…`~~ (el Fastify muerto) |

### 3.3 El traslado, paso a paso

> **La versión de PostgreSQL no es un detalle.** El formato `custom` de
> `pg_dump` lo lee `pg_restore` de su versión **o posterior, nunca anterior**:
> un volcado hecho con la 18 no se restaura en la 17. Como en el VPS va a correr
> la **17**, los volcados se hacen con `pg_dump` **17**. En este equipo están la
> 17 y la 18, y la 18 es la que sale por defecto — de ahí que
> `scripts/respaldar-produccion.ps1` fije la versión en vez de coger la más nueva.

> **Y el puerto tampoco.** El `6543` de Supabase es el *transaction pooler*:
> reparte cada sentencia por una conexión distinta del pool. `pg_dump` necesita
> lo contrario —una sesión estable, con su transacción y sus cursores abiertos de
> principio a fin— y contra el 6543 falla o, peor, saca un volcado incompleto sin
> decir nada. **Los tres volcados van por el `5432`** (session pooler) o por la
> conexión directa. La cadena de Membresías que hay a mano trae el 6543: hay que
> cambiarlo.

**El volcado de B0 está automatizado**: `scripts/respaldar-produccion.ps1`, en el
repo `dinamyt`. Lee las cadenas de un `.env.migracion` que vive **fuera de todo
repositorio**, no las imprime nunca, saca los tres volcados con los esquemas
correctos de §3.2, avisa si detecta el puerto 6543 y comprueba cada archivo con
`pg_restore --list` — un volcado truncado se ve en el momento y no dentro de tres
semanas.

```powershell
.\scripts\respaldar-produccion.ps1 -Env D:\dinamyt-migracion\.env.migracion -Destino D:\dinamyt-migracion\respaldos
```

`[ ]` **a · Ecosystem y Academy** — van **juntos y en este orden**, porque
comparten diario (ver el recuadro de abajo):

```bash
# Un solo volcado con los tres esquemas: los dos de datos y el diario.
pg_dump "$ECO_URL" --no-owner --no-privileges \
        -n ecosystem -n academy -n drizzle -Fc -f eco_acad.dump

pg_restore -d "postgresql://dinamyt_eco@localhost/dinamyt" --no-owner eco_acad.dump

# Repartir el diario compartido: uno por esquema.
node scripts/diario-migraciones.mjs separar > separar.sql
less separar.sql                      # léelo antes
psql -d dinamyt -f separar.sql
```

> ### El fallo que tenía este plan, y que costaría el despliegue entero
>
> La versión anterior de esta sección volcaba `-n ecosystem` y `-n academy` por
> separado, **sin el esquema `drizzle`**. Eso pierde el diario, y entonces la
> primera migración del VPS reintenta todo desde cero contra tablas que ya
> existen.
>
> Pero el problema de fondo es peor: **ecosystem y academy comparten la misma
> tabla de diario desde julio**, porque `drizzle.__drizzle_migrations` es un
> nombre global a la base. El migrador salta las migraciones cuyo `created_at`
> sea menor o igual al máximo que encuentre — y ese máximo puede ser de la otra
> app. Con las fechas reales:
>
> | App | Migraciones | Fechas |
> |---|---|---|
> | `ecosystem` | 0000–0003 | 30 may – **6 jul** 2026 |
> | `academy` | 0000–0005 | 10 jul – **11 jul** 2026 |
>
> **Sobre una base nueva, si academy migra primero, ecosystem ve un máximo del
> 11 de julio, da sus cuatro migraciones por aplicadas y no crea ni una tabla.**
> La app arranca sin quejarse y muere en la primera consulta.
>
> Por eso existe `scripts/diario-migraciones.mjs` (en el repo `dinamyt`), que
> calcula el hash de cada migración igual que `readMigrationFiles` de
> drizzle-orm y emite el SQL del reparto. Tres modos:
>
> | Modo | Para qué |
> |---|---|
> | `separar` | Reparte el diario compartido a `<esquema>.__drizzle_migrations`. **Es el del VPS.** |
> | `sellar` | Da por aplicadas todas las migraciones. Solo si el esquema ya es correcto y el diario se perdió |
> | `listar` | Enseña tag, fecha y hash de cada migración, para comprobar a mano |
>
> Emite SQL por la salida estándar y **no toca ninguna base**: se lee antes de
> ejecutarlo.
>
> `[ ]` **Y hay que mirar la producción actual.** Si en `yabnkl…` ya pasó esto,
> puede haber migraciones que nunca corrieron. Antes de dar el volcado por
> bueno: `node scripts/diario-migraciones.mjs listar` y contrastar los hashes
> con `SELECT hash, created_at FROM drizzle.__drizzle_migrations ORDER BY created_at;`.
> Lo que falte, falta también en el esquema.

`[ ]` **b · Membresías** — de `lhgisckr…`, y con el diario:

```bash
# El -n drizzle NO es opcional: ahí vive el diario de migraciones. Sin él, la
# API arranca creyendo que no ha aplicado ninguna y muere al crear tablas que
# ya existen.
pg_dump "$MEMB_URL" --no-owner --no-privileges -n membresias -n drizzle -Fc -f memb.dump
pg_restore -d "postgresql://dinamyt_memb@localhost/dinamyt" --no-owner memb.dump
psql -d dinamyt -c 'ALTER TABLE drizzle.__drizzle_migrations SET SCHEMA membresias;'
```

`[ ]` **c · Campeonatos** — el único con rodeo, porque sus tablas viven en
`public` y aquí van en `campeonatos`:

```bash
pg_dump "$CAMP_URL" --no-owner --no-privileges -n public -Fc -f camp_public.dump

sudo -u postgres createdb tmp_camp
pg_restore -d tmp_camp --no-owner camp_public.dump
psql -d tmp_camp -c 'ALTER SCHEMA public RENAME TO campeonatos;'
pg_dump -Fc --no-owner --no-privileges -n campeonatos tmp_camp -f camp.dump

pg_restore -d "postgresql://dinamyt_camp@localhost/dinamyt" --no-owner camp.dump
sudo -u postgres dropdb tmp_camp
```

`[ ]` **d · Verificación obligatoria.** Contar filas en origen y destino y
compararlas — no «mirar si arranca»:

```sql
SELECT schemaname, relname, n_live_tup
  FROM pg_stat_user_tables
 WHERE schemaname IN ('ecosystem','membresias','campeonatos','academy')
 ORDER BY schemaname, relname;
```

Y a mano: alumnos activos, pagos del último mes, asistencias del último mes,
competidores, campeonatos, llaves y resultados publicados.

### 3.4 Los dos arreglos de esquema, antes de compartir base

`[ ]` **Drizzle.** Una línea en cada uno:

```ts
// packages/membresias-db/src/migrate.ts
await migrate(db as never, { migrationsFolder: carpeta, migrationsSchema: 'membresias' });
```
```ts
// apps/ecosystem-api/drizzle.config.ts
migrationsSchema: 'ecosystem',
```

`[ ]` **Flask.** No hace falta tocar código: el `search_path` del rol basta para
que `db.create_all()` y `schema_compat.py` trabajen dentro de `campeonatos`.
**Pero hay que comprobarlo en un arranque de prueba** — si el `search_path` no
llega, Flask crea una segunda copia vacía de todas sus tablas en `public` y la
app arranca «bien» contra una base vacía.

### 3.5 Respaldos

```cron
0  3 * * * pg_dump -Fc dinamyt > /var/backups/dinamyt-$(date +\%F).dump
15 3 * * * rclone copy /var/backups r2:dinamyt-backups --max-age 48h
30 3 * * * find /var/backups -name '*.dump' -mtime +14 -delete
```

**Prueba el restore, no el backup.** Una vez al mes, levantar un dump en una base
vacía y entrar a mirar.

---

## 4. Identidad única — el trabajo de código

### 4.1 `ecosystem-api` — lo que le falta

| # | Qué | Por qué | Estado |
|---|---|---|---|
| 1 | Arreglar el import de `BadRequestException` | Sin esto no compila | `[ ]` |
| 2 | `POST /auth/invite` — crea cuenta sin contraseña y manda el enlace | Camino B | `[ ]` |
| 3 | `POST /auth/set-password` — canjea el enlace y marca `is_email_verified` en el mismo acto | Camino B | `[ ]` |
| 4 | Código de club: columna en `organizations` + `POST /organizations/join` + aprobación del maestro | Camino C | `[ ]` |
| 5 | `role_membresias` / `role_campeonatos` salen de `org_members.role` | El claim existe; hay que llenarlo | `[ ]` |
| 6 | Enlazar acudiente ↔ menor (`user_guardians`) desde el portal | §2.2 | `[ ]` |
| 7 | Mailer por SMTP genérico en vez de «Gmail o SMTP» | §5 | `[ ]` |
| 8 | `GET /organizations/:id/members` para el autorrellenado de Campeonatos | §2.5 | `[ ]` |

### 4.2 Campeonatos — el bloque grande, con un diseño distinto al plan viejo

El plan de integración anterior proponía migrar `usuarios.id` de Integer a UUID.
**Con 8 claves foráneas y un RLS por workspace entero, eso es reescribir media
base.** El camino con el mismo resultado y una fracción del riesgo:

> **`usuarios` deja de ser una tabla de cuentas y pasa a ser un espejo local de
> la cuenta del ecosystem.**

- Se **conserva** el `id` Integer, y con él las 8 FK y todo el RLS.
- Se **añade** `eco_sub` (UUID, único) y se reutiliza `email` para reconciliar.
- Se **elimina** `password_hash` del flujo.
- En la primera petición con token válido, si el `sub` no está se **crea la fila
  espejo**; si el correo ya existe, se **enlaza** en vez de duplicar.

| Bloque | Archivos | Qué | Estado |
|---|---|---|---|
| **C1** Verificador JWKS | `backend/app/security.py` (nuevo) | `PyJWT` + `PyJWKClient` contra `ECOSYSTEM_JWKS_URL`, con caché. Dependencias: `PyJWT[crypto]`, `cryptography` | `[ ]` |
| **C2** Guards | `app/api/scoping.py` | `usuario_actual()` lee claims y resuelve el espejo; `@requiere_scope` / `@requiere_rol` sustituyen a `@jwt_required()` | `[ ]` |
| **C3** Espejo | `models/usuario.py`, `schema_compat.py` | `eco_sub` + alta/enlace automático. `schema_compat.py` ya es el mecanismo para añadir columnas sin migraciones | `[ ]` |
| **C4** Retirar la emisión | `app/api/auth.py` | Fuera `login`, `register`, contraseñas. Se conservan `/me`, `/logout`, `/socket-ticket`, `/clubes`. `POST /auth/sesion` pasa a ser el canje SSO | `[ ]` |
| **C5** Socket.IO | `sockets/combate_ns.py:477` | `decode_token` → el verificador de C1. El token sigue viajando en el `auth` del socket | `[ ]` |
| **C6** Frontend | `lib/auth.tsx`, `app/login/page.tsx` | Leer `#token=`, canjear por cookie, quitar el formulario propio. **El acceso de jueces por QR se conserva tal cual** | `[ ]` |
| **C7** Roles | varios | `admin→admin`, `juez→judge`, `maestro→coach`. `es_superadmin` se lee del token | `[ ]` |

> **Lo que NO se toca:** campeonatos, categorías, competidores, llaves, tatamis,
> **combate en vivo y puntuación**, resultados, reportes, seeds, importación por
> Excel, exportaciones PDF/Excel/ZIP, el modo local y las ~1.950 líneas de i18n.
> El choque es **solo** de identidad.

> **El modo local sigue siendo el modo local.** El día del campeonato, sin
> internet, no hay ecosystem al que preguntar. La app tiene que arrancar y
> funcionar con `ECOSYSTEM_JWKS_URL` vacía, cayendo a su login propio — el mismo
> criterio que Membresías ya aplica. **Con un campeonato el 9 de octubre, esto
> no es opcional: es la marcha atrás.**

### 4.3 Membresías — mucho menos, porque ya está medio hecho

| Bloque | Qué | Estado |
|---|---|---|
| **M1** | Auto-aprovisionamiento controlado en `plugins/auth.ts`: hoy `usuarioVigente()` devuelve `null` si el correo no existe. Pasa a crear la ficha **solo si** hay invitación aceptada o entrada por código de club | `[ ]` |
| **M2** | `POST /users` deja de pedir contraseña: crea la ficha y (opcional) dispara la invitación | `[ ]` |
| **M3** | Botón «invitar» + estado visible: `sin cuenta` / `invitado` / `activo` | `[ ]` |
| **M4** | Pantalla de código del club y bandeja de solicitudes del maestro | `[ ]` |
| **M5** | El login propio se conserva **solo** como respaldo con `ECOSYSTEM_JWKS_URL` vacía | `[ ]` |
| **M6** | «Olvidé mi contraseña» → enlace al portal | `[ ]` |
| **M7** | `orgs.eco_org_id` + pantalla de acudientes y menores | `[ ]` |

---

## 5. El correo — y cómo cambia el software que ya existe

**Hoy ninguna de las dos apps envía un solo correo**, y el ecosystem envía por
Gmail. Esto sostiene los tres caminos de alta, así que va antes del corte.

### 5.1 Qué se contrata

| Servicio | Para qué | Costo | Estado |
|---|---|---|---|
| **Cloudflare Registrar** | El dominio `dinamyt.org` (`.com` está tomado) | ~US$10/año | `[ ]` |
| **Cloudflare Email Routing** | **Recibir**: `soporte@` y `admin@` reenviados a tu Gmail | Gratis | `[ ]` |
| **Resend** | **Enviar**: 3.000/mes, **100 al día**, 1 dominio | Gratis | `[ ]` |
| **Amazon SES** | El plan B para las ráfagas de campeonato | US$0,16/millar | `[ ]` **pedir ya: 24–48 h** |

### 5.2 Cómo cambia el software, app por app

Esto es lo que preguntaste: qué toca de lo que ya está escrito.

| App | Qué existe hoy | Qué cambia | Cuánto |
|---|---|---|---|
| **ecosystem-api** | `mailer.service.ts` con `nodemailer`, configurado para «Gmail o SMTP genérico». Ya manda OTP de verificación y de recuperación | Solo cambia la **configuración**: `MAIL_HOST=smtp.resend.com`, puerto 587, usuario `resend`, la API key como contraseña. El código de `nodemailer` sirve tal cual. Se le añaden las plantillas nuevas: invitación y «pon tu contraseña» | **Bajo.** Variables + 2 plantillas |
| **membresias-api** | **Nada.** Cero librerías de correo. Pero `notifications` **ya tiene** el canal `email` y los estados `PENDIENTE/ENVIADA/FALLIDA` desde la primera migración, sin estrenar. Y `lib/auth/tokens.ts` ya emite tokens firmados de vida corta (los del QR) | Módulo `lib/mail.ts` nuevo (nodemailer + SMTP), el contador de `MAIL_DAILY_MAX`, y el canal `email` en `generarAvisos` para `venc` y `mora` | **Medio.** Un módulo nuevo, sin tocar la arquitectura |
| **Campeonatos (Flask)** | **Nada.** Ninguna librería de correo en `requirements.txt` | `smtplib` de la biblioteca estándar (no hace falta dependencia nueva) para las invitaciones a competidores. **Se puede aplazar a la Fase 2**: para el campeonato de octubre no es imprescindible | **Bajo**, y aplazable |

### 5.3 Contrato único de variables (igual en las tres)

```bash
SMTP_HOST=smtp.resend.com
SMTP_PORT=587
SMTP_USER=resend
SMTP_PASS=                       # la API key de Resend
MAIL_FROM=DINAMYT <no-reply@dinamyt.org>
MAIL_REPLY_TO=soporte@dinamyt.org
MAIL_DAILY_MAX=90                # tope propio, por debajo del del proveedor
```

**Contra SMTP, no contra el SDK del proveedor.** Resend y SES hablan los dos
SMTP: cambiar de uno al otro son cuatro variables. Y el mismo criterio que ya
usan las apps con el SSO y con `CRON_SECRET`: **sin `SMTP_HOST`, la función de
correo no existe** — la app arranca igual, en vez de romperse a medias.

### 5.4 Qué se manda, y qué no

| Aviso | Canal | Por qué |
|---|---|---|
| Verificar cuenta / poner contraseña | **Correo** | Única forma de saber que la dirección existe |
| Recuperar contraseña | **Correo** | Camino único, en el ecosystem |
| Invitación del maestro | **Correo** | Es el mecanismo entero |
| Vencido / mora | **Correo** + push | Toca el bolsillo, y quien deja vencer es quien no abre la app |
| Por vencer | Push + campana | Ya funciona y es gratis |
| **Hay clase hoy / nota de la semana** | Push y campana, **NUNCA correo** | Es diario y para todos: él solo agota la cuota |
| Cumpleaños | Campana del maestro | Es un dato de pantalla |

Con 100 alumnos salen **~12–13 correos al día** contra un tope de 100 (números
hechos en `CORREO.md`). El aviso de clase por correo serían 100 diarios: el tope
exacto, todos los días.

El guardián: `MAIL_DAILY_MAX` se cuenta **en el código**. Si Resend rechaza el
correo 101 el fallo es silencioso y nadie se entera hasta que alguien reclama.
Con el tope propio, la fila queda en `PENDIENTE` y sale mañana.

### 5.5 DNS y reputación

`[ ]` DKIM de Resend, SPF, MX de Email Routing, y `_dmarc` con
`v=DMARC1; p=none; rua=mailto:soporte@dinamyt.org`. Empezar en `p=none`, subir a
`quarantine` y luego a `reject` a las dos semanas con los reportes limpios.
Ponerlo en `reject` el primer día es la forma más rápida de que tus propios
correos dejen de llegar.

---

## 6. El monorepo — actualizarlo sin mover nada

### La regla de oro

> **Los repos `dinamyt-combat` y `dinamyt-membresias` no se mueven, no se
> archivan y siguen siendo donde se trabaja. `dinamyt` recibe una copia
> sincronizada y NUNCA se edita a mano.**
>
> El día que alguien edite Campeonatos dentro de `dinamyt`, ese cambio se pierde
> en la siguiente sincronización. Sin excepciones.

### 6.1 Qué se hace

`[ ]` **1 · Commitear lo suelto.** 2 archivos en `dinamyt-combat`, 30 en
`dinamyt`. Un subtree sobre un árbol sucio es una tarde perdida.

`[ ]` **2 · Tag de archivo antes de borrar nada:**

```bash
cd D:/Repositorios/dinamyt
git tag archivo/antes-de-actualizar && git push origin archivo/antes-de-actualizar
```

`[ ]` **3 · Borrar las copias viejas:** `apps/campeonatos-api`,
`apps/campeonatos-web`, `apps/campeonatos-combat`, `apps/campeonatos-api-local`,
`apps/campeonatos-web-local`, `apps/membresias-agent`,
`packages/campeonatos-core`, `packages/campeonatos-db`, `packages/membresias-db`.

`[ ]` **4 · Traer las buenas con `git subtree`** (conserva el historial completo):

```bash
git checkout -b feat/actualizar-apps
git remote add combat     https://github.com/ArsenalCrack/dinamyt-combat.git
git remote add membresias https://github.com/ArsenalCrack/dinamyt-membresias.git
git fetch combat && git fetch membresias

git subtree add --prefix=services/campeonatos combat/main
git subtree add --prefix=apps/membresias      membresias/main
```

`[ ]` **5 · Guion de sincronización** (`sync-apps.ps1`), para que ponerse al día
sea un comando y no una ceremonia:

```powershell
git subtree pull --prefix=services/campeonatos combat/main     --squash
git subtree pull --prefix=apps/membresias      membresias/main --squash
```

### 6.2 Cómo queda

```
dinamyt/
├── apps/
│   ├── ecosystem-api/       (NestJS  :3001)  ← vive aquí
│   ├── ecosystem-portal/    (Next    :3000)  ← vive aquí
│   ├── academy-api/         (:3007)          ← vive aquí
│   ├── academy-web/         (:3008)          ← vive aquí
│   └── membresias/          (:3004 y :3006)  ← ESPEJO de dinamyt-membresias
├── services/
│   └── campeonatos/         (:5000 y :3003)  ← ESPEJO de dinamyt-combat
├── packages/
│   ├── shared/              ← contrato del token, fuente de verdad única
│   └── academy-db/
└── sync-apps.ps1
```

### 6.3 Qué despliega el VPS

**Los tres repos, cada uno desde su origen.** El espejo del monorepo es para
tener todo junto y para que `packages/shared` sea de verdad compartido; **no es
lo que corre en producción**. Así un despliegue no depende de acordarse de
sincronizar.

| Servicio | Se clona de |
|---|---|
| `ecosystem-api`, `ecosystem-portal`, `academy-*` | `ArsenalCrack/dinamyt` |
| Campeonatos (Flask + Next) | `ArsenalCrack/dinamyt-combat` |
| Membresías (API + web) | `ArsenalCrack/dinamyt-membresias` |

### 6.4 El contrato del token

`packages/shared/src/auth.ts` es la fuente de verdad. Las dos apps lo consumen
por **copia con puntero**: un archivo con un comentario en la primera línea que
dice de dónde salió. Flask no puede importar TypeScript de todas formas, y una
copia de 25 líneas con un puntero es más honesta que un paquete publicado que
nadie va a versionar.

---

## 7. El VPS

### 7.1 Mapa

| Host | Qué vive ahí | Puerto interno |
|---|---|---|
| `dinamyt.org` + `www` | **Portal del ecosystem** — la puerta: aquí se inicia sesión | 3000 |
| `id.dinamyt.org` | `ecosystem-api` (JWKS, registro, verificación) | 3001 |
| `campeonatos.dinamyt.org` | Next + Flask + Socket.IO | 3003 y 5000 |
| `club.dinamyt.org` | Membresías (web + API) | 3006 y 3004 |
| `academy.dinamyt.org` | Academy | 3008 y 3007 |
| `send.dinamyt.org` | Lo crea Resend solo, para los rebotes | — |

> **Cambio respecto a `PLANVPS.md`:** allí la raíz redirigía a Campeonatos. Con
> el ecosystem como único IdP, la raíz **tiene que ser el portal**: es donde se
> registra uno y adonde apuntan todos los enlaces de los correos.

### 7.2 Caddyfile

```caddyfile
dinamyt.org, www.dinamyt.org {
	encode zstd gzip
	reverse_proxy 127.0.0.1:3000
}

id.dinamyt.org {
	encode zstd gzip
	reverse_proxy 127.0.0.1:3001
}

campeonatos.dinamyt.org {
	encode zstd gzip
	handle /api/*       { reverse_proxy 127.0.0.1:5000 }
	handle /socket.io/* { reverse_proxy 127.0.0.1:5000 }
	handle              { reverse_proxy 127.0.0.1:3003 }
}

club.dinamyt.org {
	encode zstd gzip
	reverse_proxy 127.0.0.1:3006
}

academy.dinamyt.org {
	encode zstd gzip
	reverse_proxy 127.0.0.1:3008
}
```

> **Por qué Campeonatos parte las rutas y Membresías no.** En Campeonatos el
> rewrite conserva el prefijo `/api`, así que Caddy lo manda directo al Flask — y
> el WebSocket **necesita** ese camino, porque pasando por Next se degradaría a
> long-polling. En Membresías el rewrite **quita** el `/api` antes de reenviar,
> así que ahí todo entra por Next. Copiar el bloque de una a la otra rompe la API
> con 404.

### 7.3 Lo que no cambia

- Ubuntu 24.04, usuario propio, SSH por llave, `ufw` con solo 22/80/443,
  `fail2ban`, `unattended-upgrades`, `timedatectl set-timezone America/Bogota`.
- **Python 3.11, no la 3.12 del sistema**: con 3.12+ el monkey-patching de
  eventlet se rompe bajo gunicorn y **toda consulta responde 500**.
- **`gunicorn -k eventlet -w 1`** — el `-w 1` no es negociable: el estado en vivo
  de los tatamis, los rooms de Socket.IO y el limitador viven en la memoria del
  proceso. Con dos workers, dos jueces del mismo tatami ven marcadores distintos.
- **Nunca abrir 3000/3001/3003/3004/3006/3007/3008/5000/5432.**
- `systemd` por servicio, llamando a `next` directo (el `start` del
  `package.json` de Campeonatos levanta en `-H 0.0.0.0`).
- **Reconstruir tras tocar cualquier `NEXT_PUBLIC_*` o `MEMBRESIAS_API_ORIGIN`**:
  viven dentro del build.

### 7.4 RAM — ahora son seis servicios

Con academy dentro son **seis** procesos y **cuatro** frontends de Next. Reposo
~1,8 GB; el pico sigue siendo el `next build`, hasta 2 GB él solo.

> **8 GB, no 4.** Con 4 GB hay que compilar en el PC y subir el resultado en cada
> despliegue — y con un campeonato el 9 de octubre, un despliegue que depende de
> tu portátil es un riesgo que no hace falta correr.

---

## 8. Calendario · el campeonato manda

**Hoy es el 19 de agosto. El campeonato es el 9, 10 y 11 de octubre.** Son 7
semanas, y la parte delicada (la identidad) no puede quedar sin reposo.

```
ago 19 ─────── ago 29 ─── sep 5 ─── sep 19 ──── sep 30 │ oct 1 ─── oct 13 │ oct 14 ──▶
   B0   B1: servicio      B2      B3: identidad  reposo │    CONGELADO     │  Fase 2
        de vuelta       correo                          │  campeonato 9-11 │
```

### 8.1 Los bloques

| | Qué | Tope | Riesgo | Estado |
|---|---|---|---|---|
| **B0** | Commitear lo suelto · **volcado de las tres bases, guardado fuera del VPS y verificado** | 21 ago | — | `[ ]` |
| **B1** | Comprar dominio y VPS · **pedir SES** · arreglos previos (§1.5) · Postgres · restaurar las tres bases · levantar las apps **tal cual, con sus logins actuales** · DNS | **29 ago** | Medio | `[ ]` |
| **B2** | Correo: verificar dominio, plantillas, prueba a Gmail y Outlook con `SPF: PASS` y `DKIM: PASS` | 5 sep | Bajo | `[ ]` |
| **B2b** | Actualizar el monorepo (§6). Sin impacto en producción; puede ir en paralelo | 5 sep | Nulo | `[ ]` |
| **B3** | Identidad única (§4): ecosystem-api → Membresías (poco) → Campeonatos (mucho) → reconciliación (§2.4) → aviso a la gente | **19 sep** | **Alto** | `[ ]` |
| **B3s** | Reposo: 10 días con todo el mundo usándolo antes de la congelación | 20–30 sep | — | `[ ]` |
| **🔒** | **CONGELADO.** Ni un despliegue. Snapshot del VPS el día 8 | 1–13 oct | — | — |
| **B4** | Fase 2 (§10) | desde 14 oct | — | `[ ]` |

### 8.2 Las tres reglas del calendario

1. **B1 antes que B3, siempre.** Mudarse y reescribir la identidad a la vez
   significa que, cuando algo falle —y algo va a fallar—, no habrá manera de
   saber si fue la mudanza o la identidad. Separados, cada fallo tiene un solo
   sospechoso.
2. **Si B3 no está terminado y en reposo el 30 de septiembre, B3 se aplaza al 14
   de octubre.** Sin discusión. Un campeonato con la identidad recién cambiada es
   la peor combinación posible, y las apps funcionan perfectamente con sus logins
   actuales — B1 ya devolvió el servicio.
3. **Del 1 al 13 de octubre no se toca nada.** Snapshot del VPS el día 8, y el
   modo local de Campeonatos probado de punta a punta antes del día 1.

### 8.3 Verificación final

- `[ ]` `https://dinamyt.org` carga el portal, candado válido
- `[ ]` Registro nuevo: llega el código, verifica, entra
- `[ ]` «Olvidé mi contraseña»: llega el correo, se cambia, entra
- `[ ]` Desde el portal, saltar a Campeonatos y a Membresías **sin segundo login**
- `[ ]` **Recargar** en las dos apps: la sesión aguanta
- `[ ]` La cookie de sesión de cada app es `httpOnly` (no se ve desde la consola)
- `[ ]` Tatami + pantalla pública en dos dispositivos: el marcador se refleja al instante
- `[ ]` En la consola, Socket.IO como `websocket`, **no** `polling`
- `[ ]` **La puntuación funciona igual que antes**: un combate completo, con faltas y desempate
- `[ ]` Reporte en PDF y en Excel
- `[ ]` Membresías: login de maestro, check-in con QR, push al celular, carnet impreso
- `[ ]` Invitar a un alumno: llega el correo, pone contraseña, entra, y **es la misma cuenta** con la que entra a Campeonatos
- `[ ]` Código de club: alguien con cuenta lo usa y el maestro lo aprueba
- `[ ]` Un padre ve el estado de sus dos hijos desde una sola cuenta
- `[ ]` `curl` del cron responde `{"ok":true,…}`
- `[ ]` `SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname LIKE 'dinamyt_%'` → todo `f`
- `[ ]` RLS de verdad: consulta con el rol de Membresías sin fijar `app.org_id` → **cero filas**
- `[ ]` El respaldo de anoche existe y pesa lo que debe
- `[ ]` **Modo local de Campeonatos**: con `ECOSYSTEM_JWKS_URL` vacía arranca y se juzga un combate sin internet

---

## 9. Anclajes baratos — lo que se pone AHORA para no migrar dos veces

Esta sección es la respuesta a «añádelo **estratégicamente**, sin estropear lo
prioritario». Todo lo de la Fase 2 (§10) necesita columnas en la base. Ponerlas
**durante la migración** cuesta minutos; ponerlas después de que el club esté en
producción cuesta una ventana de mantenimiento.

**Ninguno de estos anclajes cambia el comportamiento de nada.** Son columnas con
valor por defecto y un punto de comprobación que de momento siempre dice que sí.

| # | Anclaje | Para qué (Fase 2) | Estado |
|---|---|---|---|
| 1 | `membresias.orgs.eco_org_id` uuid | Club único en el ecosystem (§2.5) — **necesario ya** | `[ ]` |
| 2 | `membresias.users.eco_sub` uuid | Espejo de la cuenta — **necesario ya** | `[ ]` |
| 3 | `campeonatos.usuarios.eco_sub` uuid · `campeonatos.campeonatos.eco_org_id` uuid | Ídem — **necesario ya** | `[ ]` |
| 4 | `membresias.orgs.arte_marcial` varchar default `'hapkido'` | Multi-arte en Membresías (§10.3) | `[ ]` |
| 5 | Tabla `membresias.grados` (`org_id`, `orden`, `nombre`, `color`), sembrada con los 11 cinturones actuales | Cinturones por club. Hoy son una constante en el código (`lib/cinturones.ts`, duplicada en api y web) | `[ ]` |
| 6 | `campeonatos.campeonatos.arte_marcial` + `reglamento` varchar default `'hapkido-gha'` | Paquetes de reglamento (§10.4) | `[ ]` |
| 7 | `ecosystem.subscription_plans.limites` jsonb | Plan gratuito (§10.2). Ej.: `{"membresias":{"alumnos":20},"campeonatos":{"competidores":50}}` | `[ ]` |
| 8 | Una función `assertLimite(recurso)` en cada API, llamada en los sitios de alta, que **de momento devuelve siempre `true`** | El día del plan gratuito solo hay que llenarla, no buscar dónde va | `[ ]` |

> **El 5 y el 6 son los que más ahorran.** El catálogo de cinturones está hoy
> como constante `as const` en TypeScript, duplicada en API y web; y el
> reglamento de hapkido está repartido por 782 líneas de `combate_engine.py` y
> 1.685 de `combate_ns.py`. Mover eso a datos **después** de que haya
> campeonatos y clubes cargados es mucho más caro que dejar la columna puesta hoy.

---

## 10. Fase 2 — desde el 14 de octubre

Nada de esta sección se empieza antes del campeonato. Va aquí para que los
anclajes de §9 tengan sentido y para no volver a pensarlo desde cero.

### 10.1 Portada de DINAMYT · información, planes y precios

`[ ]` Rehacer `ecosystem-portal/src/app/page.tsx` y `/planes`: qué es cada
producto, para quién, con capturas reales, y **los precios de verdad** (hoy
`/planes` solo enseña un correo de contacto).

`[ ]` Definir la tabla de precios: qué incluye cada plan, límites, y qué pasa al
pasarse. Esto es una decisión de negocio, no de código, y conviene tenerla
escrita antes de programar nada.

### 10.2 Plan gratuito de prueba

La idea: que quien entre vea las pantallas y entienda a qué escala llega el
producto, sin poder operar un club entero gratis.

| Producto | Límite propuesto | Qué se ve igual |
|---|---|---|
| **Membresías** | **20 alumnos** activos | Todas las pantallas: roster, planes, pagos, asistencia, kiosco, carnet, avisos |
| **Campeonatos** | **50 competidores** por campeonato · 1 campeonato activo | Llaves, tatamis, combate en vivo, reportes |
| **Academy** | Por definir cuando exista | — |

`[ ]` Decidir entre **límite permanente** o **un mes de prueba completo**. Mi
recomendación: **límite permanente**, no mes de prueba. Un club de 20 alumnos que
funciona gratis se convierte en cliente cuando llega a 25; un mes que caduca deja
a un club a medias con sus datos dentro, y eso genera más bajas que ventas.

`[ ]` Los límites viven en `ecosystem.subscription_plans.limites` (anclaje 7) y
se comprueban en `assertLimite()` (anclaje 8). **Nunca en el frontend**: el
frontend avisa, la API impide.

`[ ]` Mensaje al llegar al tope: qué falta, cuánto cuesta el siguiente plan, y
un botón. No un error.

### 10.3 Multi-arte en Membresías — lo fácil

Hoy `lib/cinturones.ts` es una lista fija de 11 cinturones de hapkido GHA,
duplicada en API y web. La columna ya es `varchar(40)` y no un enum,
**precisamente para esto** (lo dice el comentario del esquema).

`[ ]` Al crear el club, el maestro escribe **el nombre de su arte marcial** (texto
libre: hapkido, taekwondo, karate, jiu-jitsu, kali…).

`[ ]` Y **ordena sus grados**: nombre, orden y color, arrastrando. Con tres
plantillas de partida (hapkido GHA, taekwondo, karate) y la opción de empezar en
blanco.

`[ ]` Un club **puede no usar cinturones**: si la lista queda vacía, el campo
desaparece de la ficha y del carnet. Hay artes que no gradúan por color.

`[ ]` `lib/cinturones.ts` pasa de constante a consulta cacheada por club, en API
y en web.

### 10.4 Multi-arte en Campeonatos — lo difícil, y por qué

Tienes razón en que aquí es más complicado: **todo funciona sobre un reglamento**,
y ese reglamento no está en una tabla, está repartido por el código:

| Dónde | Líneas | Qué decide |
|---|---|---|
| `app/engine/combate_engine.py` | 782 | Puntuación, faltas, sanciones, fin de combate, desempate |
| `app/sockets/combate_ns.py` | 1.685 | El combate en vivo: rounds, tiempos, qué puede pulsar cada juez |
| `app/engine/secciones_engine.py` | 236 | Cómo se arman las categorías |
| `app/engine/figuras_engine.py` | 573 | Formas / poomsae |

**Tu idea de empaquetarlo es la correcta.** El diseño:

`[ ]` Un **paquete de reglamento** es un módulo que declara, en datos siempre que
se pueda y en código solo cuando haga falta:

1. **Categorías** — cómo se agrupa: peso, edad, grado, sexo, y los cortes.
2. **Formato del combate** — rounds, duración, descansos, tiempo de oro.
3. **Puntuación** — qué acción vale cuánto, y quién puede otorgarla.
4. **Faltas y sanciones** — cuántas amonestaciones, qué descuentan, cuándo descalifican.
5. **Fin anticipado** — diferencia técnica, KO, abandono.
6. **Desempate** — el orden de criterios.
7. **Llaves** — eliminación simple, repechaje, round robin; ¿uno o dos bronces?
8. **Impresos** — qué sale en la planilla y en el reporte.

`[ ]` `hapkido-gha` es el primer paquete, **extraído del código actual sin
cambiar ni un comportamiento**. Ese es el paso que hay que hacer con más cuidado:
la prueba de que salió bien es que un campeonato viejo, recalculado con el
paquete, da exactamente los mismos resultados.

`[ ]` Al crear el campeonato se elige **arte marcial → reglamento** (anclaje 6).
Un campeonato ya creado no cambia de reglamento: los combates ya puntuados dejarían
de cuadrar.

`[ ]` Después: `taekwondo-wt` (olímpico) y `karate-wkf`, cada uno contra su
reglamento mundial publicado.

> **Aviso honesto de tamaño.** Extraer el reglamento de hapkido a un paquete es
> el trabajo más grande de todo este documento, más que la identidad. No se toca
> hasta después de octubre, y cuando se toque, se hace con el motor cubierto de
> pruebas primero.

### 10.5 Academy conectado al ecosystem

`[ ]` Academy ya está en el monorepo y ya lee `ECOSYSTEM_JWKS_URL`. Cuando se
retome, entra por la misma puerta que las otras dos: **valida el token, no lo
emite**, y su `org_id` sale del ecosystem.

`[ ]` Su `role_academy` ya existe en el contrato del token (`shared/src/auth.ts`).
No hay que ampliar nada.

`[ ]` El plan gratuito de Academy se define con `subscription_plans.limites`,
igual que los otros dos. El anclaje ya estará puesto.

---

## 11. Riesgos y pendientes

### 11.1 Riesgos, en orden de gravedad

1. **Un campeonato el 9 de octubre y un solo servidor.** Es el riesgo que manda
   sobre todos los demás. Mitigación: la regla 2 de §8.2 (aplazar B3 si no llega),
   snapshot del VPS la víspera, y el modo local probado — `/local`, `/tablero` y
   el paquete `.json` de sincronización existen exactamente para esto.

2. **Las llaves RSA del ecosystem existen solo en tu PC.** `private.pem` y
   `public.pem` están en la raíz de `D:\Repositorios\dinamyt`, **ignorados por
   git** (`.gitignore:22`) y por tanto **sin copia en ninguna parte**. Si se
   pierde ese disco, mueren todas las sesiones del ecosistema y hay que volver a
   emitir. `[ ]` Copiarlas a un gestor de contraseñas o a un sobre cifrado **hoy**,
   antes de cualquier otra cosa. Y llevarlas al VPS por `scp`, nunca por chat ni
   por correo.

3. **Producción está caída** (Render suspendido). No hay marcha atrás a la que
   volver: el único respaldo son los volcados de B0.

4. **Todo el mundo pone contraseña nueva una vez** (§2.4). Hay que anunciarlo con
   días de antelación y con el correo ya funcionando. Si cae encima del
   campeonato, es un desastre — otra razón para la regla 2 de §8.2.

5. **Las contraseñas de Supabase viajaron por chat** (§0.1). Rotar tras verificar.

6. **El diario de Drizzle** (§1.5-2). Si se olvida, Membresías arranca contra un
   esquema incompleto.

7. **El `search_path` de Flask** (§3.4). Si no llega, la app crea tablas vacías en
   `public` y arranca «bien» contra una base sin datos.

8. **Ahora el sysadmin eres tú**: actualizaciones, respaldos y estar disponible.

9. **El tope de Resend son 100 al día.** El día que abras inscripciones del
   campeonato se pasa solo. SES pedido en B1, no en septiembre.

### 11.2 Pendientes de decisión

| # | Qué | Estado |
|---|---|---|
| 1 | RAM del VPS | `[x]` **8 GB** (19 ago) |
| 2 | Proveedor | `[x]` **Contabo** (19 ago) — ver §11.4 |
| 3 | Dominio | `[x]` **`dinamyt.org`** (19 ago) |
| 4 | Contraseña real de las bases de Membresías y Campeonatos | `[ ]` **bloquea B0** |
| 5 | Precios reales de los planes | `[ ]` Fase 2, §10.1 |
| 6 | ¿Límite permanente o mes de prueba? Recomiendo permanente | `[ ]` Fase 2, §10.2 |

### 11.4 Contabo · lo que hay que saber antes de darle a comprar

Contabo da la mejor relación RAM/precio del mercado, que es justo lo que hace
falta aquí (seis servicios y cuatro `next build`). A cambio hay cuatro cosas que
no se parecen a Hetzner o DigitalOcean y conviene no descubrir el día del
despliegue:

`[ ]` **La región.** Elegir una de las de Estados Unidos — Nueva York o
St. Louis dan la mejor latencia desde Colombia. **No coger una europea**: son
las que salen por defecto y desde aquí añaden 120–150 ms, que en el marcador de
un tatami se nota.

`[ ]` **El disco.** El plan base viene con SSD normal, no NVMe. Con PostgreSQL
encima merece la pena el NVMe: la base es pequeña, pero los `next build` y los
`pg_restore` van a disco todo el rato.

`[ ]` **El alta no es instantánea.** Hetzner entrega en segundos; Contabo puede
tardar horas y a veces pide verificación manual. **Comprar el primer día del
bloque B1, no el último**, o la semana se va esperando.

`[ ]` **La cuota de alta.** Varios planes llevan un pago único además del
mensual. Mirarlo antes para que el número no sorprenda.

Lo que **no** cambia: el puerto 25 saliente está bloqueado, como en casi todos
los proveedores — da igual, el correo sale por `smtp.resend.com:587` (§5).

### 11.3 Cuánto cuesta al mes

| Concepto | Hoy | En el VPS |
|---|---|---|
| Servidores de las apps | US$0 — **y por eso están suspendidos** | incluido |
| Web | US$0 (Vercel Hobby: no permite uso comercial) | incluido |
| Bases de datos | US$0 (3 proyectos en plan gratis) | incluido |
| VPS 8 GB | — | US$16–24 |
| Dominio | — | US$0,85 |
| Buzón y envío de correo | — | US$0–0,20 |
| Respaldos | — | ~US$0,20 |
| **Total** | **US$0 y caído** | **≈ US$18–26** |

---

## Anexo · Puertos

| Puerto | Quién | Expuesto |
|---|---|---|
| 22, 80, 443 | SSH y Caddy | Sí |
| 3000 | Portal del ecosystem | No, solo `127.0.0.1` |
| 3001 | `ecosystem-api` | No |
| 3003 | Campeonatos web | No |
| 3004 | Membresías API | No |
| 3006 | Membresías web | No |
| 3007 / 3008 | Academy API / web | No |
| 5000 | Campeonatos API + Socket.IO | No |
| 5432 | PostgreSQL | No |

## Anexo · DNS

| Tipo | Nombre | Valor | Proxy |
|---|---|---|---|
| A | `@`, `www`, `id`, `campeonatos`, `club`, `academy` | IP del VPS | **Gris** |
| MX | `@` | Los de Cloudflare Email Routing | — |
| TXT | `@` | SPF de Email Routing | — |
| TXT | `resend._domainkey` | DKIM de Resend | — |
| MX + TXT | `send` | Rebotes y SPF de Resend | — |
| TXT | `_dmarc` | `v=DMARC1; p=none; rua=mailto:soporte@dinamyt.org` | — |
| CNAME ×3 | los de SES | Easy DKIM, cuando se active | — |

> En **gris (DNS only)**: Caddy necesita validar el certificado sin nadie en
> medio. Si más adelante quieres proxear para esconder la IP, pon SSL/TLS en
> **Full (strict)** y ten en cuenta que el plan gratis corta las peticiones HTTP
> a los ~100 s — los reportes PDF de un campeonato grande pueden pasarse.
