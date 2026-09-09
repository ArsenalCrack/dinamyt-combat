"use client";

import { useCallback, useEffect, useState } from "react";
import { listLlavesTatamiAPI, type LlaveTatamiInfo } from "@/lib/api";
import type { ConfirmData } from "@/components/AlertSystem";
import { useI18n } from "@/lib/i18n";

interface CombateLlaveActivo {
  llave_id: number;
  nombre: string;
  /** Índice de ronda, o "bronce" para el partido por el 3er puesto */
  ronda: number | "bronce";
  partido: number;
  ronda_nombre: string;
  comp1: { id: number; nombre: string };
  comp2: { id: number; nombre: string };
}

/**
 * Panel del Juez Central: combates de eliminación del tatami.
 * - Muestra el siguiente combate sugerido de cada llave asignada al tatami.
 * - "Activar" carga los nombres en el marcador (crono pausado) y al guardar
 *   el ganador avanza automáticamente en la llave.
 * - "Soltar" libera el marcador para un combate suelto.
 */
export default function LlavePanel({
  tatamiDbId, combateLlave, mostrarArbol = false, hayArbol = false,
  enviarEvento, onShowConfirm,
}: {
  tatamiDbId: string;
  combateLlave?: CombateLlaveActivo | null;
  /** El público está viendo el árbol (true) o el marcador (false). */
  mostrarArbol?: boolean;
  /** Hay un árbol cargado para poder mostrarlo al público. */
  hayArbol?: boolean;
  enviarEvento: (accion: string, datos?: Record<string, unknown>) => void;
  onShowConfirm: (data: ConfirmData) => void;
}) {
  const { t } = useI18n();
  const [llaves, setLlaves] = useState<LlaveTatamiInfo[]>([]);
  const [cargado, setCargado] = useState(false);

  const cargar = useCallback(async () => {
    try {
      const data = await listLlavesTatamiAPI(tatamiDbId);
      setLlaves(data);
    } catch { /* sin permisos o sin red: el panel simplemente no se muestra */ }
    finally { setCargado(true); }
  }, [tatamiDbId]);

  // Recargar cuando cambia el combate de llave activo (p. ej. tras guardar,
  // el servidor lo libera y hay que refrescar el "siguiente" sugerido).
  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => { if (!cancelled) void cargar(); });
    return () => { cancelled = true; };
  }, [cargar, combateLlave?.llave_id, combateLlave?.partido]);

  const hayPendientes = llaves.some((l) => l.pendientes > 0 || l.campeon);
  if (!cargado || (!combateLlave && !hayPendientes && !hayArbol)) return null;

  return (
    <div className="card" style={{ marginBottom: 8, padding: "10px 14px", borderColor: "var(--gold-border)" }}>
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        gap: 8, flexWrap: "wrap", marginBottom: 8,
      }}>
        <div className="card-title" style={{ marginBottom: 0 }}>
          {t("lp.titulo")}
        </div>
        {hayArbol && (
          <button
            className="btn btn-sm"
            onClick={() => enviarEvento("mostrar_arbol", { mostrar: !mostrarArbol })}
            title={mostrarArbol
              ? t("lp.titleMarcador")
              : t("lp.titleArbol")}
            style={{
              background: mostrarArbol ? "var(--gold-bg)" : undefined,
              borderColor: mostrarArbol ? "var(--gold-border)" : undefined,
              color: mostrarArbol ? "var(--gold)" : undefined,
              fontSize: "0.82rem",
            }}
          >
            {mostrarArbol ? t("lp.mostrarPuntuacion") : t("lp.mostrarArbol")}
          </button>
        )}
      </div>
      {hayArbol && (
        <p style={{ color: "var(--text-dim)", fontSize: "0.8rem", margin: "0 0 8px" }}>
          {t("lp.publicoVe", { que: mostrarArbol ? t("lp.elArbol") : t("lp.elMarcador") })}
        </p>
      )}

      {combateLlave ? (
        /* ── Combate de llave EN CURSO en este tatami ── */
        <div style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          gap: 10, flexWrap: "wrap",
          padding: "8px 12px", background: "var(--gold-bg)",
          border: "1px solid var(--gold-border)", borderRadius: "var(--radius-sm)",
        }}>
          <div style={{ minWidth: 0 }}>
            {/* Igual que en «GrupoFigurasPanel»: lleva el nombre de la llave y
                el de la ronda, que ya vienen escritos como toca. */}
            <div style={{ fontWeight: 800, color: "var(--gold)", fontSize: "0.95rem" }}>
              {combateLlave.nombre} · {combateLlave.ronda_nombre}
            </div>
            <div style={{ fontSize: "0.9rem", marginTop: 2 }}>
              <span style={{ color: "var(--hong-light)", fontWeight: 700 }}>{combateLlave.comp1.nombre}</span>
              <span style={{ color: "var(--text-dim)" }}> {t("lp.rojo")} vs </span>
              <span style={{ color: "var(--chung-light)", fontWeight: 700 }}>{combateLlave.comp2.nombre}</span>
              <span style={{ color: "var(--text-dim)" }}> {t("lp.azul")}</span>
            </div>
            <div style={{ fontSize: "0.8rem", color: "var(--text-dim)", marginTop: 2 }}>
              {t("lp.avanzaAuto")}
            </div>
          </div>
          <button
            className="btn btn-sm btn-danger"
            onClick={() => onShowConfirm({
              titulo: t("lp.soltar.titulo"),
              mensaje: t("lp.soltar.mensaje"),
              tipo: "advertencia",
              confirmLabel: t("lp.soltarLabel"),
              cancelLabel: t("comun.cancelar"),
              onConfirm: () => enviarEvento("soltar_combate_llave"),
            })}
          >
            {t("lp.soltarBtn")}
          </button>
        </div>
      ) : (
        /* ── Llaves con combates pendientes: solo UNA a la vez para no
              saturar al JC; las demás esperan en cola ── */
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {/* Terminadas: con campeón y sin partidos pendientes (incluido el bronce) */}
          {llaves.filter((l) => l.campeon && l.pendientes === 0).map((llave) => (
            <div key={llave.id} style={{
              padding: "8px 12px", background: "var(--bg-elevated)",
              border: "1px solid var(--border)", borderRadius: "var(--radius-sm)",
            }}>
              <div style={{ fontWeight: 800, fontSize: "0.9rem" }}>{llave.nombre}</div>
              <div style={{ fontSize: "0.875rem", color: "var(--gold)", fontWeight: 800, marginTop: 2 }}>
                {t("lp.campeonLabel")} {llave.campeon!.nombre}
              </div>
            </div>
          ))}

          {(() => {
            // Activable mientras quede un partido por jugar (final o bronce),
            // aunque el campeón ya esté definido.
            const pendientes = llaves.filter((l) => l.siguiente && l.pendientes > 0);
            const llave = pendientes[0];
            if (!llave) return null;
            const enCola = pendientes.length - 1;
            return (
              <>
                <div key={llave.id} style={{
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  gap: 10, flexWrap: "wrap",
                  padding: "8px 12px", background: "var(--bg-elevated)",
                  border: "1px solid var(--border)", borderRadius: "var(--radius-sm)",
                }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 800, fontSize: "0.9rem" }}>
                      {llave.nombre}
                      <span style={{ color: "var(--text-dim)", fontWeight: 600, marginLeft: 8, fontSize: "0.82rem" }}>
                        {t("lp.pendientesN", { n: llave.pendientes })}
                      </span>
                    </div>
                    <div style={{ fontSize: "0.875rem", marginTop: 2 }}>
                      <span style={{ color: "var(--text-dim)" }}>{t("lp.sigue", { ronda: llave.siguiente!.ronda_nombre })} </span>
                      <span style={{ color: "var(--hong-light)", fontWeight: 700 }}>{llave.siguiente!.comp1.nombre}</span>
                      <span style={{ color: "var(--text-dim)" }}> vs </span>
                      <span style={{ color: "var(--chung-light)", fontWeight: 700 }}>{llave.siguiente!.comp2.nombre}</span>
                    </div>
                  </div>
                  <button
                    className="btn btn-sm btn-primary"
                    onClick={() => onShowConfirm({
                      titulo: t("lp.activar.titulo"),
                      mensaje: t("lp.activar.mensaje", {
                        llave: llave.nombre,
                        ronda: llave.siguiente?.ronda_nombre ?? "",
                        c1: llave.siguiente?.comp1.nombre ?? "",
                        c2: llave.siguiente?.comp2.nombre ?? "",
                      }),
                      tipo: "info",
                      confirmLabel: t("lp.activarLabel"),
                      cancelLabel: t("comun.cancelar"),
                      onConfirm: () => enviarEvento("activar_combate_llave", { llave_id: llave.id }),
                    })}
                  >
                    {t("lp.activarBtn")}
                  </button>
                </div>
                {enCola > 0 && (
                  <p style={{ color: "var(--text-dim)", fontSize: "0.82rem", margin: "2px 2px 0" }}>
                    {t("lp.enCola", { n: enCola })}
                  </p>
                )}
              </>
            );
          })()}
        </div>
      )}
    </div>
  );
}
