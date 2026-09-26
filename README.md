# DINAMYT — Sistema de campeonatos de combate y figuras

DINAMYT es una plataforma web para **gestionar y puntuar campeonatos de hapkido
en vivo**. Permite a un administrador organizar el evento (campeonatos, tatamis,
categorías, llaves y asignación de jueces) y a los jueces centrales puntuar
combates y figuras en tiempo real, mientras el público sigue el marcador en una
pantalla proyectada en TV.

Está pensada para usarse en polideportivos con **internet intermitente**: incluye
un modo sin conexión que permite a cada juez seguir registrando localmente y un
tablero local que el Juez Central proyecta aunque se caiga la red.

---

> **Campeonatos es una de las cuatro webs de DINAMYT**, no una aplicación
> suelta. Desde el 30 de agosto de 2026 se entra con la cuenta del ecosistema
> —sin segunda contraseña— y el pase RS256 se verifica contra el JWKS del
> portal. El manual de operación de todo el ecosistema, y el de esta app dentro
> de él, es `OPERAR.md` del monorepo `dinamyt` (§4.13 para el salto desde
> DINAMYT). Lo que está por hacer, en `HOJA-DE-RUTA.md` del mismo monorepo.

---

## Características

- **Cuatro papeles**: `admin` (organiza el evento), `maestro` (inscribe a sus
  alumnos), `juez` (puntúa combates y figuras) y `competidor`, más el
  super-admin, que ve todos los workspaces. **Una persona puede tener varios a
  la vez** (`usuarios.roles`): `rol` es el
  principal y decide a qué pantalla entra; `puede_juzgar` sigue existiendo, y
  lo escribe la lista.
- **El panel del competidor** (`/mi-panel`, F3): quien solo compite entra con
  su cuenta de DINAMYT y ve sus inscripciones, sus próximos campeonatos, sus
  resultados y sus números. La ficha de atleta se enlaza a la cuenta por
  `competidores.eco_sub` —la reclama la persona con documento y fecha de
  nacimiento, o la enlaza el administrador—, y todo sale de `/api/mi/*`, que
  filtra siempre por la cuenta de la sesión.
- **Identidad del ecosistema**: `usuarios.eco_sub` guarda la cuenta de DINAMYT y
  la fila local es su ESPEJO (`app/espejo.py`). El login propio **no se retira**:
  es la marcha atrás del día del evento, sin internet.
- **Tiempo real** vía Socket.IO (namespace `/combate`): el marcador del juez se
  refleja al instante en la pantalla pública y demás dispositivos.
- **Dos modalidades**:
  - **Combate** — motor de puntuación con marcador en vivo.
  - **Figuras** — evaluación por jueces con podio automático.
- **Gestión completa** de campeonatos, hasta **10 tatamis**, categorías canónicas,
  llaves (modelo unificado: `pendiente` / `activa` / `terminada`) y asignación de
  hasta 4 jueces.
- **Competidores**: alta manual e **importación masiva por Excel**, con
  generación de llaves a partir del listado.
- **Ingreso por QR** (`/acceso`): el administrador genera un código y el juez
  entra directo a su rol en el tatami, sin escribir usuario ni contraseña.
- **Multi-idioma (i18n)**: la interfaz cambia de idioma en vivo.
- **Pantalla pública** para TV: elige campeonato y tatami y muestra el marcador.
- **Resultados públicos** (`/resultados`): consulta y búsqueda de resultados por
  campeonato.
- **Modo local de contingencia** (`/local`): cada juez de esquina registra 100 %
  en su dispositivo, sin servidor ni conexión; las anotaciones sobreviven a
  recargas y se reingresan al volver la red.
- **Reportes** exportables a **Excel y PDF** (openpyxl + reportlab).
- **Traspaso entre la instalación de internet y la local**: un paquete `.json`
  auto-contenido lleva el campeonato completo (usuarios, competidores,
  inscripciones, tatamis, asignaciones y llaves) de una instalación a la otra,
  con vista previa antes de escribir nada. Ver
  [PLAN-SINCRONIZACION-LOCAL-ONLINE.md](PLAN-SINCRONIZACION-LOCAL-ONLINE.md).

---

## Arquitectura

```
DINAMYT-COMBAT/
├── backend/          API REST + Socket.IO (Flask)
│   └── app/
│       ├── api/        Endpoints REST (auth, campeonatos, categorias,
│       │               tatamis, llaves, combates, reportes, sincronizacion)
│       ├── sockets/    Namespace de tiempo real (/combate)
│       ├── engine/     Motores de puntuación (combate y figuras)
│       ├── models/     Modelos SQLAlchemy (usuario, campeonato, categoria,
│       │               tatami, asignacion, combate, llave)
│       ├── seeds/      Datos iniciales (categorías, admin)
│       ├── identidad.py  Verifica el pase RS256 del ecosistema (JWKS)
│       ├── espejo.py     La fila local como espejo de la cuenta de DINAMYT,
│       │                 y el puente de apariencia (tema e idioma)
│       ├── rls.py        Row Level Security en PostgreSQL
│       ├── schema_compat.py  Crea al arrancar las columnas que falten
│       ├── mantenimiento.py  El modo mantenimiento
│       ├── respaldos.py  Copias de seguridad
│       ├── uid.py      Identidad estable entre instalaciones (local ↔ online)
│       └── config.py   Configuración por entorno
└── frontend/         Aplicación web (Next.js)
    └── src/app/        Rutas: /login, /admin, /juez, /tatami,
                        /pantalla (pública), /tablero (local del JC)
```

### Stack

| Capa         | Tecnología                                                        |
| ------------ | ----------------------------------------------------------------- |
| Frontend     | Next.js 16, React 19, TypeScript, Tailwind CSS 4, socket.io-client |
| Backend      | Flask 3, Flask-SocketIO, Flask-SQLAlchemy, Flask-JWT-Extended      |
| Base de datos | PostgreSQL en producción · SQLite en local                       |
| Reportes     | openpyxl (Excel) · reportlab (PDF)                                 |
| Tiempo real  | Socket.IO sobre eventlet (gunicorn, 1 worker)                     |

> ⚠️ **Un solo worker (`-w 1`) es obligatorio**: el estado en vivo de los tatamis
> vive en memoria del proceso. Por diseño no hay escalado multiproceso
> (6 tatamis ≈ 80 conexiones, que un proceso único maneja de sobra).

---

## Desarrollo local

### Requisitos

- Python 3.11+ (en local se usa SQLite, sin necesidad de PostgreSQL)
- Node.js 18+

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows  (source venv/bin/activate en Linux/macOS)
pip install -r requirements.txt
copy .env.example .env          # crea tu .env y ajusta los valores
python run.py
```

El backend levanta:

- API REST en `http://localhost:5000`
- Socket.IO en `http://localhost:5000/combate`

En modo `development` crea las tablas y ejecuta los seeds (categorías + admin)
automáticamente.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Abre `http://localhost:3000`. Configura el `.env.local` con:

```
NEXT_PUBLIC_API_URL=http://localhost:5000
NEXT_PUBLIC_SOCKET_URL=http://localhost:5000
```

---

## Despliegue

**Producción vive en un VPS**: `/srv/campeonatos`, servicios `systemd`
(`campeonatos-api` y `campeonatos-web`), PostgreSQL en la misma máquina y Caddy
delante, junto a las otras webs del ecosistema en `campeonatos.dinamyt.org`.

| Para… | Ir a (monorepo `dinamyt`) |
|---|---|
| Montar el servidor desde cero | `MONTAR-VPS.md` |
| Desplegar un cambio | `OPERAR.md` §2.4-bis |
| Las variables que parecen opcionales y no lo son | `OPERAR.md` §1.4 |
| El PC del evento, sin internet | [INICIAR-LOCAL.md](INICIAR-LOCAL.md) |

```bash
cd /srv/campeonatos && git pull && backend/venv/bin/pip install -r backend/requirements.txt && cd frontend && npm ci && npm run build && sudo systemctl restart campeonatos-api campeonatos-web
```

Campeonatos **no migra**: crea lo que le falta al arrancar (`schema_compat`).

### Row Level Security

El aislamiento entre workspaces lo hace la aplicación (`api/scoping.py` filtra
por `created_by`). Encima de eso, con PostgreSQL el backend activa políticas de
RLS al arrancar: si algún día una consulta nueva se olvida del filtro, la base
devuelve cero filas en vez de las de otro admin.

Si el log dice `[SEGURIDAD] RLS incompleto: … must be owner of table …`, el rol
con el que se conecta el backend no es dueño de las tablas. El backend **arranca
igual** y el aislamiento por workspace sigue funcionando; solo falta la red de
abajo. Para activarla, con el rol dueño de las tablas, una vez:

```bash
flask rls
```

O transfiere la propiedad al rol de la aplicación:
`ALTER TABLE usuarios OWNER TO <rol>;` (y lo mismo para `campeonatos`,
`competidores`, `inscripciones`, `llaves` y `resultados_publicados`).

RLS no protege si el rol es `SUPERUSER` o tiene `BYPASSRLS`: el backend lo
comprueba y lo dice al arrancar. Las pruebas contra PostgreSQL de verdad están
en `backend/tests/test_rls_postgres.py` (se saltan sin `CAMPEONATOS_PG_URL`).
