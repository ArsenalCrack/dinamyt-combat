> **SUPERADO por [`PLAN-ECOSYSTEM-VPS.md`](PLAN-ECOSYSTEM-VPS.md).** El diseño de
> identidad de aquí (migrar `usuarios.id` a UUID) se descartó: hoy son 8 claves
> foráneas contra `usuarios.id` y no 3, y el RLS por workspace también es entero.
> El plan nuevo usa una tabla espejo. Se conserva por el inventario de funciones
> del competidor (Fase B), que sigue vigente.

# Plan de integración: DINAMYT-LOCAL → ecosystem DINAMYT

> Objetivo: que **dinamyt-local** (esta app: Flask + Next, autónoma de campeonatos de
> hapkido) pase a ser **el campeonatos oficial** del monorepo `dinamyt`, conectado a la
> identidad central (ecosystem), conservando su lógica tal cual y **recuperando las
> funciones que tenía el `campeonatos-*` del monorepo**.

## Decisiones tomadas (2026-07-20)

1. **Reemplazar** las apps `apps/campeonatos-api` (Fastify) y `apps/campeonatos-web` (Next)
   del monorepo por dinamyt-local. dinamyt-local es la versión que se conserva.
2. **Integración total al ecosystem**: el backend Flask **deja de emitir** tokens y pasa a
   **validar** los tokens RS256 del ecosystem contra su JWKS. Una sola cuenta para todo.
3. **Portar todas las funciones del competidor** que el monorepo tenía y local no
   (invitaciones, autoinscripción, revisión, progreso, autorrellenado).
4. **"Progreso" = panel de estadísticas del competidor** (medallas, ganados/perdidos).
5. **Con pagos**: la inscripción lleva `monto_total` y `estado_pago` (PAID/PARTIAL/PENDING).
6. **Correo de invitaciones vía proveedor transaccional** (Resend/SendGrid, con API key).
7. **Inglés obligatorio** en cada pantalla nueva (lo exige el tipo del i18n; ver §Regla i18n).

## Contexto: por qué chocan (y por qué es abordable)

| | dinamyt-local (esta app) | dinamyt (monorepo) |
|---|---|---|
| Backend | Flask / Python | Fastify/Nest + Drizzle |
| Identidad | Propia (tabla `Usuario`, login propio) | **Ecosystem central** (identidad única) |
| Token | Lo **emite** él (HS256) | Solo lo emite el **ecosystem** (RS256); las apps solo **validan** vía JWKS |
| Roles | `admin` / `juez` (+ super) | `role_campeonatos`: admin/maestro/coach/competitor/judge + `app_scopes` |
| Login (front) | Formulario propio | SSO: portal manda `…/login#token=<jwt>` |
| Foco | Admin/juez (el admin registra competidores a mano) | Competidor autogestionado (cada competidor es un usuario del ecosystem) |

El choque real es **solo la identidad/autenticación**. La lógica de campeonatos (llaves,
tatamis, combate, Socket.IO, reportes) queda intacta. El **ecosystem-api no se toca**: ya
expone `GET /auth/jwks` y su token ya incluye `app_scopes`, `role_campeonatos` e
`is_super_admin`.

Contrato del token: `packages/shared/src/auth.ts` (`sub` UUID, `email`, `fullName`,
`org_id`, `app_scopes`, `role_campeonatos`, `is_super_admin`).

---

## FASE A — Integración base (auth + monorepo)

### Bloque 5 · Puertos, URLs, CORS, .env *(primero: seguro y reversible)*
- Frontend local → puerto **3003** (el de campeonatos-web); backend Flask → **3002**
  (el de campeonatos-api). Así el portal ya apunta bien sin cambios.
- Nuevas variables: `ECOSYSTEM_JWKS_URL=http://localhost:3001/auth/jwks`,
  `ECOSYSTEM_PORTAL_URL=http://localhost:3000`.
- Ajustar CORS en `backend/app/config.py` y `backend/app/__init__.py`.
- Alinear ruta de login: el portal enlaza a `/admin/login`; local usa `/login`.

### Bloque 1 · Auth del backend (el corazón)
- Verificador JWKS en Python (equivalente a `createRemoteVerifier` de
  `apps/campeonatos-api/src/plugins/auth.ts`): `PyJWT` + `PyJWKClient`, valida RS256.
- Decoradores nuevos `@requiere_scope("campeonatos")` / `@requiere_rol(...)` que
  reemplazan `@jwt_required()`.
- Reescribir `backend/app/api/scoping.py`: `usuario_actual()` lee los claims del token
  (`sub`, `role_campeonatos`, `is_super_admin`, `org_id`), no la tabla `Usuario`.
- Retirar de `backend/app/api/auth.py`: `login`, `register`, `list_users`, `update_user`,
  `delete_user` (esa gestión vive en el portal). Conservar un `/me` que devuelva claims.
- Quitar la emisión de Flask-JWT-Extended (dejar solo verificación).

### Bloque 2 · Modelo de identidad / BD
La tabla `usuarios` es referenciada por 3 FK `Integer`, pero el ecosystem identifica por UUID:
- `campeonato.created_by` → UUID/`org_id` del ecosystem (`backend/app/models/campeonato.py:24`).
- `competidor.created_by` → igual (`backend/app/models/competidor.py:110`).
- `asignacion.usuario_id` (juez del tatami) → identificar juez por **email/UUID** del
  ecosystem (`backend/app/models/asignacion.py:16`), imitando "tatamis por email del token".
- Migración de tipo de columna; eliminar/vaciar la tabla `usuarios`.
- Mapeo de roles: `admin → admin`, `juez → judge`.

### Bloque 3 · Auth del Socket.IO
- `backend/app/sockets/combate_ns.py:477` usa `decode_token` (Flask-JWT) → cambiar al
  mismo verificador JWKS del Bloque 1. El token sigue viajando en el `auth` del socket.

### Bloque 4 · SSO en el frontend
- La página de login lee `#token=` del fragmento y lo guarda (patrón en
  `apps/campeonatos-web/src/app/admin/login/page.tsx`); adaptar `frontend/src/lib/auth.tsx`.
- Quitar el formulario de login propio; el usuario se autentica en el portal.
- Decodificar el token en cliente para la navegación por rol (como `lib/session.ts` del monorepo).

### Bloque 6 · Monorepo y retiro de lo viejo
- Archivar/eliminar `apps/campeonatos-api` y `apps/campeonatos-web`.
- El **frontend** local entra como app del workspace (misma versión de Next/React).
- El **backend Python NO encaja** en pnpm/turbo: va como carpeta/servicio aparte con su
  propio arranque, no como paquete del workspace.

---

## FASE B — Paridad del competidor (portar features del monorepo)

> Cada bloque de esta fase incluye pantallas nuevas → **claves i18n es + en obligatorias**.

### Fundacional · Ligar Competidor ↔ usuario del ecosystem
Requisito de B7–B11. Hoy `Competidor` no tiene vínculo con el ecosystem.
- Añadir a `Competidor`: `user_sub` (UUID del ecosystem), `email`, `foto_url`.
- Permite resolver "mis inscripciones / mis estadísticas / mis invitaciones" por el token.

### B7 · Autoinscripción + navegación pública
- Backend: inscripción hecha por el propio competidor; adaptar `/publico` para "inscribirme".
- Frontend: páginas `/campeonatos` y `/campeonatos/[id]/inscribirme`.

### B8 · Revisión de inscripciones (con pagos)
- Backend: `Inscripcion` gana `estado` (PENDIENTE/APROBADA/RECHAZADA), `motivo_rechazo`,
  `monto_total`, `estado_pago` (PAID/PARTIAL/PENDING). Endpoint `PATCH /inscripciones/:id/estado`
  que aprueba y auto-asigna a su sección.
- Frontend: pantalla de revisión del admin + estado/pago visible en el panel del competidor.

### B9 · Invitaciones por correo
- Backend: modelo `Invitacion`; endpoints invitar/listar/`mias`/aceptar/rechazar; **envío de
  correo vía Resend/SendGrid** (API key en variables de entorno). **Correo bilingüe** (es/en).
- Frontend: `/invitaciones` (competidor) + panel de invitaciones del admin.

### B10 · Progreso / estadísticas del competidor
- Backend: `/me/estadisticas` (medallas oro/plata/bronce, combates ganados/perdidos/empates,
  campeonatos participados, desglose por campeonato) y `/competidores/mi-perfil`.
- Frontend: `/panel` (mis inscripciones) y `/panel/estadisticas` (progreso).

### B11 · Autorrellenado desde el ecosystem
- Backend: proxys a ecosystem-api (`/users/:id/profile`, `/organizations/clubes`, `/mi-club`)
  usando el token del usuario.
- Frontend: prellenar el formulario de inscripción con documento/nombre/nacimiento/foto/club.

### B12 · (recomendado) Campeonato enriquecido + geo
- Añadir `pais/ciudad/alcance/codigo/esPublico` a `Campeonato` + catálogo geo
  (`/geo/paises`, `/geo/ciudades`). Necesario para que la navegación pública y las
  inscripciones privadas con código tengan sentido.

---

## Regla transversal · i18n (español + inglés)

El i18n local (`frontend/src/lib/i18n.tsx`, ~1950 líneas) usa `Record<ClaveTexto, string>`:
**si una pantalla nueva no tiene sus claves en inglés, el proyecto no compila.** Por tanto:
- Cada bloque de la Fase B añade sus textos como claves en el diccionario `es` **y** `en`.
- El backend ya localiza descargas con `?lang=`; los correos de invitación deben salir
  bilingües bajo el mismo criterio.

## Dependencias externas a preparar
- **Cuenta de correo transaccional** (Resend o SendGrid) + API key → variable de entorno.
- Confirmar acceso del backend Flask al `ecosystem-api` (JWKS en :3001) en local y producción.

## Orden de ejecución sugerido
**Fase A:** Bloque 5 → 1 → 2 → 3 → 4 → 6.
**Fase B:** Fundacional → B7 → B8 → B9 → B10 → B11 → B12.

## Lo que NO se toca (se conserva tal cual)
Toda la lógica de dominio de dinamyt-local: campeonatos, categorías, competidores, llaves/
brackets, tatamis, **combate en vivo por Socket.IO** (que el monorepo no tenía), resultados,
reportes, seeds, importación por Excel, exportaciones PDF/Excel/ZIP, acceso QR de jueces, y
todas las páginas y componentes del frontend existentes.
