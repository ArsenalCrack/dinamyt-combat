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

## Características

- **Roles diferenciados**: administrador y juez central, con autenticación JWT.
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

## Despliegue gratuito en internet

El proyecto se despliega completo usando solo planes gratuitos
(tiempo estimado: 30–45 min).

| Pieza                         | Herramienta                            | Costo  |
| ----------------------------- | -------------------------------------- | ------ |
| Frontend (Next.js)            | [Vercel](https://vercel.com)           | Gratis |
| Backend (Flask + Socket.IO)   | [Render](https://render.com)           | Gratis |
| Base de datos (PostgreSQL)    | [Supabase](https://supabase.com)       | Gratis |
| Mantener el backend despierto | [UptimeRobot](https://uptimerobot.com) | Gratis |

### 0. Generar los secretos (en tu PC)

Genera un `JWT_SECRET_KEY` **exclusivo para producción**:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Elige también una `ADMIN_PASSWORD` fuerte (12+ caracteres, con números y símbolos).

> El backend **se niega a arrancar** en producción si `JWT_SECRET_KEY` o
> `ADMIN_PASSWORD` son débiles o vacíos (ver `app/__init__.py`).

### 1. Base de datos — Supabase

Crea un proyecto en <https://supabase.com>, copia la **connection string** y úsala
como `DATABASE_URL`. No la subas a git. (Se usa Postgres gestionado en vez de
SQLite porque el disco de Render gratis se borra en cada reinicio; ahí los datos
persisten.)

### 2. Backend — Render

**New → Web Service**, conecta el repo `DINAMYT-COMBAT` y configura:

| Campo             | Valor                                                 |
| ----------------- | ----------------------------------------------------- |
| Root Directory    | `backend`                                             |
| Build Command     | `pip install -r requirements.txt`                     |
| **Start Command** | `gunicorn -k eventlet -w 1 -b 0.0.0.0:$PORT wsgi:app` |
| Instance Type     | Free                                                  |

Variables de entorno:

| Variable         | Valor                                                                                       |
| ---------------- | ------------------------------------------------------------------------------------------- |
| `PYTHON_VERSION` | `3.11.9` ⚠️ NO usar 3.12+: el monkey-patching de eventlet se rompe y toda consulta da 500    |
| `FLASK_ENV`      | `production`                                                                                 |
| `DATABASE_URL`   | connection string de Supabase                                                                    |
| `JWT_SECRET_KEY` | el secreto generado en el paso 0                                                             |
| `ADMIN_EMAIL`    | `admin@dinamyt.org`                                                                          |
| `ADMIN_PASSWORD` | tu contraseña fuerte                                                                         |
| `ADMIN_NOMBRE`   | `Administrador DINAMYT`                                                                      |
| `FRONTEND_URL`   | tu URL de Vercel (temporalmente `http://localhost:3000`)                                     |
| `COOKIE_SECURE`  | `true` (la sesión viaja por HTTPS)                                                           |
| `COOKIE_SAMESITE`| `Lax` — **no** `None`: la web llama a la API por su propio dominio (ver paso 3)              |
| `TRUST_PROXY_HOPS` | `2` — el navegador pide a Vercel y Vercel reenvía a Render, así que hay dos saltos         |
| `TZ`             | `America/Bogota` — zona del evento. Es el valor por defecto, así que solo hace falta ponerla para un campeonato en otro huso (`America/Caracas`, `Europe/Madrid`…) |

> **Sobre las horas.** Los timestamps se guardan y viajan en UTC, y cada
> dispositivo los muestra en SU hora: eso no depende de `TZ`. La variable
> decide la hora que va **impresa** en las actas y los reportes PDF/Excel, que
> no la convierte ningún navegador y tiene que ser la del sitio donde se
> compite. Ver `app/timeutil.py`.

Verifica que responde abriendo
`https://<tu-backend>.onrender.com/api/campeonatos/publico`.

### 3. Frontend — Vercel

**Add New → Project**, importa el repo con **Root Directory** `frontend` y agrega:

| Variable                 | Valor                               |
| ------------------------ | ----------------------------------- |
| `BACKEND_URL`            | `https://<tu-backend>.onrender.com` |
| `NEXT_PUBLIC_SOCKET_URL` | `https://<tu-backend>.onrender.com` |

Con `BACKEND_URL` definida, el navegador llama a `/api` en el dominio de Vercel
y Next reenvía a Render por detrás. Eso es lo que mantiene la cookie de sesión
como de primera parte: si el navegador fuera directo a Render, la cookie sería
de terceros, Safari la bloquearía y **la sesión se perdería en cada recarga**.
Se activa solo, no hay que indicarlo aparte.

`NEXT_PUBLIC_API_URL` ya no hace falta y se ignora cuando el proxy está
configurado. Para forzar el modo antiguo: `NEXT_PUBLIC_API_MODE=directo`.

`NEXT_PUBLIC_SOCKET_URL` sí va directo a Render: el tiempo real usa un token en
el `auth` del socket, no la cookie, y así conserva el WebSocket real (los
rewrites de Vercel no lo soportan y lo degradarían a long-polling).

### 4. Conectar las dos partes (CORS)

En Render, cambia `FRONTEND_URL` por tu URL de Vercel (exacta, con `https://` y
sin `/` final). Acepta varios orígenes separados por coma.

### 5. Mantener el backend despierto

El plan gratis de Render apaga el servicio tras 15 min sin tráfico. Crea un
monitor HTTP en <https://uptimerobot.com> apuntando a
`https://<tu-backend>.onrender.com/api/campeonatos/publico` cada 5 minutos.

### 6. Row Level Security (opcional)

El aislamiento entre workspaces lo hace la aplicación (`api/scoping.py` filtra
por `created_by`). Encima de eso, con PostgreSQL el backend intenta activar
políticas de RLS al arrancar: si algún día una consulta nueva se olvida del
filtro, la base devuelve cero filas en vez de las de otro admin.

**Es una capa extra y puede fallar sin consecuencias.** Si en el log de Render
ves algo así:

```
[SEGURIDAD] RLS incompleto: 0 sentencias aplicadas, 26 fallidas.
           · ALTER TABLE usuarios ENABLE ROW LEVEL SECURITY -> must be owner of table usuarios
```

significa que el rol con el que se conecta el backend no es dueño de las
tablas — pasa cuando la base la creó otro usuario. El backend **arranca igual**
y el aislamiento por workspace sigue funcionando; solo falta la red de abajo.

Para activarla, conéctate a la base con el rol dueño de las tablas (en Supabase,
el rol `postgres`) y ejecuta una vez:

```bash
flask rls
```

O transfiere la propiedad al rol de la aplicación:
`ALTER TABLE usuarios OWNER TO <rol>;` (y lo mismo para `campeonatos`,
`competidores`, `inscripciones`, `llaves` y `resultados_publicados`).

Ojo: RLS tampoco protege si el rol es `SUPERUSER` o tiene `BYPASSRLS`, porque
se salta todas las políticas. El backend lo comprueba y lo dice al arrancar.

### Actualizar lo ya desplegado

```powershell
git add .
git commit -m "descripcion del cambio"
git push
```

Render y Vercel detectan el push y se redespliegan solos (~3–5 min).

---

## Solución de problemas

| Síntoma                                         | Causa probable                           | Solución                                                              |
| ----------------------------------------------- | ---------------------------------------- | --------------------------------------------------------------------- |
| "Error de conexión con el servidor" en el login | Backend dormido o caído                  | Espera 1 min (despierta) o revisa logs en Render                      |
| Errores CORS en la consola del navegador        | `FRONTEND_URL` mal puesta                | Debe ser EXACTAMENTE tu URL de Vercel, con `https://` y sin `/` final |
| El deploy del backend falla con "[SEGURIDAD]"   | Secretos débiles                         | Pon `JWT_SECRET_KEY` y `ADMIN_PASSWORD` fuertes en Render             |
| Pantalla pública no actualiza en vivo           | `NEXT_PUBLIC_SOCKET_URL` mal puesta      | Debe apuntar a la URL de Render, luego redeploy en Vercel             |
| Cambié variables en Vercel y no aplica          | Las `NEXT_PUBLIC_*` se inyectan en build | Redeploy en Vercel después de cambiarlas                              |
