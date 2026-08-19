> **SUPERADO por [`PLAN-ECOSYSTEM-VPS.md`](PLAN-ECOSYSTEM-VPS.md).** Este documento
> sigue siendo correcto en lo suyo (la mudanza al VPS, el correo, el DNS), pero no
> contempla la cuenta única, el club en el ecosystem, ni el calendario atado al
> campeonato de octubre. Se conserva como referencia. Su copia duplicada
> `PLAN-VPS.md` se eliminó (era idéntica byte a byte).

# Mudanza a VPS + dominio propio + correo

> Guía operativa para sacar **Campeonatos** (este repo) y **Membresías**
> (`dinamyt-membresias`) de Render/Vercel/Neon/Supabase y ponerlos en un solo
> VPS, bajo un dominio propio, con correo que sale solo y con una dirección
> real donde la gente pueda escribir.
>
> **Sin Google Workspace.** El buzón se resuelve con Cloudflare Email Routing
> (gratis) y Gmail «Enviar como», así el correo del proyecto llega a la bandeja
> que ya usas y las respuestas salen con la dirección del proyecto.

Orden sugerido: **día 1** pasos 1–2 (comprar y acomodar el código), **día 2**
pasos 3–7 (servidor y apps), **día 3** paso 8 (correo) y 9–11 (cierre).

---

## 1. Lo que hay que comprar y las cuentas que hay que abrir

| Qué | Dónde | Costo | Notas |
|---|---|---|---|
| Dominio `dinamyt.org` | Cloudflare Registrar | ~US$10/año | `dinamyt.com` está tomado y en reventa; `.org` está libre |
| VPS | Hetzner (Ashburn), Vultr (Miami) o DigitalOcean | US$11–20/mes | Mínimo 4 GB de RAM. Ubuntu 24.04 LTS |
| Cuenta Cloudflare | cloudflare.com | Gratis | DNS + Email Routing |
| Cuenta Resend | resend.com | Gratis | 3.000 correos/mes, **100 al día** |
| Cuenta AWS (para SES) | aws.amazon.com | Gratis + US$0,16 por millar | Opcional pero **pídela desde ya**: la salida del sandbox tarda 24–48 h |
| Almacenamiento de respaldos | Cloudflare R2 o Backblaze B2 | ~US$0,20/mes | 10 GB sobran |
| Monitor | UptimeRobot o Healthchecks | Gratis | Para enterarte tú antes que un juez |

**Región del VPS:** desde Colombia, Miami o Ashburn dan 50–90 ms; Frankfurt da
120–150 ms y eso se nota en el marcador del tatami.

**RAM:** con todo encendido (Postgres + Flask + dos Next + la API de Node) el
consumo en reposo ronda 1,2 GB. El pico es el `next build`, que puede pedir 2 GB
él solo: con 4 GB conviene compilar en tu PC y subir el resultado; con 8 GB
compilas en el servidor sin pensarlo.

**Lo que NO hay que comprar:** subdominios (son registros DNS, gratis e
ilimitados), certificados HTTPS (Let's Encrypt vía Caddy), ni servidor de correo
propio (el puerto 25 saliente viene bloqueado en casi todos los proveedores y la
IP nueva no tiene reputación: los correos caen en spam sin avisar).

---

## 2. Cómo queda el mapa

| Host | Qué vive ahí | Puerto interno |
|---|---|---|
| `dinamyt.org` + `www` | Redirección a Campeonatos | — |
| `campeonatos.dinamyt.org` | Next (este repo) + Flask + Socket.IO | 3000 y 5000 |
| `club.dinamyt.org` | Membresías (web + API) | 3006 y 3004 |
| `send.dinamyt.org` | Lo crea Resend solo, para los rebotes | — |

Direcciones de correo:

| Dirección | Para qué | Por dónde |
|---|---|---|
| `no-reply@dinamyt.org` | Lo que manda el programa | Resend (luego SES) |
| `soporte@dinamyt.org` | Va como `Reply-To`; aquí contesta una persona | Email Routing → tu Gmail |
| `admin@dinamyt.org` | Cuenta de superadmin de las dos apps | Email Routing → tu Gmail |

---

## 3. Lo que hay que acomodar en los programas

Esto va **antes** de tocar el servidor: ninguna de las dos apps necesita cambios
de arquitectura, pero sí de configuración, y hay un par de detalles que si se
olvidan dejan la app arriba y rota (que es peor que caída).

### 3.1 Campeonatos — este repo

**`backend/.env`** (nuevo, en el servidor; no se sube a git):

```bash
FLASK_ENV=production
DATABASE_URL=postgresql://dinamyt:CLAVE@127.0.0.1:5432/dinamyt_campeonatos
JWT_SECRET_KEY=          # python -c "import secrets; print(secrets.token_hex(32))"
ADMIN_EMAIL=admin@dinamyt.org
ADMIN_PASSWORD=          # 12+ caracteres; el backend se niega a arrancar si es débil
ADMIN_NOMBRE=Administrador DINAMYT
FRONTEND_URL=https://campeonatos.dinamyt.org   # exacta, sin barra final
COOKIE_SECURE=true
COOKIE_SAMESITE=Lax
TRUST_PROXY_HOPS=1       # era 2 con Vercel delante; ahora solo hay Caddy
TZ=America/Bogota
```

**`frontend/.env.production`** (nuevo). Ojo: las `NEXT_PUBLIC_*` se hornean en
el build, así que esto tiene que existir **antes** de `npm run build`:

```bash
NEXT_PUBLIC_API_MODE=proxy
NEXT_PUBLIC_SOCKET_URL=https://campeonatos.dinamyt.org
```

`NEXT_PUBLIC_API_MODE=proxy` fuerza rutas relativas `/api`
(`frontend/src/lib/api.ts:26`), que es lo que mantiene la cookie de sesión como
de primera parte. `NEXT_PUBLIC_SOCKET_URL` es obligatoria: sin ella el cliente
arma la URL del socket con el puerto 5000 del mismo host
(`frontend/src/lib/socket.ts:15`) y no encuentra nada, porque ese puerto no está
abierto al exterior.

**Cambio de código (uno solo):** `backend/app/config.py:64` trae
`admin@dinamyt.com` como valor por defecto. Ese dominio es de otra persona —
está registrado y parqueado en venta. Cámbialo a `admin@dinamyt.org`.

**Lo que NO cambia:** `BACKEND_URL` deja de hacer falta (Caddy manda `/api`
directo al Flask), y `wsgi.py`, gunicorn y el resto quedan igual.

### 3.2 Membresías — `dinamyt-membresias`

**`packages/membresias-db/.env`:**

```bash
MEMBRESIAS_DATABASE_URL=postgresql://dinamyt:CLAVE@127.0.0.1:5432/dinamyt_membresias
```

**`apps/membresias-api/.env`:**

```bash
PORT=3004
MEMBRESIAS_DATABASE_URL=postgresql://dinamyt:CLAVE@127.0.0.1:5432/dinamyt_membresias
JWT_SECRET=              # node -e "console.log(require('crypto').randomBytes(48).toString('base64url'))"
JWT_EXPIRES_IN=86400
BCRYPT_ROUNDS=10
SUPERADMIN_EMAIL=admin@dinamyt.org
SUPERADMIN_PASSWORD=
SUPERADMIN_NOMBRE=Super administrador
CORS_ORIGINS=https://club.dinamyt.org
MEMBRESIAS_WEB_URL=https://club.dinamyt.org
TRUST_PROXY_HOPS=1
COOKIE_SAMESITE=lax
COOKIE_SECURE=true
VAPID_PUBLIC_KEY=        # las mismas de Render, no generes nuevas:
VAPID_PRIVATE_KEY=       # si cambian, las suscripciones push existentes mueren
VAPID_SUBJECT=mailto:soporte@dinamyt.org
CRON_SECRET=             # el mismo que ya tienes, o uno nuevo
TZ=America/Bogota
```

**`apps/membresias-web/.env.production`:**

```bash
MEMBRESIAS_API_ORIGIN=http://127.0.0.1:3004
NEXT_PUBLIC_VAPID_PUBLIC_KEY=
```

`MEMBRESIAS_API_ORIGIN` también se lee **al construir** (el rewrite se serializa
dentro del build). Y `CRON_SECRET` ya no hace falta en la web: en el VPS el cron
llama directo a la API.

**Cambios de código:** ninguno obligatorio. Dos cosas quedan inertes y conviene
saberlo para no buscarlas después:

- `apps/membresias-web/vercel.json` — el cron de Vercel deja de existir. La ruta
  `/cron/avisos` de la web sigue ahí, sin usarse; el disparo pasa a ser del
  sistema (paso 10).
- El plan gratuito de Render y su `render.yaml` quedan de referencia histórica.

### 3.3 El módulo de correo — esto sí hay que programarlo

**Hoy ninguna de las dos apps envía un solo correo.** No es que esté a medias:
en Campeonatos no hay ninguna librería de correo en `requirements.txt`, y en
Membresías el estudio está hecho en `CORREO.md` pero sin implementar. La mudanza
no lo trae puesto.

Contrato de variables, igual en las dos, para que cambiar de proveedor sea
cambiar tres líneas:

```bash
SMTP_HOST=smtp.resend.com
SMTP_PORT=587
SMTP_USER=resend
SMTP_PASS=              # la API key de Resend
MAIL_FROM=DINAMYT <no-reply@dinamyt.org>
MAIL_REPLY_TO=soporte@dinamyt.org
MAIL_DAILY_MAX=90       # tope propio, por debajo del del proveedor
```

**Escribe el envío contra SMTP, no contra el SDK del proveedor.** Resend y SES
hablan los dos SMTP; así pasar de uno al otro es cambiar estas variables y nada
más. Y mantén el mismo criterio que ya usan las dos apps con el SSO y el
`CRON_SECRET`: **sin `SMTP_HOST`, la función de correo no existe** — la app
arranca y funciona igual que hoy, en vez de romperse a medias.

Lo que falta programar, en orden de utilidad:

1. **Confirmación de la dirección al crear la cuenta** (las dos apps). Token
   firmado de vida corta, enlace, y una columna de estado. **No bloquea la
   cuenta:** al alumno lo inscribe el maestro con él delante y al competidor lo
   registra el club, así que la confirmación no es una puerta, es un detector de
   dedazos en la dirección. Marca la ficha con una advertencia y deja reenviar.
2. **Aviso de mora por correo** (Membresías). Solo `venc` y `mora`, sin cadencia
   diaria, detrás del tope propio. El aviso de clase **nunca** por correo: es
   diario y para todos, y se come la cuota entera él solo.
3. **Webhook de rebotes.** Un correo que rebota es un correo mal escrito, y esa
   es justo la información que le falta al maestro en la ficha.

El diseño detallado de los tres, con los números del club, está en
`dinamyt-membresias/CORREO.md`.

---

## 4. Preparar el VPS

Ubuntu 24.04 LTS. Un VPS con IP pública recibe intentos de login a los cinco
minutos de existir, así que esto va primero.

```bash
# 1. usuario propio, sin root
adduser dinamyt
usermod -aG sudo dinamyt

# 2. llave SSH desde tu PC (ejecutar EN TU PC)
ssh-copy-id dinamyt@TU_IP

# 3. apagar el acceso por contraseña (ya en el servidor, como dinamyt)
sudo sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sudo systemctl restart ssh

# 4. cortafuegos: solo SSH y web
sudo ufw allow OpenSSH
sudo ufw allow 80,443/tcp
sudo ufw enable

# 5. lo básico
sudo apt update && sudo apt upgrade -y
sudo apt install -y fail2ban unattended-upgrades git curl postgresql
sudo timedatectl set-timezone America/Bogota
```

**Nunca abras los puertos 3000, 3004, 3006 ni 5000.** Escuchan en `127.0.0.1` y
lo único que habla con internet es Caddy. Un puerto de app abierto es alguien
entrando sin HTTPS y sin el proxy que arregla las IPs del limitador de intentos.

**Caddy** (el reverse proxy que saca los certificados solo):

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

**Node 22 + pnpm** (Membresías):

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs
sudo corepack enable && corepack prepare pnpm@11.5.0 --activate
```

**Python 3.11** (Campeonatos) — **no la 3.12 que trae el sistema**:

```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev build-essential libpq-dev
```

> Con Python 3.12+ el monkey-patching de eventlet se rompe bajo gunicorn y
> **toda consulta responde 500**. Es el mismo motivo por el que en Render está
> fijado `PYTHON_VERSION=3.11.9`. Si prefieres no pelear con el sistema, mete
> Campeonatos en un contenedor `python:3.11-slim`.

---

## 5. Base de datos y traer los datos

```bash
sudo -u postgres psql -c "CREATE USER dinamyt WITH PASSWORD 'CLAVE_FUERTE';"
sudo -u postgres createdb dinamyt_campeonatos -O dinamyt
sudo -u postgres createdb dinamyt_membresias  -O dinamyt
```

Traer lo que ya existe, **antes de apagar nada** en la nube. Ojo con Membresías:
su esquema se llama `membresias`, no `public`.

```bash
pg_dump "URL_DE_NEON"     --no-owner --no-privileges -Fc -f campeonatos.dump
pg_dump "URL_DE_SUPABASE" --no-owner --no-privileges -n membresias -Fc -f membresias.dump

pg_restore -d "postgresql://dinamyt@localhost/dinamyt_campeonatos" campeonatos.dump
pg_restore -d "postgresql://dinamyt@localhost/dinamyt_membresias"  membresias.dump
```

Después de restaurar, cuenta filas en las dos y compáralas con el panel viejo.

Si en vez de migrar arrancas de cero: Campeonatos crea tablas y siembra con
`flask init-db` (o `flask seed` si ya existen), y Membresías aplica sus
migraciones sola al arrancar la API.

---

## 6. Subir Campeonatos

```bash
sudo mkdir -p /srv && sudo chown dinamyt:dinamyt /srv
git clone <TU_REPO> /srv/campeonatos

# backend
cd /srv/campeonatos/backend
python3.11 -m venv venv
venv/bin/pip install -r requirements.txt
nano .env          # el del paso 3.1

# frontend
cd /srv/campeonatos/frontend
npm ci
nano .env.production   # el del paso 3.1  ← antes de compilar
npm run build
```

**`/etc/systemd/system/campeonatos-api.service`:**

```ini
[Unit]
Description=DINAMYT Campeonatos - API Flask + Socket.IO
After=network.target postgresql.service

[Service]
User=dinamyt
WorkingDirectory=/srv/campeonatos/backend
EnvironmentFile=/srv/campeonatos/backend/.env
ExecStart=/srv/campeonatos/backend/venv/bin/gunicorn -k eventlet -w 1 -b 127.0.0.1:5000 wsgi:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

> **`-w 1` no es negociable.** El estado en vivo de los tatamis, los rooms de
> Socket.IO y el limitador viven en la memoria del proceso: con dos workers, dos
> jueces del mismo tatami caen en procesos distintos y ven marcadores distintos.

**`/etc/systemd/system/campeonatos-web.service`:**

```ini
[Unit]
Description=DINAMYT Campeonatos - Web Next
After=network.target

[Service]
User=dinamyt
WorkingDirectory=/srv/campeonatos/frontend
ExecStart=/srv/campeonatos/frontend/node_modules/.bin/next start -H 127.0.0.1 -p 3000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

> Se llama a `next` directo y no a `npm start` a propósito: el script `start`
> del `package.json` levanta en `-H 0.0.0.0`, y aquí queremos que escuche solo
> en local.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now campeonatos-api campeonatos-web
curl -s localhost:5000/api/campeonatos/publico | head -c 200
curl -sI localhost:3000 | head -1
```

---

## 7. Subir Membresías

```bash
git clone <TU_REPO_MEMBRESIAS> /srv/membresias
cd /srv/membresias
pnpm install --frozen-lockfile

nano packages/membresias-db/.env
nano apps/membresias-api/.env
nano apps/membresias-web/.env.production   # ← antes de compilar

pnpm --filter @dinamyt/membresias-db  build
pnpm --filter @dinamyt/membresias-api build
pnpm --filter @dinamyt/membresias-web build
```

**`/etc/systemd/system/membresias-api.service`:**

```ini
[Unit]
Description=DINAMYT Membresias - API Fastify
After=network.target postgresql.service

[Service]
User=dinamyt
WorkingDirectory=/srv/membresias
EnvironmentFile=/srv/membresias/apps/membresias-api/.env
ExecStart=/usr/bin/node apps/membresias-api/dist/main.js
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**`/etc/systemd/system/membresias-web.service`:**

```ini
[Unit]
Description=DINAMYT Membresias - Web Next (PWA)
After=network.target

[Service]
User=dinamyt
WorkingDirectory=/srv/membresias/apps/membresias-web
ExecStart=/srv/membresias/node_modules/.bin/next start -H 127.0.0.1 -p 3006
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now membresias-api membresias-web
curl -s localhost:3004/health
```

Las migraciones las aplica la API sola al arrancar; si algo falla, sale en
`journalctl -u membresias-api -n 50`.

---

## 8. Conectar el dominio (Caddy + DNS)

**En Cloudflare → DNS**, tres registros a la IP del VPS, **en gris (DNS only)**:

| Tipo | Nombre | Valor |
|---|---|---|
| A | `@` | IP del VPS |
| A | `www` | IP del VPS |
| A | `campeonatos` | IP del VPS |
| A | `club` | IP del VPS |

En gris y no en naranja porque Caddy necesita validar el certificado sin nadie
en medio. Si más adelante quieres proxear (esconder la IP), pon SSL/TLS en
**Full (strict)** y ten en cuenta que el plan gratis corta las peticiones HTTP a
los ~100 s: los reportes PDF de un campeonato grande pueden pasarse.

**`/etc/caddy/Caddyfile`:**

```caddyfile
campeonatos.dinamyt.org {
	encode zstd gzip
	handle /api/*       { reverse_proxy 127.0.0.1:5000 }
	handle /socket.io/* { reverse_proxy 127.0.0.1:5000 }
	handle              { reverse_proxy 127.0.0.1:3000 }
}

club.dinamyt.org {
	encode zstd gzip
	reverse_proxy 127.0.0.1:3006
}

dinamyt.org, www.dinamyt.org {
	redir https://campeonatos.dinamyt.org{uri}
}
```

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

> **Por qué Campeonatos parte las rutas y Membresías no.** En Campeonatos el
> rewrite conserva el prefijo `/api`, así que Caddy puede mandarlo directo al
> Flask — y el WebSocket **necesita** ese camino, porque pasando por Next se
> degradaría a long-polling. En Membresías el rewrite **quita** el `/api` antes
> de reenviar (`apps/membresias-web/next.config.ts`), así que ahí todo entra por
> Next y él reparte. Copiar el bloque de una a la otra rompe la API con 404.

---

## 9. El correo, paso a paso

Son **dos servicios distintos** y se montan por separado: uno envía, otro recibe.

### 9.1 Recibir — Cloudflare Email Routing (gratis)

1. Cloudflare → tu dominio → **Email → Email Routing → Get started**.
2. Acepta que agregue los registros `MX` y el `TXT` de SPF automáticamente.
3. **Create address:** `soporte@dinamyt.org` → destino: tu Gmail. Repite con
   `admin@dinamyt.org`.
4. Gmail te manda un correo de verificación del destino: ábrelo y confirma.
5. Prueba: escríbele a `soporte@dinamyt.org` desde otra cuenta. Debe caer en tu
   Gmail en segundos.

### 9.2 Enviar — Resend

1. resend.com → **Domains → Add domain** → escribe **`dinamyt.org`** (el dominio
   raíz, no un subdominio).
2. Pega en Cloudflare los registros que te muestre: el `TXT` de DKIM y los de
   `send.dinamyt.org` (SPF y el MX de rebotes). **Todos en gris.**
3. Espera la verificación (minutos) hasta que el dominio quede en *Verified*.
4. **API Keys → Create** → guarda la clave: es el `SMTP_PASS` del paso 3.3.

> **Por qué el dominio raíz y no `mail.dinamyt.org`.** El manual dice que el
> envío va en un subdominio para aislar la reputación, y es buen consejo — pero
> el plan gratis de Resend permite **un solo dominio**, y verificando el raíz
> puedes mandar como cualquier dirección de `@dinamyt.org`, que es lo que hace
> falta para el paso siguiente. Resend igual pone sus registros de rebote en
> `send.dinamyt.org`, así que no chocan con los `MX` de Email Routing.

### 9.3 Responder con la dirección del proyecto — Gmail «Enviar como»

Sin esto, cuando contestes un correo de soporte el otro ve tu dirección
personal.

1. Gmail → **Configuración → Cuentas e importación → Enviar como → Agregar otra
   dirección de correo**.
2. Nombre: `DINAMYT`. Dirección: `soporte@dinamyt.org`. Desmarca «Tratar como
   alias» si quieres que las respuestas salgan siempre con esa cara.
3. Servidor SMTP: `smtp.resend.com`, puerto `587`, usuario `resend`, contraseña:
   la API key. TLS.
4. Gmail manda un código a esa dirección → llega por Email Routing a tu propia
   bandeja → pégalo y listo.
5. Repite con `admin@dinamyt.org` si la quieres usar para escribir.

Esas respuestas consumen del cupo de Resend (100 al día). Para correo humano
sobra de largo.

### 9.4 DMARC

Un `TXT` en `_dmarc` con:

```
v=DMARC1; p=none; rua=mailto:soporte@dinamyt.org
```

Arranca en `p=none`: no bloquea nada y te llegan reportes de quién manda en
nombre de tu dominio. A las dos semanas, con los reportes limpios, súbelo a
`p=quarantine` y después a `p=reject`. Ponerlo en `reject` el primer día es la
forma más rápida de que tus propios correos dejen de llegar.

### 9.5 Amazon SES — para las ráfagas de campeonato

El tope de Resend que muerde no es el de 3.000 al mes: es el de **100 al día**.
El día que abras inscripciones salen ~300 confirmaciones de golpe y 200 personas
se quedan esperando.

1. Consola de AWS → SES → **Verified identities** → verifica `dinamyt.org` con
   Easy DKIM; pega los tres `CNAME` en Cloudflare.
2. **Request production access** (formulario: qué envías, cómo manejas rebotes y
   bajas). Tarda 24–48 h. **Mándalo con semanas de anticipación al primer
   campeonato.**
3. Crea credenciales SMTP (SES → SMTP settings) y cambia las cuatro variables
   `SMTP_*`. Nada más.
4. Configura el manejo de rebotes por SNS: si mandas a direcciones que no
   existen y no lo procesas, AWS suspende el envío.

Precio: US$0,16 por cada 1.000 correos, sin cuota mensual.

### 9.6 Alternativa si quieres bandeja propia en vez de reenvío

Zoho Mail plan gratis: 5 buzones con tu dominio, 5 GB cada uno, 1 dominio, solo
acceso web y app (sin IMAP, no se conecta a Outlook). Cambia el paso 9.1 por:
agregar el dominio en Zoho, pegar su `TXT` de verificación, cambiar los `MX` a
los suyos y activar su DKIM. Con eso el 9.3 sobra: respondes desde Zoho.

---

## 10. Cron, respaldos y monitoreo

**El disparo diario de avisos de Membresías** deja de venir de Vercel:

```bash
crontab -e
```

```cron
# 8:00 de Bogotá, directo a la API, sin rodeo por la web
0 8 * * * curl -fsS -X POST -H "x-cron-secret: TU_CRON_SECRET" http://127.0.0.1:3004/notifications/cron
```

Ganas dos cosas: se acabó el minuto de espera del primer despertar de Render, y
se acabó la ventana de una hora de imprecisión del plan Hobby de Vercel.

**Respaldos** — esto es lo que antes hacían Neon y Supabase por ti:

```cron
0  3 * * * pg_dump -Fc dinamyt_campeonatos > /var/backups/camp-$(date +\%F).dump
5  3 * * * pg_dump -Fc dinamyt_membresias  > /var/backups/memb-$(date +\%F).dump
15 3 * * * rclone copy /var/backups r2:dinamyt-backups --max-age 48h
30 3 * * * find /var/backups -name '*.dump' -mtime +14 -delete
```

**Prueba el restore, no el backup.** Una vez al mes, levanta un dump en una base
vacía y entra a mirar. Un respaldo que nunca se restauró no es un respaldo.

**Monitoreo:** un monitor HTTP cada 5 minutos contra
`https://campeonatos.dinamyt.org/api/campeonatos/publico` y otro contra
`https://club.dinamyt.org`. Ya no es para que no se duerma nada: es para
enterarte tú antes que un juez.

---

## 11. Verificación final

- [ ] `https://campeonatos.dinamyt.org` carga y el candado es válido
- [ ] Login de admin, y **recarga la página**: la sesión aguanta (si no, revisa
      `NEXT_PUBLIC_API_MODE` y `COOKIE_*`)
- [ ] Abre un tatami y la pantalla pública en dos dispositivos: el marcador se
      refleja al instante (si va lento o se cae, el socket cayó a long-polling:
      revisa el bloque `/socket.io/*` del Caddyfile)
- [ ] En la consola del navegador, la conexión de Socket.IO aparece como
      `websocket`, no `polling`
- [ ] Genera un reporte en PDF y en Excel
- [ ] `https://club.dinamyt.org` carga, login de maestro, check-in con QR
- [ ] Un push de prueba llega al celular (las llaves VAPID viajaron bien)
- [ ] `curl` del cron responde `{"ok":true,...}`
- [ ] Un correo de prueba llega a Gmail y a Outlook, y en «mostrar original»
      dice `SPF: PASS` y `DKIM: PASS`
- [ ] Respondes desde Gmail y al otro le llega como `soporte@dinamyt.org`
- [ ] El respaldo de anoche existe y pesa lo que debe

## 12. Apagar lo viejo

**Una semana después**, no antes: en el plan gratis, Render y Vercel cuestan lo
mismo encendidos que apagados y son tu marcha atrás.

1. Apaga primero los crons de Vercel (para que no dupliquen avisos).
2. Verifica que nadie usa las URLs viejas (revisa accesos).
3. Borra los servicios de Render y los proyectos de Vercel.
4. **Neon y Supabase de últimos**, y solo después de restaurar un respaldo del
   VPS en una base de prueba y comprobar que está todo.

---

## Anexos

### Puertos

| Puerto | Quién | Expuesto |
|---|---|---|
| 22, 80, 443 | SSH y Caddy | Sí |
| 3000 | Campeonatos web | No, solo `127.0.0.1` |
| 5000 | Campeonatos API + Socket.IO | No |
| 3006 | Membresías web | No |
| 3004 | Membresías API | No |
| 5432 | PostgreSQL | No |

### DNS, todo junto

| Tipo | Nombre | Valor | Proxy |
|---|---|---|---|
| A | `@`, `www`, `campeonatos`, `club` | IP del VPS | Gris |
| MX | `@` | Los de Cloudflare Email Routing | — |
| TXT | `@` | SPF de Email Routing | — |
| TXT | `resend._domainkey` | DKIM de Resend | — |
| MX + TXT | `send` | Rebotes y SPF de Resend | — |
| TXT | `_dmarc` | `v=DMARC1; p=none; rua=mailto:soporte@dinamyt.org` | — |
| CNAME ×3 | los de SES | Easy DKIM, cuando lo actives | — |

### Costos al mes

| Concepto | Hoy (para que funcione bien) | En el VPS |
|---|---|---|
| Servidores de las apps | US$14 (2 × Render) | incluido |
| Web | US$20 (Vercel Pro: Hobby es no comercial) | incluido |
| Bases de datos | US$0 | incluido |
| VPS | — | US$11–20 |
| Dominio | US$0,85 | US$0,85 |
| Buzón | US$0 | US$0 |
| Envío de correo | US$0 | US$0–0,20 |
| Respaldos | incluido | ~US$0,20 |
| **Total** | **≈ US$35** | **≈ US$12–21** |

### Riesgos que hay que tener presentes

- **Un solo servidor es un solo punto de falla**, y caerá el sábado del
  campeonato. Toma un snapshot la víspera (cuesta centavos) y lleva probado el
  modo local: `/local`, `/tablero` y el paquete `.json` de sincronización son
  exactamente para eso.
- **Ahora el sysadmin eres tú**: actualizaciones, respaldos y estar disponible.
- **Python 3.11 y `-w 1`** en Campeonatos: los dos ya están documentados con
  sangre; no los redescubras.
- **Reconstruye después de tocar cualquier `NEXT_PUBLIC_*` o
  `MEMBRESIAS_API_ORIGIN`**: viven dentro del build, reiniciar no basta.
