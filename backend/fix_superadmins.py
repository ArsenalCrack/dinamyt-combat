r"""
Corrige el flag de superadmin en la base de datos.

Invariante del sistema: SOLO el admin sembrado (ADMIN_EMAIL, por defecto
admin@dinamyt.org) debe ser superadmin. Cualquier otro admin que tenga
es_superadmin=True es un dato heredado y hace que vea usuarios de otros
workspaces (los jueces del superadmin, etc.).

Este script pone es_superadmin=False en TODOS los admins cuyo email no sea el
superadmin oficial. No toca jueces ni ninguna otra cosa.

USO (una sola vez):

  # Local (SQLite):
  cd backend
  venv/Scripts/python fix_superadmins.py

  # Producción (Postgres de Supabase/Neon) — pega tu connection string real:
  cd backend
  DATABASE_URL="postgresql://USUARIO:PASS@HOST/DB" \
  SUPERADMIN_EMAIL="admin@dinamyt.org" \
  venv/Scripts/python fix_superadmins.py

En PowerShell (Windows), para producción:
  $env:DATABASE_URL="postgresql://USUARIO:PASS@HOST/DB"
  $env:SUPERADMIN_EMAIL="admin@dinamyt.org"
  venv\Scripts\python fix_superadmins.py

Es idempotente: puedes correrlo las veces que quieras.
"""

import os
from sqlalchemy import create_engine, text


def main():
    url = os.getenv("DATABASE_URL", "sqlite:///instance/dinamyt.db")
    # Render/Supabase a veces entregan "postgres://"; SQLAlchemy quiere "postgresql://".
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    keep = os.getenv("SUPERADMIN_EMAIL") or os.getenv("ADMIN_EMAIL") or "admin@dinamyt.org"
    keep = keep.strip().lower()

    destino = "SQLite local" if url.startswith("sqlite") else "Postgres (producción)"
    print(f"BD: {destino}")
    print(f"Superadmin que se conserva: {keep}\n")

    engine = create_engine(url)
    with engine.begin() as cx:
        antes = cx.execute(
            text("SELECT email, es_superadmin FROM usuarios WHERE rol = 'admin' ORDER BY id")
        ).fetchall()
        print("ANTES:")
        for email, es in antes:
            print(f"  {email:<30} superadmin={bool(es)}")

        res = cx.execute(
            text(
                "UPDATE usuarios SET es_superadmin = :falso "
                "WHERE rol = 'admin' AND lower(email) <> :keep AND es_superadmin = :verdad"
            ),
            {"falso": False, "verdad": True, "keep": keep},
        )
        print(f"\nAdmins degradados a normal: {res.rowcount}")

        # Garantiza que el superadmin oficial SÍ lo sea (por si quedó en NULL/False).
        cx.execute(
            text(
                "UPDATE usuarios SET es_superadmin = :verdad "
                "WHERE rol = 'admin' AND lower(email) = :keep"
            ),
            {"verdad": True, "keep": keep},
        )

        despues = cx.execute(
            text("SELECT email, es_superadmin FROM usuarios WHERE rol = 'admin' ORDER BY id")
        ).fetchall()
        print("\nDESPUES:")
        for email, es in despues:
            print(f"  {email:<30} superadmin={bool(es)}")

    print("\n[OK] Listo. Solo el superadmin oficial conserva el privilegio.")


if __name__ == "__main__":
    main()
