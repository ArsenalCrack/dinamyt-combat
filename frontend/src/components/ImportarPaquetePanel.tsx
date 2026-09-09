"use client";

// ═════════════════════════════════════════════════════════════════════════════
// IMPORTAR UN PAQUETE DE SINCRONIZACIÓN (local ↔ internet)
//
// Flujo en dos pasos, a propósito: primero se ANALIZA el archivo (el backend
// ejecuta la importación entera y la revierte) y se muestra el informe; solo
// al confirmar se escribe, en una sola transacción. Así nunca queda a medias
// ni sorprende: lo que anuncia la vista previa es lo que va a pasar.
//
// Se usa igual para los tres paquetes (campeonato, usuarios y competidores);
// `conModo` solo se activa para el de campeonato, que es el único donde tiene
// sentido elegir entre fusionar y reemplazar.
// ═════════════════════════════════════════════════════════════════════════════

import { useRef, useState } from "react";
import {
  importarPaqueteAPI,
  type InformeImportacion,
  type ModoImportacion,
} from "@/lib/api";
import { useI18n, type ClaveTexto } from "@/lib/i18n";

const SECCIONES: { clave: keyof InformeImportacion["resumen"]; labelKey: ClaveTexto }[] = [
  { clave: "usuarios", labelKey: "sync.seccion.usuarios" },
  { clave: "competidores", labelKey: "sync.seccion.competidores" },
  { clave: "tatamis", labelKey: "sync.seccion.tatamis" },
  { clave: "asignaciones", labelKey: "sync.seccion.asignaciones" },
  { clave: "inscripciones", labelKey: "sync.seccion.inscripciones" },
  { clave: "llaves", labelKey: "sync.seccion.llaves" },
];

interface Props {
  /** Selector de fusionar/reemplazar (solo para paquetes de campeonato). */
  conModo?: boolean;
  /** Se llama tras una importación real satisfactoria.
   *
   * Puede devolver una promesa (recargar la lista): se espera antes de dar la
   * importación por terminada, para que el aviso de quien llama salga con los
   * datos nuevos ya en pantalla. */
  onImportado?: (informe: InformeImportacion) => void | Promise<void>;
}

export default function ImportarPaquetePanel({ conModo = false, onImportado }: Props) {
  const { t } = useI18n();
  const [archivo, setArchivo] = useState<File | null>(null);
  const [modo, setModo] = useState<ModoImportacion>("fusionar");
  const [forzar, setForzar] = useState(false);
  // `pedirForzar` aparece cuando el backend responde 409 porque el evento ya
  // empezó aquí: es la única vía para insistir, y siempre explícita.
  const [pedirForzar, setPedirForzar] = useState(false);
  const [previa, setPrevia] = useState<InformeImportacion | null>(null);
  const [ocupado, setOcupado] = useState<"analizando" | "importando" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  function reiniciar() {
    setArchivo(null);
    setPrevia(null);
    setError(null);
    setForzar(false);
    setPedirForzar(false);
    if (inputRef.current) inputRef.current.value = "";
  }

  async function ejecutar(vistaPrevia: boolean) {
    if (!archivo) return;
    setOcupado(vistaPrevia ? "analizando" : "importando");
    setError(null);
    try {
      const informe = await importarPaqueteAPI(archivo, { vistaPrevia, modo, forzar });
      if (vistaPrevia) {
        setPrevia(informe);
        setPedirForzar(false);
      } else {
        reiniciar();
        await onImportado?.(informe);
      }
    } catch (err) {
      const respuesta = (err as { response?: { status?: number; data?: { error?: string } } }).response;
      setError(respuesta?.data?.error || t("sync.errorImportar"));
      setPrevia(null);
      // 409 = el evento ya arrancó en esta instalación; se puede insistir.
      if (respuesta?.status === 409) setPedirForzar(true);
    } finally {
      setOcupado(null);
    }
  }

  const secciones = SECCIONES.filter((s) => previa?.resumen?.[s.clave]);

  return (
    <div className="card animate-slide" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <p className="text-muted" style={{ margin: 0, fontSize: "0.88rem" }}>
        {t("sync.importarPanel.desc")}
      </p>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <input
          ref={inputRef}
          type="file"
          accept=".json,application/json"
          aria-label={t("sync.archivoAria")}
          onChange={(e) => {
            setArchivo(e.target.files?.[0] || null);
            setPrevia(null);
            setError(null);
            setPedirForzar(false);
          }}
          style={{ fontSize: "0.88rem", color: "var(--text-muted)", maxWidth: "100%" }}
        />
        <button
          type="button"
          className="btn btn-sm"
          disabled={!archivo || ocupado !== null}
          onClick={() => ejecutar(true)}
        >
          {ocupado === "analizando" ? t("sync.analizando") : t("sync.analizar")}
        </button>
      </div>

      {conModo && (
        <fieldset style={{ border: "none", padding: 0, margin: 0 }}>
          <legend className="microetiqueta" style={{ marginBottom: 6 }}>
            {t("sync.modo")}
          </legend>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {(["fusionar", "reemplazar"] as ModoImportacion[]).map((m) => (
              <label key={m} style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: "0.88rem" }}>
                <input
                  type="radio"
                  name="modo-importacion"
                  checked={modo === m}
                  onChange={() => { setModo(m); setPrevia(null); }}
                  style={{ marginTop: 3 }}
                />
                <span>
                  <strong>{t(`sync.modo.${m}` as ClaveTexto)}</strong>
                  <span className="text-muted" style={{ display: "block", fontSize: "0.82rem" }}>
                    {t(`sync.modo.${m}.desc` as ClaveTexto)}
                  </span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
      )}

      {error && (
        <div role="alert" style={{
          padding: "10px 14px", borderRadius: "var(--radius-sm)", fontSize: "0.88rem",
          border: "1px solid rgba(255,68,68,0.35)", background: "rgba(255,68,68,0.10)",
          color: "var(--red-alert)", fontWeight: 700,
        }}>
          {error}
        </div>
      )}

      {pedirForzar && (
        <label style={{
          display: "flex", gap: 8, alignItems: "flex-start", fontSize: "0.86rem",
          border: "1px solid var(--gold-border)", background: "var(--gold-bg)",
          borderRadius: "var(--radius-sm)", padding: "10px 12px",
        }}>
          <input
            type="checkbox"
            checked={forzar}
            onChange={(e) => setForzar(e.target.checked)}
            style={{ marginTop: 3 }}
          />
          <span>{t("sync.forzar")}</span>
        </label>
      )}

      {previa && (
        <div className="animate-fade" style={{
          border: "1px solid var(--border)", borderRadius: "var(--radius-sm)",
          padding: "12px 14px", display: "flex", flexDirection: "column", gap: 10,
        }}>
          <div>
            <div style={{ fontWeight: 800, color: "var(--gold)" }}>{t("sync.vistaPrevia")}</div>
            <div className="text-muted" style={{ fontSize: "0.85rem" }}>
              {previa.message}
              {previa.origen?.admin && (
                <>
                  {" · "}
                  {t("sync.origen", {
                    admin: previa.origen.admin,
                    fecha: previa.exportado_at
                      ? new Date(previa.exportado_at).toLocaleString()
                      : "—",
                  })}
                </>
              )}
            </div>
          </div>

          {secciones.length === 0 ? (
            <p className="text-muted" style={{ margin: 0, fontSize: "0.88rem" }}>
              {t("sync.sinCambios")}
            </p>
          ) : (
            <ul style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 3 }}>
              {secciones.map(({ clave, labelKey }) => {
                const c = previa.resumen[clave]!;
                return (
                  <li key={clave} style={{ fontSize: "0.88rem" }}>
                    <strong>{t(labelKey)}:</strong>{" "}
                    <span className="text-muted">
                      {t("sync.contadores", {
                        nuevos: c.nuevos,
                        actualizados: c.actualizados,
                        omitidos: c.omitidos,
                      })}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}

          {!!previa.identidades &&
            (previa.identidades.enlazadas > 0 || previa.identidades.omitidas > 0) && (
            <div style={{ fontSize: "0.88rem" }}>
              <strong>{t("sync.identidades")}:</strong>{" "}
              <span className="text-muted">
                {t("sync.identidadesDetalle", {
                  enlazadas: previa.identidades.enlazadas,
                  omitidas: previa.identidades.omitidas,
                })}
              </span>
            </div>
          )}

          {previa.avisos.length > 0 && (
            <div>
              <div style={{ fontWeight: 700, fontSize: "0.84rem", color: "var(--orange)" }}>
                {t("sync.avisos")}
              </div>
              <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                {previa.avisos.map((a, i) => (
                  <li key={i} className="text-muted" style={{ fontSize: "0.84rem" }}>{a}</li>
                ))}
              </ul>
            </div>
          )}

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={ocupado !== null}
              onClick={() => ejecutar(false)}
            >
              {ocupado === "importando" ? t("sync.importando") : t("sync.confirmar")}
            </button>
            <button type="button" className="btn btn-sm" onClick={reiniciar}>
              {t("comun.cancelar")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
