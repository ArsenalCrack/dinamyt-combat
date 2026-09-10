"""
El arrancador del PC del evento (`iniciar_local.py`, en la raíz).

Casi todo lo que hace ese archivo es hablar con Windows —`netstat`, `tasklist`,
`taskkill`— y eso se probó a mano, arrancando y apagando de verdad. Lo que sí
puede romperse en silencio y sin que nadie lo note hasta el 9 de octubre es
**la lectura de la salida de `netstat`**: un formato ligeramente distinto y el
arrancador diría «el puerto está libre» sobre un puerto ocupado, que es
exactamente el fallo que esta fase venía a evitar.

Por eso aquí solo se fija eso, con salida enlatada: sin depender de qué haya
escuchando en la máquina que corre las pruebas.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import iniciar_local  # noqa: E402

# Salida real de `netstat -ano -p TCP`, recortada. Incluye a propósito:
#   · una línea IPv6 del mismo puerto (dos veces el mismo servicio),
#   · un puerto que CONTIENE los dígitos buscados (13000 no es 3000),
#   · una conexión establecida, que no es un servicio escuchando,
#   · la cabecera y una línea en blanco.
NETSTAT = """
Conexiones activas

  Proto  Dirección local        Dirección remota       Estado           PID
  TCP    0.0.0.0:3000           0.0.0.0:0              LISTENING       9120
  TCP    [::]:3000              [::]:0                 LISTENING       9120
  TCP    0.0.0.0:13000          0.0.0.0:0              LISTENING       4444
  TCP    127.0.0.1:3000         127.0.0.1:55110        ESTABLISHED     7777
  TCP    0.0.0.0:5000           0.0.0.0:0              LISTENING       9121
"""


class _Salida:
    def __init__(self, stdout):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = 0


def _con_netstat(monkeypatch, texto=NETSTAT):
    monkeypatch.setattr(
        iniciar_local.subprocess, "run", lambda *a, **k: _Salida(texto)
    )


class TestLeerNetstat:
    def test_encuentra_quien_escucha(self, monkeypatch):
        _con_netstat(monkeypatch)
        assert iniciar_local._pids_escuchando(3000) == ["9120"]
        assert iniciar_local._pids_escuchando(5000) == ["9121"]

    def test_un_puerto_que_contiene_los_digitos_no_cuenta(self, monkeypatch):
        """13000 no es 3000. Se compara el puerto, no el texto de la línea."""
        _con_netstat(monkeypatch)
        assert "4444" not in iniciar_local._pids_escuchando(3000)

    def test_una_conexion_establecida_no_es_un_servicio(self, monkeypatch):
        """Solo LISTENING ocupa el puerto; ESTABLISHED es alguien conectado."""
        _con_netstat(monkeypatch)
        assert "7777" not in iniciar_local._pids_escuchando(3000)

    def test_un_puerto_libre_no_devuelve_nada(self, monkeypatch):
        _con_netstat(monkeypatch)
        assert iniciar_local._pids_escuchando(8080) == []

    def test_sin_netstat_no_revienta(self, monkeypatch):
        """Si el comando falla, el arranque sigue: no puede morir por esto."""
        def _explota(*a, **k):
            raise OSError("no hay netstat")

        monkeypatch.setattr(iniciar_local.subprocess, "run", _explota)
        assert iniciar_local._pids_escuchando(3000) == []
        assert iniciar_local.quien_ocupa(3000) is None


class TestLaDireccion:
    def test_en_grande_enmarca_y_separa(self):
        iniciar_local._registro.clear()
        iniciar_local.en_grande("http://10.0.0.5:3000")
        pintado = iniciar_local._registro

        assert pintado[0].startswith("+") and pintado[0].endswith("+")
        assert pintado[-1] == pintado[0]
        # Las letras van separadas para poder leerlas desde lejos, y el marco
        # tiene que cuadrar con lo que hay dentro.
        assert "h t t p" in pintado[2]
        assert len({len(l) for l in pintado}) == 1

    def test_las_ips_inservibles_se_descartan(self, monkeypatch):
        """169.254.x.x es lo que pone Windows cuando NO hay red.

        Enseñar esa dirección el día del evento manda a treinta personas a
        teclear una IP por la que no contesta nadie.
        """
        monkeypatch.setattr(
            iniciar_local.socket, "getaddrinfo",
            lambda *a, **k: [
                (None, None, None, None, ("127.0.0.1", 0)),
                (None, None, None, None, ("169.254.13.7", 0)),
                (None, None, None, None, ("192.168.0.24", 0)),
                (None, None, None, None, ("192.168.0.24", 0)),
            ],
        )
        # Sin ruta por defecto: el truco del socket UDP no aporta candidata.
        class _SocketMudo:
            def connect(self, *a):
                raise OSError("sin ruta")

            def getsockname(self):
                raise AssertionError("no debería llegar aquí")

            def close(self):
                pass

        monkeypatch.setattr(iniciar_local.socket, "socket", lambda *a, **k: _SocketMudo())

        assert iniciar_local.ips_del_pc() == ["192.168.0.24"]
