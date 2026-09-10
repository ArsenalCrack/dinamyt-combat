"""
Apagar DINAMYT en el PC del evento, de verdad.

El manual decia "cierra las dos ventanas negras". Casi siempre funciona, pero
no siempre: cerrar la ventana mata al `cmd` y deja al servidor vivo, escuchando
en su puerto. El sintoma llega despues y disfrazado — al volver a arrancar, el
puerto 3000 esta ocupado "por nada", o peor: dos backends contra la misma base.

Aqui se apaga por PUERTO, que es lo unico que no miente: se busca quien esta
escuchando en el 5000 y en el 3000, se dice quien es, y se para. Despues se
cierran las ventanas que abrio `iniciar_local.py`.

Sin acentos, misma razon que en `iniciar_local.py`: esto se lee en una consola
de Windows.
"""

import subprocess
import sys

from iniciar_local import (
    PUERTO_BACKEND,
    PUERTO_FRONTEND,
    SEPARADOR,
    _nombre_del_proceso,
    _pids_escuchando,
    decir,
    guardar_registro,
)

# Titulos con los que `iniciar_local.py` abre las dos ventanas.
TITULOS = ("DINAMYT Backend", "DINAMYT Frontend")


def _matar(pid):
    """taskkill del proceso y de sus hijos. True si quedo parado."""
    try:
        r = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as e:
        decir(f"   no se pudo parar el PID {pid}: {e}")
        return False
    if r.returncode == 0:
        return True
    decir(f"   no se pudo parar el PID {pid}: {(r.stdout + r.stderr).strip()}")
    return False


def _cerrar_ventanas():
    """Cierra las dos consolas, que sobreviven a la muerte del servidor.

    Sin esto quedan dos ventanas negras con un proceso muerto dentro, y la
    siguiente persona que mire la pantalla creera que sigue encendido.
    """
    for titulo in TITULOS:
        try:
            subprocess.run(
                ["taskkill", "/FI", f"WINDOWTITLE eq {titulo}*", "/T", "/F"],
                capture_output=True, text=True, timeout=20,
            )
        except (OSError, subprocess.SubprocessError):
            pass


def main():
    decir(SEPARADOR)
    decir(" APAGANDO DINAMYT")
    decir(SEPARADOR)

    parados, habia_algo = 0, False
    for puerto, quien_es in ((PUERTO_FRONTEND, "frontend"), (PUERTO_BACKEND, "backend")):
        pids = _pids_escuchando(puerto)
        if not pids:
            decir(f"  Puerto {puerto} ({quien_es}): ya estaba libre")
            continue
        habia_algo = True
        for pid in pids:
            nombre = _nombre_del_proceso(pid) or "?"
            decir(f"  Puerto {puerto} ({quien_es}): parando {nombre} (PID {pid})")
            if _matar(pid):
                parados += 1

    _cerrar_ventanas()

    decir("")
    if not habia_algo:
        decir(" No habia nada encendido.")
    elif parados:
        decir(f" Parados {parados} proceso(s). Los puertos quedan libres.")
    else:
        decir(" NO SE PUDO PARAR TODO. Reinicia el PC antes de volver a arrancar.")

    registro = guardar_registro()
    if registro:
        print(f"\nQueda escrito en: {registro.name}")
    return 0 if (not habia_algo or parados) else 1


if __name__ == "__main__":
    sys.exit(main())
