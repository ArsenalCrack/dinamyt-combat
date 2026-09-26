# PRUEBAS — lo que hay que probar a mano en Campeonatos

> Escrito el 26 de septiembre de 2026, cuando el plan de Campeonatos (F1–F8)
> quedó escrito y probado en código; F9 espera un campeonato real
> (`HOJA-DE-RUTA.md` del monorepo). Las pruebas automáticas ya pasan
> —Campeonatos contra SQLite y contra PostgreSQL con RLS, ecosistema y
> portal—; esto es lo que **solo una persona puede comprobar**: pantallas,
> correos, celulares y el PC del evento.
>
> **Cuándo:** ya se puede — lo desplegado corre en la VPS desde el 26 sep 2026
> (Campeonatos `9e1d4e1`, monorepo `1277b99`). Es también el guion del
> **ensayo** (`OPERAR.md` §2.9) antes del próximo campeonato.
>
> Marca cada casilla. Si algo no sale como dice «Debe pasar», apunta qué salió
> y en qué pantalla: con eso basta para arreglarlo.

---

## 0 · Antes de empezar

### Las cuentas que hacen falta

| Quién | Qué es en DINAMYT | Para qué |
|---|---|---|
| **SUPER** | Tu cuenta de superadmin | Informe de administradores y traspaso |
| **FEDE** | Admin de una federación de prueba, con plan de Campeonatos | Organiza los campeonatos |
| **FEDE-2** | Segundo admin de la MISMA federación | El traspaso (§4) |
| **MAESTRO** | Maestro de un club afiliado a esa federación | Invitaciones e inscripción |
| **ALUMNA** | Alumna del club de MAESTRO, **con documento, fecha de nacimiento y género** en su perfil | Inscribir desde DINAMYT, su panel |
| **JUEZ** | Lo crea FEDE desde `/admin` (§6) | Tatami y QR |

Usa correos a los que tengas acceso: varias pruebas llegan por correo.

### El despliegue quedó bien

- [x] Las rutas nuevas dan **401 y no 404** *(comprobado el 26 sep 2026)*:
      `curl -s -o /dev/null -w "%{http_code}
" http://127.0.0.1:5000/api/subida/estado`
      (y `/api/mi/panel`), y en el ecosistema `http://127.0.0.1:3001/sync/clubes`
      y `/sync/miembros?maestro=x`. Un 404 en las de `:3001` es que falta
      `ECOSYSTEM_SYNC_SECRET`.
- [x] A los 5 minutos de reiniciar, `NRestarts` de `campeonatos-api` no ha subido
      (`systemctl show campeonatos-api -p NRestarts` → 0, el 26 sep).
- [ ] En el arranque de Campeonatos se lee «pase RS256 y espejo: los dos ENCENDIDOS»
      (`sudo journalctl -u campeonatos-api --since "10 min ago" | grep ecosistema`).

---

## 1 · Papeles: el portal da y el portal quita (F1, F2, D9)

- [ ] En el portal, a MAESTRO márcale **Maestro** y **Juez** en Campeonatos.
      Entra a Campeonatos desde el portal. **Debe pasar:** entra como maestro y
      puede ser asignado a un tatami.
- [ ] En el portal, quítale **Juez**. Sal y vuelve a entrar a Campeonatos.
      **Debe pasar:** ya no es juez (no aparece para asignar a tatamis).
- [ ] Como FEDE, en `/admin`, dale a MAESTRO el permiso de juez **a mano**.
      Quítaselo después en el portal y que vuelva a entrar. **Debe pasar:** lo
      conserva (lo puso la consola, no el portal).
- [ ] Nadie pierde `admin` por un cambio en el portal.

## 2 · El panel del alumno (F3)

- [ ] ALUMNA entra a Campeonatos desde el portal. **Debe pasar:** cae en
      `/mi-panel`, no en la consola.
- [ ] Si tiene una ficha de antes sin enlazar: «Enlazar mi ficha» con
      documento **y** fecha. **Debe pasar:** aparecen sus inscripciones. Con la
      fecha mal cinco veces: queda bloqueado un rato.
- [ ] FEDE enlaza a mano una ficha a una cuenta (ficha del competidor →
      «Enlazar cuenta»).

## 3 · La organización (F4)

- [ ] FEDE ve en la cabecera de `/admin` el nombre de su federación.
- [ ] SUPER ve la tarjeta «Quién administra qué» si hay organizaciones con dos
      admins o admins sin organización. Si no hay nada que decidir, no sale.

## 4 · El traspaso: la organización manda (F4 punto 3, 26 sep)

- [ ] FEDE-2 entra una vez desde el portal. SUPER ve la federación con **dos
      admins** en la tarjeta.
- [ ] «Pasar todo lo de FEDE a FEDE-2» → **Ver qué se mueve**. **Debe pasar:**
      dice cuántos campeonatos, fichas, llaves, resultados, inscripciones y
      usuarios se mueven, y **no cambia nada todavía**.
- [ ] Si hay fichas con el mismo documento en los dos: lo dice y no deja
      traspasar.
- [ ] **Traspasar** → confirmar. **Debe pasar:** FEDE-2 ve todos los
      campeonatos de FEDE **con sus llaves, inscripciones y resultados**; FEDE
      ya no ve nada. Desactiva a FEDE desde la lista de usuarios.

> Hazlo con datos de prueba: el traspaso no se deshace desde la pantalla.

## 5 · Invitaciones y aviso al club (F5, punto 3)

- [ ] FEDE crea un campeonato. En «Clubes invitados» busca el club de MAESTRO en
      el directorio e invítalo. **Debe pasar:** el mensaje dice «Se le avisó en
      DINAMYT».
- [ ] MAESTRO abre el portal. **Debe pasar:** en su campana, «Invitaron a tu club
      a un campeonato · FEDERACIÓN X invitó a tu club a COPA Y». Si tiene el
      push activado, también le llega al celular. Tocarlo lleva al panel.
- [ ] MAESTRO entra a Campeonatos. **Debe pasar:** ve el campeonato, con
      «Organiza: FEDERACIÓN X».
- [ ] FEDE retira la invitación. **Debe pasar:** MAESTRO deja de verlo; lo que
      ya inscribió se queda.
- [ ] Invitar solo por nombre (sin elegir del directorio): **no** abre la puerta a
      un maestro de fuera.

### «Solo clubes invitados»

- [ ] FEDE crea un maestro propio (modo local, o uno que ya tuviera) y un
      campeonato. Sin marcar nada, ese maestro lo ve (la puerta de siempre).
- [ ] Marca **Solo clubes invitados**. **Debe pasar:** ese maestro ya no lo ve.
- [ ] Invita a su club **por nombre**. **Debe pasar:** vuelve a verlo e inscribe.
- [ ] Lo inscrito antes de marcarlo sigue ahí.

## 6 · Inscribir a la gente del club desde DINAMYT (punto 2, 26 sep)

- [ ] MAESTRO (entrado desde el portal) abre el formulario de inscripción.
      **Debe pasar:** aparece «De tu club en DINAMYT» con ALUMNA, su fecha y su
      club. **No** aparece su documento en pantalla.
- [ ] Elige a ALUMNA. **Debe pasar:** nombre, fecha y género vienen rellenos;
      pon cinturón y peso y envía.
- [ ] Como FEDE, mira la ficha nueva. **Debe pasar:** tiene el documento de
      DINAMYT y dice «cuenta enlazada».
- [ ] ALUMNA entra a su panel. **Debe pasar:** ve la inscripción **sin haber
      reclamado nada**.
- [ ] Inscríbela en un segundo campeonato. **Debe pasar:** se reutiliza su ficha
      («con su ficha de siempre»).
- [ ] Un maestro que entró con **contraseña** (no desde el portal) ve la frase
      «Entra con tu cuenta de DINAMYT…» y puede seguir tecleando datos.

## 7 · Alta de jueces en DINAMYT (D8, D10)

- [ ] FEDE en `/admin` → Crear usuario. **Debe pasar:** no pide contraseña, solo
      ofrece «Juez», y explica que la cuenta nace en DINAMYT.
- [ ] Crea a JUEZ. **Debe pasar:** le llega el correo de DINAMYT para poner
      contraseña (o, si el correo no salió, la pantalla enseña el enlace para
      mandarlo por WhatsApp, con «Copiar enlace»).
- [ ] JUEZ pone su contraseña y entra a Campeonatos desde el portal.
- [ ] FEDE edita a JUEZ. **Debe pasar:** no hay campo de contraseña («se cambia
      en DINAMYT»).
- [ ] Si la federación de FEDE fuera un **club**: DINAMYT dice que los jueces
      los agrega la organización. Es lo esperado.

## 8 · El tatami y quién puede puntuar (seguridad, 25–26 sep)

- [ ] FEDE asigna a JUEZ como **Juez 1** de un tatami y le genera el QR. JUEZ lo
      escanea. **Debe pasar:** entra como Juez 1 y puntúa.
- [ ] Con esa misma sesión, cambia en la URL `rol=j1` por `rol=arbitro`.
      **Debe pasar:** «No estás asignado a este tatami con ese papel».
- [ ] Abre `/tatami/N?rol=arbitro` en una ventana privada (sin sesión).
      **Debe pasar:** lleva al login; y el servidor no deja entrar al socket.
- [ ] La pantalla pública (`/tatami/N?rol=pantalla`) funciona sin sesión y se
      actualiza con cada punto.
- [ ] FEDE (dueño) entra como Juez Central de su tatami sin asignación: puede.
- [ ] Un juez que abre el tatami de OTRO campeonato: no entra.

## 9 · El PC del evento (F6-bis, F7, F8)

- [ ] La víspera, con internet: en la VPS, el campeonato → **Exportar paquete**;
      en el PC, **Admin → Campeonatos → Importar campeonato** (`INICIAR-LOCAL.md`
      §2.1). `/admin` dice de cuándo es la copia. Las contraseñas de los jueces
      se ponen aquí, en el PC (en internet ya no se puede: D10; aquí sí).
- [ ] `INICIAR.bat --comprobar`. **Debe pasar:** «Secreto de sesiones: GENERADO
      para este PC» la primera vez (y «propio de este PC» las siguientes). Genera
      los QR de jueces **después** de esto.
- [ ] `INICIAR.bat`: arranca, sale el QR con la dirección, los celulares entran.
- [ ] Sin internet: el login local y los QR funcionan; se compite un combate y
      una categoría de figuras.
- [ ] Con `backend/.env` con `CAMPEONATOS_ONLINE_URL=https://campeonatos.dinamyt.org`
      y `ECOSYSTEM_JWKS_URL=https://id.dinamyt.org/auth/jwks`, al volver la red:
      en **ese mismo PC** abre `http://localhost:3000` → «Entrar con el portal
      DINAMYT». **Debe pasar:** vuelves a Campeonatos local con sesión, y en
      `/admin` sale «N campeonato(s) pendientes de subir» → **Subir ahora**.
- [ ] Desde un celular (por la IP) pulsa «Entrar con el portal DINAMYT».
      **Debe pasar:** un aviso de que solo se puede desde el propio PC.
- [ ] En internet, `/resultados` enseña lo que subió. ALUMNA, en su panel, ve
      su medalla **confirmada** (no «sin confirmar»).
- [ ] Un `CAMPEONATOS_ONLINE_URL` con `http://` a un dominio de fuera: la subida
      queda apagada y el arranque lo dice.

## 10 · Resultados y seguridad

- [ ] En `/resultados` y en su API (`/api/resultados/campeonato/…`) no aparece
      ningún `competidor_uid`.
- [ ] Un admin distinto al organizador intenta **importar** resultados del
      campeonato de otro (con su archivo): 409 con una frase.
- [ ] Inscribe a un competidor con nombre `=HYPERLINK("https://ejemplo.com";"ver")`
      y exporta el Excel del campeonato. **Debe pasar:** en Excel sale como
      texto, no como enlace.

## 11 · La salida de emergencia del tatami

Solo para saber que existe; no se deja puesta.

- [ ] En el PC del evento, `TATAMI_SIN_IDENTIDAD=1` en `backend/.env` y
      reinicia el backend. **Debe pasar:** se puede entrar a puntuar sin sesión
      (como antes del 25 sep). Quítalo y reinicia.
