"use client";

// ═════════════════════════════════════════════════════════════════════════════
// DE CUÁNDO ES LA COPIA QUE CORRE EN ESTE PC
//
// El sábado a las siete de la mañana la pregunta no es «¿se puede bajar el
// campeonato?» —eso funciona y es re-ejecutable— sino «¿esta copia trae las
// inscripciones del jueves?». El dato existía (el sobre del paquete lo trae),
// pero se enseñaba una vez en la vista previa y se perdía al confirmar.
//
// Si no hay ninguna copia, esto NO pinta nada. Es lo que hace que la misma
// pantalla valga en las dos instalaciones: la de internet no importa nunca, y
// la del gimnasio no tiene nada que enseñar hasta que alguien trae el paquete
// —que es el momento en el que está mirando el informe de la importación—.
// ═════════════════════════════════════════════════════════════════════════════

import { useEffect, useState } from "react";
import { ultimaBajadaAPI, type UltimaBajada as Datos } from "@/lib/api";
import { useI18n, type ClaveTexto } from "@/lib/i18n";

const CONTEOS: { clave: keyof NonNullable<Datos["conteos"]>; labelKey: ClaveTexto }[] = [
  { clave: "usuarios", labelKey: "sync.seccion.usuarios" },
  { clave: "competidores", labelKey: "sync.seccion.competidores" },
  { clave: "inscripciones", labelKey: "sync.seccion.inscripciones" },
  { clave: "llaves", labelKey: "sync.seccion.llaves" },
];

export default function UltimaBajada({ refrescar = 0 }: { refrescar?: number }) {
  const { t } = useI18n();
  const [datos, setDatos] = useState<Datos | null>(null);

  useEffect(() => {
    let cancelado = false;
    ultimaBajadaAPI()
      .then((d) => { if (!cancelado) setDatos(d); })
      // Sin la nota se sigue pudiendo trabajar: es un dato de apoyo, no la
      // pantalla. Un fallo aquí no puede tapar la lista de campeonatos.
      .catch(() => {});
    return () => { cancelado = true; };
  }, [refrescar]);

  if (!datos?.hay) return null;

  const avisar = !!datos.avisar;
  const fecha = datos.exportado_at
    ? new Date(datos.exportado_at).toLocaleString()
    : null;
  const trae = CONTEOS
    .filter(({ clave }) => datos.conteos?.[clave])
    .map(({ clave, labelKey }) => `${datos.conteos![clave]} ${t(labelKey).toLowerCase()}`);

  return (
    <div
      style={{
        display: "flex", flexDirection: "column", gap: 4,
        padding: "10px 14px", marginBottom: 14,
        borderRadius: "var(--radius-sm)",
        border: `1px solid ${avisar ? "var(--gold-border)" : "var(--border)"}`,
        background: avisar ? "var(--gold-bg)" : "var(--bg-elevated)",
        fontSize: "0.86rem",
      }}
    >
      <div style={{ fontWeight: 700 }}>
        {t("sync.copia")}
        {datos.campeonato ? ` · ${datos.campeonato}` : ""}
      </div>
      <div className="text-muted" style={{ overflowWrap: "anywhere" }}>
        {[
          fecha ? t("sync.copiaExportada", { fecha }) : null,
          // Las horas van al lado de la fecha a propósito: «el 7 a las 18:42»
          // no dice nada a las siete de la mañana siguiente; «hace 13 h», sí.
          datos.horas != null ? t("sync.copiaHace", { horas: Math.round(datos.horas) }) : null,
          datos.origen_admin ? t("sync.copiaDe", { admin: datos.origen_admin }) : null,
        ].filter(Boolean).join(" · ")}
      </div>
      {trae.length > 0 && (
        <div className="text-muted">{trae.join(" · ")}</div>
      )}
      {avisar && (
        <div style={{ color: "var(--gold)", fontWeight: 600 }}>
          {t("sync.copiaVieja")}
        </div>
      )}
    </div>
  );
}
