"""
Encender DINAMYT en el PC del evento, comprobando ANTES de arrancar.

── Por que existe ──────────────────────────────────────────────────────────────
`2-INICIAR.bat` abria las dos ventanas y daba por hecho que todo estaba en su
sitio. Si faltaba algo, la aplicacion arrancaba A MEDIAS y el fallo aparecia
media hora despues, con gente delante: el backend levantado y el frontend sin
compilar, o el puerto 3000 ocupado por otra cosa y nadie sabiendo por que los
celulares no entran.

El sitio donde esto falla es un gimnasio a las siete de la manana, sin internet
para buscar nada. Asi que aqui se comprueba primero y se arranca despues:

  1. Que la instalacion existe (`1-INSTALAR.bat` ya corrio).
  2. Que los puertos 5000 y 3000 estan libres, y si no, QUE los ocupa.
  3. Se arranca y se ESPERA A QUE RESPONDAN de verdad, sondeando el puerto.
     El manual decia "espera unos 15 segundos", que es adivinar: en un PC lento
     son 40 y en uno rapido son 6, y en los dos casos alguien mira la pantalla
     sin saber si ya puede repartir la direccion.
  4. Se ensena la direccion en grande y un QR para que 30 celulares no la
     tecleen a mano.
  5. Queda escrito en `local-<fecha>.log`, que es lo unico que va a quedar si
     algo se tuerce.

── Sin acentos, a proposito ────────────────────────────────────────────────────
Esto se lee en una consola de Windows, donde la pagina de codigos no esta
garantizada. Un mensaje de error que sale como "no estA instalado" es un
mensaje de error peor. Es la misma regla que siguen los .bat de al lado.

Uso:
    python iniciar_local.py                # comprueba y arranca
    python iniciar_local.py --comprobar    # SOLO comprueba (la vispera)
"""

import argparse
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
BACKEND = RAIZ / "backend"
FRONTEND = RAIZ / "frontend"

PUERTO_BACKEND = 5000
PUERTO_FRONTEND = 3000

# Cuanto se espera a que cada servicio conteste antes de darlo por fallido.
# Un PC modesto compilado en produccion tarda entre 5 y 40 segundos; 90 es
# holgado sin llegar a ser una espera eterna delante de la gente.
ESPERA_MAXIMA = 90

SEPARADOR = "=" * 62

_registro = []


def decir(linea=""):
    """A la pantalla y al registro, siempre a la vez."""
    print(linea)
    _registro.append(linea)


def guardar_registro():
    """Vuelca lo que paso a `local-<fecha>.log`, junto a este archivo.

    Solo lleva lo que vio el arrancador. Lo que escriban el backend y el
    frontend se queda en SUS ventanas: son consolas aparte, y capturarlas
    seria quitarselas de delante a quien las necesita para ver un error.
    """
    destino = RAIZ / f"local-{datetime.now():%Y-%m-%d}.log"
    try:
        with open(destino, "a", encoding="utf-8") as f:
            f.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
            f.write("\n".join(_registro) + "\n")
        return destino
    except OSError as e:
        print(f"(no se pudo escribir el registro: {e})")
        return None


# ── 1 . La instalacion esta completa ───────────────────────────────────────

def comprobar_instalacion():
    """Lista de lo que falta. Vacia = se puede arrancar."""
    faltan = []
    if not (BACKEND / "venv" / "Scripts" / "python.exe").exists():
        faltan.append("el entorno de Python del backend (backend\\venv)")
    if not (FRONTEND / "node_modules").is_dir():
        faltan.append("las dependencias del frontend (frontend\\node_modules)")
    # `.next` es la compilacion de produccion. Sin ella `npm run start` arranca
    # y muere pidiendo un build, que es el fallo a medias que esto evita.
    if not (FRONTEND / ".next").is_dir():
        faltan.append("el frontend compilado (frontend\\.next)")
    return faltan


# ── 2 . Los puertos estan libres ───────────────────────────────────────────

def _pids_escuchando(puerto):
    """PIDs que tienen el puerto en LISTENING, segun netstat."""
    try:
        salida = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True, text=True, timeout=20,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []

    pids = []
    for linea in salida.splitlines():
        partes = linea.split()
        # Formato: Proto  Direccion-local  Direccion-remota  Estado  PID
        if len(partes) < 5 or partes[3].upper() != "LISTENING":
            continue
        local = partes[1]
        # El puerto es lo que va tras el ULTIMO ":" (IPv6 lleva varios).
        if local.rsplit(":", 1)[-1] != str(puerto):
            continue
        if partes[4].isdigit() and partes[4] != "0" and partes[4] not in pids:
            pids.append(partes[4])
    return pids


def _nombre_del_proceso(pid):
    try:
        salida = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
            capture_output=True, text=True, timeout=20,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.match(r'"([^"]+)"', salida)
    return m.group(1) if m else None


def quien_ocupa(puerto):
    """Descripcion de quien tiene el puerto, o None si esta libre.

    Se dice QUE lo ocupa y no solo que esta ocupado: "lo tiene node.exe (PID
    9120)" se resuelve solo; "el puerto 3000 esta ocupado" manda a buscar en
    internet, que es justo lo que no hay ese dia.
    """
    pids = _pids_escuchando(puerto)
    if not pids:
        return None
    partes = []
    for pid in pids:
        nombre = _nombre_del_proceso(pid)
        partes.append(f"{nombre} (PID {pid})" if nombre else f"PID {pid}")
    return ", ".join(partes)


# ── 3 . Arrancar y esperar a que CONTESTEN ─────────────────────────────────

def _responde(puerto):
    """True si algo contesta HTTP en ese puerto.

    Cualquier respuesta vale, incluido un 404: lo que se comprueba es que el
    servidor esta en pie, no que exista una ruta concreta. Atarlo a una ruta
    seria atar el arranque a que esa ruta siga existiendo.
    """
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/", timeout=3):
            return True
    except urllib.error.HTTPError:
        return True  # contesto, aunque sea un error: esta vivo
    except (urllib.error.URLError, OSError, ValueError):
        return False


def esperar(puerto, etiqueta, proceso):
    """Sondea hasta que conteste. False si se rinde o el proceso se murio."""
    limite = time.monotonic() + ESPERA_MAXIMA
    print(f"  Esperando a {etiqueta} (puerto {puerto})", end="", flush=True)
    while time.monotonic() < limite:
        if _responde(puerto):
            segundos = round(ESPERA_MAXIMA - (limite - time.monotonic()))
            print(" OK")
            decir(f"  {etiqueta}: responde en el puerto {puerto} ({segundos}s)")
            return True
        if proceso is not None and proceso.poll() is not None:
            print(" FALLO")
            decir(f"  {etiqueta}: el proceso termino antes de responder.")
            return False
        print(".", end="", flush=True)
        time.sleep(1)
    print(" FALLO")
    decir(f"  {etiqueta}: no contesto en {ESPERA_MAXIMA}s.")
    return False


def _arrancar(titulo, comando, cwd, entorno=None):
    """Abre el servicio en SU ventana, como hasta ahora.

    Se mantienen las dos ventanas negras a proposito: el manual del evento
    (`INICIAR-LOCAL.md` seccion 6) dice que no se tocan, y si un servicio
    revienta el error se queda ahi a la vista. Capturarlo aqui lo escondaria.
    """
    env = dict(os.environ)
    if entorno:
        env.update(entorno)
    # CREATE_NEW_CONSOLE y no `start`: con `start` el handle que devuelve
    # Popen es el de la shell que lanza y se muere al instante, asi que el
    # sondeo lo leeria como "el servicio murio" en el primer segundo.
    #
    # `cmd /k` mantiene la ventana abierta AUNQUE el servidor reviente, que es
    # justo cuando hace falta leerla. El precio es que este handle no sirve
    # para detectar la muerte del servidor — de eso se encarga el sondeo del
    # puerto, que es lo que de verdad interesa saber.
    #
    # `title` se pone dentro para que APAGAR.bat pueda cerrar la ventana por
    # su nombre.
    return subprocess.Popen(
        f'cmd /k "title {titulo} && {comando}"',
        cwd=str(cwd), env=env,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )


# ── 4 . La direccion, en grande y en QR ────────────────────────────────────

def ips_del_pc():
    """IPv4 de red local de este PC, la mas probable primero.

    Primero la del interfaz por el que sale el trafico (el truco del socket
    UDP, que no manda nada), y despues las demas. Se descartan la de loopback
    y las 169.254.x.x, que son las que pone Windows cuando NO hay red — y en
    un evento sin internet pero con router, esas son justo las que no sirven.
    """
    candidatas = []

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        candidatas.append(s.getsockname()[0])
    except OSError:
        pass
    finally:
        s.close()

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            candidatas.append(info[4][0])
    except OSError:
        pass

    vistas, buenas = set(), []
    for ip in candidatas:
        if ip in vistas or ip.startswith(("127.", "169.254.")):
            continue
        vistas.add(ip)
        buenas.append(ip)
    return buenas


def en_grande(texto):
    """La direccion separada y enmarcada, para leerla desde lejos."""
    espaciado = " ".join(texto)
    ancho = len(espaciado) + 6
    decir("+" + "-" * ancho + "+")
    decir("|" + " " * ancho + "|")
    decir("|   " + espaciado + "   |")
    decir("|" + " " * ancho + "|")
    decir("+" + "-" * ancho + "+")


def _habilitar_ansi():
    """Sin esto, el QR sale como una parrafada de codigos de escape.

    La consola de Windows entiende ANSI desde hace anos, pero hay que pedirlo
    (ENABLE_VIRTUAL_TERMINAL_PROCESSING). Si falla, se sigue: se pierde el QR,
    no el arranque.
    """
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        modo = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(modo)):
            kernel32.SetConsoleMode(handle, modo.value | 0x0004)
    except Exception:  # noqa: BLE001 - el QR es un extra
        pass


def mostrar_qr(url):
    """Pinta el QR en la consola con el `qrcode` que ya trae el frontend.

    No es una dependencia nueva: el paquete se instala con el frontend
    (`frontend/package.json`) y la aplicacion ya lo usa para el QR del tatami.
    Asi el dia del evento no hace falta instalar nada, que es la unica
    condicion que importa: ahi no hay internet.
    """
    _habilitar_ansi()
    exe = FRONTEND / "node_modules" / ".bin" / "qrcode.CMD"
    if not exe.exists():
        decir("  (sin QR: falta frontend/node_modules; usa la direccion de arriba)")
        return
    try:
        salida = subprocess.run(
            [str(exe), url], capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as e:
        decir(f"  (sin QR: {e})")
        return
    if salida.returncode != 0 or not salida.stdout.strip():
        # El fallo tipico es que `node` no este en el PATH: el .CMD es un
        # lanzador, no el programa. Decirlo tal cual ahorra el rato de mirar
        # un QR que no aparece; la direccion de arriba sigue sirviendo.
        motivo = (salida.stderr or salida.stdout).strip().splitlines()
        decir(f"  (sin QR: {motivo[0] if motivo else 'el generador no devolvio nada'})")
        decir("   No pasa nada: teclea la direccion de arriba en los celulares.")
        return
    print(salida.stdout)
    _registro.append(f"  [QR de {url} pintado en pantalla]")


# ── El guion ───────────────────────────────────────────────────────────────

def comprobaciones(salir_si_falla=True):
    """Las dos comprobaciones previas. True si se puede arrancar."""
    decir(SEPARADOR)
    decir(" COMPROBANDO ANTES DE ARRANCAR")
    decir(SEPARADOR)

    faltan = comprobar_instalacion()
    if faltan:
        decir("")
        decir(" FALTA LA INSTALACION. No se arranca nada a medias.")
        for f in faltan:
            decir(f"   - Falta {f}")
        decir("")
        decir(" Corre 1-INSTALAR.bat (necesita internet) y vuelve a intentarlo.")
        return False
    decir("  Instalacion: completa (venv, node_modules y .next)")

    ocupados = []
    for puerto, quien_es in ((PUERTO_BACKEND, "backend"), (PUERTO_FRONTEND, "frontend")):
        ocupa = quien_ocupa(puerto)
        if ocupa:
            ocupados.append((puerto, quien_es, ocupa))
        else:
            decir(f"  Puerto {puerto} ({quien_es}): libre")

    if ocupados:
        decir("")
        decir(" HAY PUERTOS OCUPADOS:")
        for puerto, quien_es, ocupa in ocupados:
            decir(f"   - El {puerto} ({quien_es}) lo tiene {ocupa}")
        decir("")
        decir(" Si es DINAMYT de un arranque anterior, corre APAGAR.bat.")
        decir(" Si es otro programa, cierralo y vuelve a intentarlo.")
        return False

    return True


def main():
    parser = argparse.ArgumentParser(description="Encender DINAMYT en local.")
    parser.add_argument(
        "--comprobar", action="store_true",
        help="Solo comprobar que este PC puede arrancar; no arranca nada.",
    )
    args = parser.parse_args()

    listo = comprobaciones()

    if args.comprobar:
        decir("")
        decir(SEPARADOR)
        decir(" TODO EN ORDEN: este PC puede arrancar." if listo
              else " ESTE PC NO PUEDE ARRANCAR TODAVIA (mira arriba).")
        decir(SEPARADOR)
        registro = guardar_registro()
        if registro:
            print(f"\nQueda escrito en: {registro.name}")
        return 0 if listo else 1

    if not listo:
        guardar_registro()
        return 1

    decir("")
    decir(SEPARADOR)
    decir(" ARRANCANDO")
    decir(SEPARADOR)

    back = _arrancar(
        "DINAMYT Backend",
        r"venv\Scripts\python.exe run.py",
        BACKEND,
        entorno={"FLASK_ENV": "development"},
    )
    if not esperar(PUERTO_BACKEND, "el backend", back):
        decir("")
        decir(" El backend no arranco. Mira la ventana 'DINAMYT Backend'.")
        guardar_registro()
        return 1

    front = _arrancar("DINAMYT Frontend", "npm run start", FRONTEND)
    if not esperar(PUERTO_FRONTEND, "el frontend", front):
        decir("")
        decir(" El frontend no arranco. Mira la ventana 'DINAMYT Frontend'.")
        decir(" El backend SI quedo arrancado: si no lo vas a usar, APAGAR.bat.")
        guardar_registro()
        return 1

    ips = ips_del_pc()
    decir("")
    decir(SEPARADOR)
    decir(" LISTO. Esta es la direccion para los celulares:")
    decir(SEPARADOR)
    decir("")

    if not ips:
        decir(" NO SE ENCONTRO NINGUNA IP DE RED LOCAL.")
        decir(" El PC no esta conectado al router del evento (o solo por datos).")
        decir(" Conectalo al WiFi/cable del evento y vuelve a arrancar.")
        guardar_registro()
        return 1

    principal = f"http://{ips[0]}:{PUERTO_FRONTEND}"
    en_grande(principal)
    decir("")
    mostrar_qr(principal)

    if len(ips) > 1:
        decir(" Si esa no funciona, este PC tambien responde en:")
        for ip in ips[1:]:
            decir(f"   http://{ip}:{PUERTO_FRONTEND}")
        decir("")

    decir(" Las dos ventanas negras se quedan abiertas: NO LAS TOQUES.")
    decir(" Para apagar del todo: APAGAR.bat")
    registro = guardar_registro()
    if registro:
        print(f"\nQueda escrito en: {registro.name}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nCancelado.")
        guardar_registro()
        sys.exit(1)
