# DINAMYT — Versión LOCAL (servidor en tu PC, sin internet)

Esta copia corre **todo desde un solo PC**. Los jueces, la mesa y las pantallas
se conectan por **red local (LAN)** a este computador. **No usa internet ni la
nube** (nada de Render, Vercel ni Supabase). Se le quitó todo el modo "offline"
porque aquí el servidor está siempre presente en la red.

- **Frontend** (lo que ve la gente): `http://IP-DEL-PC:3000`
- **Backend** (API + tiempo real): `http://IP-DEL-PC:5000`
- **Base de datos:** SQLite local, en `backend/instance/`. Se crea sola.
- **Usuario admin inicial:** lo que pongas en `backend/.env` — `ADMIN_EMAIL`
  (por defecto `admin@dinamyt.org`) y `ADMIN_PASSWORD`, que **no tiene valor por
  defecto a propósito**: sin ella el seed no crea el admin y no puedes entrar.
  Pásale 12 caracteres o más. **Ponlas antes del primer arranque**, que es
  cuando se crea.

---

## 1) La red: cómo conectar ~30 dispositivos (IMPORTANTE)

**No uses el "Zona con cobertura" (hotspot) de Windows para 30 equipos.** Windows
lo limita a **8 dispositivos** y la antena del PC no da abasto haciendo de router
y servidor a la vez.

**Usa un router WiFi dedicado** (NO necesita internet, solo reparte la red):

```
[ Router WiFi ] --cable de red (Ethernet)--> [ Este PC: backend + frontend ]
      | WiFi
   Los ~30 celulares  ->  abren  http://IP-DEL-PC:3000
```

Pasos:
1. Conecta el **PC al router por cable Ethernet** (más estable que WiFi).
2. En la config del router, reserva/fija la **IP del PC** (DHCP reservation) para
   que no cambie durante el evento. Anota esa IP (ej. `192.168.0.30`).
3. Los celulares se conectan **al WiFi del router** y abren `http://ESA-IP:3000`.

Con esto **un solo PC basta** para 30 dispositivos: la app manda datos diminutos.
No hace falta un segundo servidor. (Si quieres respaldo, ten un segundo portátil
apagado con esta misma copia y una copia de `backend/instance/` — pero solo uno
encendido a la vez).

---

## 2) Preparación (UNA vez, en casa CON internet)

1. **Abre el firewall** (para que los celulares puedan entrar):
   clic derecho en **`abrir-firewall.bat`** → **Ejecutar como administrador**.
2. **Instala todo:** doble clic en **`1-INSTALAR.bat`** (descarga dependencias y
   compila el frontend). Tarda unos minutos. *Esto ya se hizo en este PC.*

> Si Windows pregunta al arrancar por primera vez si permitir a Python/Node en la
> red, marca **Redes privadas** y **Permitir acceso**.

---

## 2.1) La víspera, CON internet: traer el campeonato

*(añadido el 9 de septiembre de 2026. **Este paso faltaba en el manual** y es
el que trae el evento: sin él, el PC arranca perfectamente y vacío.)*

El campeonato se inscribe en internet y **se corre aquí**. Entre las dos cosas
hay una bajada, y hay que hacerla **la víspera, con red**:

1. En la instalación de **internet** (la VPS), entra como administrador y abre
   el campeonato → **Exportar paquete**. Se descarga un archivo `.json`.
2. Pásalo a este PC (USB, correo, lo que sea) y aquí, en **Admin →
   Campeonatos → Importar campeonato**, súbelo.
3. Sale una **vista previa** antes de escribir nada: dice cuántos usuarios,
   competidores e inscripciones va a traer. **Comprueba que esos números
   cuadran con los que enseña la VPS.** Si cuadran, confirma.
4. **Asigna contraseñas** a quien vaya a necesitarlas, en **Admin →
   Usuarios**. Las contraseñas **no viajan en el paquete** (a propósito), así
   que los usuarios importados llegan sin clave utilizable. Los jueces no
   necesitan ninguna: entran con el QR de su tatami (ver §3.1).

> **Se puede bajar tantas veces como haga falta.** El modo normal es
> *fusionar*: vuelve a traer lo nuevo y actualiza lo cambiado, **sin
> duplicar**. Si el jueves entran tres inscripciones más, se exporta otra vez
> el viernes, se importa otra vez, y aparecen.

> **Pero deja de poder hacerse en cuanto se compite.** Si aquí ya hay una
> llave activa o terminada, la importación se niega —podría pisar
> resultados—. **Así que la última bajada es la mañana del evento, si todavía
> hay red, y ANTES de activar la primera llave.**

### Cómo saber de cuándo es la copia que tiene este PC

En **Admin → Campeonatos** hay una línea que lo dice:

> *Copia traída de la VPS · COPA NACIONAL · exportada el 7/10/2026, 18:42 ·
> hace 13 h · 12 usuarios · 148 competidores · 160 inscripciones*

Y **si la copia lleva más de un día** y todavía no se compite, la línea se
pone en dorado y lo avisa. Es la respuesta a la pregunta de las siete de la
mañana —*«¿esto trae las inscripciones del jueves?»*— sin tener que adivinar.

---

## 3) Encender el sistema el día del evento (sin internet)

1. Doble clic en **`2-INICIAR.bat`**. Se abren **dos ventanas negras**
   (Backend y Frontend) y te muestra las direcciones `http://...:3000` del PC.
2. Espera ~15 segundos a que el frontend diga *"Ready"*.
3. En cada dispositivo, abre en el navegador: **`http://IP-DEL-PC:3000`**
   (usa la IP que reservaste en el router).

Para **apagar**: cierra las dos ventanas negras.

---

## 3.1) ⚠️ Aquí NO se entra con la cuenta de DINAMYT

*(añadido el 9 de septiembre de 2026)*

**Esto sorprende a todo el mundo la primera vez, y conviene decirlo la víspera y
no el sábado a las siete de la mañana.**

Desde agosto de 2026, en internet se entra a Campeonatos con la cuenta de DINAMYT
y sin segunda contraseña. **En el modo local eso no existe**: no hay internet, y
sin internet no hay ecosistema al que preguntar quién eres.

| En internet (`campeonatos.dinamyt.org`) | Aquí, en el PC del evento |
|---|---|
| Se entra con la cuenta de DINAMYT | Se entra con **el usuario y la contraseña de esta instalación** |
| Recuperar contraseña por correo | **No hay.** Sin correo que mandar |
| Cuentas nuevas desde el portal | **No hay.** Las crea el admin local |
| Invitaciones por WhatsApp | **No hay** |

**Las dos formas de entrar el día del evento, y no hay más:**

1. **El QR del tatami** — es la buena para los jueces. Admin → Campeonato →
   Tatami → **📱 QR** junto a cada juez. Lo escanea y entra directo a su rol, sin
   escribir nada. Dura 72 h, o sea todo el fin de semana.
2. **El usuario y la contraseña locales** — para el admin, y para quien necesite
   entrar sin QR.

> **Los usuarios que llegan en el paquete del campeonato vienen SIN contraseña.**
> Lo dice el propio informe al importar: *«5 usuario(s) se crearon SIN contraseña:
> los jueces entran con el QR de su tatami; si alguien necesita entrar con clave,
> asígnasela en Usuarios.»* Así que si alguien va a necesitar teclear su
> contraseña, **asígnasela la víspera**, con luz y sin prisa.

El porqué completo está en `B3-RIESGOS.md` §1.4: la promesa de «una cuenta para
todo» se suspende esos tres días, y es a propósito.

---

## 4) Que los celulares NO se desconecten (red sin internet)

Como esta red **no tiene internet**, Android/iOS intentan "escapar" a datos
móviles o a otro WiFi. Configura cada celular así:

- **Apaga los datos móviles.**
- **"Olvida" otras redes WiFi** para que no salte a ellas.
- **Android:** en Ajustes de red, desactiva *"Cambiar a datos móviles"* /
  *"Conectividad adaptable"*.
- **iPhone:** desactiva *"Wi-Fi Assist"* y el *Auto-Join* de otras redes.
- **Recomendado:** en el navegador, *"Agregar a pantalla de inicio"* — la app se
  abre a pantalla completa y mantiene mejor la conexión.

Si un celular se desconecta un instante, **se reconecta solo** (el sistema
reintenta cada 2 segundos) y el juez no pierde lo que estaba registrando.

---

## 5) La letra se ve igual en todos (ya resuelto)

Las tipografías van **incrustadas en la app** (no se bajan de internet ni usan la
fuente del teléfono), y el tamaño está fijado para que ningún celular lo "infle".
Requisito: usar el sistema tal cual (`2-INICIAR.bat` sirve el build de producción,
que es donde las fuentes van optimizadas). No hay que hacer nada extra.

---

## 6) MUY IMPORTANTE: no toques las ventanas negras

En Windows, hacer **clic dentro de una ventana negra** (la del Backend o la del
Frontend) activa el modo *"Selección rápida"* y **CONGELA el programa completo**
hasta que se presione ESC o Enter. Se ve exactamente como la falla del evento:
todo aparece "sin conexión" aunque el servidor "esté encendido".

- No hagas clic ni selecciones texto dentro de esas ventanas. Minimízalas.
- Si alguien lo hizo (la barra de título dice "Seleccionar"), haz clic en la
  ventana y presiona **ESC**: todo revive al instante, sin reiniciar nada.

---

## 7) Si la red falla en pleno combate (plan B)

- Cada juez, en su pantalla de puntuación, pasa solo a **registro local**: sus
  puntos se guardan en el teléfono aunque recargue. **Al volver la conexión se
  envían solos a la mesa**: al Juez Central le aparece "Registro local de
  jueces — por resolver" y con un toque los **aplica al marcador** (o los
  descarta); la libreta del juez se limpia sola.
- Además, existen paneles de contingencia que funcionan 100% en el
  dispositivo, sin servidor (ya no aparecen como botones en la pantalla de
  inicio; se abren escribiendo la dirección a mano):
  `http://IP-DEL-PC:3000/local?modo=combate` y
  `http://IP-DEL-PC:3000/local?modo=figuras`.
- Si un juez **recarga la página** o cambia de teléfono, entra de nuevo a su
  tatami sin problema: la conexión nueva reemplaza a la vieja automáticamente
  (a la sesión anterior le aparece "sesión abierta en otro dispositivo").

---

## 7.1) Novedades útiles para operar el evento

- **Respaldo automático de la BD**: cada 10 minutos se guarda una copia en
  `backend/instance/respaldos/` (se conservan las últimas 20). Si algo se
  daña, cierra todo y reemplaza `backend/instance/dinamyt.db` por el respaldo
  más reciente. (Se ajusta con `RESPALDO_MINUTOS` en `backend/.env`; 0 = off.)
- **Panel de conexiones**: el Juez Central ve arriba qué jueces están
  conectados en su tatami (verde = conectado). Si un juez aparece en rojo,
  no sigas puntuando hasta que reconecte.
- **QR de acceso por juez**: en Admin → Campeonato → Tatami → botón **📱 QR**
  junto a cada juez asignado. El juez lo escanea con la cámara (conectado al
  WiFi del evento) y entra directo a su rol, sin usuario ni contraseña.
- **PDF del sorteo**: en Admin → Llaves, cada llave tiene botón **📄 PDF** con
  el cuadro listo para imprimir y publicar en cartelera.
- **Número de combate del día** (Combate #N) visible en la pantalla pública y
  el panel del JC, y **"Próximos"** en la pantalla para que los siguientes
  competidores se preparen.
- **Anular un punto específico**: panel "Puntos del combate · anular" del JC —
  anula cualquier entrada (no solo la última) y queda constancia en el log.

---

## 8) Si algo falla

- **Los celulares no cargan la página:** ¿corriste `abrir-firewall.bat` como
  administrador? ¿El celular está en el WiFi del router y usas la IP correcta?
  El firewall debe permitir **los puertos 3000 y 5000** (el marcador en vivo y
  la API hablan directo con el 5000).
- **Carga el frontend pero no guarda / no marca en vivo:** revisa que la ventana
  del **Backend** esté abierta, sin errores y **sin modo Selección** (ver
  sección 6). Presiona ESC en esa ventana por si acaso.
- **Cambió la IP del PC:** no hay que recompilar; solo abre la nueva
  `http://NUEVA-IP:3000` en los celulares. (Por eso conviene reservar la IP.)
- **Reiniciar desde cero la base de datos:** cierra todo y borra la carpeta
  `backend/instance/`; al volver a iniciar se recrea con el admin y las categorías.
