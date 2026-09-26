# Sincronización LOCAL ↔ ONLINE — diseño y guía de uso

> Estado: **implementado** (2026-07-26). Este documento describe cómo funciona
> el traspaso de datos entre las dos instalaciones de DINAMYT y por qué está
> hecho así. Para el manual de uso rápido, ver la sección «Cómo se usa».

La organización trabaja con **dos instalaciones** de DINAMYT, con bases de datos
separadas:

| | ONLINE (internet) | LOCAL (LAN del evento) |
|---|---|---|
| Para qué | Recibe las inscripciones de los maestros y publica los resultados al público | Corre el campeonato el día del evento |
| Red | Internet (Render + Vercel + Neon) | LAN del polideportivo, **sin depender de internet** |
| Base de datos | PostgreSQL | SQLite |

---

## La idea que lo simplifica todo

**No es una sincronización bidireccional. Son dos traspasos de un solo sentido,
en momentos distintos:**

```
   ANTES DEL EVENTO                          DURANTE / DESPUÉS
   ONLINE  ──── paquete .json ───►  LOCAL    LOCAL ──── resultados ───►  ONLINE
   (inscripciones, usuarios,                 (podios y rankings, para
    config, llaves)                           la página pública)
```

Con esa regla no hace falta resolver conflictos campo a campo, ni fusionar
versiones, ni tener los relojes de las dos máquinas sincronizados.

**Regla que hay que respetar:** mientras el evento corre en LOCAL, el ONLINE no
se edita. Si alguien se inscribe online después de que exportaste, vuelves a
exportar e importar: la importación es idempotente y no duplica nada.

---

## Cómo se usa

### 1. Antes del evento: llevar el campeonato al software local

1. En el **ONLINE**, entra al campeonato → botón **«⬆️ Exportar campeonato»**.
   Elige qué incluir (maestros y jueces, competidores e inscripciones, llaves)
   y descarga el `.json`.
2. Copia el archivo al PC del evento (USB o red).
3. En el **LOCAL**, entra a `/admin` → pestaña Campeonatos →
   **«⬇️ Importar campeonato»**.
4. Selecciona el archivo y pulsa **«Analizar archivo»**. Verás exactamente qué
   va a pasar:

   ```
   Esto es lo que va a pasar
   Campeonato 'Copa Nacional 2026' importado · Exportado por admin@… · 26/07 18:42
     Maestros y jueces:      2 nuevos · 3 actualizados · 0 omitidos
     Competidores:         148 nuevos · 12 actualizados · 0 omitidos
     Inscripciones:        160 nuevos · 0 actualizados · 0 omitidos
     Tatamis:                6 nuevos · 0 actualizados · 0 omitidos
     Asignaciones de jueces: 4 nuevos · 0 actualizados · 0 omitidos
     Llaves:                32 nuevos · 0 actualizados · 0 omitidos
   Avisos
     · 5 usuario(s) se crearon SIN contraseña: los jueces entran con el QR de
       su tatami; si alguien necesita entrar con clave, asígnasela en Usuarios.
   ```

5. Si todo cuadra, **«✓ Confirmar e importar»**. Se escribe todo de golpe, en
   una sola transacción.

### 2. Después del evento: publicar los resultados

**Suben solos** cuando el PC del evento vuelve a tener red y el admin entra con
su cuenta de DINAMYT en ese mismo PC (`INICIAR-LOCAL.md` §7.2). El camino a mano
sigue valiendo: en el LOCAL, campeonato → Reportes → **«Exportar resultados»**, y
en el ONLINE, `/admin/importar-resultados`. Viajan los podios y rankings, que es
lo que ve el público.

### 3. Otros paquetes (opcionales)

- **Usuarios** — `/admin` → pestaña Jueces → Exportar / Importar. Útil para
  dejar lista una instalación nueva antes de traspasar campeonatos.
- **Competidores** — `/admin/competidores` → Exportar / Importar. JSON con
  todos los campos (el Excel sigue estando, para capturar listas a mano).

> No hace falta importar los usuarios por separado antes del campeonato:
> **el paquete de campeonato ya los lleva dentro**.

---

## Por qué está hecho así

### El problema: los ids no significan lo mismo en las dos instalaciones

Cada instalación numera sus filas con su propia clave entera autoincremental: el
usuario `id=7` del online es **otra persona** en el local. Además hay referencias
cruzadas por todas partes (`asignaciones_juez` → `usuarios` + `tatamis`,
`inscripciones` → `campeonatos` + `competidores` + `usuarios`, `llaves` →
`campeonatos` + `tatamis`).

Y el fallo más peligroso no era un error, sino el **silencio**: el aislamiento
por workspace (`api/scoping.py`) filtra por `created_by` / `creado_por_id`. Unas
filas importadas con un dueño que no existe en destino **entran a la base pero el
administrador no las ve**. Un error se corrige en el momento; eso se descubre el
día del campeonato.

### Las tres piezas de la solución

**1. Identidad estable: la columna `uid`** (`backend/app/uid.py`)

Cada fila sincronizable (usuarios, competidores, tatamis, asignaciones,
inscripciones, llaves) lleva un UUID que **no cambia al viajar** entre
instalaciones. `Campeonato` reutiliza su `export_uuid`, que ya existía para
publicar resultados, así el paquete completo y el snapshot de resultados hablan
siempre del mismo campeonato.

- Se agregó con el mecanismo que el proyecto ya usaba para esto
  (`schema_compat.py`: ALTER TABLE al arrancar, sin migraciones de Alembic), más
  un backfill que rellena las bases que ya existían.
- El uid nunca se muestra en la interfaz.
- **Emparejamiento al importar:** `uid` → clave natural (correo del usuario,
  documento del competidor, número del tatami) → crear nuevo. Ese segundo paso
  es lo que evita duplicar al maestro que ya existía en las dos instalaciones.

**2. Un paquete auto-contenido** (`backend/app/api/sincronizacion.py`)

El paquete de campeonato lleva dentro **todo lo que el campeonato necesita para
existir**, incluidos los usuarios a los que hace referencia. Así el problema del
orden de importación desaparece: no hay forma de que el usuario lo haga "en el
orden malo", porque el importador resuelve las dependencias él mismo y siempre
en la misma secuencia:

```
usuarios → campeonato → tatamis → asignaciones → competidores → inscripciones → llaves
```

Dos detalles del código existente que ayudaron mucho:

- **Las llaves no dependen de ids de competidor**: `Llave.estructura` ya guarda a
  los competidores embebidos por nombre y club, así que viajan tal cual.
- Las **categorías** se emparejan por `slug`, idéntico en ambas instalaciones
  porque sale del mismo seed.

**3. Importación transaccional con vista previa**

La vista previa **ejecuta exactamente el mismo código** que la importación real y
revierte la transacción al final. No hay dos caminos que puedan divergir: lo que
anuncia el informe es lo que va a pasar. Y si algo falla a mitad, se revierte
todo: nunca queda a medias.

### Las reglas que evitan sorpresas

| Regla | Por qué |
|---|---|
| Todo lo importado pasa al **workspace del admin que importa** | Si no, estaría en la base pero invisible (ver arriba) |
| **Las contraseñas no viajan** | Ver la sección siguiente |
| Una importación **nunca crea administradores** ni superadmins | Un archivo no debe poder darse permisos |
| Correo repetido con otra identidad → **se vincula**, no se duplica ni se pisa su contraseña | Es la misma persona creada a mano en las dos instalaciones |
| Si el campeonato local **ya tiene llaves activas o terminadas**, importar exige confirmación explícita | El evento arrancó: importar a ciegas podría pisar resultados |
| **Una llave ya disputada NUNCA se sobrescribe ni se borra**, ni con confirmación, ni en modo reemplazar | Es la invariante dura: **ninguna importación destruye resultados** |
| Modo **fusionar** (por defecto) no borra nada; **reemplazar** solo toca inscripciones y llaves *pendientes* del campeonato | Los competidores y usuarios viven fuera del campeonato |

### Sobre las contraseñas (decisión: no viajan)

No son necesarias y el riesgo no compensa:

- Los jueces entran con el **QR de su tatami** (`/acceso`), que no pide usuario
  ni contraseña. Es el flujo para el que está diseñado el sistema.
- Si alguien necesita entrar con clave, el admin se la asigna en 5 segundos
  desde Usuarios.
- Un archivo que viaja en una USB con los hashes de todas las cuentas de la
  organización es una responsabilidad sin ninguna ventaja a cambio.

Los usuarios importados se crean con una contraseña aleatoria que nadie conoce
(cuenta válida, sin acceso por clave). El informe de importación lo dice
explícitamente.

### El viaje de vuelta (decisión: solo podios)

La vuelta LOCAL → ONLINE sigue usando el mecanismo que ya existía
(`api/resultados.py` + modelo `ResultadoPublicado`): viajan los **podios y
rankings**, que es lo que consulta el público. Los combates completos no se
suben, así que los reportes en Excel/PDF se generan **en el software local**,
que es donde está el detalle.

Si en el futuro se quisieran reportes también en el online, habría que añadir
`combates` al paquete de vuelta; el formato ya está preparado para ello.

---

## Alternativas evaluadas y descartadas

| Opción | Veredicto |
|---|---|
| **Sync automático por HTTP** cuando haya internet | **Pendiente, como mejora futura.** Reutilizaría el mismo paquete (un botón «Sincronizar ahora» que hace POST del mismo JSON). No como mecanismo principal: la red del polideportivo no es fiable y un sync a medias es peor que un archivo en USB. |
| **Replicación de base de datos** (litestream, réplica lógica de PostgreSQL) | **No.** Exige conexión estable y claves compartidas; justo lo que no hay. |
| **Migrar todas las claves primarias a UUID** | **No.** Sería lo correcto en un diseño nuevo, pero es tocar 9 modelos, todas sus referencias, los sockets y el frontend. La columna `uid` en paralelo da el 95 % del beneficio con el 5 % del riesgo. |
| **Copiar el archivo SQLite entero** | **No.** Destruye lo que haya en destino y no sirve contra el PostgreSQL online. Como respaldo ya existe `app/respaldos.py`. |

---

## Dónde está cada cosa

| Pieza | Archivo |
|---|---|
| Identidad estable entre instalaciones | `backend/app/uid.py` |
| Columnas nuevas en bases existentes | `backend/app/schema_compat.py` |
| Exportar / importar (el motor) | `backend/app/api/sincronizacion.py` |
| Publicar resultados (viaje de vuelta) | `backend/app/api/resultados.py` |
| Tests del traspaso entre dos instancias | `backend/tests/test_sincronizacion.py` |
| Panel de importación (interfaz) | `frontend/src/components/ImportarPaquetePanel.tsx` |
| Llamadas del cliente | `frontend/src/lib/api.ts` (sección «Sincronización») |
