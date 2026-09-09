"use client";

import { useCallback, useEffect, useState } from "react";
import { listLlavesTatamiAPI, type LlaveTatamiInfo } from "@/lib/api";
import type { ConfirmData } from "@/components/AlertSystem";
import { useI18n } from "@/lib/i18n";

interface GrupoFigurasActivo {
  llave_id: number;
  nombre: string;
}

/**
 * Panel del Juez Central: grupos de figuras encolados para este tatami.
 * "Activar" carga TODOS los competidores del grupo de golpe en la sesión de
 * figuras (sin agregarlos a mano) y, al guardar la categoría, el grupo queda
 * terminado. Solo se ofrece UNO a la vez; los demás esperan en cola.
 */
export default function GrupoFigurasPanel({
  tatamiDbId, grupoActivo = null, enviarEvento, onShowConfirm,
}: {
  tatamiDbId: string;
  grupoActivo?: GrupoFigurasActivo | null;
  enviarEvento: (accion: string, datos?: Record<string, unknown>) => void;
  onShowConfirm: (data: ConfirmData) => void;
}) {
  const { t } = useI18n();
  const [grupos, setGrupos] = useState<LlaveTatamiInfo[]>([]);
  const [cargado, setCargado] = useState(false);

  const cargar = useCallback(async () => {
    try {
      const data = await listLlavesTatamiAPI(tatamiDbId);
      setGrupos(data.filter((l) => l.tipo === "figuras"));
    } catch { /* sin permisos o sin red: el panel no se muestra */ }
    finally { setCargado(true); }
  }, [tatamiDbId]);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => { if (!cancelled) void cargar(); });
    return () => { cancelled = true; };
  }, [cargar, grupoActivo?.llave_id]);

  // Pendientes en cola (las terminadas y la activa no se ofrecen)
  const pendientes = grupos.filter(
    (g) => g.estado === "pendiente" && (!grupoActivo || g.id !== grupoActivo.llave_id)
  );
  const siguiente = pendientes[0];
  const enCola = pendientes.length - 1;

  if (!cargado || (!grupoActivo && pendientes.length === 0)) return null;

  return (
    <div className="card" style={{ marginBottom: 8, padding: "10px 14px", borderColor: "var(--chung-border)" }}>
      <div className="card-title" style={{ marginBottom: 8 }}>
        {t("gf.titulo")}
      </div>

      {grupoActivo ? (
        <div style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          gap: 10, flexWrap: "wrap",
          padding: "8px 12px", background: "var(--chung-bg)",
          border: "1px solid var(--chung-border)", borderRadius: "var(--radius-sm)",
        }}>
          <div style={{ minWidth: 0 }}>
            {/* Titulo de panel, no micro-etiqueta: lleva dentro el NOMBRE del
                grupo, y un nombre propio en mayusculas forzadas se lee peor.
                Ver la regla en «.microetiqueta» (estilos-ecosistema.css). */}
            <div style={{ fontWeight: 800, color: "var(--chung-light)", fontSize: "0.95rem" }}>
              {t("gf.enCurso", { nombre: grupoActivo.nombre })}
            </div>
            <div style={{ fontSize: "0.8rem", color: "var(--text-dim)", marginTop: 2 }}>
              {t("gf.alGuardar")}
            </div>
          </div>
          <button
            className="btn btn-sm btn-danger"
            onClick={() => onShowConfirm({
              titulo: t("gf.soltar.titulo"),
              mensaje: t("gf.soltar.mensaje", { nombre: grupoActivo.nombre }),
              tipo: "advertencia",
              confirmLabel: t("lp.soltarLabel"),
              cancelLabel: t("comun.cancelar"),
              onConfirm: () => enviarEvento("soltar_grupo_figuras"),
            })}
          >
            {t("lp.soltarBtn")}
          </button>
        </div>
      ) : siguiente ? (
        <div style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          gap: 10, flexWrap: "wrap",
          padding: "8px 12px", background: "var(--bg-elevated)",
          border: "1px solid var(--border)", borderRadius: "var(--radius-sm)",
        }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontWeight: 800, fontSize: "0.9rem", overflowWrap: "anywhere" }}>
              {siguiente.nombre}
              <span style={{ color: "var(--text-dim)", fontWeight: 600, marginLeft: 8, fontSize: "0.82rem" }}>
                {t("gf.competidoresN", { n: siguiente.num_competidores ?? 0 })}
              </span>
            </div>
            {siguiente.descripcion && (
              <div style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginTop: 2, overflowWrap: "anywhere" }}>
                {siguiente.descripcion}
              </div>
            )}
          </div>
          <button
            className="btn btn-sm btn-primary"
            onClick={() => onShowConfirm({
              titulo: t("gf.activar.titulo"),
              mensaje: t("gf.activar.mensaje", { n: siguiente.num_competidores ?? 0, nombre: siguiente.nombre }),
              tipo: "info",
              confirmLabel: t("lp.activarLabel"),
              cancelLabel: t("comun.cancelar"),
              onConfirm: () => enviarEvento("activar_grupo_figuras", { llave_id: siguiente.id }),
            })}
          >
            {t("lp.activarBtn")}
          </button>
        </div>
      ) : null}

      {!grupoActivo && enCola > 0 && (
        <p style={{ color: "var(--text-dim)", fontSize: "0.82rem", margin: "6px 2px 0" }}>
          {t("gf.enCola", { n: enCola })}
        </p>
      )}
    </div>
  );
}
