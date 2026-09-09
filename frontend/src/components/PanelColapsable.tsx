"use client";

import { useState, type ReactNode } from "react";

/**
 * Sección colapsable para agrupar funciones del panel del Juez Central y
 * reducir el ruido visual. Lo frecuente queda visible; lo de configuración o
 * cierre se abre solo cuando se necesita. Responsiva por defecto.
 */
export default function PanelColapsable({
  titulo, icono, defaultOpen = false, badge, acento = "neutro", children,
}: {
  titulo: string;
  icono?: string;
  defaultOpen?: boolean;
  badge?: string;
  /** Color del borde/encabezado: neutro, oro (config) o rojo (finalizar). */
  acento?: "neutro" | "oro" | "rojo";
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const borde = acento === "oro" ? "var(--gold-border)" : acento === "rojo" ? "var(--hong-border)" : "var(--border)";
  const color = acento === "oro" ? "var(--gold)" : acento === "rojo" ? "var(--hong-light)" : "var(--text)";

  return (
    <div className="card" style={{ padding: 0, marginBottom: 8, overflow: "hidden", borderColor: borde }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        style={{
          display: "flex", alignItems: "center", gap: 8, width: "100%",
          padding: "10px 14px", background: "transparent", border: "none",
          color, cursor: "pointer", font: "inherit", textAlign: "left",
        }}
      >
        {/* Titulo de seccion en frase capital. En MAYUSCULAS y a peso 800
            pesaba igual que el titulo de la tarjeta que lo contiene, y un
            desplegable no compite con la pantalla en la que vive. */}
        <span style={{ fontWeight: 700, fontSize: "0.95rem", flex: 1 }}>
          {icono ? `${icono} ` : ""}{titulo}
        </span>
        {badge && <span className="badge badge-gray">{badge}</span>}
        <span style={{ color: "var(--text-dim)", fontSize: "0.875rem" }}>{open ? "▲" : "▼"}</span>
      </button>
      {open && <div style={{ padding: "0 12px 12px" }}>{children}</div>}
    </div>
  );
}
