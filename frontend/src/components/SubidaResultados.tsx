"use client";

// ═════════════════════════════════════════════════════════════════════════════
// LOS RESULTADOS QUE FALTAN POR SUBIR A INTERNET (F8 de PLAN-CAMPEONATOS)
//
// En el PC del evento: «2 campeonatos pendientes de subir · último intento
// hace 4 min · [Subir ahora]». Una cola que no se ve es una cola que nadie
// vacía, y el silencio es la avería que más caro ha salido en esta app.
//
// Dice también POR QUÉ no sube, que es lo que alguien necesita saber para
// hacer algo: entrar con DINAMYT, esperar a que acabe el combate, o que la
// instalación no tiene a dónde subir.
//
// En la instalación de internet no pinta nada: no tiene destino ni nada que
// subir. Es lo que hace que la misma pantalla valga en las dos.
// ═════════════════════════════════════════════════════════════════════════════

import { useCallback, useEffect, useState } from "react";
import { estadoSubidaAPI, subirResultadosAPI, type EstadoSubida } from "@/lib/api";
import { useI18n, type ClaveTexto } from "@/lib/i18n";
import { aviso } from "@/lib/toast";

function haceMinutos(iso: string | null): number | null {
  if (!iso) return null;
  const ms = Date.now() - new Date(iso).getTime();
  return Number.isFinite(ms) ? Math.max(0, Math.round(ms / 60000)) : null;
}

export default function SubidaResultados() {
  const { t } = useI18n();
  const [estado, setEstado] = useState<EstadoSubida | null>(null);
  const [subiendo, setSubiendo] = useState(false);

  const cargar = useCallback(async () => {
    try {
      setEstado(await estadoSubidaAPI());
    } catch {
      // Dato de apoyo: si falla, el panel sigue.
    }
  }, []);

  useEffect(() => {
    let cancelado = false;
    queueMicrotask(() => { if (!cancelado) void cargar(); });
    // Mientras la pantalla esté abierta, se relee: la cola se vacía sola en
    // segundo plano y el número tiene que bajar sin recargar.
    const cada = setInterval(() => { void cargar(); }, 60000);
    return () => { cancelado = true; clearInterval(cada); };
  }, [cargar]);

  if (!estado) return null;
  const hay = estado.pendientes.length > 0;
  if (!estado.destino && !hay) return null;

  async function subir() {
    setSubiendo(true);
    try {
      const r = await subirResultadosAPI();
      setEstado(r);
      aviso(r.pendientes.length ? t("subida.quedan", { n: r.pendientes.length }) : t("subida.listo"), "ok");
    } catch (err) {
      const datos = (err as { response?: { data?: EstadoSubida & { error?: string } } }).response?.data;
      if (datos) setEstado(datos);
      aviso(datos?.error || t("subida.error"), "error");
    } finally {
      setSubiendo(false);
    }
  }

  const minutos = haceMinutos(estado.ultimo_intento_at);
  const motivo = estado.motivo ? t(`subida.motivo.${estado.motivo}` as ClaveTexto) : null;

  return (
    <div
      style={{
        display: "flex", flexDirection: "column", gap: 6,
        padding: "10px 14px", marginBottom: 14,
        borderRadius: "var(--radius-sm)",
        border: `1px solid ${hay ? "var(--gold-border)" : "var(--border)"}`,
        background: hay ? "var(--gold-bg)" : "var(--bg-elevated)",
        fontSize: "0.86rem",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <span style={{ fontWeight: 700, flex: "1 1 14rem" }}>
          {hay ? t("subida.pendientes", { n: estado.pendientes.length }) : t("subida.alDia")}
        </span>
        {hay && (
          <button type="button" className="btn btn-sm btn-primary" disabled={subiendo} onClick={subir}>
            {subiendo ? t("subida.subiendo") : t("subida.subirAhora")}
          </button>
        )}
      </div>
      {hay && (
        <div className="text-muted" style={{ overflowWrap: "anywhere" }}>
          {estado.pendientes.map((p) => p.nombre).join(" · ")}
        </div>
      )}
      <div className="text-muted" style={{ fontSize: "0.8rem" }}>
        {[
          estado.destino ? t("subida.destino", { destino: estado.destino }) : null,
          minutos != null ? t("subida.ultimoIntento", { min: minutos }) : null,
        ].filter(Boolean).join(" · ")}
      </div>
      {motivo && hay && (
        <div style={{ color: "var(--gold)", fontWeight: 600 }}>{motivo}</div>
      )}
      {estado.ultimo_error && hay && (
        <div style={{ color: "var(--red-alert)", fontSize: "0.8rem", overflowWrap: "anywhere" }}>
          {t("subida.ultimoError", { error: estado.ultimo_error })}
        </div>
      )}
    </div>
  );
}
