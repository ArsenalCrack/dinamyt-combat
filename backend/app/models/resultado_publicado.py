"""
Modelo: ResultadoPublicado

Snapshot de resultados de un campeonato IMPORTADO desde otra instancia (p. ej.
el software local del evento) para publicarlo en la instancia online.

Flujo: la organización trabaja el campeonato en LOCAL (LAN, fluido, sin depender
de internet). Cada cierto tiempo exporta los resultados a un archivo .json y lo
importa aquí (online). La página pública /resultados muestra estos snapshots
igual que los resultados calculados en vivo.

Se identifica por `export_uuid` (estable por campeonato de origen): reimportar el
mismo campeonato REEMPLAZA el snapshot anterior, no lo duplica.
"""

from datetime import datetime, timezone

from ..extensions import db
from ..timeutil import iso_utc


def sin_uids(resultados):
    """Los resultados tal cual, menos el `competidor_uid` de podios y rankings."""
    limpios = []
    for r in resultados or []:
        if not isinstance(r, dict):
            continue
        r = dict(r)
        for lista in ("podio", "ranking"):
            if isinstance(r.get(lista), list):
                r[lista] = [
                    {k: v for k, v in fila.items() if k != "competidor_uid"}
                    if isinstance(fila, dict) else fila
                    for fila in r[lista]
                ]
        limpios.append(r)
    return limpios


class ResultadoPublicado(db.Model):
    __tablename__ = "resultados_publicados"

    id = db.Column(db.Integer, primary_key=True)
    # UUID del campeonato de origen (viaja en el archivo exportado).
    export_uuid = db.Column(db.String(64), unique=True, nullable=False, index=True)
    nombre = db.Column(db.String(255), nullable=False)
    # El JSON completo: {"resultados": [...], "categorias": [...], "tatamis": [...]}
    payload = db.Column(db.JSON, nullable=False)
    # Metadatos informativos del origen (opcional).
    exportado_at = db.Column(db.String(40), nullable=True)
    importado_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    created_by = db.Column(
        db.Integer, db.ForeignKey("usuarios.id"), nullable=True
    )

    def _resultados(self):
        return (self.payload or {}).get("resultados", []) or []

    def to_selector(self):
        """Fila para el selector público de /resultados."""
        return {
            "id": f"pub:{self.export_uuid}",
            "nombre": self.nombre,
            "num_resultados": len(self._resultados()),
            "publicado": True,
            "importado_at": iso_utc(self.importado_at),
        }

    def to_resultados(self):
        """Misma forma que el endpoint en vivo, para /resultados/campeonato/:id.

        **Sin `competidor_uid`**: el archivo lo trae (desde el 25 sep 2026, para
        que el panel del competidor confirme lo suyo), pero esta vista es
        PÚBLICA y el uid es interno (`app/uid.py`). Se quita al servir, no al
        guardar, porque el panel lo lee del `payload`.
        """
        payload = self.payload or {}
        return {
            "campeonato": {"id": f"pub:{self.export_uuid}", "nombre": self.nombre},
            "resultados": sin_uids(payload.get("resultados", [])),
            "categorias": payload.get("categorias", []),
            "tatamis": payload.get("tatamis", []),
            "publicado": True,
            "importado_at": iso_utc(self.importado_at),
        }

    def __repr__(self):
        return f"<ResultadoPublicado {self.nombre} ({self.export_uuid})>"
