# B3 · Lo que puede salir mal, y lo que no se toca

> **La decisión, tomada el 29 de agosto de 2026:** se hace **B3 — identidad
> única**. El paquete de vuelta (que las altas del día del evento regresen a la
> VPS) queda aplazado.
>
> Este documento no discute esa decisión: la acompaña. Recoge lo que **no va a
> tener solución**, lo que hay que **prevenir a toda costa**, cómo se van a ver
> las averías cuando lleguen, y **cuándo hay que parar**.
>
> Lo que hay que hacer está en `PLAN-ECOSYSTEM-VPS.md` §4. Esto es lo otro.

---

# 1 · Lo que NO va a tener solución

Cuatro cosas que hay que aceptar antes de escribir la primera línea. Ninguna se
arregla con más trabajo: son consecuencias del diseño, y el error caro sería
descubrirlas el 9 de octubre creyendo que había una salida.

## 1.1 · Pasarse a local a mitad de campeonato es imposible

Da igual si se hace B3 o no. **No es un límite de la identidad, es un límite de
lo que viaja.** Tres razones, y la tercera lo cierra:

- **El paquete no lleva los combates.** `exportar_campeonato()` exporta
  campeonato, tatamis, usuarios, asignaciones, competidores, inscripciones y
  llaves. `combates` y `eventos_combate` **no están**. Te llevarías las llaves
  como estaban, sin nada de lo peleado desde la exportación.
- **El estado vivo del tatami vive en un JSON en el servidor.**
  `_persistir_estados()` (`sockets/combate_ns.py`) lo escribe a disco, fuera de
  la base y fuera del paquete: el marcador en curso, el combate actual, el reloj
  y las propuestas de los jueces pendientes de mesa (`propuestas_local`).
- **Sin internet no puedes ni exportar.** La exportación es una llamada HTTP a
  la VPS. Si se fue la red, el mecanismo que te rescataría necesita justo lo que
  acaba de fallar.

> **La única mitigación es no estar nunca en esa situación: el campeonato corre
> en LOCAL desde el minuto uno.** La VPS es donde los maestros inscriben antes y
> donde el público ve resultados después. Durante el evento puede estar apagada.
>
> **El local no es el plan B: es el plan A.** Esto no cambia con B3, y B3 no
> puede debilitarlo.

## 1.2 · Dos personas creadas sin red en dos sitios son dos identidades

Si alguien se crea en el local durante el evento y esa misma persona se crea en
la VPS el mismo día, salen dos filas con dos `uid` distintos para un solo ser
humano. **Ningún emparejamiento automático lo resuelve bien**: el correo puede
faltar, el documento puede faltar, y los nombres se escriben de veinte maneras.

El sistema puede **proponer** coincidencias —por documento, por nombre + club,
por fecha de nacimiento— pero **confirma una persona**. Automatizarlo genera
identidades duplicadas, que es exactamente el problema que B3 existe para
eliminar.

## 1.3 · Una sesión revocada sigue entrando en Campeonatos hasta 30 minutos

No es un fallo: es el precio del diseño. Campeonatos verifica la **firma** del
token contra el JWKS **sin preguntarle a nadie** — eso es lo que le permite
funcionar aunque el ecosystem esté lento o caído. La consecuencia es que cerrar
una sesión en el portal no la corta aquí hasta que el pase caduque.

Por eso `JWT_EXPIRES_IN` **solo puede acortar**: un valor mayor a 30 minutos se
ignora. Está documentado en `OPERAR.md` §4.11 del monorepo.

## 1.4 · Sin internet no existe el ecosystem, y punto

En modo local no hay recuperación de contraseña, ni cuentas nuevas, ni
invitaciones, ni «una cuenta para todo». El local vive con **su propio
administrador** y con el **QR de los tatamis**. Es suficiente para correr un
campeonato entero — pero hay que saber que la promesa del producto se suspende
esos tres días, a propósito.

---

# 2 · Lo que hay que prevenir a toda costa

Estas ocho no se negocian. Cada una tiene detrás una avería concreta.

`[ ]` **1 · El modo local tiene que arrancar con `ECOSYSTEM_JWKS_URL` vacía y
      caer a su login propio.** Se comprueba **desconectando el cable de red**,
      no leyendo el código. Si esto falla, el día del campeonato la app le pide
      permiso a un servidor que no puede alcanzar, y no hay evento.

`[ ]` **2 · El QR de los jueces no se toca.** `/acceso` no pide usuario ni
      contraseña, y es lo que hace que el evento no dependa de nadie. El bloque
      donde más fácil se rompe es **C2 (guards)**: al sustituir `@jwt_required()`
      por `@requiere_scope`, la ruta del QR se cuela en el barrido si nadie la
      excluye a propósito.

`[ ]` **3 · `competidores` no se toca, y un competidor NO necesita cuenta.**
      `nombre_completo` es el único campo obligatorio del modelo; `documento`,
      `cinturon`, `peso` y `fecha_nacimiento` son opcionales, y **`club` es una
      columna de texto libre — no existe tabla `Club`**. Así se inscribe al
      alumno que se olvidó, al que llegó a última hora y al club invitado que no
      está en DINAMYT. B3 opera sobre `usuarios` (cuentas), que es otra tabla.

`[ ]` **4 · No migrar `usuarios.id` de entero a UUID.** Hay **10 claves foráneas**
      contra esa columna y el aislamiento por workspace también es entero. El
      diseño aprobado conserva el `id` y **añade** `eco_sub`: `usuarios` pasa a
      ser un espejo local de la cuenta del ecosystem. Mismo resultado, una
      fracción del riesgo.

`[ ]` **5 · Los diez días de reposo (B3s) no son opcionales.** Del 20 al 30 de
      septiembre, con gente usándolo de verdad. Un despliegue sin reposo no es un
      despliegue terminado.

`[ ]` **6 · Ni un despliegue entre el 1 y el 13 de octubre.** Snapshot del VPS el
      día 8.

`[ ]` **7 · El login local no es «legacy»: es un modo de primera.** El riesgo
      real de B3 a largo plazo es que la ruta offline se convierta en un camino
      de segunda que nadie ejercita — y un camino que solo corre en la emergencia
      se pudre en silencio, hasta el día de la emergencia. **Se prueba en cada
      simulacro, con el cable desconectado, sin excepción.**

`[ ]` **8 · Antes de C4, toda organización que use Campeonatos necesita
      suscripción activa que lo incluya — y la herencia escrita.** Hoy el login
      propio de Campeonatos **disimula el hueco**: los maestros entran directo a
      `campeonatos.dinamyt.org` sin pasar por el portal. **C4 quita ese login**, y
      a partir de ahí la única puerta es el salto desde el portal — que solo
      muestra lo que la suscripción permite.

      Descubierto el 29 de agosto al mirar por qué a un maestro no le salía el
      botón de Campeonatos. El estado real ese día: **de 11 organizaciones, una
      sola tenía suscripción**, y su plan era `Plan Membresías`, que no incluye
      `campeonatos`. Nadie podía llegar a la app desde el portal.

      Y hay una segunda mitad, peor: **la suscripción no se hereda.** El cálculo
      de `app_scopes` une `org_members → subscriptions` por el **mismo** `org_id` y
      no mira `parent_id`. Así que poner el plan en la organización que contrata
      **no se lo da a sus clubes afiliados**. Es el bloque 9 de §4.1 del plan.

      **Si C4 llega antes que esto, los maestros se quedan fuera de su propio
      campeonato** — y se descubre cuando vayan a inscribir.

---

# 3 · Las averías probables, y cómo se van a ver

El patrón que las une: **ninguna se parece a su causa.** Escritas aquí para
reconocerlas en caliente en vez de investigarlas desde cero.

| Se verá como… | Será | Dónde mirar |
|---|---|---|
| **Gente expulsada a mitad de combate**, sin tocar nada | El pase dura 30 min y el frontend dejó de renovarlo contra `/auth/refresh` | **C6** · `frontend/src/lib/auth.tsx` |
| **Un tatami que se queda mudo**: el marcador no avanza y no hay error en pantalla | Socket.IO reconectó con un token vencido y el handshake lo rechazó en silencio | **C5** · `sockets/combate_ns.py` |
| **Un juez entra y ve la pantalla de espectador** | El mapeo de roles no cuadró: `juez → judge`, `maestro → coach`, `admin → admin` | **C7** |
| **La misma persona aparece dos veces** en el listado | El espejo creó fila nueva en vez de enlazar: el correo llegó distinto y no se probó la clave natural | **C3** · alta/enlace por `eco_sub` → correo → crear |
| **Una ruta que antes iba y ahora da 401**, o al revés: una que debía estar protegida y quedó abierta | Son **85 puntos de llamada en 13 archivos**. Falta uno, o sobra uno | **C2** |
| **El local pide iniciar sesión y no deja** | Arrancó creyendo que hay ecosystem. `ECOSYSTEM_JWKS_URL` no estaba vacía, o el fallback no se probó | **C1** |

> **La comprobación que no miente**, para cualquiera de estas: probar el camino
> **desconectado de la red**, no leyendo el código ni confiando en que el
> comando salió sin error.

---

# 4 · Cosas a tener en cuenta antes de empezar

**Las cifras del terreno** (medidas sobre el repositorio, no estimadas):

| | |
|---|---|
| Usos de `jwt_required` / `get_jwt_identity` | **85**, repartidos en **13 archivos** |
| Archivos del frontend que tocan el token | **11** de 59 |
| `sockets/combate_ns.py` | 1.685 líneas — es el combate en vivo |
| `api/auth.py` | 594 líneas — se vacía casi entera |
| Claves foráneas contra `usuarios.id` | 10 — **se conservan**, vía espejo |

**Cuatro detalles que muerden si se olvidan:**

- **Un solo worker, siempre.** El estado de los tatamis, los rooms de Socket.IO
  y el limitador de intentos viven en la memoria del proceso. `-w 1` no es una
  preferencia (`wsgi.py`).
- **El snapshot del tatami es un archivo local.** Si el proceso cambia de
  máquina, el estado se queda atrás. Sobrevive a un reinicio, no a una mudanza.
- **`schema_compat.py` añade columnas al arrancar**, sin migraciones de Alembic.
  Es el mecanismo para meter `eco_sub` sin tocar el diario de migraciones — y es
  también el que ya tiró el servicio una vez: cualquier DDL al arrancar necesita
  su `SET LOCAL lock_timeout` (ver `OPERAR.md` §5.1-ter).
- **Lo que NO se toca**, escrito para poder señalarlo: campeonatos, categorías,
  competidores, llaves, tatamis, combate en vivo y puntuación, resultados,
  reportes, seeds, importación por Excel, exportaciones PDF/Excel/ZIP, el modo
  local y las ~1.950 líneas de i18n. **El choque es solo de identidad.**

---

# 5 · Cuándo hay que parar

Tres señales de aborto. No son sugerencias: si se cumple una, se ejecuta.

`[ ]` **El 19 de septiembre, C1–C5 no están terminadas.** → B3 se aplaza al 14 de
      octubre. Es la regla 2 del calendario del plan maestro, literal: *«sin
      discusión»*. Las apps funcionan perfectamente con sus logins actuales.

`[ ]` **El modo local falla con el cable desconectado, en cualquier momento.** →
      Se para todo lo demás y se arregla eso primero. Es la marcha atrás del
      evento entero; sin ella no hay nada que desplegar.

`[ ]` **El simulacro D-7 (2 de octubre) no sale limpio.** → Se vuelve al estado
      anterior con el tag `archivo/antes-de-actualizar-apps` y el campeonato
      corre con la identidad vieja. Un campeonato con la identidad a medias es
      peor que un campeonato sin B3.

---

# 6 · Lo que queda sin hacer por elegir B3

Escrito aquí para que sea una decisión y no un olvido.

**Las altas del día del evento no regresan a la VPS.** Hoy del local solo vuelven
los podios y los rankings. Quien se inscriba en la puerta el 9 de octubre
competirá, ganará su medalla y **esa persona no existirá en la VPS** cuando todo
vuelva a la normalidad.

- **Se puede vivir con ello**: el detalle completo queda en la carpeta
  `instance/` del PC del evento, y las altas se pasan a mano después.
- **Lo que hay que hacer sí o sí**: guardar esa carpeta en dos sitios distintos
  al terminar (ya está en el anexo de contingencia, §3.2). Es la única copia de
  quién compitió.
- **Cuándo se cierra de verdad**: después del 14 de octubre, junto con el resto
  de la fase 2. El diseño está descrito en `CONTINGENCIA-CAMPEONATO.md`, en el
  apartado del traspaso de propiedad.

---

**Escrito el 29 de agosto de 2026.** Se actualiza cuando alguna de las casillas
de §2 se cierre, o cuando una avería de §3 ocurra de verdad — entonces pasa a
`OPERAR.md`, parte 5, con el relato completo.
